"""La fecha de negocio es la de Ecuador, no la del servidor ni la del navegador."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app import tiempo  # noqa: E402


def test_zona_es_ecuador() -> None:
    assert tiempo.ahora().tzinfo is not None
    assert str(tiempo.ahora().tzinfo) == "America/Guayaquil"


def test_hoy_es_la_fecha_de_ecuador() -> None:
    assert tiempo.hoy() == datetime.now(tiempo.ZONA).date()


def test_la_fecha_no_depende_de_utc() -> None:
    # En Ecuador nunca es "mañana" antes que en UTC.
    assert tiempo.hoy() <= datetime.utcnow().date()
