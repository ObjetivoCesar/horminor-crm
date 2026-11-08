"""Modulo 5 - Verificaciones individuales del Nodo Centinela.

Cada funcion devuelve un :class:`CheckResult` y degrada a ``NO_CONFIGURADO``
cuando falta un parametro de integracion. Los errores de red o de base de
datos no se silencian aqui: :mod:`audit` los captura y los convierte en
``CRITICO`` para que un check nunca tumbe la auditoria completa.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from time import perf_counter
from typing import Any, Literal
from zoneinfo import ZoneInfo

import asyncpg
import httpx
import psutil
from redis import asyncio as redis_asyncio

from ..db import setting
from ..settings import Settings

Categoria = Literal["INFRAESTRUCTURA", "CANAL", "OPERACION"]
Estado = Literal["OK", "WARN", "CRITICO", "NO_CONFIGURADO"]

OK: Estado = "OK"
WARN: Estado = "WARN"
CRITICO: Estado = "CRITICO"
NO_CONFIGURADO: Estado = "NO_CONFIGURADO"

INFRAESTRUCTURA: Categoria = "INFRAESTRUCTURA"
CANAL: Categoria = "CANAL"
OPERACION: Categoria = "OPERACION"

UMBRAL_DB_LENTA_MS = 500.0
UMBRAL_CPU_PCT = 85.0
UMBRAL_RAM_PCT = 90.0
UMBRAL_DISCO_WARN_PCT = 85.0
UMBRAL_DISCO_CRITICO_PCT = 95.0

_TIEMPO_MINIMO = 0.5


@dataclass(slots=True)
class CheckResult:
    """Resultado de un check del Centinela, listo para serializar."""

    id: str
    categoria: Categoria
    estado: Estado
    detalle: str
    latencia_ms: float
    datos: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convierte el resultado al contrato JSON del endpoint."""
        return {
            "id": self.id,
            "categoria": self.categoria,
            "estado": self.estado,
            "detalle": self.detalle,
            "latencia_ms": round(float(self.latencia_ms), 1),
            "datos": self.datos,
        }


def _ms_desde(inicio: float) -> float:
    """Latencia transcurrida en milisegundos, redondeada a un decimal."""
    return round((perf_counter() - inicio) * 1000, 1)


def _timeout(settings: Settings) -> float:
    """Timeout corto y acotado para toda operacion de E/S del Centinela."""
    return max(float(settings.sentinel_http_timeout or 3.0), _TIEMPO_MINIMO)


async def _leer_json(pool: asyncpg.Pool, key: str) -> dict[str, Any]:
    """Lee un objeto jsonb de ``system_settings``; tolera base no disponible.

    Si la tabla no existe o la base esta caida devuelve ``{}``: un check de
    integracion que no tiene configuracion debe reportar ``NO_CONFIGURADO``,
    no reventar la auditoria.
    """
    try:
        valor = await setting(pool, key, {})
    except Exception:
        return {}
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except (TypeError, ValueError):
            return {}
    return valor if isinstance(valor, dict) else {}


def _texto(valor: Any) -> str:
    """Normaliza un valor opcional a texto sin espacios sobrantes."""
    if valor is None:
        return ""
    return str(valor).strip()


def _decimal(valor: Any) -> float | None:
    """Convierte numeric/str/json a float; devuelve ``None`` si no es numero."""
    if valor is None:
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _rango_dia(dia: date, zona: ZoneInfo) -> tuple[datetime, datetime]:
    """Rango [inicio, fin) del dia en la zona operativa, como datetimes aware."""
    inicio = datetime.combine(dia, time.min, tzinfo=zona)
    return inicio, inicio + timedelta(days=1)


async def check_db(pool: asyncpg.Pool, settings: Settings) -> CheckResult:
    """Verifica la base de datos con ``SELECT 1`` y mide la latencia."""
    inicio = perf_counter()
    await asyncio.wait_for(pool.fetchval("SELECT 1"), timeout=_timeout(settings))
    latencia = _ms_desde(inicio)
    if latencia > UMBRAL_DB_LENTA_MS:
        estado: Estado = CRITICO
        detalle = (
            f"SELECT 1 respondio en {latencia:.1f} ms "
            f"(umbral {UMBRAL_DB_LENTA_MS:.0f} ms)"
        )
    else:
        estado = OK
        detalle = f"SELECT 1 respondio en {latencia:.1f} ms"
    return CheckResult(
        id="db",
        categoria=INFRAESTRUCTURA,
        estado=estado,
        detalle=detalle,
        latencia_ms=latencia,
        datos={"latencia_ms": latencia},
    )


