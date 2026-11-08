"""Modulo 5 - Endpoint HTTP del Nodo Centinela."""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from ..settings import Settings, get_settings
from . import audit

router = APIRouter(prefix="/api/v1/sentinel", tags=["sentinel"])

CLAVE_INSEGURA = "change-me"
HEADER_CLAVE = "X-Agency-Master-Key"


def _resolver_settings(request: Request) -> Settings:
    """Usa las settings publicadas por ``main.py`` o las de entorno."""
    configurada = getattr(request.app.state, "settings", None)
    if isinstance(configurada, Settings):
        return configurada
    return get_settings()


def _verificar_clave(request: Request, settings: Settings) -> None:
    """Valida la clave maestra con comparacion en tiempo constante."""
    esperada = settings.agency_master_key or ""
    if not esperada.strip() or esperada == CLAVE_INSEGURA:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="clave maestra (agency_master_key) no configurada",
        )

    recibida = request.headers.get(HEADER_CLAVE)
    if not recibida or not hmac.compare_digest(
        recibida.encode("utf-8"), esperada.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="no autorizado",
        )


@router.get("/daily-audit")
async def daily_audit(request: Request) -> dict[str, Any]:
    """Auditoria diaria del ERP para el CRM Central de la agencia.

    Requiere el header ``X-Agency-Master-Key``. Si el pool de base de datos no
    fue publicado por ``main.py`` responde 503; si la clave maestra sigue en el
    valor por defecto inseguro tambien responde 503.
    """
    settings = _resolver_settings(request)
    _verificar_clave(request, settings)

    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="base de datos no disponible",
        )

    return await audit.ejecutar_auditoria(pool, settings)
