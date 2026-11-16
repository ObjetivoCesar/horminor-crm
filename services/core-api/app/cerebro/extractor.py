"""Extractor: del texto normalizado al sobre de hechos citados.

El LLM solo propone hechos con una cita. El backend verifica que la cita exista,
la alinea con las palabras del STT y descarta lo que no se sostiene. Después el
compilador decide si hay acciones.
"""

from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Sequence
from zoneinfo import ZoneInfo

import asyncpg
import httpx

from ..voz import (
    PalabraSTT,
    SecuenciaAlineada,
    TextoNormalizado,
    alinear_con_palabras,
    alinear_secuencias,
    localizar_palabras,
    normalizar_con_mapa,
    normalizar_texto,
)
from .compilador import (
    Borrador,
    ClienteResuelto,
    Contexto,
    Pregunta,
    Receta,
    compilar,
    dictado_revocado,
    normalizar_resistencia,
)
from .encargos import asignar, segmentar
from .hechos import (
    Evidencia,
    HechoCitado,
    desde_secuencia,
    inaudible,
    no_dijo,
    validar_hecho,
)
from .revision import resumen_legible
from .sobre import HechoIn, SobreIn, validar_sobre
from .tiempo import hora_de_cita, hora_de_recordatorio, sostiene_fecha

BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
MODELO = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
TIMEOUT = float(os.getenv("DEEPSEEK_TIMEOUT", "40"))
VERSION_PROMPT = "cerebro-v6"

CLAVES = (
    "cliente.nombre",
    "cliente.cedula",
    "cliente.telefono",
    "cliente.ciudad",
    "cliente.referencia",
    "contacto.nombre",
    "contacto.telefono",
    "contacto.rol",
    "contacto.2.nombre",
    "contacto.2.telefono",
    "contacto.2.rol",
    "contacto.3.nombre",
    "contacto.3.telefono",
    "contacto.3.rol",
    "cotizacion.obra_direccion",
    "cotizacion.volumen_m3",
    "cotizacion.resistencia",
    "cotizacion.fecha_entrega",
    "cotizacion.hora_entrega",
    "cotizacion.plazo_entrega",
    "cotizacion.descuento_pct",
    "cotizacion.dias_trabajo",
    "cotizacion.precio_m3",
    "cotizacion.forma_pago",
    "cotizacion.enviar",
    "operacion.planta_movil",
    "pago.monto",
    "pago.forma",
    "pago.referencia",
    "pago.recibido",
    "pago.cuenta_destino",
    "traslado.cuenta_banco",
    "tarea.destinatario",
    "tarea.telefono",
    "tarea.mensaje",
    "tarea.cuando",
    "tarea.adjuntar_factura",
)

