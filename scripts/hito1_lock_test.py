"""HITO 1 - Test de Candado del Modulo 0.

Inserta el pedido real del Ing. Reyes descrito en el PDR
(320 m3 de FC-210 y 52 m3 de FC-350), verifica que el reparto en
viajes y las consultas de inventario/timeline devuelvan datos sin error,
e imprime el estado de las recetas (que el PDR no trae).

Uso:
    python scripts/hito1_lock_test.py
    python scripts/hito1_lock_test.py --provisional   # calcula kardex con
                                                      # la receta derivada del PDR

Sale con codigo 1 si alguna verificacion estructural falla.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal

import _path  # noqa: F401

import asyncpg

from app.db import create_pool, run_migrations
from app.services.ordenes import NuevaOrden, crear_orden
from app.settings import get_settings

TAG = "HITO1-LOCK"
CLIENTE = "Ing. Reyes (prueba Hito 1)"
OK = "[OK]"
FALLA = "[FALLA]"
PEND = "[PENDIENTE]"


def _linea(titulo: str) -> None:
    print()
    print("=" * 68)
    print(titulo)
    print("=" * 68)


def _check(condicion: bool, mensaje: str) -> bool:
    print(f"  {OK if condicion else FALLA} {mensaje}")
    return condicion


async def _limpiar(pool: asyncpg.Pool) -> None:
    """Deja el test idempotente borrando solo lo que el mismo genero."""
    await pool.execute(
        """
        DELETE FROM inventory_movements
         WHERE order_id IN (SELECT id FROM orders WHERE notas = $1)
        """,
        TAG,
    )
    await pool.execute("DELETE FROM orders WHERE notas = $1", TAG)


async def _cliente_id(pool: asyncpg.Pool) -> str:
    row = await pool.fetchrow("SELECT id::text FROM clients WHERE nombre = $1", CLIENTE)
    if row:
        return row["id"]
    return await pool.fetchval(
        """
        INSERT INTO clients (nombre, estado, notas)
        VALUES ($1, 'ACTIVO', 'Creado por scripts/hito1_lock_test.py')
        RETURNING id::text
        """,
        CLIENTE,
    )


async def main(provisional: bool) -> int:
    settings = get_settings()
    pool = await create_pool(settings.database_url)
    fallos = 0

    try:
        aplicadas = await run_migrations(pool, settings.migrations_dir)
        _linea("HITO 1 - MODULO 0 (PostgreSQL)")
        print(f"  Migraciones aplicadas ahora: {aplicadas or 'ninguna (ya estaban)'}")

        tablas = await pool.fetchval(
            """
            SELECT count(*) FROM information_schema.tables
             WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
               AND table_name <> 'schema_migrations'
            """
        )
        print(f"  Tablas de negocio/operacion creadas: {tablas}")

        await _limpiar(pool)
        cliente_id = await _cliente_id(pool)

        orden_210 = await crear_orden(
            pool,
            NuevaOrden(
                cliente_id=cliente_id,
                resistencia="FC-210",
                volumen_m3=Decimal("320"),
                planta_codigo="PLANTA-COCA",
                forma_pago="FIADO",
                notas=TAG,
                creada_por="hito1_lock_test",
                permitir_receta_provisional=provisional,
            ),
        )
        orden_350 = await crear_orden(
            pool,
            NuevaOrden(
                cliente_id=cliente_id,
                resistencia="FC-350",
                volumen_m3=Decimal("52"),
                planta_codigo="PLANTA-COCA",
                forma_pago="FIADO",
                notas=TAG,
                creada_por="hito1_lock_test",
                permitir_receta_provisional=provisional,
            ),
        )

        _linea("PEDIDO DEL ING. REYES")
        print(f"  Orden #{orden_210.orden_numero}: 320 m3 FC-210 -> {orden_210.total_viajes} viajes")
        print(f"  Orden #{orden_350.orden_numero}:  52 m3 FC-350 -> {orden_350.total_viajes} viajes")

        _linea("VERIFICACIONES ESTRUCTURALES")
        fallos += not _check(orden_210.total_viajes == 40, "320 m3 / mixer 8 m3 = 40 viajes")
        fallos += not _check(
            sum(Decimal(str(v["volumen_m3"])) for v in orden_210.viajes) == Decimal("320"),
            "La suma de los 40 viajes es exactamente 320 m3",
        )
        fallos += not _check(
            orden_350.total_viajes == 7,
            "52 m3 con politica ultimo_parcial = 6 viajes de 8 m3 + 1 de 4 m3",
        )
        fallos += not _check(
            sum(Decimal(str(v["volumen_m3"])) for v in orden_350.viajes) == Decimal("52"),
            "La suma de los viajes de FC-350 es exactamente 52 m3",
        )

        viajes_db = await pool.fetchval(
            "SELECT count(*) FROM mixer_dispatches WHERE order_id = $1::uuid",
            orden_210.orden_id,
        )
        fallos += not _check(viajes_db == 40, "PostgreSQL devuelve 40 filas en mixer_dispatches")

        timeline = await pool.fetch(
            "SELECT * FROM v_dispatch_timeline WHERE order_id = $1::uuid ORDER BY viaje_numero",
            orden_210.orden_id,
        )
        fallos += not _check(len(timeline) == 40, "v_dispatch_timeline devuelve los 40 viajes")
        fallos += not _check(
            timeline[0]["estado_actual"] == "PROGRAMADO",
            "El primer viaje arranca en estado PROGRAMADO",
        )

        inventario = await pool.fetch("SELECT * FROM v_inventario ORDER BY codigo")
        fallos += not _check(len(inventario) == 5, "v_inventario devuelve los 5 materiales")

        kardex = await pool.fetchval(
            """
            SELECT count(*) FROM inventory_movements
             WHERE order_id IN (SELECT id FROM orders WHERE notas = $1)
            """,
            TAG,
        )
        print(f"  Movimientos de kardex generados: {kardex}")

        _linea("ESTADO DE LAS RECETAS (dato que el PDR NO trae)")
        recetas = await pool.fetch(
            "SELECT resistencia, cemento_sacos_m3, retardante_litros_m3, confirmado, fuente"
            "  FROM concrete_recipes ORDER BY resistencia"
        )
        for r in recetas:
            estado = "CONFIRMADA" if r["confirmado"] else "PROVISIONAL"
            print(
                f"  {r['resistencia']}: cemento={r['cemento_sacos_m3']} sacos/m3, "
                f"retardante={r['retardante_litros_m3']} L/m3 -> {estado}"
            )
            if not r["confirmado"]:
                print(f"      {PEND} {r['fuente']}")

        consumo_210 = orden_210.consumo_orden
        if consumo_210:
            print(
                f"\n  Consumo teorico FC-210 (provisional={consumo_210['provisional']}): "
                f"{consumo_210['cemento_sacos']} sacos, "
                f"{consumo_210['retardante_litros']} L de retardante"
            )
        print("\n  Avisos del motor:")
        for aviso in orden_210.advertencias + orden_350.advertencias:
            print(f"    - {aviso}")

        _linea("RESULTADO")
        if fallos == 0:
            print("  [CANDADO ABIERTO] La estructura del Modulo 0 responde sin error.")
            print("  Para CERRAR el Hito 1 falta que Julio valide las recetas reales.")
            return 0
        print(f"  [CANDADO BLOQUEADO] {fallos} verificacion(es) fallaron.")
        return 1
    finally:
        await pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test de Candado del Hito 1")
    parser.add_argument(
        "--provisional",
        action="store_true",
        help="Calcula el kardex con la receta derivada del PDR (FC-210) aunque no este confirmada.",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.provisional)))
