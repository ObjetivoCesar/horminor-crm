"""Procesamiento de multimedia del cliente (v6.9).

El binario nunca se guarda en PostgreSQL. Este modulo valida, comprime y
calcula la ruta; el router lo sube a Bunny.net (o al sandbox local) y registra
el indice en ``media_assets``.

Reglas:
- Imagenes: se convierten a WebP, se limita el lado mayor y se quita el EXIF.
- Videos: se recomprimen a H.264/AAC dentro de 1280x720 y un maximo de segundos.
- Audios: pasan tal cual (solo se valida el tope).
- Documentos: lista blanca de extensiones; nunca ejecutables.
- La ruta usa ``clientes/<nombre>_<cedula>/`` para que no haya homonimos.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging
import os
import re
import secrets
import shutil
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from PIL import Image, ImageOps

try:  # HEIC de iPhone, si el paquete esta instalado
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:  # pragma: no cover - sin HEIC simplemente se rechaza
    pass

log = logging.getLogger(__name__)

TIPOS = ("IMAGEN", "VIDEO", "AUDIO", "DOCUMENTO")

_EXT_IMAGEN = {"jpg", "jpeg", "png", "webp", "gif", "bmp", "tif", "tiff", "heic", "heif"}
_EXT_VIDEO = {"mp4", "mov", "m4v", "webm", "3gp", "avi", "mkv"}
_EXT_AUDIO = {"ogg", "opus", "mp3", "m4a", "wav", "webm", "aac", "amr"}
_EXT_DOCUMENTO = {"pdf", "doc", "docx", "xls", "xlsx", "csv", "txt", "pptx", "ppt"}
_EXT_PROHIBIDAS = {
    "exe", "bat", "cmd", "ps1", "sh", "js", "vbs", "scr", "msi", "com",
    "jar", "py", "php", "html", "htm", "svg", "dll", "apk", "iso",
}

_MIME_POR_EXT = {
    "webp": "image/webp",
    "mp4": "video/mp4",
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
    "opus": "audio/opus",
    "m4a": "audio/mp4",
    "wav": "audio/wav",
    "pdf": "application/pdf",
}


class MediaInvalido(ValueError):
    """El archivo no cumple las reglas (tipo, tamano o contenido)."""


class MediaNoDisponible(RuntimeError):
    """Falta ffmpeg o el almacenamiento no esta configurado."""


@dataclass
class ArchivoProcesado:
    datos: bytes
    tipo: str
    mime: str
    extension: str
    ancho: int | None = None
    alto: int | None = None
    duracion_seg: float | None = None


def extension(nombre: str) -> str:
    return (Path(nombre or "").suffix.lstrip(".") or "").lower()


def detectar_tipo(nombre: str, mime: str | None, tipo_declarado: str | None = None) -> str:
    """Clasifica por extension y MIME; una extension prohibida falla siempre."""
    ext = extension(nombre)
    if ext in _EXT_PROHIBIDAS:
        raise MediaInvalido(f"extension no permitida: .{ext}")
    if tipo_declarado in TIPOS:
        return str(tipo_declarado)
    mime = (mime or "").lower()
    if mime.startswith("video/"):
        return "VIDEO"
    if mime.startswith("audio/"):
        return "AUDIO"
    if mime.startswith("image/"):
        return "IMAGEN"
    if ext in _EXT_VIDEO:
        return "VIDEO"
    if ext in _EXT_IMAGEN:
        return "IMAGEN"
    if ext in _EXT_AUDIO:
        return "AUDIO"
    if ext in _EXT_DOCUMENTO:
        return "DOCUMENTO"
    raise MediaInvalido(f"tipo de archivo no soportado: {nombre or mime or 'desconocido'}")


def limite_bytes(tipo: str, settings: Any) -> int:
    mb = {
        "IMAGEN": settings.media_max_imagen_mb,
        "VIDEO": settings.media_max_video_mb,
        "AUDIO": settings.media_max_audio_mb,
        "DOCUMENTO": settings.media_max_documento_mb,
    }.get(tipo, settings.media_max_documento_mb)
    return int(mb) * 1024 * 1024


def validar_tamano(tipo: str, bytes_archivo: int, settings: Any) -> None:
    limite = limite_bytes(tipo, settings)
    if bytes_archivo <= 0:
        raise MediaInvalido("el archivo esta vacio")
    if bytes_archivo > limite:
        raise MediaInvalido(
            f"el archivo supera el limite de {limite // (1024 * 1024)} MB para {tipo.lower()}"
        )


def slug(texto: str, max_len: int = 48) -> str:
    normal = unicodedata.normalize("NFKD", str(texto or ""))
    normal = "".join(c for c in normal if not unicodedata.combining(c)).lower()
    normal = re.sub(r"[^a-z0-9]+", "_", normal).strip("_")
    return normal[:max_len].strip("_") or "cliente"


def carpeta_cliente(
    nombre: str, cedula: str | None, ruc: str | None, cliente_id: str
) -> str:
    """Nombre legible + identificador para evitar homonimos.

    Orden: cedula > RUC > id del cliente. Nunca se inventa un documento.
    """
    identificador = re.sub(r"[^0-9A-Za-z]", "", cedula or ruc or "")
    if not identificador:
        identificador = cliente_id.replace("-", "")[:12]
    return f"{slug(nombre)}_{identificador}"


def ruta_media(
    carpeta: str, tipo: str, ext: str, *, ahora: datetime | None = None
) -> str:
    if ahora is None:
        try:
            from zoneinfo import ZoneInfo

            ahora = datetime.now(ZoneInfo("America/Guayaquil"))
        except Exception:
            ahora = datetime.now()
    fecha = ahora.strftime("%Y-%m-%d")
    azar = secrets.token_hex(4)
    ext = re.sub(r"[^a-z0-9]", "", (ext or "bin").lower()) or "bin"
    return f"clientes/{carpeta}/{fecha}_{tipo.lower()}_{azar}.{ext}"


def sha256(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def comprimir_imagen(datos: bytes, settings: Any, max_lado: int = 1920) -> ArchivoProcesado:
    """Convierte a WebP, corrige orientacion EXIF y elimina metadatos."""
    Image.MAX_IMAGE_PIXELS = int(settings.media_max_pixeles)
    try:
        with Image.open(io.BytesIO(datos)) as original:
            original.load()
            imagen = ImageOps.exif_transpose(original)
            if imagen.mode not in ("RGB", "RGBA"):
                imagen = imagen.convert("RGBA" if "A" in imagen.getbands() else "RGB")
            if max(imagen.size) > max_lado:
                imagen.thumbnail((max_lado, max_lado), Image.LANCZOS)
            salida = io.BytesIO()
            imagen.save(salida, "WEBP", quality=82, method=6)
            return ArchivoProcesado(
                datos=salida.getvalue(),
                tipo="IMAGEN",
                mime="image/webp",
                extension="webp",
                ancho=imagen.width,
                alto=imagen.height,
            )
    except MediaInvalido:
        raise
    except Exception as exc:
        raise MediaInvalido(f"imagen invalida o danada: {type(exc).__name__}") from exc


def _ffmpeg() -> str:
    ruta = shutil.which("ffmpeg")
    if not ruta:
        raise MediaNoDisponible("ffmpeg no esta instalado en el contenedor")
    return ruta


async def _probe(ruta: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise MediaNoDisponible("ffprobe no esta instalado en el contenedor")
    proceso = await asyncio.create_subprocess_exec(
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration:stream=width,height,codec_type",
        "-of", "json",
        str(ruta),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        salida, error = await asyncio.wait_for(proceso.communicate(), timeout=20)
    except asyncio.TimeoutError as exc:
        proceso.kill()
        await proceso.wait()
        raise MediaInvalido("ffprobe tardo demasiado en leer el archivo") from exc
    if proceso.returncode != 0:
        raise MediaInvalido(
            "no se pudo leer el archivo: " + (error or b"").decode("utf-8", "ignore")[:200]
        )
    import json

    try:
        return json.loads(salida or b"{}")
    except ValueError as exc:
        raise MediaInvalido("metadatos de media ilegibles") from exc


async def procesar_video(
    ruta_entrada: Path, settings: Any, *, max_lado: int | None = None
) -> ArchivoProcesado:
    info = await _probe(ruta_entrada)
    duracion = float((info.get("format") or {}).get("duration") or 0)
    if duracion <= 0:
        raise MediaInvalido("el video no tiene duracion valida")
    if duracion > float(settings.media_video_max_seg):
        raise MediaInvalido(
            f"el video dura {duracion:.0f}s y el maximo es {settings.media_video_max_seg}s"
        )
    alto = int(max_lado or settings.media_video_alto)
    ancho = 1280
    salida = ruta_entrada.with_suffix(".mp4")
    filtro = (
        f"scale=w='min({ancho},iw)':h='min({alto},ih)':"
        "force_original_aspect_ratio=decrease:force_divisible_by=2"
    )
    proceso = await asyncio.create_subprocess_exec(
        _ffmpeg(),
        "-y",
        "-i", str(ruta_entrada),
        "-t", str(settings.media_video_max_seg),
        "-vf", filtro,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", str(settings.media_video_crf),
        "-c:a", "aac",
        "-b:a", "96k",
        "-movflags", "+faststart",
        str(salida),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, error = await asyncio.wait_for(proceso.communicate(), timeout=180)
    except asyncio.TimeoutError as exc:
        proceso.kill()
        await proceso.wait()
        raise MediaInvalido("la compresion del video supero 180 segundos") from exc
    if proceso.returncode != 0 or not salida.exists():
        raise MediaInvalido(
            "no se pudo comprimir el video: "
            + (error or b"").decode("utf-8", "ignore")[:300]
        )
    datos = salida.read_bytes()
    info_final = await _probe(salida)
    streams = [s for s in info_final.get("streams") or [] if s.get("codec_type") == "video"]
    return ArchivoProcesado(
        datos=datos,
        tipo="VIDEO",
        mime="video/mp4",
        extension="mp4",
        ancho=int(streams[0]["width"]) if streams else None,
        alto=int(streams[0]["height"]) if streams else None,
        duracion_seg=round(float((info_final.get("format") or {}).get("duration") or duracion), 2),
    )


def procesar_audio(datos: bytes, nombre: str, mime: str | None) -> ArchivoProcesado:
    ext = extension(nombre) or "ogg"
    if ext not in _EXT_AUDIO:
        raise MediaInvalido(f"formato de audio no soportado: .{ext}")
    return ArchivoProcesado(
        datos=datos,
        tipo="AUDIO",
        mime=mime or _MIME_POR_EXT.get(ext, "audio/ogg"),
        extension=ext,
    )


def procesar_documento(datos: bytes, nombre: str, mime: str | None) -> ArchivoProcesado:
    ext = extension(nombre)
    if ext not in _EXT_DOCUMENTO:
        raise MediaInvalido(f"documento no permitido: .{ext or 'sin extension'}")
    return ArchivoProcesado(
        datos=datos,
        tipo="DOCUMENTO",
        mime=mime or _MIME_POR_EXT.get(ext, "application/octet-stream"),
        extension=ext,
    )


async def procesar(
    *, nombre: str, mime: str | None, datos: bytes | None, ruta: Path | None, settings: Any
) -> ArchivoProcesado:
    if not nombre:
        raise MediaInvalido("falta el nombre del archivo")
    tipo = detectar_tipo(nombre, mime)
    if ruta is not None:
        tamano = ruta.stat().st_size
    else:
        tamano = len(datos or b"")
    validar_tamano(tipo, tamano, settings)
    if tipo == "IMAGEN":
        return comprimir_imagen(datos or b"", settings)
    if tipo == "VIDEO":
        if ruta is None:
            raise MediaInvalido("el video requiere archivo temporal")
        return await procesar_video(ruta, settings)
    if tipo == "AUDIO":
        return procesar_audio(datos or b"", nombre, mime)
    return procesar_documento(datos or b"", nombre, mime)


def firmar_url_bunny(
    cdn_host: str, storage_path: str, token_key: str | None, *, ttl_segundos: int = 3600
) -> str:
    """URL del CDN. Con ``token_key`` agrega token y expiracion (Bunny)."""
    host = (cdn_host or "").strip().rstrip("/")
    for prefijo in ("https://", "http://"):
        if host.lower().startswith(prefijo):
            host = host[len(prefijo):]
            break
    host = host.strip("/")
    ruta = "/" + (storage_path or "").lstrip("/")
    base = f"https://{host}{ruta}"
    clave = (token_key or "").strip()
    if not clave:
        return base
    expira = int(time.time()) + max(60, int(ttl_segundos))
    digest = hashlib.sha256(f"{clave}{ruta}{expira}".encode("utf-8")).digest()
    token = quote(base64.b64encode(digest).decode("ascii"), safe="")
    return f"{base}?token={token}&expires={expira}"


def ruta_sandbox(media_dir: str, storage_path: str) -> Path:
    """Resuelve la ruta local sin permitir escapes del directorio base."""
    base = Path(media_dir).resolve()
    destino = (base / storage_path).resolve()
    if base not in destino.parents and destino != base:
        raise MediaInvalido("ruta de almacenamiento invalida")
    return destino


def guardar_sandbox(media_dir: str, storage_path: str, datos: bytes) -> None:
    destino = ruta_sandbox(media_dir, storage_path)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    tmp.write_bytes(datos)
    os.replace(tmp, destino)


def borrar_sandbox(media_dir: str, storage_path: str) -> None:
    try:
        ruta_sandbox(media_dir, storage_path).unlink(missing_ok=True)
    except Exception:  # la limpieza nunca tumba la peticion
        log.warning("no se pudo borrar %s", storage_path)


def directorio_temporal() -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(prefix="horminor-media-")
