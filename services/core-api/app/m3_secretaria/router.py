"""Modulo 3 - Endpoints HTTP de Secretaria y Caja.

Sin login en esta etapa (Directriz 2026-11-08): el selector de rol de la UI
navega entre Secretaria, Gerencia y Superadmin. Las rutas no se exponen a
Internet hasta implementar autenticacion.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Awaitable, Callable

import asyncpg
from fastapi import APIRouter, Body, HTTPException, Query, Request

from ..services.ordenes import NuevaOrden, crear_orden
from .service import MemorySecretariaStore, PostgresSecretariaStore, SecretariaStore

router = APIRouter(prefix="/api/v1/secretaria", tags=["secretaria"])


def _store(request: Request) -> SecretariaStore:
    configurado = getattr(request.app.state, "secretaria_store", None)
    if configurado is not None:
        return configurado
    pool = getattr(request.app.state, "pool", None)
    if not isinstance(pool, asyncpg.Pool):
        raise HTTPException(status_code=503, detail="base de datos no disponible")
    store = PostgresSecretariaStore(pool)
    request.app.state.secretaria_store = store
    return store


def _creador(request: Request) -> Callable[[NuevaOrden], Awaitable[Any]]:
    """Permite inyectar el alta de ordenes en tests sin PostgreSQL."""
    inyectado = getattr(request.app.state, "crear_orden_fn", None)
    if inyectado is not None:
        return inyectado

    pool = getattr(request.app.state, "pool", None)
    if not isinstance(pool, asyncpg.Pool):
        raise HTTPException(status_code=503, detail="base de datos no disponible")

    async def _real(datos: NuevaOrden) -> Any:
        return await crear_orden(pool, datos)

    return _real


@router.get("/clientes")
async def listar_clientes(
    request: Request, q: str | None = Query(default=None)
) -> dict[str, Any]:
    return {"clientes": await _store(request).listar_clientes(q)}


@router.get("/opciones")
async def opciones(request: Request) -> dict[str, Any]:
    """Catalogos para el formulario de Nueva Orden."""
    pool = getattr(request.app.state, "pool", None)
    if not isinstance(pool, asyncpg.Pool):
        raise HTTPException(status_code=503, detail="base de datos no disponible")
    recetas = await pool.fetch(
        """
        SELECT resistencia, precio_m3, iva_pct, uso_comercial, confirmado,
               cemento_sacos_m3, retardante_litros_m3
          FROM concrete_recipes
         ORDER BY resistencia
        """
    )
    plantas = await pool.fetch(
        "SELECT codigo, nombre, tipo FROM plants WHERE activa ORDER BY nombre"
    )
    mixers_cfg = await pool.fetchval(
        "SELECT value FROM system_settings WHERE key = 'flota.mixers'"
    )
    import json as _json

    if isinstance(mixers_cfg, str):
        try:
            mixers_cfg = _json.loads(mixers_cfg)
        except ValueError:
            mixers_cfg = []
    return {
        "recetas": [
            {
                "resistencia": fila["resistencia"],
                "precio_m3": None if fila["precio_m3"] is None else float(fila["precio_m3"]),
                "iva_pct": None if fila["iva_pct"] is None else float(fila["iva_pct"]),
                "uso_comercial": fila["uso_comercial"],
                "confirmado": bool(fila["confirmado"]),
                "cemento_sacos_m3": (
                    None
                    if fila["cemento_sacos_m3"] is None
                    else float(fila["cemento_sacos_m3"])
                ),
                "retardante_litros_m3": (
                    None
                    if fila["retardante_litros_m3"] is None
                    else float(fila["retardante_litros_m3"])
                ),
            }
            for fila in recetas
        ],
        "plantas": [dict(fila) for fila in plantas],
        "mixers": mixers_cfg or [],
    }


@router.get("/clientes/{cliente_id}/carpeta")
async def carpeta_cliente(request: Request, cliente_id: str) -> dict[str, Any]:
    carpeta = await _store(request).obtener_carpeta(cliente_id)
    if carpeta is None:
        raise HTTPException(status_code=404, detail=f"cliente inexistente: {cliente_id}")
    return carpeta


@router.get("/ordenes")
async def listar_ordenes(
    request: Request,
    cliente_id: str | None = Query(default=None),
    limite: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    return {
        "ordenes": await _store(request).listar_ordenes(
            cliente_id=cliente_id, limite=limite
        )
    }


@router.post("/ordenes", status_code=201)
async def crear_orden_secretaria(
    request: Request, datos: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    try:
        orden = NuevaOrden(
            cliente_id=str(datos["cliente_id"]),
            resistencia=str(datos["resistencia"]),
            volumen_m3=Decimal(str(datos["volumen_m3"])),
            planta_codigo=str(datos["planta_codigo"]),
            forma_pago=str(datos["forma_pago"]).upper(),
            precio_m3=(
                None
                if datos.get("precio_m3") in (None, "")
                else Decimal(str(datos["precio_m3"]))
            ),
            creada_por=datos.get("creada_por") or "Secretaria",
            notas=datos.get("notas"),
            politica_viajes=datos.get("politica_viajes"),
            permitir_receta_provisional=bool(
                datos.get("permitir_receta_provisional", True)
            ),
            mixer_codigo=datos.get("mixer_codigo"),
            chofer_nombre=datos.get("chofer_nombre"),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"orden invalida: {exc}") from exc

    resultado = await _creador(request)(orden)
    if hasattr(resultado, "orden_id"):
        return {
            "orden_id": resultado.orden_id,
            "numero": resultado.orden_numero,
            "total_viajes": resultado.total_viajes,
            "viajes": resultado.viajes,
            "advertencias": resultado.advertencias,
            "consumo_orden": resultado.consumo_orden,
            "excede_cupo_credito": resultado.excede_cupo_credito,
            "cupo_credito_usd": (
                None
                if resultado.cupo_credito_usd is None
                else float(resultado.cupo_credito_usd)
            ),
            "saldo_cliente_usd": (
                None
                if resultado.saldo_cliente_usd is None
                else float(resultado.saldo_cliente_usd)
            ),
        }
    return dict(resultado) if isinstance(resultado, dict) else {"orden": resultado}


@router.get("/cierre-caja")
async def resumen_cierre(
    request: Request, fecha: date | None = Query(default=None)
) -> dict[str, Any]:
    return await _store(request).resumen_cierre(fecha or date.today())


@router.post("/cierre-caja")
async def cerrar_caja(
    request: Request, datos: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    crudo = datos.get("fecha")
    if crudo:
        try:
            fecha = date.fromisoformat(str(crudo))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"fecha invalida: {crudo}") from exc
    else:
        fecha = date.today()

    contado = datos.get("efectivo_contado")
    try:
        efectivo_contado = None if contado in (None, "") else Decimal(str(contado))
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"efectivo_contado invalido: {contado}"
        ) from exc

    return await _store(request).cerrar_caja(
        fecha=fecha,
        efectivo_contado=efectivo_contado,
        cerrado_por=datos.get("cerrado_por") or "Secretaria",
        observaciones=datos.get("observaciones"),
    )


@router.get("/cierres")
async def listar_cierres(
    request: Request, limite: int = Query(default=30, ge=1, le=120)
) -> dict[str, Any]:
    return {"cierres": await _store(request).listar_cierres(limite)}
