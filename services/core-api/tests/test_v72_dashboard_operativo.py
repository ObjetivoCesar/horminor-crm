"""Tests del dashboard operativo: operacion, inventario y cobranza (v6.21)."""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.m4_dashboard import operativo  # noqa: E402


class PoolFalso:
    def __init__(self, respuestas, filas=None):
        self.respuestas = list(respuestas)
        self.filas = list(filas or [])
        self.consultas: list[tuple[str, tuple]] = []

    async def fetch(self, sql: str, *args):
        self.consultas.append((sql, args))
        return self.respuestas.pop(0)

    async def fetchrow(self, sql: str, *args):
        self.consultas.append((sql, args))
        return self.filas.pop(0)


def _material(**extra):
    base = {
        "codigo": "CEMENTO",
        "nombre": "Cemento",
        "unidad": "saco",
        "stock_actual": 3500,
        "stock_minimo": 500,
        "ultimo_levantamiento_at": None,
        "stock_proyectado_disponible": 3500,
        "estado_alerta_proyectada": "SIN_FECHA_CONTEO",
        "necesario_ventas": 3212,
        "neto_registrado": -3212,
        "neto_simetrico": -3212,
        "brecha_asimetria": 0,
        "consumo_30d": 3212,
        "movimientos_teoricos_count": 249,
        "viajes_asimetria_count": 2,
    }
    base.update(extra)
    return base


def test_capacidad_semilla_es_inconsistente_y_no_inventa_42() -> None:
    cap = operativo._capacidad(
        [
            {"codigo": "MIXER-01", "capacidad_m3": 8, "viajes_max_dia": 0, "activo": True},
            {"codigo": "MIXER-02", "capacidad_m3": 8, "viajes_max_dia": 0, "activo": True},
            {"codigo": "MIXER-03", "capacidad_m3": 7, "viajes_max_dia": 0, "activo": True},
        ],
        {},
        {"mixers_activos_esperados": 2, "capacidad_unitaria_esperada_m3": 7, "ciclo_viaje_min": 110},
        {"hora_apertura": "07:00", "hora_cierre": "18:00"},
        {"libre_max_pct": 70, "ajustado_max_pct": 90},
    )

    assert cap["estado_configuracion"] == "CONFIGURACION_INCONSISTENTE"
    assert cap["efectiva_m3_dia"] is None
    assert cap["flota_m3_dia"] is None


def test_capacidad_2x7x3_da_42_y_cuello_flota() -> None:
    cap = operativo._capacidad(
        [
            {"codigo": "MIXER-01", "capacidad_m3": 7, "viajes_max_dia": 3, "activo": True},
            {"codigo": "MIXER-02", "capacidad_m3": 7, "viajes_max_dia": 3, "activo": True},
        ],
        {},
        {"mixers_activos_esperados": 2, "capacidad_unitaria_esperada_m3": 7, "ciclo_viaje_min": 110},
        {"hora_apertura": "07:00", "hora_cierre": "18:00"},
        {"libre_max_pct": 70, "ajustado_max_pct": 90},
    )

    assert cap["estado_configuracion"] == "CONFIGURADO_PARCIAL"
    assert cap["flota_m3_dia"] == "42"
    assert cap["jornada_m3_dia"] == "84"
    assert cap["efectiva_m3_dia"] == "42"
    assert cap["cuello_botella"] == "FLOTA"


def test_capacidad_planta_es_el_cuello_cuando_es_menor() -> None:
    cap = operativo._capacidad(
        [
            {"codigo": "MIXER-01", "capacidad_m3": 7, "viajes_max_dia": 3, "activo": True},
            {"codigo": "MIXER-02", "capacidad_m3": 7, "viajes_max_dia": 3, "activo": True},
        ],
        {"PLANTA-COCA": {"produccion_m3_hora": 5, "horas_efectivas_dia": 6}},
        {"mixers_activos_esperados": 2, "capacidad_unitaria_esperada_m3": 7, "ciclo_viaje_min": 110},
        {"hora_apertura": "07:00", "hora_cierre": "18:00"},
        {"libre_max_pct": 70, "ajustado_max_pct": 90},
    )

    assert cap["planta_m3_dia"] == "30"
    assert cap["efectiva_m3_dia"] == "30"
    assert cap["cuello_botella"] == "PLANTA"


def test_capacidad_sin_activos_es_no_configurado() -> None:
    cap = operativo._capacidad([], {}, {}, {}, {})
    assert cap["estado_configuracion"] == "NO_CONFIGURADO"
    assert cap["efectiva_m3_dia"] is None


