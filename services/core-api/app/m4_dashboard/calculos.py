"""Modulo 4 - Matematica pura del dashboard y del simulador bancario.

Nada de LLM aqui: amortizacion francesa con ``Decimal``, DSCR y cuota de
mercado. Todas las funciones reciben numeros y devuelven numeros; la E/S vive
en :mod:`service`.

Formula francesa (cuota fija):

    i = tasa_nominal_anual / 12
    cuota = monto * i / (1 - (1 + i) ** -n)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping

CENT = Decimal("0.01")


def _d(valor: Any, por_defecto: str = "0") -> Decimal:
    if valor is None or valor == "":
        return Decimal(por_defecto)
    try:
        return Decimal(str(valor))
    except (TypeError, ValueError):
        return Decimal(por_defecto)


def _cent(valor: Decimal) -> Decimal:
    return valor.quantize(CENT, rounding=ROUND_HALF_UP)


def cuota_francesa(
    monto: Decimal | float | str,
    tasa_anual_pct: Decimal | float | str,
    plazo_meses: int,
) -> Decimal:
    """Cuota fija mensual. Tasa 0 -> capital / plazo."""
    capital = _d(monto)
    meses = int(plazo_meses)
    if meses <= 0:
        raise ValueError("plazo_meses debe ser mayor que cero")
    tasa_mensual = _d(tasa_anual_pct) / Decimal("100") / Decimal("12")
    if tasa_mensual <= 0:
        return _cent(capital / Decimal(meses))
    factor = (Decimal("1") + tasa_mensual) ** (-meses)
    cuota = capital * tasa_mensual / (Decimal("1") - factor)
    return _cent(cuota)


def dscr(flujo_mensual: Decimal | float | str, cuota: Decimal | float | str) -> float | None:
    """Debt Service Coverage Ratio. ``None`` si no hay cuota."""
    servicio = _d(cuota)
    if servicio <= 0:
        return None
    return float((_d(flujo_mensual) / servicio).quantize(CENT, rounding=ROUND_HALF_UP))


@dataclass
class Escenario:
    nombre: str
    monto_usd: Decimal
    plazo_meses: int
    m3_extra_mes: Decimal
    cuota_mensual: Decimal
    total_pagado: Decimal
    total_intereses: Decimal
    flujo_incremental_mensual: Decimal
    dscr_proyectado: float | None
    dscr_historico: float | None


def construir_escenario(
    *,
    nombre: str,
    monto_usd: Decimal | float | str,
    tasa_anual_pct: Decimal | float | str,
    plazo_meses: int,
    m3_extra_mes: Decimal | float | str,
    margen_neto_m3: Decimal | float | str,
    flujo_historico_mensual: Decimal | float | str = 0,
) -> Escenario:
    capital = _d(monto_usd)
    cuota = cuota_francesa(capital, tasa_anual_pct, plazo_meses)
    total = _cent(cuota * Decimal(plazo_meses))
    incremental = _cent(_d(m3_extra_mes) * _d(margen_neto_m3))
    historico = _d(flujo_historico_mensual)
    return Escenario(
        nombre=nombre,
        monto_usd=_cent(capital),
        plazo_meses=int(plazo_meses),
        m3_extra_mes=_d(m3_extra_mes),
        cuota_mensual=cuota,
        total_pagado=total,
        total_intereses=_cent(total - capital),
        flujo_incremental_mensual=incremental,
        dscr_proyectado=dscr(incremental, cuota),
        dscr_historico=dscr(historico + incremental, cuota),
    )


def _escenario_dict(escenario: Escenario, semaforo: str) -> dict[str, Any]:
    return {
        "nombre": escenario.nombre,
        "monto_usd": float(escenario.monto_usd),
        "plazo_meses": escenario.plazo_meses,
        "m3_extra_mes": float(escenario.m3_extra_mes),
        "cuota_mensual": float(escenario.cuota_mensual),
        "total_pagado": float(escenario.total_pagado),
        "total_intereses": float(escenario.total_intereses),
        "flujo_incremental_mensual": float(escenario.flujo_incremental_mensual),
        "dscr_proyectado": escenario.dscr_proyectado,
        "dscr_historico": escenario.dscr_historico,
        "semaforo": semaforo,
    }


def semaforo_dscr(valor: float | None) -> str:
    if valor is None:
        return "SIN_DATOS"
    if valor >= Decimal("1.50"):
        return "VERDE"
    if valor >= Decimal("1.20"):
        return "AMBAR"
    return "ROJO"


def simular_bancario(
    config: Mapping[str, Any],
    *,
    flujo_historico_mensual: Decimal | float | str = 0,
) -> dict[str, Any]:
    """Dos tarjetas: Pluma $100k/36m y Combo China $240k/48m."""
    cfg = dict(config or {})
    tasa = _d(cfg.get("tasa_anual_pct"), "11.2")
    margen = _d(cfg.get("margen_neto_m3"), "42.50")
    plazos = list(cfg.get("plazos_meses") or [36, 48])

    pluma = construir_escenario(
        nombre="Pluma China",
        monto_usd=_d(cfg.get("pluma_monto_usd"), "100000"),
        tasa_anual_pct=tasa,
        plazo_meses=int(plazos[0]) if plazos else 36,
        m3_extra_mes=_d(cfg.get("m3_extra_pluma"), "180"),
        margen_neto_m3=margen,
        flujo_historico_mensual=flujo_historico_mensual,
    )
    combo = construir_escenario(
        nombre="Combo Pluma + 2 Mixers",
        monto_usd=_d(cfg.get("combo_china_monto_usd"), "240000"),
        tasa_anual_pct=tasa,
        plazo_meses=int(plazos[1]) if len(plazos) > 1 else 48,
        m3_extra_mes=_d(cfg.get("m3_extra_combo"), "450"),
        margen_neto_m3=margen,
        flujo_historico_mensual=flujo_historico_mensual,
    )
    return {
        "parametros": {
            "tasa_anual_pct": float(tasa),
            "tasa_mensual_pct": float((tasa / Decimal("12")).quantize(CENT)),
            "margen_neto_m3": float(margen),
            "flujo_historico_mensual": float(_d(flujo_historico_mensual)),
            "metodo": "AMORTIZACION_FRANCESA",
        },
        "escenarios": [
            _escenario_dict(pluma, semaforo_dscr(pluma.dscr_proyectado)),
            _escenario_dict(combo, semaforo_dscr(combo.dscr_proyectado)),
        ],
    }


# ---------------------------------------------------------------------------
# Cuota de mercado
# ---------------------------------------------------------------------------
def calcular_cuota_mercado(
    *,
    provincia: str,
    anio: int,
    ventas_m3: Decimal | float | str,
    demanda_m3: Decimal | float | str,
    precio_m3: Decimal | float | str,
) -> dict[str, Any]:
    ventas = _d(ventas_m3)
    demanda = _d(demanda_m3)
    precio = _d(precio_m3)
    if demanda <= 0:
        return {
            "provincia": provincia,
            "anio": anio,
            "ventas_m3": float(ventas),
            "demanda_m3": float(demanda),
            "cuota_pct": None,
            "valor_mercado_usd": None,
            "capturado_usd": None,
            "competencia_usd": None,
            "mensaje": "Sin benchmark cargado para esta provincia/anio.",
        }
    cuota = (ventas / demanda * Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
    faltante = max(Decimal("0"), demanda - ventas)
    if cuota >= Decimal("15"):
        mensaje = (
            f"Orminorth controla {cuota}% del mercado de {provincia}. "
            "La Planta Movil permite sostener el ritmo sin depender de la planta fija."
        )
    elif cuota >= Decimal("5"):
        mensaje = (
            f"Orminorth tiene {cuota}% de {provincia}. Cada 10,000 m3 adicionales "
            "con la Planta Movil suman aproximadamente $1.18M capturados a la competencia."
        )
    else:
        mensaje = (
            f"Orminorth tiene {cuota}% de {provincia}: el mercado vale "
            f"${float(demanda * precio):,.0f}. La Planta Movil es la palanca para "
            "capturar obra petrolera y vial fuera de El Coca."
        )
    return {
        "provincia": provincia,
        "anio": anio,
        "ventas_m3": float(ventas),
        "demanda_m3": float(demanda),
        "cuota_pct": float(cuota),
        "valor_mercado_usd": float(_cent(demanda * precio)),
        "capturado_usd": float(_cent(ventas * precio)),
        "competencia_usd": float(_cent(faltante * precio)),
        "mensaje": mensaje,
    }


# ---------------------------------------------------------------------------
# Periodos
# ---------------------------------------------------------------------------
def rango_periodo(
    periodo: str,
    *,
    anio: int,
    hoy: date | None = None,
) -> tuple[date, date]:
    """``12_MESES_MOVILES`` (hoy - 365d) o ``ANIO_CALENDARIO`` (1 ene - 31 dic)."""
    referencia = hoy or date.today()
    if str(periodo).upper() == "ANIO_CALENDARIO":
        return date(anio, 1, 1), date(anio, 12, 31)
    return referencia - timedelta(days=365), referencia
