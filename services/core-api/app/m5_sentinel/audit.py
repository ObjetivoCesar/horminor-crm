"""Modulo 5 - Orquestacion y agregacion de la auditoria diaria.

Aqui se separa lo puro (reglas de agregacion y armado del resumen) de la E/S
(ejecucion de los checks). Las funciones puras no tocan base de datos ni red,
por eso se pueden probar de forma aislada.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from time import perf_counter
from typing import Any, Awaitable, Callable, Sequence
from zoneinfo import ZoneInfo

import asyncpg

from ..db import setting
from ..settings import Settings
from . import checks
from .checks import (
    CRITICO,
    NO_CONFIGURADO,
    OK,
    WARN,
    Categoria,
    CheckResult,
    Estado,
)

ZONA_POR_DEFECTO = "America/Guayaquil"
CLAVE_ZONA_HORARIA = "core.zona_horaria"
CLIENTE = "ORMINORTH"


def agregar_estado_global(estados: Sequence[Estado]) -> Estado:
    """Aplica la regla de agregacion del contrato del Centinela.

    - Cualquier ``CRITICO`` => ``CRITICO``.
    - Si no, cualquier ``WARN`` => ``WARN``.
    - Si todos ``NO_CONFIGURADO`` (o no hay checks) => ``NO_CONFIGURADO``.
    - En cualquier otro caso => ``OK``.
    """
    lista = list(estados)
    if not lista:
        return NO_CONFIGURADO
    if CRITICO in lista:
        return CRITICO
    if WARN in lista:
        return WARN
    if all(estado == NO_CONFIGURADO for estado in lista):
        return NO_CONFIGURADO
    return OK


# id del check -> (campo del resumen, clave dentro de `datos`)
_MAPA_RESUMEN: dict[str, tuple[str, str]] = {
    "despachos_ayer": ("viajes_despachados_ayer", "total"),
    "viajes_en_ruta": ("viajes_en_ruta", "total_en_ruta"),
    "riesgo_termico": ("viajes_en_riesgo_termico", "total"),
    "caja": ("cajas_sin_cerrar", "faltantes"),
    "errores": ("errores_24h", "total"),
}


def construir_resumen_operativo(resultados: Sequence[CheckResult]) -> dict[str, int]:
    """Arma ``resumen_operativo`` a partir de los ``datos`` de cada check.

    Es una funcion pura: no consulta nada. Un check ausente o con datos
    incompletos aporta 0, nunca lanza excepcion.
    """
    resumen: dict[str, int] = {
        "viajes_despachados_ayer": 0,
        "viajes_en_ruta": 0,
        "viajes_en_riesgo_termico": 0,
        "cajas_sin_cerrar": 0,
        "errores_24h": 0,
    }
    for resultado in resultados:
        destino = _MAPA_RESUMEN.get(resultado.id)
        if destino is None:
            continue
        campo, clave = destino
        valor = resultado.datos.get(clave)
        try:
            resumen[campo] = int(valor) if valor is not None else 0
        except (TypeError, ValueError):
            resumen[campo] = 0
    return resumen


def _timeout(settings: Settings) -> float:
    """Timeout corto para acotar cada check."""
    return max(float(settings.sentinel_http_timeout or 3.0), 0.5)


async def obtener_zona_horaria(pool: asyncpg.Pool) -> ZoneInfo:
    """Resuelve la zona desde ``core.zona_horaria`` (sin hardcodear el offset)."""
    nombre = ZONA_POR_DEFECTO
    try:
        valor = await setting(pool, CLAVE_ZONA_HORARIA, ZONA_POR_DEFECTO)
        if isinstance(valor, str) and valor.strip():
            nombre = valor.strip()
    except Exception:
        nombre = ZONA_POR_DEFECTO

    for candidato in (nombre, ZONA_POR_DEFECTO):
        try:
            return ZoneInfo(candidato)
        except Exception:
            continue
    # Ultimo recurso si el sistema no trae base IANA (tzdata ausente).
    return ZoneInfo("UTC")


def _dia_anterior(zona: ZoneInfo) -> date:
    """Fecha de ayer en la zona operativa (no en UTC)."""
    return datetime.now(zona).date() - timedelta(days=1)


async def _ejecutar_check(
    check_id: str,
    categoria: Categoria,
    fabrica: Callable[[], Awaitable[CheckResult]],
    timeout: float,
) -> CheckResult:
    """Ejecuta un check y garantiza que nunca propague una excepcion.

    Cualquier error o timeout se devuelve como ``CRITICO`` con el detalle.
    """
    inicio = perf_counter()
    try:
        return await asyncio.wait_for(fabrica(), timeout=timeout)
    except asyncio.TimeoutError:
        latencia = round((perf_counter() - inicio) * 1000, 1)
        return CheckResult(
            id=check_id,
            categoria=categoria,
            estado=CRITICO,
            detalle=f"timeout tras {timeout:.1f} s",
            latencia_ms=latencia,
            datos={"timeout_s": timeout},
        )
    except Exception as exc:  # ningun check debe tumbar la auditoria
        latencia = round((perf_counter() - inicio) * 1000, 1)
        return CheckResult(
            id=check_id,
            categoria=categoria,
            estado=CRITICO,
            detalle=f"{type(exc).__name__}: {exc}",
            latencia_ms=latencia,
            datos={"error": type(exc).__name__},
        )


async def ejecutar_auditoria(
    pool: asyncpg.Pool, settings: Settings
) -> dict[str, Any]:
    """Ejecuta todos los checks y devuelve el payload del contrato.

    Se ejecutan en paralelo; cada uno esta acotado por
    ``settings.sentinel_http_timeout`` y capturado de forma individual.
    """
    inicio = perf_counter()
    zona = await obtener_zona_horaria(pool)
    ayer = _dia_anterior(zona)
    timeout = _timeout(settings)

    fabricas = construir_fabricas(pool, settings, ayer, zona)

    resultados = await asyncio.gather(
        *(
            _ejecutar_check(check_id, categoria, fabrica, timeout)
            for check_id, categoria, fabrica in fabricas
        )
    )

    latencia_total = round((perf_counter() - inicio) * 1000, 1)
    return {
        "cliente": CLIENTE,
        "generado_at": datetime.now(zona).isoformat(timespec="seconds"),
        "latencia_total_ms": latencia_total,
        "estado_global": agregar_estado_global([r.estado for r in resultados]),
        "checks": [r.to_dict() for r in resultados],
        "resumen_operativo": construir_resumen_operativo(resultados),
    }


def construir_fabricas(
    pool: asyncpg.Pool,
    settings: Settings,
    dia: date,
    zona: ZoneInfo,
) -> list[tuple[str, Categoria, Callable[[], Awaitable[CheckResult]]]]:
    """Registro de checks del Centinela, en orden de contrato.

    Esta funcion existe para que el conjunto de chequeos sea inspeccionable
    por los tests sin abrir conexiones a base de datos.
    """
    return [
        ("db", checks.INFRAESTRUCTURA, lambda: checks.check_db(pool, settings)),
        ("redis", checks.INFRAESTRUCTURA, lambda: checks.check_redis(settings)),
        ("infra", checks.INFRAESTRUCTURA, lambda: checks.check_infra()),
        (
            "evolution",
            checks.CANAL,
            lambda: checks.check_evolution(pool, settings),
        ),
        ("bunny", checks.CANAL, lambda: checks.check_bunny(pool, settings)),
        (
            "viajes_en_ruta",
            checks.OPERACION,
            lambda: checks.check_viajes_en_ruta(pool, dia),
        ),
        (
            "riesgo_termico",
            checks.OPERACION,
            lambda: checks.check_riesgo_termico(pool),
        ),
        (
            "recetas_provisionales",
            checks.OPERACION,
            lambda: checks.check_recetas_provisionales(pool),
        ),
        ("caja", checks.OPERACION, lambda: checks.check_caja(pool, dia)),
        ("merma", checks.OPERACION, lambda: checks.check_merma(pool, dia, zona)),
        ("errores", checks.OPERACION, lambda: checks.check_errores(pool)),
        (
            "despachos_ayer",
            checks.OPERACION,
            lambda: checks.check_despachos_ayer(pool, dia, zona),
        ),
    ]
