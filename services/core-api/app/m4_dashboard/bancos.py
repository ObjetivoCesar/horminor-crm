"""Cuentas bancarias y su detalle (v6.11).

El saldo contable sale de ``v_balance_general`` (libro mayor, cuenta hija por
banco). Los movimientos salen de ``payments`` asignados a esa cuenta. Los
préstamos salen de ``financial_liabilities`` por ``bank_account_id`` o por el
nombre de la entidad. Si no hay datos, se devuelve 0/lista vacía: nunca se
inventa un saldo.
"""

from __future__ import annotations

from typing import Any

import asyncpg

_CAMPOS_BANCO = """
    b.id::text, b.slug, b.nombre, b.tipo_cuenta, b.numero_cuenta,
    b.titular, b.moneda, b.estado, b.saldo_informado,
    b.saldo_informado_at, b.notas, b.accounting_account_id::text,
    COALESCE(v.saldo_neto, 0) AS saldo_contable
"""

_MATCH_PRESTAMO = """
    (f.bank_account_id = b.id
     OR (f.bank_account_id IS NULL
         AND lower(f.entidad_financiera) LIKE '%' || b.slug || '%'))
"""


def _f(valor: Any) -> float:
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def _iso(valor: Any) -> str | None:
    return valor.isoformat() if valor is not None else None


