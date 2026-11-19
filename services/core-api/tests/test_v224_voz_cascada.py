"""Cascada de claves de Groq: se usa la de respaldo si la principal falla."""

from __future__ import annotations

import pytest

from app.voz.proveedores.groq import GroqCascada
from app.voz.stt import _claves_groq


class _Respuesta:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = "" if status_code < 400 else f"error {status_code}"

    def json(self) -> dict:
        return self._payload


class _Cliente:
    """Devuelve las respuestas en orden y apunta las claves usadas."""

    def __init__(self, respuestas: list[_Respuesta]) -> None:
        self.respuestas = list(respuestas)
        self.claves: list[str] = []

    async def post(self, url, *, headers, files, data):
        self.claves.append(headers["Authorization"].replace("Bearer ", ""))
        return self.respuestas.pop(0)


def test_claves_en_orden_sin_duplicados_y_sin_espacios(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", " gsk_principal ")
    monkeypatch.setenv("GROQ_API_KEY2", "gsk_respaldo")
    monkeypatch.setenv("GROQ_API_KEY3", "gsk_principal")
    monkeypatch.delenv("GROQ_API_KEYS", raising=False)

    claves = _claves_groq({})
    assert claves == ["gsk_principal", "gsk_respaldo"]


def test_cfg_del_panel_tiene_prioridad(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_entorno")

    claves = _claves_groq({"api_key": "gsk_panel", "api_key2": "gsk_panel_2"})
    assert claves[:2] == ["gsk_panel", "gsk_panel_2"]
    assert "gsk_entorno" in claves


@pytest.mark.asyncio
async def test_usa_la_clave_de_respaldo_si_la_principal_da_401():
    cliente = _Cliente(
        [
            _Respuesta(401),
            _Respuesta(200, {"text": "hola", "language": "es"}),
        ]
    )
    proveedor = GroqCascada(["gsk_mala", "gsk_buena"], http_client=cliente)

    resultado = await proveedor.transcribir(b"audio", "audio/wav")

    assert resultado.estado == "COMPLETADO"
    assert resultado.texto_crudo == "hola"
    assert cliente.claves == ["gsk_mala", "gsk_buena"]


@pytest.mark.asyncio
async def test_no_gasta_la_respaldo_si_el_audio_es_invalido():
    cliente = _Cliente([_Respuesta(400)])
    proveedor = GroqCascada(["gsk_mala", "gsk_buena"], http_client=cliente)

    resultado = await proveedor.transcribir(b"audio", "audio/wav")

    assert resultado.estado == "FALLIDO"
    assert "GROQ_HTTP_400" in (resultado.error or "")
    assert cliente.claves == ["gsk_mala"]


@pytest.mark.asyncio
async def test_si_todas_fallan_lo_dice_sin_exponer_claves():
    cliente = _Cliente([_Respuesta(401), _Respuesta(429)])
    proveedor = GroqCascada(["gsk_uno", "gsk_dos"], http_client=cliente)

    resultado = await proveedor.transcribir(b"audio", "audio/wav")

    assert resultado.estado == "FALLIDO"
    error = resultado.error or ""
    assert error.startswith("GROQ_TODAS_LAS_CLAVES_FALLARON")
    assert "gsk_" not in error


@pytest.mark.asyncio
async def test_sin_claves_se_degrada_sin_inventar():
    proveedor = GroqCascada([])

    resultado = await proveedor.transcribir(b"audio", "audio/wav")

    assert resultado.estado == "DEGRADADO_SIN_CREDENCIAL"
    assert resultado.texto_crudo is None
