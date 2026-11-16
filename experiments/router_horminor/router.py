"""Router Horminor: tres lectores + conciliador que produce un borrador.

No ejecuta nada. El resultado es una propuesta conversacional para Julio.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
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
    tocados = []
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
        if any(p in base for p in palabras):
            tocados.append(encargo)
    return tocados


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

    # 2. Observaciones de C
    for obs in observaciones:
        texto_obs = plano(" ".join([obs.objeto or "", obs.texto or "", " ".join(obs.citas)]))
        if obs.ambiguo:
            dicho = " ".join([obs.texto or "", obs.objeto or ""])
            palabras = {p for p in plano(dicho).split() if len(p) > 3}
            lo_investiga = any(
                palabras & {p for p in plano(item).split() if len(p) > 3}
                for encargo in borrador.encargos
                for item in encargo.por_investigar
            )
            if not lo_investiga:
                borrador.preguntas.append(
                    obs.texto
                    or obs.objeto
                    or "Hay una referencia que no sé a qué encargo apunta."
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
            for encargo in objetivos:
                encargo.origen = "CITA_CLIENTE"
                borrador.notas.append(
                    f"{encargo.id}: proviene de lo que pidió un cliente; se revisa, no se ejecuta"
                )
            continue

        if obs.tipo == "AUTORIZACION" and obs.autoriza_ejecucion:
            for encargo in objetivos:
                encargo.autorizado = True
                borrador.notas.append(f"{encargo.id}: ejecución autorizada por Julio")
            continue

        if obs.tipo == "CONTRADICCION":
            borrador.preguntas.append(
                obs.texto or "Hay dos frases del dictado que no coinciden."
            )
            continue

        # CONDICION / DEPENDENCIA / PROHIBICION de una operación
        if obs.tipo in ("CONDICION", "DEPENDENCIA") and not obs.condiciona_operacion:
            marca_real = any(
                m in plano(obs.texto or "")
                for m in ("hasta que", "antes de", "depende", "si ")
            )
            if not marca_real:
                # Una descripción no es una condición: no se ensucia la tarea.
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
    borrador.resumen = resumen_conversacional(borrador)
    return borrador


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


def resumen_conversacional(borrador: BorradorRouter) -> str:
    if not borrador.encargos:
        if borrador.consultas:
            return "Entendí una consulta: " + "; ".join(borrador.consultas) + "."
        return "No entendí un encargo concreto en este dictado."
    cuentas = {"SECRETARIA": 0, "JEFE_PLANTA": 0, "JULIO": 0, "POR_DEFINIR": 0}
    for encargo in borrador.encargos:
        cuentas[encargo.responsable] += 1
    partes = []
    if cuentas["SECRETARIA"]:
        partes.append(
            f"{cuentas['SECRETARIA']} tarea(s) para secretaría"
        )
    if cuentas["JEFE_PLANTA"]:
        partes.append(f"{cuentas['JEFE_PLANTA']} para el jefe de planta")
    if cuentas["JULIO"]:
        partes.append(f"{cuentas['JULIO']} para ti")
    if cuentas["POR_DEFINIR"]:
        partes.append(f"{cuentas['POR_DEFINIR']} por asignar")
    texto = f"Julio, entendí {len(borrador.encargos)} encargo(s): " + ", ".join(partes) + ". "
    detalle = []
    for encargo in borrador.encargos:
        linea = f"{encargo.id} {encargo.titulo}"
        if encargo.condiciones:
            linea += " (condicionado)"
        if encargo.por_investigar:
            linea += " (con datos por averiguar)"
        detalle.append(linea)
    texto += " · ".join(detalle) + "."
    if borrador.preguntas:
        texto += " Antes de confirmar: " + " ".join(borrador.preguntas)
    else:
        texto += " ¿Confirmas?"
    return texto
