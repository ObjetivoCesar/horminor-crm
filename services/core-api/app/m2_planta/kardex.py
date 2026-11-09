"""Modulo 2 - Kardex de materiales.

Convencion: `inventory_movements.cantidad` lleva signo (negativo = salida).
`materials.stock_actual` es el stock REAL (levantamiento fisico o compras),
no el teorico. El teorico se obtiene sumando movimientos tipo TEORICO.

v4.3 (decision 2026-11-09): el inventario se valora por **promedio
ponderado**. `materials.costo_unitario` guarda el costo vigente y cada
movimiento conserva `costo_unitario_snapshot` para valorar COGS sin
recalcular el pasado.

`ANULACION` revierte un consumo TEORICO (no toca stock fisico); una
correccion de un movimiento REAL/COMPRA/AJUSTE se registra como `AJUSTE`
con el signo contrario.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

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

TIPOS_MOVIMIENTO_FISICO = ("REAL", "COMPRA", "AJUSTE")
_CUATRO_DECIMALES = Decimal("0.0001")


def _redondear_costo(valor: Decimal) -> Decimal:
    """Redondea a 4 decimales, igual que `numeric(10,4)`/`numeric(14,4)`."""
    return valor.quantize(_CUATRO_DECIMALES, rounding=ROUND_HALF_UP)


def costo_promedio_ponderado(
    *,
    stock_actual: Decimal | None,
    costo_actual: Decimal | None,
    cantidad_comprada: Decimal,
    costo_compra: Decimal,
) -> Decimal:
    """Costo promedio despues de una compra.

    Si no hay stock o costo previo confirmado, el costo de la compra es la
    unica base real disponible: no se inventa un stock inicial. Si el stock
    previo es cero o negativo, tambien prevalece el costo de compra.
    """
    if cantidad_comprada <= 0:
        raise ValueError("cantidad_comprada debe ser mayor que cero")
    if costo_compra < 0:
        raise ValueError("costo_compra no puede ser negativo")

    if (
        stock_actual is None
        or costo_actual is None
        or stock_actual <= 0
    ):
        return _redondear_costo(costo_compra)

    valor_previo = stock_actual * costo_actual
    valor_compra = cantidad_comprada * costo_compra
    return _redondear_costo(
        (valor_previo + valor_compra) / (stock_actual + cantidad_comprada)
    )


async def material_id(conn: asyncpg.Connection, codigo: str) -> str | None:
    return await conn.fetchval("SELECT id::text FROM materials WHERE codigo = $1", codigo)


async def registrar_consumo_teorico(
    conn: asyncpg.Connection,
    *,
    consumo: Consumo,
    order_id: str | None = None,
    dispatch_id: str | None = None,
    referencia: str = "receta",
) -> list[dict]:
    """Descuenta del kardex teorico lo que la receta dice para este viaje.

    No modifica `materials.stock_actual` (el stock es fisico). Guarda el costo
    promedio vigente como snapshot para poder valorar el consumo despues.
    """
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
        fila = await conn.fetchrow(
            """
            SELECT id::text, costo_unitario
              FROM materials
             WHERE codigo = $1
            """,
            codigo,
        )
        if fila is None:
            continue
        costo = fila["costo_unitario"]
        snapshot = None if costo is None else _redondear_costo(Decimal(costo))
        await conn.execute(
            """
            INSERT INTO inventory_movements
                (material_id, tipo, cantidad, order_id, dispatch_id, referencia,
                 costo_unitario_snapshot)
            VALUES ($1, 'TEORICO', $2, $3, $4, $5, $6)
            """,
            fila["id"],
            -Decimal(cantidad),
            order_id,
            dispatch_id,
            referencia,
            snapshot,
        )
        movimientos.append(
            {
                "material": codigo,
                "cantidad": float(-Decimal(cantidad)),
                "costo_unitario_snapshot": (
                    None if snapshot is None else float(snapshot)
                ),
            }
        )
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
    costo_unitario: Decimal | float | None = None,
) -> dict:
    """Registra un movimiento fisico y actualiza stock y costo promedio.

    - `COMPRA`: exige cantidad positiva y costo unitario; recalcula el costo
      promedio ponderado de `materials.costo_unitario`.
    - `REAL` / `AJUSTE`: mueven el stock al costo vigente (o al costo indicado
      en `costo_unitario`) sin alterar el promedio.
    """
    if tipo not in TIPOS_MOVIMIENTO_FISICO:
        raise ValueError("tipo debe ser REAL, COMPRA o AJUSTE")
    cantidad_dec = Decimal(str(cantidad))
    if tipo == "COMPRA" and cantidad_dec <= 0:
        raise ValueError("Una COMPRA debe tener cantidad positiva")
    if tipo == "COMPRA" and costo_unitario is None:
        raise ValueError("Una COMPRA requiere costo_unitario")

    fila = await conn.fetchrow(
        """
        SELECT id::text, stock_actual, costo_unitario
          FROM materials
         WHERE codigo = $1
        """,
        codigo,
    )
    if fila is None:
        raise ValueError(f"Material desconocido: {codigo}")

    stock_previo = (
        None if fila["stock_actual"] is None else Decimal(fila["stock_actual"])
    )
    costo_previo = (
        None if fila["costo_unitario"] is None else Decimal(fila["costo_unitario"])
    )

    if costo_unitario is not None:
        costo_snapshot = _redondear_costo(Decimal(str(costo_unitario)))
    elif costo_previo is not None:
        costo_snapshot = _redondear_costo(costo_previo)
    else:
        costo_snapshot = None

    nuevo_stock = (stock_previo or Decimal("0")) + cantidad_dec
    if tipo == "COMPRA":
        nuevo_costo = costo_promedio_ponderado(
            stock_actual=stock_previo,
            costo_actual=costo_previo,
            cantidad_comprada=cantidad_dec,
            costo_compra=costo_snapshot,
        )
    else:
        nuevo_costo = costo_previo

    movimiento = await conn.fetchrow(
        """
        INSERT INTO inventory_movements
            (material_id, tipo, cantidad, order_id, dispatch_id, referencia,
             costo_unitario_snapshot)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id
        """,
        fila["id"],
        tipo,
        cantidad_dec,
        order_id,
        dispatch_id,
        referencia,
        costo_snapshot,
    )
    await conn.execute(
        """
        UPDATE materials
           SET stock_actual = $2,
               costo_unitario = $3,
               updated_at = now()
         WHERE id = $1
        """,
        fila["id"],
        nuevo_stock,
        nuevo_costo,
    )
    return {
        "movimiento_id": movimiento["id"],
        "material": codigo,
        "tipo": tipo,
        "cantidad": cantidad_dec,
        "stock_actual": nuevo_stock,
        "costo_unitario": nuevo_costo,
        "costo_unitario_snapshot": costo_snapshot,
    }


async def anular_consumo_teorico(
    conn: asyncpg.Connection,
    *,
    movimiento_id: int | str,
    referencia: str | None = None,
) -> dict:
    """Revierte un movimiento TEORICO con una fila ANULACION.

    No borra el original ni toca `materials.stock_actual`: el consumo teorico
    nunca movio stock fisico. La vista `v_stock_proyectado` suma la ANULACION
    en valor absoluto. Es idempotente por `referencia` (por defecto
    ``ANULA:<id>``): repetir la llamada devuelve la misma anulacion.
    """
    original = await conn.fetchrow(
        """
        SELECT id, material_id, tipo, cantidad, order_id, dispatch_id,
               costo_unitario_snapshot
          FROM inventory_movements
         WHERE id = $1
        """,
        int(movimiento_id),
    )
    if original is None:
        raise ValueError(f"Movimiento desconocido: {movimiento_id}")
    if original["tipo"] != "TEORICO":
        raise ValueError(
            "ANULACION solo revierte movimientos TEORICO; para REAL/COMPRA/"
            "AJUSTE registre un AJUSTE con el signo contrario"
        )
    cantidad = Decimal(original["cantidad"])
    if cantidad == 0:
        raise ValueError("El movimiento TEORICO no tiene cantidad que anular")

    referencia_anulacion = referencia or f"ANULA:{original['id']}"
    existente = await conn.fetchrow(
        """
        SELECT id
          FROM inventory_movements
         WHERE tipo = 'ANULACION' AND referencia = $1
        """,
        referencia_anulacion,
    )
    if existente is not None:
        return {
            "movimiento_id": original["id"],
            "anulacion_id": existente["id"],
            "ya_existia": True,
        }

    anulacion = await conn.fetchrow(
        """
        INSERT INTO inventory_movements
            (material_id, tipo, cantidad, order_id, dispatch_id, referencia,
             costo_unitario_snapshot)
        VALUES ($1, 'ANULACION', $2, $3, $4, $5, $6)
        RETURNING id
        """,
        original["material_id"],
        -cantidad,
        original["order_id"],
        original["dispatch_id"],
        referencia_anulacion,
        original["costo_unitario_snapshot"],
    )
    return {
        "movimiento_id": original["id"],
        "anulacion_id": anulacion["id"],
        "cantidad": -cantidad,
        "costo_unitario_snapshot": original["costo_unitario_snapshot"],
        "ya_existia": False,
    }


async def inventario(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    return await pool.fetch("SELECT * FROM v_inventario ORDER BY codigo")
