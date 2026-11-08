"""Modulo 1 - Ventana de agrupacion (debounce) de mensajes fragmentados.

El PDR fija 14 segundos: un remitente escribe "ya", "llego", "el mixer",
"todo bien" y el bot no debe procesar cuatro eventos sueltos. Se acumulan por
telefono y se procesan cuando pasa la ventana de silencio.

Hay dos implementaciones del buffer:

- :class:`RedisBufferStore` para produccion (Redis es el que manda, como pide
  el PDR y como ya esta en el compose).
- :class:`MemoryBufferStore` para tests y como degradacion local si Redis no
  responde. No cambia la logica, solo donde se guarda la cola.

La ventana es inyectable: en tests se usa ``0.1`` segundos y el
comportamiento es identico al de 14.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from .models import IncomingMessage, MessageBatch

log = logging.getLogger(__name__)

PREFIJO_REDIS = "orminorth:wa"
CLAVE_PENDIENTES = f"{PREFIJO_REDIS}:pendientes"
CLAVE_INICIO = f"{PREFIJO_REDIS}:inicio"
CLAVE_BUFFER = f"{PREFIJO_REDIS}:buffer:"
TTL_BUFFER_SEGUNDOS = 3600


def _ahora(ahora: datetime | None = None) -> datetime:
    return ahora or datetime.now(timezone.utc)


def _ts(momento: datetime) -> float:
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.timestamp()


class BufferStore(Protocol):
    """Contrato minimo de un buffer de debounce."""

    nombre: str

    async def push(
        self, telefono: str, mensaje: IncomingMessage, ahora: datetime
    ) -> None: ...

    async def collect_ready(
        self,
        *,
        ahora: datetime,
        ventana_segundos: float,
        maximo_segundos: float | None = None,
    ) -> list[MessageBatch]: ...

    async def cerrar(self) -> None: ...


@dataclass
class MemoryBufferStore:
    """Buffer en memoria del proceso. Para tests y degradacion local."""

    nombre: str = "memoria"
    _buffers: dict[str, list[tuple[float, IncomingMessage]]] = field(
        default_factory=dict
    )
    _inicio: dict[str, float] = field(default_factory=dict)

    async def push(
        self, telefono: str, mensaje: IncomingMessage, ahora: datetime
    ) -> None:
        clave = mensaje.telefono_normalizado or telefono
        momento = _ts(ahora)
        self._buffers.setdefault(clave, []).append((momento, mensaje))
        self._inicio.setdefault(clave, momento)

    async def collect_ready(
        self,
        *,
        ahora: datetime,
        ventana_segundos: float,
        maximo_segundos: float | None = None,
    ) -> list[MessageBatch]:
        momento = _ts(ahora)
        corte = momento - max(float(ventana_segundos), 0.0)
        corte_maximo = (
            momento - max(float(maximo_segundos), 0.0)
            if maximo_segundos is not None
            else None
        )

        listos: list[MessageBatch] = []
        for telefono in list(self._buffers):
            entradas = self._buffers[telefono]
            if not entradas:
                self._buffers.pop(telefono, None)
                self._inicio.pop(telefono, None)
                continue
            ultimo = entradas[-1][0]
            inicio = self._inicio.get(telefono, entradas[0][0])
            por_silencio = ultimo <= corte
            por_tope = corte_maximo is not None and inicio <= corte_maximo
            if not (por_silencio or por_tope):
                continue
            entradas.sort(key=lambda par: par[0])
            listos.append(
                MessageBatch(
                    telefono=telefono,
                    mensajes=tuple(mensaje for _, mensaje in entradas),
                )
            )
            self._buffers.pop(telefono, None)
            self._inicio.pop(telefono, None)
        return listos

    async def cerrar(self) -> None:  # nada que cerrar
        return None


_SCRIPT_COLLECT = """
local cutoff = tonumber(ARGV[1])
local tope = tonumber(ARGV[2])
local limite = tonumber(ARGV[3])