async def listar(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    filas = await pool.fetch(
        f"""
        SELECT {_CAMPOS_BANCO},
               (SELECT count(*) FROM financial_liabilities f
                 WHERE f.deleted_at IS NULL AND {_MATCH_PRESTAMO}) AS prestamos_count,
               (SELECT COALESCE(sum(f.saldo_capital_actual), 0)
                  FROM financial_liabilities f
                 WHERE f.deleted_at IS NULL AND {_MATCH_PRESTAMO}) AS prestamos_saldo
          FROM bank_accounts b
          LEFT JOIN v_balance_general v ON v.account_id = b.accounting_account_id
         ORDER BY array_position(
                      ARRAY['pichincha', 'guayaquil', 'internacional']::text[], b.slug
                  ),
                  b.slug
        """
    )
    return [
        {
            "id": fila["id"],
            "slug": fila["slug"],
            "nombre": fila["nombre"],
            "tipo_cuenta": fila["tipo_cuenta"],
            "numero_cuenta": fila["numero_cuenta"],
            "titular": fila["titular"],
            "moneda": fila["moneda"],
            "estado": fila["estado"],
            "saldo_contable": _f(fila["saldo_contable"]),
            "saldo_informado": _f(fila["saldo_informado"]) if fila["saldo_informado"] is not None else None,
            "saldo_informado_at": _iso(fila["saldo_informado_at"]),
            "prestamos_count": int(fila["prestamos_count"] or 0),
            "prestamos_saldo": _f(fila["prestamos_saldo"]),
        }
        for fila in filas
    ]


async def detalle(pool: asyncpg.Pool, slug: str) -> dict[str, Any] | None:
    banco = await pool.fetchrow(
        f"""
        SELECT {_CAMPOS_BANCO}
          FROM bank_accounts b
          LEFT JOIN v_balance_general v ON v.account_id = b.accounting_account_id
         WHERE b.slug = $1 OR b.id::text = $1
        """,
        slug,
    )
    if banco is None:
        return None

    prestamos = await pool.fetch(
        """
        SELECT f.id::text, f.entidad_financiera, f.numero_operacion,
               f.fecha_desembolso, f.monto_original, f.saldo_capital_actual,
               f.tasa_interes_anual_pct, f.cuota_mensual_referencial,
               f.plazo_restante_meses,
               (SELECT count(*) FROM loan_payments lp WHERE lp.liability_id = f.id) AS pagos
          FROM financial_liabilities f
         WHERE f.deleted_at IS NULL
           AND (f.bank_account_id = $1
                OR (f.bank_account_id IS NULL
                    AND lower(f.entidad_financiera) LIKE '%' || $2 || '%'))
         ORDER BY f.fecha_desembolso DESC
         LIMIT 50
        """,
        banco["id"],
        banco["slug"],
    )

    movimientos: list[asyncpg.Record] = []
    if banco["accounting_account_id"]:
        movimientos = await pool.fetch(
            """
            SELECT p.fecha, p.tipo_movimiento, p.metodo, p.monto, p.referencia,
                   p.es_anticipo, p.created_at,
                   c.nombre AS cliente_nombre, o.numero AS orden_numero
              FROM payments p
              LEFT JOIN clients c ON c.id = p.cliente_id
              LEFT JOIN orders o ON o.id = p.order_id
             WHERE p.account_id = $1::uuid
               AND p.deleted_at IS NULL
             ORDER BY p.fecha DESC, p.created_at DESC
             LIMIT 50
            """,
            banco["accounting_account_id"],
        )

    entradas = sum(
        _f(m["monto"]) for m in movimientos if m["tipo_movimiento"] == "COBRO"
    )
    salidas = sum(
        _f(m["monto"])
        for m in movimientos
        if m["tipo_movimiento"] in ("GASTO_BANCARIO", "GASTO_CAJA_CHICA")
    )
    prestamos_saldo = sum(_f(p["saldo_capital_actual"]) for p in prestamos)
    prestamos_cuota = sum(_f(p["cuota_mensual_referencial"]) for p in prestamos)

    return {
        "banco": {
            "id": banco["id"],
            "slug": banco["slug"],
            "nombre": banco["nombre"],
            "tipo_cuenta": banco["tipo_cuenta"],
            "numero_cuenta": banco["numero_cuenta"],
            "titular": banco["titular"],
            "moneda": banco["moneda"],
            "estado": banco["estado"],
            "saldo_contable": _f(banco["saldo_contable"]),
            "saldo_informado": _f(banco["saldo_informado"]) if banco["saldo_informado"] is not None else None,
            "saldo_informado_at": _iso(banco["saldo_informado_at"]),
            "notas": banco["notas"],
        },
        "resumen": {
            "saldo_contable": _f(banco["saldo_contable"]),
            "saldo_informado": _f(banco["saldo_informado"]) if banco["saldo_informado"] is not None else None,
            "entradas": entradas,
            "salidas": salidas,
            "movimientos_count": len(movimientos),
            "prestamos_count": len(prestamos),
            "prestamos_saldo": prestamos_saldo,
            "prestamos_cuota": prestamos_cuota,
        },
        "prestamos": [
            {
                "id": p["id"],
                "entidad": p["entidad_financiera"],
                "numero_operacion": p["numero_operacion"],
                "fecha_desembolso": _iso(p["fecha_desembolso"]),
                "monto_original": _f(p["monto_original"]),
                "saldo_capital": _f(p["saldo_capital_actual"]),
                "tasa_pct": _f(p["tasa_interes_anual_pct"]),
                "cuota": _f(p["cuota_mensual_referencial"]),
                "plazo_meses": int(p["plazo_restante_meses"] or 0),
                "pagos": int(p["pagos"] or 0),
            }
            for p in prestamos
        ],
        "movimientos": [
            {
                "fecha": _iso(m["fecha"]),
                "tipo": m["tipo_movimiento"],
                "metodo": m["metodo"],
                "monto": _f(m["monto"]),
                "referencia": m["referencia"],
                "es_anticipo": bool(m["es_anticipo"]),
                "cliente": m["cliente_nombre"],
                "orden": m["orden_numero"],
            }
            for m in movimientos
        ],
    }


async def actualizar(
    pool: asyncpg.Pool, slug: str, datos: dict[str, Any]
) -> dict[str, Any] | None:
    """Actualiza solo campos permitidos; el saldo informado lo carga Gerencia."""
    permitidos = {
        "numero_cuenta",
        "tipo_cuenta",
        "saldo_informado",
        "titular",
        "notas",
        "estado",
    }
    asignaciones: list[str] = []
    valores: list[Any] = []
    for campo, valor in datos.items():
        if campo not in permitidos:
            continue
        asignaciones.append(f"{campo} = ${len(valores) + 1}")
        valores.append(valor)
    if "saldo_informado" in datos:
        asignaciones.append(
            "saldo_informado_at = NULL"
            if datos["saldo_informado"] is None
            else "saldo_informado_at = now()"
        )
    if not asignaciones:
        return await detalle(pool, slug)
    asignaciones.append("updated_at = now()")
    valores.append(slug)
    fila = await pool.fetchrow(
        f"""
        UPDATE bank_accounts
           SET {', '.join(asignaciones)}
         WHERE slug = ${len(valores)} OR id::text = ${len(valores)}
        RETURNING id
        """,
        *valores,
    )
    if fila is None:
        return None
    return await detalle(pool, slug)
