"""CRUD de usuarios/perfiles del panel y checklist de modulos (v6.2)."""

from __future__ import annotations

from typing import Any

import asyncpg
from fastapi import APIRouter, Body, HTTPException, Request

from ..panel_acl import (
    MODULOS,
    ROLES_BASE,
    _store,
    exigir_modulo,
    validar_usuario,
)

router = APIRouter(prefix="/api/v1/superadmin/usuarios", tags=["superadmin"])


@router.get("")
async def listar_usuarios(request: Request) -> dict[str, Any]:
    await exigir_modulo(request, "superadmin_config")
    return {"usuarios": await _store(request).listar(solo_activos=False)}


@router.get("/modulos")
async def listar_modulos() -> dict[str, Any]:
    etiquetas = {
        "dashboard_gerencial": "Dashboard gerencial",
        "secretaria_ventanilla": "Ventanilla y pedidos",
        "secretaria_cobros_gastos": "Cobros, abonos y gastos",
        "secretaria_cierre_caja": "Cierre de caja",
        "agenda_despachos": "Agenda de despachos",
        "compras_materiales": "Compras de materiales",
        "planta_kardex": "Planta, flota y kardex",
        "clientes_cartera": "Clientes y cartera",
        "finanzas_balance_auditoria": "Finanzas, balance y auditoria",
        "superadmin_config": "Superadmin y configuracion",
    }
    return {
        "modulos": [
            {"id": modulo, "label": etiquetas.get(modulo, modulo)}
            for modulo in MODULOS
        ],
        "roles_base": list(ROLES_BASE),
    }


@router.post("", status_code=201)
async def crear_usuario(
    request: Request, datos: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    await exigir_modulo(request, "superadmin_config", mutacion=True)
    try:
        normal = validar_usuario(datos)
    except ValueError as exc:
        raise _error(exc) from exc
    try:
        usuario = await _store(request).crear(normal)
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(
            status_code=409, detail="ya existe un usuario con ese nombre"
        ) from exc
    return {"usuario": usuario}


@router.put("/{usuario_id}")
async def actualizar_usuario(
    request: Request,
    usuario_id: str,
    datos: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    await exigir_modulo(request, "superadmin_config", mutacion=True)
    try:
        normal = validar_usuario(datos, parcial=True)
    except ValueError as exc:
        raise _error(exc) from exc
    try:
        usuario = await _store(request).actualizar(usuario_id, normal)
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(
            status_code=409, detail="ya existe un usuario con ese nombre"
        ) from exc
    if usuario is None:
        raise HTTPException(status_code=404, detail="usuario no encontrado")
    return {"usuario": usuario}


@router.delete("/{usuario_id}")
async def eliminar_usuario(request: Request, usuario_id: str) -> dict[str, Any]:
    await exigir_modulo(request, "superadmin_config", mutacion=True)
    eliminado = await _store(request).eliminar(usuario_id)
    if not eliminado:
        raise HTTPException(status_code=404, detail="usuario no encontrado")
    return {"eliminado": True, "id": usuario_id}


def _error(exc: ValueError) -> HTTPException:
    codigo = (
        "EMPTY_MODULE_CHECKLIST"
        if "checklist" in str(exc).lower()
        else "INVALID_USER"
    )
    return HTTPException(
        status_code=422,
        detail={"code": codigo, "message": str(exc)},
    )
