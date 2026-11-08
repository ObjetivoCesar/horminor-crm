"""Modulo 2 - Kardex de materiales.

Convencion: `inventory_movements.cantidad` lleva signo (negativo = salida).
`materials.stock_actual` es el stock REAL (levantamiento fisico o compras),
no el teorico. El teorico se obtiene sumando movimientos tipo TEORICO.
"""

from __future__ import annotations

from decimal import Decimal

import asyncpg

from .dosificador import Consumo

MAPA_RECETA_MATERIAL: dict[str, str] = {
    "cemento_sacos": "CEMENTO",
    "arena_m3": "ARENA",
    "ripio_m3": "RIPIO",
    "agua_litros": "AGUA",
    "retardante_litros": "RETARDANTE",
}

MAPA_CONSUMO_MATERIAL: dict[str, str] = {
    "cemento_sacos": "CEMENTO",
    "arena_m3": "ARENA",
    "ripio_m3": "RIPIO",
    "agua_litros": "AGUA",
    "retardante_litros": "RETARDANTE",
}


async def material_id(conn: asyncpg.Connection, codigo: str) -> str | None:
    return await conn.fetchval("SELECT id::text FROM materials WHERE codigo = $1", codigo)


async def registrar_consumo_teorico(
    conn: asyncpg.Connection,
    *,
    order_id: str,
    dispatch_id: str,
    consumo: Consumo,
    referencia: str = "receta",
) -> list[dict]:
    """Descuenta del kardex teorico lo que la receta dice para este viaje."""
    movimientos: list[dict] = []
    valores = {
        "cemento_sacos": consumo.cemento_sacos,
        "arena_m3": consumo.arena_m3,
        "ripio_m3": consumo.ripio_m3,
        "agua_litros": consumo.agua_litros,
        "retardante_litros": consumo.retardante_litros,
    }
    for campo, codigo in MAPA_CONSUMO_MATERIAL.items():
        cantidad = valores[campo]
        if cantidad is None:
            continue
        mid = await material_id(conn, codigo)
        if mid is None:
            continue
        await conn.execute(
            """
            INSERT INTO inventory_movements
                (material_id, tipo, cantidad, order_id, dispatch_id, referencia)
            VALUES ($1, 'TEORICO', $2, $3, $4, $5)
            """,
            mid,
            -Decimal(cantidad),
            order_id,
            dispatch_id,
            referencia,
        )
        movimientos.append({"material": codigo, "cantidad": float(-Decimal(cantidad))})
    return movimientos


async def registrar_movimiento_real(
    conn: asyncpg.Connection,
    *,
    codigo: str,
    cantidad: Decimal | float,
    referencia: str | None = None,
    order_id: str | None = None,
    dispatch_id: str | None = None,
    tipo: str = "REAL",
) -> None:
    """Registra un movimiento fisico y actualiza el stock real."""
    if tipo not in ("REAL", "COMPRA", "AJUSTE"):
        raise ValueError("tipo debe ser REAL, COMPRA o AJUSTE")
    mid = await material_id(conn, codigo)
    if mid is None:
        raise ValueError(f"Material desconocido: {codigo}")
    cantidad_dec = Decimal(str(cantidad))
    await conn.execute(
        """
        INSERT INTO inventory_movements
            (material_id, tipo, cantidad, order_id, dispatch_id, referencia)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        mid,
        tipo,
        cantidad_dec,
        order_id,
        dispatch_id,
        referencia,
    )
    await conn.execute(
        """
        UPDATE materials
           SET stock_actual = COALESCE(stock_actual, 0) + $2,
               updated_at = now()
         WHERE id = $1
        """,
        mid,
        cantidad_dec,
    )


async def inventario(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    return await pool.fetch("SELECT * FROM v_inventario ORDER BY codigo")
