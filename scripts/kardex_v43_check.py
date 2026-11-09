"""Verificacion de integracion del kardex v4.3.

Se ejecuta contra una base de prueba (por defecto el clon ``orminorth_v43``)
y trabaja dentro de una transaccion que **siempre se revierte**: no deja
materiales, movimientos ni cambios de stock en la base.

Verifica:
  1. COMPRA: costo promedio ponderado y `costo_unitario_snapshot`.
  2. REAL: mueve stock al costo vigente sin alterar el promedio.
  3. TEORICO: guarda el costo vigente como snapshot sin tocar stock.
  4. ANULACION: revierte el TEORICO en `v_stock_proyectado` y es idempotente.
  5. Una ANULACION no puede revertir un movimiento fisico.

Uso:
    docker compose run --rm --no-deps \
      -e DATABASE_URL=postgresql://orminorth:orminorth@postgres:5432/orminorth_v43 \
      core-api python scripts/kardex_v43_check.py
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal

import _path  # noqa: F401

from app.db import create_pool
from app.m2_planta.dosificador import Consumo
from app.m2_planta.kardex import (
    anular_consumo_teorico,
    registrar_consumo_teorico,
    registrar_movimiento_real,
)
from app.settings import get_settings

CODIGO = "TEST-KARDEX-V43"
REFERENCIA = "TEST-KARDEX-V43"
_fallos = 0


def check(condicion: bool, mensaje: str, detalle: str = "") -> None:
    global _fallos
    if condicion:
        print(f"  [OK] {mensaje}")
        return
    _fallos += 1
    print(f"  [FALLA] {mensaje}" + (f" -> {detalle}" if detalle else ""))


def d(valor: object) -> Decimal:
    return Decimal(str(valor))


async def main() -> int:
    settings = get_settings()
    pool = await create_pool(settings.database_url)
    try:
        async with pool.acquire() as conn:
            tr = conn.transaction()
            await tr.start()
            try:
                material = await conn.fetchrow(
                    """
                    INSERT INTO materials
                        (codigo, nombre, unidad, stock_actual, stock_minimo,
                         costo_unitario, ultimo_levantamiento_at)
                    VALUES ($1, 'Material de prueba kardex v4.3', 'kg', 0, NULL,
                            NULL, now() - interval '1 hour')
                    RETURNING id::text
                    """,
                    CODIGO,
                )
                material_id = material["id"]
                print(f"Material de prueba: {material_id}\n")

                print("1. COMPRA y promedio ponderado")
                compra1 = await registrar_movimiento_real(
                    conn,
                    codigo=CODIGO,
                    cantidad=Decimal("100"),
                    costo_unitario=Decimal("8.20"),
                    referencia=REFERENCIA,
                    tipo="COMPRA",
                )
                check(
                    compra1["stock_actual"] == Decimal("100.000"),
                    "primera compra deja stock 100",
                    str(compra1["stock_actual"]),
                )
                check(
                    compra1["costo_unitario"] == Decimal("8.2000"),
                    "primera compra fija costo 8.2000",
                    str(compra1["costo_unitario"]),
                )
                check(
                    compra1["costo_unitario_snapshot"] == Decimal("8.2000"),
                    "snapshot de la primera compra = 8.2000",
                    str(compra1["costo_unitario_snapshot"]),
                )

                compra2 = await registrar_movimiento_real(
                    conn,
                    codigo=CODIGO,
                    cantidad=Decimal("100"),
                    costo_unitario=Decimal("10.00"),
                    referencia=REFERENCIA,
                    tipo="COMPRA",
                )
                check(
                    compra2["stock_actual"] == Decimal("200.000"),
                    "segunda compra deja stock 200",
                    str(compra2["stock_actual"]),
                )
                check(
                    compra2["costo_unitario"] == Decimal("9.1000"),
                    "promedio ponderado = (100*8.20 + 100*10.00)/200 = 9.1000",
                    str(compra2["costo_unitario"]),
                )
                check(
                    compra2["costo_unitario_snapshot"] == Decimal("10.0000"),
                    "snapshot de la segunda compra = costo de compra 10.0000",
                    str(compra2["costo_unitario_snapshot"]),
                )

                print("\n2. Movimiento REAL al costo vigente")
                real = await registrar_movimiento_real(
                    conn,
                    codigo=CODIGO,
                    cantidad=Decimal("-50"),
                    referencia=REFERENCIA,
                    tipo="REAL",
                )
                check(
                    real["stock_actual"] == Decimal("150.000"),
                    "salida REAL deja stock 150",
                    str(real["stock_actual"]),
                )
                check(
                    real["costo_unitario"] == Decimal("9.1000"),
                    "la salida no cambia el costo promedio",
                    str(real["costo_unitario"]),
                )
                check(
                    real["costo_unitario_snapshot"] == Decimal("9.1000"),
                    "snapshot de la salida = costo vigente 9.1000",
                    str(real["costo_unitario_snapshot"]),
                )

                print("\n3. TEORICO: snapshot sin mover stock")
                consumo = Consumo(
                    resistencia="FC-210",
                    volumen_m3=Decimal("0.01"),
                    cemento_sacos=Decimal("0.075"),
                    arena_m3=None,
                    ripio_m3=None,
                    agua_litros=None,
                    retardante_litros=None,
                    campos_faltantes=(),
                    provisional=False,
                )
                teorico = await registrar_consumo_teorico(
                    conn,
                    consumo=consumo,
                    referencia=REFERENCIA,
                )
                check(
                    len(teorico) == 1,
                    "el consumo TEORICO solo toca el material con cantidad",
                    str(len(teorico)),
                )
                check(
                    teorico[0]["costo_unitario_snapshot"] == 8.2,
                    "TEORICO guarda el costo vigente del CEMENTO (8.20)",
                    str(teorico[0]["costo_unitario_snapshot"]),
                )
                cemento_stock = await conn.fetchval(
                    "SELECT stock_actual FROM materials WHERE codigo = 'CEMENTO'"
                )
                check(
                    d(cemento_stock) == Decimal("3500.000"),
                    "el TEORICO no modifica el stock fisico del CEMENTO",
                    str(cemento_stock),
                )

                print("\n4. ANULACION de un TEORICO")
                teorico_temp = await conn.fetchrow(
                    """
                    INSERT INTO inventory_movements
                        (material_id, tipo, cantidad, referencia,
                         costo_unitario_snapshot)
                    VALUES ($1, 'TEORICO', -10, $2, 9.1000)
                    RETURNING id
                    """,
                    material_id,
                    REFERENCIA,
                )
                proyectado = await conn.fetchrow(
                    """
                    SELECT stock_real_fisico, consumo_teorico_acumulado,
                           stock_proyectado_disponible
                      FROM v_stock_proyectado
                     WHERE codigo = $1
                    """,
                    CODIGO,
                )
                check(
                    d(proyectado["stock_real_fisico"]) == Decimal("150.000"),
                    "stock real del material de prueba = 150",
                    str(proyectado["stock_real_fisico"]),
                )
                check(
                    d(proyectado["consumo_teorico_acumulado"]) == Decimal("-10.000"),
                    "el TEORICO descuenta 10 del proyectado",
                    str(proyectado["consumo_teorico_acumulado"]),
                )
                check(
                    d(proyectado["stock_proyectado_disponible"]) == Decimal("140.000"),
                    "stock proyectado = 150 - 10 = 140",
                    str(proyectado["stock_proyectado_disponible"]),
                )

                anulacion = await anular_consumo_teorico(
                    conn, movimiento_id=teorico_temp["id"]
                )
                check(
                    anulacion["cantidad"] == Decimal("10"),
                    "ANULACION guarda la reversa +10",
                    str(anulacion["cantidad"]),
                )
                check(
                    anulacion["costo_unitario_snapshot"] == Decimal("9.1000"),
                    "ANULACION conserva el snapshot del TEORICO",
                    str(anulacion["costo_unitario_snapshot"]),
                )
                despues = await conn.fetchrow(
                    """
                    SELECT consumo_teorico_acumulado, stock_proyectado_disponible
                      FROM v_stock_proyectado
                     WHERE codigo = $1
                    """,
                    CODIGO,
                )
                check(
                    d(despues["consumo_teorico_acumulado"]) == Decimal("0.000"),
                    "la ANULACION devuelve el consumo teorico a 0",
                    str(despues["consumo_teorico_acumulado"]),
                )
                check(
                    d(despues["stock_proyectado_disponible"]) == Decimal("150.000"),
                    "la ANULACION devuelve el proyectado a 150",
                    str(despues["stock_proyectado_disponible"]),
                )

                repetida = await anular_consumo_teorico(
                    conn, movimiento_id=teorico_temp["id"]
                )
                check(
                    repetida["ya_existia"] is True
                    and repetida["anulacion_id"] == anulacion["anulacion_id"],
                    "anular dos veces es idempotente",
                    str(repetida),
                )
                total_anulaciones = await conn.fetchval(
                    "SELECT count(*) FROM inventory_movements "
                    "WHERE tipo = 'ANULACION' AND referencia = $1",
                    f"ANULA:{teorico_temp['id']}",
                )
                check(
                    total_anulaciones == 1,
                    "no se duplica la fila ANULACION",
                    str(total_anulaciones),
                )

                print("\n5. Una ANULACION no revierte movimientos fisicos")
                try:
                    await anular_consumo_teorico(
                        conn, movimiento_id=compra1["movimiento_id"]
                    )
                except ValueError as exc:
                    check(
                        "solo revierte movimientos TEORICO" in str(exc),
                        "COMPRA se rechaza y se remite a AJUSTE",
                        str(exc),
                    )
                else:
                    check(False, "COMPRA se rechaza y se remite a AJUSTE")

                snapshots = await conn.fetch(
                    """
                    SELECT tipo, cantidad, costo_unitario_snapshot
                      FROM inventory_movements
                     WHERE material_id = $1
                     ORDER BY id
                    """,
                    material_id,
                )
                check(
                    len(snapshots) == 5,
                    "el material de prueba tiene 5 movimientos",
                    str(len(snapshots)),
                )
                check(
                    all(fila["costo_unitario_snapshot"] is not None for fila in snapshots),
                    "todos los movimientos tienen costo_unitario_snapshot",
                )

                print()
                if _fallos:
                    print(f"KARDEX V4.3: {_fallos} FALLA(S)")
                    return 1
                print("KARDEX V4.3: OK")
                return 0
            finally:
                await tr.rollback()
    finally:
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
