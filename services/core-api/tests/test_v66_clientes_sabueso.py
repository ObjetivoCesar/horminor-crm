"""Tests del buscador Sabueso y la UX de Carpetas de Clientes v6.6."""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.routers.clients_search import (  # noqa: E402
    _coincide_orden,
    _coincide_texto,
    _query_compacta,
    norm_texto,
)

PANEL = RAIZ_SERVICIO / "app" / "web" / "templates" / "panel.html"


def test_normalizacion_ortografica_y_fonetica() -> None:
    assert norm_texto("Vaca & Vélez") == norm_texto("baca & beles")
    assert norm_texto("Zambrano") == norm_texto("sambrano")
    assert norm_texto("Reyes") == norm_texto("REYES")
    assert norm_texto("Loreto") == "loreto"


def test_compacta_espacios_en_patrones_de_trabajo() -> None:
    assert _query_compacta("7 m3") == "7m3"
    assert _query_compacta("FC 210") == "fc-210"
    assert _query_compacta("# 56") == "#56"


def test_patron_volumen_y_resistencia_y_orden() -> None:
    orden = {"numero": 56, "volumen_m3": 7, "resistencia": "FC-210", "notas": "Obra Loreto"}
    assert _coincide_orden("7m3", orden)
    assert _coincide_orden("7 m3", orden)
    assert _coincide_orden("FC-210", orden)
    assert _coincide_orden("fc 210", orden)
    assert _coincide_orden("#56", orden)
    assert not _coincide_orden("#55", orden)
    assert not _coincide_orden("8m3", orden)


def test_coincidencia_por_texto_de_obra() -> None:
    assert _coincide_texto("loreto", "Obra Puente Loreto")
    assert _coincide_texto("puente loreto", "Obra Puente Loreto")
    assert not _coincide_texto("sacha", "Obra Puente Loreto")


def test_vista_clientes_tiene_banner_sabueso_y_pestanas() -> None:
    html = PANEL.read_text(encoding="utf-8")
    assert "CARTERA Y EXPEDIENTES" in html
    assert "¿Qué clientes necesitas encontrar hoy?" in html
    assert "Con deuda / Fiado" in html
    assert "En obra / Entregas activas" in html
    assert "Pagos y Transferencias" in html
    assert "Todos y Prospectos" in html
    assert 'id="buscar-cliente"' in html
    assert 'id="sabueso-sugerencias"' in html
    assert 'id="filtro-ciudad"' in html
    assert 'id="filtro-pago"' in html
    assert 'id="filtro-fecha"' in html
    assert 'id="filtro-resistencia"' in html
    assert 'id="cli-paginacion"' in html
    assert "Órdenes y Viajes" in html
    assert "Pagos y Estado de Cuenta" in html
    assert "Ficha y Datos" in html