def test_inventario_excluye_agua_y_ordena_los_cuatro_materiales() -> None:
    import asyncio

    pool = PoolFalso([[_material()], []])
    resultado = asyncio.run(operativo.inventario(pool))

    assert "AGUA" not in operativo.MATERIALES_TABLERO
    assert operativo.MATERIALES_TABLERO == ("CEMENTO", "ARENA", "RIPIO", "RETARDANTE")
    sql, args = pool.consultas[0]
    assert "v_stock_proyectado" in sql
    assert args[0] == ["CEMENTO", "ARENA", "RIPIO", "RETARDANTE"]
    assert resultado["fuente"][0] == "materials"
    assert resultado["filtros"]["incluye_agua"] is False
    assert resultado["datos"]["materiales"][0]["stock"] == "3500"


def test_inventario_sin_conteo_no_presenta_semilla_como_real() -> None:
    import asyncio

    fila = _material(
        codigo="ARENA",
        nombre="Arena",
        unidad="m3",
        stock_actual=450,
        stock_minimo=80,
        necesario_ventas=206.44,
        neto_registrado=-198.12,
        neto_simetrico=-206.44,
        brecha_asimetria=8.32,
        consumo_30d=198.12,
    )
    resultado = asyncio.run(operativo.inventario(PoolFalso([[fila], []])))

    assert resultado["vacio"]["motivo"] == "SIN_CONTEO_FISICO"
    assert resultado["datos"]["sin_conteo"] == 1
    assert resultado["datos"]["materiales"][0]["stock_neto_registrado"] == "251.88"
    assert resultado["datos"]["materiales"][0]["stock_neto_corregido_por_asimetria"] == "243.56"


def test_inventario_con_conteo_no_devuelve_vacio() -> None:
    import asyncio

    fila = _material(
        ultimo_levantamiento_at=datetime(2026, 11, 10, 8, 0),
        stock_proyectado_disponible=3490,
        estado_alerta_proyectada="OK",
    )
    resultado = asyncio.run(operativo.inventario(PoolFalso([[fila], []])))

    assert resultado["vacio"] is None
    assert resultado["datos"]["materiales"][0]["ultimo_conteo"].startswith("2026-11-10")


def test_inventario_expone_triple_lectura_y_asimetria() -> None:
    import asyncio

    resultado = asyncio.run(operativo.inventario(PoolFalso([[_material()], []])))
    material = resultado["datos"]["materiales"][0]

    assert material["necesario_ventas"] == "3212"
    assert material["stock_neto_registrado"] == "288"
    assert material["cobertura_declarada_pct"] == "108.97"
    assert material["cobertura_neta_registrada_pct"] == "8.97"
    assert resultado["datos"]["alerta_integridad_bodega"]["viajes_asimetria_kardex_count"] == 2
    assert resultado["datos"]["alerta_integridad_bodega"]["movimientos_teoricos_count"] == 249


def _orden(numero, total, cliente="Ing. Reyes", cid="c1", provincia="Orellana", **extra):
    base = {
        "id": f"o-{numero}",
        "numero": numero,
        "cliente_id": cid,
        "cliente": cliente,
        "provincia": provincia,
        "credit_limit_usd": None,
        "total": total,
        "fecha_vencimiento": None,
        "fecha_emision": date(2026, 11, 9),
        "volumen_m3": 16,
        "m3_confirmados": 0,
        "m3_salidos": 0,
    }
    base.update(extra)
    return base


def test_cobranza_documento_unico_excluye_factura_ficticia() -> None:
    import asyncio

    pool = PoolFalso(
        [
            [_orden(55, 43424), _orden(56, 9448.4), _orden(57, 2171.2, cliente="Cliente Prueba", cid="c2", provincia="Sucumbios")],
            [
                {
                    "id": "f1",
                    "numero": "PRUEBA-0001",
                    "orden_id": "o-55",
                    "cliente_id": "c1",
                    "total": 43424,
                    "fecha": date(2026, 11, 12),
                    "fecha_vencimiento": None,
                    "es_ficticia": True,
                }
            ],
            [],
        ],
        filas=[{"saldo": 55043.6}],
    )
    resultado = asyncio.run(operativo.cobranza(pool))

    assert resultado["datos"]["reconciliacion"]["total_documental_unico_usd"] == "55043.6"
    assert resultado["datos"]["reconciliacion"]["ficticias_excluidas_count"] == 1
    assert resultado["datos"]["reconciliacion"]["diferencia_reconciliacion_usd"] == "0"
    assert resultado["datos"]["documentos_total"] == 3