PROMPT = """Extraes datos para Horminor (hormigon premezclado, El Coca, Ecuador).
Devuelve SOLO un objeto JSON, sin markdown ni explicaciones.

Claves permitidas: {claves}.

Forma:
{{"intencion":"MUTACION|CONSULTA|MIXTA","hechos":[{{"clave":"...","valor":...,"tipo":"TEXTO|ENTERO|DECIMAL|FECHA|HORA|TELEFONO|CEDULA|BOOLEANO","estado":"EXTRAIDO|NO_DIJO|INAUDIBLE_NO_ENTENDI|BAJA_CONFIANZA_STT","cita":"...","hablante":"SUPERADMIN|SECRETARIA|VENDEDOR|CONTADORA|CHOFER|CLIENTE|TERCERO|NO_DETERMINADO"}}],"faltantes":[],"ambiguedades":[],"preguntas":[]}}

Reglas duras:
1. `cita` debe ser una copia EXACTA de un fragmento del TEXTO NORMALIZADO.
2. No inventes ningun dato. Si no esta, no lo incluyas o marca NO_DIJO.
3. `hablante` es quien sostiene el dato: si no hay marca de otra persona, es SUPERADMIN (quien dicta el audio). Si el texto cita al cliente ("el dice", "me dijo", comillas), usa CLIENTE. Si no se sabe, NO_DETERMINADO.
4. Fechas: ISO YYYY-MM-DD, calculadas con HOY y la zona America/Guayaquil. Si "proximo sabado" es ambiguo, pon el candidato y agrega una ambiguedad. Una hora suelta ("a las seis de la manana") NO es una fecha: usa cotizacion.hora_entrega con tipo HORA y valor HH:MM, y NO pongas cotizacion.fecha_entrega.
5. Montos en USD como numero DECIMAL, sin simbolos. Volumen en m3 como DECIMAL.
6. `intencion`: CONSULTA si solo pregunta o pide revisar; MUTACION si pide crear, registrar o enviar; MIXTA si hace las dos.
7. Maximo 3 preguntas, solo las que bloquean la accion.
8. Si el audio repite o corrige un dato, usa el ultimo valor y cita la correccion.
9. Un numero de 10 digitos que empieza con 09 es un telefono, pero la clave depende de quien es: cliente.telefono solo si es el numero del cliente; contacto.telefono si es el maestro, encargado o ingeniero del cliente; tarea.telefono si es el destinatario de un recordatorio. Una cedula de 10 digitos que no empieza con 09 va en cliente.cedula.
10. `contacto.*` es una persona distinta del cliente (maestro, encargado, ingeniero, chofer del cliente): contacto.nombre, contacto.rol y contacto.telefono. contacto.rol es una sola palabra ("maestro", "ingeniero", "encargado"), copiada de la cita. Ese telefono no va en cliente.telefono.
11. Si el audio menciona VARIAS personas de contacto, usa contacto.* para la primera, contacto.2.* para la segunda y contacto.3.* para la tercera, con nombre, rol y telefono de cada una. No las juntes en un solo hecho ni pongas sus numeros en cliente.telefono.
12. `pago.recibido` es BOOLEANO: true si el dinero YA entro ("ya me deposito", "ya me transfirio", "recibi el abono"); false si todavia no ("nos va a hacer", "todavia no me envia el comprobante", "queda pendiente"). Si no se dice, no lo incluyas.
13. `pago.cuenta_destino` es el banco o la cuenta donde el cliente transfiere ("a la cuenta del Banco de Pichincha"). No uses traslado.cuenta_banco para eso.
14. `traslado.cuenta_banco` SOLO si el audio ordena mover efectivo de caja al banco ("llevar la caja al banco", "depositar el efectivo").
15. Si el audio pide enviar un recordatorio, un aviso o pedir el comprobante, usa: tarea.telefono (numero al que se envia), tarea.destinatario (nombre si lo hay), tarea.mensaje (las palabras exactas que se deben enviar, sin agregar montos ni fechas), tarea.cuando (hora o fecha del envio; "ahora" solo si dice ya/ahora/de una; omitela si no dice cuando) y tarea.adjuntar_factura (BOOLEANO). Eso NO es cotizacion.enviar.
16. `cotizacion.enviar` solo si el audio dice explicitamente enviar o mandar la cotizacion.
17. La resistencia y el precio no son lo mismo. "todo el hormigon es de 240" o "hormigon de 210" es `cotizacion.resistencia` (ENTERO 240 / 210), NO es `cotizacion.precio_m3`. Usa `cotizacion.precio_m3` SOLO si dice un precio por metro cubico en dolares ("a 118 el metro", "precio de 118 por m3").
18. `cliente.nombre` incluye empresas y contratistas ("Diaz Sur", "empresa Diaz Sur"): no lo omitas porque sea una empresa ni lo cambies por el nombre de una persona.
19. Condiciones del contrato: "entregados en un mes" va en `cotizacion.plazo_entrega` como TEXTO copiado de la cita ("en un mes" o "un mes"); NO lo conviertas a "1 mes", NO calcules una fecha y NO pongas `cotizacion.fecha_entrega`. "13 de descuento" va en `cotizacion.descuento_pct` (ENTERO 13). "sabados y domingos" va en `cotizacion.dias_trabajo` (TEXTO). "llevar la planta movil" va en `operacion.planta_movil` (BOOLEANO true).
20. Una instruccion a alguien del equipo ("que revisen en secretaria como van los despachos", "verifica que el deposito ya este hecho", "que Mauricio confirme el stock") SI es MUTACION: usa tarea.mensaje con la instruccion copiada de la cita y tarea.destinatario si nombra a la persona o al area ("secretaria", "bodega", "Mauricio"). NO inventes un telefono y NO pongas tarea.telefono si no lo dictan: ese encargo se registra como tarea interna del CRM, no como WhatsApp.
21. Si el hablante NIEGA o CONDICIONA un dato o una accion ("no le hagan todavia el descuento", "primero tengo que revisar el precio", "no se lo manden"), no emitas ese hecho como si estuviera ordenado. Si hace falta registrar que se hablo del tema, usa estado NO_DIJO; nunca conviertas una negacion en una instruccion.
22. Si el hablante DUDA o APROXIMA ("creo que", "300 y pico", "mas o menos", "o el sabado"), emite el hecho con estado TENTATIVO, el valor aproximado en valor y la expresion original en cita. El sistema no lo usa como definitivo: pregunta.
23. Si el audio CITA palabras de otra persona o un mensaje ("me mandaron decir que...", "te voy a leer un mensaje..."), eso no es una orden de Julio: no generes acciones a partir de la cita. Si ademas dice "eso no lo hagas", no emitas el hecho.
24. Si el hablante se CORRIGE a si mismo en el mismo audio ("380, bueno, 300 y pico"), emite un solo hecho con el ULTIMO valor y estado CORREGIDO_EN_AUDIO, citando la correccion.
"""


