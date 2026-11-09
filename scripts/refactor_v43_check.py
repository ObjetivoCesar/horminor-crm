"""Verificacion de integracion del refactor v4.3 (IVA + COBRO inicial).

Se ejecuta contra una base de prueba (por defecto el clon ``orminorth_v43``),
crea un cliente marcado, registra cuatro ventas (EFECTIVO, TRANSFERENCIA,
ABONO y FIADO), verifica ``orders``, ``payments`` y ``v_cliente_saldo``, y
borra sus propios datos al terminar.

Uso:
    docker compose run --rm --no-deps \
      -e DATABASE_URL=postgresql://orminorth:orminorth@postgres:5432/orminorth_v43 \
      core-api python scripts/refactor_v43_check.py

No toca datos de negocio: todo lo que crea queda con ``creada_por`` = TAG y se
elimina en el bloque ``finally``. Sale con codigo 1 si una verificacion falla.
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal

import _path  # noqa: F401

import asyncpg

from app.db import create_pool
from app.services.ordenes import NuevaOrden, crear_orden
from app.settings import get_settings

TAG = "REFACTOR-V43-CHECK"
CLIENTE = "Cliente prueba refactor v4.3"
RESISTENCIA = "FC-210"
PLANTA = "PLANTA-COCA"
VOLUMEN = Decimal("2")

_fallos = 0


def check(condicion: bool, mensaje: str, detalle: str = "") -> None:
    global _fallos
    if condicion:
        print(f"  [OK] {mensaje}")
        return
    _fallos += 1
    print(f"  [FALLA] {mensaje}" + (f" -> {detalle}" if detalle else ""))


async def limpiar(pool: asyncpg.Pool, cliente_id: str | None = None) -> None:
    async with pool.acquire() as conn:
        if cliente_id is None:
            fila = await conn.fetchrow(
                "SELECT id::text FROM clients WHERE nombre = $1", CLIENTE
            )
            cliente_id = fila["id"] if fila else None
        if cliente_id is None:
            return
        # Orden correcto por las FKs: kardex -> pagos -> ordenes (cascada de
        # viajes) -> cliente.
        await conn.execute(
            """
            DELETE FROM inventory_movements
             WHERE order_id IN (SELECT id FROM orders WHERE cliente_id = $1)
            """,
            cliente_id,
        )
        await conn.execute("DELETE FROM payments WHERE cliente_id = $1", cliente_id)
        await conn.execute("DELETE FROM orders WHERE cliente_id = $1", cliente_id)
        await conn.execute("DELETE FROM clients WHERE id = $1", cliente_id)


async def cobro_de(pool: asyncpg.Pool, orden_id: str) -> list[asyncpg.Record]:
    return await pool.fetch(
        """
        SELECT p.id::text, p.metodo, p.monto, p.bolsa, p.tipo_movimiento,
               p.deleted_at, a.slug AS cuenta
          FROM payments p
          LEFT JOIN accounting_accounts a ON a.id = p.account_id
         WHERE p.order_id = $1
         ORDER BY p.created_at
        """,
        orden_id,
    )


async def main() -> int:
    settings = get_settings()
    pool = await create_pool(settings.database_url)
    cliente_id: str | None = None
    try:
        await limpiar(pool)
        cliente = await pool.fetchrow(
            """
            INSERT INTO clients (nombre, estado)
            VALUES ($1, 'ACTIVO')
            RETURNING id::text
            """,
            CLIENTE,
        )
        cliente_id = cliente["id"]
        print(f"Cliente de prueba: {cliente_id}")

        escenarios = [
            ("EFECTIVO", Decimal("0")),
            ("TRANSFERENCIA", Decimal("0")),
            ("ABONO", Decimal("100.00")),
            ("FIADO", Decimal("0")),
        ]
        ordenes: dict[str, object] = {}

        print("\n1. Alta de ventas con IVA y COBRO inicial")
        for forma_pago, abono in escenarios:
            datos = NuevaOrden(
                cliente_id=cliente_id,
                resistencia=RESISTENCIA,
                volumen_m3=VOLUMEN,
                planta_codigo=PLANTA,
                forma_pago=forma_pago,
                creada_por=TAG,
                aplica_iva=True,
                abono_inicial_monto=abono if forma_pago == "ABONO" else None,
                abono_inicial_metodo=(
                    "TRANSFERENCIA" if forma_pago == "ABONO" else None
                ),
            )
            orden = await crear_orden(pool, datos)
            ordenes[forma_pago] = orden
            check(
                orden.total == Decimal("236.00"),
                f"{forma_pago}: subtotal = 2 m3 x 118 = 236.00",
                str(orden.total),
            )
            check(
                orden.iva_pct == Decimal("15.00"),
                f"{forma_pago}: IVA 15% tomado de concrete_recipes",
                str(orden.iva_pct),
            )
            check(
                orden.iva_monto == Decimal("35.40"),
                f"{forma_pago}: IVA = 35.40",
                str(orden.iva_monto),
            )
            check(
                orden.total_con_iva == Decimal("271.40"),
                f"{forma_pago}: total bruto = 271.40",
                str(orden.total_con_iva),
            )

            fila = await pool.fetchrow(
                "SELECT total, iva_pct, iva_monto, total_con_iva "
                "FROM orders WHERE id = $1",
                orden.orden_id,
            )
            check(
                fila["total_con_iva"] == Decimal("271.40"),
                f"{forma_pago}: orders.total_con_iva persistido",
                str(fila["total_con_iva"]),
            )

            cobros = await cobro_de(pool, orden.orden_id)
            if forma_pago == "FIADO":
                check(len(cobros) == 0, "FIADO no genera COBRO")
                continue
            if forma_pago == "ABONO":
                check(len(cobros) == 1, "ABONO genera un COBRO inicial")
                esperado = Decimal("100.00")
                metodo = "TRANSFERENCIA"
                bolsa = "BANCO_GERENCIA"
                cuenta = "bancos_gerencia"
            else:
                check(len(cobros) == 1, f"{forma_pago} genera un COBRO")
                esperado = Decimal("271.40")
                metodo = forma_pago
                bolsa = (
                    "CAJA_DIARIA" if forma_pago == "EFECTIVO" else "BANCO_GERENCIA"
                )
                cuenta = (
                    "caja_diaria_secretaria"
                    if forma_pago == "EFECTIVO"
                    else "bancos_gerencia"
                )
            cobro = cobros[0]
            check(cobro["tipo_movimiento"] == "COBRO", f"{forma_pago}: tipo COBRO")
            check(cobro["metodo"] == metodo, f"{forma_pago}: metodo {metodo}")
            check(cobro["monto"] == esperado, f"{forma_pago}: monto {esperado}")
            check(cobro["bolsa"] == bolsa, f"{forma_pago}: bolsa {bolsa}")
            check(cobro["cuenta"] == cuenta, f"{forma_pago}: cuenta {cuenta}")

        print("\n2. Cartera del cliente (v_cliente_saldo)")
        saldo = await pool.fetchrow(
            """
            SELECT total_m3, total_facturado, total_cobrado, total_fiado,
                   saldo_pendiente, saldo_a_favor
              FROM v_cliente_saldo WHERE id = $1
            """,
            cliente_id,
        )
        check(saldo["total_m3"] == Decimal("8.000"), "total_m3 = 8", str(saldo["total_m3"]))
        check(
            saldo["total_facturado"] == Decimal("1085.60"),
            "total_facturado = 4 x 271.40 = 1085.60",
            str(saldo["total_facturado"]),
        )
        check(
            saldo["total_cobrado"] == Decimal("642.80"),
            "total_cobrado = 271.40 + 271.40 + 100.00 = 642.80",
            str(saldo["total_cobrado"]),
        )
        check(
            saldo["total_fiado"] == Decimal("271.40"),
            "total_fiado = solo la venta FIADO",
            str(saldo["total_fiado"]),
        )
        check(
            saldo["saldo_pendiente"] == Decimal("442.80"),
            "saldo_pendiente = 1085.60 - 642.80 = 442.80",
            str(saldo["saldo_pendiente"]),
        )
        check(
            saldo["saldo_a_favor"] == Decimal("0.00"),
            "saldo_a_favor = 0",
            str(saldo["saldo_a_favor"]),
        )

        print("\n3. Pago con deleted_at no cuenta para cartera")
        abono_id = (await cobro_de(pool, ordenes["ABONO"].orden_id))[0]["id"]
        await pool.execute(
            "UPDATE payments SET deleted_at = now() WHERE id = $1", abono_id
        )
        saldo_borrado = await pool.fetchrow(
            """
            SELECT total_cobrado, saldo_pendiente
              FROM v_cliente_saldo WHERE id = $1
            """,
            cliente_id,
        )
        check(
            saldo_borrado["total_cobrado"] == Decimal("542.80"),
            "COBRO borrado baja total_cobrado a 542.80",
            str(saldo_borrado["total_cobrado"]),
        )
        check(
            saldo_borrado["saldo_pendiente"] == Decimal("542.80"),
            "COBRO borrado sube saldo_pendiente a 542.80",
            str(saldo_borrado["saldo_pendiente"]),
        )

        print("\n4. Caja y dashboard ignoran payments.deleted_at")
        from app.m3_secretaria.service import PostgresSecretariaStore
        from app.m4_dashboard.service import PostgresDashboardStore

        fecha_pago = await pool.fetchval(
            "SELECT fecha FROM payments WHERE id = $1", abono_id
        )
        movimientos = await PostgresSecretariaStore(pool)._movimientos(fecha_pago)
        check(
            all(mov["id"] != abono_id for mov in movimientos),
            "el cierre de caja no lista el COBRO borrado",
        )
        resumen = await PostgresSecretariaStore(pool).resumen_cierre(fecha_pago)
        check(
            resumen["ventas"]["fiado"] == 271.40,
            "el cierre usa el total con IVA de la venta fiada",
            str(resumen["ventas"]["fiado"]),
        )
        check(
            resumen["cobros"]["transferencia"] == 271.40,
            "el cierre no suma el COBRO borrado",
            str(resumen["cobros"]["transferencia"]),
        )
        kpis = await PostgresDashboardStore(pool).hero_kpis(fecha_pago)
        check(
            kpis["kpi_caja"]["efectivo_hoy"] == 271.40,
            "dashboard: efectivo del dia sin borrados",
            str(kpis["kpi_caja"]["efectivo_hoy"]),
        )
        check(
            kpis["kpi_caja"]["transferencias_hoy"] == 271.40,
            "dashboard: transferencias del dia sin borrados",
            str(kpis["kpi_caja"]["transferencias_hoy"]),
        )
        check(
            kpis["kpi_caja"]["fiado_hoy"] == 271.40,
            "dashboard: fiado del dia sobre total con IVA",
            str(kpis["kpi_caja"]["fiado_hoy"]),
        )

        print("\n5. Validaciones de negocio")
        from app.services.ordenes import OrdenInvalidaError, validar_abono_inicial

        try:
            validar_abono_inicial(
                forma_pago="ABONO",
                monto=Decimal("300.00"),
                metodo="EFECTIVO",
                total_con_iva=Decimal("271.40"),
            )
        except OrdenInvalidaError:
            check(True, "abono mayor al total se rechaza")
        else:
            check(False, "abono mayor al total se rechaza")

        try:
            await crear_orden(
                pool,
                NuevaOrden(
                    cliente_id=cliente_id,
                    resistencia=RESISTENCIA,
                    volumen_m3=VOLUMEN,
                    planta_codigo=PLANTA,
                    forma_pago="EFECTIVO",
                    creada_por=TAG,
                aplica_iva=True,
                    abono_inicial_monto=Decimal("10.00"),
                    abono_inicial_metodo="EFECTIVO",
                ),
            )
        except OrdenInvalidaError:
            check(True, "abono inicial en venta EFECTIVO se rechaza")
        else:
            check(False, "abono inicial en venta EFECTIVO se rechaza")

        print()
        if _fallos:
            print(f"REFACTOR V4.3: {_fallos} FALLA(S)")
            return 1
        print("REFACTOR V4.3: OK")
        return 0
    finally:
        await limpiar(pool, cliente_id)
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
