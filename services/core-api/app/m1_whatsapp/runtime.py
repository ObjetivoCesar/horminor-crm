"""Modulo 1 - Ensamblaje del runtime (Redis, Juez, Bunny, worker).

Un solo lugar arma las piezas para que ``main.py`` no sepa de detalles y para
que los tests puedan construir el pipeline a mano sin pasar por aqui.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import asyncpg
from redis import asyncio as redis_asyncio

from ..settings import Settings
from .bunny import BunnyStorageClient, construir_bunny
from .debounce import (
    BufferStore,
    DebounceAccumulator,
    MemoryBufferStore,
    RedisBufferStore,
)
from .identity import IdentityResolver
from .judges import BooleanJudgeProvider, construir_juez
from .notifications import (
    EvolutionNotifier,
    Notifier,
    NullNotifier,
    SentinelAlerter,
)
from .pipeline import WhatsAppPipeline
from .repositorio import PostgresRepositorio, RepositorioWhatsApp
from .worker import DebounceWorker

log = logging.getLogger(__name__)

DEBOUNCE_POR_DEFECTO = 14.0
DEBOUNCE_MAXIMO_POR_DEFECTO = 60.0


@dataclass
class WhatsAppRuntime:
    accumulator: DebounceAccumulator
    pipeline: WhatsAppPipeline
    worker: DebounceWorker
    repo: RepositorioWhatsApp
    store: BufferStore
    juez: BooleanJudgeProvider
    bunny: BunnyStorageClient
    notifier: Notifier
    alerter: SentinelAlerter
    ventana_segundos: float
    redis_cliente: Any = None
    extra: dict[str, Any] = field(default_factory=dict)

    def estado(self) -> dict[str, Any]:
        """Estado de configuracion para /health (nunca expone claves)."""
        return {
            "store": self.store.nombre,
            "ventana_segundos": self.ventana_segundos,
            "juez": self.juez.nombre,
            "bunny": self.bunny.nombre,
            "notifier": self.notifier.nombre,
            "webhook_centinela": (
                "CONFIGURADO" if self.alerter.configurado() else "NO_CONFIGURADO"
            ),
        }

    async def cerrar(self) -> None:
        await self.worker.detener()
        await self.accumulator.cerrar()
        if self.redis_cliente is not None:
            try:
                await self.redis_cliente.aclose()
            except Exception:  # nunca tumbar el apagado
                log.warning("no se pudo cerrar el cliente Redis del Modulo 1")

    async def recargar_config(self) -> dict[str, Any]:
        """Aplica en caliente lo que el Superadmin acaba de guardar.

        No reinicia el worker ni toca Redis: solo cambia la ventana que el
        acumulador usa en el proximo ``tick`` y tira la cache de identidad para
        que el siguiente mensaje vea el directorio nuevo.
        """
        valor = await self.repo.parametro("operacion.debounce_segundos", None)
        if valor is not None:
            try:
                ventana = max(float(valor), 0.0)
            except (TypeError, ValueError):
                ventana = self.ventana_segundos
            self.accumulator.ventana_segundos = ventana
            self.ventana_segundos = ventana

        identidad = getattr(self.pipeline, "identidad", None)
        invalidar = getattr(identidad, "invalidar_cache", None)
        if callable(invalidar):
            invalidar()
        return self.estado()


async def _ventana(pool: asyncpg.Pool, settings: Settings) -> float:
    valor = settings.debounce_seconds
    if valor is None:
        repo = PostgresRepositorio(pool)
        try:
            valor = await repo.parametro(
                "operacion.debounce_segundos", DEBOUNCE_POR_DEFECTO
            )
        except Exception:
            valor = DEBOUNCE_POR_DEFECTO
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        numero = DEBOUNCE_POR_DEFECTO
    return max(numero, 0.0)


async def _tope_debounce(pool: asyncpg.Pool, ventana: float) -> float:
    repo = PostgresRepositorio(pool)
    try:
        valor = await repo.parametro(
            "whatsapp.tiempo_maximo_debounce_segundos",
            DEBOUNCE_MAXIMO_POR_DEFECTO,
        )
        tope = float(valor)
    except Exception:
        tope = DEBOUNCE_MAXIMO_POR_DEFECTO
    return max(tope, ventana)


async def construir_runtime(pool: asyncpg.Pool, settings: Settings) -> WhatsAppRuntime:
    """Arma el Modulo 1. Si Redis no responde, degrada a buffer en memoria."""
    repo = PostgresRepositorio(pool)
    ventana = await _ventana(pool, settings)
    tope = await _tope_debounce(pool, ventana)

    store: BufferStore
    redis_cliente: Any = None
    try:
        redis_cliente = redis_asyncio.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
        )
        await redis_cliente.ping()
        store = RedisBufferStore(redis_cliente)
        log.info("Modulo 1: debounce en Redis (ventana %.1f s)", ventana)
    except Exception as exc:
        if redis_cliente is not None:
            try:
                await redis_cliente.aclose()
            except Exception:
                pass
        redis_cliente = None
        store = MemoryBufferStore()
        log.warning(
            "Modulo 1: Redis no disponible (%s). Debounce en memoria del proceso.",
            type(exc).__name__,
        )

    identidad = IdentityResolver(pool=pool)
    juez = construir_juez(
        gemini_api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        timeout=settings.gemini_timeout,
    )
    bunny = construir_bunny(settings)

    notifier: Notifier
    evolution = EvolutionNotifier(
        base_url=settings.evolution_url,
        instancia=settings.evolution_instance,
        api_key=settings.evolution_api_key,
    )
    notifier = evolution if evolution.configurado() else NullNotifier()

    alerter = SentinelAlerter(
        webhook_url=settings.agency_crm_webhook_url,
        master_key=settings.clave_maestra_sentinel,
        repo=repo,
    )

    pipeline = WhatsAppPipeline(
        repo=repo,
        identidad=identidad,
        juez=juez,
        bunny=bunny,
        notifier=notifier,
        alerter=alerter,
    )
    accumulator = DebounceAccumulator(
        store, ventana_segundos=ventana, maximo_segundos=tope
    )
    worker = DebounceWorker(
        accumulator=accumulator,
        pipeline=pipeline,
        repo=repo,
        intervalo_segundos=settings.debounce_poll_seconds,
    )

    return WhatsAppRuntime(
        accumulator=accumulator,
        pipeline=pipeline,
        worker=worker,
        repo=repo,
        store=store,
        juez=juez,
        bunny=bunny,
        notifier=notifier,
        alerter=alerter,
        ventana_segundos=ventana,
        redis_cliente=redis_cliente,
    )