async def check_redis(settings: Settings) -> CheckResult:
    """Hace ``PING`` a Redis usando la URL configurada."""
    inicio = perf_counter()
    url = _texto(settings.redis_url)
    if not url:
        return CheckResult(
            id="redis",
            categoria=INFRAESTRUCTURA,
            estado=NO_CONFIGURADO,
            detalle="redis_url no configurada",
            latencia_ms=_ms_desde(inicio),
            datos={},
        )

    timeout = _timeout(settings)
    cliente = redis_asyncio.from_url(
        url,
        socket_connect_timeout=timeout,
        socket_timeout=timeout,
    )
    try:
        await cliente.ping()
        latencia = _ms_desde(inicio)
        return CheckResult(
            id="redis",
            categoria=INFRAESTRUCTURA,
            estado=OK,
            detalle=f"PING correcto en {latencia:.1f} ms",
            latencia_ms=latencia,
            datos={"latencia_ms": latencia},
        )
    finally:
        with suppress(Exception):
            await cliente.aclose()


async def check_infra() -> CheckResult:
    """Reporta CPU, memoria y disco del host del Centinela."""
    inicio = perf_counter()
    cpu = float(psutil.cpu_percent(interval=None))
    ram = float(psutil.virtual_memory().percent)

    # En Windows "/" no siempre representa la raiz del sistema; se usa la
    # raiz real (abspath(os.sep)) como respaldo.
    disco_info = None
    error_disco: str | None = None
    for ruta in ("/", os.path.abspath(os.sep)):
        try:
            disco_info = psutil.disk_usage(ruta)
            break
        except OSError as exc:
            error_disco = f"{type(exc).__name__}: {exc}"
    if disco_info is None:
        raise OSError(f"no se pudo leer el disco: {error_disco or 'ruta desconocida'}")

    disco = float(disco_info.percent)

    if disco > UMBRAL_DISCO_CRITICO_PCT:
        estado: Estado = CRITICO
        detalle = f"disco al {disco:.1f}% (critico > {UMBRAL_DISCO_CRITICO_PCT:.0f}%)"
    elif (
        cpu > UMBRAL_CPU_PCT
        or ram > UMBRAL_RAM_PCT
        or disco > UMBRAL_DISCO_WARN_PCT
    ):
        estado = WARN
        detalle = (
            f"cpu {cpu:.1f}%, ram {ram:.1f}%, disco {disco:.1f}% "
            "(alguno supera el umbral de aviso)"
        )
    else:
        estado = OK
        detalle = f"cpu {cpu:.1f}%, ram {ram:.1f}%, disco {disco:.1f}%"

    return CheckResult(
        id="infra",
        categoria=INFRAESTRUCTURA,
        estado=estado,
        detalle=detalle,
        latencia_ms=_ms_desde(inicio),
        datos={"cpu_pct": cpu, "ram_pct": ram, "disco_pct": disco},
    )


async def _config_evolution(
    pool: asyncpg.Pool, settings: Settings
) -> tuple[str, str, str]:
    """Resuelve URL, instancia y API key desde entorno o ``system_settings``."""
    url = _texto(settings.evolution_url)
    instancia = _texto(settings.evolution_instance)
    api_key = _texto(settings.evolution_api_key)
    if not (url and instancia and api_key):
        datos = await _leer_json(pool, "integraciones.evolution")
        url = url or _texto(datos.get("url"))
        instancia = instancia or _texto(datos.get("instancia"))
        api_key = api_key or _texto(datos.get("api_key"))
    return url, instancia, api_key


async def _modo_sandbox(pool: asyncpg.Pool, settings: Settings) -> bool:
    """Lee el switch SANDBOX de la integracion; por defecto el de entorno."""
    datos = await _leer_json(pool, "integraciones.evolution")
    if "sandbox" in datos:
        return bool(datos.get("sandbox"))
    return bool(getattr(settings, "sandbox_mode", True))


