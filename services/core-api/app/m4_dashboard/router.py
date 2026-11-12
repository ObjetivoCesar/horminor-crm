"""Modulo 4 - Endpoints HTTP del Dashboard Gerencial."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

import asyncpg
from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from ..panel_acl import exigir_modulo
from ..superadmin.secciones import SECCION_EMPRESA, SECCION_FINANZAS
from ..superadmin.store import ConfigStore, PostgresConfigStore
from . import bancos as bancos_svc
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


def _pool(request: Request) -> asyncpg.Pool:
    pool = getattr(request.app.state, "pool", None)
    if not isinstance(pool, asyncpg.Pool):
        raise HTTPException(status_code=503, detail="base de datos no disponible")
    return pool


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


class BancoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    numero_cuenta: str | None = Field(default=None, max_length=40)
    tipo_cuenta: Literal["CORRIENTE", "AHORRO"] | None = None
    saldo_informado: float | None = Field(default=None, ge=0)
    titular: str | None = Field(default=None, max_length=160)
    notas: str | None = Field(default=None, max_length=500)
    estado: Literal["ACTIVA", "PENDIENTE", "CERRADA"] | None = None


@router.get("/bancos")
async def cuentas_bancarias(request: Request) -> dict[str, Any]:
    """Catalogo de bancos con saldo contable y resumen de prestamos."""
    return {"bancos": await bancos_svc.listar(_pool(request))}


@router.get("/bancos/{slug}")
async def detalle_banco(request: Request, slug: str) -> dict[str, Any]:
    datos = await bancos_svc.detalle(_pool(request), slug)
    if datos is None:
        raise HTTPException(status_code=404, detail="banco no encontrado")
    return datos


@router.put("/bancos/{slug}")
async def actualizar_banco(
    request: Request, slug: str, body: BancoUpdate = Body(...)
) -> dict[str, Any]:
    await exigir_modulo(request, "finanzas_balance_auditoria", mutacion=True)
    datos = body.model_dump(exclude_unset=True)
    actualizado = await bancos_svc.actualizar(_pool(request), slug, datos)
    if actualizado is None:
        raise HTTPException(status_code=404, detail="banco no encontrado")
    return actualizado


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
