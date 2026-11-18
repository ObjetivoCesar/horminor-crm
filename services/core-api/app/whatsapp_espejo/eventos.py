"""Espejo de WhatsApp - aviso en vivo de mensajes nuevos (SSE).

Un solo proceso publica y varios paneles escuchan. No se guarda nada: si el
navegador se desconecta, al volver a entrar se reengancha y el estado se
recupera con la lectura normal del chat.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

log = logging.getLogger(__name__)

# Centinela para despertar a los generadores y que revisen si deben cerrar.
_LATIDO = object()


class BusEventos:
    """Fan-out en memoria: cada suscriptor tiene su propia cola."""

    def __init__(self, maxsize: int = 100) -> None:
        self._suscriptores: set[asyncio.Queue[Any]] = set()
        self._maxsize = maxsize

    def suscribir(self) -> asyncio.Queue[Any]:
        cola: asyncio.Queue[Any] = asyncio.Queue(maxsize=self._maxsize)
        self._suscriptores.add(cola)
        return cola

    def desuscribir(self, cola: asyncio.Queue[Any]) -> None:
        self._suscriptores.discard(cola)

    @property
    def suscriptores(self) -> int:
        return len(self._suscriptores)

    def publicar(self, evento: dict[str, Any]) -> None:
        """Nunca bloquea: si una cola esta llena se descarta para ese panel."""
        for cola in list(self._suscriptores):
            try:
                cola.put_nowait(evento)
            except asyncio.QueueFull:
                log.debug("eventos: cola llena, se descarta un aviso")

    async def transmitir(self, cola: asyncio.Queue[Any]) -> AsyncIterator[str]:
        """Generador SSE con latido para mantener viva la conexion."""
        try:
            yield _sse({"tipo": "listo"})
            while True:
                try:
                    evento = await asyncio.wait_for(cola.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield ": latido\n\n"
                    continue
                yield _sse(evento)
        finally:
            self.desuscribir(cola)


def _sse(datos: dict[str, Any]) -> str:
    return f"data: {json.dumps(datos, ensure_ascii=False, default=str)}\n\n"
