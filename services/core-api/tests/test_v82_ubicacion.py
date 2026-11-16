"""Tests v8.2: ubicacion de la obra y Sabueso visible.

Que protegen estos tests:
- La ubicacion se guarda tal como llega (texto y/o pin real). Nada se estima.
- Un pin incompleto o sin origen se rechaza: no se inventan coordenadas.
- El pin que comparte el cliente por WhatsApp cae en la cotizacion abierta.
- El PDF y el panel muestran la ubicacion; el buscador no queda tapado.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from fastapi import HTTPException  # noqa: E402

from app.m1_whatsapp.models import (  # noqa: E402
    IncomingMessage,
    MessageBatch,
    UbicacionCompartida,
)
from app.m1_whatsapp.pipeline import WhatsAppPipeline  # noqa: E402
from app.m1_whatsapp.repositorio import MemoriaRepositorio  # noqa: E402
from app.m1_whatsapp.webhook import normalizar_evento  # noqa: E402
from app.routers import cotizaciones as cot  # noqa: E402
from app.services.factura_pdf import generar_pdf  # noqa: E402

PANEL = RAIZ_SERVICIO / "app" / "web" / "templates" / "panel.html"


class PoolFalso:
    def __init__(self, filas):
        self.filas = list(filas)

    async def fetchrow(self, sql: str, *args):
        return self.filas.pop(0)


def _body(**extra):
    base = {
        "cliente_id": str(uuid.uuid4()),
        "obra_direccion": "Obra de prueba",
        "volumen_m3": Decimal("10"),
        "resistencia": "FC-210",
        "forma_pago": "FIADO",
        "validez_dias": 15,
        "extras": [],
    }
    base.update(extra)
    return cot.CotizacionIn(**base)


def _pool_cliente_receta():
    return PoolFalso(
        [
            {"id": uuid.uuid4(), "nombre": "Cliente Prueba"},
            {
                "precio_m3": Decimal("118"),
                "iva_pct": Decimal("15"),
                "precio_estado": "PROVISIONAL",
            },
        ]
    )


# ---------------------------------------------------------------------------
# Calculo y contrato de la cotizacion
# ---------------------------------------------------------------------------
def test_calcular_guarda_texto_y_pin_real() -> None:
    datos = asyncio.run(
        cot._calcular(
            _pool_cliente_receta(),
            _body(
                ubicacion_texto="  Km 3 via Loreto, frente a la escuela  ",
                ubicacion_lat=Decimal("-0.4621"),
                ubicacion_lng=Decimal("-76.9871"),
                ubicacion_origen="GPS",
            ),
        )
    )

    assert datos["ubicacion_texto"] == "Km 3 via Loreto, frente a la escuela"
    assert datos["ubicacion_lat"] == Decimal("-0.4621000")
    assert datos["ubicacion_lng"] == Decimal("-76.9871000")
    assert datos["ubicacion_origen"] == "GPS"


def test_calcular_sin_ubicacion_deja_todo_en_null() -> None:
    datos = asyncio.run(cot._calcular(_pool_cliente_receta(), _body()))

    assert datos["ubicacion_texto"] is None
    assert datos["ubicacion_lat"] is None
    assert datos["ubicacion_lng"] is None
    assert datos["ubicacion_origen"] is None


def test_calcular_rechaza_pin_incompleto() -> None:
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            cot._calcular(
                _pool_cliente_receta(),
                _body(ubicacion_lat=Decimal("-0.46"), ubicacion_origen="GPS"),
            )
        )

    assert exc.value.status_code == 422
    assert "UBICACION_INCOMPLETA" in str(exc.value.detail)


def test_calcular_rechaza_pin_sin_origen() -> None:
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            cot._calcular(
                _pool_cliente_receta(),
                _body(
                    ubicacion_lat=Decimal("-0.46"),
                    ubicacion_lng=Decimal("-76.98"),
                ),
            )
        )

    assert exc.value.status_code == 422
    assert "UBICACION_ORIGEN_REQUERIDO" in str(exc.value.detail)


def test_resumen_expone_pin_y_enlace_de_mapa() -> None:
    fila = {
        "id": uuid.uuid4(),
        "numero": "HORM-COT-2026-0001",
        "cliente_id": uuid.uuid4(),
        "cliente_nombre": "Cliente Prueba",
        "obra_direccion": "Obra",
        "volumen_m3": Decimal("10"),
        "resistencia": "FC-210",
        "precio_m3": Decimal("118"),
        "precio_estado": "PROVISIONAL",
        "forma_pago": "FIADO",
        "valida_hasta": date(2026, 11, 28),
        "estado": "BORRADOR",
        "version": 1,
        "subtotal": Decimal("1180"),
        "iva_pct": Decimal("15"),
        "iva_monto": Decimal("177"),
        "total": Decimal("1357"),
        "orden_id": None,
        "created_at": datetime(2026, 11, 13, tzinfo=timezone.utc),
        "ubicacion_texto": "Km 3",
        "ubicacion_lat": Decimal("-0.4621000"),
        "ubicacion_lng": Decimal("-76.9871000"),
        "ubicacion_origen": "WHATSAPP",
        "ubicacion_solicitada_at": datetime(2026, 11, 13, tzinfo=timezone.utc),
        "ubicacion_recibida_at": datetime(2026, 11, 13, tzinfo=timezone.utc),
    }

    resumen = cot._resumen(fila)

    assert resumen["ubicacion_origen"] == "WHATSAPP"
    assert resumen["ubicacion_lat"] == pytest.approx(-0.4621)
    assert resumen["ubicacion_maps_url"] == "https://www.google.com/maps?q=-0.4621,-76.9871"
    assert resumen["ubicacion_recibida_at"] is not None


def test_resumen_sin_pin_no_inventa_enlace() -> None:
    fila = {
        "id": uuid.uuid4(),
        "numero": "HORM-COT-2026-0002",
        "cliente_id": uuid.uuid4(),
        "cliente_nombre": "Cliente Prueba",
        "obra_direccion": "Obra sin pin",
        "volumen_m3": Decimal("5"),
        "resistencia": "FC-210",
        "precio_m3": Decimal("118"),
        "precio_estado": "PROVISIONAL",
        "forma_pago": "FIADO",
        "valida_hasta": date(2026, 11, 28),
        "estado": "BORRADOR",
        "version": 1,
        "subtotal": Decimal("590"),
        "iva_pct": Decimal("15"),
        "iva_monto": Decimal("88.50"),
        "total": Decimal("678.50"),
        "orden_id": None,
        "created_at": datetime(2026, 11, 13, tzinfo=timezone.utc),
    }

    resumen = cot._resumen(fila)

    assert resumen["ubicacion_maps_url"] is None
    assert resumen["ubicacion_lat"] is None


def test_ruta_pedir_ubicacion_publicada() -> None:
    rutas = {r.path for r in cot.router.routes}
    assert "/api/v1/cotizaciones/{cotizacion_id}/pedir-ubicacion" in rutas


# ---------------------------------------------------------------------------
# WhatsApp: pin entrante
# ---------------------------------------------------------------------------
def _payload(mensaje: dict) -> dict:
    return {
        "event": "messages.upsert",
        "data": [
            {
                "key": {
                    "remoteJid": "593999999999@s.whatsapp.net",
                    "fromMe": False,
                    "id": "LOC1",
                },
                "message": mensaje,
            }
        ],
    }


def test_webhook_lee_pin_fijo() -> None:
    mensajes = normalizar_evento(
        _payload(
            {
                "locationMessage": {
                    "degreesLatitude": -0.4621,
                    "degreesLongitude": -76.9871,
                    "name": "Obra Loreto",
                }
            }
        )
    )

    assert len(mensajes) == 1
    ubicacion = mensajes[0].ubicacion
    assert ubicacion is not None
    assert ubicacion.latitud == pytest.approx(-0.4621)
    assert ubicacion.longitud == pytest.approx(-76.9871)
    assert ubicacion.nombre == "Obra Loreto"
    assert ubicacion.en_vivo is False


def test_webhook_lee_pin_en_vivo() -> None:
    mensajes = normalizar_evento(
        _payload(
            {
                "liveLocationMessage": {
                    "degreesLatitude": "-0.5",
                    "degreesLongitude": "-76.9",
                }
            }
        )
    )

    assert len(mensajes) == 1
    ubicacion = mensajes[0].ubicacion
    assert ubicacion is not None
    assert ubicacion.en_vivo is True


def test_webhook_descarta_pin_sin_coordenadas() -> None:
    assert normalizar_evento(_payload({"locationMessage": {"name": "sin numeros"}})) == []


# ---------------------------------------------------------------------------
# Pipeline: el pin cae en la cotizacion abierta
# ---------------------------------------------------------------------------
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


def _pipe(repo):
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


def _lote(ubicacion: UbicacionCompartida) -> MessageBatch:
    return MessageBatch(
        telefono="0999999999",
        mensajes=(
            IncomingMessage(
                mensaje_id="wamid-loc-1", telefono="0999999999", ubicacion=ubicacion
            ),
        ),
    )


def _repo_con_cotizacion() -> MemoriaRepositorio:
    return MemoriaRepositorio(
        cotizaciones=[
            {
                "id": "cot-1",
                "numero": "HORM-COT-2026-0001",
                "cliente_id": "cli-1",
                "estado": "ENVIADA",
                "orden": 1,
            }
        ]
    )


def test_pipeline_adjunta_pin_y_avisa_al_cliente() -> None:
    from app.m1_whatsapp.pipeline import ResultadoLote

    repo = _repo_con_cotizacion()
    pipe, notifier, alerter = _pipe(repo)
    resultado = ResultadoLote(
        telefono="0999999999", rol="CLIENTE", origen_identidad="registro_cliente"
    )
    ubicacion = UbicacionCompartida(
        latitud=-0.4621, longitud=-76.9871, nombre="Obra Loreto"
    )

    manejo = asyncio.run(pipe._gate_ubicacion(_lote(ubicacion), "cli-1", resultado))

    assert manejo is True
    assert resultado.acciones[-1] == "UBICACION_GUARDADA"
    assert repo.ubicaciones[0]["cotizacion_id"] == "cot-1"
    assert repo.cotizaciones[0]["ubicacion_lat"] == pytest.approx(-0.4621)
    assert "HORM-COT-2026-0001" in notifier.mensajes[0][1]
    assert alerter.alertas[0]["codigo"] == "COTIZACION_UBICACION"


def test_pipeline_sin_cotizacion_no_inventa_nada() -> None:
    from app.m1_whatsapp.pipeline import ResultadoLote

    repo = MemoriaRepositorio()
    pipe, notifier, _ = _pipe(repo)
    resultado = ResultadoLote(
        telefono="0999999999", rol="CLIENTE", origen_identidad="registro_cliente"
    )
    ubicacion = UbicacionCompartida(latitud=-0.4621, longitud=-76.9871)

    manejo = asyncio.run(pipe._gate_ubicacion(_lote(ubicacion), "cli-1", resultado))

    assert manejo is False
    assert "UBICACION_SIN_COTIZACION_ABIERTA" in resultado.acciones
    assert repo.ubicaciones == []
    assert notifier.mensajes == []


def test_repositorio_memoria_prefiere_cotizacion_sin_pin() -> None:
    repo = MemoriaRepositorio(
        cotizaciones=[
            {
                "id": "con-pin",
                "numero": "A",
                "cliente_id": "cli-1",
                "estado": "ENVIADA",
                "orden": 2,
                "ubicacion_lat": -0.4,
            },
            {
                "id": "sin-pin",
                "numero": "B",
                "cliente_id": "cli-1",
                "estado": "ENVIADA",
                "orden": 1,
            },
        ]
    )

    guardada = asyncio.run(
        repo.guardar_ubicacion_cotizacion(
            "cli-1", latitud=-0.5, longitud=-76.9, texto="Obra"
        )
    )

    assert guardada is not None
    assert guardada["id"] == "sin-pin"
    assert "con-pin" not in {u["cotizacion_id"] for u in repo.ubicaciones}


def test_pin_whatsapp_no_pisa_la_referencia_escrita() -> None:
    """El nombre del pin solo rellena: la referencia del asesor se conserva."""
    repo = MemoriaRepositorio(
        cotizaciones=[
            {
                "id": "ya-escrita",
                "numero": "A",
                "cliente_id": "cli-1",
                "estado": "ENVIADA",
                "orden": 2,
                "ubicacion_texto": "Km 3 via Loreto, junto al tanque",
            },
            {
                "id": "sin-texto",
                "numero": "B",
                "cliente_id": "cli-2",
                "estado": "ENVIADA",
                "orden": 1,
            },
        ]
    )

    asyncio.run(
        repo.guardar_ubicacion_cotizacion(
            "cli-1", latitud=-0.5, longitud=-76.9, texto="Obra La Joya"
        )
    )
    asyncio.run(
        repo.guardar_ubicacion_cotizacion(
            "cli-2", latitud=-0.6, longitud=-76.8, texto="Obra La Joya"
        )
    )

    por_id = {c["id"]: c for c in repo.cotizaciones}
    assert por_id["ya-escrita"]["ubicacion_texto"] == "Km 3 via Loreto, junto al tanque"
    assert por_id["sin-texto"]["ubicacion_texto"] == "Obra La Joya"


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def test_pdf_de_cotizacion_con_pin_se_genera() -> None:
    pdf = generar_pdf(
        {
            "tipo_documento": "COTIZACION",
            "numero": "HORM-COT-2026-0001",
            "fecha": date(2026, 11, 13),
            "referencia": "Cotizacion HORM-COT-2026-0001",
            "cliente_nombre": "Cliente Prueba",
            "cliente_ruc": "0999999999001",
            "cliente_ciudad": "El Coca",
            "obra_direccion": "Km 3 via Loreto",
            "ubicacion": {
                "texto": "Frente a la escuela",
                "lat": -0.4621,
                "lng": -76.9871,
                "origen": "WHATSAPP",
                "maps_url": "https://www.google.com/maps?q=-0.4621,-76.9871",
            },
            "resistencia": "FC-210",
            "volumen_m3": "7.00",
            "precio_m3": "118.00",
            "precio_estado": "PROVISIONAL",
            "forma_pago": "POR DEFINIR",
            "validez": "2026-11-28",
            "subtotal": "826.00",
            "iva_pct": "15.00",
            "iva_monto": "123.90",
            "total": "949.90",
            "empresa": {"company_name": "HORMINOR", "ruc": "2290000000001"},
            "extras": [],
        }
    )

    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 3000


# ---------------------------------------------------------------------------
# Panel: ubicacion y Sabueso por encima del resto
# ---------------------------------------------------------------------------
def test_panel_tiene_campos_de_ubicacion() -> None:
    html = PANEL.read_text(encoding="utf-8")

    assert 'id="cot-ubicacion"' in html
    assert 'id="cot-ubicacion-lat"' in html
    assert 'id="cot-ubicacion-lng"' in html
    assert 'id="cot-ubicacion-origen"' in html
    assert "usarMiUbicacionCot()" in html
    assert "pedirUbicacionCot()" in html
    assert "onUbicacionTextoCot(this.value)" in html
    assert "ubicacion_maps_url" in html


def test_panel_manda_la_ubicacion_al_backend() -> None:
    html = PANEL.read_text(encoding="utf-8")

    assert "ubicacion_texto: ubicacion.texto || null" in html
    assert "ubicacion_lat: ubicacion.lat" in html
    assert "ubicacion_lng: ubicacion.lng" in html
    assert "ubicacion_origen:" in html


def test_sabueso_no_queda_debajo_de_las_otras_tarjetas() -> None:
    html = PANEL.read_text(encoding="utf-8")

    # El backdrop-filter de .card crea contexto de apilamiento: la tarjeta del
    # buscador necesita su propio z-index, no basta el del desplegable.
    assert ".card.card-buscar-clientes" in html
    assert "z-index: 6;" in html
    assert 'class="card card-buscar-clientes"' in html
    assert "onBuscarClientesTecla(event)" in html
    assert "navSugerenciasClientes" in html
    assert 'role="listbox"' in html
    assert "sabueso-saldo" in html
