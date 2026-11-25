"""Implementación PostgreSQL de AvisosDineroPort.

Cuando Gato escucha «me pagaron $200», NO toca la tabla payments.
Solo crea o actualiza un aviso en cerebro_tareas_internas para que
Secretaría lo vea en su bandeja y registre el cobro formalmente.

Idempotencia: si ya existe un aviso abierto para ese (cliente, monto, forma, día),
devuelve el existente en lugar de duplicarlo. Si el hablante ya lo confirmó antes,
marca repetido=True pero no falla.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

import asyncpg

_LOG = logging.getLogger(__name__)


def _clave_externa(
    cliente_id: str | None,
    monto_usd: Any,
    forma_pago: str | None,
    hoy: date,
) -> str:
    partes = f"{cliente_id or ''}|{monto_usd}|{forma_pago or ''}|{hoy.isoformat()}"
    return hashlib.sha256(partes.encode()).hexdigest()[:40]


class PostgresAvisosDinero:
    """Implementa AvisosDineroPort contra la tabla cerebro_tareas_internas."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def abierto(
        self,
        *,
        cliente_id: str | None,
        borrador_id: str | None,
    ) -> Mapping[str, Any] | None:
        """Busca un aviso de dinero pendiente para este cliente o borrador."""
        async with self._pool.acquire() as conn:
            if borrador_id:
                fila = await conn.fetchrow(
                    """
                    SELECT id::text, ficha_json, estado
                      FROM cerebro_tareas_internas
                     WHERE tipo = 'aviso_dinero'
                       AND estado NOT IN ('CERRADA', 'CANCELADA')
                       AND (ficha_json->>'borrador_id')::text = $1
                     ORDER BY creada_en DESC
                     LIMIT 1
                    """,
                    str(borrador_id),
                )
                if fila:
                    return dict(fila)
            if cliente_id:
                fila = await conn.fetchrow(
                    """
                    SELECT id::text, ficha_json, estado
                      FROM cerebro_tareas_internas
                     WHERE tipo = 'aviso_dinero'
                       AND estado NOT IN ('CERRADA', 'CANCELADA')
                       AND (ficha_json->>'cliente_id')::text = $1
                     ORDER BY creada_en DESC
                     LIMIT 1
                    """,
                    str(cliente_id),
                )
                if fila:
                    return dict(fila)
        return None

    async def registrar_aviso(
        self,
        *,
        cliente_id: str | None,
        cliente_nombre: str | None,
        monto_usd: Any,
        forma_pago: str | None,
        referencia: str | None,
        cita: str | None,
        hablante: str,
        actor: Any,  # ActorLike
        clave: str,
        borrador_id: str | None = None,
        extraccion_id: str | None = None,
    ) -> Mapping[str, Any]:
        """Crea o actualiza el aviso para Secretaría. Nunca toca payments."""
        from ... import tiempo  # import local para evitar circular

        try:
            monto_decimal = Decimal(str(monto_usd)).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError, ValueError):
            monto_decimal = None

        hoy = tiempo.hoy()
        clave_ext = _clave_externa(cliente_id, monto_usd, forma_pago, hoy)

        ficha: dict[str, Any] = {
            "cliente_id": cliente_id,
            "cliente_nombre": cliente_nombre,
            "monto_usd": str(monto_decimal) if monto_decimal else str(monto_usd),
            "forma_pago": forma_pago,
            "referencia": referencia,
            "cita": cita,
            "hablante": hablante,
            "reportado_por": actor.actor_id,
            "borrador_id": borrador_id,
            "extraccion_id": extraccion_id,
            "clave_externa": clave_ext,
            "clave": clave,
        }
        ficha_json = json.dumps(ficha, ensure_ascii=False, default=str)

        async with self._pool.acquire() as conn:
            # Buscar si ya existe un aviso con la misma clave externa (mismo día, monto y forma)
            existente = await conn.fetchrow(
                """
                SELECT id::text, estado, (ficha_json->>'repetido')::boolean AS repetido
                  FROM cerebro_tareas_internas
                 WHERE tipo = 'aviso_dinero'
                   AND ficha_json->>'clave_externa' = $1
                 LIMIT 1
                """,
                clave_ext,
            )
            if existente:
                # Si ya está notificado, marcamos repetido sin crear otro
                if existente["estado"] in ("NOTIFICADA", "CERRADA"):
                    _LOG.info("Aviso de dinero duplicado (ya notificado): %s", clave_ext)
                    return {"id": existente["id"], "estado": existente["estado"], "repetido": True}
                # Está abierto: actualizar con la cita más reciente
                await conn.execute(
                    """
                    UPDATE cerebro_tareas_internas
                       SET ficha_json = $1::jsonb,
                           actualizado_en = now()
                     WHERE id = $2::uuid
                    """,
                    ficha_json,
                    existente["id"],
                )
                _LOG.info("Aviso de dinero actualizado: %s", existente["id"])
                return {"id": existente["id"], "estado": existente["estado"], "repetido": False}

            # Crear nuevo aviso
            fila = await conn.fetchrow(
                """
                INSERT INTO cerebro_tareas_internas
                       (tipo, descripcion, prioridad, asignado_a_rol,
                        creado_por, ficha_json)
                VALUES ('aviso_dinero',
                        $1,
                        'ALTA',
                        'SECRETARIA',
                        $2,
                        $3::jsonb)
                RETURNING id::text, estado
                """,
                f"Pago reportado por {actor.nombre}: "
                f"{monto_decimal or monto_usd} USD "
                f"({forma_pago or 'sin especificar forma'}) "
                f"- {cliente_nombre or 'cliente sin identificar'}",
                actor.actor_id,
                ficha_json,
            )
            _LOG.info("Aviso de dinero creado: %s", fila["id"])
            return {"id": fila["id"], "estado": fila["estado"], "repetido": False}