async def check_evolution(pool: asyncpg.Pool, settings: Settings) -> CheckResult:
    """Consulta el estado de la instancia de Evolution API (WhatsApp)."""
    inicio = perf_counter()
    sandbox = await _modo_sandbox(pool, settings)
    if sandbox:
        return CheckResult(
            id="evolution",
            categoria=CANAL,
            estado=OK,
            detalle=(
                "SANDBOX: sin llamadas externas. Los mensajes salientes se "
                "encolan en sandbox_outbox y se ven en el panel."
            ),
            latencia_ms=_ms_desde(inicio),
            datos={"modo": "SANDBOX", "outbox": "sandbox_outbox"},
        )

    url, instancia, api_key = await _config_evolution(pool, settings)
    if not (url and instancia and api_key):
        return CheckResult(
            id="evolution",
            categoria=CANAL,
            estado=NO_CONFIGURADO,
            detalle="Evolution API sin url, instancia o api_key",
            latencia_ms=_ms_desde(inicio),
            datos={"modo": "PRODUCCION"},
        )

    endpoint = f"{url.rstrip('/')}/instance/connectionState/{instancia}"
    timeout = _timeout(settings)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as cliente:
        respuesta = await cliente.get(endpoint, headers={"apikey": api_key})

    if respuesta.status_code != 200:
        return CheckResult(
            id="evolution",
            categoria=CANAL,
            estado=WARN,
            detalle=f"Evolution API respondio HTTP {respuesta.status_code}",
            latencia_ms=_ms_desde(inicio),
            datos={"http_status": respuesta.status_code},
        )

    try:
        cuerpo = respuesta.json()
    except ValueError:
        cuerpo = {}
    if not isinstance(cuerpo, dict):
        cuerpo = {}
    instancia_datos = cuerpo.get("instance")
    estado_canal = None
    if isinstance(instancia_datos, dict):
        estado_canal = instancia_datos.get("state")
    if estado_canal is None:
        estado_canal = cuerpo.get("state")

    latencia = _ms_desde(inicio)
    if estado_canal == "open":
        return CheckResult(
            id="evolution",
            categoria=CANAL,
            estado=OK,
            detalle="instancia de Evolution API conectada (state=open)",
            latencia_ms=latencia,
            datos={"state": estado_canal, "http_status": respuesta.status_code},
        )
    return CheckResult(
        id="evolution",
        categoria=CANAL,
        estado=WARN,
        detalle=f"Evolution API respondio pero state={estado_canal!r}",
        latencia_ms=latencia,
        datos={"state": estado_canal, "http_status": respuesta.status_code},
    )


async def _host_bunny(pool: asyncpg.Pool, settings: Settings) -> str:
    """Resuelve el host CDN de Bunny desde entorno o ``system_settings``."""
    host = _texto(settings.bunny_cdn_host)
    if not host:
        datos = await _leer_json(pool, "integraciones.bunny")
        host = _texto(datos.get("cdn_host"))
    return host


async def check_bunny(pool: asyncpg.Pool, settings: Settings) -> CheckResult:
    """Hace ``HEAD`` al host del CDN de Bunny.net (nunca en SANDBOX)."""
    inicio = perf_counter()
    cfg = await _leer_json(pool, "integraciones.bunny")
    sandbox = bool(cfg.get("sandbox", getattr(settings, "sandbox_mode", True)))
    if sandbox:
        return CheckResult(
            id="bunny",
            categoria=CANAL,
            estado=OK,
            detalle=(
                "SANDBOX: sin llamadas externas. Las evidencias reciben una URL "
                "deterministica bajo /sandbox/ en la Carpeta del Cliente."
            ),
            latencia_ms=_ms_desde(inicio),
            datos={"modo": "SANDBOX", "generador": "url_simulada"},
        )

    host = await _host_bunny(pool, settings)
    if not host:
        return CheckResult(
            id="bunny",
            categoria=CANAL,
            estado=NO_CONFIGURADO,
            detalle="bunny_cdn_host no configurado",
            latencia_ms=_ms_desde(inicio),
            datos={"modo": "PRODUCCION"},
        )

    limpio = host.removeprefix("https://").removeprefix("http://").strip("/")
    endpoint = f"https://{limpio}/"
    timeout = _timeout(settings)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as cliente:
        respuesta = await cliente.head(endpoint)

    latencia = _ms_desde(inicio)
    if 200 <= respuesta.status_code <= 399:
        return CheckResult(
            id="bunny",
            categoria=CANAL,
            estado=OK,
            detalle=f"CDN responde HTTP {respuesta.status_code}",
            latencia_ms=latencia,
            datos={"http_status": respuesta.status_code, "host": limpio},
        )
    return CheckResult(
        id="bunny",
        categoria=CANAL,
        estado=WARN,
        detalle=f"CDN respondio HTTP {respuesta.status_code}",
        latencia_ms=latencia,
        datos={"http_status": respuesta.status_code, "host": limpio},
    )


