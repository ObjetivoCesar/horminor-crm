"""Parametros de agenda y horarios de planta (v6.2).

Los valores viven en ``system_settings`` bajo ``agenda.parametros``. Este
modulo solo normaliza y valida; no escribe en base de datos. Los defaults son
los aprobados en el plan v6.2 y se usan cuando la llave no existe.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

DIAS_VALIDOS = ("LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM")
_HORA_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

DEFAULTS: dict[str, Any] = {
    "hora_apertura": "07:00",
    "hora_cierre": "18:00",
    "duracion_entrega_default_min": 90,
    "intervalo_slot_min": 30,
    "dias_laborables": ["LUN", "MAR", "MIE", "JUE", "VIE", "SAB"],
}


def _minutos(hora: str) -> int:
    return int(hora[:2]) * 60 + int(hora[3:5])


def _cargar(valor: Any) -> Mapping[str, Any]:
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except ValueError:
            return {}
    return valor if isinstance(valor, Mapping) else {}


def normalizar_parametros(valor: Any) -> dict[str, Any]:
    """Devuelve siempre un contrato completo y usable.

    Si un valor guardado esta corrupto se usa el default de ese campo; la
    agenda no debe caerse por una edicion manual en ``system_settings``.
    """
    datos = _cargar(valor)
    salida = {
        "hora_apertura": str(datos.get("hora_apertura") or DEFAULTS["hora_apertura"]),
        "hora_cierre": str(datos.get("hora_cierre") or DEFAULTS["hora_cierre"]),
        "duracion_entrega_default_min": int(
            datos.get("duracion_entrega_default_min")
            or DEFAULTS["duracion_entrega_default_min"]
        ),
        "intervalo_slot_min": int(
            datos.get("intervalo_slot_min") or DEFAULTS["intervalo_slot_min"]
        ),
        "dias_laborables": list(
            datos.get("dias_laborables") or DEFAULTS["dias_laborables"]
        ),
    }
    if not _HORA_RE.match(salida["hora_apertura"]):
        salida["hora_apertura"] = DEFAULTS["hora_apertura"]
    if not _HORA_RE.match(salida["hora_cierre"]):
        salida["hora_cierre"] = DEFAULTS["hora_cierre"]
    if _minutos(salida["hora_cierre"]) <= _minutos(salida["hora_apertura"]):
        salida["hora_apertura"] = DEFAULTS["hora_apertura"]
        salida["hora_cierre"] = DEFAULTS["hora_cierre"]
    if not (30 <= salida["duracion_entrega_default_min"] <= 720):
        salida["duracion_entrega_default_min"] = DEFAULTS[
            "duracion_entrega_default_min"
        ]
    if not (5 <= salida["intervalo_slot_min"] <= 120):
        salida["intervalo_slot_min"] = DEFAULTS["intervalo_slot_min"]
    dias = [
        str(dia).strip().upper()
        for dia in salida["dias_laborables"]
        if str(dia).strip().upper() in DIAS_VALIDOS
    ]
    salida["dias_laborables"] = dias or list(DEFAULTS["dias_laborables"])
    return salida


def validar_parametros(datos: Mapping[str, Any]) -> dict[str, Any]:
    """Valida una edicion del Superadmin. Lanza ``ValueError`` legible."""
    datos = dict(datos)
    apertura = str(datos.get("hora_apertura", DEFAULTS["hora_apertura"]))
    cierre = str(datos.get("hora_cierre", DEFAULTS["hora_cierre"]))
    if not _HORA_RE.match(apertura):
        raise ValueError("hora_apertura debe tener formato HH:MM")
    if not _HORA_RE.match(cierre):
        raise ValueError("hora_cierre debe tener formato HH:MM")
    if _minutos(cierre) <= _minutos(apertura):
        raise ValueError("hora_cierre debe ser mayor que hora_apertura")

    try:
        duracion = int(datos.get("duracion_entrega_default_min", DEFAULTS["duracion_entrega_default_min"]))
    except (TypeError, ValueError) as exc:
        raise ValueError("duracion_entrega_default_min debe ser numerico") from exc
    try:
        intervalo = int(datos.get("intervalo_slot_min", DEFAULTS["intervalo_slot_min"]))
    except (TypeError, ValueError) as exc:
        raise ValueError("intervalo_slot_min debe ser numerico") from exc
    if not (30 <= duracion <= 720):
        raise ValueError("duracion_entrega_default_min debe estar entre 30 y 720")
    if not (5 <= intervalo <= 120):
        raise ValueError("intervalo_slot_min debe estar entre 5 y 120")

    dias = datos.get("dias_laborables", DEFAULTS["dias_laborables"])
    if not isinstance(dias, (list, tuple)):
        raise ValueError("dias_laborables debe ser una lista")
    limpios = [str(d).strip().upper() for d in dias if str(d).strip()]
    if not limpios:
        raise ValueError("dias_laborables necesita al menos un dia")
    invalidos = [d for d in limpios if d not in DIAS_VALIDOS]
    if invalidos:
        raise ValueError(f"dias_laborables invalidos: {', '.join(invalidos)}")

    return {
        "hora_apertura": apertura,
        "hora_cierre": cierre,
        "duracion_entrega_default_min": duracion,
        "intervalo_slot_min": intervalo,
        "dias_laborables": limpios,
    }


def dia_laborable(fecha, parametros: Mapping[str, Any]) -> bool:
    """``fecha`` es un ``datetime.date``; LUN=0 ... DOM=6."""
    clave = DIAS_VALIDOS[fecha.weekday()]
    return clave in (parametros.get("dias_laborables") or DEFAULTS["dias_laborables"])
