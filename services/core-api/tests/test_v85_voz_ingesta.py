"""Ingesta de voz: validaciones y degradación sin proveedor."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.services.media import MediaInvalido
from app.voz.ingesta import validar_audio
from app.voz.stt import AdaptadorPendiente, SinProveedor


def _settings(**extra) -> SimpleNamespace:
    base = {
        "media_max_audio_mb": 1,
        "media_max_imagen_mb": 10,
        "media_max_video_mb": 200,
        "media_max_documento_mb": 20,
    }
    base.update(extra)
    return SimpleNamespace(**base)


def test_acepta_audio_valido() -> None:
    procesado = validar_audio(b"OggS-falso", "nota.ogg", "audio/ogg", _settings())
    assert procesado.tipo == "AUDIO"
    assert procesado.extension == "ogg"
    assert procesado.datos == b"OggS-falso"


def test_rechaza_archivo_que_no_es_audio() -> None:
    with pytest.raises(MediaInvalido):
        validar_audio(b"hola", "nota.txt", "text/plain", _settings())


def test_rechaza_audio_vacio() -> None:
    with pytest.raises(MediaInvalido):
        validar_audio(b"", "nota.ogg", "audio/ogg", _settings())


def test_rechaza_audio_sobre_el_limite() -> None:
    grande = b"x" * (1024 * 1024 + 1)
    with pytest.raises(MediaInvalido):
        validar_audio(grande, "nota.ogg", "audio/ogg", _settings())


def test_sin_proveedor_no_inventa_texto() -> None:
    resultado = asyncio.run(
        SinProveedor().transcribir(b"OggS", "audio/ogg")
    )
    assert resultado.estado == "DEGRADADO_SIN_CREDENCIAL"
    assert resultado.texto_crudo is None
    assert resultado.segmentos == []
    assert "GROQ_API_KEY" in (resultado.error or "")


def test_adaptador_pendiente_falla_explicito() -> None:
    resultado = asyncio.run(
        AdaptadorPendiente().transcribir(b"OggS", "audio/ogg")
    )
    assert resultado.estado == "FALLIDO"
    assert resultado.texto_crudo is None
    assert "ADAPTADOR_STT_NO_IMPLEMENTADO" in (resultado.error or "")