async def check_viajes_en_ruta(
    pool: asyncpg.Pool, dia: date
) -> CheckResult:
    """Cuenta viajes en ruta y aquellos que exceden la alerta de llegada.

    ``dia`` se usa solo como referencia informativa en ``datos`` (la
    antiguedad se mide contra ``now()`` de la base).
    """
    inicio = perf_counter()
    umbral = await setting(
        pool, "operacion.alerta_viaje_sin_llegada_minutos", 90
    )
    umbral_min = int(umbral) if umbral is not None else 90

    fila = await pool.fetchrow(
        """
        SELECT
            count(*) AS total_en_ruta,
            count(*) FILTER (
                WHERE salida_planta < now() - ($1::int * INTERVAL '1 minute')
            ) AS sin_llegada_vencidos
        FROM v_dispatch_timeline
        WHERE salida_planta IS NOT NULL
          AND (llegada_obra_chofer IS NULL
               OR confirmacion_whatsapp_cliente IS NULL)
        """,
        umbral_min,
    )
    total = int(fila["total_en_ruta"] or 0) if fila else 0
    vencidos = int(fila["sin_llegada_vencidos"] or 0) if fila else 0

    latencia = _ms_desde(inicio)
    if vencidos > 0:
        estado: Estado = WARN
        detalle = (
            f"{vencidos} viaje(s) en ruta con mas de {umbral_min} min "
            "sin llegada/confirmacion"
        )
    else:
        estado = OK
        detalle = f"{total} viaje(s) en ruta dentro del umbral de {umbral_min} min"

    return CheckResult(
        id="viajes_en_ruta",
        categoria=OPERACION,
        estado=estado,
        detalle=detalle,
        latencia_ms=latencia,
        datos={
            "total_en_ruta": total,
            "sin_llegada_vencidos": vencidos,
            "umbral_minutos": umbral_min,
            "fecha_referencia": dia.isoformat(),
        },
    )


async def check_riesgo_termico(pool: asyncpg.Pool) -> CheckResult:
    """Clasifica los viajes en ruta con el reloj de fraguado.

    Dos umbrales ratificados (migracion 040), medidos desde
    ``operacion.reloj_termico_minutos`` (150 min en el PDR):

    - ``ALERTA_TEMPRANA``    -> quedan <= 60 min (minuto 90 del viaje) => WARN.
    - ``POR_VENCER_CRITICO`` -> quedan <= 30 min (minuto 120)         => CRITICO.
    - ``VENCIDO``            -> el limite ya paso                    => CRITICO.

    Solo se miran viajes sin confirmacion del cliente: si el cliente ya sello
    la recepcion, el reloj deja de importar.
    """
    inicio = perf_counter()
    temprana = int(
        await setting(pool, "operacion.alerta_temprana_minutos_antes", 60) or 60
    )
    critico = int(
        await setting(pool, "operacion.por_vencer_critico_minutos_antes", 30) or 30
    )
    # Si alguien invierte los umbrales en la base, se normaliza.
    if critico > temprana:
        temprana, critico = critico, temprana

    fila = await pool.fetchrow(
        """
        SELECT
            count(*) FILTER (
                WHERE limite_termico_fraguado < now()
            ) AS vencidos,
            count(*) FILTER (
                WHERE limite_termico_fraguado >= now()
                  AND limite_termico_fraguado < now() + ($1::int * INTERVAL '1 minute')
            ) AS por_vencer_criticos,
            count(*) FILTER (
                WHERE limite_termico_fraguado >= now() + ($1::int * INTERVAL '1 minute')
                  AND limite_termico_fraguado < now() + ($2::int * INTERVAL '1 minute')
            ) AS alerta_temprana
        FROM v_dispatch_timeline
        WHERE limite_termico_fraguado IS NOT NULL
          AND confirmacion_whatsapp_cliente IS NULL
        """,
        critico,
        temprana,
    )
    vencidos = int(fila["vencidos"] or 0) if fila else 0
    criticos = int(fila["por_vencer_criticos"] or 0) if fila else 0
    tempranos = int(fila["alerta_temprana"] or 0) if fila else 0
    latencia = _ms_desde(inicio)

    datos: dict[str, Any] = {
        # `total` conserva el significado historico: viajes ya vencidos.
        "total": vencidos,
        "vencidos": vencidos,
        "por_vencer_criticos": criticos,
        "alerta_temprana": tempranos,
        "umbral_alerta_temprana_min": temprana,
        "umbral_por_vencer_critico_min": critico,
    }

    if vencidos > 0:
        estado: Estado = CRITICO
        detalle = f"{vencidos} viaje(s) con limite termico vencido sin confirmar"
    elif criticos > 0:
        estado = CRITICO
        detalle = (
            f"{criticos} viaje(s) a {critico} min o menos del limite termico "
            "sin confirmar (POR_VENCER_CRITICO)"
        )
    elif tempranos > 0:
        estado = WARN
        detalle = (
            f"{tempranos} viaje(s) a {temprana} min o menos del limite termico "
            "sin confirmar (ALERTA_TEMPRANA)"
        )
    else:
        estado = OK
        detalle = "sin viajes en riesgo termico"

    return CheckResult(
        id="riesgo_termico",
        categoria=OPERACION,
        estado=estado,
        detalle=detalle,
        latencia_ms=latencia,
        datos=datos,
    )


