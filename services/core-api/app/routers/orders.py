"""Alta de ordenes de hormigon (Modulo 0 + Modulo 2)."""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal

import asyncpg
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..services.ordenes import NuevaOrden, OrdenInvalidaError, crear_orden

router = APIRouter(prefix="/api/v1", tags=["ordenes"])


class OrdenCreate(BaseModel):
    cliente_id: str
    resistencia: str
    volumen_m3: Decimal = Field(gt=0)
    planta_codigo: str
    forma_pago: str
    precio_m3: Decimal | None = Field(default=None, ge=0)
    creada_por: str | None = None
    notas: str | None = None
    politica_viajes: str | None = None
    # Ratificado 2026-11-08: por defecto se permite vender con receta provisional.
    permitir_receta_provisional: bool = True
    mixer_codigo: str | None = None
    chofer_nombre: str | None = None
    # v4.3: IVA y abono inicial.
    aplica_iva: bool | None = None
    abono_inicial_monto: Decimal | None = Field(default=None, ge=0)
    abono_inicial_metodo: str | None = None


def _pool(request: Request) -> asyncpg.Pool:
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="base de datos no disponible")
    return pool


@router.post("/orders", status_code=201)
async def nueva_orden(request: Request, body: OrdenCreate):
    pool = _pool(request)
    try:
        resultado = await crear_orden(
            pool,
            NuevaOrden(
                cliente_id=body.cliente_id,
                resistencia=body.resistencia,
                volumen_m3=body.volumen_m3,
                planta_codigo=body.planta_codigo,
                forma_pago=body.forma_pago,
                precio_m3=body.precio_m3,
                creada_por=body.creada_por,
                notas=body.notas,
                politica_viajes=body.politica_viajes,
                permitir_receta_provisional=body.permitir_receta_provisional,
                mixer_codigo=body.mixer_codigo,
                chofer_nombre=body.chofer_nombre,
                aplica_iva=body.aplica_iva,
                abono_inicial_monto=body.abono_inicial_monto,
                abono_inicial_metodo=body.abono_inicial_metodo,
            ),
        )
    except OrdenInvalidaError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return asdict(resultado)
