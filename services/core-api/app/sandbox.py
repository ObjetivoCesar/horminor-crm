"""Modo SANDBOX - adaptadores que permiten demostrar el flujo completo sin
credenciales externas.

Directriz de Arquitectura (2026-11-08): ninguna credencial pendiente bloquea el
cierre del Hito 3. En SANDBOX:

- **WhatsApp:** en lugar de llamar a Evolution API, el mensaje se encola en
  ``sandbox_outbox`` y la UI del Superadmin lo muestra. No se finge un envio
  real: queda registrado como ``ENCOLADO`` con ``modo = SANDBOX``.
- **Bunny.net:** en lugar de subir a un Storage Zone real, se devuelve una URL
  deterministica bajo ``/sandbox/`` para que la Carpeta del Cliente muestre la
  galeria.
- **Juez:** sin ``GEMINI_API_KEY`` se usa el Juez deterministico y el Centinela
  lo publica como ``DETERMINISTIC_FALLBACK``.

Al cargar credenciales reales y apagar el switch ``sandbox``, los mismos
contratos pasan a los adaptadores de produccion sin tocar el pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from .m1_whatsapp.bunny import BunnyStorageClient
from .m1_whatsapp.notifications import Notifier
from .m1_whatsapp.repositorio import RepositorioWhatsApp

CDN_SANDBOX_POR_DEFECTO = "https://horminor.b-cdn.net"


@dataclass
class SandboxNotifier:
    """Encola los mensajes salientes en ``sandbox_outbox``."""

    repo: RepositorioWhatsApp
    nombre: str = "sandbox"

    async def enviar_texto(self, telefono: str, texto: str) -> bool:
        await self.repo.registrar_outbox(
            canal="WHATSAPP",
            destino=telefono,
            tipo="TEXTO",
            contenido=texto,
            metadatos={"modo": "SANDBOX", "proveedor": "evolution"},
        )
        return True

    async def enviar_documento(
        self,
        telefono: str,
        nombre: str,
        mimetype: str,
        contenido: bytes,
        texto: str | None = None,
    ) -> bool:
        await self.repo.registrar_outbox(
            canal="WHATSAPP",
            destino=telefono,
            tipo="DOCUMENTO",
            contenido=f"{nombre} · {texto or ''}".strip(" ·"),
            metadatos={
                "modo": "SANDBOX",
                "proveedor": "evolution",
                "mimetype": mimetype,
                "bytes": len(contenido),
                "archivo": nombre,
            },
        )
        return True


@dataclass
class SandboxBunnyStorageClient:
    """Devuelve URLs deterministas sin subir archivos a Bunny.net."""

    cdn_host: str = CDN_SANDBOX_POR_DEFECTO
    nombre: str = "sandbox"
    subidas: list[dict[str, Any]] = field(default_factory=list)

    def _base(self) -> str:
        host = (self.cdn_host or CDN_SANDBOX_POR_DEFECTO).strip().rstrip("/")
        if not host.lower().startswith(("http://", "https://")):
            host = f"https://{host}"
        return host

    async def subir(
        self,
        *,
        nombre_archivo: str,
        contenido: bytes | None = None,
        url_origen: str | None = None,
        mimetype: str | None = None,
    ) -> str:
        limpio = re.sub(r"[^A-Za-z0-9._/-]", "_", nombre_archivo or "evidencia")
        limpio = limpio.lstrip("/")
        url = f"{self._base()}/sandbox/{quote(limpio, safe='/._-')}"
        self.subidas.append(
            {
                "nombre_archivo": nombre_archivo,
                "bytes": len(contenido or b""),
                "url_origen": url_origen,
                "mimetype": mimetype,
                "url": url,
            }
        )
        return url


def construir_notifier_sandbox(
    repo: RepositorioWhatsApp, *, cdn_host: str | None = None
) -> tuple[Notifier, BunnyStorageClient]:
    """Par listo para inyectar en el pipeline cuando no hay credenciales."""
    return (
        SandboxNotifier(repo=repo),
        SandboxBunnyStorageClient(cdn_host=cdn_host or CDN_SANDBOX_POR_DEFECTO),
    )