class ExtractorNoDisponible(RuntimeError):
    """Falta la clave del LLM o el proveedor fallo."""


def _hoy() -> date:
    return datetime.now(ZoneInfo("America/Guayaquil")).date()


def _digitos(texto: Any) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def _mensaje(
    texto_normalizado: str,
    palabras: Sequence[PalabraSTT],
    hoy: date,
    clientes: Sequence[str],
    vocabulario: Sequence[tuple[str, str]] = (),
) -> str:
    lista = ", ".join(
        f"{i}:{p.texto}@{p.start_ms or 0}-{p.end_ms or 0}" for i, p in enumerate(palabras[:2000])
    )
    conocidos = ", ".join(clientes[:200]) if clientes else "(sin lista)"
    pistas = "; ".join(f"«{mal}» → «{bien}»" for mal, bien in vocabulario[:40])
    return (
        f"HOY: {hoy.isoformat()} (America/Guayaquil)\n"
        f"CLIENTES CONOCIDOS (copia el nombre exacto si coincide): {conocidos}\n"
        f"CORRECCIONES CONOCIDAS (el STT suele escribir lo primero; la persona"
        f" corrigio lo segundo): {pistas or '(sin correcciones)'}\n"
        f"TEXTO NORMALIZADO:\n{texto_normalizado}\n\n"
        f"PALABRAS (indice:palabra@inicio_ms-fin_ms):\n{lista or '(sin palabras)'}"
    )


async def extraer(
    *,
    texto_normalizado: str,
    palabras: Sequence[PalabraSTT],
    hoy: date,
    clientes: Sequence[str] = (),
    vocabulario: Sequence[tuple[str, str]] = (),
    http_client: Any = None,
) -> SobreIn:
    """Llama al LLM y valida el sobre. Un reintento si el JSON no cumple."""
    clave = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not clave:
        raise ExtractorNoDisponible("DEEPSEEK_API_KEY no configurada")

    mensajes = [
        {"role": "system", "content": PROMPT.format(claves=", ".join(CLAVES))},
        {
            "role": "user",
            "content": _mensaje(
                texto_normalizado, palabras, hoy, clientes, vocabulario
            ),
        },
    ]
    cliente = http_client
    propio = cliente is None
    if cliente is None:
        cliente = httpx.AsyncClient(timeout=TIMEOUT)
    try:
        ultimo_error = ""
        for intento in range(2):
            try:
                respuesta = await cliente.post(
                    f"{BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {clave}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": MODELO,
                        "messages": mensajes,
                        "temperature": 0,
                        "response_format": {"type": "json_object"},
                    },
                )
                if respuesta.status_code >= 400:
                    raise ExtractorNoDisponible(
                        f"LLM_HTTP_{respuesta.status_code}: {(respuesta.text or '')[:200]}"
                    )
                contenido = respuesta.json()["choices"][0]["message"]["content"]
                return validar_sobre(json.loads(contenido))
            except (ValueError, KeyError, TypeError) as exc:
                ultimo_error = f"{type(exc).__name__}: {exc}"
                mensajes.append(
                    {
                        "role": "user",
                        "content": (
                            "El JSON no cumple el contrato. Corrigelo y devuelve solo "
                            f"JSON valido. Error: {ultimo_error}"
                        ),
                    }
                )
        raise ExtractorNoDisponible(f"SOBRE_INVALIDO: {ultimo_error}")
    finally:
        if propio:
            await cliente.aclose()


def _ventana(
    palabras: Sequence[PalabraSTT], crudo_inicio: int, crudo_fin: int
) -> tuple[int | None, int | None, float | None]:
    indices = [
        i
        for i, palabra in enumerate(palabras)
        if palabra.fin > crudo_inicio and palabra.inicio < crudo_fin
    ]
    inicios = [palabras[i].start_ms for i in indices if palabras[i].start_ms is not None]
    fines = [palabras[i].end_ms for i in indices if palabras[i].end_ms is not None]
    confianzas = [
        palabras[i].confianza for i in indices if palabras[i].confianza is not None
    ]
    return (
        min(inicios) if inicios else None,
        max(fines) if fines else None,
        min(confianzas) if confianzas else None,
    )


