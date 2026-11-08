"""Modulo 1 - Acceso a datos: lo unico del bot que toca PostgreSQL.

Principio de caja negra del PDR: el Modulo 1 **lee estado** y **actualiza
``mixer_dispatches.tracking_payload``**. No escribe columnas planas (las
sincroniza el trigger ``trg_dispatch_project``) ni toca ordenes, caja o
inventario. La unica excepcion explicita del PDR es el Gate #4, que crea el
prospecto en ``clients``.

``MemoriaRepositorio`` existe para tests y simulaciones: implementa el mismo
contrato sin base de datos.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol, Sequence

import asyncpg

from ..db import setting
from ..obs import log_event
from .models import ReferenciaViaje, normalizar_codigo_mixer, normalizar_telefono

log = logging.getLogger(__name__)


def _json_dict(valor: Any) -> dict[str, Any]:
    """asyncpg devuelve ``jsonb`` como texto si no hay codec registrado."""
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except ValueError:
            return {}
    return dict(valor) if isinstance(valor, dict) else {}


@dataclass(frozen=True)
class ViajeObjetivo:
    """Viaje de mixer sobre el que actua una compuerta."""

    dispatch_id: str
    order_id: str
    orden_numero: int
    viaje_numero: int
    total_viajes_orden: int
    mixer_codigo: str | None
    cliente_id: str
    cliente_nombre: str
    cliente_telefono: str | None
    payload: dict[str, Any]

    @property
    def estado_actual(self) -> str:
        return str(self.payload.get("estado_actual") or "PROGRAMADO")


class RepositorioWhatsApp(Protocol):
    async def buscar_viaje(
        self,
        *,
        referencia: ReferenciaViaje | None = None,
        cliente_id: str | None = None,
        estados: Sequence[str] | None = None,
    ) -> ViajeObjetivo | None: ...

    async def actualizar_payload(
        self,
        dispatch_id: str,
        mutar: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]: ...

    async def crear_lead(
        self, *, telefono: str, nombre: str | None, mensaje: str
    ) -> dict[str, Any]: ...

    async def registrar_log(
        self,
        *,
        nivel: str,
        mensaje: str,
        contexto: dict[str, Any] | None = None,
        order_id: str | None = None,
        dispatch_id: str | None = None,
    ) -> None: ...

    async def parametro(self, clave: str, por_defecto: Any = None) -> Any: ...

    async def recetas_publicas(self) -> list[dict[str, Any]]:
        """Recetas confirmadas y con precio: insumo del bot de atencion."""
        ...

    async def registrar_outbox(
        self,
        *,
        canal: str,
        destino: str,
        tipo: str,
        contenido: str,
        metadatos: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Encola una salida del modo SANDBOX (WhatsApp / Bunny / CRM)."""
        ...

    async def listar_outbox(self, limite: int = 50) -> list[dict[str, Any]]:
        """Ultimas salidas simuladas, para la UI del Superadmin."""
        ...


_SQL_BUSCAR = """
SELECT d.id::text                AS dispatch_id,
       d.order_id::text          AS order_id,
       o.numero                 AS orden_numero,
       d.viaje_numero           AS viaje_numero,
       d.total_viajes_orden     AS total_viajes_orden,
       d.mixer_codigo           AS mixer_codigo,
       d.estado_actual          AS estado_actual,
       c.id::text               AS cliente_id,
       c.nombre                 AS cliente_nombre,
       c.telefono_whatsapp      AS cliente_telefono,
       d.tracking_payload::text AS payload
  FROM mixer_dispatches d
  JOIN orders  o ON o.id = d.order_id
  JOIN clients c ON c.id = o.cliente_id
 WHERE o.estado <> 'ANULADA'
   AND ($1::bigint IS NULL OR o.numero = $1)
   AND ($2::int    IS NULL OR d.viaje_numero = $2)
   AND ($3::uuid   IS NULL OR o.cliente_id = $3::uuid)
   AND ($4::text[] IS NULL OR d.estado_actual = ANY($4::text[]))
 ORDER BY CASE WHEN d.estado_actual = 'EN_RUTA' THEN 0 ELSE 1 END,
          o.created_at DESC,
          d.viaje_numero ASC
 LIMIT 50
"""


