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


class RepoFalso:
    def __init__(self, encontrada):
        self.encontrada = encontrada
        self.confirmada = None
        self.evento = None

    async def buscar_cotizacion_abierta(self, cliente_id):
        return self.encontrada

    async def confirmar_cotizacion(self, cotizacion_id, **kwargs):
        self.confirmada = (cotizacion_id, kwargs)
        return {"id": cotizacion_id, "numero": "HORM-COT-2026-0001"}

    async def registrar_evento_cotizacion(self, cotizacion_id, **kwargs):
        self.evento = (cotizacion_id, kwargs)


class NotifierFalso:
    def __init__(self):
        self.mensajes = []

    async def enviar_texto(self, telefono, texto):
        self.mensajes.append((telefono, texto))
        return True


class AlerterFalso:
    def __init__(self):
        self.alertas = []

    async def alertar(self, **kwargs):
        self.alertas.append(kwargs)
        return True


def _pipeline(repo):
    from app.m1_whatsapp.pipeline import WhatsAppPipeline

    notifier = NotifierFalso()
    alerter = AlerterFalso()
    pipe = WhatsAppPipeline(
        repo=repo,
        identidad=None,
        juez=None,
        bunny=None,
        notifier=notifier,
        alerter=alerter,
    )
    return pipe, notifier, alerter


def test_clasificador_de_respuestas() -> None:
    from app.m1_whatsapp.pipeline import clasificar_respuesta_cotizacion

    assert clasificar_respuesta_cotizacion("Confirmo") == "CONFIRMACION"
    assert clasificar_respuesta_cotizacion("sí, de acuerdo") == "CONFIRMACION"
    assert clasificar_respuesta_cotizacion("muy caro, bajame el precio") == "NEGOCIACION"
    assert clasificar_respuesta_cotizacion("no me interesa") == "RECHAZO"
    assert clasificar_respuesta_cotizacion("¿incluye bombeo?") == "PREGUNTA"
    assert clasificar_respuesta_cotizacion("hola") == "AMBIGUA"


def test_gate_confirmacion_acepta_y_responde() -> None:
    from types import SimpleNamespace

    from app.m1_whatsapp.pipeline import ResultadoLote

    repo = RepoFalso(
        {
            "multiple": False,
            "cotizacion": {"id": "cot-1", "numero": "HORM-COT-2026-0001", "estado": "ENVIADA"},
        }
    )
    pipe, notifier, alerter = _pipeline(repo)
    resultado = ResultadoLote(
        telefono="+593990000013", rol="CLIENTE", origen_identidad="registro_cliente"
    )
    lote = SimpleNamespace(telefono="+593990000013", texto="Confirmo", ultimo_id="wamid-1")

    manejo = asyncio.run(pipe._gate_cotizacion(lote, "cliente-1", resultado))

    assert manejo is True
    assert repo.confirmada is not None
    assert "COTIZACION_CONFIRMADA" in resultado.acciones
    assert "quedó confirmada" in notifier.mensajes[0][1]
    assert alerter.alertas[0]["codigo"] == "COTIZACION_CONFIRMADA"


def test_gate_multiples_cotizaciones_pregunta_cual() -> None:
    from types import SimpleNamespace

    from app.m1_whatsapp.pipeline import ResultadoLote

    repo = RepoFalso(
        {
            "multiple": True,
            "cotizaciones": [
                {"id": "c1", "numero": "HORM-COT-2026-0001"},
                {"id": "c2", "numero": "HORM-COT-2026-0002"},
            ],
        }
    )
    pipe, notifier, _ = _pipeline(repo)
    resultado = ResultadoLote(
        telefono="+593990000013", rol="CLIENTE", origen_identidad="registro_cliente"
    )
    lote = SimpleNamespace(telefono="+593990000013", texto="Confirmo", ultimo_id="wamid-2")

    assert asyncio.run(pipe._gate_cotizacion(lote, "cliente-1", resultado)) is True
    assert "COTIZACION_MULTIPLE_PREGUNTADA" in resultado.acciones
    assert "varias cotizaciones" in notifier.mensajes[0][1]
    assert repo.confirmada is None


def test_gate_negociacion_registra_evento_sin_aceptar() -> None:
    from types import SimpleNamespace

    from app.m1_whatsapp.pipeline import ResultadoLote

    repo = RepoFalso(
        {
            "multiple": False,
            "cotizacion": {"id": "cot-1", "numero": "HORM-COT-2026-0001", "estado": "ENVIADA"},
        }
    )
    pipe, _, _ = _pipeline(repo)
    resultado = ResultadoLote(
        telefono="+593990000013", rol="CLIENTE", origen_identidad="registro_cliente"
    )
    lote = SimpleNamespace(
        telefono="+593990000013", texto="Muy caro, bajame el precio", ultimo_id="wamid-3"
    )

    assert asyncio.run(pipe._gate_cotizacion(lote, "cliente-1", resultado)) is True
    assert repo.confirmada is None
    assert repo.evento[1]["tipo"] == "NEGOCIACION"
    assert "COTIZACION_NEGOCIACION" in resultado.acciones


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
