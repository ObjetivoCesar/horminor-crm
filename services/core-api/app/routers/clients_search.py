"""Buscador "Sabueso" de clientes y expedientes (v6.6).

Endpoints:
- ``GET /api/v1/clients/search``: busqueda multi-variable con paginacion,
  normalizacion ortografica/fonetica y coincidencia por trabajo/venta.
- ``PUT /api/v1/clients/{cliente_id}``: ficha editable del cliente.

La logica vive en SQL para no traer cientos de filas a Python. La
normalizacion convierte tildes y aplica equivalencias hispanas simples
(b/v, z/s/c, ll/y) tanto al texto guardado como a la busqueda.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from typing import Any, Mapping

import asyncpg
from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ..panel_acl import exigir_modulo

router = APIRouter(prefix="/api/v1", tags=["clientes"])


def _pool(request: Request) -> asyncpg.Pool:
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="base de datos no disponible")
    return pool


def norm_texto(valor: Any) -> str:
    """Minusculas, sin tildes y con equivalencias foneticas simples."""
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    for viejo, nuevo in (("v", "b"), ("z", "s"), ("c", "s"), ("ll", "y")):
        texto = texto.replace(viejo, nuevo)
    return texto


def _norm_sql(col: str) -> str:
    return (
        "replace(replace(replace(replace("
        f"translate(lower(coalesce({col}, '')), 'áéíóúüñ', 'aeiouun')"
        ", 'v', 'b'), 'z', 's'), 'c', 's'), 'll', 'y')"
    )


def _query_compacta(q: str) -> str:
    texto = re.sub(r"(\d)\s+m3", r"\1m3", str(q or ""), flags=re.I)
    texto = re.sub(r"fc\s*-?\s*(\d{3})", r"fc-\1", texto, flags=re.I)
    texto = re.sub(r"#\s+(\d+)", r"#\1", texto)
    return texto


def _tokens(q: str) -> list[str]:
    return [tok for tok in norm_texto(_query_compacta(q)).split() if tok]


def _filtros_busqueda(q: str) -> tuple[list[str], list[Any], list[str]]:
    """Devuelve condiciones SQL, parametros y patrones de trabajo."""
    condiciones: list[str] = []
    valores: list[Any] = []
    patrones: list[str] = []
    for crudo in _query_compacta(q).lower().split():
        token = norm_texto(crudo)
        orden = re.fullmatch(r"#(\d+)", crudo)
        volumen = re.fullmatch(r"(\d+(?:\.\d+)?)\s*m3", crudo)
        resistencia = re.fullmatch(r"fc-?(\d{3})", crudo) or re.fullmatch(
            r"fs-?(\d{3})", token
        )
        if orden:
            numero = int(orden.group(1))
            condiciones.append(
                "EXISTS (SELECT 1 FROM orders o WHERE o.cliente_id = c.id "
                "AND o.numero = $%d)" % (len(valores) + 1)
            )
            valores.append(numero)
            patrones.append(f"orden:{numero}")
            continue
        if volumen:
            cantidad = float(volumen.group(1))
            idx1 = len(valores) + 1
            valores.append(cantidad - 0.01)
            idx2 = len(valores) + 1
            valores.append(cantidad + 0.01)
            condiciones.append(
                "(EXISTS (SELECT 1 FROM orders o WHERE o.cliente_id = c.id "
                f"AND o.volumen_m3 BETWEEN ${idx1} AND ${idx2}) "
                "OR EXISTS (SELECT 1 FROM dispatch_schedule d WHERE d.cliente_id = c.id "
                f"AND d.volumen_m3 BETWEEN ${idx1} AND ${idx2}))"
            )
            patrones.append(f"m3:{cantidad:g}")
            continue
        if resistencia:
            sufijo = resistencia.group(1)
            condiciones.append(
                "EXISTS (SELECT 1 FROM orders o WHERE o.cliente_id = c.id "
                f"AND {_norm_sql('o.resistencia')} LIKE $%d)" % (len(valores) + 1)
            )
            valores.append(f"%{norm_texto(sufijo)}%")
            patrones.append(f"fc:{sufijo}")
            continue
        # Texto libre: nombre, constructora, ciudad, obra, notas, orden, guia o pago.
        idx = len(valores) + 1
        valores.append(f"%{token}%")
        condiciones.append(
            "(" +
            " OR ".join(
                [
                    f"{_norm_sql('c.nombre')} LIKE ${idx}",
                    f"{_norm_sql('c.constructora')} LIKE ${idx}",
                    f"{_norm_sql('c.ciudad')} LIKE ${idx}",
                    f"{_norm_sql('c.direccion_obra')} LIKE ${idx}",
                    f"{_norm_sql('c.notas')} LIKE ${idx}",
                    "EXISTS (SELECT 1 FROM orders o WHERE o.cliente_id = c.id "
                    f"AND ({_norm_sql('o.notas')} LIKE ${idx} OR {_norm_sql('o.resistencia')} LIKE ${idx}))",
                    "EXISTS (SELECT 1 FROM dispatch_schedule d WHERE d.cliente_id = c.id "
                    f"AND ({_norm_sql('d.direccion_obra')} LIKE ${idx} OR {_norm_sql('d.notas')} LIKE ${idx}))",
                    "EXISTS (SELECT 1 FROM payments p WHERE p.cliente_id = c.id "
                    f"AND p.deleted_at IS NULL AND {_norm_sql('p.referencia')} LIKE ${idx})",
                ]
            ) + ")"
        )
        patrones.append(f"texto:{token}")
    return condiciones, valores, patrones


def _rango_fechas(
    periodo: str | None, desde: date | None, hasta: date | None
) -> tuple[date | None, date | None]:
    hoy = date.today()
    if desde or hasta:
        return desde, hasta
    if not periodo or periodo.upper() == "TODO":
        return None, None
    if periodo.upper() == "HOY":
        return hoy, hoy
    if periodo.upper() == "SEMANA":
        inicio = hoy - timedelta(days=hoy.weekday())
        return inicio, inicio + timedelta(days=6)
    if periodo.upper() == "MES":
        return hoy.replace(day=1), hoy.replace(day=28) + timedelta(days=4)
    return None, None


_ULTIMA_ACTIVIDAD = """GREATEST(
    COALESCE((SELECT max(o.created_at) FROM orders o WHERE o.cliente_id = c.id), 'epoch'::timestamptz),
    COALESCE((SELECT max(p.created_at) FROM payments p WHERE p.cliente_id = c.id AND p.deleted_at IS NULL), 'epoch'::timestamptz),
    COALESCE((SELECT max(d.created_at) FROM dispatch_schedule d WHERE d.cliente_id = c.id AND d.deleted_at IS NULL), 'epoch'::timestamptz)
)"""


def _select_base() -> str:
    return f"""
        SELECT c.id::text AS cliente_id, c.nombre, c.constructora, c.ruc,
               c.telefono_whatsapp AS telefono, c.estado, c.provincia,
               c.ciudad, c.direccion_obra, c.notas, c.credit_limit_usd,
               COALESCE(s.total_m3, 0) AS total_m3,
               COALESCE(s.total_facturado, 0) AS total_facturado,
               COALESCE(s.total_cobrado, 0) AS total_cobrado,
               COALESCE(s.total_fiado, 0) AS total_fiado,
               COALESCE(s.saldo_pendiente, 0) AS saldo_pendiente,
               COALESCE(s.saldo_a_favor, 0) AS saldo_a_favor,
               {_ULTIMA_ACTIVIDAD} AS ultima_actividad,
               (SELECT count(*) FROM orders o WHERE o.cliente_id = c.id) AS total_ordenes,
               (c.estado = 'PROSPECTO') AS es_prospecto
          FROM clients c
          LEFT JOIN v_cliente_saldo s ON s.id = c.id
    """


def _where_filtros(
    *,
    grupo: str,
    ciudad: str | None,
    pago: str | None,
    resistencia: str | None,
    m3_min: float | None,
    m3_max: float | None,
    desde: date | None,
    hasta: date | None,
    q: str,
) -> tuple[list[str], list[Any]]:
    condiciones: list[str] = []
    valores: list[Any] = []
    grupo = (grupo or "TODOS").upper()
    if grupo == "DEUDA":
        condiciones.append("COALESCE(s.saldo_pendiente, 0) > 0")
    elif grupo == "OBRA":
        condiciones.append(
            "(EXISTS (SELECT 1 FROM orders o WHERE o.cliente_id = c.id "
            "AND o.estado <> 'ANULADA' AND o.created_at >= now() - interval '90 days') "
            "OR EXISTS (SELECT 1 FROM dispatch_schedule d WHERE d.cliente_id = c.id "
            "AND d.deleted_at IS NULL AND d.estado NOT IN ('CANCELADO','REAGENDADO') "
            "AND d.fecha_entrega BETWEEN current_date - 7 AND current_date + 30))"
        )
    elif grupo == "PAGOS":
        condiciones.append(
            "(EXISTS (SELECT 1 FROM payments p WHERE p.cliente_id = c.id "
            "AND p.deleted_at IS NULL AND p.tipo_movimiento = 'COBRO') "
            "OR COALESCE(s.saldo_a_favor, 0) > 0)"
        )
    elif grupo == "PROSPECTOS":
        condiciones.append("c.estado = 'PROSPECTO'")

    if ciudad:
        idx = len(valores) + 1
        valores.append(f"%{norm_texto(ciudad)}%")
        condiciones.append(
            f"({_norm_sql('c.ciudad')} LIKE ${idx} OR {_norm_sql('c.provincia')} LIKE ${idx})"
        )

    pago = (pago or "TODOS").upper()
    if pago in {"TRANSFERENCIA", "EFECTIVO"}:
        idx = len(valores) + 1
        valores.append(pago)
        condiciones.append(
            "EXISTS (SELECT 1 FROM payments p WHERE p.cliente_id = c.id "
            f"AND p.deleted_at IS NULL AND p.metodo = ${idx} AND p.tipo_movimiento = 'COBRO')"
        )
    elif pago == "FIADO":
        condiciones.append(
            "(COALESCE(s.total_fiado, 0) > 0 OR EXISTS ("
            "SELECT 1 FROM orders o WHERE o.cliente_id = c.id AND o.forma_pago = 'FIADO'))"
        )
    elif pago == "ANTICIPO":
        condiciones.append(
            "(COALESCE(s.saldo_a_favor, 0) > 0 OR EXISTS ("
            "SELECT 1 FROM payments p WHERE p.cliente_id = c.id "
            "AND p.deleted_at IS NULL AND p.es_anticipo = true))"
        )

    if resistencia:
        idx = len(valores) + 1
        valores.append(f"%{norm_texto(resistencia)}%")
        condiciones.append(
            "EXISTS (SELECT 1 FROM orders o WHERE o.cliente_id = c.id "
            f"AND {_norm_sql('o.resistencia')} LIKE ${idx})"
        )

    if m3_min is not None or m3_max is not None:
        idx1 = len(valores) + 1
        valores.append(m3_min if m3_min is not None else 0)
        idx2 = len(valores) + 1
        valores.append(m3_max if m3_max is not None else 99999)
        condiciones.append(
            "EXISTS (SELECT 1 FROM orders o WHERE o.cliente_id = c.id "
            f"AND o.volumen_m3 BETWEEN ${idx1} AND ${idx2})"
        )

    if desde is not None:
        idx = len(valores) + 1
        valores.append(desde)
        condiciones.append(f"({_ULTIMA_ACTIVIDAD})::date >= ${idx}")
    if hasta is not None:
        idx = len(valores) + 1
        valores.append(hasta)
        condiciones.append(f"({_ULTIMA_ACTIVIDAD})::date <= ${idx}")

    busqueda, valores_q, _ = _filtros_busqueda(q)
    if busqueda:
        # Los indices de los parametros de busqueda empiezan despues de los filtros.
        offset = len(valores)
        for cond in busqueda:
            condiciones.append(re.sub(r"\$(\d+)", lambda m: f"${int(m.group(1)) + offset}", cond))
        valores.extend(valores_q)
    return condiciones, valores


def _orden_sql(orden: str) -> str:
    orden = (orden or "DEUDA").upper()
    if orden == "ACTIVIDAD":
        return f"({_ULTIMA_ACTIVIDAD}) DESC NULLS LAST, c.nombre"
    if orden == "VOLUMEN":
        return "COALESCE(s.total_m3, 0) DESC, c.nombre"
    if orden == "NOMBRE":
        return "c.nombre ASC"
    return "COALESCE(s.saldo_pendiente, 0) DESC, c.nombre"


def _compacto(valor: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", norm_texto(valor))


def _coincide_orden(q: str, orden: Mapping[str, Any]) -> bool:
    if not q.strip():
        return False
    crudos = _query_compacta(q).lower().split()
    for crudo in crudos:
        token = _compacto(crudo)
        match_orden = re.fullmatch(r"#(\d+)", crudo)
        match_vol = re.fullmatch(r"(\d+(?:\.\d+)?)\s*m3", crudo)
        match_res = re.fullmatch(r"fc-?(\d{3})", crudo) or re.fullmatch(
            r"fs-?(\d{3})", token
        )
        if match_orden:
            if int(orden.get("numero") or 0) != int(match_orden.group(1)):
                return False
            continue
        if match_vol:
            cantidad = float(match_vol.group(1))
            if abs(float(orden.get("volumen_m3") or 0) - cantidad) > 0.01:
                return False
            continue
        if match_res:
            if match_res.group(1) not in _compacto(orden.get("resistencia")):
                return False
            continue
        if token and token not in _compacto(
            f"{orden.get('notas') or ''} {orden.get('resistencia') or ''} "
            f"{orden.get('numero') or ''} {orden.get('volumen_m3') or ''}"
        ):
            return False
    return True


def _coincide_texto(q: str, *partes: Any) -> bool:
    if not q.strip():
        return False
    haystack = _compacto(" ".join(str(p or "") for p in partes))
    for crudo in _query_compacta(q).lower().split():
        if re.fullmatch(r"#\d+", crudo) or re.fullmatch(r"(\d+(?:\.\d+)?)\s*m3", crudo):
            continue
        if re.fullmatch(r"fc-?\d{3}", crudo):
            continue
        token = _compacto(crudo)
        if token and token not in haystack:
            return False
    return True


async def _match_hints(
    pool: asyncpg.Pool,
    ids: list[str],
    q: str,
) -> dict[str, str]:
    if not ids or not q.strip():
        return {}
    ordenes = await pool.fetch(
        """
        SELECT cliente_id::text, numero, volumen_m3, resistencia, notas, created_at
          FROM orders WHERE cliente_id = ANY($1::uuid[])
         ORDER BY created_at DESC LIMIT 300
        """,
        ids,
    )
    entregas = await pool.fetch(
        """
        SELECT cliente_id::text, fecha_entrega, volumen_m3, direccion_obra, notas
          FROM dispatch_schedule
         WHERE cliente_id = ANY($1::uuid[]) AND deleted_at IS NULL
         ORDER BY fecha_entrega DESC LIMIT 300
        """,
        ids,
    )
    pagos = await pool.fetch(
        """
        SELECT cliente_id::text, fecha, metodo, monto, referencia
          FROM payments
         WHERE cliente_id = ANY($1::uuid[]) AND deleted_at IS NULL
         ORDER BY fecha DESC LIMIT 300
        """,
        ids,
    )
    hints: dict[str, str] = {}
    for fila in ordenes:
        cid = str(fila["cliente_id"])
        if cid in hints or not _coincide_orden(q, fila):
            continue
        hints[cid] = (
            f"Orden #{fila['numero']} · {float(fila['volumen_m3']):g} m³ "
            f"{fila['resistencia']} · {fila['created_at'].strftime('%d/%m/%Y')}"
        )
    for fila in entregas:
        cid = str(fila["cliente_id"])
        if cid in hints or not _coincide_texto(
            q, fila["direccion_obra"], fila["notas"], fila["fecha_entrega"]
        ):
            continue
        hints[cid] = (
            f"Entrega {fila['fecha_entrega'].strftime('%d/%m/%Y')} · "
            f"{float(fila['volumen_m3']):g} m³ · {fila['direccion_obra'] or 'sin dirección'}"
        )
    for fila in pagos:
        cid = str(fila["cliente_id"])
        if cid in hints or not _coincide_texto(
            q, fila["metodo"], fila["referencia"], fila["fecha"]
        ):
            continue
        hints[cid] = (
            f"Pago {fila['metodo']} {fila['fecha'].strftime('%d/%m/%Y')} · "
            f"${float(fila['monto']):,.2f}"
        )
    return hints


class ClienteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=160)
    constructora: str | None = Field(default=None, max_length=160)
    ruc: str | None = Field(default=None, max_length=40)
    telefono_whatsapp: str | None = Field(default=None, max_length=40)
    provincia: str | None = Field(default=None, max_length=80)
    ciudad: str | None = Field(default=None, max_length=120)
    direccion_obra: str | None = Field(default=None, max_length=240)
    credit_limit_usd: float | None = Field(default=None, ge=0)
    notas: str | None = Field(default=None, max_length=500)


@router.get("/clients/search")
async def buscar_clientes(
    request: Request,
    q: str = Query(default=""),
    grupo: str = Query(default="TODOS"),
    ciudad: str | None = Query(default=None),
    pago: str | None = Query(default=None),
    resistencia: str | None = Query(default=None),
    m3_min: float | None = Query(default=None, ge=0),
    m3_max: float | None = Query(default=None, ge=0),
    periodo: str | None = Query(default=None),
    desde: date | None = Query(default=None),
    hasta: date | None = Query(default=None),
    orden: str = Query(default="DEUDA"),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=12, ge=5, le=50),
) -> dict[str, Any]:
    await exigir_modulo(request, "clientes_cartera")
    pool = _pool(request)
    desde, hasta = _rango_fechas(periodo, desde, hasta)
    condiciones, valores = _where_filtros(
        grupo=grupo, ciudad=ciudad, pago=pago, resistencia=resistencia,
        m3_min=m3_min, m3_max=m3_max, desde=desde, hasta=hasta, q=q,
    )
    where = " WHERE " + " AND ".join(condiciones) if condiciones else ""
    base = _select_base() + where
    total = await pool.fetchval(f"SELECT count(*) FROM ({base}) x", *valores)
    offset = (pagina - 1) * por_pagina
    filas = await pool.fetch(
        f"{base} ORDER BY {_orden_sql(orden)} LIMIT ${len(valores)+1} OFFSET ${len(valores)+2}",
        *valores, por_pagina, offset,
    )
    ids = [str(f["cliente_id"]) for f in filas]
    hints = await _match_hints(pool, ids, q)

    resumen = await pool.fetchrow(
        """
        SELECT
          (SELECT count(*) FROM v_cliente_saldo WHERE saldo_pendiente > 0) AS deuda_clientes,
          (SELECT COALESCE(sum(saldo_pendiente), 0) FROM v_cliente_saldo WHERE saldo_pendiente > 0) AS deuda_monto,
          (SELECT count(*) FROM clients c WHERE
             EXISTS (SELECT 1 FROM orders o WHERE o.cliente_id = c.id
                     AND o.estado <> 'ANULADA' AND o.created_at >= now() - interval '90 days')
             OR EXISTS (SELECT 1 FROM dispatch_schedule d WHERE d.cliente_id = c.id
                        AND d.deleted_at IS NULL AND d.estado NOT IN ('CANCELADO','REAGENDADO')
                        AND d.fecha_entrega BETWEEN current_date - 7 AND current_date + 30)) AS obra_clientes,
          (SELECT count(*) FROM clients c WHERE
             EXISTS (SELECT 1 FROM payments p WHERE p.cliente_id = c.id
                     AND p.deleted_at IS NULL AND p.tipo_movimiento = 'COBRO')
             OR COALESCE((SELECT saldo_a_favor FROM v_cliente_saldo s WHERE s.id = c.id), 0) > 0) AS pagos_clientes,
          (SELECT count(*) FROM clients) AS todos_clientes,
          (SELECT count(*) FROM clients WHERE estado = 'PROSPECTO') AS prospectos
        """
    )
    ciudades = await pool.fetch(
        """
        SELECT DISTINCT COALESCE(NULLIF(trim(ciudad), ''), NULLIF(trim(provincia), '')) AS ciudad
          FROM clients
         WHERE COALESCE(NULLIF(trim(ciudad), ''), NULLIF(trim(provincia), '')) IS NOT NULL
         ORDER BY ciudad
        """
    )
    resistencias = await pool.fetch(
        "SELECT DISTINCT resistencia FROM orders ORDER BY resistencia"
    )
    clientes = [
        {
            **dict(fila),
            "match_hint": hints.get(str(fila["cliente_id"])),
        }
        for fila in filas
    ]
    return {
        "clientes": clientes,
        "paginacion": {
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total": total,
            "paginas": max(1, (int(total) + por_pagina - 1) // por_pagina),
        },
        "resumen": dict(resumen),
        "filtros": {
            "ciudades": [f["ciudad"] for f in ciudades],
            "resistencias": [f["resistencia"] for f in resistencias],
        },
    }


@router.put("/clients/{cliente_id}")
async def actualizar_cliente(
    request: Request,
    cliente_id: str,
    body: ClienteUpdate = Body(...),
) -> dict[str, Any]:
    await exigir_modulo(request, "clientes_cartera", mutacion=True)
    datos = body.model_dump(exclude_unset=True)
    if not datos:
        raise HTTPException(status_code=422, detail="nada que actualizar")
    columnas = {
        "nombre": "nombre",
        "constructora": "constructora",
        "ruc": "ruc",
        "telefono_whatsapp": "telefono_whatsapp",
        "provincia": "provincia",
        "ciudad": "ciudad",
        "direccion_obra": "direccion_obra",
        "credit_limit_usd": "credit_limit_usd",
        "notas": "notas",
    }
    asignaciones = []
    valores: list[Any] = []
    for campo, valor in datos.items():
        if campo not in columnas:
            continue
        asignaciones.append(f"{columnas[campo]} = ${len(valores)+1}")
        valores.append(valor)
    valores.append(cliente_id)
    fila = await _pool(request).fetchrow(
        f"""
        UPDATE clients SET {', '.join(asignaciones)}
         WHERE id = ${len(valores)}
        RETURNING id::text, nombre, constructora, ruc, telefono_whatsapp,
                  provincia, ciudad, direccion_obra, credit_limit_usd, notas
        """,
        *valores,
    )
    if fila is None:
        raise HTTPException(status_code=404, detail="cliente no encontrado")
    return dict(fila)
