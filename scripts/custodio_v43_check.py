"""Verificacion de integracion del Custodio v4.3 contra el clon.

Recorre el contrato completo: 14 intents de mutacion, 9 consultas, idempotencia
y correcciones con testigo. Todo ocurre en una unica conexion con una
transaccion externa que termina en ``ROLLBACK``: no queda ningun dato de
prueba, ni siquiera si una verificacion falla.

El script se niega a correr contra la base real ``orminorth``. Uso:

    docker compose run --rm --no-deps \
      -e DATABASE_URL=postgresql://orminorth:orminorth@postgres:5432/orminorth_v43 \
      core-api python scripts/custodio_v43_check.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import _path  # noqa: F401

import asyncpg

from app.custodio import Actor, Gate
from app.settings import get_settings

TAG = "CUSTODIO-V43-CHECK"
PREFIJO = "CUSTODIO V43 CHECK"

# Conteo real de solicitudes ejercitadas. No se escribe a mano en el resumen:
# si una prueba se agrega o se quita, la etiqueta cambia sola.
ESTADISTICAS: dict = {
    "intents": set(),
    "mutaciones": {},
    "testigos": {},
    "aprobaciones": 0,
}


class PoolDeUnaConexion:
    """Adapta una conexion con transaccion abierta a la interfaz de pool.

    El Gate abre ``conn.transaction()``; sobre esta conexion eso crea un
    savepoint. El ``ROLLBACK`` externo deshace todo el escenario.
    """

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    def acquire(self):
        conn = self._conn

        @asynccontextmanager
        async def _ctx():
            yield conn

        return _ctx()

    def __getattr__(self, nombre: str):
        return getattr(self._conn, nombre)


def exigir(condicion: bool, mensaje: str) -> None:
    if not condicion:
        raise AssertionError(mensaje)


def d(valor) -> Decimal:
    return Decimal(str(valor))


def solicitud_mutacion(intent: str, payload: dict, actor: Actor) -> dict:
    return {
        "contract_version": "1.3.0",
        "request_id": str(uuid4()),
        "channel": "TEST" if actor.role != "SYSTEM_CRON" else "SYSTEM_CRON",
        "intent": intent,
        "payload": payload,
    }


def solicitud_consulta(intent: str, filtros: dict) -> dict:
    return {
        "contract_version": "1.3.0",
        "request_id": str(uuid4()),
        "channel": "TEST",
        "intent": intent,
        "filters": filtros,
    }


def solicitud_testigo(
    intent: str,
    target_table: str,
    changes: dict,
    *,
    target_record_id: str | None = None,
    motivo: str = "Correccion de prueba con motivo suficiente",
) -> dict:
    datos = {
        "contract_version": "1.3.0",
        "request_id": str(uuid4()),
        "channel": "TEST",
        "intent": intent,
        "target_table": target_table,
        "motivo": motivo,
        "changes": changes,
    }
    if target_record_id is not None:
        datos["target_record_id"] = target_record_id
    return datos


async def mutar(
    gate: Gate,
    actor: Actor,
    intent: str,
    payload: dict,
    etiqueta: str,
    *,
    esperado: str = "ACCEPT",
) -> tuple[dict, dict]:
    solicitud = solicitud_mutacion(intent, payload, actor)
    respuesta = await gate.mutar(solicitud, actor)
    exigir(
        respuesta["status"] == esperado,
        f"{etiqueta}: se esperaba {esperado} y llego {respuesta}",
    )
    ESTADISTICAS["intents"].add(intent)
    estado = respuesta["status"]
    ESTADISTICAS["mutaciones"][estado] = (
        ESTADISTICAS["mutaciones"].get(estado, 0) + 1
    )
    if intent == "RESOLVE_APPROVAL_REQUEST":
        ESTADISTICAS["aprobaciones"] += 1
    return solicitud, respuesta


async def testigo(
    gate: Gate,
    actor: Actor,
    intent: str,
    target_table: str,
    changes: dict,
    etiqueta: str,
    *,
    target_record_id: str | None = None,
    esperado: str = "ACCEPT",
) -> dict:
    solicitud = solicitud_testigo(
        intent, target_table, changes, target_record_id=target_record_id
    )
    respuesta = await gate.testigo(solicitud, actor)
    exigir(
        respuesta["status"] == esperado,
        f"{etiqueta}: se esperaba {esperado} y llego {respuesta}",
    )
    estado = respuesta["status"]
    ESTADISTICAS["testigos"][estado] = (
        ESTADISTICAS["testigos"].get(estado, 0) + 1
    )
    return respuesta


async def consultar(
    gate: Gate, actor: Actor, intent: str, filtros: dict, etiqueta: str
) -> dict:
    respuesta = await gate.consultar(solicitud_consulta(intent, filtros), actor)
    exigir(
        respuesta["status"] == "ACCEPT",
        f"{etiqueta}: la consulta fallo: {respuesta}",
    )
    return respuesta


async def saldo_cuenta(conn: asyncpg.Connection, slug: str) -> Decimal:
    valor = await conn.fetchval(
        """
        SELECT COALESCE(SUM(le.debe - le.haber), 0)
          FROM ledger_entries le
          JOIN accounting_accounts aa ON aa.id = le.account_id
         WHERE aa.slug = $1
        """,
        slug,
    )
    return d(valor)


async def main() -> int:
    settings = get_settings()
    dsn = settings.database_url
    conn = await asyncpg.connect(dsn)
    base = await conn.fetchval("SELECT current_database()")
    if base != "orminorth_v43":
        print(
            f"ABORTADO: este check solo corre contra el clon orminorth_v43; "
            f"la conexion apunta a {base}."
        )
        await conn.close()
        return 2

    tablas = (
        "processed_requests",
        "audit_witness_log",
        "approval_requests",
        "ledger_entries",
        "payments",
        "supplier_payments",
        "purchases",
        "purchase_items",
        "goods_receipts",
        "suppliers",
        "fixed_assets",
        "depreciation_runs",
        "financial_liabilities",
        "loan_payments",
        "accounting_accounts",
        "orders",
        "clients",
    )
    antes = {
        tabla: await conn.fetchval(f"SELECT count(*) FROM {tabla}")
        for tabla in tablas
    }

    transaccion = conn.transaction()
    await transaccion.start()
    try:
        pool = PoolDeUnaConexion(conn)
        gate = Gate(pool)
        hoy: date = await conn.fetchval("SELECT CURRENT_DATE")
        vencimiento = hoy + timedelta(days=30)
        actor = Actor("SUPERADMIN", f"custodio-check-{uuid4()}")
        cron = Actor("SYSTEM_CRON", f"cron-check-{uuid4()}")
        bodega = Actor("BODEGA_PLANTA", f"bodega-check-{uuid4()}")

        print(f"Base: {base} | fecha de trabajo: {hoy.isoformat()}")

        # ------------------------------------------------------------------
        # Datos maestros de la prueba
        # ------------------------------------------------------------------
        cliente_id = await conn.fetchval(
            """
            INSERT INTO clients (nombre, constructora, ruc, estado,
                                 credit_limit_usd)
            VALUES ($1, $2, $3, 'ACTIVO', 100000.00)
            RETURNING id::text
            """,
            f"{PREFIJO} Cliente",
            "Constructora de prueba",
            f"TEST-{uuid4().hex[:12]}",
        )
        planta = await conn.fetchrow(
            "SELECT codigo FROM plants WHERE codigo = 'PLANTA-COCA'"
        )
        exigir(planta is not None, "falta la planta PLANTA-COCA en el clon")
        cemento = await conn.fetchrow(
            """
            SELECT id::text, stock_actual, costo_unitario
              FROM materials WHERE codigo = 'CEMENTO'
            """
        )
        exigir(cemento is not None, "falta el material CEMENTO en el clon")
        receta = await conn.fetchrow(
            """
            SELECT precio_m3, iva_pct
              FROM concrete_recipes
             WHERE resistencia = 'FC-210' AND confirmado = true
            """
        )
        exigir(receta is not None, "falta la receta confirmada FC-210")

        # ------------------------------------------------------------------
        # 1. CREATE_SUPPLIER
        # ------------------------------------------------------------------
        _, r = await mutar(
            gate,
            actor,
            "CREATE_SUPPLIER",
            {
                "nombre": f"{PREFIJO} Proveedor",
                "identificacion": f"TEST{uuid4().hex[:10].upper()}",
                "telefono": None,
            },
            "CREATE_SUPPLIER",
        )
        supplier_id = r["data"]["supplier"]["id"]
        print("1. CREATE_SUPPLIER: OK")

        # ------------------------------------------------------------------
        # 2. CREATE_FIXED_ASSET
        # ------------------------------------------------------------------
        codigo_activo = f"{TAG}-ACT-{uuid4().hex[:8].upper()}"
        _, r = await mutar(
            gate,
            actor,
            "CREATE_FIXED_ASSET",
            {
                "codigo": codigo_activo,
                "nombre": "Equipo de prueba custodia",
                "categoria": "EQUIPO_OFICINA",
                "fecha_adquisicion": hoy.isoformat(),
                "fecha_inicio_depreciacion": hoy.isoformat(),
                "costo_historico": "1200.00",
                "valor_residual": "0.00",
                "vida_util_meses": 12,
            },
            "CREATE_FIXED_ASSET",
        )
        asset_id = r["data"]["fixed_asset"]["id"]
        print("2. CREATE_FIXED_ASSET: OK")

        # ------------------------------------------------------------------
        # 3. CREATE_FINANCIAL_LIABILITY
        # ------------------------------------------------------------------
        _, r = await mutar(
            gate,
            actor,
            "CREATE_FINANCIAL_LIABILITY",
            {
                "entidad_financiera": f"{PREFIJO} Banco",
                "numero_operacion": f"OP-{uuid4().hex[:10].upper()}",
                "fecha_desembolso": hoy.isoformat(),
                "monto_original": "1000.00",
                "saldo_capital_actual": "1000.00",
                "tasa_interes_anual_pct": "12.00",
                "cuota_mensual_referencial": "100.00",
                "plazo_restante_meses": 10,
            },
            "CREATE_FINANCIAL_LIABILITY",
        )
        liability_id = r["data"]["financial_liability"]["id"]
        print("3. CREATE_FINANCIAL_LIABILITY: OK")

        # ------------------------------------------------------------------
        # 4. SET_OPENING_BALANCES
        # ------------------------------------------------------------------
        _, r = await mutar(
            gate,
            actor,
            "SET_OPENING_BALANCES",
            {
                "fecha_corte": hoy.isoformat(),
                "saldos": [
                    {"account_slug": "caja_diaria_secretaria", "monto": "1000.00"},
                    {"account_slug": "inventario_insumos_silos", "monto": "500.00"},
                    {"account_slug": "cuentas_por_pagar_proveedores", "monto": "200.00"},
                    {"account_slug": "prestamos_bancarios_lp", "monto": "1000.00"},
                ],
            },
            "SET_OPENING_BALANCES",
        )
        exigir(
            d(r["data"]["contrapartida_capital"]) == Decimal("300.00"),
            f"capital de apertura inesperado: {r['data']}",
        )
        # Una segunda apertura debe rechazarse.
        await mutar(
            gate,
            actor,
            "SET_OPENING_BALANCES",
            {
                "fecha_corte": hoy.isoformat(),
                "saldos": [
                    {"account_slug": "caja_diaria_secretaria", "monto": "1.00"}
                ],
            },
            "SET_OPENING_BALANCES duplicado",
            esperado="REJECT",
        )
        print("4. SET_OPENING_BALANCES: OK")

        # ------------------------------------------------------------------
        # 5. CREATE_CONCRETE_ORDER + idempotencia
        # ------------------------------------------------------------------
        volumen = Decimal("10")
        total_neto = (d(receta["precio_m3"]) * volumen).quantize(Decimal("0.01"))
        iva_esperado = (total_neto * d(receta["iva_pct"]) / Decimal("100")).quantize(
            Decimal("0.01")
        )
        total_bruto = total_neto + iva_esperado

        solicitud_orden, r = await mutar(
            gate,
            actor,
            "CREATE_CONCRETE_ORDER",
            {
                "cliente_id": cliente_id,
                "planta_codigo": "PLANTA-COCA",
                "resistencia": "FC-210",
                "volumen_m3": str(volumen),
                "forma_pago": "FIADO",
                "notas": "Orden de prueba Custodio v4.3",
            },
            "CREATE_CONCRETE_ORDER",
        )
        orden1_id = r["data"]["orden_id"]
        exigir(
            d(r["data"]["subtotal"]) == total_neto,
            f"subtotal inesperado: {r['data']}",
        )
        exigir(
            d(r["data"]["iva_monto"]) == iva_esperado,
            f"IVA inesperado: {r['data']}",
        )
        exigir(
            d(r["data"]["total_con_iva"]) == total_bruto,
            f"total con IVA inesperado: {r['data']}",
        )
        exigir(
            r["data"]["cobro_inicial_id"] is None,
            "FIADO no debe generar COBRO inicial",
        )
        exigir(
            r["transaction_group_id"] is not None,
            "la venta FIADO debe tener asiento",
        )

        replay = await gate.mutar(solicitud_orden, actor)
        exigir(
            replay["status"] == "ACCEPT"
            and replay["data"]["orden_id"] == orden1_id,
            f"el replay no devolvio la misma orden: {replay}",
        )
        # Mismo request_id y mismo payload, pero otro actor: no puede repetir.
        ajeno = await gate.mutar(
            solicitud_orden, Actor("SUPERADMIN", f"otro-{uuid4()}")
        )
        exigir(
            ajeno["status"] == "REJECT"
            and "UNAUTHORIZED_ACTOR" in ajeno["rejection_codes"],
            f"actor distinto no rechazado: {ajeno}",
        )
        # Mismo request_id con payload distinto.
        alterada = json.loads(json.dumps(solicitud_orden))
        alterada["payload"]["volumen_m3"] = "11"
        choque = await gate.mutar(alterada, actor)
        exigir(
            choque["status"] == "REJECT"
            and "PAYLOAD_HASH_MISMATCH_ON_RETRY" in choque["rejection_codes"],
            f"hash distinto no rechazado: {choque}",
        )
        ledger_orden = await conn.fetch(
            """
            SELECT aa.slug, le.debe, le.haber
              FROM ledger_entries le
              JOIN accounting_accounts aa ON aa.id = le.account_id
             WHERE le.source_type = 'ORDER' AND le.source_id = $1
            """,
            orden1_id,
        )
        exigir(len(ledger_orden) == 3, f"asiento de venta con {len(ledger_orden)} lineas")
        exigir(
            sum(d(f["debe"]) for f in ledger_orden) == total_bruto,
            "el asiento de venta no cuadra",
        )
        print("5. CREATE_CONCRETE_ORDER + idempotencia: OK")

        # ------------------------------------------------------------------
        # 6. REGISTER_CLIENT_PAYMENT
        # ------------------------------------------------------------------
        _, r = await mutar(
            gate,
            actor,
            "REGISTER_CLIENT_PAYMENT",
            {
                "cliente_id": cliente_id,
                "order_id": orden1_id,
                "fecha": hoy.isoformat(),
                "metodo": "EFECTIVO",
                "bolsa": "CAJA_DIARIA",
                "monto": "100.00",
                "referencia": "REC-CUSTODIO-1",
            },
            "REGISTER_CLIENT_PAYMENT",
        )
        pago_cliente_id = r["data"]["payment_id"]
        exigir(
            await saldo_cuenta(conn, "cuentas_por_cobrar_clientes")
            == total_bruto - Decimal("100.00"),
            "la cartera del cliente no bajo con el cobro",
        )
        # Un cobro que supera el saldo debe rechazarse.
        await mutar(
            gate,
            actor,
            "REGISTER_CLIENT_PAYMENT",
            {
                "cliente_id": cliente_id,
                "order_id": orden1_id,
                "fecha": hoy.isoformat(),
                "metodo": "EFECTIVO",
                "bolsa": "CAJA_DIARIA",
                "monto": "99999.00",
            },
            "cobro por encima del saldo",
            esperado="REJECT",
        )
        print("6. REGISTER_CLIENT_PAYMENT: OK")

        # ------------------------------------------------------------------
        # 7. REGISTER_EXPENSE (con y sin comprobante)
        # ------------------------------------------------------------------
        await mutar(
            gate,
            actor,
            "REGISTER_EXPENSE",
            {
                "fecha": hoy.isoformat(),
                "account_slug": "materiales_oficina_papeleria",
                "metodo": "EFECTIVO",
                "bolsa": "CAJA_DIARIA",
                "monto": "10.00",
                "descripcion": "Gasto sin comprobante",
            },
            "gasto que exige comprobante",
            esperado="REJECT",
        )
        _, r = await mutar(
            gate,
            actor,
            "REGISTER_EXPENSE",
            {
                "fecha": hoy.isoformat(),
                "account_slug": "viaticos_peajes_caja_chica",
                "metodo": "EFECTIVO",
                "bolsa": "CAJA_DIARIA",
                "monto": "25.50",
                "descripcion": "Viaticos de prueba custodia",
            },
            "REGISTER_EXPENSE",
        )
        gasto_id = r["data"]["payment_id"]
        print("7. REGISTER_EXPENSE: OK")

        # ------------------------------------------------------------------
        # 8. REGISTER_PURCHASE + RECEIVE_PURCHASED_MATERIAL
        # ------------------------------------------------------------------
        stock_previo = d(cemento["stock_actual"])
        costo_previo = d(cemento["costo_unitario"])
        _, r = await mutar(
            gate,
            actor,
            "REGISTER_PURCHASE",
            {
                "supplier_id": supplier_id,
                "fecha_compra": hoy.isoformat(),
                "fecha_vencimiento": vencimiento.isoformat(),
                "modalidad_pago": "CREDITO_PROVEEDOR",
                "modo_recepcion": "EN_TRANSITO",
                "items": [
                    {
                        "material_id": cemento["id"],
                        "account_slug": "inventario_insumos_silos",
                        "descripcion": "Cemento de prueba",
                        "cantidad": "10",
                        "costo_unitario": "9.5000",
                    }
                ],
                "iva_monto": "0.00",
            },
            "REGISTER_PURCHASE credito",
        )
        compra_credito_id = r["data"]["purchase_id"]
        exigir(
            d(r["data"]["saldo_pendiente"]) == Decimal("95.00"),
            f"saldo de compra inesperado: {r['data']}",
        )
        item_id = await conn.fetchval(
            "SELECT id::text FROM purchase_items WHERE purchase_id = $1",
            compra_credito_id,
        )
        _, r = await mutar(
            gate,
            actor,
            "RECEIVE_PURCHASED_MATERIAL",
            {
                "purchase_item_id": item_id,
                "cantidad_recibida": "4",
                "guia_remision": "GUIA-CUSTODIO-1",
            },
            "recepcion parcial",
        )
        exigir(r["data"]["estado_recepcion"] == "PARCIAL", f"estado: {r['data']}")
        _, r = await mutar(
            gate,
            actor,
            "RECEIVE_PURCHASED_MATERIAL",
            {
                "purchase_item_id": item_id,
                "cantidad_recibida": "6",
                "guia_remision": "GUIA-CUSTODIO-2",
            },
            "recepcion completa",
        )
        exigir(r["data"]["estado_recepcion"] == "COMPLETA", f"estado: {r['data']}")
        material_tras_compra = await conn.fetchrow(
            "SELECT stock_actual, costo_unitario FROM materials WHERE id = $1",
            cemento["id"],
        )
        exigir(
            d(material_tras_compra["stock_actual"]) == stock_previo + Decimal("10"),
            "la recepcion no sumo 10 al stock",
        )
        costo_nuevo = d(material_tras_compra["costo_unitario"])
        exigir(
            min(costo_previo, Decimal("9.5")) <= costo_nuevo <= max(costo_previo, Decimal("9.5")),
            f"costo promedio fuera de rango: {costo_nuevo}",
        )
        exigir(
            await saldo_cuenta(conn, "inventario_insumos_silos")
            == Decimal("595.00"),
            "el inventario contable no coincide con la apertura + compra",
        )
        print("8. REGISTER_PURCHASE + RECEIVE_PURCHASED_MATERIAL: OK")

        # ------------------------------------------------------------------
        # 9. PAY_SUPPLIER_DEBT + correccion con testigo
        # ------------------------------------------------------------------
        _, r = await mutar(
            gate,
            actor,
            "PAY_SUPPLIER_DEBT",
            {
                "supplier_id": supplier_id,
                "purchase_id": compra_credito_id,
                "fecha": hoy.isoformat(),
                "metodo": "EFECTIVO",
                "bolsa": "CAJA_DIARIA",
                "monto": "40.00",
                "referencia": "PAGO-CUSTODIO-1",
            },
            "PAY_SUPPLIER_DEBT",
        )
        pago_proveedor_id = r["data"]["supplier_payment_id"]
        exigir(
            d(r["data"]["saldo_pendiente"]) == Decimal("55.00"),
            f"saldo tras pago: {r['data']}",
        )
        correccion = await testigo(
            gate,
            actor,
            "CORRECT_MOVEMENT_WITH_WITNESS",
            "supplier_payments",
            {"nuevo_monto": "30.00"},
            "correccion de pago a proveedor",
            target_record_id=pago_proveedor_id,
        )
        exigir(
            correccion["witness_id"] is not None,
            "la correccion no dejo testigo",
        )
        compra_corregida = await conn.fetchrow(
            "SELECT monto_pagado, saldo_pendiente FROM purchases WHERE id = $1",
            compra_credito_id,
        )
        exigir(
            d(compra_corregida["monto_pagado"]) == Decimal("30.00"),
            f"monto pagado no corregido: {compra_corregida}",
        )
        exigir(
            d(compra_corregida["saldo_pendiente"]) == Decimal("65.00"),
            f"saldo no recalculado: {compra_corregida}",
        )
        activos_pago = await conn.fetchval(
            """
            SELECT count(*)
              FROM ledger_entries le
             WHERE le.source_type = 'SUPPLIER_PAYMENT'
               AND le.source_id = $1
               AND le.is_reversal = false
               AND NOT EXISTS (
                    SELECT 1 FROM ledger_entries r
                     WHERE r.reverses_group_id = le.transaction_group_id
                       AND r.is_reversal = true
               )
            """,
            pago_proveedor_id,
        )
        exigir(activos_pago == 2, f"asiento vigente del pago con {activos_pago} lineas")
        print("9. PAY_SUPPLIER_DEBT + testigo: OK")

        # ------------------------------------------------------------------
        # 10. Correccion de una compra de servicio (una sola linea)
        # ------------------------------------------------------------------
        _, r = await mutar(
            gate,
            actor,
            "REGISTER_PURCHASE",
            {
                "supplier_id": supplier_id,
                "fecha_compra": hoy.isoformat(),
                "fecha_vencimiento": vencimiento.isoformat(),
                "modalidad_pago": "CREDITO_PROVEEDOR",
                "modo_recepcion": "NO_APLICA",
                "referencia_comprobante": "FACT-CUSTODIO-SERV",
                "items": [
                    {
                        "material_id": None,
                        "account_slug": "insumos_menores_no_inventariables",
                        "descripcion": "Servicio de prueba",
                        "cantidad": "1",
                        "costo_unitario": "50.0000",
                    }
                ],
                "iva_monto": "0.00",
            },
            "compra de servicio",
        )
        compra_servicio_id = r["data"]["purchase_id"]
        correccion = await testigo(
            gate,
            actor,
            "CORRECT_MOVEMENT_WITH_WITNESS",
            "purchases",
            {"nuevo_monto": "60.00"},
            "correccion de compra de servicio",
            target_record_id=compra_servicio_id,
        )
        exigir(correccion["witness_id"] is not None, "compra sin testigo")
        compra_servicio = await conn.fetchrow(
            "SELECT subtotal, monto_total FROM purchases WHERE id = $1",
            compra_servicio_id,
        )
        exigir(
            d(compra_servicio["subtotal"]) == Decimal("60.00")
            and d(compra_servicio["monto_total"]) == Decimal("60.00"),
            f"compra de servicio no corregida: {compra_servicio}",
        )
        print("10. Correccion de compra de servicio: OK")

        # ------------------------------------------------------------------
        # 11. RUN_MONTHLY_DEPRECIATION
        # ------------------------------------------------------------------
        periodo = hoy.strftime("%Y-%m")
        _, r = await mutar(
            gate,
            actor,
            "RUN_MONTHLY_DEPRECIATION",
            {"periodo_ym": periodo, "asset_id": asset_id},
            "depreciacion mensual",
        )
        exigir(len(r["data"]["cuotas"]) == 1, f"cuotas: {r['data']}")
        exigir(
            d(r["data"]["cuotas"][0]["cuota"]) == Decimal("100.00"),
            f"cuota inesperada: {r['data']}",
        )
        await mutar(
            gate,
            actor,
            "RUN_MONTHLY_DEPRECIATION",
            {"periodo_ym": periodo, "asset_id": asset_id},
            "depreciacion duplicada",
            esperado="REJECT",
        )
        print("11. RUN_MONTHLY_DEPRECIATION: OK")

        # ------------------------------------------------------------------
        # 12. PAY_BANK_LOAN_INSTALLMENT
        # ------------------------------------------------------------------
        _, r = await mutar(
            gate,
            actor,
            "PAY_BANK_LOAN_INSTALLMENT",
            {
                "liability_id": liability_id,
                "fecha": hoy.isoformat(),
                "bolsa": "BANCO_GERENCIA",
                "monto_capital": "100.00",
                "monto_interes": "10.00",
                "referencia": "CUOTA-CUSTODIO-1",
            },
            "cuota de prestamo",
        )
        exigir(
            d(r["data"]["saldo_capital_actual"]) == Decimal("900.00"),
            f"saldo del prestamo: {r['data']}",
        )
        print("12. PAY_BANK_LOAN_INSTALLMENT: OK")

        # ------------------------------------------------------------------
        # 13. CANCEL_CONCRETE_ORDER + RESOLVE_APPROVAL_REQUEST
        # ------------------------------------------------------------------
        _, r = await mutar(
            gate,
            actor,
            "CANCEL_CONCRETE_ORDER",
            {
                "order_id": orden1_id,
                "motivo": "Anulacion de prueba con cobro activo",
            },
            "cancelacion con cobro",
            esperado="PENDING_JULIO_APPROVAL",
        )
        aprobacion1 = r["approval_request_id"]
        exigir(aprobacion1 is not None, "aprobacion sin id")
        _, r = await mutar(
            gate,
            actor,
            "RESOLVE_APPROVAL_REQUEST",
            {
                "approval_request_id": aprobacion1,
                "decision": "APPROVED",
                "comentario": "Aprobado para probar la regla de reembolso",
            },
            "resolver anulacion con cobro",
        )
        exigir(
            r["data"]["ejecutada"] is False
            and r["data"]["motivo"] == "REFUND_RULE_NOT_CONFIRMED",
            f"se anulo una orden con cobros: {r['data']}",
        )
        estado_orden1 = await conn.fetchval(
            "SELECT estado FROM orders WHERE id = $1", orden1_id
        )
        exigir(estado_orden1 != "ANULADA", "la orden con cobro quedo anulada")

        # Orden nueva sin cobros: la anulacion si se ejecuta.
        _, r = await mutar(
            gate,
            actor,
            "CREATE_CONCRETE_ORDER",
            {
                "cliente_id": cliente_id,
                "planta_codigo": "PLANTA-COCA",
                "resistencia": "FC-180",
                "volumen_m3": "5",
                "forma_pago": "FIADO",
            },
            "orden para anular",
        )
        orden2_id = r["data"]["orden_id"]
        _, r = await mutar(
            gate,
            actor,
            "CANCEL_CONCRETE_ORDER",
            {
                "order_id": orden2_id,
                "motivo": "Anulacion de prueba sin cobros",
            },
            "cancelacion sin cobro",
            esperado="PENDING_JULIO_APPROVAL",
        )
        aprobacion2 = r["approval_request_id"]
        _, r = await mutar(
            gate,
            actor,
            "RESOLVE_APPROVAL_REQUEST",
            {
                "approval_request_id": aprobacion2,
                "decision": "APPROVED",
                "comentario": "Aprobado: no hay cobros que devolver",
            },
            "resolver anulacion sin cobro",
        )
        exigir(r["data"]["ejecutada"] is True, f"no se anulo: {r['data']}")
        exigir(
            r["data"]["movimientos_anulados"] >= 1,
            f"no se anularon consumos teoricos: {r['data']}",
        )
        estado_orden2 = await conn.fetchval(
            "SELECT estado FROM orders WHERE id = $1", orden2_id
        )
        exigir(estado_orden2 == "ANULADA", "la orden sin cobros no quedo anulada")
        print("13. CANCEL_CONCRETE_ORDER + aprobacion: OK")

        # ------------------------------------------------------------------
        # 14. Categorias contables: crear, duplicado, renombrar, fusionar
        # ------------------------------------------------------------------
        r = await testigo(
            gate,
            actor,
            "CREATE_ACCOUNTING_CATEGORY",
            "accounting_accounts",
            {
                "nuevo_nombre_categoria": f"{PREFIJO} Fletes",
                "account_type": "EXPENSE",
                "normal_balance": "DEBIT",
                "parent_group": "COSTO_DIRECTO",
                "default_bolsa": "BANCO_GERENCIA",
                "requires_voucher": True,
            },
            "crear categoria",
        )
        cuenta_fletes = r["data"]["account"]["id"]
        r = await testigo(
            gate,
            actor,
            "CREATE_ACCOUNTING_CATEGORY",
            "accounting_accounts",
            {
                "nuevo_nombre_categoria": f"{PREFIJO.lower()} fletes",
                "account_type": "EXPENSE",
                "normal_balance": "DEBIT",
                "parent_group": "COSTO_DIRECTO",
                "default_bolsa": "BANCO_GERENCIA",
                "requires_voucher": True,
            },
            "categoria duplicada",
            esperado="REJECT",
        )
        exigir(
            "DUPLICATE_CATEGORY_SIMILARITY" in r["rejection_codes"],
            f"duplicado no detectado: {r}",
        )
        r = await testigo(
            gate,
            actor,
            "CREATE_ACCOUNTING_CATEGORY",
            "accounting_accounts",
            {
                "nuevo_nombre_categoria": f"{PREFIJO} Fletes locales",
                "account_type": "EXPENSE",
                "normal_balance": "DEBIT",
                "parent_group": "COSTO_DIRECTO",
                "default_bolsa": "CAJA_DIARIA",
                "requires_voucher": False,
            },
            "crear segunda categoria",
        )
        cuenta_locales = r["data"]["account"]["id"]
        await testigo(
            gate,
            actor,
            "RENAME_ACCOUNTING_CATEGORY",
            "accounting_accounts",
            {"nuevo_nombre_categoria": f"{PREFIJO} Fletes y transporte"},
            "renombrar categoria",
            target_record_id=cuenta_fletes,
        )
        r = await testigo(
            gate,
            actor,
            "MERGE_ACCOUNTING_CATEGORIES",
            "accounting_accounts",
            {
                "source_account_id": cuenta_locales,
                "target_account_id": cuenta_fletes,
            },
            "fusionar categorias",
        )
        exigir(
            r["data"]["resultado"]["merged_into_id"] == cuenta_fletes,
            f"fusion no aplicada: {r['data']}",
        )
        caja_id = await conn.fetchval(
            "SELECT id::text FROM accounting_accounts WHERE slug = 'caja_diaria_secretaria'"
        )
        r = await testigo(
            gate,
            actor,
            "MERGE_ACCOUNTING_CATEGORIES",
            "accounting_accounts",
            {
                "source_account_id": caja_id,
                "target_account_id": cuenta_fletes,
            },
            "fusionar cuenta base",
            esperado="REJECT",
        )
        exigir(
            "IMMUTABLE_ROOT_ACCOUNT" in r["rejection_codes"],
            f"cuenta base fusionada: {r}",
        )
        print("14. Categorias contables: OK")

        # ------------------------------------------------------------------
        # 15. Autorizacion por rol
        # ------------------------------------------------------------------
        r = await gate.mutar(
            solicitud_mutacion(
                "REGISTER_EXPENSE",
                {
                    "fecha": hoy.isoformat(),
                    "account_slug": "viaticos_peajes_caja_chica",
                    "metodo": "EFECTIVO",
                    "bolsa": "CAJA_DIARIA",
                    "monto": "1.00",
                    "descripcion": "Gasto no autorizado",
                },
                bodega,
            ),
            bodega,
        )
        exigir(
            r["status"] == "REJECT"
            and "UNAUTHORIZED_DOMAIN_ACCESS" in r["rejection_codes"],
            f"bodega pudo registrar un gasto: {r}",
        )
        r = await gate.mutar(
            {
                **solicitud_mutacion(
                    "RUN_MONTHLY_DEPRECIATION",
                    {"periodo_ym": periodo},
                    cron,
                ),
                "channel": "WEB_PANEL",
            },
            cron,
        )
        exigir(
            r["status"] == "REJECT"
            and "UNAUTHORIZED_ACTOR" in r["rejection_codes"],
            f"cron pudo entrar por panel: {r}",
        )
        print("15. Autorizacion por rol: OK")

        # ------------------------------------------------------------------
        # 16. Las nueve consultas
        # ------------------------------------------------------------------
        r = await consultar(
            gate,
            actor,
            "GET_CLIENT_BALANCE",
            {"cliente_id": cliente_id},
            "GET_CLIENT_BALANCE",
        )
        exigir(
            d(r["data"]["cliente"]["saldo_pendiente"]) == total_bruto - Decimal("100.00"),
            f"saldo del cliente: {r['data']['cliente']}",
        )
        exigir(
            d(r["data"]["cliente"]["total_cobrado"]) == Decimal("100.00"),
            f"cobrado del cliente: {r['data']['cliente']}",
        )

        r = await consultar(
            gate,
            actor,
            "GET_DAILY_CASH_CLOSURE",
            {"fecha_desde": hoy.isoformat()},
            "GET_DAILY_CASH_CLOSURE",
        )
        exigir(
            d(r["data"]["cobros"]["efectivo"]) == Decimal("100.00"),
            f"cobros del dia: {r['data']}",
        )
        exigir(
            d(r["data"]["caja_chica"]) == Decimal("25.50"),
            f"caja chica: {r['data']}",
        )
        exigir(
            d(r["data"]["efectivo_sistema"]) == Decimal("74.50"),
            f"efectivo del dia: {r['data']}",
        )

        r = await consultar(
            gate,
            actor,
            "GET_ACCOUNTS_PAYABLE",
            {"supplier_id": supplier_id},
            "GET_ACCOUNTS_PAYABLE",
        )
        exigir(r["data"]["cantidad"] == 2, f"por pagar: {r['data']}")
        exigir(
            d(r["data"]["total"]) == Decimal("125.00"),
            f"total por pagar: {r['data']}",
        )

        r = await consultar(
            gate,
            actor,
            "GET_INVENTORY_AND_ALERTS",
            {},
            "GET_INVENTORY_AND_ALERTS",
        )
        cemento_vista = next(
            m for m in r["data"]["materiales"] if m["codigo"] == "CEMENTO"
        )
        exigir(
            d(cemento_vista["stock_real_fisico"]) == stock_previo + Decimal("10"),
            f"stock proyectado: {cemento_vista}",
        )
        exigir(
            "PENDING_PHYSICAL_INVENTORY_RECONCILIATION" in r["residual_risks"],
            "falta el riesgo de conteo fisico",
        )

        r = await consultar(
            gate,
            actor,
            "GET_DISPATCH_TIMELINE",
            {"order_id": orden1_id},
            "GET_DISPATCH_TIMELINE",
        )
        exigir(len(r["data"]["despachos"]) >= 1, "la orden no tiene despachos")

        desde = hoy.replace(day=1)
        r = await consultar(
            gate,
            actor,
            "GET_INCOME_STATEMENT_PL",
            {"fecha_desde": desde.isoformat(), "fecha_hasta": hoy.isoformat()},
            "GET_INCOME_STATEMENT_PL",
        )
        exigir(
            d(r["data"]["ingresos"]) == total_neto,
            f"ingresos del mes: {r['data']}",
        )
        exigir(
            d(r["data"]["gastos"]) == Decimal("195.50"),
            f"gastos del mes: {r['data']}",
        )
        exigir(
            d(r["data"]["resultado"]) == total_neto - Decimal("195.50"),
            f"resultado del mes: {r['data']}",
        )

        r = await consultar(
            gate,
            actor,
            "GET_BALANCE_SHEET_REALTIME",
            {},
            "GET_BALANCE_SHEET_REALTIME",
        )
        exigir(
            d(r["data"]["descuadre"]) == Decimal("0.00"),
            f"balance descuadrado: {r['data']}",
        )
        exigir(
            d(r["data"]["activo"]) == Decimal("2686.50"),
            f"activo inesperado: {r['data']}",
        )
        exigir(
            d(r["data"]["pasivo"]) == Decimal("1402.00"),
            f"pasivo inesperado: {r['data']}",
        )
        exigir(
            d(r["data"]["patrimonio"]) == Decimal("300.00"),
            f"patrimonio inesperado: {r['data']}",
        )
        exigir(
            d(r["data"]["resultado_ejercicio"]) == total_neto - Decimal("195.50"),
            f"resultado del ejercicio: {r['data']}",
        )

        r = await consultar(
            gate,
            actor,
            "GET_VALUATION_AND_10Y_PROJECTION",
            {"horizon_years": 10},
            "GET_VALUATION_AND_10Y_PROJECTION",
        )
        exigir(
            r["data"]["estado"] == "PENDIENTE"
            and "VALUATION_FORMULA_NOT_CONFIRMED" in r["residual_risks"],
            f"valoracion inventada: {r}",
        )

        r = await consultar(
            gate,
            actor,
            "GET_DEBT_CAPACITY_DSCR",
            {"horizon_years": 10},
            "GET_DEBT_CAPACITY_DSCR",
        )
        exigir(
            r["data"]["estado"] == "PENDIENTE"
            and "DSCR_DEFINITION_NOT_CONFIRMED" in r["residual_risks"],
            f"DSCR inventado: {r}",
        )
        print("16. Las nueve consultas: OK")

        # ------------------------------------------------------------------
        # Cierre del escenario
        # ------------------------------------------------------------------
        mut = ESTADISTICAS["mutaciones"]
        test = ESTADISTICAS["testigos"]
        print(
            "CUSTODIO V4.3: OK | "
            f"{len(ESTADISTICAS['intents'])}/14 intents de mutacion, "
            f"{sum(mut.values())} solicitudes "
            f"({mut.get('ACCEPT', 0)} ACCEPT, {mut.get('REJECT', 0)} REJECT, "
            f"{mut.get('PENDING_JULIO_APPROVAL', 0)} PENDING), "
            f"{sum(test.values())} testigos "
            f"({test.get('ACCEPT', 0)} ACCEPT/{test.get('REJECT', 0)} REJECT), "
            f"{ESTADISTICAS['aprobaciones']} aprobaciones, 9 consultas"
        )
        print("Transaccion de prueba: se revierte con ROLLBACK.")
        return 0
    finally:
        await transaccion.rollback()
        despues = {
            tabla: await conn.fetchval(f"SELECT count(*) FROM {tabla}")
            for tabla in tablas
        }
        if despues != antes:
            print("ADVERTENCIA: el ROLLBACK dejo diferencias de conteo.")
            for tabla in tablas:
                if antes[tabla] != despues[tabla]:
                    print(f"  {tabla}: antes={antes[tabla]} despues={despues[tabla]}")
        else:
            print("ROLLBACK verificado: 17 tablas con el mismo conteo que antes.")
        await conn.close()


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as exc:
        print(f"CUSTODIO V4.3: FALLO -> {exc}")
        sys.exit(1)
