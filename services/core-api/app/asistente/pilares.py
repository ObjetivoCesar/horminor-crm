"""Pilares que gobiernan las consultas del bibliotecario."""

from __future__ import annotations

from typing import Any

PILARES: dict[str, dict[str, Any]] = {
    "cartera-cobros": {
        "descripcion": "Saldos, cupos, cobros y estado de órdenes.",
        "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA"),
        "acciones": {
            "cartera_total": {
                "consulta": "cartera_total",
                "roles": ("SUPERADMIN", "CONTADORA"),
                "descripcion": "Lista de clientes con saldo y total por cobrar.",
            },
            "cliente_saldo": {
                "consulta": "cartera_cliente",
                "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA"),
                "descripcion": "Saldo, fiado, cobrado y cupo de un cliente.",
                "pasos": ("cliente_buscar", "cartera_cliente"),
            },
            "cliente_ficha": {
                "consulta": "cliente_ficha",
                "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA"),
                "descripcion": "Ficha completa de un cliente.",
            },
            "facturas_cliente": {
                "consulta": "cliente_facturas",
                "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA"),
                "descripcion": (
                    "Facturas internas (PDF o foto) adjuntas a un cliente. "
                    "No son comprobantes electrónicos del SRI."
                ),
                "pasos": ("cliente_buscar", "cliente_facturas"),
            },
            "orden_estado": {
                "consulta": "orden_timeline",
                "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA", "BODEGA"),
                "descripcion": "Estado de una orden por número (no uses el número de una resistencia FC).",
            },
            "orden_cliente": {
                "consulta": "orden_timeline",
                "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA", "BODEGA"),
                "descripcion": "Órdenes activas de un cliente por nombre o RUC.",
                "pasos": ("cliente_ordenes",),
            },
        },
    },
    "caja-cierre": {
        "descripcion": "Cierre de caja, cobros y gastos del día.",
        "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA"),
        "acciones": {
            "cierre_dia": {
                "consulta": "cierre_dia",
                "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA"),
                "descripcion": "Resumen del cierre de una fecha.",
            },
            "movimientos": {
                "consulta": "movimientos_dia",
                "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA"),
                "descripcion": "Cobros y gastos de un rango de fechas.",
            },
        },
    },
    "banca-mercado": {
        "descripcion": "Bancos, préstamos, cuota de mercado y simulador.",
        "roles": ("SUPERADMIN", "CONTADORA"),
        "acciones": {
            "banco_detalle": {
                "consulta": "banco_detalle",
                "roles": ("SUPERADMIN", "CONTADORA"),
                "descripcion": "Saldo contable, informado y préstamos de un banco.",
            },
            "banco_movimientos": {
                "consulta": "banco_movimientos",
                "roles": ("SUPERADMIN", "CONTADORA"),
                "descripcion": "Movimientos recientes de un banco.",
            },
            "cuota_mercado": {
                "consulta": "cuota_mercado",
                "roles": ("SUPERADMIN", "CONTADORA"),
                "descripcion": "Cuota de mercado por provincia.",
            },
        },
    },
    "planta-inventario": {
        "descripcion": "Stock, kardex y alertas de bodega.",
        "roles": ("SUPERADMIN", "CONTADORA", "BODEGA"),
        "acciones": {
            "stock_actual": {
                "consulta": "stock_actual",
                "roles": ("SUPERADMIN", "CONTADORA", "BODEGA"),
                "descripcion": "Stock actual y mínimo por material.",
            },
            "stock_proyectado": {
                "consulta": "stock_proyectado",
                "roles": ("SUPERADMIN", "CONTADORA", "BODEGA"),
                "descripcion": "Stock proyectado con consumos teóricos.",
            },
        },
    },
    "agenda-obras-visitas": {
        "descripcion": "Entregas de obra y citas comerciales.",
        "roles": ("SUPERADMIN", "SECRETARIA", "BODEGA"),
        "acciones": {
            "agenda_obras": {
                "consulta": "agenda_obras",
                "roles": ("SUPERADMIN", "SECRETARIA", "BODEGA"),
                "descripcion": "Entregas programadas en un rango de fechas.",
            },
            "disponibilidad": {
                "consulta": "disponibilidad_agenda",
                "roles": ("SUPERADMIN", "SECRETARIA", "BODEGA"),
                "descripcion": "Ocupación de mixers en una fecha.",
            },
            "viaje_estado": {
                "consulta": "viaje_estado",
                "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA", "BODEGA"),
                "descripcion": "Estado de un viaje por dispatch_id.",
            },
        },
    },
    "configuracion-precios": {
        "descripcion": "Empresa, recetas, precios y costos.",
        "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA"),
        "acciones": {
            "precios": {
                "consulta": "recetas_precio_publico",
                "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA"),
                "descripcion": "Precios por m³ sin IVA de las resistencias FC-180 a FC-350. No es una orden.",
            },
            "costo": {
                "consulta": "recetas_costo",
                "roles": ("SUPERADMIN", "CONTADORA"),
                "descripcion": "Costo y margen por receta (PROPUESTA).",
                "estado": "PROPUESTA",
            },
            "empresa_info": {
                "consulta": "empresa_info",
                "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA"),
                "descripcion": "RUC, horario, cobertura y datos públicos.",
            },
        },
    },
    "contabilidad-reportes": {
        "descripcion": "Balance, resultados y cuentas por pagar.",
        "roles": ("SUPERADMIN", "CONTADORA"),
        "acciones": {
            "balance": {
                "consulta": "balance",
                "roles": ("SUPERADMIN", "CONTADORA"),
                "descripcion": "Balance general por cuenta.",
            },
            "resultados": {
                "consulta": "resultados",
                "roles": ("SUPERADMIN", "CONTADORA"),
                "descripcion": "Estado de resultados por período.",
            },
        },
    },
    "compras-proveedores": {
        "descripcion": "Compras, recepciones y cuentas por pagar.",
        "roles": ("SUPERADMIN", "CONTADORA"),
        "acciones": {
            "compras_pendientes": {
                "consulta": "compras_pendientes",
                "roles": ("SUPERADMIN", "CONTADORA"),
                "descripcion": "Compras en tránsito y recepciones.",
            },
            "por_pagar": {
                "consulta": "por_pagar",
                "roles": ("SUPERADMIN", "CONTADORA"),
                "descripcion": "Saldo por pagar a proveedores.",
            },
        },
    },
    "pdf-cotizaciones": {
        "descripcion": "Consulta y emisión de cotizaciones.",
        "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA"),
        "acciones": {
            "consultar": {
                "consulta": "cotizacion_consultar",
                "roles": ("SUPERADMIN", "CONTADORA", "SECRETARIA"),
                "descripcion": "Estado y PDF de una cotización (PROPUESTA).",
                "estado": "PROPUESTA",
            },
        },
    },
    "salud-sistema": {
        "descripcion": "Centinela, errores y outbox.",
        "roles": ("SUPERADMIN",),
        "acciones": {
            "salud": {
                "consulta": "salud_sistema",
                "roles": ("SUPERADMIN",),
                "descripcion": "Salud del sistema y errores recientes.",
            },
        },
    },
}


def permite(pilar: str, accion: str, rol: str) -> bool:
    datos = PILARES.get(pilar, {})
    if rol not in datos.get("roles", ()):
        return False
    return rol in datos.get("acciones", {}).get(accion, {}).get("roles", ())


def accion(pilar: str, nombre: str) -> dict[str, Any]:
    return PILARES.get(pilar, {}).get("acciones", {}).get(nombre, {})


def pilares_para(rol: str) -> dict[str, dict[str, Any]]:
    """Pilares y acciones que el rol puede ejecutar."""
    salida: dict[str, dict[str, Any]] = {}
    for pilar, datos in PILARES.items():
        if rol not in datos["roles"]:
            continue
        acciones = {
            nombre: accion
            for nombre, accion in datos["acciones"].items()
            if rol in accion["roles"] and accion.get("estado") != "PROPUESTA"
        }
        if acciones:
            salida[pilar] = {"descripcion": datos["descripcion"], "acciones": acciones}
    return salida
