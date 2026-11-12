"""Tests de multimedia del cliente (v6.9).

Validan las reglas puras: clasificacion, limites, carpeta por cliente,
compresion WebP, firma de Bunny y defensa contra rutas maliciosas. No
requieren base de datos ni credenciales.
"""

from __future__ import annotations

import base64
import hashlib
import io
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from PIL import Image

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.services import media as media_svc  # noqa: E402

PANEL = RAIZ_SERVICIO / "app" / "web" / "templates" / "panel.html"
AJUSTES = SimpleNamespace(
    media_max_imagen_mb=25,
    media_max_video_mb=250,
    media_max_audio_mb=40,
    media_max_documento_mb=25,
    media_max_pixeles=50_000_000,
    media_video_max_seg=180,
    media_video_alto=720,
    media_video_crf=28,
    media_dir="/tmp/horminor-media-test",
)


def _migracion() -> Path:
    for base in (RAIZ_SERVICIO, *RAIZ_SERVICIO.parents):
        candidato = base / "db" / "migrations" / "071_media_clientes.sql"
        if candidato.is_file():
            return candidato
    raise FileNotFoundError("071_media_clientes.sql no encontrada")


def test_carpeta_cliente_usa_cedula_y_evita_homonimos() -> None:
    assert media_svc.carpeta_cliente("Ing. Reyes & Vélez", "1712345678", "1799", "uuid") == (
        "ing_reyes_velez_1712345678"
    )
    # Sin cedula usa el RUC; sin ambos, el id. Nunca inventa un documento.
    assert media_svc.carpeta_cliente("Debug", None, "1790012345001", "uuid") == (
        "debug_1790012345001"
    )
    assert media_svc.carpeta_cliente("Cliente Prueba", None, None, "83d195e8-9ea5-4bb3-a5f0") == (
        "cliente_prueba_83d195e89ea5"
    )


def test_clasificacion_audio_video_y_extensiones_prohibidas() -> None:
    assert media_svc.detectar_tipo("foto.HEIC", "image/heic") == "IMAGEN"
    assert media_svc.detectar_tipo("audio.webm", "audio/webm") == "AUDIO"
    assert media_svc.detectar_tipo("clip.webm", "video/webm") == "VIDEO"
    assert media_svc.detectar_tipo("guia.pdf", "application/pdf") == "DOCUMENTO"
    with pytest.raises(media_svc.MediaInvalido):
        media_svc.detectar_tipo("virus.exe", "application/octet-stream")


def test_limites_por_tipo() -> None:
    media_svc.validar_tamano("IMAGEN", 1024, AJUSTES)
    with pytest.raises(media_svc.MediaInvalido):
        media_svc.validar_tamano("IMAGEN", 26 * 1024 * 1024, AJUSTES)
    with pytest.raises(media_svc.MediaInvalido):
        media_svc.validar_tamano("AUDIO", 0, AJUSTES)


def test_comprime_imagen_a_webp_y_limita_lado() -> None:
    original = Image.new("RGB", (3000, 2000), (200, 120, 30))
    buffer = io.BytesIO()
    original.save(buffer, "PNG")
    resultado = media_svc.comprimir_imagen(buffer.getvalue(), AJUSTES)
    assert resultado.tipo == "IMAGEN"
    assert resultado.mime == "image/webp"
    assert resultado.extension == "webp"
    assert max(resultado.ancho, resultado.alto) == 1920
    with Image.open(io.BytesIO(resultado.datos)) as comprobacion:
        assert comprobacion.format == "WEBP"


def test_firma_bunny_usa_token_y_expiracion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(media_svc.time, "time", lambda: 1_000_000_000)
    url = media_svc.firmar_url_bunny(
        "https://cdn.ejemplo.com/", "/clientes/reyes/foto.webp", "clave-secreta", ttl_segundos=60
    )
    expira = 1_000_000_060
    esperado = quote(
        base64.b64encode(
            hashlib.sha256(f"clave-secreta/clientes/reyes/foto.webp{expira}".encode()).digest()
        ).decode(),
        safe="",
    )
    assert url == f"https://cdn.ejemplo.com/clientes/reyes/foto.webp?token={esperado}&expires={expira}"
    # Sin clave devuelve la URL publica, sin inventar token.
    assert media_svc.firmar_url_bunny("cdn.ejemplo.com", "a/b.webp", None) == (
        "https://cdn.ejemplo.com/a/b.webp"
    )


def test_ruta_sandbox_no_permite_escapar(tmp_path: Path) -> None:
    ruta = media_svc.ruta_sandbox(str(tmp_path), "clientes/reyes/foto.webp")
    assert str(ruta).startswith(str(tmp_path.resolve()))
    with pytest.raises(media_svc.MediaInvalido):
        media_svc.ruta_sandbox(str(tmp_path), "../secreto.txt")


def test_migracion_071_define_media_y_cedula() -> None:
    sql = _migracion().read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS cedula" in sql
    assert "CREATE TABLE IF NOT EXISTS media_assets" in sql
    assert "ux_clients_cedula" in sql
    assert "storage_path" in sql and "sha256" in sql
    assert "etiquetas" in sql


def test_panel_tiene_clip_whatsapp_y_columnas_iguales() -> None:
    html = PANEL.read_text(encoding="utf-8")
    assert 'id="chat-sheet"' in html
    assert 'id="chat-file-galeria"' in html
    assert 'id="chat-file-camara"' in html
    assert 'id="chat-file-documento"' in html
    assert "function chatElegir(" in html
    assert "async function chatSubirArchivo(" in html
    assert "async function chatGrabarAudio(" in html
    assert 'id="ficha-cedula"' in html
    assert 'class="card clientes-col"' in html
    assert ".clientes-col { display: flex; flex-direction: column; height: 100%; }" in html
    assert "chat-ticks" in html
    assert "chat-img" in html
