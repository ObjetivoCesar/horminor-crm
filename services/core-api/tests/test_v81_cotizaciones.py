"""Tests de cotizaciones: contrato, calculo y presencia en el panel (v6.20)."""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from fastapi import HTTPException  # noqa: E402

from app.panel_acl import MODULOS  # noqa: E402
from app.routers import cotizaciones as cot  # noqa: E402


class PoolFalso:
    def __init__(self, filas):
        self.filas = list(filas)
        self.consultas: list[tuple[str, tuple]] = []

    async def fetchrow(self, sql: str, *args):
        self.consultas.append((sql, args))
        return self.filas.pop(0)


def _body(**extra):
    base = {
        "cliente_id": str(uuid.uuid4()),
        "obra_direccion": "Obra de prueba",
        "volumen_m3": Decimal("10"),
        "resistencia": "FC-210",
        "forma_pago": "FIADO",
        "extras": [],
    }
    base.update(extra)
    return cot.CotizacionIn(**base)


def test_calcula_total_con_iva_y_extra_cobrable() -> None:
    pool = PoolFalso(
        [
            {"id": uuid.uuid4(), "nombre": "Cliente Prueba"},
            {"precio_m3": Decimal("118"), "iva_pct": Decimal("15"), "precio_estado": "PROVISIONAL"},
            {"value": 15},
        ]
    )
    body = _body(extras=[cot.ExtraIn(descripcion="Flete", monto=Decimal("100"), cobrable=True)])
    datos = asyncio.run(cot._calcular(pool, body))

    assert datos["subtotal"] == Decimal("1280.00")
    assert datos["iva_monto"] == Decimal("192.00")
    assert datos["total"] == Decimal("1472.00")
    assert datos["precio_estado"] == "PROVISIONAL"
    assert datos["valida_hasta"] == date.today() + timedelta(days=15)


def test_extra_no_cobrable_no_suma_al_cliente() -> None:
    pool = PoolFalso(
        [
            {"id": uuid.uuid4(), "nombre": "Cliente Prueba"},
            {"precio_m3": Decimal("118"), "iva_pct": Decimal("15"), "precio_estado": "PROVISIONAL"},
            {"value": 15},
        ]
    )
    body = _body(
        extras=[cot.ExtraIn(descripcion="Retro para abrir paso", monto=Decimal("50"), cobrable=False)]
    )
    datos = asyncio.run(cot._calcular(pool, body))

    assert datos["subtotal"] == Decimal("1180.00")
    assert datos["total"] == Decimal("1357.00")


def test_sin_precio_en_receta_devuelve_precio_requerido() -> None:
    pool = PoolFalso(
        [
            {"id": uuid.uuid4(), "nombre": "Cliente Prueba"},
            {"precio_m3": None, "iva_pct": Decimal("15"), "precio_estado": "PROVISIONAL"},
        ]
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(cot._calcular(pool, _body()))

    assert exc.value.status_code == 422
    assert "PRECIO_REQUERIDO" in str(exc.value.detail)


def test_snapshot_y_hash_son_deterministicos() -> None:
    cotizacion = {
        "numero": "HORM-COT-2026-0001",
        "cliente_id": uuid.uuid4(),
        "obra_direccion": "Obra",
        "volumen_m3": Decimal("10"),
        "resistencia": "FC-210",
        "precio_m3": Decimal("118"),
        "precio_estado": "PROVISIONAL",
        "incluye_equipo": True,
        "incluye_bombeo": True,
        "forma_pago": "FIADO",
        "valida_hasta": date(2026, 11, 28),
        "subtotal": Decimal("1180"),
        "iva_pct": Decimal("15"),
        "iva_monto": Decimal("177"),
        "total": Decimal("1357"),
    }
    uno = cot._snapshot(cotizacion, [])
    dos = cot._snapshot(cotizacion, [])
    assert cot._hash(uno) == cot._hash(dos)
    assert len(cot._hash(uno)) == 64


def test_acl_y_rutas_de_cotizaciones() -> None:
    assert "cotizaciones" in MODULOS
    rutas = {r.path for r in cot.router.routes}
    assert "/api/v1/cotizaciones" in rutas
    assert "/api/v1/cotizaciones/{cotizacion_id}/aceptar" in rutas
    assert "/api/v1/cotizaciones/{cotizacion_id}/convertir" in rutas


def test_panel_tiene_cotizaciones_en_la_columna_izquierda() -> None:
    html = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "web"
        / "templates"
        / "panel.html"
    ).read_text(encoding="utf-8")

    assert 'data-role-btn="cotizaciones"' in html
    assert 'data-view="cotizaciones"' in html
    assert 'id="dlg-cotizacion"' in html
    assert "cotizaciones: 'Cotizaciones y ventas'" in html
    assert "cotizaciones: ['cotizaciones']" in html
