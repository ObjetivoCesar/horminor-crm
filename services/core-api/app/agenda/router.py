"""HTTP de la agenda visual: solo lectura, sin ejecutar envios."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request

from .. import tiempo
from ..panel_acl import exigir_modulos
from . import eventos as eventos_svc

router = APIRouter(prefix="/api/v1/agenda", tags=["agenda"])

_MODULOS = tuple(
    sorted({modulo for modulos in eventos_svc.MODULOS_POR_TIPO.values() for modulo in modulos})
)
_RANGO_MAXIMO_DIAS = 400


def _pool(request: Request) -> asyncpg.Pool:
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="base de datos no disponible")
    return pool


def _tipos_permitidos(perfil: dict[str, Any]) -> list[str]:
    permitidos = perfil.get("modulos_permitidos") or {}
    return [
        tipo
        for tipo in eventos_svc.TIPOS
        if any(permitidos.get(modulo) for modulo in eventos_svc.MODULOS_POR_TIPO[tipo])
    ]


@router.get("/eventos")
async def listar_eventos(
    request: Request,
    tipo: str | None = Query(default=None),
    desde: date | None = Query(default=None),
    hasta: date | None = Query(default=None),
) -> dict[str, Any]:
    """Eventos de la agenda entre dos fechas (por defecto, el mes en curso).

    ``tipo`` es opcional: sin el se devuelven todas las pestañas que el perfil
    puede ver, y el panel reparte por pestaña. El calendario no modifica nada.
    """
    perfil = await exigir_modulos(request, _MODULOS)
    permitidos = _tipos_permitidos(perfil)

    if tipo is not None:
        limpio = tipo.strip().lower()
        if limpio not in eventos_svc.TIPOS:
            raise HTTPException(
                status_code=422,
                detail=f"tipo de agenda invalido: {tipo}",
            )
        if limpio not in permitidos:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "MODULE_NOT_ALLOWED",
                    "message": "el perfil no tiene permiso sobre esta agenda",
                    "modulos": list(eventos_svc.MODULOS_POR_TIPO[limpio]),
                },
            )
        tipos = (limpio,)
    else:
        tipos = tuple(permitidos)

    fin = hasta or tiempo.hoy()
    inicio = desde or fin.replace(day=1)
    if inicio > fin:
        raise HTTPException(status_code=422, detail="desde no puede ser mayor que hasta")
    if (fin - inicio) > timedelta(days=_RANGO_MAXIMO_DIAS):
        raise HTTPException(
            status_code=422,
            detail=f"el rango no puede superar {_RANGO_MAXIMO_DIAS} dias",
        )

    eventos = await eventos_svc.listar(
        _pool(request), desde=inicio, hasta=fin, tipos=tipos
    )
    return {
        "zona": eventos_svc.ZONA,
        "hoy": tiempo.hoy().isoformat(),
        "desde": inicio.isoformat(),
        "hasta": fin.isoformat(),
        "tipos": list(tipos),
        "conteo": eventos_svc.conteo(eventos),
        "total": len(eventos),
        "eventos": eventos,
    }
