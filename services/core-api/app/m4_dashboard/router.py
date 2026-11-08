"""Modulo 4 - Endpoints HTTP del Dashboard Gerencial."""

from __future__ import annotations

from datetime import date
from typing import Any

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from ..superadmin.secciones import SECCION_EMPRESA, SECCION_FINANZAS
from ..superadmin.store import ConfigStore, PostgresConfigStore
from .calculos import simular_bancario
from .dossier import construir_dossier_html
from .service import DashboardStore, MemoryDashboardStore, PostgresDashboardStore

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def _store(request: Request) -> DashboardStore:
    configurado = getattr(request.app.state, "dashboard_store", None)
    if configurado is not None:
        return configurado
    pool = getattr(request.app.state, "pool", None)
    if not isinstance(pool, asyncpg.Pool):
        raise HTTPException(status_code=503, detail="base de datos no disponible")
    store = PostgresDashboardStore(pool)
    request.app.state.dashboard_store = store
    return store


def _config(request: Request) -> ConfigStore:
    configurado = getattr(request.app.state, "config_store", None)
    if configurado is not None:
        return configurado
    pool = getattr(request.app.state, "pool", None)
    if not isinstance(pool, asyncpg.Pool):
        raise HTTPException(status_code=503, detail="base de datos no disponible")
    store = PostgresConfigStore(pool)
    request.app.state.config_store = store
    return store


@router.get("/hero-kpis")
async def hero_kpis(
    request: Request,
    fecha: date | None = Query(default=None),
    planta: str | None = Query(default=None),
) -> dict[str, Any]:
    return await _store(request).hero_kpis(fecha, planta)


@router.get("/mercado")
async def cuota_mercado(
    request: Request,
    periodo: str = Query(default="12_MESES_MOVILES"),
    anio: int = Query(default=2026, ge=2020, le=2100),
) -> dict[str, Any]:
    return await _store(request).cuota_mercado(periodo=periodo, anio=anio)


@router.get("/benchmarks")
async def benchmarks(request: Request) -> dict[str, Any]:
    return {"benchmarks": await _store(request).benchmarks()}


async def _simulador(request: Request) -> dict[str, Any]:
    finanzas = await _config(request).leer_seccion(SECCION_FINANZAS)
    config = dict(finanzas.get("simulador") or {})
    flujo = await _store(request).flujo_operativo_mensual(90)
    resultado = simular_bancario(config, flujo_historico_mensual=flujo)
    resultado["config"] = config
    return resultado


@router.get("/simulador")
async def simulador(request: Request) -> dict[str, Any]:
    return await _simulador(request)


@router.get("/dossier", response_class=HTMLResponse)
async def dossier(request: Request) -> HTMLResponse:
    empresa = await _config(request).leer_seccion(SECCION_EMPRESA)
    datos_simulador = await _simulador(request)
    mercado = await _store(request).cuota_mercado(
        periodo="12_MESES_MOVILES", anio=2026
    )
    kpis = await _store(request).hero_kpis()
    return HTMLResponse(
        construir_dossier_html(
            empresa=empresa,
            simulador=datos_simulador,
            mercado=mercado,
            kpis=kpis,
        )
    )
