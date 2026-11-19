"""Fecha y hora oficial del CRM: America/Guayaquil.

Una sola fuente para todo modulo que dependa del dia (leads, citas, cierres).
Nunca `datetime.now()` sin zona para decisiones de negocio.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

ZONA = ZoneInfo("America/Guayaquil")


def ahora() -> datetime:
    """Fecha y hora actuales en Ecuador, con zona."""
    return datetime.now(ZONA)


def hoy() -> date:
    """Fecha actual en Ecuador (la que usa el negocio)."""
    return ahora().date()


def iso() -> str:
    """Marca de tiempo legible de Ecuador."""
    return ahora().isoformat(timespec="seconds")
