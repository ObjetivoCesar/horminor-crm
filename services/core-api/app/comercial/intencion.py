"""Intencion de cita en lenguaje natural, sin duplicar codigo.

Lo usan Gato interno y el webhook de WhatsApp: la fecha siempre sale de
``app.tiempo`` (America/Guayaquil). Lo que falta queda en ``None``; no se
inventa una fecha ni una hora.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from .. import tiempo
from . import leads as leads_svc

_RE_AGENDAR = re.compile(
    r"\b(agenda|agendar|agendame|programa|programar|reserva|reservar|solicita|solicitar|registra|registrar|anota|anotar|apunta|apuntar)\b",
    re.IGNORECASE,
)
_RE_CITA = re.compile(
    r"\b(cita|visita|visitar|reunion|medicion|medir|entrega|entregar)\b",
    re.IGNORECASE,
)
_RE_HORA = re.compile(r"\ba\s+las?\s+(\d{1,2})(?::(\d{2}))?\b", re.IGNORECASE)
_RE_HORA_MOMENTO = re.compile(
    r"\ba\s+las?\s+(\d{1,2})(?::(\d{2}))?\s*"
    r"(?:de\s+la\s+(manana|tarde|noche|madrugada)|(am|pm))",
    re.IGNORECASE,
)
_RE_HORA_RELOJ = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)")
_RE_HORA_H = re.compile(r"(?<!\d)(\d{1,2})\s*h(?:(\d{2}))?(?!\d)")
_RE_HORA_MEDIA = re.compile(r"\ba\s+las?\s+(\d{1,2})\s+y\s+media\b")
_RE_MEDIO_DIA = re.compile(r"\b(mediodia|medianoche)\b")
_RE_FECHA_NUMERICA = re.compile(
    r"(?<!\d)(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?(?!\d)"
)
_RE_FECHA_MES = re.compile(
    r"\b(\d{1,2})\s+de\s+([a-z]+)(?:\s+(?:de|del)\s+(\d{4}))?\b"
)
_RE_CORRECCION = re.compile(
    r"\b(rectifico|rectificar|corrijo|corregir|corrige|mejor|en\s+realidad|"
    r"cambia|cambiar|cambiarle|cambiemos|mueve|mover|movamos|muevela|muevala|pasala|"
    r"reagenda|reagendar|reagendala|reprograma|reprogramar|actualiza|actualizar|"
    r"no\s+es\s+(?:a\s+las?|el|la|hoy|manana)|perdon)\b",
    re.IGNORECASE,
)
_RE_CANCELAR = re.compile(
    r"\b(cancela|cancelar|anula|anular|elimina|eliminar|borra|borrar)\b",
    re.IGNORECASE,
)
_MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
_DIAS = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "domingo": 6,
}
_RE_NOMBRE = re.compile(
    r"\b(?:cita|visita|visitar|reunion|medicion|medir|entrega|entregar)\s+"
    r"(?:a|con|para|de)\s+"
    r"([a-z0-9 .'-]+?)(?=\s+(?:hoy|manana|pasado|a\s+las|para|el|la)\b|$)",
    re.IGNORECASE,
)


def es_peticion_cita(texto: str) -> bool:
    """True si el texto pide agendar una cita (no la confirma)."""
    t = leads_svc.normalizar(texto)
    return bool(_RE_AGENDAR.search(t) and _RE_CITA.search(t))


def _horas_dichas(texto: str) -> list[str]:
    """Todas las horas del texto, en orden de aparición.

    La última es la que vale en una corrección. Se combinan los formatos
    («3 de la tarde», «16», «16:00», «16h30») y se ordenan por posición.
    """
    t = leads_svc.normalizar(texto)
    encontradas: dict[int, str] = {}

    def guardar(pos: int, hh: int, mm: int, momento: str = "") -> None:
        momento = (momento or "").lower()
        if momento in ("tarde", "noche", "pm") and hh < 12:
            hh += 12
        elif momento in ("manana", "madrugada", "am") and hh == 12:
            hh = 0
        elif momento == "noche" and hh == 12:
            hh = 0
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            encontradas[pos] = f"{hh:02d}:{mm:02d}"

    for m in _RE_HORA_MEDIA.finditer(t):
        guardar(m.start(), int(m.group(1)), 30)
    for m in _RE_HORA_H.finditer(t):
        guardar(m.start(), int(m.group(1)), int(m.group(2) or 0))
    for m in _RE_HORA.finditer(t):
        guardar(m.start(), int(m.group(1)), int(m.group(2) or 0))
    for m in _RE_HORA_RELOJ.finditer(t):
        guardar(m.start(), int(m.group(1)), int(m.group(2)))
    for m in _RE_MEDIO_DIA.finditer(t):
        guardar(m.start(), 12 if m.group(1) == "mediodia" else 0, 0)
    # Al final: «2 de la tarde» y «2 y media» mandan sobre el «a las 2».
    for m in _RE_HORA_MOMENTO.finditer(t):
        guardar(
            m.start(),
            int(m.group(1)),
            int(m.group(2) or 0),
            m.group(3) or m.group(4) or "",
        )
    for m in _RE_HORA_MEDIA.finditer(t):
        guardar(m.start(), int(m.group(1)), 30)

    return [hora for _, hora in sorted(encontradas.items())]


def _fecha_dicha(texto: str, hoy: date) -> date | None:
    """Fecha presente en el texto; None si no se dijo ninguna.

    «de la mañana/tarde/noche» es la hora, no el día siguiente. Se quita antes
    de buscar «mañana» para no mover una cita al día equivocado.
    """
    t = leads_svc.normalizar(texto)
    t = re.sub(
        r"\b(?:de|en|por)\s+la\s+(?:manana|tarde|noche|madrugada)\b", " ", t
    )
    t = re.sub(r"\b(?:a|para)\s+la\s+(?:manana|tarde|noche)\b", " ", t)

    if re.search(r"\bpasado\s+manana\b", t):
        return hoy + timedelta(days=2)
    if re.search(r"\bmanana\b", t):
        return hoy + timedelta(days=1)
    if re.search(r"\bhoy\b", t):
        return hoy

    m = _RE_FECHA_NUMERICA.search(t)
    if m:
        dia, mes = int(m.group(1)), int(m.group(2))
        anio = int(m.group(3)) if m.group(3) else hoy.year
        if anio < 100:
            anio += 2000
        try:
            return date(anio, mes, dia)
        except ValueError:
            return None

    m = _RE_FECHA_MES.search(t)
    if m:
        dia = int(m.group(1))
        mes = _MESES.get(m.group(2))
        anio = int(m.group(3)) if m.group(3) else hoy.year
        if mes:
            try:
                return date(anio, mes, dia)
            except ValueError:
                return None

    for nombre_dia, indice in _DIAS.items():
        if re.search(rf"\b(?:este\s+|el\s+)?{nombre_dia}\b", t):
            dias = (indice - hoy.weekday()) % 7
            return hoy + timedelta(days=dias)
    return None


def es_correccion_cita(texto: str) -> bool:
    """«Rectifico, no es a la 13:00 sino a las 14:00»."""
    t = leads_svc.normalizar(texto)
    if any(palabra in t for palabra in ("recordatorio", "tarea")):
        return False
    no_es = re.search(r"\bno\s+es\s+(?:a\s+las?|el|la|hoy|manana)\b", t)
    no_hora = re.search(r"^\s*no[,;]?\s+a\s+las?\s+\d", t)
    if not (_RE_CORRECCION.search(t) or no_es or no_hora):
        return False
    # «Mejor agenda una visita...» o «registra la cita de Juan...» es una cita
    # nueva. La corrección se reserva a movimientos y rectificaciones.
    if _RE_AGENDAR.search(t) and not re.search(
        r"\b(rectifico|corrijo|corrige|no\s+es\s+(?:a\s+las?|el|la))\b", t
    ):
        return False
    if any(
        palabra in t
        for palabra in (
            "cita",
            "visita",
            "reunion",
            "agenda",
            "eso",
            "esa",
            "compromiso",
            "muevela",
            "muevala",
            "pasala",
            "reagendala",
        )
    ):
        return True
    limpio = t.strip(" .,!¡¿?")
    solo_hora = re.fullmatch(
        r"(?:mejor|perdon|en realidad|no|otra vez|que sea|rectifico|corrijo|corrige)?\s*"
        r"(?:a\s+las?|para\s+las?)?\s*\d{1,2}(?::\d{2})?"
        r"\s*(?:de\s+la\s+(?:manana|tarde|noche)|am|pm)?",
        limpio,
    )
    return solo_hora is not None or bool(no_es) or bool(no_hora)


def es_cancelacion_cita(texto: str) -> bool:
    t = leads_svc.normalizar(texto)
    if any(palabra in t for palabra in ("recordatorio", "tarea")):
        return False
    if not _RE_CANCELAR.search(t) and not re.search(
        r"\b(cancelala|cancelalo|anulala|borrala)\b", t
    ):
        return False
    return bool(
        re.search(
            r"\b(cita|visita|reunion|agenda|compromiso|eso|esa)\b", t
        )
    )


def _hora_ambigua(texto: str) -> bool:
    """«a las 2» sin tarde/noche ni minutos: no se asume la madrugada."""
    t = leads_svc.normalizar(texto)
    if re.search(
        r"\d{1,2}:\d{2}|\d{1,2}\s*h|de\s+la\s+(?:manana|tarde|noche)|"
        r"\b(?:am|pm)\b|mediodia|medianoche|y\s+media",
        t,
    ):
        return False
    m = _RE_HORA.search(t)
    return bool(m and not m.group(2) and 1 <= int(m.group(1)) <= 7)


def parse_correccion(
    texto: str, *, fecha_base: date, hora_base: str
) -> dict[str, Any]:
    """Qué cambia la corrección. Lo que no se dijo se queda como estaba."""
    t = leads_svc.normalizar(texto)
    horas = _horas_dichas(t)
    fecha = _fecha_dicha(texto, tiempo.hoy())
    if _hora_ambigua(texto):
        horas = []
    # «No es a la 1» niega una hora y no ofrece otra: hay que preguntar.
    if len(horas) == 1 and re.search(r"\bno\s+es\s+a\s+las?\s+\d", t):
        horas = []
    return {
        "fecha": fecha or fecha_base,
        "hora": horas[-1] if horas else hora_base,
        "dijo_fecha": fecha is not None,
        "dijo_hora": bool(horas),
    }


def _nombre_valido(nombre: str | None) -> str | None:
    """Descarta lo que el regex capturó de más: fechas, horas o tipos."""
    if not nombre:
        return None
    limpio = " ".join(str(nombre).split()).strip(" .'-")
    corte = re.search(
        r"\b(?:hoy|manana|mañana|pasado|lunes|martes|miercoles|miércoles|"
        r"jueves|viernes|sabado|sábado|domingo|enero|febrero|marzo|abril|"
        r"mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|"
        r"diciembre|a\s+las|de\s+la)\b",
        limpio,
        re.IGNORECASE,
    )
    if corte:
        limpio = limpio[: corte.start()].strip(" .'-")
    plano = leads_svc.normalizar(limpio)
    if not plano or len(plano) < 2:
        return None
    if re.fullmatch(r"[\d\s:./-]+", plano):
        return None
    if plano in (
        "visita",
        "cita",
        "reunion",
        "medicion",
        "entrega",
        "cliente",
        "un cliente",
        "mi agenda",
    ):
        return None
    return limpio


def parse_cita(texto: str) -> dict[str, Any]:
    """Extrae fecha, hora, tipo y nombre. Lo que falte queda en None."""
    t = leads_svc.normalizar(texto)
    hoy = tiempo.hoy()
    fecha = _fecha_dicha(texto, hoy)

    horas = _horas_dichas(t)
    hora: str | None = horas[0] if horas else None
    if _hora_ambigua(texto):
        hora = None

    nombre: str | None = None
    m2 = _RE_NOMBRE.search(t)
    if m2:
        nombre = _nombre_valido(m2.group(1))

    tipo = "VISITA"
    if "reunion" in t:
        tipo = "REUNION"
    elif "medicion" in t:
        tipo = "MEDICION"
    elif "entrega" in t:
        tipo = "ENTREGA"

    return {"fecha": fecha, "hora": hora, "nombre": nombre, "tipo": tipo}


__all__ = ["es_peticion_cita", "parse_cita"]
