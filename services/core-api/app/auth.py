"""Autenticacion interna por clave maestra (Centinela y herramientas del bot).

Compartida por el Nodo Centinela y por los endpoints de simulacion del
Modulo 1 para que no existan dos definiciones de "clave valida".
"""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status

from .settings import CLAVE_INSEGURA, Settings

HEADER_CLAVE = "X-Agency-Master-Key"


def verificar_clave(request: Request, settings: Settings) -> None:
    """Valida la clave maestra con comparacion en tiempo constante."""
    esperada = settings.clave_maestra_sentinel
    if not esperada or esperada == CLAVE_INSEGURA:
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
