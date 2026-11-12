"""Tests de la cabecera de Banca y el fondo de Planta (v6.10)."""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

PANEL = RAIZ_SERVICIO / "app" / "web" / "templates" / "panel.html"
STATIC = RAIZ_SERVICIO / "app" / "web" / "static" / "brand"
ROUTER = RAIZ_SERVICIO / "app" / "m4_dashboard" / "router.py"
BANCOS = RAIZ_SERVICIO / "app" / "m4_dashboard" / "bancos.py"


def _migracion(numero: str) -> Path:
    for base in (RAIZ_SERVICIO, *RAIZ_SERVICIO.parents):
        candidato = base / "db" / "migrations" / numero
        if candidato.is_file():
            return candidato
    raise FileNotFoundError(numero)


def test_panel_tiene_cabecera_de_bancos_con_logos() -> None:
    html = PANEL.read_text(encoding="utf-8")
    assert 'class="card sec-ventanilla banca-hero"' in html
    assert "Banco Pichincha" in html
    assert "Banco Guayaquil" in html
    assert "Banco Internacional" in html
    assert "/static/brand/bancos/pichincha.svg" in html
    assert "/static/brand/bancos/guayaquil.svg" in html
    assert "/static/brand/bancos/internacional.svg" in html
    assert "function renderBancos(" in html
    assert "/api/v1/dashboard/bancos" in html
    assert 'id="banco-detalle"' in html
    assert 'data-banco="pichincha"' in html
    assert "async function seleccionarBanco(" in html
    assert "classList.toggle('activo'" in html
    assert 'id="dlg-banco"' in html
    assert "async function guardarBanco(" in html


def test_planta_usa_la_foto_de_fondo() -> None:
    html = PANEL.read_text(encoding="utf-8")
    assert 'class="card planta-agenda"' in html
    assert "/static/brand/fotos/planta-agenda.webp" in html
    assert ".planta-agenda" in html


def test_logos_y_fondo_existen() -> None:
    logos = {
        "pichincha.svg": "#FFD100",
        "guayaquil.svg": "#C7007E",
        "internacional.svg": "#F39200",
    }
    for nombre, color in logos.items():
        ruta = STATIC / "bancos" / nombre
        assert ruta.is_file(), nombre
        assert ruta.stat().st_size > 300, nombre
        assert color in ruta.read_text(encoding="utf-8"), nombre
    fondo = STATIC / "fotos" / "planta-agenda.webp"
    assert fondo.is_file()
    assert fondo.stat().st_size > 50_000


def test_endpoints_de_bancos_y_detalle() -> None:
    fuente = ROUTER.read_text(encoding="utf-8")
    assert '@router.get("/bancos")' in fuente
    assert '@router.get("/bancos/{slug}")' in fuente
    assert '@router.put("/bancos/{slug}")' in fuente
    assert "bancos_svc.listar" in fuente
    assert "bancos_svc.detalle" in fuente
    assert "bank_accounts" in BANCOS.read_text(encoding="utf-8")


def test_migracion_072_modela_los_bancos() -> None:
    sql = _migracion("072_bancos_detalle.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS bank_accounts" in sql
    assert "saldo_informado" in sql
    assert "1102.01" in sql and "1102.02" in sql and "1102.03" in sql
    assert "financial_liabilities" in sql
    assert "bank_account_id" in sql