def construir_hechos(
    sobre: SobreIn,
    *,
    texto_crudo: str,
    mapa: TextoNormalizado,
    palabras: Sequence[PalabraSTT],
) -> tuple[list[HechoCitado], list[str]]:
    """Verifica cada hecho contra la cita y lo alinea con el audio."""
    secuencias = alinear_secuencias(mapa, palabras)
    hechos: list[HechoCitado] = []
    notas: list[str] = []

    for item in sobre.hechos:
        if item.estado == "NO_DIJO":
            hechos.append(no_dijo(item.clave, item.tipo))
            continue
        if item.estado == "INAUDIBLE_NO_ENTENDI":
            hechos.append(inaudible(item.clave, item.tipo))
            continue

        cita = (item.cita or "").strip()
        if not cita:
            notas.append(f"{item.clave}: sin cita, se descarta")
            continue
        inicio = mapa.texto.find(cita)
        if inicio < 0:
            inicio = mapa.texto.lower().find(cita.lower())
        if inicio < 0:
            # El normalizador reescribe cifras («mil dólares» → «1000 USD»).
            # Si la cita no aparece tal cual, se busca su forma normalizada
            # antes de descartar el hecho, que es lo que hace el LLM al citar
            # lo que escuchó y no lo que quedó escrito.
            cita_norm = normalizar_texto(cita)
            if cita_norm and cita_norm != cita:
                inicio = mapa.texto.find(cita_norm)
                if inicio < 0:
                    inicio = mapa.texto.lower().find(cita_norm.lower())
                if inicio >= 0:
                    cita = cita_norm
        if inicio < 0:
            notas.append(f"{item.clave}: la cita no esta en el texto normalizado")
            continue
        fin = inicio + len(cita)

        if item.tipo in ("CEDULA", "TELEFONO", "ENTERO", "DECIMAL"):
            buscado = _digitos(item.valor)
            secuencia = next(
                (s for s in secuencias if s.digitos == buscado),
                None,
            )
            if secuencia is None:
                notas.append(
                    f"{item.clave}: el numero {item.valor} no coincide con el audio"
                )
                continue
            hecho = desde_secuencia(
                item.clave,
                secuencia,
                texto_crudo,
                hablante=item.hablante,
                tipo=item.tipo,
                estado=item.estado,
            )
        else:
            tokens = [
                token
                for token in mapa.tokens
                if token.inicio < fin
                and token.fin > inicio
                and token.tipo not in ("ESPACIO", "PUNTUACION")
            ]
            if not tokens:
                notas.append(f"{item.clave}: no se pudo ubicar la cita")
                continue
            primero, ultimo = tokens[0], tokens[-1]
            inicio_ms, fin_ms, confianza = _ventana(
                palabras, primero.crudo_inicio, ultimo.crudo_fin
            )
            evidencia = Evidencia(
                cita=texto_crudo[primero.crudo_inicio : ultimo.crudo_fin],
                sostiene=mapa.texto[inicio:fin],
                crudo_inicio=primero.crudo_inicio,
                crudo_fin=ultimo.crudo_fin,
                start_ms=inicio_ms,
                end_ms=fin_ms,
                confianza=confianza,
                hablante=item.hablante,
            )
            hecho = HechoCitado(
                clave=item.clave,
                valor=item.valor,
                estado=item.estado,
                tipo=item.tipo,
                evidencia=evidencia,
            )

        errores = validar_hecho(hecho)
        if (
            item.clave == "cotizacion.fecha_entrega"
            and not sostiene_fecha(hecho.evidencia.cita if hecho.evidencia else cita)
        ):
            notas.append(
                f"{item.clave}: la cita menciona una hora, no una fecha; "
                "no se usa como fecha de entrega"
            )
            hora = hora_de_cita(cita)
            if hora and not any(
                h.clave == "cotizacion.hora_entrega" and h.utilizable for h in hechos
            ):
                hechos.append(
                    HechoCitado(
                        clave="cotizacion.hora_entrega",
                        valor=hora,
                        estado="EXTRAIDO",
                        tipo="HORA",
                        evidencia=hecho.evidencia,
                    )
                )
                notas.append(
                    f"cotizacion.hora_entrega: se interpreta {hora} como hora, "
                    "no como fecha"
                )
            continue
        if errores:
            notas.append(f"{item.clave}: {'; '.join(errores)}")
            continue
        hechos.append(hecho)

    notas.extend(_inferir_telefono(secuencias, hechos, texto_crudo))
    notas.extend(_completar_cuando_de_tarea(hechos, mapa.texto))
    notas.extend(_degradar_pago_no_declarado(hechos, texto_crudo))
    # Cada hecho queda en el encargo (tramo) del dictado donde está su cita.
    return asignar(hechos, segmentar(texto_crudo)), notas