class PostgresRepositorio:
    """Implementacion real sobre asyncpg."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def buscar_viaje(
        self,
        *,
        referencia: ReferenciaViaje | None = None,
        cliente_id: str | None = None,
        estados: Sequence[str] | None = None,
    ) -> ViajeObjetivo | None:
        ref = referencia or ReferenciaViaje()
        filas = await self._pool.fetch(
            _SQL_BUSCAR,
            ref.orden_numero,
            ref.viaje_numero,
            cliente_id,
            list(estados) if estados else None,
        )
        for fila in filas:
            asignado = normalizar_codigo_mixer(fila["mixer_codigo"])
            # El mixer del mensaje es una pista, no un filtro absoluto: si el
            # viaje aun no tiene mixer asignado (NULL), la referencia del
            # bodeguero/chofer sirve para identificarlo y se registra despues.
            if ref.mixer_codigo and asignado and asignado != ref.mixer_codigo:
                continue
            return ViajeObjetivo(
                dispatch_id=fila["dispatch_id"],
                order_id=fila["order_id"],
                orden_numero=int(fila["orden_numero"]),
                viaje_numero=int(fila["viaje_numero"]),
                total_viajes_orden=int(fila["total_viajes_orden"]),
                mixer_codigo=fila["mixer_codigo"],
                cliente_id=fila["cliente_id"],
                cliente_nombre=fila["cliente_nombre"],
                cliente_telefono=fila["cliente_telefono"],
                payload=json.loads(fila["payload"]),
            )
        return None

    async def actualizar_payload(
        self,
        dispatch_id: str,
        mutar: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                fila = await conn.fetchrow(
                    """
                    SELECT tracking_payload::text AS payload
                      FROM mixer_dispatches
                     WHERE id = $1::uuid
                       FOR UPDATE
                    """,
                    dispatch_id,
                )
                if fila is None:
                    raise LookupError(f"viaje inexistente: {dispatch_id}")
                payload = json.loads(fila["payload"])
                mutar(payload)
                await conn.execute(
                    """
                    UPDATE mixer_dispatches
                       SET tracking_payload = $2::jsonb
                     WHERE id = $1::uuid
                    """,
                    dispatch_id,
                    json.dumps(payload, ensure_ascii=False, default=str),
                )
        return payload

    async def crear_lead(
        self, *, telefono: str, nombre: str | None, mensaje: str
    ) -> dict[str, Any]:
        fila = await self._pool.fetchrow(
            """
            INSERT INTO clients (nombre, telefono_whatsapp, estado, notas)
            VALUES ($1, $2, 'PROSPECTO', $3)
            ON CONFLICT (telefono_whatsapp) DO UPDATE
               SET estado = CASE
                       WHEN clients.estado = 'ACTIVO' THEN clients.estado
                       ELSE 'PROSPECTO'
                   END,
                   notas = CASE
                       WHEN clients.estado = 'ACTIVO' THEN clients.notas
                       ELSE EXCLUDED.notas
                   END
            RETURNING id::text AS cliente_id, nombre, estado
            """,
            nombre or f"Lead WhatsApp {normalizar_telefono(telefono)}",
            telefono,
            (mensaje or "")[:2000],
        )
        return dict(fila) if fila else {}

    async def registrar_log(
        self,
        *,
        nivel: str,
        mensaje: str,
        contexto: dict[str, Any] | None = None,
        order_id: str | None = None,
        dispatch_id: str | None = None,
    ) -> None:
        await log_event(
            self._pool,
            nivel,
            "M1_WHATSAPP",
            mensaje,
            contexto,
            order_id=order_id,
            dispatch_id=dispatch_id,
        )

    async def parametro(self, clave: str, por_defecto: Any = None) -> Any:
        return await setting(self._pool, clave, por_defecto)

    async def recetas_publicas(self) -> list[dict[str, Any]]:
        """Recetas confirmadas con precio; el bot nunca inventa una faltante."""
        filas = await self._pool.fetch(
            """
            SELECT resistencia, precio_m3, iva_pct, uso_comercial,
                   cemento_sacos_m3, arena_m3_m3, ripio_m3_m3,
                   agua_litros_m3, retardante_litros_m3, saco_kg
              FROM concrete_recipes
             WHERE confirmado AND precio_m3 IS NOT NULL
             ORDER BY resistencia
            """
        )
        return [
            {
                "resistencia": fila["resistencia"],
                "precio_m3": (
                    None if fila["precio_m3"] is None else float(fila["precio_m3"])
                ),
                "iva_pct": None if fila["iva_pct"] is None else float(fila["iva_pct"]),
                "uso_comercial": fila["uso_comercial"],
                "cemento_sacos_m3": (
                    None
                    if fila["cemento_sacos_m3"] is None
                    else float(fila["cemento_sacos_m3"])
                ),
                "arena_m3_m3": (
                    None if fila["arena_m3_m3"] is None else float(fila["arena_m3_m3"])
                ),
                "ripio_m3_m3": (
                    None if fila["ripio_m3_m3"] is None else float(fila["ripio_m3_m3"])
                ),
                "agua_litros_m3": (
                    None
                    if fila["agua_litros_m3"] is None
                    else float(fila["agua_litros_m3"])
                ),
                "retardante_litros_m3": (
                    None
                    if fila["retardante_litros_m3"] is None
                    else float(fila["retardante_litros_m3"])
                ),
                "saco_kg": None if fila["saco_kg"] is None else float(fila["saco_kg"]),
            }
            for fila in filas
        ]

    async def registrar_outbox(
        self,
        *,
        canal: str,
        destino: str,
        tipo: str,
        contenido: str,
        metadatos: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fila = await self._pool.fetchrow(
            """
            INSERT INTO sandbox_outbox
                (canal, destino, tipo, contenido, metadatos)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            RETURNING id, canal, destino, tipo, contenido, estado, created_at
            """,
            canal,
            destino,
            tipo,
            contenido,
            json.dumps(metadatos or {}, ensure_ascii=False, default=str),
        )
        return {
            "id": int(fila["id"]),
            "canal": fila["canal"],
            "destino": fila["destino"],
            "tipo": fila["tipo"],
            "contenido": fila["contenido"],
            "metadatos": dict(metadatos or {}),
            "estado": fila["estado"],
            "created_at": fila["created_at"].isoformat(),
        }

    async def listar_outbox(self, limite: int = 50) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT id, canal, destino, tipo, contenido, metadatos, estado, created_at
              FROM sandbox_outbox
             ORDER BY created_at DESC, id DESC
             LIMIT $1
            """,
            max(1, min(int(limite), 500)),
        )
        return [
            {
                "id": int(fila["id"]),
                "canal": fila["canal"],
                "destino": fila["destino"],
                "tipo": fila["tipo"],
                "contenido": fila["contenido"],
                "metadatos": _json_dict(fila["metadatos"]),
                "estado": fila["estado"],
                "created_at": fila["created_at"].isoformat(),
            }
            for fila in filas
        ]


