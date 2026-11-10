"""POST /api/v1/secretaria/pagos — ventanilla de cobros y gastos.

Es una fachada delgada sobre ``Gate.mutar``: arma el contrato 1.3.0 segun
``tipo_movimiento`` y traduce el sobre del Gate a HTTP. La idempotencia, la
validacion de saldo, el asiento y el testigo viven en el Custodio.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .auth import ActorContext, require_payment_actor
from .router import _gate, http_response

router = APIRouter(prefix="/api/v1/secretaria", tags=["secretaria"])


class PagoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo_movimiento: Literal["COBRO", "GASTO_CAJA_CHICA", "GASTO_BANCARIO"] = "COBRO"
    cliente_id: UUID | None = None
    order_id: UUID | None = None
    fecha: date = Field(default_factory=date.today)
    metodo: Literal["EFECTIVO", "TRANSFERENCIA"]
    bolsa: Literal["CAJA_DIARIA", "BANCO_GERENCIA"] | None = None
    monto: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    referencia: str | None = Field(default=None, max_length=120)
    descripcion: str | None = Field(default=None, min_length=3, max_length=250)
    account_slug: str | None = Field(
        default=None, pattern=r"^[a-z0-9_]+$"
    )
    es_anticipo: bool = False
    autorizado_exceso_caja: bool = False
    request_id: UUID | None = None

    @model_validator(mode="after")
    def _validar_por_tipo(self):
        if self.tipo_movimiento == "COBRO":
            if self.cliente_id is None:
                raise ValueError("cliente_id es obligatorio para COBRO")
            if self.account_slug is not None or self.descripcion is not None:
                raise ValueError(
                    "account_slug/descripcion solo aplican a gastos"
                )
        else:
            if not self.account_slug:
                raise ValueError("account_slug es obligatorio para gastos")
            if not self.descripcion:
                raise ValueError("descripcion es obligatoria para gastos")
            if self.cliente_id is not None or self.order_id is not None:
                raise ValueError("un gasto no se asocia a cliente ni a orden")
        return self


def _resolver_request_id(body: PagoCreate, idempotency_key: str | None) -> str:
    del_header: UUID | None = None
    if idempotency_key:
        try:
            del_header = UUID(idempotency_key.strip())
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "INVALID_IDEMPOTENCY_KEY",
                    "message": "Idempotency-Key debe ser un UUID",
                },
            ) from exc
    if body.request_id and del_header and body.request_id != del_header:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "IDEMPOTENCY_KEY_MISMATCH",
                "message": "request_id del body no coincide con Idempotency-Key",
            },
        )
    # v4.4.0: request_id es opcional; si no viene, se genera y se devuelve.
    # Para reintentos seguros el cliente debe reenviar el mismo request_id o
    # usar Idempotency-Key.
    elegido = body.request_id or del_header or uuid4()
    return str(elegido)


async def _es_reintento(gate, request_id: str) -> bool:
    pool = getattr(gate, "pool", None)
    if pool is None:
        return False
    async with pool.acquire() as conn:
        return bool(
            await conn.fetchval(
                "SELECT 1 FROM processed_requests WHERE request_id = $1",
                request_id,
            )
        )


def _payload(body: PagoCreate) -> dict[str, Any]:
    if body.tipo_movimiento == "COBRO":
        payload: dict[str, Any] = {
            "cliente_id": str(body.cliente_id),
            "fecha": body.fecha.isoformat(),
            "metodo": body.metodo,
            "monto": format(body.monto, ".2f"),
            "es_anticipo": body.es_anticipo,
        }
        if body.order_id is not None:
            payload["order_id"] = str(body.order_id)
        if body.bolsa is not None:
            payload["bolsa"] = body.bolsa
        if body.referencia is not None:
            payload["referencia"] = body.referencia
        return payload

    bolsa = body.bolsa or (
        "CAJA_DIARIA" if body.metodo == "EFECTIVO" else "BANCO_GERENCIA"
    )
    return {
        "fecha": body.fecha.isoformat(),
        "account_slug": body.account_slug,
        "metodo": body.metodo,
        "bolsa": bolsa,
        "monto": format(body.monto, ".2f"),
        "descripcion": body.descripcion,
        "referencia_comprobante": body.referencia,
    }


def _solicitud(request_id: str, body: PagoCreate, ctx: ActorContext) -> dict[str, Any]:
    intent = (
        "REGISTER_CLIENT_PAYMENT"
        if body.tipo_movimiento == "COBRO"
        else "REGISTER_EXPENSE"
    )
    return {
        "contract_version": "1.3.0",
        "request_id": request_id,
        "channel": ctx.channel,
        "intent": intent,
        "payload": _payload(body),
    }


@router.post("/pagos")
async def registrar_pago(
    request: Request,
    body: PagoCreate = Body(...),
    ctx: ActorContext = Depends(require_payment_actor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    request_id = _resolver_request_id(body, idempotency_key)
    gate = _gate(request)
    reintento = await _es_reintento(gate, request_id)
    respuesta = await gate.mutar(_solicitud(request_id, body, ctx), ctx.actor)
    return http_response(respuesta, success_code=200 if reintento else 201)
