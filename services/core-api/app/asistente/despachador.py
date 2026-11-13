"""Despachador de recordatorios: el "cron" de Gato.

No es un cron del sistema operativo ni un servicio aparte: es una tarea de
fondo dentro de la misma API, igual que el worker de WhatsApp. Cada `tick`
reclama las filas vencidas con `FOR UPDATE SKIP LOCKED` (seguro si algún día
corren dos replicas) y las envía por el notificador del Módulo 1.

- En SANDBOX el notificador es `SandboxNotifier`: el envío queda en
  `sandbox_outbox` y se ve en el panel, sin tocar un teléfono real.
- En producción el notificador es `EvolutionNotifier` y sale por WhatsApp.

Si no hay notificador configurado, la fila vuelve a `PENDIENTE` sin gastar
intentos: no se finge un envío.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

import httpx

from ..m1_whatsapp.models import formato_whatsapp
from ..services.media import ruta_sandbox

log = logging.getLogger(__name__)

INTERVALO_POR_DEFECTO = 20.0


class DespachadorRecordatorios:
    def __init__(
        self,
        *,
        pool: Any,
        proveedor_notifier: Callable[[], Any | None],
        intervalo_segundos: float = INTERVALO_POR_DEFECTO,
        media_dir: str = "",
    ) -> None:
        self.pool = pool
        self._proveedor_notifier = proveedor_notifier
        self.intervalo = max(float(intervalo_segundos), 1.0)
        self.media_dir = media_dir
        self._tarea: asyncio.Task[None] | None = None
        self._recuperado = False

    # -- ciclo ------------------------------------------------------------
    async def _recuperar(self) -> None:
        """Devuelve a PENDIENTE lo que quedó ENVIANDO por una caída."""
        await self.pool.execute(
            """
            UPDATE gato_recordatorios
               SET estado = 'PENDIENTE', updated_at = now()
             WHERE estado = 'ENVIANDO'
               AND updated_at < now() - interval '5 minutes'
            """
        )
        self._recuperado = True

    async def _reclamar(self, limite: int = 10) -> list[dict[str, Any]]:
        filas = await self.pool.fetch(
            """
            WITH lote AS (
                SELECT id
                  FROM gato_recordatorios
                 WHERE estado = 'PENDIENTE'
                   AND programado_at <= now()
                 ORDER BY programado_at
                 LIMIT $1
                 FOR UPDATE SKIP LOCKED
            )
            UPDATE gato_recordatorios r
               SET estado = 'ENVIANDO',
                   intentos = r.intentos + 1,
                   updated_at = now()
              FROM lote
             WHERE r.id = lote.id
            RETURNING r.id, r.telefono, r.mensaje, r.intentos,
                      r.destinatario_nombre, r.media_id
            """,
            limite,
        )
        return [dict(f) for f in filas]

    async def _cargar_media(
        self, media_id: Any
    ) -> tuple[str, str, bytes] | None:
        """(nombre, mimetype, bytes) del adjunto, desde sandbox o CDN."""
        fila = await self.pool.fetchrow(
            """
            SELECT backend, storage_path, nombre_original, mime_final, cdn_url
              FROM media_assets
             WHERE id = $1
            """,
            media_id,
        )
        if fila is None:
            return None
        nombre = str(fila["nombre_original"] or "documento")
        mime = str(fila["mime_final"] or "application/octet-stream")

        if str(fila["backend"]).upper() == "SANDBOX":
            if not self.media_dir:
                return None
            ruta = ruta_sandbox(self.media_dir, str(fila["storage_path"]))
            if not ruta.exists():
                return None
            return nombre, mime, ruta.read_bytes()

        url = (fila["cdn_url"] or "").strip()
        if not url:
            return None
        try:
            async with httpx.AsyncClient(timeout=30.0) as cliente:
                respuesta = await cliente.get(url)
            if respuesta.status_code != 200:
                return None
            return nombre, mime, respuesta.content
        except httpx.HTTPError:
            return None

    async def _enviado(self, recordatorio_id: Any, hora: Any) -> None:
        await self.pool.execute(
            """
            UPDATE gato_recordatorios
               SET estado = 'ENVIADO', enviado_at = $2, ultimo_error = NULL,
                   updated_at = now()
             WHERE id = $1
            """,
            recordatorio_id,
            hora,
        )

    async def _fallido(self, fila: dict[str, Any], error: str) -> None:
        from .recordatorios import MAX_INTENTOS

        intentos = int(fila.get("intentos") or 0)
        if intentos >= MAX_INTENTOS:
            await self.pool.execute(
                """
                UPDATE gato_recordatorios
                   SET estado = 'FALLIDO', ultimo_error = $2, updated_at = now()
                 WHERE id = $1
                """,
                fila["id"],
                error[:500],
            )
            log.warning("recordatorio %s falló definitivamente: %s", fila["id"], error)
            return
        await self.pool.execute(
            """
            UPDATE gato_recordatorios
               SET estado = 'PENDIENTE',
                   programado_at = now() + ($3::int * interval '1 minute'),
                   ultimo_error = $2,
                   updated_at = now()
             WHERE id = $1
            """,
            fila["id"],
            error[:500],
            intentos,
        )

    async def _liberar(self, recordatorio_id: Any) -> None:
        """Sin canal: devuelve la fila sin consumir intento."""
        await self.pool.execute(
            """
            UPDATE gato_recordatorios
               SET estado = 'PENDIENTE',
                   intentos = GREATEST(intentos - 1, 0),
                   updated_at = now()
             WHERE id = $1
            """,
            recordatorio_id,
        )

    async def tick(self) -> list[dict[str, Any]]:
        """Envía lo vencido y devuelve lo que procesó. No duerme."""
        if not self._recuperado:
            await self._recuperar()

        filas = await self._reclamar()
        if not filas:
            return []

        notifier = self._proveedor_notifier()
        if notifier is None:
            for fila in filas:
                await self._liberar(fila["id"])
            log.warning(
                "recordatorios vencidos sin canal de envío: %s quedan pendientes",
                len(filas),
            )
            return []

        from datetime import datetime, timezone

        procesados: list[dict[str, Any]] = []
        for fila in filas:
            destino = formato_whatsapp(str(fila["telefono"]))
            # Un cancelar que llegue entre el reclamo y el envio debe ganar.
            estado = await self.pool.fetchval(
                "SELECT estado FROM gato_recordatorios WHERE id = $1", fila["id"]
            )
            if estado != "ENVIANDO":
                continue

            adjunto = None
            if fila.get("media_id"):
                adjunto = await self._cargar_media(fila["media_id"])
                if adjunto is None:
                    await self._fallido(fila, "no se pudo leer el adjunto")
                    procesados.append({**fila, "resultado": "FALLIDO"})
                    continue

            try:
                if adjunto is not None:
                    nombre, mime, datos = adjunto
                    ok = await notifier.enviar_documento(
                        destino, nombre, mime, datos, str(fila["mensaje"])
                    )
                else:
                    ok = await notifier.enviar_texto(destino, str(fila["mensaje"]))
            except Exception as exc:  # el loop nunca debe morir por un envío
                log.exception("error enviando recordatorio %s", fila["id"])
                await self._fallido(fila, f"{type(exc).__name__}: {exc}")
                continue

            if ok:
                await self._enviado(fila["id"], datetime.now(timezone.utc))
                procesados.append({**fila, "resultado": "ENVIADO"})
            else:
                await self._fallido(fila, "el notificador devolvió False")
                procesados.append({**fila, "resultado": "FALLIDO"})
        return procesados

    # -- tarea de fondo ---------------------------------------------------
    async def run(self, stop: asyncio.Event | None = None) -> None:
        while stop is None or not stop.is_set():
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover - red de seguridad del loop
                log.exception("falló el tick de recordatorios")
            try:
                if stop is None:
                    await asyncio.sleep(self.intervalo)
                else:
                    await asyncio.wait_for(stop.wait(), timeout=self.intervalo)
            except asyncio.TimeoutError:
                continue

    def iniciar(self) -> None:
        if self._tarea is None or self._tarea.done():
            self._tarea = asyncio.create_task(self.run())
            log.info("despachador de recordatorios activo (cada %.0fs)", self.intervalo)

    async def detener(self) -> None:
        if self._tarea is not None:
            self._tarea.cancel()
            try:
                await self._tarea
            except (asyncio.CancelledError, Exception):
                pass
            self._tarea = None


__all__ = ["DespachadorRecordatorios", "INTERVALO_POR_DEFECTO"]
