"""Router HTTP del Custodio v4.4.0.

Traduce el sobre del Gate (ACCEPT / REJECT / PENDING) a HTTP sin reinterpretar
el contrato. La autenticacion es de servicio: clave + headers de actor.
"""

from __future__ import annotations

from typing import Any

import asyncpg
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from ..custodio import Gate
from .auth import ActorContext, require_gate_actor

router = APIRouter(prefix="/api/v1/custodio", tags=["custodio"])


def _gate(request: Request) -> Gate:
    fabrica = getattr(request.app.state, "gate_factory", None)
    if fabrica is not None:
        return fabrica(getattr(request.app.state, "pool", None))
    pool = getattr(request.app.state, "pool", None)
    if not isinstance(pool, asyncpg.Pool):
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "pool no disponible"},
        )
    return Gate(pool)


def http_response(respuesta: dict[str, Any], *, success_code: int = 200):
    """Mapea el sobre del Gate a un status HTTP estable."""
    status = respuesta.get("status")
    if status == "ACCEPT":
        return JSONResponse(status_code=success_code, content=respuesta)
    if status == "PENDING_JULIO_APPROVAL":
        return JSONResponse(status_code=202, content=respuesta)

    codigos = set(respuesta.get("rejection_codes") or [])
    if "UNAUTHORIZED_ACTOR" in codigos:
        code = 401
    elif "UNAUTHORIZED_DOMAIN_ACCESS" in codigos:
        code = 403
    elif "PAYLOAD_HASH_MISMATCH_ON_RETRY" in codigos:
        code = 409
    else:
        code = 422
    return JSONResponse(status_code=code, content=respuesta)


def _canal_del_servidor(body: dict[str, Any], ctx: ActorContext) -> dict[str, Any]:
    """El canal lo resuelve el servidor; nunca se confia en el del JSON."""
    solicitud = dict(body)
    declarado = str(solicitud.get("channel") or "").strip().upper()
    if declarado and declarado != ctx.channel:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "CHANNEL_MISMATCH",
                "message": (
                    f"el canal del contrato ({declarado}) no coincide con "
                    f"X-Channel ({ctx.channel})"
                ),
            },
        )
    solicitud["channel"] = ctx.channel
    return solicitud


@router.post("/mutations")
@router.post("/mutaciones", include_in_schema=False)
async def mutaciones(
    request: Request,
    body: dict[str, Any] = Body(...),
    ctx: ActorContext = Depends(require_gate_actor),
):
    solicitud = _canal_del_servidor(body, ctx)
    respuesta = await _gate(request).mutar(solicitud, ctx.actor)
    return http_response(respuesta)


@router.post("/queries")
@router.post("/consultas", include_in_schema=False)
async def consultas(
    request: Request,
    body: dict[str, Any] = Body(...),
    ctx: ActorContext = Depends(require_gate_actor),
):
    solicitud = _canal_del_servidor(body, ctx)
    respuesta = await _gate(request).consultar(solicitud, ctx.actor)
    return http_response(respuesta)


@router.post("/witness")
@router.post("/testigos", include_in_schema=False)
async def testigos(
    request: Request,
    body: dict[str, Any] = Body(...),
    ctx: ActorContext = Depends(require_gate_actor),
):
    solicitud = _canal_del_servidor(body, ctx)
    respuesta = await _gate(request).testigo(solicitud, ctx.actor)
    return http_response(respuesta)


@router.get("/catalog")
async def catalogo(
    request: Request,
    ctx: ActorContext = Depends(require_gate_actor),
):
    """Cuentas activas para los selectores y el boton [ + ] del panel."""
    gate = _gate(request)
    pool = getattr(gate, "pool", None) or getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "pool no disponible"},
        )
    async with pool.acquire() as conn:
        filas = await conn.fetch(
            """
            SELECT id::text, code, slug, name, account_type, normal_balance,
                   parent_group, default_bolsa, requires_voucher,
                   is_system_locked
              FROM accounting_accounts
             WHERE deleted_at IS NULL
             ORDER BY code
            """
        )
    return {"cuentas": [dict(f) for f in filas]}
