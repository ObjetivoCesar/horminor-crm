"""Registro de eventos en error_logs (usado por el Centinela y por la API)."""

from __future__ import annotations

import json
import logging
from uuid import UUID

import asyncpg

log = logging.getLogger(__name__)


async def log_event(
    pool: asyncpg.Pool,
    nivel: str,
    origen: str,
    mensaje: str,
    contexto: dict | None = None,
    order_id: UUID | str | None = None,
    dispatch_id: UUID | str | None = None,
) -> None:
    try:
        await pool.execute(
            """
            INSERT INTO error_logs (nivel, origen, mensaje, contexto, order_id, dispatch_id)
            VALUES ($1, $2, $3, $4::jsonb, $5::uuid, $6::uuid)
            """,
            nivel,
            origen,
            mensaje[:2000],
            json.dumps(contexto or {}, ensure_ascii=False, default=str),
            str(order_id) if order_id else None,
            str(dispatch_id) if dispatch_id else None,
        )
    except Exception:  # el log nunca debe tumbar la peticion
        log.exception("no se pudo escribir en error_logs")
