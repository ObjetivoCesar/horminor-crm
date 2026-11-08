"""Consulta de clientes, ordenes, viajes e inventario (Modulo 0 -> UI)."""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1", tags=["catalogo"])


def _pool(request: Request) -> asyncpg.Pool:
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="base de datos no disponible")
    return pool


class ClienteCreate(BaseModel):
    nombre: str = Field(min_length=1)
    constructora: str | None = None
    ruc: str | None = None
    telefono_whatsapp: str | None = None
    estado: str = "ACTIVO"


@router.get("/clients")
async def listar_clientes(
    request: Request,
    q: str | None = Query(default=None, description="Nombre, constructora o RUC"),
    limit: int = Query(default=50, ge=1, le=200),
):
    pool = _pool(request)
    if q:
        patron = f"%{q.lower()}%"
        return await pool.fetch(
            """
            SELECT v.* FROM v_cliente_saldo v
              JOIN clients c ON c.id = v.id
             WHERE lower(v.nombre) LIKE $1
                OR lower(coalesce(c.constructora, '')) LIKE $1
                OR coalesce(c.ruc, '') LIKE $1
             ORDER BY v.nombre
             LIMIT $2
            """,
            patron,
            limit,
        )
    return await pool.fetch(
        "SELECT * FROM v_cliente_saldo ORDER BY nombre LIMIT $1", limit
    )


@router.post("/clients", status_code=201)
async def crear_cliente(request: Request, body: ClienteCreate):
    pool = _pool(request)
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO clients (nombre, constructora, ruc, telefono_whatsapp, estado)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id::text, nombre, constructora, ruc, estado
            """,
            body.nombre,
            body.constructora,
            body.ruc,
            body.telefono_whatsapp,
            body.estado,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail="telefono_whatsapp ya registrado") from exc
    return dict(row)


@router.get("/orders")
async def listar_ordenes(
    request: Request,
    cliente_id: UUID | None = None,
    estado: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    pool = _pool(request)
    return await pool.fetch(
        """
        SELECT o.id::text, o.numero, o.resistencia, o.volumen_m3, o.forma_pago,
               o.precio_m3, o.total, o.estado, o.created_at,
               c.nombre AS cliente, p.nombre AS planta,
               (SELECT count(*) FROM mixer_dispatches d WHERE d.order_id = o.id) AS viajes
          FROM orders o
          JOIN clients c ON c.id = o.cliente_id
          JOIN plants  p ON p.id = o.planta_id
         WHERE ($1::uuid IS NULL OR o.cliente_id = $1)
           AND ($2::text IS NULL OR o.estado = $2)
         ORDER BY o.created_at DESC
         LIMIT $3
        """,
        cliente_id,
        estado,
        limit,
    )


@router.get("/orders/{order_id}")
async def detalle_orden(request: Request, order_id: UUID):
    pool = _pool(request)
    orden = await pool.fetchrow(
        """
        SELECT o.*, c.nombre AS cliente, p.nombre AS planta
          FROM orders o
          JOIN clients c ON c.id = o.cliente_id
          JOIN plants  p ON p.id = o.planta_id
         WHERE o.id = $1
        """,
        order_id,
    )
    if orden is None:
        raise HTTPException(status_code=404, detail="orden no encontrada")
    viajes = await pool.fetch(
        "SELECT * FROM v_dispatch_timeline WHERE order_id = $1 ORDER BY viaje_numero",
        order_id,
    )
    return {"orden": dict(orden), "viajes": [dict(v) for v in viajes]}


@router.get("/inventory")
async def inventario(request: Request):
    pool = _pool(request)
    return await pool.fetch("SELECT * FROM v_inventario ORDER BY codigo")


@router.get("/commercial/benchmarks")
async def benchmarks(request: Request):
    pool = _pool(request)
    return await pool.fetch(
        "SELECT * FROM market_benchmarks ORDER BY provincia"
    )
