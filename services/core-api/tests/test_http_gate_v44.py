"""Tests HTTP v4.4.0: autenticacion de servicio, pagos y router del Gate.

No tocan PostgreSQL. La integracion real se verifica con
``scripts/http_gate_v44_check.py`` contra el clon y con ROLLBACK.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.http_gate.payments import router as payments_router  # noqa: E402
from app.http_gate.router import router as custodio_router  # noqa: E402

CLAVE = "test-gate-key"


class _FakeConn:
    def __init__(self, existe: bool = False) -> None:
        self.existe = existe

    async def fetchval(self, *args, **kwargs):
        return 1 if self.existe else None


class _FakePool:
    def __init__(self, existe: bool = False) -> None:
        self.existe = existe

    def acquire(self):
        conn = _FakeConn(self.existe)

        @asynccontextmanager
        async def _ctx():
            yield conn

        return _ctx()


class _FakeGate:
    def __init__(self, respuesta: dict, pool=None) -> None:
        self.respuesta = respuesta
        self.pool = pool
        self.solicitudes: list[dict] = []
        self.actores: list[object] = []

    async def mutar(self, solicitud, actor):
        self.solicitudes.append(dict(solicitud))
        self.actores.append(actor)
        return self.respuesta

    async def consultar(self, solicitud, actor):
        return await self.mutar(solicitud, actor)

    async def testigo(self, solicitud, actor):
        return await self.mutar(solicitud, actor)


def _respuesta(status: str = "ACCEPT", **extra) -> dict:
    base = {
        "contract_version": "1.3.0",
        "request_id": str(uuid4()),
        "status": status,
        "rejection_codes": [],
        "residual_risks": [],
        "witness_id": None,
        "transaction_group_id": None,
        "approval_request_id": None,
        "data": {},
    }
    base.update(extra)
    return base


def _app(respuesta: dict | None = None, *, clave: str = CLAVE, pool=None) -> FastAPI:
    app = FastAPI()
    app.state.settings = SimpleNamespace(gate_api_key=clave)
    fake = _FakeGate(respuesta or _respuesta(), pool=pool)
    app.state.gate_factory = lambda _pool: fake
    app.state.fake_gate = fake
    app.include_router(custodio_router)
    app.include_router(payments_router)
    return app


def _headers(
    *,
    clave: str = CLAVE,
    rol: str = "CAJA_SECRETARIA",
    actor: str = "secretaria-01",
    canal: str = "WEB_PANEL",
) -> dict[str, str]:
    return {
        "X-Gate-Key": clave,
        "X-Actor-Role": rol,
        "X-Actor-Id": actor,
        "X-Channel": canal,
    }


def _pago(**extra) -> dict:
    datos = {
        "request_id": str(uuid4()),
        "cliente_id": str(uuid4()),
        "order_id": str(uuid4()),
        "fecha": date(2026, 11, 9).isoformat(),
        "metodo": "EFECTIVO",
        "bolsa": "CAJA_DIARIA",
        "monto": "100.00",
        "referencia": "REC-001",
        "es_anticipo": False,
    }
    datos.update(extra)
    return datos


async def _post(app: FastAPI, ruta: str, body: dict, **kwargs):
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as client:
        return await client.post(ruta, json=body, **kwargs)


# ---------------------------------------------------------------------------
# Autenticacion
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sin_clave_configurada_falla_cerrado() -> None:
    r = await _post(_app(clave=""), "/api/v1/secretaria/pagos", _pago(), headers=_headers())
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "GATE_AUTH_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_clave_invalida_401() -> None:
    r = await _post(
        _app(),
        "/api/v1/secretaria/pagos",
        _pago(),
        headers=_headers(clave="otra"),
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "UNAUTHORIZED_ACTOR"


@pytest.mark.asyncio
async def test_rol_no_permitido_403() -> None:
    r = await _post(
        _app(),
        "/api/v1/secretaria/pagos",
        _pago(),
        headers=_headers(rol="BODEGA_PLANTA"),
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "UNAUTHORIZED_DOMAIN_ACCESS"


@pytest.mark.asyncio
async def test_system_cron_no_registra_pagos() -> None:
    r = await _post(
        _app(),
        "/api/v1/secretaria/pagos",
        _pago(),
        headers=_headers(rol="SYSTEM_CRON", canal="SYSTEM_CRON"),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_actor_sin_id_usa_default() -> None:
    app = _app()
    r = await _post(
        app,
        "/api/v1/secretaria/pagos",
        _pago(),
        headers=_headers(actor="   "),
    )
    assert r.status_code == 201
    assert app.state.fake_gate.actores[0].id == "CAJA_SECRETARIA_DEFAULT"


# ---------------------------------------------------------------------------
# Pagos
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pago_aceptado_201_y_contrato_correcto() -> None:
    respuesta = _respuesta(
        data={"payment_id": str(uuid4()), "saldo_pendiente": 55043.6}
    )
    app = _app(respuesta)
    body = _pago()
    r = await _post(app, "/api/v1/secretaria/pagos", body, headers=_headers())
    assert r.status_code == 201
    assert r.json()["status"] == "ACCEPT"
    assert r.json()["data"]["payment_id"] == respuesta["data"]["payment_id"]
    solicitud = app.state.fake_gate.solicitudes[0]
    assert solicitud["intent"] == "REGISTER_CLIENT_PAYMENT"
    assert solicitud["channel"] == "WEB_PANEL"
    assert solicitud["payload"]["monto"] == "100.00"
    assert solicitud["payload"]["cliente_id"] == body["cliente_id"]


@pytest.mark.asyncio
async def test_pago_sin_idempotencia_genera_request_id() -> None:
    body = _pago()
    body.pop("request_id")
    r = await _post(_app(), "/api/v1/secretaria/pagos", body, headers=_headers())
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_pago_con_idempotency_header() -> None:
    body = _pago()
    body.pop("request_id")
    clave = str(uuid4())
    r = await _post(
        _app(),
        "/api/v1/secretaria/pagos",
        body,
        headers={**_headers(), "Idempotency-Key": clave},
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_pago_request_id_y_header_distintos_422() -> None:
    r = await _post(
        _app(),
        "/api/v1/secretaria/pagos",
        _pago(),
        headers={**_headers(), "Idempotency-Key": str(uuid4())},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "IDEMPOTENCY_KEY_MISMATCH"


@pytest.mark.asyncio
async def test_pago_reintento_devuelve_200() -> None:
    r = await _post(
        _app(pool=_FakePool(existe=True)),
        "/api/v1/secretaria/pagos",
        _pago(),
        headers=_headers(),
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_pago_rechazo_422() -> None:
    respuesta = _respuesta(
        "REJECT",
        rejection_codes=["MISSING_VOUCHER_REFERENCE"],
        data={"errores": ["falta referencia"]},
    )
    r = await _post(
        _app(respuesta),
        "/api/v1/secretaria/pagos",
        _pago(),
        headers=_headers(),
    )
    assert r.status_code == 422
    assert r.json()["rejection_codes"] == ["MISSING_VOUCHER_REFERENCE"]


@pytest.mark.asyncio
async def test_pago_monto_con_tres_decimales_422() -> None:
    r = await _post(
        _app(),
        "/api/v1/secretaria/pagos",
        _pago(monto="100.001"),
        headers=_headers(),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_pago_monto_negativo_422() -> None:
    r = await _post(
        _app(),
        "/api/v1/secretaria/pagos",
        _pago(monto="-1.00"),
        headers=_headers(),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_pago_anticipo_se_envia_al_gate() -> None:
    app = _app()
    body = _pago(es_anticipo=True, order_id=None)
    r = await _post(app, "/api/v1/secretaria/pagos", body, headers=_headers())
    assert r.status_code == 201
    payload = app.state.fake_gate.solicitudes[0]["payload"]
    assert payload["es_anticipo"] is True
    assert "order_id" not in payload


# ---------------------------------------------------------------------------
# Router del Gate
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mutacion_accept_200() -> None:
    app = _app()
    body = {
        "contract_version": "1.3.0",
        "request_id": str(uuid4()),
        "channel": "WEB_PANEL",
        "intent": "CREATE_SUPPLIER",
        "payload": {"nombre": "Proveedor de prueba"},
    }
    r = await _post(app, "/api/v1/custodio/mutaciones", body, headers=_headers(rol="SUPERADMIN"))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_mutacion_canal_distinto_422() -> None:
    body = {
        "contract_version": "1.3.0",
        "request_id": str(uuid4()),
        "channel": "SYSTEM_CRON",
        "intent": "CREATE_SUPPLIER",
        "payload": {"nombre": "Proveedor de prueba"},
    }
    r = await _post(
        _app(),
        "/api/v1/custodio/mutaciones",
        body,
        headers=_headers(rol="SUPERADMIN"),
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "CHANNEL_MISMATCH"


@pytest.mark.asyncio
async def test_hash_mismatch_409() -> None:
    respuesta = _respuesta(
        "REJECT", rejection_codes=["PAYLOAD_HASH_MISMATCH_ON_RETRY"]
    )
    body = {
        "contract_version": "1.3.0",
        "request_id": str(uuid4()),
        "channel": "WEB_PANEL",
        "intent": "CREATE_SUPPLIER",
        "payload": {"nombre": "Proveedor de prueba"},
    }
    r = await _post(
        _app(respuesta),
        "/api/v1/custodio/mutaciones",
        body,
        headers=_headers(rol="SUPERADMIN"),
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_pending_202() -> None:
    respuesta = _respuesta("PENDING_JULIO_APPROVAL", approval_request_id=str(uuid4()))
    body = {
        "contract_version": "1.3.0",
        "request_id": str(uuid4()),
        "channel": "WEB_PANEL",
        "intent": "CANCEL_CONCRETE_ORDER",
        "payload": {"order_id": str(uuid4()), "motivo": "Anulacion de prueba"},
    }
    r = await _post(
        _app(respuesta),
        "/api/v1/custodio/mutaciones",
        body,
        headers=_headers(rol="SUPERADMIN"),
    )
    assert r.status_code == 202


@pytest.mark.asyncio
async def test_testigo_accept_200() -> None:
    app = _app()
    body = {
        "contract_version": "1.3.0",
        "request_id": str(uuid4()),
        "channel": "WEB_PANEL",
        "intent": "CREATE_ACCOUNTING_CATEGORY",
        "target_table": "accounting_accounts",
        "motivo": "Correccion de prueba con motivo",
        "changes": {"nuevo_nombre_categoria": "Fletes"},
    }
    r = await _post(app, "/api/v1/custodio/testigos", body, headers=_headers(rol="SUPERADMIN"))
    assert r.status_code == 200
    assert app.state.fake_gate.solicitudes[0]["intent"] == "CREATE_ACCOUNTING_CATEGORY"