@dataclass
class MemoriaRepositorio:
    """Implementacion en memoria: tests y simulacion local.

    No es un atajo de produccion; reproduce el mismo contrato para poder
    probar las cuatro compuertas sin base de datos.
    """

    viajes: list[ViajeObjetivo] = field(default_factory=list)
    parametros: dict[str, Any] = field(default_factory=dict)
    leads: list[dict[str, Any]] = field(default_factory=list)
    logs: list[dict[str, Any]] = field(default_factory=list)
    actualizaciones: list[str] = field(default_factory=list)
    recetas: list[dict[str, Any]] = field(default_factory=list)
    outbox: list[dict[str, Any]] = field(default_factory=list)

    async def buscar_viaje(
        self,
        *,
        referencia: ReferenciaViaje | None = None,
        cliente_id: str | None = None,
        estados: Sequence[str] | None = None,
    ) -> ViajeObjetivo | None:
        ref = referencia or ReferenciaViaje()
        candidatos = [
            v
            for v in self.viajes
            if (ref.orden_numero is None or v.orden_numero == ref.orden_numero)
            and (ref.viaje_numero is None or v.viaje_numero == ref.viaje_numero)
            and (cliente_id is None or v.cliente_id == cliente_id)
            and (
                not estados
                or v.estado_actual in set(estados)
            )
            and (
                ref.mixer_codigo is None
                or not v.mixer_codigo
                or normalizar_codigo_mixer(v.mixer_codigo) == ref.mixer_codigo
            )
        ]
        if not candidatos:
            return None
        candidatos.sort(
            key=lambda v: (0 if v.estado_actual == "EN_RUTA" else 1, v.viaje_numero)
        )
        return candidatos[0]

    async def actualizar_payload(
        self,
        dispatch_id: str,
        mutar: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        for viaje in self.viajes:
            if viaje.dispatch_id == dispatch_id:
                mutar(viaje.payload)
                self.actualizaciones.append(dispatch_id)
                return viaje.payload
        raise LookupError(f"viaje inexistente: {dispatch_id}")

    async def crear_lead(
        self, *, telefono: str, nombre: str | None, mensaje: str
    ) -> dict[str, Any]:
        clave = normalizar_telefono(telefono)
        for lead in self.leads:
            if normalizar_telefono(lead["telefono"]) == clave:
                lead["mensaje"] = mensaje
                return lead
        lead = {
            "cliente_id": f"lead-{len(self.leads) + 1}",
            "nombre": nombre or f"Lead WhatsApp {clave}",
            "estado": "PROSPECTO",
            "telefono": telefono,
            "mensaje": mensaje,
        }
        self.leads.append(lead)
        return lead

    async def registrar_log(
        self,
        *,
        nivel: str,
        mensaje: str,
        contexto: dict[str, Any] | None = None,
        order_id: str | None = None,
        dispatch_id: str | None = None,
    ) -> None:
        self.logs.append(
            {
                "nivel": nivel,
                "origen": "M1_WHATSAPP",
                "mensaje": mensaje,
                "contexto": contexto or {},
                "order_id": order_id,
                "dispatch_id": dispatch_id,
            }
        )

    async def parametro(self, clave: str, por_defecto: Any = None) -> Any:
        return self.parametros.get(clave, por_defecto)

    async def recetas_publicas(self) -> list[dict[str, Any]]:
        return [
            dict(receta)
            for receta in self.recetas
            if receta.get("confirmado", True) and receta.get("precio_m3") is not None
        ]

    async def registrar_outbox(
        self,
        *,
        canal: str,
        destino: str,
        tipo: str,
        contenido: str,
        metadatos: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item = {
            "id": len(self.outbox) + 1,
            "canal": canal,
            "destino": destino,
            "tipo": tipo,
            "contenido": contenido,
            "metadatos": dict(metadatos or {}),
            "estado": "ENCOLADO",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.outbox.insert(0, item)
        return item

    async def listar_outbox(self, limite: int = 50) -> list[dict[str, Any]]:
        return [dict(item) for item in self.outbox[: max(1, int(limite))]]