# «No recibido» es una afirmación financiera. Solo se acepta como dato cuando
# el dictado la declara; si solo la sugiere («el pago que tiene que hacernos»),
# queda como inferencia y el resumen dice «sin ingreso confirmado».
_MARCAS_PAGO_NO_RECIBIDO = (
    "no ha pagado",
    "no ha depositado",
    "no nos ha pagado",
    "no nos ha depositado",
    "no me ha pagado",
    "no nos ha transferido",
    "no ha transferido",
    "no ha cancelado",
    "no ha entrado",
    "no ha llegado",
    "todavia no",
    "aun no",
    "falta que nos pague",
    "queda pendiente",
    "quedo pendiente",
)


def _degradar_pago_no_declarado(
    hechos: list[HechoCitado], texto_crudo: str
) -> list[str]:
    plano = _sin_tildes(texto_crudo)
    for indice, hecho in enumerate(hechos):
        if hecho.clave != "pago.recibido" or hecho.valor is not False:
            continue
        if hecho.estado == "CORREGIDO_POR_HUMANO":
            continue
        cita = _sin_tildes(
            hecho.evidencia.cita if hecho.evidencia is not None else ""
        )
        if any(marca in plano or marca in cita for marca in _MARCAS_PAGO_NO_RECIBIDO):
            continue
        hechos[indice] = HechoCitado(
            clave=hecho.clave,
            valor=hecho.valor,
            estado="INFERIDO",
            tipo=hecho.tipo,
            evidencia=hecho.evidencia,
            checksum_valido=hecho.checksum_valido,
        )
        return [
            "pago.recibido: el dictado sugiere que el anticipo no ha llegado, "
            "pero no lo declara; queda como inferencia y el resumen lo dice "
            "«sin ingreso confirmado»"
        ]
    return []


def _completar_cuando_de_tarea(
    hechos: list[HechoCitado], texto_normalizado: str
) -> list[str]:
    """Si el LLM no capturó la hora del recordatorio, se toma de su frase.

    Un recordatorio dictado «a las 18:00» no puede terminar programado
    «ahora» porque el modelo olvidó la hora. Se busca la hora en la misma
    oración del teléfono o del mensaje de la tarea.
    """
    if any(h.clave == "tarea.cuando" and h.utilizable for h in hechos):
        return []
    if not any(h.clave.startswith("tarea.") for h in hechos):
        return []

    referencia = next(
        (
            h
            for h in hechos
            if h.clave in ("tarea.telefono", "tarea.mensaje")
            and h.utilizable
            and h.evidencia is not None
        ),
        None,
    )
    if referencia is None:
        return []

    ancla = str(referencia.valor or "")
    posicion = texto_normalizado.find(ancla) if ancla else -1
    if posicion < 0:
        return []
    inicio = max(0, texto_normalizado.rfind(".", 0, posicion) + 1)
    fin = texto_normalizado.find(".", posicion + len(ancla))
    ventana = texto_normalizado[
        inicio : fin + 1 if fin >= 0 else len(texto_normalizado)
    ].strip()
    hora = hora_de_recordatorio(ventana)
    if not hora:
        return []

    evidencia = Evidencia(
        cita=ventana,
        sostiene=ventana,
        crudo_inicio=referencia.evidencia.crudo_inicio,
        crudo_fin=referencia.evidencia.crudo_fin,
        start_ms=referencia.evidencia.start_ms,
        end_ms=referencia.evidencia.end_ms,
        confianza=referencia.evidencia.confianza,
        hablante=referencia.evidencia.hablante,
    )
    hechos.append(
        HechoCitado(
            clave="tarea.cuando",
            valor=hora,
            estado="EXTRAIDO",
            tipo="TEXTO",
            evidencia=evidencia,
        )
    )
    return [
        f"tarea.cuando: se toma {hora} de la misma frase del recordatorio "
        "(el modelo no la habia extraido)"
    ]


