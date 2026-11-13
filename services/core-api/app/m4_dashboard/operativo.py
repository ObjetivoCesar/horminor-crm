"""Consultas del dashboard operativo: operacion, inventario y cobranza.

Regla del tablero: cada respuesta dice de que fuente sale, cuando se consulto y
por que esta vacia. Un cero sin explicacion es un dato falso.

La capacidad es una restriccion declarada en ``system_settings``; nunca se
estima desde el historico. Si falta o es inconsistente se devuelve
``NO_CONFIGURADO`` o ``CONFIGURACION_INCONSISTENTE``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping

import asyncpg

from ..db import setting

# Materiales del tablero. El agua no es stock: sigue en la receta y en el costo.
MATERIALES_TABLERO: tuple[str, ...] = ("CEMENTO", "ARENA", "RIPIO", "RETARDANTE")

CUBOS_COBRANZA: tuple[str, ...] = (
    "VENCIDA",
    "POR_VENCER_7",
    "CORRIENTE",
    "SIN_VENCIMIENTO",
)

CUBOS_AGING: tuple[str, ...] = (
    "VENCIDA_MAS_90",
    "VENCIDA_61_90",
    "VENCIDA_31_60",
    "VENCIDA_1_30",
    "POR_VENCER_7",
    "POR_VENCER_30",
    "CORRIENTE",
    "SIN_VENCIMIENTO",
)

CLAVES_CAPACIDAD: tuple[str, ...] = (
    "flota.mixers",
    "flota.capacidad_plantas",
    "flota.supuestos_capacidad",
    "agenda.parametros",
    "operacion.umbrales_ocupacion",
)


def _d(valor: Any, por_defecto: str = "0") -> Decimal:
    if valor is None or valor == "":
        return Decimal(por_defecto)
    return Decimal(str(valor))


def _texto(valor: Any) -> str | None:
    """Decimal -> texto, para no viajar como float."""
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        limpio = valor.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        return f"{limpio:.4f}".rstrip("0").rstrip(".")
    return str(valor)


def _entero(valor: Any, por_defecto: int = 0) -> int:
    try:
        return int(Decimal(str(valor)))
    except (TypeError, ValueError, ArithmeticError):
        return por_defecto


def _pct(parte: Any, total: Any) -> str | None:
    denominador = _d(total)
    if denominador <= 0:
        return None
    return _texto((_d(parte) / denominador * Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    ))


def _ahora() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _hoy() -> date:
    return datetime.now().astimezone().date()


def _minutos_hora(valor: Any) -> int | None:
    texto = str(valor or "").strip()
    if len(texto) < 4 or ":" not in texto:
        return None
    try:
        hh, mm = texto.split(":")[:2]
        return int(hh) * 60 + int(mm)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Capacidad declarada
# ---------------------------------------------------------------------------
def _capacidad(
    mixers: Iterable[Mapping[str, Any]] | None,
    capacidad_plantas: Mapping[str, Any] | None,
    supuestos: Mapping[str, Any] | None,
    agenda: Mapping[str, Any] | None,
    umbrales: Mapping[str, Any] | None,
    planta: str | None = None,
) -> dict[str, Any]:
    """Capacidad diaria = min(flota, planta, jornada).

    No estima: solo usa lo declarado. Si falta un dato devuelve el estado que
    corresponde y ``efectiva_m3_dia = None`` cuando no hay base para calcular.
    """
    lista = [dict(m) for m in (mixers or []) if isinstance(m, Mapping)]
    activos = [m for m in lista if bool(m.get("activo"))]
    supuestos = dict(supuestos or {})
    umbrales = dict(umbrales or {})
    plantas = dict(capacidad_plantas or {})
    agenda = dict(agenda or {})

    base: dict[str, Any] = {
        "configurado": False,
        "flota_m3_dia": None,
        "planta_m3_dia": None,
        "jornada_m3_dia": None,
        "efectiva_m3_dia": None,
        "cuello_botella": None,
        "restricciones_sin_declarar": [],
        "umbrales_ocupacion_pct": {
            "libre_max": _texto(umbrales.get("libre_max_pct")) if umbrales.get("libre_max_pct") is not None else None,
            "ajustado_max": _texto(umbrales.get("ajustado_max_pct")) if umbrales.get("ajustado_max_pct") is not None else None,
            "estado": "CONFIGURADO" if umbrales.get("libre_max_pct") is not None and umbrales.get("ajustado_max_pct") is not None else "NO_CONFIGURADO",
        },
        "supuestos": {
            "ciclo_viaje_min": supuestos.get("ciclo_viaje_min"),
            "fuente": supuestos.get("fuente_declaracion"),
            "estado": "CONFIGURADO" if supuestos.get("ciclo_viaje_min") is not None else "NO_CONFIGURADO",
        },
    }

    if not activos:
        base.update(
            {
                "estado_configuracion": "NO_CONFIGURADO",
                "detalle_inconsistencia": "No hay mixers activos configurados en Superadmin.",
            }
        )
        return base

    sin_viajes = [
        m for m in activos if _entero(m.get("viajes_max_dia"), 0) <= 0
    ]
    capacidades = [_d(m.get("capacidad_m3")) for m in activos]
    detalle_partes: list[str] = []
    if sin_viajes:
        detalle_partes.append(
            "flota.mixers tiene "
            f"{len(activos)} unidades activas {[str(c) for c in capacidades]} "
            "sin viajes_max_dia confirmados"
        )

    esperados = supuestos.get("mixers_activos_esperados")
    cap_esperada = supuestos.get("capacidad_unitaria_esperada_m3")
    if esperados is not None and cap_esperada is not None:
        try:
            esperados_int = int(esperados)
            esperada_dec = _d(cap_esperada)
        except (TypeError, ValueError, ArithmeticError):
            esperados_int = None
            esperada_dec = None
        if esperados_int is not None and esperada_dec is not None:
            distinto = len(activos) != esperados_int or any(
                c != esperada_dec for c in capacidades
            )
            if distinto:
                detalle_partes.append(
                    f"Direccion declaro {esperados_int} mixers de "
                    f"{_texto(esperada_dec)} m3/dia"
                )

    if detalle_partes:
        base.update(
            {
                "estado_configuracion": "CONFIGURACION_INCONSISTENTE",
                "detalle_inconsistencia": "; ".join(detalle_partes)
                + "; reconciliar en Superadmin antes de comprometer entregas.",
            }
        )
        return base

    flota = sum(
        (_d(m.get("capacidad_m3")) * Decimal(_entero(m.get("viajes_max_dia"), 0)))
        for m in activos
    )
    base["flota_m3_dia"] = _texto(flota)

    # Planta: solo si produccion y horas estan declaradas.
    codigo_planta = planta or ("PLANTA-COCA" if "PLANTA-COCA" in plantas else next(iter(plantas), None))
    datos_planta = dict(plantas.get(codigo_planta) or {}) if codigo_planta else {}
    produccion = datos_planta.get("produccion_m3_hora")
    horas = datos_planta.get("horas_efectivas_dia")
    if produccion is not None and horas is not None and _d(produccion) > 0 and _d(horas) > 0:
        base["planta_m3_dia"] = _texto(_d(produccion) * _d(horas))
    else:
        base["restricciones_sin_declarar"].append("PLANTA")

    # Jornada: horario declarado / ciclo declarado.
    ciclo = supuestos.get("ciclo_viaje_min")
    apertura = _minutos_hora(agenda.get("hora_apertura"))
    cierre = _minutos_hora(agenda.get("hora_cierre"))
    if ciclo is not None and _d(ciclo) > 0 and apertura is not None and cierre is not None and cierre > apertura:
        viajes_por_mixer = int((cierre - apertura) // _entero(ciclo, 1))
        capacidad_promedio = (sum(capacidades) / Decimal(len(capacidades))) if capacidades else Decimal("0")
        jornada = capacidad_promedio * Decimal(viajes_por_mixer) * Decimal(len(activos))
        base["jornada_m3_dia"] = _texto(jornada)
    else:
        base["restricciones_sin_declarar"].append("JORNADA")

    terminos = {
        "FLOTA": _d(base["flota_m3_dia"]),
        "PLANTA": _d(base["planta_m3_dia"]) if base["planta_m3_dia"] is not None else None,
        "JORNADA": _d(base["jornada_m3_dia"]) if base["jornada_m3_dia"] is not None else None,
    }
    validos = {k: v for k, v in terminos.items() if v is not None and v > 0}
    if not validos:
        base.update(
            {
                "estado_configuracion": "NO_CONFIGURADO",
                "detalle_inconsistencia": "No hay restricciones declaradas para calcular capacidad.",
            }
        )
        return base

    minimo = min(validos.values())
    cuello = [k for k, v in validos.items() if v == minimo]
    base.update(
        {
            "configurado": True,
            "efectiva_m3_dia": _texto(minimo),
            "cuello_botella": "+".join(cuello),
            "estado_configuracion": "CONFIGURADO_COMPLETO"
            if base["planta_m3_dia"] is not None and base["jornada_m3_dia"] is not None
            else "CONFIGURADO_PARCIAL",
        }
    )
    return base


# ---------------------------------------------------------------------------
# Operacion y capacidad
# ---------------------------------------------------------------------------
async def operacion(
    pool: asyncpg.Pool,
    *,
    fecha: date | None = None,
    dias: int = 14,
    planta_id: str | None = None,
) -> dict[str, Any]:
    dia = fecha or _hoy()
    dias = max(1, min(int(dias), 90))

    mixers = await setting(pool, "flota.mixers", []) or []
    plantas = await setting(pool, "flota.capacidad_plantas", {}) or {}
    supuestos = await setting(pool, "flota.supuestos_capacidad", {}) or {}
    agenda = await setting(pool, "agenda.parametros", {}) or {}
    umbrales = await setting(pool, "operacion.umbrales_ocupacion", {}) or {}
    meta_mensual = await setting(pool, "comercial.meta_mensual_m3", None)
    punto_equilibrio = await setting(pool, "finanzas.punto_equilibrio", {}) or {}

    cap = _capacidad(mixers, plantas, supuestos, agenda, umbrales, planta_id)

    compromiso = await pool.fetchrow(
        """
        WITH ordenes AS (
            SELECT o.id,
                   o.volumen_m3::numeric(14,2) AS volumen_m3,
                   o.created_at,
                   COALESCE(SUM(ds.volumen_m3) FILTER (
                       WHERE ds.estado <> 'CANCELADO' AND ds.deleted_at IS NULL
                   ), 0)::numeric(14,2) AS agendado_m3,
                   COALESCE((
                       SELECT SUM(md.volumen_m3)
                         FROM mixer_dispatches md
                        WHERE md.order_id = o.id
                          AND NULLIF(md.tracking_payload->'tiempos_forenses'->>'salida_planta', '') IS NOT NULL
                   ), 0)::numeric(14,2) AS ejecutado_m3
              FROM orders o
              LEFT JOIN dispatch_schedule ds ON ds.order_id = o.id
             WHERE o.estado <> 'ANULADA'
             GROUP BY o.id, o.volumen_m3, o.created_at
        )
        SELECT
            COALESCE(SUM(ds.volumen_m3) FILTER (WHERE ds.fecha_entrega = $1::date), 0)::numeric(14,2) AS hoy_m3,
            COUNT(*) FILTER (WHERE ds.fecha_entrega = $1::date)::int AS viajes_hoy,
            COALESCE(SUM(ds.volumen_m3) FILTER (
                WHERE ds.fecha_entrega BETWEEN date_trunc('week', $1::date)::date
                                          AND (date_trunc('week', $1::date)::date + 6)
            ), 0)::numeric(14,2) AS semana_m3,
            COALESCE(SUM(ds.volumen_m3) FILTER (
                WHERE date_trunc('month', ds.fecha_entrega::timestamp) = date_trunc('month', $1::date::timestamp)
            ), 0)::numeric(14,2) AS mes_agendado_m3,
            (SELECT COUNT(*) FROM ordenes WHERE volumen_m3 - agendado_m3 > 0)::int AS ordenes_sin_agendar,
            (SELECT COALESCE(SUM(GREATEST(0, volumen_m3 - agendado_m3)), 0) FROM ordenes)::numeric(14,2) AS sin_agendar_m3,
            (SELECT COALESCE(SUM(GREATEST(0, volumen_m3 - GREATEST(agendado_m3, ejecutado_m3))), 0) FROM ordenes)::numeric(14,2) AS sin_despachar_m3,
            (SELECT COALESCE(SUM(volumen_m3), 0) FROM ordenes)::numeric(14,2) AS vendido_total_m3,
            (SELECT COALESCE(SUM(volumen_m3), 0) FROM ordenes
              WHERE date_trunc('month', created_at::timestamp) = date_trunc('month', $1::date::timestamp))::numeric(14,2) AS vendido_mes_m3
          FROM dispatch_schedule ds
         WHERE ds.estado <> 'CANCELADO' AND ds.deleted_at IS NULL
        """,
        dia,
    )

    serie = await pool.fetch(
        """
        WITH viajes AS (
            SELECT md.id,
                   md.volumen_m3::numeric(14,2) AS volumen_m3,
                   NULLIF(md.tracking_payload->'tiempos_forenses'->>'salida_planta', '') AS salida_planta,
                   (COALESCE(
                        NULLIF(md.tracking_payload->'tiempos_forenses'->>'salida_planta', '')::timestamptz,
                        md.created_at
                   ) AT TIME ZONE 'America/Guayaquil')::date AS fecha_viaje
              FROM mixer_dispatches md
              JOIN orders o ON o.id = md.order_id
             WHERE o.estado <> 'ANULADA'
               AND ($3::uuid IS NULL OR o.planta_id = $3::uuid)
        )
        SELECT gs.dia::date AS fecha,
               COUNT(vf.id) FILTER (WHERE vf.salida_planta IS NOT NULL)::int AS viajes_ejecutados,
               COALESCE(SUM(vf.volumen_m3) FILTER (WHERE vf.salida_planta IS NOT NULL), 0)::numeric(14,2) AS m3_ejecutados,
               COUNT(vf.id) FILTER (WHERE vf.salida_planta IS NULL)::int AS viajes_programados_sin_salida,
               COALESCE(SUM(vf.volumen_m3) FILTER (WHERE vf.salida_planta IS NULL), 0)::numeric(14,2) AS m3_programados_sin_salida
          FROM generate_series($1::date - ($2::int - 1), $1::date, INTERVAL '1 day') AS gs(dia)
          LEFT JOIN viajes vf ON vf.fecha_viaje = gs.dia::date
         GROUP BY gs.dia
         ORDER BY gs.dia ASC
        """,
        dia,
        dias,
        planta_id,
    )

    resistencia = await pool.fetch(
        """
        SELECT resistencia,
               COUNT(*)::int AS ordenes,
               COALESCE(SUM(volumen_m3), 0)::numeric(14,2) AS m3
          FROM orders
         WHERE estado <> 'ANULADA'
           AND ($1::uuid IS NULL OR planta_id = $1::uuid)
         GROUP BY resistencia
         ORDER BY m3 DESC, resistencia
        """,
        planta_id,
    )

    en_ruta = await pool.fetch(
        """
        SELECT mixer_codigo, estado_actual, salida_planta, dosificado_planta,
               orden_numero, cliente, resistencia, limite_termico_fraguado
          FROM v_dispatch_timeline
         WHERE estado_actual = 'EN_RUTA'
         ORDER BY salida_planta NULLS LAST
        """
    )
    ahora = datetime.now().astimezone()
    por_mixer: dict[str, dict[str, Any]] = {}
    for fila in en_ruta:
        salida = fila["salida_planta"] or fila["dosificado_planta"]
        minutos = None
        if isinstance(salida, datetime):
            minutos = max(0.0, (ahora - salida.astimezone(ahora.tzinfo)).total_seconds() / 60)
        por_mixer[str(fila["mixer_codigo"] or "SIN_MIXER")] = {
            "codigo": fila["mixer_codigo"],
            "estado_ruta": fila["estado_actual"],
            "minutos_en_ruta": None if minutos is None else round(minutos, 1),
            "semaforo_termico": "VERDE" if (minutos or 0) < 90 else "AMBAR" if (minutos or 0) < 150 else "ROJO",
        }

    mixers_estado = []
    for mixer in [m for m in (mixers or []) if isinstance(m, Mapping) and bool(m.get("activo"))]:
        codigo = str(mixer.get("codigo") or "")
        estado = por_mixer.get(codigo) or {
            "codigo": codigo,
            "estado_ruta": "SIN_DESPACHO_ACTIVO",
            "minutos_en_ruta": None,
            "semaforo_termico": "INACTIVO",
        }
        mixers_estado.append(estado)

    cap_configurada = bool(cap.get("configurado"))
    efectiva = _d(cap.get("efectiva_m3_dia")) if cap.get("efectiva_m3_dia") else None
    hoy_m3 = _d(compromiso["hoy_m3"]) if compromiso else Decimal("0")
    ocupacion = None
    semaforo = "NO_CONFIGURADO"
    if efectiva and efectiva > 0:
        ocupacion = _texto((hoy_m3 / efectiva * Decimal("100")).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        ))
        umbral = cap["umbrales_ocupacion_pct"]
        if umbral["estado"] == "CONFIGURADO":
            libre = _d(umbral["libre_max"])
            ajustado = _d(umbral["ajustado_max"])
            if hoy_m3 / efectiva * Decimal("100") <= libre:
                semaforo = "LIBRE"
            elif hoy_m3 / efectiva * Decimal("100") <= ajustado:
                semaforo = "AJUSTADO"
            else:
                semaforo = "SATURADO"
    elif cap.get("estado_configuracion") == "CONFIGURACION_INCONSISTENTE":
        semaforo = "CONFIGURACION_INCONSISTENTE"

    vendido_mes = _d(compromiso["vendido_mes_m3"]) if compromiso else Decimal("0")
    meta: dict[str, Any] = {
        "estado": "NO_CONFIGURADO",
        "motivo": "FALTA_META_MENSUAL",
        "meta_mensual_m3": None,
        "vendido_mes_m3": _texto(vendido_mes),
        "diferencia_m3": None,
        "cumplimiento_pct": None,
        "dias_planta_extra": None,
    }
    if meta_mensual is not None and _d(meta_mensual) > 0:
        objetivo = _d(meta_mensual)
        diferencia = vendido_mes - objetivo
        extra = None
        if efectiva and efectiva > 0:
            extra = _texto((diferencia / efectiva).quantize(
                Decimal("0.1"), rounding=ROUND_HALF_UP
            ))
        meta = {
            "estado": "SUPERADA" if diferencia >= 0 else "EN_CURSO",
            "motivo": None,
            "meta_mensual_m3": _texto(objetivo),
            "vendido_mes_m3": _texto(vendido_mes),
            "diferencia_m3": _texto(diferencia),
            "cumplimiento_pct": _pct(vendido_mes, objetivo),
            "dias_planta_extra": extra,
        }

    pe_cfg = dict(punto_equilibrio)
    faltantes: list[str] = []
    if pe_cfg.get("costos_fijos_mensual_usd") is None:
        faltantes.append("COSTOS_FIJOS_MENSUALES")
    if pe_cfg.get("precio_m3_usd") is None:
        faltantes.append("PRECIO_M3")
    if pe_cfg.get("costo_variable_m3_usd") is None:
        faltantes.append("COSTO_VARIABLE_M3")
    margen = None
    pe_m3 = None
    estado_pe = "NO_CONFIGURADO"
    motivo_pe = "FALTAN_DATOS" if faltantes else None
    if not faltantes:
        margen = _d(pe_cfg.get("precio_m3_usd")) - _d(pe_cfg.get("costo_variable_m3_usd"))
        if margen <= 0:
            estado_pe = "NO_CONFIGURADO"
            motivo_pe = "MARGEN_NO_POSITIVO"
        else:
            pe_m3 = _d(pe_cfg.get("costos_fijos_mensual_usd")) / margen
            estado_pe = "CONFIGURADO"

    punto_equilibrio_out = {
        "estado": estado_pe,
        "motivo": motivo_pe,
        "costos_fijos_mensual_usd": _texto(pe_cfg.get("costos_fijos_mensual_usd")),
        "precio_m3_usd": _texto(pe_cfg.get("precio_m3_usd")),
        "costo_variable_m3_usd": _texto(pe_cfg.get("costo_variable_m3_usd")),
        "margen_m3_usd": _texto(margen) if margen is not None else None,
        "punto_equilibrio_m3": _texto(pe_m3) if pe_m3 is not None else None,
        "faltantes": faltantes,
    }

    return {
        "fuente": [
            "system_settings",
            "orders",
            "dispatch_schedule",
            "mixer_dispatches",
            "v_dispatch_timeline",
        ],
        "consultado": _ahora(),
        "filtros": {
            "fecha": dia.isoformat(),
            "dias_serie": dias,
            "planta_id": planta_id,
        },
        "datos": {
            "capacidad": cap,
            "meta": meta,
            "punto_equilibrio": punto_equilibrio_out,
            "comprometido": {
                "hoy_m3": _texto(compromiso["hoy_m3"]) if compromiso else "0",
                "viajes_hoy": _entero(compromiso["viajes_hoy"]) if compromiso else 0,
                "ocupacion_hoy_pct": ocupacion,
                "estado_semaforo_hoy": semaforo,
                "semana_m3": _texto(compromiso["semana_m3"]) if compromiso else "0",
                "mes_agendado_m3": _texto(compromiso["mes_agendado_m3"]) if compromiso else "0",
                "vendido_mes_m3": _texto(compromiso["vendido_mes_m3"]) if compromiso else "0",
            },
            "sin_agendar": {
                "ordenes_count": _entero(compromiso["ordenes_sin_agendar"]) if compromiso else 0,
                "m3": _texto(compromiso["sin_agendar_m3"]) if compromiso else "0",
                "sin_despachar_m3": _texto(compromiso["sin_despachar_m3"]) if compromiso else "0",
                "vendido_total_m3": _texto(compromiso["vendido_total_m3"]) if compromiso else "0",
            },
            "por_resistencia": [
                {
                    "resistencia": f["resistencia"],
                    "ordenes": _entero(f["ordenes"]),
                    "m3": _texto(f["m3"]),
                }
                for f in resistencia
            ],
            "serie_dias": [
                {
                    "fecha": f["fecha"].isoformat() if hasattr(f["fecha"], "isoformat") else str(f["fecha"]),
                    "viajes_ejecutados": _entero(f["viajes_ejecutados"]),
                    "m3_ejecutados": _texto(f["m3_ejecutados"]),
                    "viajes_programados_sin_salida": _entero(f["viajes_programados_sin_salida"]),
                    "m3_programados_sin_salida": _texto(f["m3_programados_sin_salida"]),
                }
                for f in serie
            ],
            "mixers_estado": mixers_estado,
        },
        "vacio": None,
    }


# ---------------------------------------------------------------------------
# Inventario vs ventas y kardex
# ---------------------------------------------------------------------------
async def inventario(
    pool: asyncpg.Pool,
    *,
    desde: date | None = None,
    hasta: date | None = None,
    material_codigo: str | None = None,
) -> dict[str, Any]:
    fin = hasta or _hoy()
    inicio = desde or (fin - timedelta(days=13))

    filas = await pool.fetch(
        """
        WITH recetas AS (
            SELECT resistencia, 'CEMENTO'::text AS mat, cemento_sacos_m3::numeric AS factor FROM concrete_recipes
            UNION ALL SELECT resistencia, 'ARENA'::text, arena_m3_m3::numeric FROM concrete_recipes
            UNION ALL SELECT resistencia, 'RIPIO'::text, ripio_m3_m3::numeric FROM concrete_recipes
            UNION ALL SELECT resistencia, 'RETARDANTE'::text, retardante_litros_m3::numeric FROM concrete_recipes
            UNION ALL SELECT resistencia, 'AGUA'::text, agua_litros_m3::numeric FROM concrete_recipes
        ),
        volumen_orden AS (
            SELECT resistencia, SUM(volumen_m3)::numeric AS m3
              FROM orders
             WHERE estado <> 'ANULADA'
             GROUP BY resistencia
        ),
        mrp AS (
            SELECT r.mat, COALESCE(SUM(v.m3 * r.factor), 0)::numeric(14,3) AS necesario
              FROM recetas r
              LEFT JOIN volumen_orden v ON v.resistencia = r.resistencia
             GROUP BY r.mat
        ),
        viajes_teorico AS (
            SELECT DISTINCT md.id, md.volumen_m3::numeric AS volumen_m3, o.resistencia
              FROM mixer_dispatches md
              JOIN orders o ON o.id = md.order_id
             WHERE EXISTS (
                 SELECT 1 FROM inventory_movements im
                  WHERE im.dispatch_id = md.id AND im.tipo = 'TEORICO'
             )
        ),
        simetrico AS (
            SELECT r.mat, (-COALESCE(SUM(vt.volumen_m3 * r.factor), 0))::numeric(14,3) AS neto
              FROM recetas r
              LEFT JOIN viajes_teorico vt ON vt.resistencia = r.resistencia
             GROUP BY r.mat
        ),
        kardex AS (
            SELECT material_id,
                   COALESCE(SUM(cantidad) FILTER (WHERE tipo IN ('TEORICO', 'ANULACION')), 0)::numeric(14,3) AS neto,
                   COALESCE(ABS(SUM(cantidad) FILTER (
                       WHERE tipo = 'TEORICO' AND created_at >= (NOW() - INTERVAL '30 days')
                   )), 0)::numeric(14,3) AS consumo_30d
              FROM inventory_movements
             GROUP BY material_id
        )
        SELECT m.codigo, m.nombre, m.unidad,
               m.stock_actual::numeric(14,3) AS stock_actual,
               m.stock_minimo::numeric(14,3) AS stock_minimo,
               m.ultimo_levantamiento_at,
               vsp.stock_proyectado_disponible::numeric(14,3) AS stock_proyectado_disponible,
               vsp.estado_alerta_proyectada,
               COALESCE(mrp.necesario, 0)::numeric(14,3) AS necesario_ventas,
               COALESCE(k.neto, 0)::numeric(14,3) AS neto_registrado,
               COALESCE(s.neto, 0)::numeric(14,3) AS neto_simetrico,
               (COALESCE(k.neto, 0) - COALESCE(s.neto, 0))::numeric(14,3) AS brecha_asimetria,
               COALESCE(k.consumo_30d, 0)::numeric(14,3) AS consumo_30d,
               (SELECT COUNT(*) FROM inventory_movements WHERE tipo = 'TEORICO')::int AS movimientos_teoricos_count,
               (SELECT COUNT(*) FROM (
                    SELECT md.id
                      FROM mixer_dispatches md
                      JOIN inventory_movements im ON im.dispatch_id = md.id AND im.tipo = 'TEORICO'
                      JOIN materials mm ON mm.id = im.material_id
                     GROUP BY md.id
                    HAVING COUNT(DISTINCT mm.codigo) < 5
               ) x)::int AS viajes_asimetria_count,
               (SELECT COALESCE(SUM(volumen_m3), 0) FROM orders WHERE estado <> 'ANULADA')::numeric(14,2) AS m3_vendidos,
               (SELECT cemento_sacos_m3 FROM concrete_recipes WHERE resistencia = 'FC-210')::numeric(14,4) AS fc210_cemento,
               (SELECT retardante_litros_m3 FROM concrete_recipes WHERE resistencia = 'FC-210')::numeric(14,4) AS fc210_retardante
          FROM materials m
          LEFT JOIN v_stock_proyectado vsp ON vsp.codigo = m.codigo
          LEFT JOIN mrp ON mrp.mat = m.codigo
          LEFT JOIN kardex k ON k.material_id = m.id
          LEFT JOIN simetrico s ON s.mat = m.codigo
         WHERE m.codigo = ANY($1::text[])
         ORDER BY array_position($1::text[], m.codigo)
        """,
        list(MATERIALES_TABLERO),
    )

    serie = await pool.fetch(
        """
        SELECT (im.created_at AT TIME ZONE 'America/Guayaquil')::date AS fecha,
               m.codigo AS material,
               im.tipo,
               COUNT(*)::int AS movimientos_count,
               COALESCE(SUM(im.cantidad), 0)::numeric(14,3) AS cantidad_neta
          FROM inventory_movements im
          JOIN materials m ON m.id = im.material_id
         WHERE (im.created_at AT TIME ZONE 'America/Guayaquil')::date BETWEEN $1::date AND $2::date
           AND ($3::text IS NULL OR $3::text = 'TODOS' OR m.codigo = $3::text)
         GROUP BY 1, 2, 3
         ORDER BY 1 ASC, 2 ASC, 3 ASC
        """,
        inicio,
        fin,
        material_codigo,
    )

    materiales: list[dict[str, Any]] = []
    for f in filas:
        stock_declarado = f["stock_actual"]
        neto_registrado = None
        neto_corregido = None
        if stock_declarado is not None:
            neto_registrado = _d(stock_declarado) + _d(f["neto_registrado"])
            neto_corregido = _d(stock_declarado) + _d(f["neto_simetrico"])
        if f["ultimo_levantamiento_at"] is not None:
            neto_registrado = f["stock_proyectado_disponible"]
            neto_corregido = f["stock_proyectado_disponible"]

        necesario = _d(f["necesario_ventas"])
        cobertura_declarada = _pct(stock_declarado, necesario) if stock_declarado is not None else None
        cobertura_registrada = _pct(neto_registrado, necesario) if neto_registrado is not None else None
        cobertura_corregida = _pct(neto_corregido, necesario) if neto_corregido is not None else None

        def _estado(cobertura: str | None) -> str:
            if cobertura is None:
                return "SIN_LEVANTAR"
            valor = _d(cobertura)
            if valor < 100:
                return "FALTA_MATERIAL"
            if valor <= 120:
                return "AJUSTADO"
            return "HOLGADO"

        materiales.append(
            {
                "codigo": f["codigo"],
                "nombre": f["nombre"],
                "unidad": f["unidad"],
                "stock": _texto(stock_declarado),
                "stock_real": _texto(stock_declarado),
                "stock_declarado": _texto(stock_declarado),
                "stock_neto_registrado": _texto(neto_registrado),
                "stock_neto_corregido_por_asimetria": _texto(neto_corregido),
                "brecha_asimetria_omitida": _texto(f["brecha_asimetria"]),
                "stock_minimo": _texto(f["stock_minimo"]),
                "ultimo_conteo": f["ultimo_levantamiento_at"].isoformat()
                if f["ultimo_levantamiento_at"]
                else None,
                "necesario_ventas": _texto(necesario),
                "consumo_30d": _texto(f["consumo_30d"]),
                "cobertura_declarada_pct": cobertura_declarada,
                "cobertura_neta_registrada_pct": cobertura_registrada,
                "cobertura_neta_corregida_pct": cobertura_corregida,
                "estado_declarado": _estado(cobertura_declarada),
                "estado": f["estado_alerta_proyectada"],
                "estado_conservador": _estado(cobertura_corregida)
                if cobertura_corregida is not None
                else f["estado_alerta_proyectada"],
            }
        )

    sin_conteo = [m for m in materiales if m["estado"] in ("SIN_LEVANTAR", "SIN_FECHA_CONTEO")]
    movimientos = _entero(filas[0]["movimientos_teoricos_count"]) if filas else 0
    asimetrias = _entero(filas[0]["viajes_asimetria_count"]) if filas else 0

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

    cemento = next((m for m in materiales if m["codigo"] == "CEMENTO"), None)
    retardante = next((m for m in materiales if m["codigo"] == "RETARDANTE"), None)
    fila_base = dict(filas[0]) if filas else {}
    vendidos = _d(fila_base.get("m3_vendidos"))
    fc_cemento = _d(fila_base.get("fc210_cemento"))
    fc_retardante = _d(fila_base.get("fc210_retardante"))
    m3_declarado = None
    m3_neto = None
    if cemento and retardante:
        limites_decl = []
        limites_netos = []
        if cemento["stock_declarado"] is not None and fc_cemento > 0:
            limites_decl.append(_d(cemento["stock_declarado"]) / fc_cemento)
        if retardante["stock_declarado"] is not None and fc_retardante > 0:
            limites_decl.append(_d(retardante["stock_declarado"]) / fc_retardante)
        if cemento["stock_neto_registrado"] is not None and fc_cemento > 0:
            limites_netos.append(_d(cemento["stock_neto_registrado"]) / fc_cemento)
        if retardante["stock_neto_registrado"] is not None and fc_retardante > 0:
            limites_netos.append(_d(retardante["stock_neto_registrado"]) / fc_retardante)
        if limites_decl:
            m3_declarado = _texto(min(limites_decl).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
        if limites_netos:
            m3_neto = _texto(min(limites_netos).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))

    medibles = [m for m in materiales if m["cobertura_neta_registrada_pct"] is not None]
    cuello = min(medibles, key=lambda m: _d(m["cobertura_neta_registrada_pct"])) if medibles else None

    return {
        "fuente": [
            "materials",
            "v_stock_proyectado",
            "inventory_movements",
            "orders",
            "concrete_recipes",
        ],
        "consultado": _ahora(),
        "filtros": {
            "materiales": list(MATERIALES_TABLERO),
            "incluye_agua": False,
            "desde": inicio.isoformat(),
            "hasta": fin.isoformat(),
        },
        "datos": {
            "materiales": materiales,
            "sin_conteo": len(sin_conteo),
            "alerta_integridad_bodega": {
                "conteo_fisico_pendiente": len(sin_conteo) == len(materiales) and bool(materiales),
                "materiales_sin_conteo_count": len(sin_conteo),
                "movimientos_teoricos_count": movimientos,
                "viajes_asimetria_kardex_count": asimetrias,
                "mensaje": (
                    "Sin conteo fisico: se muestran stock declarado, neto registrado "
                    "y neto corregido por la asimetria del 2026-11-08."
                    if len(sin_conteo) == len(materiales) and materiales
                    else "Conteo fisico registrado o parcial."
                ),
            },
            "ventas_equivalencia": {
                "m3_comprometidos": _texto(vendidos),
                "m3_fc210_disponibles_declarado": m3_declarado,
                "m3_fc210_disponibles_neto_kardex": m3_neto,
                "material_cuello_botella": cuello["codigo"] if cuello else None,
            },
            "serie_kardex": [
                {
                    "fecha": f["fecha"].isoformat() if hasattr(f["fecha"], "isoformat") else str(f["fecha"]),
                    "material": f["material"],
                    "tipo": f["tipo"],
                    "movimientos_count": _entero(f["movimientos_count"]),
                    "cantidad_neta": _texto(f["cantidad_neta"]),
                }
                for f in serie
            ],
        },
        "vacio": vacio,
    }


# ---------------------------------------------------------------------------
# Cobranza: documento unico + cascada FIFO
# ---------------------------------------------------------------------------
def _cubo_aging(vencimiento: date | None, corte: date) -> str:
    if vencimiento is None:
        return "SIN_VENCIMIENTO"
    dias = (corte - vencimiento).days
    if dias > 90:
        return "VENCIDA_MAS_90"
    if dias >= 61:
        return "VENCIDA_61_90"
    if dias >= 31:
        return "VENCIDA_31_60"
    if dias >= 1:
        return "VENCIDA_1_30"
    if -7 <= dias <= 0:
        return "POR_VENCER_7"
    if -30 <= dias <= -8:
        return "POR_VENCER_30"
    return "CORRIENTE"


def _aplicar_pagos(docs: list[dict[str, Any]], pagos: list[Mapping[str, Any]]) -> None:
    """Aplica pagos directos por orden y luego pagos libres por cliente.

    Los documentos ya vienen con ``monto`` y ``saldo``. La cascada es FIFO por
    vencimiento/emision para que el saldo cierre al centavo.
    """
    por_orden: dict[str, Decimal] = {}
    libre: dict[str, Decimal] = {}
    for p in pagos:
        monto = _d(p.get("monto"))
        if p.get("order_id"):
            por_orden[str(p["order_id"])] = por_orden.get(str(p["order_id"]), Decimal("0")) + monto
        elif p.get("cliente_id"):
            libre[str(p["cliente_id"])] = libre.get(str(p["cliente_id"]), Decimal("0")) + monto

    ordenados = sorted(
        docs,
        key=lambda d: (
            d["cliente_id"],
            0 if d["tipo_doc"] == "FACTURA" else 1,
            d["fecha_vencimiento"] or date.max,
            d["fecha_emision"],
            d["doc_id"],
        ),
    )

    # 1) Pagos directos a la orden.
    for doc in ordenados:
        disponible = por_orden.get(doc["orden_id"] or "", Decimal("0"))
        if disponible <= 0 or doc["saldo"] <= 0:
            continue
        aplicar = min(doc["saldo"], disponible)
        doc["saldo"] -= aplicar
        doc["cobrado"] += aplicar
        por_orden[doc["orden_id"]] = disponible - aplicar

    # 2) Pagos libres por cliente, FIFO.
    for doc in ordenados:
        disponible = libre.get(doc["cliente_id"], Decimal("0"))
        if disponible <= 0 or doc["saldo"] <= 0:
            continue
        aplicar = min(doc["saldo"], disponible)
        doc["saldo"] -= aplicar
        doc["cobrado"] += aplicar
        libre[doc["cliente_id"]] = disponible - aplicar


async def cobranza(
    pool: asyncpg.Pool,
    limite_clientes: int = 8,
    *,
    fecha: date | None = None,
    preset: str = "TODOS",
    cubo: str = "TODOS",
    exigibilidad: str = "TODA_CARTERA",
    cliente_id: str | None = None,
    provincia: str | None = None,
    ordenar_por: str = "MONTO_DESC",
) -> dict[str, Any]:
    corte = fecha or _hoy()
    preset = (preset or "TODOS").upper()
    cubo = (cubo or "TODOS").upper()
    exigibilidad = (exigibilidad or "TODA_CARTERA").upper()
    ordenar_por = (ordenar_por or "MONTO_DESC").upper()

    ordenes = await pool.fetch(
        """
        SELECT o.id, o.numero, o.cliente_id, c.nombre AS cliente, c.provincia,
               c.credit_limit_usd,
               COALESCE(o.total_con_iva, o.total)::numeric(14,2) AS total,
               o.fecha_vencimiento,
               (o.created_at AT TIME ZONE 'America/Guayaquil')::date AS fecha_emision,
               o.volumen_m3::numeric(14,2) AS volumen_m3,
               COALESCE((
                   SELECT SUM(md.volumen_m3) FROM mixer_dispatches md
                    WHERE md.order_id = o.id AND md.estado_actual = 'CONFIRMADO_CLIENTE'
               ), 0)::numeric(14,2) AS m3_confirmados,
               COALESCE((
                   SELECT SUM(md.volumen_m3) FROM mixer_dispatches md
                    WHERE md.order_id = o.id
                      AND NULLIF(md.tracking_payload->'tiempos_forenses'->>'salida_planta', '') IS NOT NULL
               ), 0)::numeric(14,2) AS m3_salidos
          FROM orders o
          JOIN clients c ON c.id = o.cliente_id
         WHERE o.estado <> 'ANULADA'
         ORDER BY o.numero
        """
    )

    facturas = await pool.fetch(
        """
        SELECT ci.id, ci.numero, ci.orden_id, ci.cliente_id, ci.total::numeric(14,2) AS total,
               ci.fecha, ci.fecha_vencimiento, ci.es_ficticia
          FROM client_invoices ci
         WHERE ci.estado = 'EMITIDA'
         ORDER BY ci.fecha, ci.numero
        """
    )

    pagos = await pool.fetch(
        """
        SELECT p.order_id, p.cliente_id, SUM(p.monto)::numeric(14,2) AS monto
          FROM payments p
         WHERE p.tipo_movimiento = 'COBRO'
           AND p.metodo <> 'FIADO'
           AND p.deleted_at IS NULL
         GROUP BY p.order_id, p.cliente_id
        """
    )

    saldo_vista = await pool.fetchrow(
        "SELECT COALESCE(SUM(saldo_pendiente), 0)::numeric(14,2) AS saldo FROM v_cliente_saldo"
    )

    facturas_reales = [f for f in facturas if not bool(f["es_ficticia"])]
    ficticias = [f for f in facturas if bool(f["es_ficticia"])]
    facturado_por_orden: dict[str, Decimal] = {}
    for f in facturas_reales:
        if f["orden_id"]:
            facturado_por_orden[str(f["orden_id"])] = (
                facturado_por_orden.get(str(f["orden_id"]), Decimal("0")) + _d(f["total"])
            )

    docs: list[dict[str, Any]] = []
    for f in facturas_reales:
        docs.append(
            {
                "doc_id": str(f["id"]),
                "tipo_doc": "FACTURA",
                "doc_numero": f["numero"],
                "cliente_id": str(f["cliente_id"]),
                "cliente_nombre": next((o["cliente"] for o in ordenes if str(o["cliente_id"]) == str(f["cliente_id"])), ""),
                "provincia": next((o["provincia"] for o in ordenes if str(o["cliente_id"]) == str(f["cliente_id"])), None),
                "credit_limit_usd": next((o["credit_limit_usd"] for o in ordenes if str(o["cliente_id"]) == str(f["cliente_id"])), None),
                "orden_id": str(f["orden_id"]) if f["orden_id"] else None,
                "fecha_emision": f["fecha"],
                "fecha_vencimiento": f["fecha_vencimiento"],
                "monto": _d(f["total"]),
                "cobrado": Decimal("0"),
                "saldo": _d(f["total"]),
                "volumen_m3": None,
                "m3_confirmados": Decimal("0"),
                "m3_salidos": Decimal("0"),
            }
        )

    for o in ordenes:
        total = o["total"]
        remanente = None
        if total is not None:
            remanente = _d(total) - facturado_por_orden.get(str(o["id"]), Decimal("0"))
        if remanente is not None and remanente <= 0:
            continue
        docs.append(
            {
                "doc_id": str(o["id"]),
                "tipo_doc": "ORDEN",
                "doc_numero": str(o["numero"]),
                "cliente_id": str(o["cliente_id"]),
                "cliente_nombre": o["cliente"],
                "provincia": o["provincia"],
                "credit_limit_usd": o["credit_limit_usd"],
                "orden_id": str(o["id"]),
                "fecha_emision": o["fecha_emision"],
                "fecha_vencimiento": o["fecha_vencimiento"],
                "monto": remanente,
                "cobrado": Decimal("0"),
                "saldo": remanente if remanente is not None else Decimal("0"),
                "volumen_m3": _d(o["volumen_m3"]),
                "m3_confirmados": _d(o["m3_confirmados"]),
                "m3_salidos": _d(o["m3_salidos"]),
            }
        )

    _aplicar_pagos(docs, pagos)

    for doc in docs:
        doc["cubo"] = (
            "MONTO_NULO_HISTORICO"
            if doc["monto"] is None
            else "PAGADO"
            if doc["saldo"] == 0
            else _cubo_aging(doc["fecha_vencimiento"], corte)
        )
        doc["dias_mora"] = (
            None
            if doc["fecha_vencimiento"] is None
            else max(0, (corte - doc["fecha_vencimiento"]).days)
        )
        doc["estado_cupo"] = (
            "SIN_CUPO_ASIGNADO"
            if doc["credit_limit_usd"] is None
            else "EXCEDIDO"
            if doc["saldo"] > _d(doc["credit_limit_usd"])
            else "OK"
        )
        doc["recepcion_confirmada_o_facturada"] = (
            doc["monto"]
            if doc["tipo_doc"] == "FACTURA"
            else doc["monto"]
            * min(Decimal("1"), doc["m3_confirmados"] / doc["volumen_m3"])
            if doc["volumen_m3"] and doc["monto"] is not None
            else Decimal("0")
        )
        doc["con_viaje_salido"] = (
            doc["monto"]
            if doc["tipo_doc"] == "FACTURA"
            else doc["monto"]
            * min(Decimal("1"), doc["m3_salidos"] / doc["volumen_m3"])
            if doc["volumen_m3"] and doc["monto"] is not None
            else Decimal("0")
        )

    # Filtros de decision
    def _coincide(doc: Mapping[str, Any]) -> bool:
        if cliente_id and doc["cliente_id"] != cliente_id:
            return False
        if provincia and (doc["provincia"] or "SIN_PROVINCIA") != provincia:
            return False
        if cubo != "TODOS" and doc["cubo"] != cubo:
            return False
        if exigibilidad == "RECEPCION_CONFIRMADA_O_FACTURA" and doc["recepcion_confirmada_o_facturada"] <= 0:
            return False
        if exigibilidad == "CON_VIAJE_SALIDO" and doc["con_viaje_salido"] <= 0:
            return False
        if exigibilidad == "COMPROMETIDO_SIN_SALIDA" and doc["con_viaje_salido"] > 0:
            return False
        if preset == "URGENCIA_7D":
            return doc["saldo"] > 0 and doc["fecha_vencimiento"] is not None and doc["fecha_vencimiento"] <= corte + timedelta(days=7)
        if preset == "MORA_ACTIVA":
            return doc["saldo"] > 0 and doc["fecha_vencimiento"] is not None and doc["dias_mora"] >= 1
        if preset == "SIN_VENCIMIENTO":
            return doc["saldo"] > 0 and doc["fecha_vencimiento"] is None
        if preset == "CUPO_EXCEDIDO":
            return doc["saldo"] > 0 and doc["estado_cupo"] in ("EXCEDIDO", "SIN_CUPO_ASIGNADO")
        if preset == "LISTO_PARA_COBRAR_ENTREGADO":
            return doc["saldo"] > 0 and (doc["tipo_doc"] == "FACTURA" or doc["m3_confirmados"] > 0)
        return doc["saldo"] > 0 or doc["monto"] is None

    visibles = [d for d in docs if _coincide(d)]
    if preset == "CLIENTES_GRANDES":
        totales: dict[str, Decimal] = {}
        for d in visibles:
            if d["saldo"] > 0:
                totales[d["cliente_id"]] = totales.get(d["cliente_id"], Decimal("0")) + d["saldo"]
        top = set(sorted(totales, key=lambda k: totales[k], reverse=True)[:5])
        visibles = [d for d in visibles if d["cliente_id"] in top]

    def _orden(d: Mapping[str, Any]):
        if ordenar_por == "DIAS_MORA_DESC":
            return (-(d["dias_mora"] or 0), -d["saldo"])
        if ordenar_por == "VENCIMIENTO_ASC":
            return (d["fecha_vencimiento"] or date.max, -d["saldo"])
        return (-d["saldo"], d["fecha_vencimiento"] or date.max)

    visibles.sort(key=_orden)

    aging = {c: {"cubo": c, "monto": Decimal("0"), "documentos": 0} for c in CUBOS_AGING}
    for d in docs:
        if d["cubo"] in aging and d["saldo"] > 0:
            aging[d["cubo"]]["monto"] += d["saldo"]
            aging[d["cubo"]]["documentos"] += 1

    saldo_total = sum((d["saldo"] for d in docs if d["saldo"] > 0), Decimal("0"))
    saldo_vista_total = _d(saldo_vista["saldo"]) if saldo_vista else Decimal("0")
    documentos = [d for d in docs if d["monto"] is not None]

    sin_fecha = [d for d in documentos if d["saldo"] > 0 and d["fecha_vencimiento"] is None]
    con_fecha = [d for d in documentos if d["saldo"] > 0 and d["fecha_vencimiento"] is not None]
    esperada_7d = None
    esperada_30d = None
    if con_fecha:
        esperada_7d = sum((d["saldo"] for d in con_fecha if d["fecha_vencimiento"] <= corte + timedelta(days=7)), Decimal("0"))
        esperada_30d = sum((d["saldo"] for d in con_fecha if d["fecha_vencimiento"] <= corte + timedelta(days=30)), Decimal("0"))

    cobrado_30d = sum((_d(p["monto"]) for p in pagos if p["monto"]), Decimal("0"))
    dso = None
    if cobrado_30d > 0 and saldo_total > 0:
        dso = _texto((saldo_total / cobrado_30d * Decimal("30")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))

    def _cubo_resumen(nombre: str) -> dict[str, Any]:
        if nombre == "VENCIDA":
            monto = sum((aging[c]["monto"] for c in ("VENCIDA_MAS_90", "VENCIDA_61_90", "VENCIDA_31_60", "VENCIDA_1_30")), Decimal("0"))
            docs_count = sum(aging[c]["documentos"] for c in ("VENCIDA_MAS_90", "VENCIDA_61_90", "VENCIDA_31_60", "VENCIDA_1_30"))
        else:
            monto = aging[nombre]["monto"]
            docs_count = aging[nombre]["documentos"]
        return {"estado": nombre, "documentos": docs_count, "monto": _texto(monto)}

    clientes: dict[str, dict[str, Any]] = {}
    for d in docs:
        if d["saldo"] <= 0:
            continue
        actual = clientes.setdefault(
            d["cliente_id"],
            {
                "nombre": d["cliente_nombre"],
                "facturado": Decimal("0"),
                "saldo": Decimal("0"),
            },
        )
        actual["facturado"] += d["monto"] or Decimal("0")
        actual["saldo"] += d["saldo"]
    top_clientes = sorted(clientes.values(), key=lambda c: c["saldo"], reverse=True)[:limite_clientes]

    vacio = None
    if not docs:
        vacio = {"motivo": "SIN_DOCUMENTOS", "mensaje": "No hay ordenes ni facturas por cobrar."}
    elif not con_fecha:
        vacio = {
            "motivo": "SIN_FECHAS_CAPTURADAS",
            "mensaje": "Ningun documento tiene fecha de vencimiento; no se puede calcular antiguedad.",
        }

    return {
        "fuente": ["orders", "client_invoices", "payments", "v_cliente_saldo"],
        "consultado": _ahora(),
        "filtros": {
            "preset": preset,
            "cubo_aging": cubo,
            "exigibilidad": exigibilidad,
            "cliente_id": cliente_id,
            "provincia": provincia,
            "ordenar_por": ordenar_por,
            "limite_clientes": limite_clientes,
        },
        "datos": {
            "cubos": [_cubo_resumen(c) for c in CUBOS_COBRANZA],
            "aging": [
                {
                    "cubo": c,
                    "monto": _texto(aging[c]["monto"]),
                    "documentos_count": aging[c]["documentos"],
                }
                for c in CUBOS_AGING
            ],
            "clientes": [
                {
                    "nombre": c["nombre"],
                    "facturado": _texto(c["facturado"]),
                    "saldo": _texto(c["saldo"]),
                }
                for c in top_clientes
            ],
            "documentos": [
                {
                    "doc_id": d["doc_id"],
                    "tipo_doc": d["tipo_doc"],
                    "doc_numero": d["doc_numero"],
                    "cliente_nombre": d["cliente_nombre"],
                    "provincia": d["provincia"],
                    "fecha_emision": d["fecha_emision"].isoformat()
                    if hasattr(d["fecha_emision"], "isoformat")
                    else str(d["fecha_emision"]),
                    "fecha_vencimiento": d["fecha_vencimiento"].isoformat()
                    if d["fecha_vencimiento"]
                    else None,
                    "monto": _texto(d["monto"]),
                    "cobrado_aplicado": _texto(d["cobrado"]),
                    "saldo": _texto(d["saldo"]),
                    "dias_mora": d["dias_mora"],
                    "cubo_aging": d["cubo"],
                    "estado_cupo": d["estado_cupo"],
                    "recepcion_confirmada_o_facturada": _texto(d["recepcion_confirmada_o_facturada"]),
                    "con_viaje_salido": _texto(d["con_viaje_salido"]),
                }
                for d in visibles
            ],
            "documentos_total": len(documentos),
            "saldo_total": _texto(saldo_total),
            "reconciliacion": {
                "total_documental_unico_usd": _texto(saldo_total),
                "saldo_vista_cartera_usd": _texto(saldo_vista_total),
                "diferencia_reconciliacion_usd": _texto(saldo_total - saldo_vista_total),
                "ficticias_excluidas_count": len(ficticias),
                "ordenes_sin_precio_historico_count": sum(1 for d in docs if d["monto"] is None),
            },
            "desglose_exigibilidad": {
                "recepcion_confirmada_o_facturada_usd": _texto(
                    sum((d["recepcion_confirmada_o_facturada"] for d in documentos), Decimal("0"))
                ),
                "con_viaje_salido_planta_usd": _texto(
                    sum((d["con_viaje_salido"] for d in documentos), Decimal("0"))
                ),
                "comprometido_sin_salida_planta_usd": _texto(
                    sum((d["monto"] or Decimal("0")) - d["con_viaje_salido"] for d in documentos)
                ),
            },
            "caja": {
                "esperada_7d": _texto(esperada_7d),
                "esperada_30d": _texto(esperada_30d),
                "documentos_sin_fecha_count": len(sin_fecha),
                "monto_sin_fecha": _texto(sum((d["saldo"] for d in sin_fecha), Decimal("0"))),
                "cobrado_30d": _texto(cobrado_30d),
                "dso_dias": dso,
                "motivo_caja_nula": None if con_fecha else "SIN_FECHAS_VENCIMIENTO",
                "motivo_dso_nulo": None if dso is not None else "SIN_HISTORIAL_PAGOS",
            },
            "vacio": vacio,
        },
        "vacio": vacio,
    }
