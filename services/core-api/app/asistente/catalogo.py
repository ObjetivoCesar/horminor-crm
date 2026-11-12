"""Catálogo de consultas del bibliotecario (espejo de docs/CATALOGO_CONSULTAS.json).

Solo las 22 IMPLEMENTADA. Si cambia el JSON, `scripts/auditar_skills.py` avisa.
"""

from __future__ import annotations

from typing import Any

ROLES_INTERNOS = ("SUPERADMIN", "CONTADORA", "SECRETARIA", "BODEGA")

CONSULTAS: dict[str, dict[str, Any]] = {
    "cliente_buscar": {
        "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA", "BODEGA"),
        "parametros": ("texto", "limite"),
        "requeridos": ("texto",),
        "handler": "cliente_buscar",
    },
    "cliente_ficha": {
        "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA"),
        "parametros": ("cliente_id",),
        "requeridos": ("cliente_id",),
        "handler": "cliente_ficha",
    },
    "cartera_cliente": {
        "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA"),
        "parametros": ("cliente_id",),
        "requeridos": ("cliente_id",),
        "handler": "cartera_cliente",
    },
    "cliente_facturas": {
        "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA"),
        "parametros": ("cliente_id",),
        "requeridos": ("cliente_id",),
        "handler": "cliente_facturas",
    },
    "cartera_total": {
        "roles": ("SUPERADMIN", "CONTADORA"),
        "parametros": ("desde", "hasta"),
        "requeridos": (),
        "handler": "cartera_total",
    },
    "cierre_dia": {
        "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA"),
        "parametros": ("desde", "hasta"),
        "requeridos": ("desde", "hasta"),
        "handler": "cierre_dia",
    },
    "movimientos_dia": {
        "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA"),
        "parametros": ("desde", "hasta", "limite"),
        "requeridos": ("desde", "hasta"),
        "handler": "movimientos_dia",
    },
    "orden_timeline": {
        "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA", "BODEGA"),
        "parametros": ("orden_numero",),
        "requeridos": ("orden_numero",),
        "handler": "orden_timeline",
    },
    "viaje_estado": {
        "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA", "BODEGA"),
        "parametros": ("dispatch_id",),
        "requeridos": ("dispatch_id",),
        "handler": "viaje_estado",
    },
    "stock_actual": {
        "roles": ("SUPERADMIN", "CONTADORA", "BODEGA"),
        "parametros": ("material",),
        "requeridos": (),
        "handler": "stock_actual",
    },
    "stock_proyectado": {
        "roles": ("SUPERADMIN", "CONTADORA", "BODEGA"),
        "parametros": ("material",),
        "requeridos": (),
        "handler": "stock_proyectado",
    },
    "compras_pendientes": {
        "roles": ("SUPERADMIN", "CONTADORA"),
        "parametros": ("limite",),
        "requeridos": (),
        "handler": "compras_pendientes",
    },
    "por_pagar": {
        "roles": ("SUPERADMIN", "CONTADORA"),
        "parametros": ("limite",),
        "requeridos": (),
        "handler": "por_pagar",
    },
    "balance": {
        "roles": ("SUPERADMIN", "CONTADORA"),
        "parametros": (),
        "requeridos": (),
        "handler": "balance",
    },
    "resultados": {
        "roles": ("SUPERADMIN", "CONTADORA"),
        "parametros": ("desde", "hasta"),
        "requeridos": ("desde", "hasta"),
        "handler": "resultados",
    },
    "banco_detalle": {
        "roles": ("SUPERADMIN", "CONTADORA"),
        "parametros": ("banco",),
        "requeridos": ("banco",),
        "handler": "banco_detalle",
    },
    "banco_movimientos": {
        "roles": ("SUPERADMIN", "CONTADORA"),
        "parametros": ("banco", "limite"),
        "requeridos": ("banco",),
        "handler": "banco_movimientos",
    },
    "cuota_mercado": {
        "roles": ("SUPERADMIN", "CONTADORA"),
        "parametros": ("provincia", "anio"),
        "requeridos": ("provincia",),
        "handler": "cuota_mercado",
    },
    "agenda_obras": {
        "roles": ("SUPERADMIN", "SECRETARIA", "BODEGA"),
        "parametros": ("desde", "hasta"),
        "requeridos": ("desde", "hasta"),
        "handler": "agenda_obras",
    },
    "disponibilidad_agenda": {
        "roles": ("SUPERADMIN", "SECRETARIA"),
        "parametros": ("fecha",),
        "requeridos": ("fecha",),
        "handler": "disponibilidad_agenda",
    },
    "recetas_precio_publico": {
        "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA"),
        "parametros": (),
        "requeridos": (),
        "handler": "recetas_precio_publico",
    },
    "empresa_info": {
        "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA"),
        "parametros": (),
        "requeridos": (),
        "handler": "empresa_info",
    },
    "salud_sistema": {
        "roles": ("SUPERADMIN",),
        "parametros": (),
        "requeridos": (),
        "handler": "salud_sistema",
    },
}


def permite(consulta: str, rol: str) -> bool:
    return rol in CONSULTAS.get(consulta, {}).get("roles", ())


def herramientas_para(rol: str) -> dict[str, dict[str, Any]]:
    """Solo las consultas que el rol puede usar y que tienen handler."""
    return {
        nombre: datos
        for nombre, datos in CONSULTAS.items()
        if rol in datos["roles"] and datos.get("handler")
    }
