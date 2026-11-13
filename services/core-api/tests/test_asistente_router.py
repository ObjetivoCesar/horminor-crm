"""Test del endpoint del asistente: el rol no viaja en el body."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

import app.asistente.router as mod  # noqa: E402
from app.asistente.orquestador import Respuesta  # noqa: E402


def _cliente(monkeypatch) -> TestClient:
    async def falso(
        pregunta: str,
        rol: str,
        biblio,
        nombre=None,
        historial=None,
        actor_id="panel",
        conversacion_id=None,
        modo_envio="",
    ):
        return Respuesta(f"{rol}:{pregunta}", "OK")

    monkeypatch.setattr(mod, "responder_detallado", falso)
    app = FastAPI()
    app.include_router(mod.router)
    app.state.pool = object()
    return TestClient(app)


def test_chat_usa_rol_del_header(monkeypatch) -> None:
    cliente = _cliente(monkeypatch)
    r = cliente.post(
        "/api/v1/asistente/chat",
        json={"mensaje": "¿Quién me debe?"},
        headers={"X-Panel-Role": "secretaria", "X-Panel-Name": "Ana"},
    )
    assert r.status_code == 200
    assert r.json()["respuesta"] == "SECRETARIA:¿Quién me debe?"
    assert r.json()["conversacion_id"]


def test_chat_sin_sesion_retorna_401(monkeypatch) -> None:
    cliente = _cliente(monkeypatch)
    r = cliente.post("/api/v1/asistente/chat", json={"mensaje": "hola"})
    assert r.status_code == 401


def test_chat_rechaza_actor_context_en_el_body(monkeypatch) -> None:
    cliente = _cliente(monkeypatch)
    r = cliente.post(
        "/api/v1/asistente/chat",
        json={
            "mensaje": "hola",
            "actor_context": {"rol": "SUPERADMIN", "actor_id": "hack"},
        },
        headers={"X-Panel-Role": "secretaria"},
    )
    assert r.status_code == 422


def test_header_desconocido_retorna_401(monkeypatch) -> None:
    cliente = _cliente(monkeypatch)
    r = cliente.post(
        "/api/v1/asistente/chat",
        json={"mensaje": "hola"},
        headers={"X-Panel-Role": "root"},
    )
    assert r.status_code == 401
