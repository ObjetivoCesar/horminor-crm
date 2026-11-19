"""HTTP del modulo comercial: leads y citas. El origen no cambia las reglas."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

import asyncpg
from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from .. import tiempo
from ..panel_acl import exigir_modulo
from . import citas as citas_svc
from . import leads as leads_svc

router = APIRouter(prefix="/api/v1/comercial", tags=["comercial"])


def _pool(request: Request) -> asyncpg.Pool:
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="base de datos no disponible")
    return pool


class LeadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telefono: str = Field(min_length=7, max_length=30)
    nombre: str | None = Field(default=None, max_length=160)


class RespuestaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texto: str | None = Field(default=None, max_length=2000)
    actor: str | None = Field(default=None, max_length=120)


class LeadEstadoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: Literal[
        "CONTACTO",
        "LEAD",
        "CALIFICADO",
        "EN_ESPERA",
        "HANDOFF",
        "CAIDO",
        "CONVERTIDO",
    ]
    motivo: str | None = Field(default=None, max_length=300)
    actor: str | None = Field(default=None, max_length=120)


class CitaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: Literal["VISITA", "REUNION", "MEDICION", "ENTREGA"]
    fecha: date
    hora_inicio: str = Field(min_length=4, max_length=5)
    duracion_min: int = Field(default=60, ge=15, le=480)
    cliente_id: str | None = Field(default=None, max_length=80)
    lead_id: str | None = Field(default=None, max_length=80)
    solicitada_por: str | None = Field(default=None, max_length=120)
    notas: str | None = Field(default=None, max_length=500)


class CitaEstadoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: str | None = Field(default=None, max_length=300)


@router.get("/hoy")
async def hoy_ecuador() -> dict[str, str]:
    """La fecha que usa el negocio. La decision siempre es del servidor."""
    return {
        "fecha": tiempo.hoy().isoformat(),
        "hora": tiempo.ahora().isoformat(timespec="seconds"),
        "zona": "America/Guayaquil",
    }


@router.post("/leads", status_code=201)
async def crear_lead(request: Request, body: LeadIn) -> dict[str, Any]:
    await exigir_modulo(request, "clientes_cartera", mutacion=True)
    try:
        return await leads_svc.crear_o_reutilizar(
            _pool(request),
            telefono_lead=body.telefono,
            # El origen lo decide el servidor: el panel no puede etiquetar un
            # lead como si viniera de WhatsApp.
            origen="PANEL",
            nombre=body.nombre,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/leads/{lead_id}/mensaje")
async def registrar_mensaje(
    request: Request, lead_id: str, body: RespuestaIn = Body(...)
) -> dict[str, Any]:
    """Mensaje del lead: aplica las reglas de intencion."""
    await exigir_modulo(request, "clientes_cartera", mutacion=True)
    try:
        return await leads_svc.registrar_mensaje(
            _pool(request), lead_id=lead_id, texto=body.texto, actor=body.actor
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/leads/{lead_id}/estado")
async def cambiar_estado_lead(
    request: Request, lead_id: str, body: LeadEstadoIn
) -> dict[str, Any]:
    """Cambio manual de estado: una persona puede revertir la propuesta."""
    await exigir_modulo(request, "clientes_cartera", mutacion=True)
    try:
        return await leads_svc.cambiar_estado(
            _pool(request),
            lead_id=lead_id,
            estado=body.estado,
            motivo=body.motivo,
            actor=body.actor,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/leads/{lead_id}/respuesta")
async def registrar_respuesta(
    request: Request, lead_id: str, body: RespuestaIn = Body(...)
) -> dict[str, Any]:
    await exigir_modulo(request, "clientes_cartera", mutacion=True)
    try:
        return await leads_svc.registrar_respuesta(
            _pool(request), lead_id=lead_id, texto=body.texto, actor=body.actor
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/leads")
async def listar_leads(
    request: Request, estado: str | None = Query(default=None)
) -> dict[str, Any]:
    await exigir_modulo(request, "clientes_cartera")
    return {"leads": await leads_svc.listar(_pool(request), estado=estado)}


@router.get("/citas")
async def listar_citas(
    request: Request,
    fecha: date | None = Query(default=None),
    desde: date | None = Query(default=None),
) -> dict[str, Any]:
    await exigir_modulo(request, "clientes_cartera")
    return {"hoy": tiempo.hoy().isoformat(), "citas": await citas_svc.listar(
        _pool(request), fecha=fecha, desde=desde
    )}


@router.post("/citas", status_code=201)
async def crear_cita(request: Request, body: CitaIn) -> dict[str, Any]:
    await exigir_modulo(request, "clientes_cartera", mutacion=True)
    try:
        return await citas_svc.crear(
            _pool(request),
            tipo=body.tipo,
            fecha=body.fecha,
            hora_inicio=body.hora_inicio,
            origen="PANEL",
            duracion_min=body.duracion_min,
            cliente_id=body.cliente_id,
            lead_id=body.lead_id,
            solicitada_por=body.solicitada_por,
            notas=body.notas,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/citas/{cita_id}/confirmar")
async def confirmar_cita(request: Request, cita_id: str) -> dict[str, Any]:
    await exigir_modulo(request, "clientes_cartera", mutacion=True)
    try:
        return await citas_svc.cambiar_estado(
            _pool(request), cita_id=cita_id, nuevo="CONFIRMADA"
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/citas/{cita_id}/cancelar")
async def cancelar_cita(
    request: Request, cita_id: str, body: CitaEstadoIn = Body(default=CitaEstadoIn())
) -> dict[str, Any]:
    await exigir_modulo(request, "clientes_cartera", mutacion=True)
    try:
        return await citas_svc.cambiar_estado(
            _pool(request),
            cita_id=cita_id,
            nuevo="CANCELADA",
            motivo=body.motivo,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/disponibilidad")
async def disponibilidad(
    request: Request, fecha: date | None = Query(default=None)
) -> dict[str, Any]:
    await exigir_modulo(request, "clientes_cartera")
    return await citas_svc.disponibilidad(
        _pool(request), fecha=fecha or tiempo.hoy()
    )
