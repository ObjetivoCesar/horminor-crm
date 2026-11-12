"""Tests del historial CHAT por cliente (v6.8).

No tocan base de datos: validan el contrato de la migracion, la logica pura
de limpieza de mensajes y que el panel tenga la pestana y sus puntos de
entrada. La prueba real de persistencia se hace contra el stack local.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.routers.chat_clientes import _id_cliente, _jsonb, limpiar_cuerpo  # noqa: E402

PANEL = RAIZ_SERVICIO / "app" / "web" / "templates" / "panel.html"
MAIN = RAIZ_SERVICIO / "app" / "main.py"


def _ruta_migracion() -> Path:
    """Funciona con el servicio suelto y dentro del contenedor (/app/db)."""
    for base in (RAIZ_SERVICIO, *RAIZ_SERVICIO.parents):
        candidato = base / "db" / "migrations" / "070_chat_clientes.sql"
        if candidato.is_file():
            return candidato
    raise FileNotFoundError("070_chat_clientes.sql no encontrada")


MIGRACION = _ruta_migracion()


def test_limpiar_cuerpo_normaliza_y_valida() -> None:
    assert limpiar_cuerpo("  Hola \n\n  Julio, ¿cómo va la obra? ") == (
        "Hola Julio, ¿cómo va la obra?"
    )
    with pytest.raises(ValueError):
        limpiar_cuerpo("   \n  ")
    with pytest.raises(ValueError):
        limpiar_cuerpo("x" * 8001)


def test_id_cliente_normaliza_uuid_y_rechaza_basura() -> None:
    assert _id_cliente("3F2504E0-4F89-11D3-9A0C-0305E82C3301") == (
        "3f2504e0-4f89-11d3-9a0c-0305e82c3301"
    )
    with pytest.raises(HTTPException) as exc:
        _id_cliente("no-es-un-uuid")
    assert exc.value.status_code == 404


def test_jsonb_acepta_texto_objeto_y_nulo() -> None:
    assert _jsonb('[{"tipo": "foto"}]', []) == [{"tipo": "foto"}]
    assert _jsonb([{"tipo": "foto"}], []) == [{"tipo": "foto"}]
    assert _jsonb(None, []) == []
    assert _jsonb("no-json", {}) == {}


def test_migracion_define_tablas_indices_y_vista() -> None:
    sql = MIGRACION.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS chat_conversaciones" in sql
    assert "CREATE TABLE IF NOT EXISTS chat_mensajes" in sql
    assert "UNIQUE (cliente_id, canal)" in sql
    assert "ux_chat_mensajes_whatsapp" in sql
    assert "to_tsvector('spanish'" in sql
    assert "trg_chat_ultimo_mensaje" in sql
    assert "CREATE OR REPLACE VIEW v_chat_conversacion" in sql
    assert "no_leidos" in sql


def test_router_registrado_en_la_api() -> None:
    fuente = MAIN.read_text(encoding="utf-8")
    assert "chat_clientes" in fuente
    assert "app.include_router(chat_clientes.router)" in fuente


def test_panel_tiene_la_pestana_chat_y_su_compositor() -> None:
    html = PANEL.read_text(encoding="utf-8")
    assert "💬 Chat" in html
    assert 'onclick="cambiarTabCarpeta(\'chat\')"' in html
    assert 'id="chat-hilo"' in html
    assert 'id="chat-input"' in html
    assert "async function chatCargar(" in html
    assert "async function chatEnviar(" in html
    assert "async function chatMarcarLeido(" in html
    assert "/chat/leido" in html
    assert ".chat-burbuja" in html
    assert "renderChatBadge()" in html
