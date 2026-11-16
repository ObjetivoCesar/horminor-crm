"""Servicio de clientes: alta compartida entre el panel y el Cerebro.

El Cerebro no debe insertar en ``clients`` por su cuenta: la unicidad del
teléfono y de la cédula, y el estado inicial, se resuelven en un solo lugar.
"""

from __future__ import annotations

from typing import Any

import asyncpg
from fastapi import HTTPException


async def crear_cliente(
    pool: asyncpg.Pool,
    *,
    nombre: str,
    constructora: str | None = None,
    ruc: str | None = None,
    telefono_whatsapp: str | None = None,
    provincia: str | None = None,
    ciudad: str | None = None,
    direccion_obra: str | None = None,
    credit_limit_usd: float | None = None,
    notas: str | None = None,
    estado: str = "ACTIVO",
    cedula: str | None = None,
) -> dict[str, Any]:
    """Crea el cliente y devuelve la fila creada.

    ``telefono_whatsapp`` y ``cedula`` son únicos: si chocan, se responde 409
    para que el llamador resuelva el cliente existente en vez de duplicarlo.
    """
    try:
        fila = await pool.fetchrow(
            """
            INSERT INTO clients
                (nombre, constructora, ruc, telefono_whatsapp, provincia,
                 ciudad, direccion_obra, credit_limit_usd, notas, estado, cedula)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING id::text, nombre, constructora, ruc, provincia, ciudad,
                      direccion_obra, credit_limit_usd, notas, estado, cedula,
                      telefono_whatsapp
            """,
            nombre,
            constructora,
            ruc,
            telefono_whatsapp,
            provincia,
            ciudad,
            direccion_obra,
            credit_limit_usd,
            notas,
            estado,
            cedula,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(
            status_code=409,
            detail="telefono_whatsapp o cedula ya registrados",
        ) from exc
    return dict(fila)
