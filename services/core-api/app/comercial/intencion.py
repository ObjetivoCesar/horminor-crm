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
_RE_NOMBRE = re.compile(
    r"\b(?:cita|visita|visitar|reunion|medicion|medir|entrega|entregar)\s+"
    r"(?:a|con|para|de)\s+"
    r"([a-z0-9 .'-]+?)(?=\s+(?:hoy|manana|pasado|a\s+las)\b|$)",
    re.IGNORECASE,
)


def es_peticion_cita(texto: str) -> bool:
    """True si el texto pide agendar una cita (no la confirma)."""
    return bool(_RE_AGENDAR.search(texto or "") and _RE_CITA.search(texto or ""))


def parse_cita(texto: str) -> dict[str, Any]:
    """Extrae fecha, hora, tipo y nombre. Lo que falte queda en None."""
    t = leads_svc.normalizar(texto)
    hoy = tiempo.hoy()
    fecha: date | None = None
    if "pasado manana" in t:
        fecha = hoy + timedelta(days=2)
    elif "manana" in t:
        fecha = hoy + timedelta(days=1)
    elif "hoy" in t:
        fecha = hoy

    if fecha is None:
        # «este sábado», «el domingo», «el lunes que viene»: el calendario se
        # calcula desde la fecha de Ecuador, no desde el navegador.
        for nombre_dia, indice in (
            ("sabado", 5),
            ("domingo", 6),
            ("lunes", 0),
            ("martes", 1),
            ("miercoles", 2),
            ("jueves", 3),
            ("viernes", 4),
        ):
            if re.search(rf"\b(?:este\s+|el\s+)?{nombre_dia}\b", t):
                fecha = hoy + timedelta(days=(indice - hoy.weekday()) % 7)
                break

    hora: str | None = None
    m = _RE_HORA.search(t)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2) or 0)
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            hora = f"{hh:02d}:{mm:02d}"

    nombre: str | None = None
    m2 = _RE_NOMBRE.search(t)
    if m2:
        nombre = m2.group(1).strip(" .'-") or None

    tipo = "VISITA"
    if "reunion" in t:
        tipo = "REUNION"
    elif "medicion" in t:
        tipo = "MEDICION"
    elif "entrega" in t:
        tipo = "ENTREGA"

    return {"fecha": fecha, "hora": hora, "nombre": nombre, "tipo": tipo}


__all__ = ["es_peticion_cita", "parse_cita"]
