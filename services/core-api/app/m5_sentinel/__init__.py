"""Modulo 5 - Nodo Centinela.

Expone la auditoria diaria del ERP: infraestructura, canal de WhatsApp/CDN y
salud operativa. La fachada publica vive en :mod:`router` y la logica pura de
agregacion en :mod:`audit`.
"""

from __future__ import annotations

from .audit import (
    agregar_estado_global,
    construir_resumen_operativo,
    ejecutar_auditoria,
)
from .checks import CheckResult
from .router import router

__all__ = [
    "CheckResult",
    "agregar_estado_global",
    "construir_resumen_operativo",
    "ejecutar_auditoria",
    "router",
]
