"""Proveedores de transcripción del componente de voz.

Hoy solo existe el camino degradado: sin credenciales no se inventa texto. El
adaptador real (Deepgram o Whisper) se enchufa detrás del mismo protocolo sin
tocar la ingesta ni el router.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from ..db import setting


@dataclass(frozen=True)
class ResultadoSTT:
    """Lo que devuelve cualquier proveedor, con o sin éxito."""

    estado: str
    proveedor: str
    modelo: str
    texto_crudo: str | None = None
    segmentos: list[dict[str, Any]] = field(default_factory=list)
    palabras: list[dict[str, Any]] = field(default_factory=list)
    confianza: float | None = None
    idioma: str = "es-EC"
    duracion_ms: int | None = None
    costo_usd: Decimal = Decimal("0")
    error: str | None = None


class ProveedorSTT(Protocol):
    nombre: str
    modelo: str

    async def transcribir(
        self, datos: bytes, mime: str, *, idioma: str = "es-EC"
    ) -> ResultadoSTT: ...


class SinProveedor:
    """Degradación honesta: guarda el audio y avisa que no transcribió."""

    nombre = "NO_CONFIGURADO"
    modelo = "ninguno"

    def __init__(self, motivo: str = "STT_API_KEY no configurada") -> None:
        self.motivo = motivo

    async def transcribir(
        self, datos: bytes, mime: str, *, idioma: str = "es-EC"
    ) -> ResultadoSTT:
        return ResultadoSTT(
            estado="DEGRADADO_SIN_CREDENCIAL",
            proveedor=self.nombre,
            modelo=self.modelo,
            idioma=idioma,
            error=self.motivo,
        )


class AdaptadorPendiente:
    """Hay credencial pero el adaptador todavía no está conectado."""

    nombre = "PENDIENTE"
    modelo = "ninguno"

    async def transcribir(
        self, datos: bytes, mime: str, *, idioma: str = "es-EC"
    ) -> ResultadoSTT:
        return ResultadoSTT(
            estado="FALLIDO",
            proveedor=self.nombre,
            modelo=self.modelo,
            idioma=idioma,
            error=(
                "ADAPTADOR_STT_NO_IMPLEMENTADO: hay credencial pero el "
                "adaptador todavía no está conectado"
            ),
        )


async def construir_proveedor(pool: Any, settings: Any) -> ProveedorSTT:
    """Devuelve el proveedor configurado o el camino degradado.

    La configuración vive en ``integraciones.stt``; si no hay, se usa
    ``GROQ_API_KEY`` del entorno. Si hay clave pero el proveedor no está
    implementado, se responde FALLIDO con un motivo explícito.
    """
    cfg = await setting(pool, "integraciones.stt", {}) or {}
    if not isinstance(cfg, dict):
        cfg = {}
    proveedor = str(cfg.get("proveedor") or "").strip().lower() or None
    clave = str(cfg.get("api_key") or "").strip() or (
        os.getenv("GROQ_API_KEY") or ""
    ).strip()
    modelo = (
        str(cfg.get("modelo") or "").strip()
        or os.getenv("GROQ_MODEL")
        or "whisper-large-v3"
    )
    if not clave:
        return SinProveedor()
    if proveedor in (None, "groq"):
        from .proveedores.groq import GroqSTT

        return GroqSTT(api_key=clave, modelo=modelo)
    return AdaptadorPendiente()
