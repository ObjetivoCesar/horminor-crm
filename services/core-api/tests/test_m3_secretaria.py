"""Tests del Modulo 3 - Secretaria y Cierre de Caja.

Todo sin infraestructura: el ``MemorySecretariaStore`` reproduce las vistas de
PostgreSQL y el alta de ordenes se inyecta con un doble.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.m3_secretaria.router import router as secretaria_router  # noqa: E402
from app.m3_secretaria.service import (  # noqa: E402
    MemorySecretariaStore,
    calcular_resumen_caja,
)
from app.services.ordenes import ResultadoOrden  # noqa: E402


def _app(store: MemorySecretariaStore, creador=None) -> FastAPI:
    app = FastAPI()
    app.state.secretaria_store = store
    app.state.crear_orden_fn = creador
    app.include_router(secretaria_router)
    return app


# ---------------------------------------------------------------------------
# Calculo puro
# ---------------------------------------------------------------------------
def test_resumen_caja_suma_ventas_cobros_y_gastos() -> None:
    resumen = calcular_resumen_caja(
        fecha=date(2026, 11, 8),
        ordenes=[
            {"forma_pago": "FIADO", "total": "6136.00"},
            {"forma_pago": "EFECTIVO", "total": "472.00"},
            {"forma_pago": "ANULADA", "total": "999.00"},
        ],
        movimientos=[
            {
                "id": "p1",
                "tipo_movimiento": "COBRO",
                "metodo": "EFECTIVO",
                "monto": "500.00",
            },
            {
                "id": "p2",
                "tipo_movimiento": "COBRO",
                "metodo": "TRANSFERENCIA",
                "monto": "2832.00",
            },
            {
                "id": "p3",
                "tipo_movimiento": "GASTO_CAJA_CHICA",
                "metodo": "EFECTIVO",
                "monto": "25.00",
            },
        ],
        efectivo_contado=Decimal("475.00"),
    )

    assert resumen["ventas"]["fiado"] == 6136.0
    assert resumen["ventas"]["efectivo"] == 472.0
    assert resumen["cobros"]["efectivo"] == 500.0
    assert resumen["cobros"]["transferencia"] == 2832.0
    assert resumen["caja_chica"] == 25.0
    assert resumen["efectivo_sistema"] == 475.0
    assert resumen["diferencia"] == 0.0
    assert len(resumen["detalle"]) == 3


def test_resumen_caja_usa_el_total_con_iva_cuando_existe() -> None:
    resumen = calcular_resumen_caja(
        fecha=date(2026, 11, 9),
        ordenes=[
            {
                "forma_pago": "EFECTIVO",
                "total": "100.00",
                "total_con_iva": "115.00",
            },
            {"forma_pago": "FIADO", "total": "200.00"},
        ],
        movimientos=[],
    )

    assert resumen["ventas"]["efectivo"] == 115.0
    # Historico sin total_con_iva: conserva el neto, no se inventa IVA.
    assert resumen["ventas"]["fiado"] == 200.0


def test_resumen_caja_sin_contado_no_inventa_diferencia() -> None:
    resumen = calcular_resumen_caja(
        fecha=date(2026, 11, 8), ordenes=[], movimientos=[]
    )
    assert resumen["efectivo_contado"] is None
    assert resumen["diferencia"] is None
    assert resumen["efectivo_sistema"] == 0.0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_listar_clientes_y_carpeta_forense() -> None:
    store = MemorySecretariaStore()
    transporte = httpx.ASGITransport(app=_app(store))
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as cliente:
        listado = await cliente.get("/api/v1/secretaria/clientes")
        assert listado.status_code == 200
        cuerpo = listado.json()
        assert len(cuerpo["clientes"]) == 2
        cliente_id = cuerpo["clientes"][0]["cliente_id"]

        carpeta = await cliente.get(
            f"/api/v1/secretaria/clientes/{cliente_id}/carpeta"
        )
        assert carpeta.status_code == 200
        datos = carpeta.json()
        assert datos["cliente"]["nombre"]
        assert "saldo" in datos and "ordenes" in datos
        assert datos["viajes"][0]["juez"]["despacho_validado"] is True
        assert datos["evidencias"][0]["url"].startswith("https://horminor.b-cdn.net/")


@pytest.mark.asyncio
async def test_carpeta_de_cliente_inexistente_da_404() -> None:
    transporte = httpx.ASGITransport(app=_app(MemorySecretariaStore()))
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as cliente:
        respuesta = await cliente.get(
            "/api/v1/secretaria/clientes/00000000-0000-0000-0000-000000000000/carpeta"
        )
    assert respuesta.status_code == 404


@pytest.mark.asyncio
async def test_cierre_de_caja_se_guarda_y_se_relee() -> None:
    store = MemorySecretariaStore()
    transporte = httpx.ASGITransport(app=_app(store))
    hoy = date.today().isoformat()
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as cliente:
        resumen = await cliente.get("/api/v1/secretaria/cierre-caja")
        assert resumen.status_code == 200
        datos = resumen.json()
        assert datos["cerrado"] is False
        assert datos["cobros"]["efectivo"] == 500.0
        assert datos["caja_chica"] == 25.0

        cierre = await cliente.post(
            "/api/v1/secretaria/cierre-caja",
            json={
                "fecha": hoy,
                "efectivo_contado": 475,
                "cerrado_por": "Caja Test",
            },
        )
        assert cierre.status_code == 200
        guardado = cierre.json()
        assert guardado["estado"] == "CERRADO"
        assert guardado["diferencia"] == 0.0
        assert guardado["cerrado_por"] == "Caja Test"

        despues = await cliente.get("/api/v1/secretaria/cierre-caja")
        assert despues.json()["cerrado"] is True

        historial = await cliente.get("/api/v1/secretaria/cierres")
        assert historial.json()["cierres"][0]["fecha"] == hoy


@pytest.mark.asyncio
async def test_alta_de_orden_expone_alerta_de_cupo_sin_bloquear() -> None:
    store = MemorySecretariaStore()

    async def creador_falso(datos) -> ResultadoOrden:
        assert datos.forma_pago == "FIADO"
        assert datos.volumen_m3 == Decimal("16")
        return ResultadoOrden(
            orden_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
            orden_numero=2000,
            total_viajes=2,
            advertencias=["ALERTA DE CREDITO: supera el cupo"],
            excede_cupo_credito=True,
            cupo_credito_usd=Decimal("1500.00"),
            saldo_cliente_usd=Decimal("1400.00"),
        )

    transporte = httpx.ASGITransport(app=_app(store, creador_falso))
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as cliente:
        respuesta = await cliente.post(
            "/api/v1/secretaria/ordenes",
            json={
                "cliente_id": "11111111-1111-1111-1111-111111111111",
                "resistencia": "FC-210",
                "volumen_m3": 16,
                "planta_codigo": "PLANTA-COCA",
                "forma_pago": "FIADO",
            },
        )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["numero"] == 2000
    assert cuerpo["excede_cupo_credito"] is True
    assert cuerpo["cupo_credito_usd"] == 1500.0
    assert cuerpo["advertencias"]


def test_resumen_caja_descuenta_compras_pagadas_en_efectivo() -> None:
    resumen = calcular_resumen_caja(
        fecha=date(2026, 11, 9),
        ordenes=[],
        movimientos=[
            {
                "id": "c1",
                "tipo_movimiento": "COBRO",
                "metodo": "EFECTIVO",
                "monto": "500.00",
            },
            {
                "id": "g1",
                "tipo_movimiento": "GASTO_CAJA_CHICA",
                "metodo": "EFECTIVO",
                "monto": "25.00",
            },
        ],
        pagos_proveedores=[
            {"metodo": "EFECTIVO", "bolsa": "CAJA_DIARIA", "monto": "94.00"},
            {"metodo": "TRANSFERENCIA", "bolsa": "BANCO_GERENCIA", "monto": "300.00"},
            {"metodo": "EFECTIVO", "bolsa": "CAJA_DIARIA", "monto": "50.00", "deleted_at": "x"},
        ],
        efectivo_contado=Decimal("381.00"),
    )

    assert resumen["compras_efectivo"] == 94.0
    assert resumen["efectivo_sistema"] == 381.0
    assert resumen["diferencia"] == 0.0