local telefonos = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', cutoff, 'LIMIT', 0, limite)
local en_lista = {}
for _, p in ipairs(telefonos) do en_lista[p] = true end

local forzados = redis.call('HGETALL', KEYS[2])
for i = 1, #forzados, 2 do
    local p = forzados[i]
    local inicio = tonumber(forzados[i + 1])
    if inicio and inicio <= tope and not en_lista[p] then
        table.insert(telefonos, p)
        en_lista[p] = true
    end
end

local salida = {}
for _, p in ipairs(telefonos) do
    local clave = KEYS[3] .. p
    local items = redis.call('LRANGE', clave, 0, -1)
    if #items > 0 then
        table.insert(salida, items)
    end
    redis.call('DEL', clave)
    redis.call('ZREM', KEYS[1], p)
    redis.call('HDEL', KEYS[2], p)
end
return salida
"""


class RedisBufferStore:
    """Buffer compartido en Redis: sobrevive reinicios y escala horizontal."""

    nombre = "redis"

    def __init__(self, cliente: Any) -> None:
        self._redis = cliente

    async def push(
        self, telefono: str, mensaje: IncomingMessage, ahora: datetime
    ) -> None:
        clave = mensaje.telefono_normalizado or telefono
        momento = _ts(ahora)
        pipe = self._redis.pipeline()
        pipe.rpush(f"{CLAVE_BUFFER}{clave}", mensaje.a_json())
        pipe.zadd(CLAVE_PENDIENTES, {clave: momento})
        pipe.hsetnx(CLAVE_INICIO, clave, momento)
        pipe.expire(f"{CLAVE_BUFFER}{clave}", TTL_BUFFER_SEGUNDOS)
        await pipe.execute()

    async def collect_ready(
        self,
        *,
        ahora: datetime,
        ventana_segundos: float,
        maximo_segundos: float | None = None,
    ) -> list[MessageBatch]:
        momento = _ts(ahora)
        corte = momento - max(float(ventana_segundos), 0.0)
        tope = momento - max(float(maximo_segundos or ventana_segundos), 0.0)
        crudo = await self._redis.eval(
            _SCRIPT_COLLECT,
            3,
            CLAVE_PENDIENTES,
            CLAVE_INICIO,
            CLAVE_BUFFER,
            corte,
            tope,
            200,
        )
        listos: list[MessageBatch] = []
        for grupo in crudo or []:
            mensajes = tuple(
                IncomingMessage.desde_json(item) for item in (grupo or [])
            )
            if not mensajes:
                continue
            listos.append(
                MessageBatch(
                    telefono=mensajes[0].telefono_normalizado,
                    mensajes=mensajes,
                )
            )
        return listos

    async def cerrar(self) -> None:
        try:
            await self._redis.aclose()
        except Exception:  # nunca tumbar el apagado por Redis
            log.warning("no se pudo cerrar el cliente Redis del debounce")


class DebounceAccumulator:
    """Acumula mensajes por remitente y entrega lotes listos para procesar."""

    def __init__(
        self,
        store: BufferStore,
        ventana_segundos: float,
        *,
        maximo_segundos: float | None = None,
    ) -> None:
        self.store = store
        self.ventana_segundos = max(float(ventana_segundos), 0.0)
        self.maximo_segundos = maximo_segundos

    async def agregar(
        self, mensaje: IncomingMessage, ahora: datetime | None = None
    ) -> None:
        await self.store.push(
            mensaje.telefono_normalizado or mensaje.telefono,
            mensaje,
            _ahora(ahora),
        )

    async def listos(self, ahora: datetime | None = None) -> list[MessageBatch]:
        return await self.store.collect_ready(
            ahora=_ahora(ahora),
            ventana_segundos=self.ventana_segundos,
            maximo_segundos=self.maximo_segundos,
        )

    async def cerrar(self) -> None:
        await self.store.cerrar()