async def check_recetas_provisionales(pool: asyncpg.Pool) -> CheckResult:
    """Reporta viajes despachados con una receta aun no validada por Julio.

    Ajuste ratificado 2026-11-08: la receta PROVISIONAL no bloquea la venta,
    pero el Centinela debe avisar para que la dosificacion se valide. Se
    miran los viajes sin salida (pendientes) y los de los ultimos 7 dias:
    un viaje viejo ya no requiere accion.

    Cierre Hito 1 (2026-11-08): la semilla oficial confirmo las 5 recetas.
    El chequeo cruza contra ``concrete_recipes.confirmado`` para no dejar un
    WARN eterno por viajes historicos cuyo payload nacio con la bandera en
    true. Si la receta ya fue validada, no hay accion pendiente.
    """
    inicio = perf_counter()
    fila = await pool.fetchrow(
        """
        SELECT count(*) AS total
          FROM v_dispatch_timeline t
          JOIN orders o ON o.id = t.order_id
          JOIN concrete_recipes r ON r.resistencia = o.resistencia
         WHERE r.confirmado IS NOT TRUE
           AND (t.tracking_payload ->> 'receta_provisional')::boolean IS TRUE
           AND (
                 t.salida_planta IS NULL
                 OR t.salida_planta >= now() - INTERVAL '7 days'
               )
        """
    )
    total = int(fila["total"] or 0) if fila else 0
    latencia = _ms_desde(inicio)
    if total > 0:
        estado: Estado = WARN
        detalle = (
            f"{total} viaje(s) con receta PROVISIONAL en los ultimos 7 dias o "
            "pendientes de despacho; Julio debe validar la dosificacion"
        )
    else:
        estado = OK
        detalle = "sin viajes con receta provisional"
    return CheckResult(
        id="recetas_provisionales",
        categoria=OPERACION,
        estado=estado,
        detalle=detalle,
        latencia_ms=latencia,
        datos={"total": total, "ventana_dias": 7},
    )


async def check_caja(pool: asyncpg.Pool, dia: date) -> CheckResult:
    """Verifica que la caja del dia anterior este cerrada.

    Se emite una sola fila agregada: ``faltantes`` vale 1 si falta el cierre
    y 0 si existe.
    """
    inicio = perf_counter()
    fila = await pool.fetchrow(
        """
        SELECT count(*) AS total
        FROM cash_closures
        WHERE fecha = $1::date
          AND estado = 'CERRADO'
        """,
        dia,
    )
    total = int(fila["total"] or 0) if fila else 0
    faltantes = 1 if total == 0 else 0
    latencia = _ms_desde(inicio)
    if faltantes:
        estado: Estado = WARN
        detalle = f"caja del {dia.isoformat()} sin cierre (estado CERRADO)"
    else:
        estado = OK
        detalle = f"caja del {dia.isoformat()} cerrada"
    return CheckResult(
        id="caja",
        categoria=OPERACION,
        estado=estado,
        detalle=detalle,
        latencia_ms=latencia,
        datos={"fecha": dia.isoformat(), "faltantes": faltantes},
    )


