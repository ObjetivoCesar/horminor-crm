"""Tests del dashboard operativo: inventario y cobranza (v6.20)."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.m4_dashboard import operativo  # noqa: E402


class PoolFalso:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.consultas: list[tuple[str, tuple]] = []

    async def fetch(self, sql: str, *args):
        self.consultas.append((sql, args))
        return self.respuestas.pop(0)


def test_inventario_excluye_agua_y_ordena_los_cuatro_materiales() -> None:
    import asyncio

    pool = PoolFalso(
        [[
            {
                "codigo": "CEMENTO",
                "nombre": "Cemento",
                "unidad": "saco",
                "stock_real_fisico": 3500,
                "stock_proyectado_disponible": 3500,
                "stock_minimo": 500,
                "ultimo_levantamiento_at": None,
                "estado_alerta_proyectada": "SIN_FECHA_CONTEO",
            }
        ]]
    )
    resultado = asyncio.run(operativo.inventario(pool))

    assert "AGUA" not in operativo.MATERIALES_TABLERO
    assert operativo.MATERIALES_TABLERO == ("CEMENTO", "ARENA", "RIPIO", "RETARDANTE")
    sql, args = pool.consultas[0]
    assert "v_stock_proyectado" in sql
    assert args[0] == ["CEMENTO", "ARENA", "RIPIO", "RETARDANTE"]
    assert resultado["fuente"] == ["v_stock_proyectado"]
    assert resultado["filtros"]["incluye_agua"] is False
    assert resultado["datos"]["materiales"][0]["stock"] == "3500"


def test_inventario_sin_conteo_no_presenta_semilla_como_real() -> None:
    import asyncio

    fila = {
        "codigo": "ARENA",
        "nombre": "Arena",
        "unidad": "m3",
        "stock_real_fisico": 450,
        "stock_proyectado_disponible": 450,
        "stock_minimo": 80,
        "ultimo_levantamiento_at": None,
        "estado_alerta_proyectada": "SIN_FECHA_CONTEO",
    }
    resultado = asyncio.run(operativo.inventario(PoolFalso([[fila]])))

    assert resultado["vacio"]["motivo"] == "SIN_CONTEO_FISICO"
    assert resultado["datos"]["sin_conteo"] == 1


def test_inventario_con_conteo_no_devuelve_vacio() -> None:
    import asyncio

    fila = {
        "codigo": "CEMENTO",
        "nombre": "Cemento",
        "unidad": "saco",
        "stock_real_fisico": 3500,
        "stock_proyectado_disponible": 3490,
        "stock_minimo": 500,
        "ultimo_levantamiento_at": datetime(2026, 11, 10, 8, 0),
        "estado_alerta_proyectada": "OK",
    }
    resultado = asyncio.run(operativo.inventario(PoolFalso([[fila]])))

    assert resultado["vacio"] is None
    assert resultado["datos"]["materiales"][0]["ultimo_conteo"].startswith("2026-11-10")


def test_cobranza_arma_los_cuatro_cubos_y_no_confunde_documento_con_saldo() -> None:
    import asyncio

    cubos = [
        {"tipo": "ORDEN", "estado_vencimiento": "SIN_VENCIMIENTO", "documentos": 4, "monto": 55043.6},
        {"tipo": "FACTURA", "estado_vencimiento": "VENCIDA", "documentos": 1, "monto": 43424},
    ]
    clientes = [{"nombre": "Ing. Reyes", "total_facturado": 55043.6, "saldo_pendiente": 12000}]
    saldo = [{"saldo": 12000}]

    resultado = asyncio.run(operativo.cobranza(PoolFalso([cubos, clientes, saldo])))

    estados = {c["estado"]: c for c in resultado["datos"]["cubos"]}
    assert list(estados) == ["VENCIDA", "POR_VENCER_7", "CORRIENTE", "SIN_VENCIMIENTO"]
    assert estados["VENCIDA"]["documentos"] == 1
    assert estados["POR_VENCER_7"]["documentos"] == 0
    assert resultado["datos"]["documentos"] == 5
    assert resultado["datos"]["saldo_total"] == "12000"
    assert resultado["fuente"] == ["v_cobranza_documentos", "v_cliente_saldo"]
    assert resultado["vacio"] is None


def test_cobranza_avisa_cuando_no_hay_fechas_capturadas() -> None:
    import asyncio

    cubos = [
        {"tipo": "ORDEN", "estado_vencimiento": "SIN_VENCIMIENTO", "documentos": 4, "monto": 55043.6},
    ]
    resultado = asyncio.run(operativo.cobranza(PoolFalso([cubos, [], [{"saldo": 0}]])))

    assert resultado["vacio"]["motivo"] == "SIN_FECHAS_CAPTURADAS"
    assert "antiguedad" in resultado["vacio"]["mensaje"]


def test_cobranza_sin_documentos() -> None:
    import asyncio

    resultado = asyncio.run(operativo.cobranza(PoolFalso([[], [], [{"saldo": 0}]])))

    assert resultado["vacio"]["motivo"] == "SIN_DOCUMENTOS"


def test_router_expone_los_dos_endpoints() -> None:
    from app.m4_dashboard.router import router

    rutas = {r.path for r in router.routes}
    assert "/api/v1/dashboard/inventario" in rutas
    assert "/api/v1/dashboard/cobranza" in rutas