def test_cobranza_avisa_cuando_no_hay_fechas_capturadas() -> None:
    import asyncio

    pool = PoolFalso([[_orden(55, 43424)], [], []], filas=[{"saldo": 43424}])
    resultado = asyncio.run(operativo.cobranza(pool))

    assert resultado["vacio"]["motivo"] == "SIN_FECHAS_CAPTURADAS"
    assert "antiguedad" in resultado["vacio"]["mensaje"]
    assert resultado["datos"]["caja"]["esperada_7d"] is None
    assert resultado["datos"]["caja"]["documentos_sin_fecha_count"] == 1


def test_cobranza_sin_documentos() -> None:
    import asyncio

    resultado = asyncio.run(operativo.cobranza(PoolFalso([[], [], []], filas=[{"saldo": 0}])))

    assert resultado["vacio"]["motivo"] == "SIN_DOCUMENTOS"


def test_cobranza_exigibilidad_separa_confirmado_de_salido() -> None:
    import asyncio

    orden = _orden(
        57,
        2171.2,
        cliente="Cliente Prueba",
        cid="c2",
        provincia="Sucumbios",
        volumen_m3=16,
        m3_confirmados=8,
        m3_salidos=16,
    )
    pool = PoolFalso([[orden], [], []], filas=[{"saldo": 2171.2}])
    resultado = asyncio.run(operativo.cobranza(pool))
    desglose = resultado["datos"]["desglose_exigibilidad"]

    assert desglose["recepcion_confirmada_o_facturada_usd"] == "1085.6"
    assert desglose["con_viaje_salido_planta_usd"] == "2171.2"
    assert desglose["comprometido_sin_salida_planta_usd"] == "0"


def test_superadmin_persiste_viajes_y_capacidad_declarada() -> None:
    import asyncio

    from app.superadmin.store import MemoryConfigStore

    store = MemoryConfigStore()

    async def _flujo():
        await store.guardar_seccion(
            "flota_y_operacion",
            {
                "mixers": [
                    {
                        "codigo": "MIXER-01",
                        "capacidad_m3": 7,
                        "viajes_max_dia": 3,
                        "planta_asignada": "PLANTA-COCA",
                        "activo": True,
                    }
                ],
                "capacidad_plantas": {
                    "PLANTA-COCA": {
                        "produccion_m3_hora": None,
                        "horas_efectivas_dia": None,
                    }
                },
                "supuestos_capacidad": {
                    "ciclo_viaje_min": 110,
                    "mixers_activos_esperados": 2,
                },
                "umbrales_ocupacion": {
                    "libre_max_pct": 70,
                    "ajustado_max_pct": 90,
                },
            },
        )
        return await store.leer_seccion("flota_y_operacion")

    leida = asyncio.run(_flujo())

    assert leida["mixers"][0]["viajes_max_dia"] == 3
    assert leida["mixers"][0]["planta_asignada"] == "PLANTA-COCA"
    assert leida["capacidad_plantas"]["PLANTA-COCA"]["produccion_m3_hora"] is None
    assert leida["supuestos_capacidad"]["ciclo_viaje_min"] == 110
    assert leida["umbrales_ocupacion"]["libre_max_pct"] == 70


def test_panel_banner_primero_y_agenda_encapsulada() -> None:
    html = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "web"
        / "templates"
        / "panel.html"
    ).read_text(encoding="utf-8")

    assert html.index('id="julio-ventanilla"') < html.index('data-kpi-window="operacion"')
    assert html.index('data-kpi-window="operacion"') < html.index('id="chart-op-bullet"')
    assert html.count("data-dash-tab=") == 4
    assert 'class="sec-accion primary"' in html
    assert 'data-sub-view="agenda"' in html
    for chart_id in (
        "chart-op-bullet",
        "chart-op-serie",
        "chart-op-resistencia",
        "chart-inventario",
        "chart-fechas",
        "chart-cobranza",
        "cob-documentos",
    ):
        assert f'id="{chart_id}"' in html


def test_router_expone_los_tres_endpoints() -> None:
    from app.m4_dashboard.router import router

    rutas = {r.path for r in router.routes}
    assert "/api/v1/dashboard/operacion" in rutas
    assert "/api/v1/dashboard/inventario" in rutas
    assert "/api/v1/dashboard/cobranza" in rutas
