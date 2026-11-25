"""Agenda operativa de Bodega. Solo expone datos necesarios para preparar cargas."""

import json
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Request

from ..panel_acl import exigir_modulo, resolver_perfil
from ..tiempo import hoy

router = APIRouter(prefix="/api/v1/bodega", tags=["bodega"])

_CARGAS = """
    WITH agenda AS (
        SELECT DISTINCT ON (order_id) order_id, fecha_entrega, hora_inicio,
               direccion_obra, mixer_codigo, created_at, updated_at, reagendado_de_id
          FROM dispatch_schedule
         WHERE order_id IS NOT NULL AND deleted_at IS NULL
           AND estado NOT IN ('CANCELADO', 'REAGENDADO', 'RESERVA_CAMPO')
         ORDER BY order_id, updated_at DESC, id
    )
    SELECT d.id::text, o.numero, c.nombre AS cliente, a.direccion_obra,
           a.fecha_entrega, left(a.hora_inicio::text, 5) AS hora_entrega,
           COALESCE(a.mixer_codigo, d.mixer_codigo) AS mixer,
           d.viaje_numero, d.total_viajes_orden, d.volumen_m3, o.resistencia,
           d.estado_actual, d.tracking_payload->'consumo_materiales' AS materiales,
           d.tracking_payload->>'receta_provisional' = 'true' AS provisional
      FROM mixer_dispatches d
      JOIN orders o ON o.id = d.order_id
      JOIN clients c ON c.id = o.cliente_id
      LEFT JOIN agenda a ON a.order_id = o.id
     WHERE (a.fecha_entrega = $1 AND o.estado IN ('CONFIRMADA', 'EN_DESPACHO', 'COMPLETADA')
         OR a.fecha_entrega IS NULL AND $1 = $2 AND d.estado_actual = 'PROGRAMADO'
            AND o.estado IN ('CONFIRMADA', 'EN_DESPACHO')
            AND NOT EXISTS (
                SELECT 1 FROM dispatch_schedule s WHERE s.order_id = o.id
            ))
     ORDER BY a.hora_inicio NULLS LAST, o.numero, d.viaje_numero
"""

_INVENTARIO = """
    SELECT codigo, nombre, unidad, stock_real_fisico, ultimo_levantamiento_at,
           CASE WHEN ultimo_levantamiento_at IS NOT NULL
                THEN -consumo_teorico_acumulado END AS consumo_desde_conteo,
           CASE WHEN ultimo_levantamiento_at IS NOT NULL
                THEN stock_proyectado_disponible END AS disponible
      FROM v_stock_proyectado
     ORDER BY nombre
"""

_AVISOS = """
    SELECT DISTINCT ON (s.order_id) o.numero, s.fecha_entrega,
           left(s.hora_inicio::text, 5) AS hora_entrega,
           left(anterior.hora_inicio::text, 5) AS hora_anterior,
           anterior.fecha_entrega AS fecha_anterior,
           s.reagendado_de_id IS NOT NULL OR s.updated_at > s.created_at AS actualizado
      FROM dispatch_schedule s
      JOIN orders o ON o.id = s.order_id
      LEFT JOIN dispatch_schedule anterior ON anterior.id = s.reagendado_de_id
     WHERE s.deleted_at IS NULL AND s.fecha_entrega >= $1
       AND s.estado IN ('PROGRAMADO', 'EN_PLANTA')
       AND o.estado IN ('CONFIRMADA', 'EN_DESPACHO')
       AND (s.updated_at AT TIME ZONE 'America/Guayaquil')::date >= $1
     ORDER BY s.order_id, s.updated_at DESC, s.id
"""


@router.get("/tareas")
async def tareas(request: Request, fecha: date | None = None):
    perfil = await resolver_perfil(request)
    if perfil["rol_base"] != "BODEGA":
        await exigir_modulo(request, "planta_kardex")
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(503, "Base de datos no disponible")
    hoy_ec = hoy()
    dia = fecha or hoy_ec
    cargas = []
    for fila in await pool.fetch(_CARGAS, dia, hoy_ec):
        carga = dict(fila)
        if isinstance(carga["materiales"], str):
            carga["materiales"] = json.loads(carga["materiales"])
        cargas.append(carga)
    inventario = [dict(fila) for fila in await pool.fetch(_INVENTARIO)]
    return {
        "hoy": hoy_ec,
        "manana": hoy_ec + timedelta(days=1),
        "fecha": dia,
        "cargas": cargas,
        "inventario": inventario,
        "avisos": [dict(fila) for fila in await pool.fetch(_AVISOS, hoy_ec)],
    }


@router.get("/faltantes")
async def faltantes(request: Request):
    await exigir_modulo(request, "dashboard_gerencial")
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(503, "Base de datos no disponible")
    filas = await pool.fetch(_INVENTARIO)
    return {"faltantes": [
        {"nombre": fila["nombre"], "unidad": fila["unidad"], "cantidad": -fila["disponible"]}
        for fila in filas if fila["disponible"] is not None and fila["disponible"] < 0
    ]}
