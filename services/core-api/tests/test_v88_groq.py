"""Adaptador Groq: parseo de palabras/tiempos y degradación."""

from __future__ import annotations

import asyncio
import math

import pytest

from app.voz.proveedores.groq import GroqSTT, parsear_respuesta
from app.voz.stt import construir_proveedor

PAYLOAD = {
    "text": "quiere veinticinco cubos",
    "language": "es",
    "segments": [
        {
            "start": 0.0,
            "end": 2.0,
            "text": "quiere veinticinco cubos",
            "avg_logprob": -0.1,
        }
    ],
    "words": [
        {"word": "quiere", "start": 0.0, "end": 0.4},
        {"word": "veinticinco", "start": 0.4, "end": 1.2},
        {"word": "cubos", "start": 1.2, "end": 1.8},
    ],
}


def test_parsea_texto_palabras_y_tiempos() -> None:
    resultado = parsear_respuesta(PAYLOAD, "whisper-large-v3")

    assert resultado.estado == "COMPLETADO"
    assert resultado.texto_crudo == "quiere veinticinco cubos"
    assert resultado.duracion_ms == 2000
    assert [p["palabra"] for p in resultado.palabras] == [
        "quiere",
        "veinticinco",
        "cubos",
    ]
    assert resultado.palabras[1]["inicio_ms"] == 400
    assert resultado.palabras[1]["fin_ms"] == 1200
    assert resultado.palabras[1]["confianza"] == pytest.approx(
        math.exp(-0.1), abs=1e-6
    )
    assert resultado.costo_usd > 0


def test_texto_vacio_es_fallo_sin_inventar() -> None:
    resultado = parsear_respuesta({"text": "", "segments": []}, "whisper-large-v3")
    assert resultado.estado == "FALLIDO"
    assert resultado.texto_crudo is None


class _Respuesta:
    def __init__(self, status_code: int, payload=None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _Cliente:
    def __init__(self, respuesta: _Respuesta) -> None:
        self.respuesta = respuesta
        self.llamada = None

    async def post(self, url, **kwargs):
        self.llamada = (url, kwargs)
        return self.respuesta

    async def aclose(self) -> None:
        return None


def test_adaptador_envia_modelo_idioma_y_granularidad() -> None:
    cliente = _Cliente(_Respuesta(200, PAYLOAD))
    resultado = asyncio.run(
        GroqSTT("clave", http_client=cliente).transcribir(b"OggS", "audio/ogg")
    )

    assert resultado.estado == "COMPLETADO"
    _, kwargs = cliente.llamada
    campos = dict(kwargs["data"])
    assert campos["model"] == "whisper-large-v3"
    assert campos["language"] == "es"
    assert campos["response_format"] == "verbose_json"
    assert kwargs["headers"]["Authorization"] == "Bearer clave"


def test_http_401_es_fallo_con_motivo() -> None:
    cliente = _Cliente(_Respuesta(401, text="invalid api key"))
    resultado = asyncio.run(
        GroqSTT("mala", http_client=cliente).transcribir(b"OggS", "audio/ogg")
    )

    assert resultado.estado == "FALLIDO"
    assert "GROQ_HTTP_401" in (resultado.error or "")


def test_sin_clave_no_finge_transcripcion() -> None:
    resultado = asyncio.run(GroqSTT("").transcribir(b"OggS", "audio/ogg"))
    assert resultado.estado == "DEGRADADO_SIN_CREDENCIAL"
    assert resultado.texto_crudo is None


def test_construir_proveedor_usa_groq_si_hay_clave(monkeypatch) -> None:
    async def _setting(_pool, _clave, _defecto):
        return {}

    monkeypatch.setattr("app.voz.stt.setting", _setting)
    monkeypatch.setenv("GROQ_API_KEY", "clave-de-prueba")

    proveedor = asyncio.run(construir_proveedor(None, None))
    assert proveedor.nombre == "groq"


def test_construir_proveedor_degrada_sin_clave(monkeypatch) -> None:
    async def _setting(_pool, _clave, _defecto):
        return {}

    monkeypatch.setattr("app.voz.stt.setting", _setting)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    proveedor = asyncio.run(construir_proveedor(None, None))
    assert proveedor.nombre == "NO_CONFIGURADO"
