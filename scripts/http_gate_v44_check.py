"""Verificacion HTTP v4.4.0 contra el clon orminorth_v43.

Levanta la app FastAPI en memoria (ASGITransport), apunta el pool a una unica
conexion con transaccion externa y prueba los endpoints oficiales:

- GET  /api/v1/custodio/catalog
- POST /api/v1/custodio/mutations
- POST /api/v1/custodio/queries
- POST /api/v1/secretaria/pagos (COBRO, anticipo, gasto, idempotencia)

Al terminar hace ROLLBACK: no queda ningun dato de prueba. Se niega a correr
contra la base real ``orminorth``.

Uso:
    docker compose run --rm --no-deps \
      -e DATABASE_URL=postgresql://orminorth:orminorth@postgres:5432/orminorth_v43 \
      core-api python scripts/http_gate_v44_check.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import _path  # noqa: F401

import asyncpg
import httpx
from fastapi import FastAPI

from app.custodio import Gate
from app.http_gate import custodio_router, payments_router
from app.settings import get_settings

TAG = "HTTP-V44-CHECK"
PREFIJO = "HTTP V44 CHECK"

TOKENS = SimpleNamespace(
    custodio_token_superadmin="check-superadmin",
    custodio_token_contadora="check-contadora",
    custodio_token_secretaria="check-secretaria",
    custodio_token_bodega="check-bodega",
    custodio_token_chofer="check-chofer",
    custodio_token_system_cron="check-cron",
    custodio_allow_dev_header=False,
    gate_api_key="",
)


class PoolDeUnaConexion:
    """Adapta una conexion con transaccion abierta a la interfaz de pool."""

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


def _headers(rol: str, *, actor: str | None = None) -> dict[str, str]:
    token = {
        "SUPERADMIN": TOKENS.custodio_token_superadmin,
        "CONTADORA": TOKENS.custodio_token_contadora,
        "SECRETARIA": TOKENS.custodio_token_secretaria,
        "BODEGA": TOKENS.custodio_token_bodega,
        "CHOFER": TOKENS.custodio_token_chofer,
        "SYSTEM_CRON": TOKENS.custodio_token_system_cron,
    }[rol]
    return {
        "X-Actor-Token": token,
        "X-Actor-Id": actor or f"{rol}_CHECK",
        "X-Channel": "SYSTEM_CRON" if rol == "SYSTEM_CRON" else "WEB_PANEL",
    }


async def main() -> int:
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
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
        app = FastAPI()
        app.state.pool = pool
        app.state.settings = TOKENS
        app.state.gate_factory = lambda p: Gate(p)
        app.include_router(custodio_router)
        app.include_router(payments_router)

        transporte = httpx.ASGITransport(app=app)
        cliente_http = httpx.AsyncClient(
            transport=transporte, base_url="http://test"
        )

        hoy: date = await conn.fetchval("SELECT CURRENT_DATE")
        cliente_id = await conn.fetchval(
            """
            INSERT INTO clients (nombre, estado, credit_limit_usd)
            VALUES ($1, 'ACTIVO', 100000.00)
            RETURNING id::text
            """,
            f"{PREFIJO} Cliente",
        )
        cliente_anticipo = await conn.fetchval(
            """
            INSERT INTO clients (nombre, estado)
            VALUES ($1, 'ACTIVO')
            RETURNING id::text
            """,
            f"{PREFIJO} Anticipo",
        )

        # 1. Auth
        r = await cliente_http.get("/api/v1/custodio/catalog")
        exigir(r.status_code == 401, f"sin token no dio 401: {r.status_code}")
        r = await cliente_http.get(
            "/api/v1/custodio/catalog",
            headers={"X-Actor-Token": "invalido", "X-Actor-Id": "x"},
        )
        exigir(r.status_code == 401, f"token invalido no dio 401: {r.status_code}")
        print("1. Auth: sin token y token invalido -> 401: OK")

        # 2. Catalogo
        r = await cliente_http.get(
            "/api/v1/custodio/catalog", headers=_headers("SUPERADMIN")
        )
        exigir(r.status_code == 200, f"catalogo fallo: {r.text}")
        cuentas = r.json()["cuentas"]
        exigir(len(cuentas) >= 26, f"catalogo incompleto: {len(cuentas)}")
        print(f"2. GET /custodio/catalog: {len(cuentas)} cuentas: OK")

        # 3. Mutacion: crear orden
        request_orden = str(uuid4())
        r = await cliente_http.post(
            "/api/v1/custodio/mutations",
            headers=_headers("SECRETARIA", actor="secretaria-http"),
            json={
                "contract_version": "1.3.0",
                "request_id": request_orden,
                "channel": "WEB_PANEL",
                "intent": "CREATE_CONCRETE_ORDER",
                "payload": {
                    "cliente_id": cliente_id,
                    "planta_codigo": "PLANTA-COCA",
                    "resistencia": "FC-210",
                    "volumen_m3": "2",
                    "forma_pago": "FIADO",
                    "aplica_iva": True,
                    "notas": f"{PREFIJO} orden HTTP",
                },
            },
        )
        exigir(r.status_code == 200, f"mutacion fallo: {r.status_code} {r.text}")
        orden_id = r.json()["data"]["orden_id"]
        print("3. POST /custodio/mutations (orden): OK")

        # 4. Consulta
        r = await cliente_http.post(
            "/api/v1/custodio/queries",
            headers=_headers("SECRETARIA", actor="secretaria-http"),
            json={
                "contract_version": "1.3.0",
                "request_id": str(uuid4()),
                "channel": "WEB_PANEL",
                "intent": "GET_CLIENT_BALANCE",
                "filters": {"cliente_id": cliente_id},
            },
        )
        exigir(r.status_code == 200, f"consulta fallo: {r.status_code} {r.text}")
        print("4. POST /custodio/queries (saldo): OK")

        # 5. Pago COBRO
        pago_body = {
            "request_id": str(uuid4()),
            "tipo_movimiento": "COBRO",
            "cliente_id": cliente_id,
            "order_id": orden_id,
            "fecha": hoy.isoformat(),
            "metodo": "EFECTIVO",
            "bolsa": "CAJA_DIARIA",
            "monto": "100.00",
            "referencia": "HTTP-COBRO-1",
        }
        r = await cliente_http.post(
            "/api/v1/secretaria/pagos",
            headers=_headers("SECRETARIA", actor="secretaria-http"),
            json=pago_body,
        )
        exigir(r.status_code == 201, f"cobro fallo: {r.status_code} {r.text}")
        data = r.json()["data"]
        exigir(d(data["parte_cxc"]) == Decimal("100.00"), f"parte_cxc: {data}")
        exigir(d(data["parte_anticipo"]) == Decimal("0.00"), f"anticipo: {data}")
        print("5. POST /secretaria/pagos (COBRO parcial): OK")

        # 6. Reintento idempotente y choque de hash
        r = await cliente_http.post(
            "/api/v1/secretaria/pagos",
            headers=_headers("SECRETARIA", actor="secretaria-http"),
            json=pago_body,
        )
        exigir(r.status_code == 200, f"replay no dio 200: {r.status_code}")
        alterado = json.loads(json.dumps(pago_body))
        alterado["monto"] = "90.00"
        r = await cliente_http.post(
            "/api/v1/secretaria/pagos",
            headers=_headers("SECRETARIA", actor="secretaria-http"),
            json=alterado,
        )
        exigir(r.status_code == 409, f"hash distinto no dio 409: {r.status_code}")
        print("6. Idempotencia HTTP (200 replay / 409 hash): OK")

        # 7. Pago que supera saldo sin anticipo
        r = await cliente_http.post(
            "/api/v1/secretaria/pagos",
            headers=_headers("SECRETARIA", actor="secretaria-http"),
            json={
                "request_id": str(uuid4()),
                "tipo_movimiento": "COBRO",
                "cliente_id": cliente_anticipo,
                "fecha": hoy.isoformat(),
                "metodo": "EFECTIVO",
                "bolsa": "CAJA_DIARIA",
                "monto": "50.00",
                "es_anticipo": False,
            },
        )
        exigir(r.status_code == 422, f"sobrepago no dio 422: {r.status_code}")
        exigir(
            "PAYMENT_EXCEEDS_PENDING_BALANCE" in r.json()["rejection_codes"],
            f"codigo inesperado: {r.text}",
        )
        print("7. Sobrepago sin anticipo -> PAYMENT_EXCEEDS_PENDING_BALANCE: OK")

        # 8. Anticipo
        r = await cliente_http.post(
            "/api/v1/secretaria/pagos",
            headers=_headers("SECRETARIA", actor="secretaria-http"),
            json={
                "request_id": str(uuid4()),
                "tipo_movimiento": "COBRO",
                "cliente_id": cliente_anticipo,
                "fecha": hoy.isoformat(),
                "metodo": "EFECTIVO",
                "bolsa": "CAJA_DIARIA",
                "monto": "200.00",
                "es_anticipo": True,
            },
        )
        exigir(r.status_code == 201, f"anticipo fallo: {r.status_code} {r.text}")
        data = r.json()["data"]
        exigir(d(data["parte_cxc"]) == Decimal("0.00"), f"anticipo cxc: {data}")
        exigir(
            d(data["parte_anticipo"]) == Decimal("200.00"),
            f"anticipo excedente: {data}",
        )
        exigir(
            d(data["saldo_a_favor"]) == Decimal("200.00"),
            f"saldo a favor: {data}",
        )
        print("8. Anticipo -> 2102 y saldo_a_favor: OK")

        # 9. Gasto
        r = await cliente_http.post(
            "/api/v1/secretaria/pagos",
            headers=_headers("SECRETARIA", actor="secretaria-http"),
            json={
                "request_id": str(uuid4()),
                "tipo_movimiento": "GASTO_CAJA_CHICA",
                "fecha": hoy.isoformat(),
                "metodo": "EFECTIVO",
                "bolsa": "CAJA_DIARIA",
                "monto": "5.00",
                "account_slug": "viaticos_peajes_caja_chica",
                "descripcion": f"{PREFIJO} gasto HTTP",
            },
        )
        exigir(r.status_code == 201, f"gasto fallo: {r.status_code} {r.text}")
        print("9. POST /secretaria/pagos (GASTO_CAJA_CHICA): OK")

        # 10. Rol sin permiso
        r = await cliente_http.post(
            "/api/v1/secretaria/pagos",
            headers=_headers("BODEGA"),
            json={
                "request_id": str(uuid4()),
                "tipo_movimiento": "COBRO",
                "cliente_id": cliente_id,
                "fecha": hoy.isoformat(),
                "metodo": "EFECTIVO",
                "monto": "1.00",
            },
        )
        exigir(r.status_code == 403, f"bodega pudo cobrar: {r.status_code}")
        print("10. BODEGA no registra pagos -> 403: OK")

        await cliente_http.aclose()
        print(
            "HTTP GATE V4.4: OK | catalog, mutations, queries, pagos, "
            "anticipo, gasto, idempotencia y roles"
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
        print(f"HTTP GATE V4.4: FALLO -> {exc}")
        sys.exit(1)
