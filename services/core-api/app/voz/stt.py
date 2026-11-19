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

    def __init__(
        self,
        motivo: str = "GROQ_API_KEY no configurada (o integraciones.stt.api_key)",
    ) -> None:
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


def _claves_groq(cfg: dict[str, Any]) -> list[str]:
    """Claves de Groq en orden de prioridad, sin vacias ni repetidas.

    1. ``integraciones.stt.api_key`` (panel) y ``api_key2``.
    2. ``GROQ_API_KEY``, ``GROQ_API_KEY2``, ``GROQ_API_KEY3``... del entorno.
    3. ``GROQ_API_KEYS`` como lista separada por comas.
    """
    crudas: list[Any] = [cfg.get("api_key"), cfg.get("api_key2")]
    for nombre in (
        "GROQ_API_KEY",
        "GROQ_API_KEY2",
        "GROQ_API_KEY3",
        "GROQ_API_KEY_2",
        "GROQ_KEY",
    ):
        crudas.append(os.getenv(nombre))
    crudas.extend((os.getenv("GROQ_API_KEYS") or "").split(","))

    vistas: set[str] = set()
    claves: list[str] = []
    for valor in crudas:
        clave = str(valor or "").strip().strip('"').strip("'").strip()
        if clave and clave not in vistas:
            vistas.add(clave)
            claves.append(clave)
    return claves


async def construir_proveedor(pool: Any, settings: Any) -> ProveedorSTT:
    """Devuelve el proveedor configurado o el camino degradado.

    La configuración vive en ``integraciones.stt``; si no hay, se usan las
    claves del entorno (``GROQ_API_KEY`` y su respaldo ``GROQ_API_KEY2``). Si
    hay claves, se usan en cascada: si la primera falla por credencial, cuota o
    red, se prueba la siguiente.
    """
    cfg = await setting(pool, "integraciones.stt", {}) or {}
    if not isinstance(cfg, dict):
        cfg = {}
    proveedor = str(cfg.get("proveedor") or "").strip().lower() or None
    claves = _claves_groq(cfg)
    modelo = (
        str(cfg.get("modelo") or "").strip()
        or os.getenv("GROQ_MODEL")
        or "whisper-large-v3"
    )
    if not claves:
        return SinProveedor()
    if proveedor in (None, "groq"):
        from .proveedores.groq import GroqCascada

        return GroqCascada(claves, modelo=modelo)
    return AdaptadorPendiente()
