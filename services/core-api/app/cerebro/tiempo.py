"""Lectura determinística de fechas y horas en una cita.

Una hora suelta («a las seis de la mañana») no es una fecha. El LLM tiende a
convertirla en el día de hoy, y eso inventa un dato de negocio. Estas funciones
miran la cita —no el valor— para decidir qué sostiene de verdad.
"""

from __future__ import annotations

import re
import unicodedata

from ..voz import normalizar_texto

_MESES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "setiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
_DIAS = (
    "lunes",
    "martes",
    "miercoles",
    "jueves",
    "viernes",
    "sabado",
    "domingo",
)

# Hora con marca explícita de momento del día. Sin marca no se interpreta:
# «a las 6» puede ser la hora de salida de la planta o un número cualquiera.
_HORA_CITA = re.compile(
    r"(?i)(?<!\d)(\d{1,2})(?::(\d{2}))?\s*"
    r"(?:de\s+la\s+(manana|tarde|noche|madrugada)|(am|pm))(?![a-z])"
)
_HORA_VALOR = re.compile(
    r"(?i)^(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?$"
)
_HORA_EXPLICITA = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)")
# «a las 15 y 27», «a las 3 y 30 de la tarde»: la hora con minutos dicha en
# palabras. Se exige el «a las» para no confundirla con una enumeracion
# («entre 15 y 27 metros»).
_HORA_CON_Y = re.compile(
    r"(?i)\ba\s+las?\s+(\d{1,2})\s+y\s+(\d{1,2})\b"
    r"(?:\s*(?:de\s+la\s+(manana|tarde|noche|madrugada)|(am|pm)))?"
)


def _plano(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto or "")
    return "".join(
        c for c in descompuesto if unicodedata.category(c) != "Mn"
    ).lower()


def _a_24h(hora: int, minuto: int, momento: str) -> str | None:
    momento = momento.lower().replace(".", "")
    if momento in ("tarde", "noche", "pm") and hora < 12:
        hora += 12
    elif momento in ("noche", "madrugada", "am") and hora == 12:
        hora = 0
    if not (0 <= hora <= 23 and 0 <= minuto <= 59):
        return None
    return f"{hora:02d}:{minuto:02d}"


def normalizar_hora(valor: object) -> str | None:
    """Devuelve ``HH:MM`` o ``None``; nunca completa lo que falta."""
    coincidencia = _HORA_VALOR.match(str(valor or "").strip())
    if coincidencia is None:
        return None
    return _a_24h(
        int(coincidencia.group(1)),
        int(coincidencia.group(2) or 0),
        coincidencia.group(3) or "",
    )


def hora_de_cita(cita: str) -> str | None:
    """Hora dicha en la cita, solo si trae «de la mañana/tarde/noche» o am/pm."""
    texto = _plano(normalizar_texto(cita))
    coincidencia = _HORA_CITA.search(texto)
    if coincidencia is None:
        return None
    return _a_24h(
        int(coincidencia.group(1)),
        int(coincidencia.group(2) or 0),
        coincidencia.group(3) or coincidencia.group(4) or "",
    )


def hora_explicita(texto: str) -> str | None:
    """HH:MM dicho o escrito, sin exigir «de la mañana»."""
    plano = _plano(normalizar_texto(texto))
    coincidencia = _HORA_EXPLICITA.search(plano)
    if coincidencia is not None:
        return _a_24h(int(coincidencia.group(1)), int(coincidencia.group(2)), "")
    hablada = _HORA_CON_Y.search(plano)
    if hablada is not None:
        return _a_24h(
            int(hablada.group(1)),
            int(hablada.group(2)),
            hablada.group(3) or hablada.group(4) or "",
        )
    return None


def hora_de_recordatorio(texto: str) -> str | None:
    """Hora de un recordatorio: primero HH:MM, después la forma hablada."""
    return hora_explicita(texto) or hora_de_cita(texto)


def sostiene_fecha(cita: str) -> bool:
    """¿La cita contiene una fecha, y no solo una hora del día?"""
    texto = _plano(normalizar_texto(cita))
    texto = _HORA_CITA.sub(" ", texto)
    texto = re.sub(r"\ba\s+las?\b", " ", texto)

    if re.search(r"\b(?:19|20)\d{2}\b", texto):
        return True
    if any(mes in texto for mes in _MESES):
        return True
    if any(re.search(rf"\b{dia}\b", texto) for dia in _DIAS):
        return True
    if re.search(r"\b(hoy|ayer|anteayer|pasado manana|manana)\b", texto):
        return True
    return bool(re.search(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", texto))
