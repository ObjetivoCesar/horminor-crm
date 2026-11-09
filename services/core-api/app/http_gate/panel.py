"""Puente interno del panel web con el Custodio v4.4.0.

El navegador no recibe ``CUSTODIO_TOKEN_*``. Mientras el login de usuario
final (Paso 3) no exista, el panel llama a estas rutas y el servidor resuelve
un actor de panel por ``X-Panel-Role`` (default SECRETARIA). Cuando se agregue
la sesión, este archivo se reemplaza por la dependencia de sesión y las rutas
pueden quedar como fachada interna.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Header, HTTPException, Request

from ..custodio.gate import Actor
from .auth import ActorContext
from .payments import (
    PagoCreate,
    _es_reintento,
    _resolver_request_id,
    _solicitud,
)
from .router import _gate, http_response

router = APIRouter(prefix="/api/v1/panel", tags=["panel"])

ROLES_PANEL = ("SUPERADMIN", "CONTADORA", "SECRETARIA")


def _pool(request: Request):
    """Acepta asyncpg.Pool o un envoltorio con ``acquire`` (tests/clon)."""
    pool = getattr(request.app.state, "pool", None)
    if pool is None or not hasattr(pool, "acquire"):
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "pool no disponible"},
        )
    return pool


def _contexto_panel(rol: str, actor_id: str | None) -> ActorContext:
    rol = str(rol or "SECRETARIA").strip().upper()
    if rol not in ROLES_PANEL:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "UNAUTHORIZED_DOMAIN_ACCESS",
                "message": "el panel solo opera como SUPERADMIN, CONTADORA o SECRETARIA",
            },
        )
    identificador = str(actor_id or "").strip() or f"{rol}_PANEL"
    return ActorContext(actor=Actor(role=rol, id=identificador), channel="WEB_PANEL")


@router.get("/catalog")
async def catalogo_panel(request: Request) -> dict[str, Any]:
    """Cuentas activas para los selectores de gasto del panel."""
    filas = await _pool(request).fetch(
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


@router.post("/pagos")
async def registrar_pago_panel(
    request: Request,
    body: PagoCreate = Body(...),
    rol: str = Header(default="SECRETARIA", alias="X-Panel-Role"),
    actor_id: str | None = Header(default=None, alias="X-Panel-Actor"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Fachada interna: mismo contrato y mismas reglas que el endpoint oficial."""
    ctx = _contexto_panel(rol, actor_id)
    request_id = _resolver_request_id(body, idempotency_key)
    gate = _gate(request)
    reintento = await _es_reintento(gate, request_id)
    respuesta = await gate.mutar(_solicitud(request_id, body, ctx), ctx.actor)
    return http_response(respuesta, success_code=200 if reintento else 201)
