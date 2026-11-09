"""Modulo 4 - Servicio de datos del Dashboard Gerencial.

Tres lecturas, una por Hero KPI, mas la cuota de mercado y el flujo historico
que alimenta el DSCR. El store en memoria reproduce el contrato para tests.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping, Protocol

import asyncpg

from .calculos import calcular_cuota_mercado, rango_periodo

ZONA_TERMICA_VERDE_MIN = 90
ZONA_TERMICA_AMBAR_MIN = 120

TODAS_LAS_PLANTAS = None


def _f(valor: Any) -> float | None:
    if valor is None:
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _d(valor: Any, por_defecto: str = "0") -> Decimal:
    if valor is None or valor == "":
        return Decimal(por_defecto)
    try:
        return Decimal(str(valor))
    except (TypeError, ValueError):
        return Decimal(por_defecto)


def semaforo_termico(minutos: float | None) -> str:
    if minutos is None:
        return "SIN_DATOS"
    if minutos < ZONA_TERMICA_VERDE_MIN:
        return "VERDE"
    if minutos <= ZONA_TERMICA_AMBAR_MIN:
        return "AMBAR"
    return "ROJO"


def _peor_semaforo(valores: list[str]) -> str:
    orden = {"ROJO": 3, "AMBAR": 2, "VERDE": 1, "SIN_DATOS": 0}
    return max(valores, key=lambda v: orden.get(v, 0), default="SIN_DATOS")


# ---------------------------------------------------------------------------
# Contrato
# ---------------------------------------------------------------------------
class DashboardStore(Protocol):
    async def hero_kpis(
        self, fecha: date | None = None, planta_codigo: str | None = None
    ) -> dict[str, Any]: ...

    async def cuota_mercado(
        self, *, periodo: str = "12_MESES_MOVILES", anio: int = 2026
    ) -> dict[str, Any]: ...

    async def flujo_operativo_mensual(self, dias: int = 90) -> float: ...

    async def benchmarks(self) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------
class PostgresDashboardStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def hero_kpis(
        self, fecha: date | None = None, planta_codigo: str | None = None
    ) -> dict[str, Any]:
        dia = fecha or date.today()
        planta = (planta_codigo or "").strip() or None

        caja = await self._pool.fetchrow(
            """
            SELECT
              COALESCE(SUM(monto) FILTER (
                  WHERE tipo_movimiento = 'COBRO' AND metodo = 'EFECTIVO'), 0) AS efectivo,
              COALESCE(SUM(monto) FILTER (
                  WHERE tipo_movimiento = 'COBRO' AND metodo = 'TRANSFERENCIA'), 0) AS transferencia,
              COALESCE(SUM(monto) FILTER (
                  WHERE tipo_movimiento = 'GASTO_CAJA_CHICA'), 0) AS caja_chica
              FROM payments
             WHERE fecha = $1
               AND deleted_at IS NULL
            """,
            dia,
        )
        cartera = await self._pool.fetchrow(
            """
            SELECT COALESCE(SUM(saldo_pendiente), 0) AS por_cobrar,
                   COUNT(*) FILTER (WHERE saldo_pendiente > 0) AS clientes
              FROM v_cliente_saldo
             WHERE estado = 'ACTIVO'
            """
        )
        fiado = await self._pool.fetchrow(
            """
            SELECT COALESCE(SUM(COALESCE(o.total_con_iva, o.total, 0)), 0) AS monto,
                   COUNT(*) AS ordenes,
                   COUNT(*) FILTER (WHERE o.excede_cupo_credito) AS excedidas
              FROM orders o
              JOIN plants p ON p.id = o.planta_id
             WHERE o.created_at::date = $1
               AND o.forma_pago = 'FIADO'
               AND o.estado <> 'ANULADA'
               AND ($2::text IS NULL OR p.codigo = $2)
            """,
            dia,
            planta,
        )

        volumen = await self._pool.fetchrow(
            """
            SELECT
              COALESCE(SUM(d.volumen_m3) FILTER (
                  WHERE o.created_at::date = $1), 0) AS hoy,
              COALESCE(SUM(d.volumen_m3) FILTER (
                  WHERE o.created_at >= date_trunc('month', $1::date)), 0) AS mes
              FROM mixer_dispatches d
              JOIN orders o ON o.id = d.order_id
              JOIN plants p ON p.id = o.planta_id
             WHERE o.estado <> 'ANULADA'
               AND ($2::text IS NULL OR p.codigo = $2)
            """,
            dia,
            planta,
        )

        en_ruta = await self._pool.fetch(
            """
            SELECT mixer_codigo, chofer_nombre, orden_numero, viaje_numero,
                   total_viajes_orden, salida_planta, dosificado_planta,
                   limite_termico_fraguado, cliente, resistencia
              FROM v_dispatch_timeline
             WHERE estado_actual = 'EN_RUTA'
             ORDER BY salida_planta NULLS LAST
            """
        )
        ahora = datetime.now(timezone.utc)
        mixers: list[dict[str, Any]] = []
        for fila in en_ruta:
            salida = fila["salida_planta"] or fila["dosificado_planta"]
            minutos = None
            if isinstance(salida, datetime):
                minutos = max(0.0, (ahora - salida.astimezone(timezone.utc)).total_seconds() / 60)
            mixers.append(
                {
                    "mixer_codigo": fila["mixer_codigo"],
                    "chofer": fila["chofer_nombre"],
                    "cliente": fila["cliente"],
                    "resistencia": fila["resistencia"],
                    "orden_numero": fila["orden_numero"],
                    "viaje": f"{fila['viaje_numero']}/{fila['total_viajes_orden']}",
                    "salida_planta": _iso(salida),
                    "limite_termico": _iso(fila["limite_termico_fraguado"]),
                    "minutos_en_ruta": None if minutos is None else round(minutos, 1),
                    "semaforo": semaforo_termico(minutos),
                }
            )

        bodega = await self._pool.fetchrow(
            """
            SELECT
              (SELECT stock_actual FROM materials WHERE codigo = 'CEMENTO')  AS cemento,
              (SELECT stock_actual FROM materials WHERE codigo = 'RETARDANTE') AS retardante
            """
        )
        receta = await self._pool.fetchrow(
            """
            SELECT cemento_sacos_m3, retardante_litros_m3
              FROM concrete_recipes WHERE resistencia = 'FC-210'
            """
        )
        m3_disponibles = _m3_disponibles(
            _f(bodega["cemento"]) if bodega else None,
            _f(bodega["retardante"]) if bodega else None,
            _f(receta["cemento_sacos_m3"]) if receta else None,
            _f(receta["retardante_litros_m3"]) if receta else None,
        )
        merma = await self._pool.fetchrow(
            """
            SELECT COALESCE(SUM((tracking_payload #>> '{consumo_materiales,cemento_sacos_teorico}')::numeric
                              - (tracking_payload #>> '{consumo_materiales,cemento_sacos_real}')::numeric), 0) AS merma,
                   COUNT(*) FILTER (
                       WHERE (tracking_payload #>> '{consumo_materiales,cemento_sacos_real}') IS NOT NULL
                   ) AS lecturas
              FROM mixer_dispatches
             WHERE created_at >= now() - interval '30 days'
            """
        )

        return {
            "fecha": dia.isoformat(),
            "planta": planta or "TODAS",
            "kpi_caja": {
                "efectivo_hoy": _f(caja["efectivo"]),
                "transferencias_hoy": _f(caja["transferencia"]),
                "cobrado_hoy": _f(_d(caja["efectivo"]) + _d(caja["transferencia"])),
                "caja_chica_hoy": _f(caja["caja_chica"]),
                "por_cobrar_total": _f(cartera["por_cobrar"]),
                "clientes_con_saldo": int(cartera["clientes"] or 0),
                "fiado_hoy": _f(fiado["monto"]),
                "ordenes_fiado_hoy": int(fiado["ordenes"] or 0),
                "ordenes_fiado_excedidas": int(fiado["excedidas"] or 0),
            },
            "kpi_operacion": {
                "m3_hoy": _f(volumen["hoy"]),
                "m3_mes": _f(volumen["mes"]),
                "mixers_en_ruta": len(mixers),
                "detalle_mixers": mixers,
                "semaforo_termico": _peor_semaforo([m["semaforo"] for m in mixers]),
            },
            "kpi_bodega": {
                "cemento_sacos": _f(bodega["cemento"]) if bodega else None,
                "retardante_litros": _f(bodega["retardante"]) if bodega else None,
                "m3_fc210_disponibles": m3_disponibles,
                "merma_cemento_sacos_30d": _f(merma["merma"]),
                "lecturas_reales_30d": int(merma["lecturas"] or 0),
                "alerta_merma": bool((_f(merma["merma"]) or 0) > 0),
            },
        }

    async def cuota_mercado(
        self, *, periodo: str = "12_MESES_MOVILES", anio: int = 2026
    ) -> dict[str, Any]:
        desde, hasta = rango_periodo(periodo, anio=anio)
        precio_cfg = await _setting(self._pool, "mercado.valorizacion", {})
        precio = _d((precio_cfg or {}).get("precio_m3"), "118.00")

        ventas = await self._pool.fetch(
            """
            SELECT COALESCE(c.provincia, 'SIN_PROVINCIA') AS provincia,
                   COALESCE(SUM(o.volumen_m3), 0) AS m3
              FROM orders o
              JOIN clients c ON c.id = o.cliente_id
             WHERE o.created_at::date BETWEEN $1 AND $2
               AND o.estado <> 'ANULADA'
             GROUP BY 1
            """,
            desde,
            hasta,
        )
        por_provincia = {
            _normalizar_provincia(fila["provincia"]): _d(fila["m3"]) for fila in ventas
        }
        benchmarks = await self._benchmarks_anio(anio)
        provincias = [
            calcular_cuota_mercado(
                provincia=provincia,
                anio=anio,
                ventas_m3=por_provincia.get(provincia, Decimal("0")),
                demanda_m3=_d(datos.get("demanda_m3")),
                precio_m3=precio,
            )
            for provincia, datos in benchmarks.items()
        ]
        return {
            "periodo": periodo,
            "anio": anio,
            "desde": desde.isoformat(),
            "hasta": hasta.isoformat(),
            "precio_valorizacion_m3": float(precio),
            "resistencia_valorizacion": (precio_cfg or {}).get("resistencia") or "FC-210",
            "provincias": provincias,
            "sin_provincia_m3": float(por_provincia.get("SIN_PROVINCIA", Decimal("0"))),
            "nota": (
                "Ventas sin provincia asignada no se reparten entre mercados; "
                "asignar clients.provincia desde Secretaria."
            ),
        }

    async def flujo_operativo_mensual(self, dias: int = 90) -> float:
        desde = date.today() - timedelta(days=max(1, int(dias)))
        fila = await self._pool.fetchrow(
            """
            SELECT COALESCE(SUM(monto) FILTER (
                       WHERE tipo_movimiento = 'COBRO' AND metodo <> 'FIADO'), 0)
                 - COALESCE(SUM(monto) FILTER (
                       WHERE tipo_movimiento = 'GASTO_CAJA_CHICA'), 0) AS flujo
              FROM payments
             WHERE fecha >= $1
               AND deleted_at IS NULL
            """,
            desde,
        )
        meses = max(1.0, dias / 30.0)
        return round(float(_d(fila["flujo"]) / Decimal(str(meses))), 2)

    async def benchmarks(self) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT provincia, anio, demanda_m3, precio_promedio_m3, fuente
              FROM market_benchmarks
             ORDER BY provincia, anio NULLS LAST
            """
        )
        return [
            {
                "provincia": fila["provincia"],
                "anio": fila["anio"],
                "demanda_m3": _f(fila["demanda_m3"]),
                "precio_promedio_m3": _f(fila["precio_promedio_m3"]),
                "fuente": fila["fuente"],
            }
            for fila in filas
        ]

    async def _benchmarks_anio(self, anio: int) -> dict[str, dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT DISTINCT ON (lower(provincia))
                   provincia, anio, demanda_m3
              FROM market_benchmarks
             WHERE anio = $1 OR anio IS NULL
             ORDER BY lower(provincia), anio NULLS LAST
            """,
            anio,
        )
        salida: dict[str, dict[str, Any]] = {}
        for fila in filas:
            provincia = _normalizar_provincia(fila["provincia"])
            salida[provincia] = {"demanda_m3": fila["demanda_m3"], "anio": fila["anio"]}
        return salida


# ---------------------------------------------------------------------------
# Memoria
# ---------------------------------------------------------------------------
@dataclass
class MemoryDashboardStore:
    clientes: list[dict[str, Any]] = field(default_factory=list)
    ordenes: list[dict[str, Any]] = field(default_factory=list)
    pagos: list[dict[str, Any]] = field(default_factory=list)
    viajes: list[dict[str, Any]] = field(default_factory=list)
    materiales: dict[str, float] = field(default_factory=dict)
    receta_fc210: dict[str, float] = field(default_factory=dict)
    benchmarks_data: list[dict[str, Any]] = field(default_factory=list)
    precio_mercado: float = 118.00

    def __post_init__(self) -> None:
        hoy = date.today()
        if not self.clientes:
            self.clientes = [
                {
                    "cliente_id": "11111111-1111-1111-1111-111111111111",
                    "nombre": "Constructora Reyes",
                    "provincia": "Orellana",
                    "estado": "ACTIVO",
                    "saldo_pendiente": 3136.0,
                },
                {
                    "cliente_id": "22222222-2222-2222-2222-222222222222",
                    "nombre": "Petroconstrucciones",
                    "provincia": "Sucumbios",
                    "estado": "ACTIVO",
                    "saldo_pendiente": 0.0,
                },
            ]
        if not self.ordenes:
            self.ordenes = [
                {
                    "orden_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "numero": 1001,
                    "cliente_id": self.clientes[0]["cliente_id"],
                    "resistencia": "FC-210",
                    "volumen_m3": 52.0,
                    "planta_codigo": "PLANTA-COCA",
                    "forma_pago": "FIADO",
                    "total": 6136.0,
                    "estado": "CONFIRMADA",
                    "excede_cupo_credito": True,
                    "created_at": hoy.isoformat(),
                },
                {
                    "orden_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                    "numero": 1002,
                    "cliente_id": self.clientes[1]["cliente_id"],
                    "resistencia": "FC-210",
                    "volumen_m3": 24.0,
                    "planta_codigo": "PLANTA-MOVIL",
                    "forma_pago": "TRANSFERENCIA",
                    "total": 2832.0,
                    "estado": "CONFIRMADA",
                    "excede_cupo_credito": False,
                    "created_at": hoy.isoformat(),
                },
            ]
        if not self.pagos:
            self.pagos = [
                {
                    "fecha": hoy.isoformat(),
                    "tipo_movimiento": "COBRO",
                    "metodo": "EFECTIVO",
                    "monto": 500.0,
                },
                {
                    "fecha": hoy.isoformat(),
                    "tipo_movimiento": "COBRO",
                    "metodo": "TRANSFERENCIA",
                    "monto": 2832.0,
                },
                {
                    "fecha": hoy.isoformat(),
                    "tipo_movimiento": "GASTO_CAJA_CHICA",
                    "metodo": "EFECTIVO",
                    "monto": 25.0,
                },
            ]
        if not self.viajes:
            salida = datetime.now(timezone.utc) - timedelta(minutes=45)
            self.viajes = [
                {
                    "dispatch_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
                    "orden_numero": 1001,
                    "cliente": "Constructora Reyes",
                    "resistencia": "FC-210",
                    "mixer_codigo": "MIXER-01",
                    "chofer_nombre": "Pedro Andy",
                    "viaje_numero": 1,
                    "total_viajes_orden": 7,
                    "volumen_m3": 8.0,
                    "estado_actual": "EN_RUTA",
                    "salida_planta": salida.isoformat(),
                    "dosificado_planta": salida.isoformat(),
                    "limite_termico_fraguado": None,
                    "cemento_sacos_teorico": 60.0,
                    "cemento_sacos_real": 58.0,
                }
            ]
        if not self.materiales:
            self.materiales = {"CEMENTO": 3500.0, "RETARDANTE": 600.0}
        if not self.receta_fc210:
            self.receta_fc210 = {
                "cemento_sacos_m3": 7.5,
                "retardante_litros_m3": 1.2,
            }
        if not self.benchmarks_data:
            self.benchmarks_data = [
                {"provincia": "Orellana", "anio": 2025, "demanda_m3": 120000.0},
                {"provincia": "Orellana", "anio": 2026, "demanda_m3": 120000.0},
                {"provincia": "Sucumbios", "anio": 2025, "demanda_m3": 95000.0},
                {"provincia": "Sucumbios", "anio": 2026, "demanda_m3": 95000.0},
            ]

    async def hero_kpis(
        self, fecha: date | None = None, planta_codigo: str | None = None
    ) -> dict[str, Any]:
        dia = (fecha or date.today()).isoformat()
        planta = (planta_codigo or "").strip() or None
        pagos = [
            p
            for p in self.pagos
            if str(p["fecha"])[:10] == dia and not p.get("deleted_at")
        ]
        efectivo = sum(
            _d(p["monto"])
            for p in pagos
            if p["tipo_movimiento"] == "COBRO" and p["metodo"] == "EFECTIVO"
        )
        transferencia = sum(
            _d(p["monto"])
            for p in pagos
            if p["tipo_movimiento"] == "COBRO" and p["metodo"] == "TRANSFERENCIA"
        )
        caja_chica = sum(
            _d(p["monto"]) for p in pagos if p["tipo_movimiento"] == "GASTO_CAJA_CHICA"
        )
        ordenes_hoy = [
            o
            for o in self.ordenes
            if str(o["created_at"])[:10] == dia
            and o["estado"] != "ANULADA"
            and (planta is None or o["planta_codigo"] == planta)
        ]
        fiado_hoy = sum(
            _d(o.get("total_con_iva") or o.get("total"))
            for o in ordenes_hoy
            if o["forma_pago"] == "FIADO"
        )
        excedidas = sum(
            1 for o in ordenes_hoy if o["forma_pago"] == "FIADO" and o["excede_cupo_credito"]
        )
        m3_hoy = sum(_d(o["volumen_m3"]) for o in ordenes_hoy)
        mes_prefijo = dia[:7]
        m3_mes = sum(
            _d(o["volumen_m3"])
            for o in self.ordenes
            if str(o["created_at"])[:7] == mes_prefijo and o["estado"] != "ANULADA"
        )
        ahora = datetime.now(timezone.utc)
        mixers = []
        for viaje in self.viajes:
            if viaje["estado_actual"] != "EN_RUTA":
                continue
            salida = viaje.get("salida_planta")
            minutos = None
            if salida:
                try:
                    fecha_salida = datetime.fromisoformat(str(salida))
                    if fecha_salida.tzinfo is None:
                        fecha_salida = fecha_salida.replace(tzinfo=timezone.utc)
                    minutos = max(
                        0.0, (ahora - fecha_salida).total_seconds() / 60
                    )
                except ValueError:
                    minutos = None
            mixers.append(
                {
                    "mixer_codigo": viaje["mixer_codigo"],
                    "chofer": viaje["chofer_nombre"],
                    "cliente": viaje["cliente"],
                    "resistencia": viaje["resistencia"],
                    "orden_numero": viaje["orden_numero"],
                    "viaje": f"{viaje['viaje_numero']}/{viaje['total_viajes_orden']}",
                    "salida_planta": salida,
                    "limite_termico": viaje.get("limite_termico_fraguado"),
                    "minutos_en_ruta": None if minutos is None else round(minutos, 1),
                    "semaforo": semaforo_termico(minutos),
                }
            )
        merma = sum(
            _d(v.get("cemento_sacos_teorico")) - _d(v.get("cemento_sacos_real"))
            for v in self.viajes
            if v.get("cemento_sacos_real") is not None
        )
        return {
            "fecha": dia,
            "planta": planta or "TODAS",
            "kpi_caja": {
                "efectivo_hoy": float(efectivo),
                "transferencias_hoy": float(transferencia),
                "cobrado_hoy": float(efectivo + transferencia),
                "caja_chica_hoy": float(caja_chica),
                "por_cobrar_total": float(
                    sum(_d(c.get("saldo_pendiente")) for c in self.clientes)
                ),
                "clientes_con_saldo": sum(
                    1 for c in self.clientes if _d(c.get("saldo_pendiente")) > 0
                ),
                "fiado_hoy": float(fiado_hoy),
                "ordenes_fiado_hoy": sum(
                    1 for o in ordenes_hoy if o["forma_pago"] == "FIADO"
                ),
                "ordenes_fiado_excedidas": excedidas,
            },
            "kpi_operacion": {
                "m3_hoy": float(m3_hoy),
                "m3_mes": float(m3_mes),
                "mixers_en_ruta": len(mixers),
                "detalle_mixers": mixers,
                "semaforo_termico": _peor_semaforo([m["semaforo"] for m in mixers]),
            },
            "kpi_bodega": {
                "cemento_sacos": self.materiales.get("CEMENTO"),
                "retardante_litros": self.materiales.get("RETARDANTE"),
                "m3_fc210_disponibles": _m3_disponibles(
                    self.materiales.get("CEMENTO"),
                    self.materiales.get("RETARDANTE"),
                    self.receta_fc210.get("cemento_sacos_m3"),
                    self.receta_fc210.get("retardante_litros_m3"),
                ),
                "merma_cemento_sacos_30d": float(merma),
                "lecturas_reales_30d": sum(
                    1 for v in self.viajes if v.get("cemento_sacos_real") is not None
                ),
                "alerta_merma": bool(merma > 0),
            },
        }

    async def cuota_mercado(
        self, *, periodo: str = "12_MESES_MOVILES", anio: int = 2026
    ) -> dict[str, Any]:
        desde, hasta = rango_periodo(periodo, anio=anio)
        por_provincia: dict[str, Decimal] = {}
        for orden in self.ordenes:
            if orden["estado"] == "ANULADA":
                continue
            fecha = str(orden["created_at"])[:10]
            if not (desde.isoformat() <= fecha <= hasta.isoformat()):
                continue
            cliente = next(
                (c for c in self.clientes if c["cliente_id"] == orden["cliente_id"]), None
            )
            provincia = _normalizar_provincia(
                (cliente or {}).get("provincia") or "SIN_PROVINCIA"
            )
            por_provincia[provincia] = por_provincia.get(provincia, Decimal("0")) + _d(
                orden["volumen_m3"]
            )

        benchmarks: dict[str, dict[str, Any]] = {}
        for fila in self.benchmarks_data:
            provincia = _normalizar_provincia(fila["provincia"])
            if fila.get("anio") in (anio, None):
                benchmarks[provincia] = fila
        precio = Decimal(str(self.precio_mercado))
        return {
            "periodo": periodo,
            "anio": anio,
            "desde": desde.isoformat(),
            "hasta": hasta.isoformat(),
            "precio_valorizacion_m3": float(precio),
            "resistencia_valorizacion": "FC-210",
            "provincias": [
                calcular_cuota_mercado(
                    provincia=provincia,
                    anio=anio,
                    ventas_m3=por_provincia.get(provincia, Decimal("0")),
                    demanda_m3=_d(datos.get("demanda_m3")),
                    precio_m3=precio,
                )
                for provincia, datos in benchmarks.items()
            ],
            "sin_provincia_m3": float(por_provincia.get("SIN_PROVINCIA", Decimal("0"))),
            "nota": (
                "Ventas sin provincia asignada no se reparten entre mercados; "
                "asignar clients.provincia desde Secretaria."
            ),
        }

    async def flujo_operativo_mensual(self, dias: int = 90) -> float:
        desde = date.today() - timedelta(days=max(1, int(dias)))
        total = Decimal("0")
        for pago in self.pagos:
            if pago.get("deleted_at"):
                continue
            fecha = str(pago["fecha"])[:10]
            if fecha < desde.isoformat():
                continue
            if pago["tipo_movimiento"] == "COBRO" and pago["metodo"] != "FIADO":
                total += _d(pago["monto"])
            elif pago["tipo_movimiento"] == "GASTO_CAJA_CHICA":
                total -= _d(pago["monto"])
        meses = max(1.0, dias / 30.0)
        return round(float(total) / meses, 2)

    async def benchmarks(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self.benchmarks_data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalizar_provincia(valor: Any) -> str:
    crudo = str(valor or "").strip().upper()
    if crudo.startswith("ORELLANA"):
        return "Orellana"
    if crudo.startswith("SUCUMB"):
        return "Sucumbios"
    return str(valor or "").strip() or "SIN_PROVINCIA"


def _m3_disponibles(
    cemento: float | None,
    retardante: float | None,
    sacos_m3: float | None,
    litros_m3: float | None,
) -> float | None:
    limites: list[float] = []
    if cemento is not None and sacos_m3:
        limites.append(float(cemento) / float(sacos_m3))
    if retardante is not None and litros_m3:
        limites.append(float(retardante) / float(litros_m3))
    if not limites:
        return None
    return round(min(limites), 1)


def _iso(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.isoformat()
    return str(valor)


async def _setting(pool: asyncpg.Pool, clave: str, por_defecto: Any) -> Any:
    from ..db import setting

    valor = await setting(pool, clave, por_defecto)
    return dict(valor) if isinstance(valor, Mapping) else valor
