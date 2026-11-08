"""Tests del Modulo 4 - Dashboard Gerencial, Cuota de Mercado y Simulador.

La matematica se prueba con ``Decimal`` y los endpoints con stores en memoria,
sin PostgreSQL ni red.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.m4_dashboard.calculos import (  # noqa: E402
    calcular_cuota_mercado,
    cuota_francesa,
    rango_periodo,
    simular_bancario,
)
from app.m4_dashboard.router import router as dashboard_router  # noqa: E402
from app.m4_dashboard.service import (  # noqa: E402
    MemoryDashboardStore,
    semaforo_termico,
)
from app.superadmin.store import MemoryConfigStore  # noqa: E402


def _app(store: MemoryDashboardStore, config: MemoryConfigStore | None = None) -> FastAPI:
    app = FastAPI()
    app.state.dashboard_store = store
    app.state.config_store = config or MemoryConfigStore()
    app.include_router(dashboard_router)
    return app


# ---------------------------------------------------------------------------
# Simulador bancario
# ---------------------------------------------------------------------------
def test_cuota_francesa_pluma_cuadra_con_la_direccion() -> None:
    cuota = cuota_francesa("100000", "11.2", 36)
    assert cuota == Decimal("3283.35")


def test_cuota_francesa_combo_cuadra_con_la_direccion() -> None:
    cuota = cuota_francesa("240000", "11.2", 48)
    assert cuota == Decimal("6226.26")


def test_simulador_dos_escenarios_y_dscr() -> None:
    resultado = simular_bancario(
        {
            "pluma_monto_usd": 100000,
            "combo_china_monto_usd": 240000,
            "tasa_anual_pct": 11.2,
            "plazos_meses": [36, 48],
            "margen_neto_m3": 42.50,
            "m3_extra_pluma": 180,
            "m3_extra_combo": 450,
        },
        flujo_historico_mensual=1000,
    )

    pluma, combo = resultado["escenarios"]
    assert pluma["cuota_mensual"] == 3283.35
    assert pluma["flujo_incremental_mensual"] == 7650.0
    assert pluma["dscr_proyectado"] == 2.33
    assert pluma["dscr_historico"] == 2.63  # (1000 + 7650) / 3283.35
    assert pluma["semaforo"] == "VERDE"

    assert combo["cuota_mensual"] == 6226.26
    assert combo["dscr_proyectado"] == 3.07
    assert resultado["parametros"]["tasa_mensual_pct"] == 0.93


def test_dscr_insuficiente_pinta_rojo() -> None:
    resultado = simular_bancario(
        {"margen_neto_m3": 10, "m3_extra_pluma": 100, "plazos_meses": [36, 48]}
    )
    pluma = resultado["escenarios"][0]
    assert pluma["semaforo"] == "ROJO"


# ---------------------------------------------------------------------------
# Cuota de mercado
# ---------------------------------------------------------------------------
def test_cuota_mercado_valoriza_la_competencia() -> None:
    cuota = calcular_cuota_mercado(
        provincia="Orellana",
        anio=2026,
        ventas_m3=12000,
        demanda_m3=120000,
        precio_m3=118,
    )
    assert cuota["cuota_pct"] == 10.0
    assert cuota["valor_mercado_usd"] == 14160000.0
    assert cuota["capturado_usd"] == 1416000.0
    assert cuota["competencia_usd"] == 12744000.0
    assert "Planta Movil" in cuota["mensaje"]


def test_periodo_doce_meses_vs_anio_calendario() -> None:
    desde, hasta = rango_periodo(
        "12_MESES_MOVILES", anio=2026, hoy=date(2026, 11, 8)
    )
    assert (hasta - desde).days == 365
    desde, hasta = rango_periodo("ANIO_CALENDARIO", anio=2026)
    assert desde == date(2026, 1, 1)
    assert hasta == date(2026, 12, 31)


def test_semaforo_termico_90_120() -> None:
    assert semaforo_termico(89.9) == "VERDE"
    assert semaforo_termico(90) == "AMBAR"
    assert semaforo_termico(120) == "AMBAR"
    assert semaforo_termico(120.1) == "ROJO"
    assert semaforo_termico(None) == "SIN_DATOS"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_hero_kpis_expone_los_tres_indicadores() -> None:
    transporte = httpx.ASGITransport(app=_app(MemoryDashboardStore()))
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as cliente:
        respuesta = await cliente.get("/api/v1/dashboard/hero-kpis")
        assert respuesta.status_code == 200
        datos = respuesta.json()

    assert set(datos) >= {"kpi_caja", "kpi_operacion", "kpi_bodega"}
    assert datos["kpi_caja"]["cobrado_hoy"] == 3332.0
    assert datos["kpi_caja"]["por_cobrar_total"] == 3136.0
    assert datos["kpi_operacion"]["m3_hoy"] == 76.0
    assert datos["kpi_operacion"]["mixers_en_ruta"] == 1
    assert datos["kpi_operacion"]["semaforo_termico"] == "VERDE"
    assert datos["kpi_bodega"]["m3_fc210_disponibles"] == 466.7
    assert datos["kpi_bodega"]["alerta_merma"] is True


@pytest.mark.asyncio
async def test_cuota_mercado_endpoint_dos_provincias() -> None:
    transporte = httpx.ASGITransport(app=_app(MemoryDashboardStore()))
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as cliente:
        respuesta = await cliente.get(
            "/api/v1/dashboard/mercado?periodo=12_MESES_MOVILES&anio=2026"
        )
        assert respuesta.status_code == 200
        datos = respuesta.json()

    provincias = {p["provincia"]: p for p in datos["provincias"]}
    assert provincias["Orellana"]["demanda_m3"] == 120000.0
    assert provincias["Sucumbios"]["demanda_m3"] == 95000.0
    assert provincias["Orellana"]["ventas_m3"] == 52.0
    assert provincias["Sucumbios"]["ventas_m3"] == 24.0
    assert datos["precio_valorizacion_m3"] == 118.0


@pytest.mark.asyncio
async def test_simulador_endpoint_y_dossier_imprimible() -> None:
    app = _app(MemoryDashboardStore())
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as cliente:
        simulador = await cliente.get("/api/v1/dashboard/simulador")
        assert simulador.status_code == 200
        datos = simulador.json()
        assert datos["escenarios"][0]["cuota_mensual"] == 3283.35
        assert datos["escenarios"][1]["cuota_mensual"] == 6226.26
        # El flujo historico del store en memoria entra al DSCR.
        assert datos["escenarios"][0]["dscr_historico"] is not None

        dossier = await cliente.get("/api/v1/dashboard/dossier")
        assert dossier.status_code == 200
        assert "text/html" in dossier.headers["content-type"]
        html = dossier.text
        assert "Dossier Financiero de Pre-Calificacion Bancaria" in html
        assert "Pluma China" in html
        assert "Banco Pichincha" not in html  # el memory store no trae cuentas
