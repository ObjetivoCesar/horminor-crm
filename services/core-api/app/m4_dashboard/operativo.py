"""Consultas del dashboard operativo: inventario y cobranza.

Regla del tablero: cada respuesta dice de que fuente sale, cuando se consulto y
por que esta vacia. Un cero sin explicacion es un dato falso.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import asyncpg

# Materiales del tablero. El agua no es stock: sigue en la receta y en el costo.
MATERIALES_TABLERO: tuple[str, ...] = ("CEMENTO", "ARENA", "RIPIO", "RETARDANTE")

CUBOS_COBRANZA: tuple[str, ...] = (
    "VENCIDA",
    "POR_VENCER_7",
    "CORRIENTE",
    "SIN_VENCIMIENTO",
)


def _texto(valor: Any) -> str | None:
    """Decimal -> texto, para no viajar como float."""
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return f"{valor:.4f}".rstrip("0").rstrip(".")
    return str(valor)


def _ahora() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


async def inventario(pool: asyncpg.Pool) -> dict[str, Any]:
    filas = await pool.fetch(
        """
        SELECT codigo, nombre, unidad,
               stock_real_fisico,
               stock_proyectado_disponible,
               stock_minimo,
               ultimo_levantamiento_at,
               estado_alerta_proyectada
          FROM v_stock_proyectado
         WHERE codigo = ANY($1::text[])
         ORDER BY array_position($1::text[], codigo)
        """,
        list(MATERIALES_TABLERO),
    )

    materiales = [
        {
            "codigo": f["codigo"],
            "nombre": f["nombre"],
            "unidad": f["unidad"],
            "stock": _texto(f["stock_proyectado_disponible"]),
            "stock_real": _texto(f["stock_real_fisico"]),
            "stock_minimo": _texto(f["stock_minimo"]),
            "ultimo_conteo": f["ultimo_levantamiento_at"].isoformat()
            if f["ultimo_levantamiento_at"]
            else None,
            "estado": f["estado_alerta_proyectada"],
        }
        for f in filas
    ]

    sin_conteo = [m for m in materiales if m["estado"] in ("SIN_LEVANTAR", "SIN_FECHA_CONTEO")]
    vacio = None
    if not materiales:
        vacio = {
            "motivo": "SIN_MATERIALES",
            "mensaje": "No hay materiales configurados para el tablero.",
        }
    elif len(sin_conteo) == len(materiales):
        vacio = {
            "motivo": "SIN_CONTEO_FISICO",
            "mensaje": "Ningun material tiene fecha de conteo. El stock es de semilla.",
        }

    return {
        "fuente": ["v_stock_proyectado"],
        "consultado": _ahora(),
        "filtros": {"materiales": list(MATERIALES_TABLERO), "incluye_agua": False},
        "datos": {"materiales": materiales, "sin_conteo": len(sin_conteo)},
        "vacio": vacio,
    }


async def cobranza(pool: asyncpg.Pool, limite_clientes: int = 8) -> dict[str, Any]:
    cubos_filas = await pool.fetch(
        """
        SELECT tipo, estado_vencimiento,
               count(*) AS documentos,
               COALESCE(sum(monto_documento), 0) AS monto
          FROM v_cobranza_documentos
         GROUP BY tipo, estado_vencimiento
         ORDER BY tipo, estado_vencimiento
        """
    )

    cubos: dict[str, dict[str, Any]] = {
        cubo: {"estado": cubo, "documentos": 0, "monto": "0"} for cubo in CUBOS_COBRANZA
    }
    for fila in cubos_filas:
        estado = fila["estado_vencimiento"]
        actual = cubos.setdefault(
            estado, {"estado": estado, "documentos": 0, "monto": "0"}
        )
        actual["documentos"] += int(fila["documentos"])
        actual["monto"] = _texto(
            Decimal(actual["monto"] or 0) + Decimal(fila["monto"] or 0)
        )

    clientes = await pool.fetch(
        """
        SELECT nombre, total_facturado, saldo_pendiente
          FROM v_cliente_saldo
         WHERE saldo_pendiente > 0
         ORDER BY saldo_pendiente DESC, nombre
         LIMIT $1
        """,
        limite_clientes,
    )

    saldo_filas = await pool.fetch(
        "SELECT COALESCE(sum(saldo_pendiente), 0) AS saldo FROM v_cliente_saldo"
    )
    saldo_total = _texto(saldo_filas[0]["saldo"]) if saldo_filas else "0"

    documentos = sum(c["documentos"] for c in cubos.values())
    vacio = None
    if documentos == 0:
        vacio = {
            "motivo": "SIN_DOCUMENTOS",
            "mensaje": "No hay ordenes ni facturas por cobrar.",
        }
    elif all(cubo["documentos"] == 0 for k, cubo in cubos.items() if k != "SIN_VENCIMIENTO"):
        vacio = {
            "motivo": "SIN_FECHAS_CAPTURADAS",
            "mensaje": "Ningun documento tiene fecha de vencimiento; no se puede calcular antiguedad.",
        }

    return {
        "fuente": ["v_cobranza_documentos", "v_cliente_saldo"],
        "consultado": _ahora(),
        "filtros": {"limite_clientes": limite_clientes},
        "datos": {
            "cubos": [cubos[c] for c in CUBOS_COBRANZA if c in cubos],
            "clientes": [
                {
                    "nombre": f["nombre"],
                    "facturado": _texto(f["total_facturado"]),
                    "saldo": _texto(f["saldo_pendiente"]),
                }
                for f in clientes
            ],
            "saldo_total": saldo_total,
            "documentos": documentos,
        },
        "vacio": vacio,
    }