def _inferir_telefono(
    secuencias: Sequence[SecuenciaAlineada],
    hechos: list[HechoCitado],
    texto_crudo: str,
) -> list[str]:
    """Propone un teléfono si el audio dicta un 09… y el LLM no lo captó.

    Es una propuesta, no un hecho: se marca INFERIDO y el compilador obliga a
    confirmarla antes de escribir. Si el número ya sostiene otro dato (por
    ejemplo una cédula de Azuay), no se propone.
    """
    if any(h.clave == "cliente.telefono" and h.utilizable for h in hechos):
        return []
    # Si el audio ya asignó teléfonos a contactos o a una tarea, el número que
    # sobra no es del cliente: no se propone para no robarle el contacto.
    if any(
        h.utilizable
        and (h.clave.startswith("contacto") or h.clave.startswith("tarea."))
        for h in hechos
    ):
        return []
    usados = {
        _digitos(h.valor) for h in hechos if h.utilizable and h.clave != "cliente.nombre"
    }
    candidatos = {
        secuencia.digitos: secuencia
        for secuencia in secuencias
        if secuencia.tipo == "TELEFONO" and secuencia.digitos not in usados
    }
    if not candidatos:
        return []
    if len(candidatos) > 1:
        return [
            "cliente.telefono: el audio trae varios numeros ("
            + ", ".join(sorted(candidatos))
            + "); no se propone ninguno"
        ]
    (secuencia,) = candidatos.values()
    hechos.append(
        desde_secuencia(
            "cliente.telefono",
            secuencia,
            texto_crudo,
            hablante="NO_DETERMINADO",
            tipo="TELEFONO",
            estado="INFERIDO",
        )
    )
    return [
        f"cliente.telefono: se propone {secuencia.digitos} porque aparece en el "
        "audio; hay que confirmarlo"
    ]


def _valor(hechos: Sequence[HechoCitado], clave: str) -> Any:
    for hecho in hechos:
        if hecho.clave == clave and hecho.utilizable:
            # Un dato inferido sirve para preguntar, no para resolver identidad.
            if hecho.estado == "INFERIDO":
                continue
            return hecho.valor
    return None


def _sin_tildes(texto: str) -> str:
    normal = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in normal if unicodedata.category(c) != "Mn").lower()


_VACIAS = {
    "de",
    "del",
    "la",
    "las",
    "los",
    "el",
    "y",
    "don",
    "dona",
    "sr",
    "sra",
    "senor",
    "senora",
    "ing",
    "inge",
}


def _tokens_nombre(texto: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", _sin_tildes(texto))
        if token not in _VACIAS
    }


def _nombres_compatibles(dicho: str, registrado: str) -> bool:
    """«Olmedo» encaja con «Joaquín Olmedo»; «Palo Velez» no encaja."""
    a = _tokens_nombre(dicho)
    b = _tokens_nombre(registrado)
    if not a or not b:
        return True
    corto, largo = (a, b) if len(a) <= len(b) else (b, a)
    return corto <= largo


async def _resolver_cliente(
    pool: asyncpg.Pool, hechos: Sequence[HechoCitado]
) -> tuple[
    ClienteResuelto | None,
    list[dict[str, str]] | None,
    Pregunta | None,
]:
    cedula = _valor(hechos, "cliente.cedula")
    telefono = _valor(hechos, "cliente.telefono")
    nombre = _valor(hechos, "cliente.nombre")

    fila = None
    via: str | None = None
    if cedula:
        fila = await pool.fetchrow(
            "SELECT id::text AS id, nombre FROM clients WHERE cedula = $1",
            str(cedula),
        )
        via = "cédula"
    if fila is None and telefono:
        fila = await pool.fetchrow(
            "SELECT id::text AS id, nombre FROM clients WHERE telefono_whatsapp = $1",
            str(telefono),
        )
        via = "teléfono"
    if fila is not None:
        if nombre and not _nombres_compatibles(str(nombre), str(fila["nombre"])):
            documento = cedula if via == "cédula" else telefono
            return (
                None,
                None,
                Pregunta(
                    "cliente.identidad",
                    f"El {via} {documento} ya está registrado a nombre de "
                    f"{fila['nombre']}, pero el audio dice {nombre}. "
                    "¿Es el mismo cliente?",
                    ("Sí, es el mismo", "No, crear cliente nuevo"),
                ),
            )
        return ClienteResuelto(fila["id"], fila["nombre"], True), None, None

    if nombre:
        filas = await pool.fetch(
            """
            SELECT id::text AS id, nombre
              FROM clients
             WHERE lower(nombre) LIKE $1
             ORDER BY nombre
             LIMIT 5
            """,
            f"%{str(nombre).lower()}%",
        )
        if len(filas) == 1:
            return ClienteResuelto(filas[0]["id"], filas[0]["nombre"], True), None, None
        if len(filas) > 1:
            return None, [dict(f) for f in filas], None
    return None, None, None