async def check_merma(
    pool: asyncpg.Pool, dia: date, zona: ZoneInfo
) -> CheckResult:
    """Compara cemento teorico vs real del dia anterior.

    Sin umbral configurado (``operacion.merma_cemento_pct_alerta`` nulo) el
    check queda ``NO_CONFIGURADO``: el PDR no fija la cifra.
    """
    inicio = perf_counter()
    umbral_raw = await setting(pool, "operacion.merma_cemento_pct_alerta", None)
    umbral = _decimal(umbral_raw)
    if umbral is None:
        return CheckResult(
            id="merma",
            categoria=OPERACION,
            estado=NO_CONFIGURADO,
            detalle=(
                "operacion.merma_cemento_pct_alerta sin definir "
                "(PDR no fija la cifra)"
            ),
            latencia_ms=_ms_desde(inicio),
            datos={"fecha": dia.isoformat(), "umbral_pct": None},
        )

    desde, hasta = _rango_dia(dia, zona)
    fila = await pool.fetchrow(
        """
        SELECT
            COALESCE(SUM(cemento_sacos_teorico), 0) AS teorico,
            COALESCE(SUM(cemento_sacos_real), 0)    AS real,
            count(*) FILTER (
                WHERE cemento_sacos_teorico IS NOT NULL
                  AND cemento_sacos_real IS NOT NULL
            ) AS filas
        FROM v_dispatch_timeline
        WHERE salida_planta >= $1
          AND salida_planta < $2
        """,
        desde,
        hasta,
    )
    teorico = _decimal(fila["teorico"]) if fila else None
    real = _decimal(fila["real"]) if fila else None
    filas = int(fila["filas"] or 0) if fila else 0
    latencia = _ms_desde(inicio)

    datos: dict[str, Any] = {
        "fecha": dia.isoformat(),
        "umbral_pct": umbral,
        "filas": filas,
        "teorico": teorico,
        "real": real,
    }

    if filas == 0 or teorico is None or real is None:
        return CheckResult(
            id="merma",
            categoria=OPERACION,
            estado=OK,
            detalle=f"sin datos de consumo de cemento para {dia.isoformat()}",
            latencia_ms=latencia,
            datos=datos,
        )
    if teorico <= 0:
        return CheckResult(
            id="merma",
            categoria=OPERACION,
            estado=NO_CONFIGURADO,
            detalle="consumo teorico de cemento nulo: no hay base de comparacion",
            latencia_ms=latencia,
            datos=datos,
        )

    desviacion = abs(real - teorico) / teorico * 100.0
    datos["desviacion_pct"] = round(desviacion, 2)
    if desviacion > umbral:
        estado: Estado = CRITICO
        detalle = (
            f"desviacion de cemento {desviacion:.2f}% supera el umbral "
            f"{umbral:.2f}%"
        )
    else:
        estado = OK
        detalle = (
            f"desviacion de cemento {desviacion:.2f}% dentro del umbral "
            f"{umbral:.2f}%"
        )
    return CheckResult(
        id="merma",
        categoria=OPERACION,
        estado=estado,
        detalle=detalle,
        latencia_ms=latencia,
        datos=datos,
    )


async def check_errores(pool: asyncpg.Pool) -> CheckResult:
    """Cuenta errores/criticos registrados en las ultimas 24 horas."""
    inicio = perf_counter()
    fila = await pool.fetchrow(
        """
        SELECT count(*) AS total
        FROM error_logs
        WHERE nivel IN ('ERROR', 'CRITICAL')
          AND created_at >= now() - INTERVAL '24 hours'
        """
    )
    total = int(fila["total"] or 0) if fila else 0
    latencia = _ms_desde(inicio)
    if total > 0:
        estado: Estado = WARN
        detalle = f"{total} error(es) registrados en las ultimas 24 h"
    else:
        estado = OK
        detalle = "sin errores registrados en las ultimas 24 h"
    return CheckResult(
        id="errores",
        categoria=OPERACION,
        estado=estado,
        detalle=detalle,
        latencia_ms=latencia,
        datos={"total": total},
    )


async def check_despachos_ayer(
    pool: asyncpg.Pool, dia: date, zona: ZoneInfo
) -> CheckResult:
    """Cuenta los viajes despachados (salida de planta) el dia anterior."""
    inicio = perf_counter()
    desde, hasta = _rango_dia(dia, zona)
    fila = await pool.fetchrow(
        """
        SELECT count(*) AS total
        FROM v_dispatch_timeline
        WHERE salida_planta >= $1
          AND salida_planta < $2
        """,
        desde,
        hasta,
    )
    total = int(fila["total"] or 0) if fila else 0
    return CheckResult(
        id="despachos_ayer",
        categoria=OPERACION,
        estado=OK,
        detalle=f"{total} viaje(s) despachados el {dia.isoformat()}",
        latencia_ms=_ms_desde(inicio),
        datos={"fecha": dia.isoformat(), "total": total},
    )
