"""Modulo 1 - Worker que vacia la ventana de debounce y ejecuta las compuertas.

Corre como tarea de fondo dentro de la misma API (no hay Celery en el PDR).
Cada ``tick`` pide al buffer los lotes listos y los pasa por el pipeline. Un
error en un lote se registra y el loop continua: el bot no se cae por un
mensaje raro.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .debounce import DebounceAccumulator
from .models import MessageBatch
from .pipeline import ResultadoLote, WhatsAppPipeline
from .repositorio import RepositorioWhatsApp

log = logging.getLogger(__name__)


class DebounceWorker:
    def __init__(
        self,
        *,
        accumulator: DebounceAccumulator,
        pipeline: WhatsAppPipeline,
        repo: RepositorioWhatsApp,
        intervalo_segundos: float = 1.0,
    ) -> None:
        self.accumulator = accumulator
        self.pipeline = pipeline
        self.repo = repo
        self.intervalo = max(float(intervalo_segundos), 0.01)
        self._tarea: asyncio.Task[None] | None = None

    async def tick(self) -> list[ResultadoLote]:
        """Procesa los lotes listos ahora mismo. No duerme."""
        resultados: list[ResultadoLote] = []
        lotes = await self.accumulator.listos()
        for lote in lotes:
            try:
                resultados.append(await self.pipeline.procesar(lote))
            except Exception as exc:  # el loop del bot nunca debe morir
                log.exception("error procesando lote de %s", lote.telefono)
                await self.repo.registrar_log(
                    nivel="ERROR",
                    mensaje=f"Error procesando lote de WhatsApp: {exc}",
                    contexto={"telefono": lote.telefono, "error": type(exc).__name__},
                )
        return resultados

    async def run(self, stop: asyncio.Event | None = None) -> None:
        """Loop de fondo hasta que se pida parar."""
        while stop is None or not stop.is_set():
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover - red de seguridad del loop
                log.exception("fallo el tick del debounce")
            try:
                if stop is None:
                    await asyncio.sleep(self.intervalo)
                else:
                    await asyncio.wait_for(stop.wait(), timeout=self.intervalo)
            except asyncio.TimeoutError:
                continue

    def iniciar(self) -> asyncio.Task[None]:
        if self._tarea is None or self._tarea.done():
            self._tarea = asyncio.create_task(self.run(), name="m1-debounce-worker")
        return self._tarea

    async def detener(self) -> None:
        if self._tarea is None:
            return
        self._tarea.cancel()
        try:
            await self._tarea
        except (asyncio.CancelledError, Exception):
            pass
        self._tarea = None


def resumen_lote(lote: MessageBatch) -> dict[str, Any]:
    """Ayuda de diagnostico para /flush y scripts."""
    return {
        "telefono": lote.telefono,
        "mensajes": len(lote.mensajes),
        "texto": lote.texto,
    }