async def _resolver_receta(
    pool: asyncpg.Pool, hechos: Sequence[HechoCitado]
) -> Receta | None:
    resistencia = normalizar_resistencia(
        _valor(hechos, "cotizacion.resistencia")
    )
    if not resistencia:
        return None
    fila = await pool.fetchrow(
        """
        SELECT resistencia, precio_m3, precio_estado, iva_pct
          FROM concrete_recipes
         WHERE resistencia = $1
        """,
        str(resistencia).strip().upper(),
    )
    if fila is None or fila["precio_m3"] is None:
        return None
    return Receta(
        resistencia=fila["resistencia"],
        precio_m3=Decimal(str(fila["precio_m3"])),
        precio_estado=fila["precio_estado"] or "PROVISIONAL",
        iva_pct=Decimal(str(fila["iva_pct"] or 15)),
    )


def _notas_de_dinero_y_tarea(
    hechos: Sequence[HechoCitado], borrador: Borrador
) -> list[str]:
    """Explica por qué no se propone una acción que el dictado insinuaba."""
    notas: list[str] = []

    def booleano(clave: str) -> bool | None:
        for hecho in hechos:
            if hecho.clave != clave or not hecho.utilizable:
                continue
            if isinstance(hecho.valor, bool):
                return hecho.valor
            texto = str(hecho.valor).strip().lower()
            if texto in ("true", "si", "sí", "1", "yes"):
                return True
            if texto in ("false", "no", "0"):
                return False
        return None

    hay_monto = any(
        hecho.clave == "pago.monto" and hecho.utilizable for hecho in hechos
    )
    if booleano("pago.recibido") is False and hay_monto:
        notas.append(
            "pago.monto: la transferencia aun no ha entrado; no se registra el "
            "abono hasta que llegue el comprobante"
        )
    hay_traslado = any(
        hecho.clave == "traslado.cuenta_banco" and hecho.utilizable
        for hecho in hechos
    )
    forma = next(
        (
            str(hecho.valor).upper()
            for hecho in hechos
            if hecho.clave == "pago.forma" and hecho.utilizable
        ),
        "",
    )
    if hay_traslado and "TRANSFERENCIA" in forma:
        notas.append(
            "traslado.cuenta_banco: se ignora; la transferencia del cliente ya "
            "entra al banco, no es un traslado de caja"
        )
    if any(
        accion.nombre == "crear_tarea_recordatorio"
        and accion.parametros.get("programado_inferido")
        for accion in borrador.acciones
    ):
        notas.append(
            "tarea.cuando: no se dicto hora; antes de programarlo hay que "
            "confirmar el envio inmediato"
        )
    if any(
        accion.nombre == "crear_tarea_recordatorio"
        and accion.parametros.get("mensaje_por_confirmar")
        for accion in borrador.acciones
    ):
        notas.append(
            "tarea.mensaje: lo dictado describe el encargo («"
            + str(
                next(
                    accion.parametros.get("instruccion")
                    for accion in borrador.acciones
                    if accion.nombre == "crear_tarea_recordatorio"
                )
                or ""
            )
            + "»); el mensaje que leera el destinatario se define antes de "
            "enviar"
        )
    return notas


async def _borrador_desde_hechos(
    pool: asyncpg.Pool,
    hechos: list[HechoCitado],
    *,
    intencion: str,
    sandbox: bool,
    hoy: date,
    texto: str | None = None,
) -> tuple[Borrador, list[str], Any]:
    """Resuelve cliente y receta y compila. Sin LLM: es determinístico."""
    notas: list[str] = []
    cliente, candidatos, conflicto = await _resolver_cliente(pool, hechos)
    if conflicto is not None:
        borrador = Borrador(
            estado="REQUIERE_ACLARACION",
            intencion="MUTACION",
            acciones=(),
            preguntas=(conflicto,),
            hechos=tuple(hechos),
        )
    elif candidatos:
        candidatos_txt = ", ".join(c["nombre"] for c in candidatos)
        borrador = Borrador(
            estado="REQUIERE_ACLARACION",
            intencion="MUTACION",
            acciones=(),
            preguntas=(
                Pregunta(
                    "cliente.nombre",
                    f"Hay varios clientes parecidos: {candidatos_txt}. ¿Cuál es?",
                    tuple(c["nombre"] for c in candidatos),
                ),
            ),
            hechos=tuple(hechos),
        )
    else:
        receta = await _resolver_receta(pool, hechos)
        borrador = compilar(
            hechos,
            Contexto(
                hoy=hoy,
                sandbox=sandbox,
                cliente=cliente,
                receta=receta,
                texto=texto,
            ),
            intencion=intencion,
        )
        notas.extend(_notas_de_dinero_y_tarea(hechos, borrador))
        if dictado_revocado(texto):
            notas.append(
                "El dictado revoca la instruccion: no se proponen acciones."
            )
    return borrador, notas, cliente


