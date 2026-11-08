"""Modulo 1 - Conector de Bunny.net Storage.

Gate #3 manda la foto/video del chofer a Bunny.net y deja la URL CDN en
``tracking_payload.evidencias_bunny_cdn``. Nunca se guarda el archivo en el
VPS (el PDR lo prohibe: "ningun archivo ocupa disco en el VPS").

El cliente es inyectable: en tests se usa :class:`MemoryBunnyStorageClient`,
asi que el pipeline se prueba completo sin red ni credenciales.
"""

from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

log = logging.getLogger(__name__)


class BunnyError(RuntimeError):
    """Fallo real de Bunny.net (red, credenciales, HTTP != 201)."""


class BunnyNoConfigurado(BunnyError):
    """Faltan Storage Zone, API key o CDN host."""


class BunnyStorageClient(Protocol):
    nombre: str

    async def subir(
        self,
        *,
        nombre_archivo: str,
        contenido: bytes | None = None,
        url_origen: str | None = None,
        mimetype: str | None = None,
    ) -> str: ...


def _host_sin_esquema(valor: str) -> str:
    """Acepta ``cdn.ejemplo.com`` o ``https://cdn.ejemplo.com`` y devuelve el host."""
    limpio = (valor or "").strip().strip("/")
    for prefijo in ("https://", "http://"):
        if limpio.lower().startswith(prefijo):
            limpio = limpio[len(prefijo):]
            break
    return limpio.strip("/")


def nombre_evidencia(
    *, orden_numero: int | None, viaje_numero: int | None, mensaje_id: str, extension: str
) -> str:
    """Ruta estable dentro del Storage Zone.

    Convencion del PDR: ``ordenes/<orden>/viaje_<n>_<id>.<ext>``.
    """
    orden = f"{int(orden_numero):03d}" if orden_numero else "sin_orden"
    viaje = f"{int(viaje_numero):02d}" if viaje_numero else "00"
    limpio = re.sub(r"[^A-Za-z0-9_-]", "", mensaje_id or "")[:60] or "mensaje"
    ext = re.sub(r"[^A-Za-z0-9]", "", extension or "bin") or "bin"
    return f"ordenes/{orden}/viaje_{viaje}_{limpio}.{ext}"


@dataclass
class MemoryBunnyStorageClient:
    """Doble de prueba: registra lo que se habria subido y devuelve una URL."""

    cdn_host: str = "cdn.prueba.local"
    nombre: str = "memoria"
    subidas: list[dict[str, Any]] = field(default_factory=list)

    async def subir(
        self,
        *,
        nombre_archivo: str,
        contenido: bytes | None = None,
        url_origen: str | None = None,
        mimetype: str | None = None,
    ) -> str:
        self.subidas.append(
            {
                "nombre_archivo": nombre_archivo,
                "bytes": len(contenido or b""),
                "url_origen": url_origen,
                "mimetype": mimetype,
            }
        )
        return f"https://{_host_sin_esquema(self.cdn_host)}/{nombre_archivo.lstrip('/')}"


class NullBunnyStorageClient:
    """Sin credenciales: falla explicito para que quede la incidencia."""

    nombre = "no_configurado"

    async def subir(
        self,
        *,
        nombre_archivo: str,
        contenido: bytes | None = None,
        url_origen: str | None = None,
        mimetype: str | None = None,
    ) -> str:
        raise BunnyNoConfigurado(
            "Bunny.net sin configurar (BUNNY_STORAGE_ZONE / BUNNY_STORAGE_API_KEY / "
            "BUNNY_CDN_HOST)"
        )


class BunnyHttpStorageClient:
    """Sube por la API de Storage de Bunny.net y devuelve la URL del CDN."""

    nombre = "bunny_http"

    def __init__(
        self,
        *,
        storage_zone: str,
        api_key: str,
        cdn_host: str,
        endpoint: str = "https://storage.bunnycdn.com",
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._zone = storage_zone.strip()
        self._api_key = api_key.strip()
        self._cdn = _host_sin_esquema(cdn_host)
        self._endpoint = endpoint.rstrip("/")
        self._http = http_client
        self._timeout = timeout

    async def subir(
        self,
        *,
        nombre_archivo: str,
        contenido: bytes | None = None,
        url_origen: str | None = None,
        mimetype: str | None = None,
    ) -> str:
        datos = contenido
        if datos is None and url_origen:
            datos = await self._descargar(url_origen)
        if not datos:
            raise BunnyError(f"sin contenido para subir: {nombre_archivo}")

        url = f"{self._endpoint}/{self._zone}/{nombre_archivo.lstrip('/')}"
        cabeceras = {
            "AccessKey": self._api_key,
            "Content-Type": mimetype or "application/octet-stream",
        }
        if self._http is not None:
            respuesta = await self._http.put(
                url, content=datos, headers=cabeceras, timeout=self._timeout
            )
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as cliente:
                respuesta = await cliente.put(url, content=datos, headers=cabeceras)

        if respuesta.status_code not in (200, 201):
            raise BunnyError(
                f"Bunny.net respondio HTTP {respuesta.status_code} al subir {nombre_archivo}"
            )
        return f"https://{self._cdn.strip('/')}/{nombre_archivo.lstrip('/')}"

    async def _descargar(self, url: str) -> bytes:
        if self._http is not None:
            respuesta = await self._http.get(url, timeout=self._timeout)
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as cliente:
                respuesta = await cliente.get(url)
        respuesta.raise_for_status()
        return respuesta.content


def decodificar_base64(crudo: str | None) -> bytes | None:
    """Acepta base64 plano o data URI (``data:image/jpeg;base64,...``)."""
    if not crudo:
        return None
    limpio = crudo.split(",", 1)[1] if crudo.startswith("data:") and "," in crudo else crudo
    try:
        return base64.b64decode(limpio, validate=False)
    except (ValueError, TypeError):
        log.warning("adjunto base64 invalido; se ignora")
        return None


def construir_bunny(settings: Any) -> BunnyStorageClient:
    zona = (getattr(settings, "bunny_storage_zone", None) or "").strip()
    clave = (getattr(settings, "bunny_storage_api_key", None) or "").strip()
    cdn = (getattr(settings, "bunny_cdn_host", None) or "").strip()
    if not (zona and clave and cdn):
        return NullBunnyStorageClient()
    return BunnyHttpStorageClient(
        storage_zone=zona,
        api_key=clave,
        cdn_host=cdn,
        endpoint=getattr(settings, "bunny_storage_endpoint", "https://storage.bunnycdn.com"),
    )
