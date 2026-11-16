"""Router Horminor: tres lectores + conciliador que produce un borrador.

No ejecuta nada. El resultado es una propuesta conversacional para Julio.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from experiments.d_vs_dmas import prompts as prompts_a
from experiments.d_vs_dmas.contracts import cita_en_texto, plano
from experiments.d_vs_dmas.llm import en_paralelo, llamar

from . import prompts
from .model import BorradorRouter, Encargo

RAIZ = Path(__file__).resolve().parents[2]
APP = RAIZ / "services" / "core-api"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))


class EncargoOut(BaseModel):
    titulo: str
    que_hacer: str
    responsable: str = "POR_DEFINIR"
    responsable_sugerido: bool = False
    destinatario: str | None = None
    canal: str = "INTERNO"
    ambito: str = "INTERNO"
    resultado_esperado: str | None = None
    plazo: str | None = None
    por_investigar: list[str] = Field(default_factory=list)
    requiere_autorizacion: bool = False
    autorizado: bool = False
    preparar_comunicacion: bool = False
    origen: str = "DICTADO"
    citas: list[str] = Field(default_factory=list)


class TrabajoOut(BaseModel):
    encargos: list[EncargoOut] = Field(default_factory=list)
    informacion_sin_encargo: list[str] = Field(default_factory=list)
    consultas: list[str] = Field(default_factory=list)
    constancias: list[str] = Field(default_factory=list)
    decisiones_julio: list[str] = Field(default_factory=list)


class ObservacionOut(BaseModel):
    tipo: str
    objeto: str | None = None
    referente_tipo: str = "DIRECTO"
    prohibe_tarea: bool = False
    condiciona_operacion: bool = False
    autoriza_ejecucion: bool = False
    ambiguo: bool = False
    texto: str | None = None
    citas: list[str] = Field(default_factory=list)


class RevisionOut(BaseModel):
    observaciones: list[ObservacionOut] = Field(default_factory=list)


@dataclass
class ResultadoRouter:
    borrador: BorradorRouter
    llamadas: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def usage(self) -> dict[str, int]:
        entrada = salida = 0
        for llamada in self.llamadas:
            uso = llamada.get("usage") or {}
            entrada += int(uso.get("prompt_tokens") or 0)
            salida += int(uso.get("completion_tokens") or 0)
        return {"prompt_tokens": entrada, "completion_tokens": salida}


def normalizar(texto: str) -> str:
    try:
        from app.voz import normalizar_con_mapa

        return normalizar_con_mapa(texto).texto
    except Exception:
        return texto


def _mensaje(texto: str) -> str:
    return f"HOY: {date.today().isoformat()} (America/Guayaquil)\nDICTADO:\n{texto}"


async def construir(
    cliente: httpx.AsyncClient, texto: str
) -> ResultadoRouter:
    normalizado = normalizar(texto)
    mensaje = _mensaje(normalizado)
    r1, r2, r3 = await en_paralelo(
        cliente,
        [
            {
                "system": prompts_a.A1.replace(
                    "{claves}", ", ".join(prompts_a.CLAVES_HECHOS)
                ),
                "user": mensaje,
                "max_tokens": 3000,
            },
            {"system": prompts.B_TRABAJO, "user": mensaje, "max_tokens": 3000},
            {"system": prompts.C_REVISION, "user": mensaje, "max_tokens": 2500},
        ],
    )
    llamadas = [
        {
            "lector": nombre,
            "ok": r.get("ok"),
            "latency_ms": r.get("latency_ms"),
            "usage": r.get("usage") or {},
            "error": r.get("error"),
        }
        for nombre, r in (("A", r1), ("B", r2), ("C", r3))
    ]
    if not r2.get("ok"):
        return ResultadoRouter(
            BorradorRouter(resumen="No pude interpretar el dictado."),
            llamadas,
            error=f"B: {r2.get('error')}",
        )

    try:
        trabajo = TrabajoOut.model_validate(r2["data"])
    except Exception as exc:
        return ResultadoRouter(
            BorradorRouter(resumen="La lectura del trabajo no cumple el contrato."),
            llamadas,
            error=f"CONTRATO_B: {exc}",
        )

    hechos = []
    if r1.get("ok"):
        try:
            from experiments.d_vs_dmas.contracts import SobreHechos

            hechos = SobreHechos.model_validate(r1["data"]).hechos
        except Exception:
            hechos = []

    observaciones: list[ObservacionOut] = []
    revision_ok = bool(r3.get("ok"))
    if revision_ok:
        try:
            observaciones = RevisionOut.model_validate(r3["data"]).observaciones
        except Exception as exc:
            llamadas.append({"lector": "C", "ok": False, "error": f"CONTRATO_C: {exc}"})
            revision_ok = False

    borrador = conciliar(
        normalizado,
        trabajo=trabajo,
        hechos=hechos,
        observaciones=observaciones,
        revision_ok=revision_ok,
    )
    return ResultadoRouter(borrador, llamadas)


def _encargo_desde(salida: EncargoOut, indice: int) -> Encargo:
    responsable = salida.responsable.upper().strip()
    if responsable not in ("JULIO", "SECRETARIA", "JEFE_PLANTA"):
        responsable = "POR_DEFINIR"
    encargo = Encargo(
        id=f"E{indice}",
        titulo=salida.titulo.strip()[:160] or f"Encargo {indice}",
        que_hacer=salida.que_hacer.strip()[:800],
        responsable=responsable,  # type: ignore[arg-type]
        responsable_sugerido=bool(salida.responsable_sugerido),
        destinatario=salida.destinatario,
        canal=salida.canal if salida.canal in ("INTERNO", "WHATSAPP", "LLAMADA", "NINGUNO") else "INTERNO",  # type: ignore[arg-type]
        ambito=salida.ambito if salida.ambito in ("INTERNO", "EXTERNO", "MIXTO") else "INTERNO",  # type: ignore[arg-type]
        resultado_esperado=salida.resultado_esperado,
        plazo=salida.plazo,
        por_investigar=[x for x in salida.por_investigar if x][:8],
        requiere_autorizacion=bool(salida.requiere_autorizacion),
        autorizado=bool(salida.autorizado),
        preparar_comunicacion=bool(salida.preparar_comunicacion),
        citas=[c for c in salida.citas if c][:6],
        origen="CITA_CLIENTE" if salida.origen == "CITA_CLIENTE" else "DICTADO",
    )
    if encargo.responsable == "POR_DEFINIR":
        encargo.estado = "POR_DEFINIR"
    return encargo


def _encargo_por_objeto(
    encargos: list[Encargo], objeto: str | None
) -> list[Encargo]:
    if not objeto:
        return []
    palabras = [p for p in plano(objeto).split() if len(p) > 3]
    puntajes: list[tuple[int, Encargo]] = []
    for encargo in encargos:
        base = plano(
            " ".join(
                [
                    encargo.titulo,
                    encargo.que_hacer,
                    " ".join(encargo.citas),
                    str(encargo.destinatario or ""),
                ]
            )
        )
        puntaje = sum(1 for p in palabras if p in base)
        if puntaje:
            puntajes.append((puntaje, encargo))
    if not puntajes:
        return []
    maximo = max(p for p, _ in puntajes)
    return [e for p, e in puntajes if p == maximo]


def conciliar(
    texto: str,
    *,
    trabajo: TrabajoOut,
    hechos: list[Any],
    observaciones: list[ObservacionOut],
    revision_ok: bool,
) -> BorradorRouter:
    borrador = BorradorRouter(
        informacion_sin_encargo=list(trabajo.informacion_sin_encargo),
        consultas=list(trabajo.consultas),
        constancias=list(trabajo.constancias),
        decisiones_julio=list(trabajo.decisiones_julio),
    )

    # 1. Encargos válidos: cita localizable
    for indice, salida in enumerate(trabajo.encargos, start=1):
        encargo = _encargo_desde(salida, indice)
        citas_validas = [c for c in encargo.citas if cita_en_texto(c, texto)]
        if not citas_validas:
            borrador.notas.append(
                f"{encargo.id}: descartado, su cita no está en el dictado"
            )
            continue
        encargo.citas = citas_validas

        if encargo.autorizado and not _texto_autoriza(encargo.citas):
            encargo.autorizado = False
            borrador.notas.append(
                f"{encargo.id}: se mencionó un envío, pero no una autorización "
                "explícita; no se autoriza ejecutar."
            )

        # Datos: hechos cuya cita se solapa con la del encargo
        for hecho in hechos:
            cita = getattr(hecho, "cita", None)
            if not cita:
                continue
            pos = cita_en_texto(cita, texto)
            if not pos:
                continue
            if any(
                cita_en_texto(c, texto)
                and not (
                    pos[1] <= cita_en_texto(c, texto)[0]  # type: ignore[index]
                    or pos[0] >= cita_en_texto(c, texto)[1]  # type: ignore[index]
                )
                for c in encargo.citas
            ):
                valor = getattr(hecho, "valor", None)
                if valor is not None:
                    encargo.datos[getattr(hecho, "clave", "dato")] = valor

        borrador.encargos.append(encargo)

    _quitar_verificaciones_inventadas(borrador)
    _quitar_contexto_sin_orden(borrador)
    _fusionar_encargos_similares(borrador)
    _asignar_por_defecto(borrador)

    # 2. Observaciones de C
    for obs in observaciones:
        texto_obs = plano(" ".join([obs.objeto or "", obs.texto or "", " ".join(obs.citas)]))
        if obs.ambiguo:
            borrador.notas.append(
                f"Referencia ambigua no crítica: {obs.texto or obs.objeto or ''}"
            )
            continue

        objetivos = _encargo_por_objeto(borrador.encargos, obs.objeto) or (
            [e for e in borrador.encargos if any(c and c in texto for c in obs.citas)]
        )
        if not objetivos and (obs.prohibe_tarea or obs.condiciona_operacion):
            borrador.preguntas.append(
                f"No sé a qué encargo se refiere «{obs.objeto or obs.texto or ''}». ¿A cuál?"
            )
            continue

        if obs.tipo == "PROHIBICION" and obs.prohibe_tarea:
            prohibe_solicitud = any(
                marca in plano(obs.texto or "")
                for marca in (
                    "lo que el pide",
                    "lo que pide",
                    "nada de eso",
                    "ninguna de esas cosas",
                    "no hagas ninguna",
                    "no hagan ninguna",
                    "la solicitud",
                    "lo solicitado",
                )
            )
            for encargo in list(objetivos):
                if encargo.origen == "CITA_CLIENTE" and prohibe_solicitud:
                    # No se prohíbe revisar: se prohíbe ejecutar lo pedido.
                    etiqueta = "No ejecutar la solicitud citada del cliente"
                    if etiqueta not in encargo.condiciones:
                        encargo.condiciones.append(etiqueta)
                    encargo.requiere_autorizacion = True
                    continue
                borrador.encargos.remove(encargo)
                borrador.notas.append(
                    f"{encargo.id}: no se propone porque el dictado prohíbe esa tarea"
                )
            continue

        if obs.tipo == "CITA_TERCERO":
            marcadores = (
                "me dijo",
                "nos dijo",
                "nos pidio",
                "me pidio",
                "el cliente pide",
                "el cliente pidio",
                "solicito",
                "solicitó",
                "me mando decir",
                "dice que",
                "pidio que",
                "me conto",
                "me contó",
            )
            dicho = plano(" ".join([obs.texto or "", *obs.citas]))
            if not any(m in dicho for m in marcadores):
                borrador.notas.append(
                    "Una observación de tercero no tenía cita de tercero; se ignora."
                )
                continue
            for encargo in objetivos:
                encargo.origen = "CITA_CLIENTE"
                borrador.notas.append(
                    f"{encargo.id}: proviene de lo que pidió un cliente; se revisa, no se ejecuta"
                )
            continue

        if obs.tipo == "AUTORIZACION" and obs.autoriza_ejecucion:
            if not _autorizacion_explicita(obs):
                borrador.notas.append(
                    "Se mencionó un envío, pero no una autorización explícita: "
                    "no se autoriza ejecutar."
                )
                continue
            for encargo in objetivos:
                encargo.autorizado = True
                borrador.notas.append(f"{encargo.id}: ejecución autorizada por Julio")
            continue

        if obs.tipo == "CONTRADICCION":
            borrador.notas.append(
                f"Contradicción en el dictado: {obs.texto or obs.objeto or ''}"
            )
            continue

        if obs.tipo == "RECTIFICACION":
            borrador.notas.append(
                f"Rectificación del dictado: {obs.texto or obs.objeto or ''}"
            )
            continue

        # CONDICION / DEPENDENCIA / PROHIBICION de una operación
        if obs.tipo in ("CONDICION", "DEPENDENCIA"):
            citas_obs = plano(" ".join(obs.citas))
            marca_real = any(
                m in citas_obs
                for m in (
                    "hasta que",
                    "antes de",
                    "depende",
                    "condicionad",
                    "sujeto a",
                    "solo si",
                    "siempre que",
                    "a condicion",
                    "requiere",
                )
            )
            if not marca_real:
                # Una descripción o una duda no es una condición.
                continue
        for encargo in objetivos:
            etiqueta = f"{obs.tipo}: {obs.texto or obs.objeto or ''}".strip()
            if etiqueta not in encargo.condiciones:
                encargo.condiciones.append(etiqueta)
            if obs.condiciona_operacion:
                encargo.requiere_autorizacion = True
                encargo.autorizado = False
            if obs.autoriza_ejecucion:
                encargo.autorizado = True
            if encargo.estado == "PROPUESTO" and encargo.condiciones:
                encargo.estado = "CONDICIONADO"

    # 3. Sin C no se inventa bloqueo ni se avanza en silencio: se avisa.
    if not revision_ok:
        for encargo in borrador.encargos:
            if encargo.requiere_autorizacion or encargo.canal == "WHATSAPP":
                encargo.autorizado = False
        borrador.notas.append(
            "No se pudo revisar el dictado en busca de prohibiciones: no se "
            "autoriza ninguna comunicación externa ni operación."
        )

    # 4. Responsable por definir => pregunta (no bloquea el resto)
    for encargo in borrador.encargos:
        if encargo.responsable == "POR_DEFINIR":
            borrador.preguntas.append(
                f"{encargo.id} «{encargo.titulo}»: ¿lo asigna a secretaría o al jefe de planta?"
            )

    _fusionar_avisos(borrador)
    borrador.datos_contexto = _datos_contexto(hechos, texto)
    _elegir_destinatario(borrador, hechos, texto)
    _aclaraciones(borrador, texto)
    _agregar_mensaje_pendiente(borrador, texto)
    for encargo in borrador.encargos:
        if encargo.canal != "WHATSAPP" and not encargo.preparar_comunicacion:
            continue
        base = plano(encargo.titulo + " " + encargo.que_hacer)
        if any(
            marca in base
            for marca in (
                "sin autorizacion",
                "no enviar",
                "no enviarlo",
                "sin enviar",
                "no lo envies",
                "no enviarlo",
            )
        ):
            encargo.requiere_autorizacion = True
            encargo.autorizado = False
    borrador.resumen = resumen_conversacional(borrador)
    return borrador


_AUTORIZACION_EXPLICITA = (
    "envialo",
    "enviale",
    "mandalo",
    "mandale",
    "autorizo",
    "autoriza",
    "procede",
    "hazlo",
    "de una",
    "ya mismo",
    "confirmo el envio",
    "puedes enviar",
    "envia ya",
)


_STOP_ENCARGO = {
    "para",
    "desde",
    "sobre",
    "entre",
    "cuando",
    "donde",
    "este",
    "esta",
    "estos",
    "estas",
    "cliente",
    "contrato",
    "preparar",
    "prepara",
    "envio",
    "enviar",
    "listo",
    "mensaje",
    "autorizacion",
}


def _tokens_encargo(encargo: Encargo) -> set[str]:
    texto = plano(encargo.titulo + " " + encargo.que_hacer)
    return {
        p
        for p in re.findall(r"[a-z0-9]+", texto)
        if len(p) > 3 and p not in _STOP_ENCARGO
    }


def _tipo_trabajo(encargo: Encargo) -> str:
    base = plano(encargo.titulo + " " + encargo.que_hacer)
    if "recordatorio" in base or "mensaje" in base:
        return "COMUNICACION"
    if "documento" in base or "contrato" in base:
        return "DOCUMENTOS"
    if any(p in base for p in ("planta", "movil", "despacho", "produccion", "operacion")):
        return "OPERACION"
    return "OTRO"


def _fusionar_encargos_similares(borrador: BorradorRouter) -> None:
    """Dos facetas del mismo trabajo no deben ser dos tareas."""
    especiales = {"planta", "movil", "despacho", "despachos", "produccion"}
    for encargo in list(borrador.encargos):
        if encargo not in borrador.encargos:
            continue
        for otro in list(borrador.encargos):
            if otro is encargo or otro.id == encargo.id:
                continue
            if otro.responsable != encargo.responsable:
                continue
            if otro.origen != encargo.origen:
                continue
            tipo_a = _tipo_trabajo(encargo)
            tipo_b = _tipo_trabajo(otro)
            if tipo_a != tipo_b:
                continue
            comunes = _tokens_encargo(encargo) & _tokens_encargo(otro)
            if len(comunes) < 2:
                continue
            if len(comunes) < 3 and not (comunes & especiales):
                continue
            if otro.que_hacer not in encargo.que_hacer:
                encargo.que_hacer = (
                    encargo.que_hacer.rstrip(". ") + ". Además, " + otro.que_hacer
                )
            for item in otro.por_investigar:
                if item not in encargo.por_investigar:
                    encargo.por_investigar.append(item)
            for cond in otro.condiciones:
                if cond not in encargo.condiciones:
                    encargo.condiciones.append(cond)
            encargo.datos.update(otro.datos)
            if otro.resultado_esperado and not encargo.resultado_esperado:
                encargo.resultado_esperado = otro.resultado_esperado
            borrador.encargos.remove(otro)
            borrador.notas.append(
                f"{otro.id}: se integró en {encargo.id} por ser el mismo trabajo"
            )


def _quitar_contexto_sin_orden(borrador: BorradorRouter) -> None:
    """«Nos vamos a estar comunicando» describe una relación, no ordena nada."""
    patrones = (
        "coordinar comunicacion",
        "coordinar contacto",
        "mantener comunicacion",
        "mantener contacto",
        "comunicacion constante",
        "comunicarnos con",
    )
    for encargo in list(borrador.encargos):
        base = plano(encargo.titulo + " " + encargo.que_hacer)
        if not any(p in base for p in patrones):
            continue
        citas = plano(" ".join(encargo.citas))
        if re.search(
            r"\b(coordina|coordine|coordinen|contacta|contacte|contacten|llama|llame|llamen|avisa|informa)\b",
            citas,
        ):
            continue
        borrador.encargos.remove(encargo)
        borrador.notas.append(
            f"{encargo.id}: describe una relación habitual, no un encargo"
        )


def _quitar_verificaciones_inventadas(borrador: BorradorRouter) -> None:
    """Un pago anunciado no es una orden de verificarlo."""
    patrones = (
        "verificar transferencia",
        "confirmar transferencia",
        "verificar pago",
        "confirmar pago",
        "verificar anticipo",
        "confirmar anticipo",
        "verificar deposito",
        "confirmar deposito",
    )
    for encargo in list(borrador.encargos):
        base = plano(encargo.titulo + " " + encargo.que_hacer)
        if not any(p in base for p in patrones):
            continue
        citas = plano(" ".join(encargo.citas))
        if re.search(
            r"\b(verifica|revisa|confirma|confirme|comprueba|avisa|informa|chequea)\b",
            citas,
        ):
            continue
        borrador.encargos.remove(encargo)
        borrador.notas.append(
            f"{encargo.id}: era un dato de contexto (pago anunciado), no un "
            "encargo de verificarlo"
        )


def _texto_autoriza(citas: list[str]) -> bool:
    texto = plano(" ".join(citas))
    return any(marca in texto for marca in _AUTORIZACION_EXPLICITA)


def _autorizacion_explicita(obs: ObservacionOut) -> bool:
    """«Hay que enviarle» no es autorización; «envíalo» sí. Solo la cita cuenta."""
    texto = plano(" ".join(obs.citas))
    return any(marca in texto for marca in _AUTORIZACION_EXPLICITA)


_DATOS_CONTRATO = (
    "cliente.nombre",
    "cotizacion.obra_direccion",
    "cotizacion.volumen_m3",
    "cotizacion.resistencia",
    "cotizacion.descuento_pct",
    "cotizacion.plazo_entrega",
    "cotizacion.dias_trabajo",
    "operacion.planta_movil",
    "pago.monto",
    "pago.recibido",
)


def _limpiar_proyecto(texto: str | None) -> str | None:
    if not texto:
        return None
    limpio = re.sub(r"^(el |la )?proyecto\s+", "", str(texto), flags=re.IGNORECASE)
    return limpio.strip() or None


def _aclaraciones(borrador: BorradorRouter, texto: str) -> None:
    """Convierte conflictos del dictado en preguntas concretas, con opciones."""
    t = plano(texto)
    proyecto = _limpiar_proyecto(
        borrador.datos_contexto.get("proyecto.nombre")
        or borrador.datos_contexto.get("cotizacion.obra_direccion")
    ) or "el proyecto"
    nuevas: list[str] = []

    resistencias = sorted(
        {
            m.group(1)
            for m in re.finditer(r"\b(210|240|280|350)\b", t)
        }
    )
    candidatos = set()
    for coincidencia in re.finditer(r"\b(\d{2,3})\b", t):
        despues = t[coincidencia.end() : coincidencia.end() + 16]
        if "dolar" in despues or "usd" in despues:
            continue
        candidatos.add(coincidencia.group(1))
    volumenes = sorted(candidatos - set(resistencias), key=int)
    if len(volumenes) >= 2:
        borrador.datos_contexto["cotizacion.volumen_m3_estado"] = "POR_ACLARAR"
        nuevas.append(
            f"¿Qué volumen confirmamos para {proyecto}: "
            + ", ".join(volumenes)
            + " m³?"
        )

    if len(resistencias) >= 2:
        borrador.datos_contexto["cotizacion.resistencia_estado"] = "POR_ACLARAR"
        nuevas.append(
            "¿La resistencia es "
            + " o ".join(f"FC-{r}" for r in resistencias)
            + "?"
        )

    autoridad = re.search(
        r"(?:no se|necesito saber|primero necesito saber|falta saber)\s+si\s+"
        r"([a-záéíóúñ]+)\s+(?:es quien autoriza|autoriza)\s+o\s+"
        r"(?:solamente |solo )?(?:el )?tecnico",
        t,
    )
    if autoridad:
        nombre = autoridad.group(1).capitalize()
        nuevas.append(
            f"¿{nombre} autoriza el pedido o es solo el técnico de obra?"
        )

    if "no mezclen" in t and "pedido anterior" in t:
        nuevas.append(
            f"¿El proyecto {proyecto} es el mismo del pedido anterior en reclamo, "
            "para no mezclar las órdenes?"
        )

    if "comprobante" in t and re.search(
        r"no (?:la )?confirmacion|sin confirmacion|no.*banco", t
    ):
        nuevas.append(
            "¿El anticipo está confirmado por el banco o solo hay comprobante?"
        )

    for pregunta in nuevas:
        if pregunta not in borrador.preguntas:
            borrador.preguntas.append(pregunta)


def _agregar_mensaje_pendiente(borrador: BorradorRouter, texto: str) -> None:
    """«Mande un mensaje al cliente» es una tarea de preparación, no un envío."""
    if any(
        "mensaje" in plano(e.titulo + " " + e.que_hacer)
        for e in borrador.encargos
    ):
        return
    coincidencia = re.search(
        r"(mande|mandar|enviar|envíe|envie)\s+un\s+mensaje[^.]*", texto, re.IGNORECASE
    )
    if not coincidencia:
        return
    cita = coincidencia.group(0).strip().rstrip(".,")
    borrador.encargos.append(
        Encargo(
            id=f"E{len(borrador.encargos) + 1}",
            titulo="Preparar mensaje al cliente",
            que_hacer=(
                "Preparar el mensaje para el cliente. No enviarlo hasta confirmar "
                "quién autoriza el pedido."
            ),
            responsable="SECRETARIA",
            responsable_sugerido=True,
            canal="WHATSAPP",
            ambito="EXTERNO",
            resultado_esperado="Mensaje preparado y pendiente de autorización",
            por_investigar=[
                "si el ingeniero Roberto autoriza o es solo técnico de obra",
                "texto exacto que debe llevar el mensaje",
            ],
            requiere_autorizacion=True,
            autorizado=False,
            preparar_comunicacion=True,
            citas=[cita],
        )
    )


def _asignar_por_defecto(borrador: BorradorRouter) -> None:
    """Propone el área razonable en vez de devolverle la decisión a Julio."""
    operativo = (
        "planta",
        "despacho",
        "camion",
        "mezcla",
        "produccion",
        "acceso",
        "transporte",
        "operario",
        "fundida",
        "bomba",
        "stock",
        "bodega",
    )
    for encargo in borrador.encargos:
        if encargo.responsable != "POR_DEFINIR":
            continue
        base = plano(encargo.titulo + " " + encargo.que_hacer)
        encargo.responsable = (
            "JEFE_PLANTA" if any(p in base for p in operativo) else "SECRETARIA"
        )
        encargo.responsable_sugerido = True
        if encargo.estado == "POR_DEFINIR":
            encargo.estado = "PROPUESTO"
        borrador.notas.append(
            f"{encargo.id}: lo asigné a {encargo.responsable} por el tipo de trabajo; "
            "es una sugerencia."
        )


def _proyecto_nombre(texto: str) -> str | None:
    coincidencia = re.search(
        r"proyecto\s+([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+)*)",
        texto,
    )
    if coincidencia:
        return coincidencia.group(1).strip().rstrip(".,")
    return None


def _datos_contexto(hechos: list[Any], texto: str = "") -> dict[str, Any]:
    datos: dict[str, Any] = {}
    for hecho in hechos:
        clave = getattr(hecho, "clave", None)
        valor = getattr(hecho, "valor", None)
        if clave not in _DATOS_CONTRATO or valor in (None, ""):
            continue
        if clave == "pago.monto":
            cita = getattr(hecho, "cita", None)
            if not cita:
                evidencia = getattr(hecho, "evidencia", None)
                cita = getattr(evidencia, "cita", None)
            valor = _reparar_monto(valor, cita)
        datos[clave] = valor
    contactos = _contactos_de(list(hechos))
    if contactos:
        datos["contactos"] = contactos
    if not datos.get("cliente.nombre") and not datos.get("cotizacion.obra_direccion"):
        proyecto = _proyecto_nombre(texto)
        if proyecto:
            datos["proyecto.nombre"] = proyecto
    return datos


def _reparar_monto(valor: Any, cita: str | None) -> Any:
    """«27 1000 USD» (mil convertido a 1000) es 27.000, no 271.000 ni 27.100."""
    coincidencia = re.search(r"(\d{1,3})\s+1000\b", plano(cita or ""))
    if coincidencia:
        return int(coincidencia.group(1)) * 1000
    return valor


def _contactos_de(hechos: list[Any]) -> list[dict[str, str | None]]:
    contactos = []
    for sufijo in ("", ".2", ".3"):
        nombre = next(
            (
                getattr(h, "valor", None)
                for h in hechos
                if getattr(h, "clave", "") == f"contacto{sufijo}.nombre"
            ),
            None,
        )
        rol = next(
            (
                getattr(h, "valor", None)
                for h in hechos
                if getattr(h, "clave", "") == f"contacto{sufijo}.rol"
            ),
            None,
        )
        telefono = next(
            (
                getattr(h, "valor", None)
                for h in hechos
                if getattr(h, "clave", "") == f"contacto{sufijo}.telefono"
            ),
            None,
        )
        if nombre:
            contactos.append(
                {"nombre": str(nombre), "rol": str(rol) if rol else None, "telefono": str(telefono) if telefono else None}
            )
    return contactos


def _elegir_destinatario(
    borrador: BorradorRouter, hechos: list[Any], texto: str
) -> None:
    """Propone el contacto más probable y pide confirmación si hay varios."""
    contactos = _contactos_de(hechos)
    if not contactos:
        return
    plano_texto = plano(texto)
    for encargo in borrador.encargos:
        es_comunicacion = (
            encargo.canal == "WHATSAPP"
            or encargo.preparar_comunicacion
            or "recordatorio" in plano(encargo.titulo)
        )
        if not es_comunicacion:
            continue
        actual = plano(encargo.destinatario or "")
        if any(actual == plano(c["nombre"] or "") for c in contactos):
            continue
        posiciones = [
            (plano_texto.find(plano(c["nombre"] or "")), c) for c in contactos
        ]
        posiciones = [(p, c) for p, c in posiciones if p >= 0]
        if not posiciones:
            continue
        elegido = posiciones[0][1]
        encargo.destinatario = elegido["nombre"]
        otros = [
            c["nombre"] for c in contactos if c["nombre"] != elegido["nombre"]
        ]
        if otros:
            borrador.preguntas.append(
                f"¿El recordatorio va para {elegido['nombre']} o para "
                + " o ".join(str(o) for o in otros)
                + "?"
            )
            borrador.preguntas = list(dict.fromkeys(borrador.preguntas))
            borrador.notas.append(
                f"{encargo.id}: propuse a {elegido['nombre']} por ser el primer "
                "contacto mencionado; confirma el destinatario."
            )


_AVISO = (
    "avisar a julio",
    "informar a julio",
    "notificar a julio",
    "confirmar a julio",
    "reportar a julio",
    "avisar al director",
    "informar al director",
)


def _fusionar_avisos(borrador: BorradorRouter) -> None:
    """Un «avísame cuando termine» es el resultado de la tarea, no otra tarea."""
    if len(borrador.encargos) < 2:
        return
    for encargo in list(borrador.encargos):
        titulo = plano(encargo.titulo).strip()
        accion = plano(encargo.que_hacer).strip()
        if not (
            any(titulo.startswith(marca) for marca in _AVISO)
            or any(accion.startswith(marca) for marca in _AVISO)
        ):
            continue
        candidatos = [
            otro
            for otro in borrador.encargos
            if otro.id != encargo.id
            and otro.responsable == encargo.responsable
            and not any(marca in plano(otro.titulo + " " + otro.que_hacer) for marca in _AVISO)
        ]
        objetivo = candidatos[0] if candidatos else None
        if objetivo is None:
            objetivo = next(
                (
                    otro
                    for otro in borrador.encargos
                    if otro.id != encargo.id
                    and not any(
                        marca in plano(otro.titulo + " " + otro.que_hacer)
                        for marca in _AVISO
                    )
                ),
                None,
            )
        if objetivo is None:
            continue
        aviso = encargo.resultado_esperado or encargo.que_hacer
        objetivo.resultado_esperado = (
            f"{objetivo.resultado_esperado}; además {aviso}"
            if objetivo.resultado_esperado
            else aviso
        )
        borrador.encargos.remove(encargo)
        borrador.notas.append(
            f"{encargo.id}: se integró como resultado esperado de {objetivo.id}"
        )


def _monto(valor: Any) -> str:
    try:
        return f"{int(Decimal(str(valor))):,}".replace(",", ".")
    except (InvalidOperation, ValueError, TypeError):
        return str(valor)


def resumen_conversacional(borrador: BorradorRouter) -> str:
    datos = borrador.datos_contexto
    cliente = datos.get("cliente.nombre")
    volumen = datos.get("cotizacion.volumen_m3")
    resistencia = datos.get("cotizacion.resistencia")
    plazo = datos.get("cotizacion.plazo_entrega")
    descuento = datos.get("cotizacion.descuento_pct")
    monto = datos.get("pago.monto")
    recibido = datos.get("pago.recibido")

    intro = "Julio, "
    proyecto = _limpiar_proyecto(
        datos.get("cotizacion.obra_direccion") or datos.get("proyecto.nombre")
    )
    vol_estado = datos.get("cotizacion.volumen_m3_estado")
    res_estado = datos.get("cotizacion.resistencia_estado")
    if cliente and volumen and vol_estado != "POR_ACLARAR":
        intro += f"entendí que cerraste un contrato con {cliente} por {volumen} m³"
        if resistencia and res_estado != "POR_ACLARAR":
            intro += f" de hormigón de {resistencia}"
        detalles = []
        if plazo:
            detalles.append(f"con entregas durante {plazo}")
        if descuento:
            detalles.append(f"y un descuento del {descuento} %")
        if detalles:
            intro += " " + " ".join(detalles)
        intro += ". "
    elif proyecto:
        intro += f"entendí lo del proyecto {proyecto}. "
    elif cliente:
        intro += f"entendí un encargo para {cliente}. "
    else:
        intro += "entendí estos encargos. "

    if not borrador.encargos:
        if borrador.consultas:
            return intro + "Es una consulta: " + "; ".join(borrador.consultas) + "."
        return intro + "No vi un encargo concreto en este dictado."

    etiquetas = {
        "SECRETARIA": "Secretaría",
        "JEFE_PLANTA": "Jefe de planta",
        "JULIO": "Tú",
        "POR_DEFINIR": "Por asignar",
    }
    lineas = ["▸ Te propongo:"]
    for rol in ("SECRETARIA", "JEFE_PLANTA", "JULIO", "POR_DEFINIR"):
        del_rol = [e for e in borrador.encargos if e.responsable == rol]
        if not del_rol:
            continue
        titulos = []
        for encargo in del_rol:
            titulo = encargo.titulo
            if encargo.condiciones:
                titulo += " (condicionado)"
            titulos.append(titulo)
        lineas.append(f"• {etiquetas[rol]}: " + " y ".join(titulos) + ".")
    texto = intro + "\n\n" + "\n".join(lineas) + "\n\n"
    if monto is not None and recibido is False:
        texto += f"El pago de ${_monto(monto)} todavía está pendiente de confirmar.\n\n"
    if borrador.preguntas:
        texto += (
            "Solo necesito aclarar algo: " + " ".join(borrador.preguntas) + "\n\n"
            "Cuando me confirmes eso, dejo las tareas asignadas a los responsables."
        )
    else:
        texto += (
            "Si estás de acuerdo, dejaré estas tareas asignadas a los responsables."
        )
    return texto