async def _vocabulario(pool: asyncpg.Pool) -> list[tuple[str, str]]:
    """Pares de corrección ya aprendidos, como pista para el modelo.

    Si la vista no existe (base sin migración 087) no se rompe la extracción:
    el aprendizaje es una mejora, no un requisito.
    """
    try:
        filas = await pool.fetch(
            """
            SELECT valor_anterior, valor_nuevo
              FROM v_cerebro_vocabulario
             WHERE clave IN ('cliente.nombre', 'contacto.nombre', 'cotizacion.dias_trabajo')
             ORDER BY veces DESC, ultima_vez DESC
             LIMIT 40
            """
        )
    except Exception:
        return []
    return [
        (str(fila["valor_anterior"]), str(fila["valor_nuevo"]))
        for fila in filas
        if fila["valor_anterior"] and fila["valor_nuevo"]
    ]


async def interpretar(
    pool: asyncpg.Pool,
    *,
    texto_crudo: str,
    palabras_crudas: Sequence[Any] | None = None,
    sandbox: bool = True,
    hoy: date | None = None,
    http_client: Any = None,
) -> dict[str, Any]:
    """Texto → sobre verificado → borrador. No escribe en la base."""
    hoy = hoy or _hoy()
    mapa = normalizar_con_mapa(texto_crudo)
    palabras = localizar_palabras(texto_crudo, palabras_crudas or [])
    clientes = [
        str(fila["nombre"])
        for fila in await pool.fetch(
            "SELECT nombre FROM clients ORDER BY nombre LIMIT 200"
        )
    ]
    sobre = await extraer(
        texto_normalizado=mapa.texto,
        palabras=palabras,
        hoy=hoy,
        clientes=clientes,
        vocabulario=await _vocabulario(pool),
        http_client=http_client,
    )
    hechos, notas = construir_hechos(
        sobre, texto_crudo=texto_crudo, mapa=mapa, palabras=palabras
    )
    borrador, notas_compiladas, cliente = await _borrador_desde_hechos(
        pool,
        hechos,
        intencion=sobre.intencion,
        sandbox=sandbox,
        hoy=hoy,
        texto=mapa.texto,
    )
    notas.extend(notas_compiladas)
    hechos_finales = list(borrador.hechos)
    textos_por_encargo = {
        segmento.indice: segmento.texto for segmento in segmentar(mapa.texto)
    }

    return {
        "sobre": sobre,
        "hechos": hechos_finales,
        "borrador": borrador,
        "notas": notas,
        "resumen": resumen_legible(
            hechos_finales,
            texto=mapa.texto,
            condiciones=borrador.condiciones,
            textos_por_encargo=textos_por_encargo,
        ),
        "cliente": cliente,
        "texto_normalizado": mapa.texto,
        "palabras": [p.__dict__ for p in palabras],
    }


async def recompilar(
    pool: asyncpg.Pool,
    *,
    hechos: Sequence[HechoCitado],
    intencion: str = "MUTACION",
    sandbox: bool = True,
    hoy: date | None = None,
    texto: str | None = None,
) -> dict[str, Any]:
    """Vuelve a compilar con hechos ya corregidos, sin llamar al LLM."""
    hoy = hoy or _hoy()
    lista = list(hechos)
    borrador, notas, _cliente = await _borrador_desde_hechos(
        pool, lista, intencion=intencion, sandbox=sandbox, hoy=hoy, texto=texto
    )
    return {
        "hechos": list(borrador.hechos),
        "borrador": borrador,
        "notas": notas,
        "resumen": resumen_legible(
            list(borrador.hechos),
            texto=texto,
            condiciones=borrador.condiciones,
            textos_por_encargo=(
                {
                    segmento.indice: segmento.texto
                    for segmento in segmentar(texto or "")
                }
                if texto
                else None
            ),
        ),
    }
