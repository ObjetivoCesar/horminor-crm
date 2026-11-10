"""Tests de la UX de Superadmin v6.4 (action cards y cero JSON crudo)."""

from __future__ import annotations

from pathlib import Path

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
PANEL = RAIZ_SERVICIO / "app" / "web" / "templates" / "panel.html"


def test_superadmin_action_cards_y_accesos_directos() -> None:
    html = PANEL.read_text(encoding="utf-8")
    assert "CENTRO DE CONTROL" in html
    assert "¿Qué vas a configurar hoy?" in html
    assert "Usuarios y accesos" in html
    assert "Caja chica y horarios" in html
    assert "Recetas, flota y precios" in html
    assert "Tasas y conteo de silos" in html
    assert 'id="perfiles-lista"' in html
    assert 'id="reglas-resumen"' in html
    assert 'id="dlg-super-usuarios"' in html
    assert 'id="dlg-super-caja"' in html
    assert 'id="dlg-super-recetas"' in html
    assert 'id="dlg-super-tasas"' in html
    assert "+ Crear usuario" in html
    assert "Probar vista" in html
    assert "Viendo como:" in html
    assert "+ Crear / gestionar usuarios" in html


def test_superadmin_sin_json_crudo_ni_null_literal() -> None:
    html = PANEL.read_text(encoding="utf-8")
    assert "data-json" not in html
    assert 'placeholder="null"' not in html
    assert "Recetas (JSON" not in html
    assert "Flota (JSON" not in html
    assert "Configuración en caliente" not in html
    # Los parámetros financieros usan placeholders humanos.
    assert "Sin definir (ej. 12.5%)" in html
