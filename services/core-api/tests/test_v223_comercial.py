"""Pruebas del nucleo comercial: reglas puras y fecha de Ecuador."""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app import tiempo  # noqa: E402
from app.comercial import citas, leads  # noqa: E402


def test_normaliza_tildes_y_espacios() -> None:
    assert leads.normalizar("  No  Me   Interesa ") == "no me interesa"
    assert leads.normalizar("Está caro") == "esta caro"


def test_telefono_solo_digitos() -> None:
    assert leads.telefono("+593 99 000 0000") == "593990000000"
    with pytest.raises(ValueError):
        leads.telefono("")


def test_coincide_por_frase_completa() -> None:
    assert leads.coincide("No me interesa, gracias", ["no me interesa"])
    assert leads.coincide("Está caro para mi", ["esta caro"])
    assert not leads.coincide("me interesa mucho", ["no me interesa"])
    assert not leads.coincide("", ["no me interesa"])


def test_elegir_regla_respeta_el_orden() -> None:
    reglas = [
        {"clave": "RECHAZO", "patrones": ["no me interesa"], "estado_destino": "CAIDO"},
        {"clave": "PRECIO", "patrones": ["esta caro"], "estado_destino": "EN_ESPERA"},
    ]
    assert leads.elegir_regla("No me interesa", reglas)["clave"] == "RECHAZO"
    assert leads.elegir_regla("esta caro", reglas)["clave"] == "PRECIO"
    assert leads.elegir_regla("hola", reglas) is None


def test_cita_no_se_agenda_en_el_pasado() -> None:
    ayer = tiempo.hoy() - timedelta(days=1)
    with pytest.raises(ValueError):
        citas.validar(tipo="VISITA", fecha=ayer, origen="PANEL", duracion_min=60)
    citas.validar(tipo="VISITA", fecha=tiempo.hoy(), origen="PANEL", duracion_min=60)


def test_cita_rechaza_tipo_y_origen_invalidos() -> None:
    with pytest.raises(ValueError):
        citas.validar(tipo="OTRO", fecha=tiempo.hoy(), origen="PANEL", duracion_min=60)
    with pytest.raises(ValueError):
        citas.validar(tipo="VISITA", fecha=tiempo.hoy(), origen="OTRO", duracion_min=60)
    with pytest.raises(ValueError):
        citas.validar(tipo="VISITA", fecha=tiempo.hoy(), origen="PANEL", duracion_min=5)


def test_detecta_leads_caidos_y_agendar() -> None:
    from app.asistente import comercial_bridge as puente

    assert puente.es_leads_caidos("dame los leads caidos")
    assert puente.es_leads_caidos("leads sin respuesta")
    assert not puente.es_leads_caidos("dame los leads")
    assert puente.es_agendar("agenda una visita a Paola manana a las 10:30")
    assert not puente.es_agendar("como va la cartera")


def test_parse_cita_usa_la_fecha_de_ecuador() -> None:
    from app.asistente import comercial_bridge as puente

    hoy = tiempo.hoy()
    datos = puente.parse_cita("agenda una visita a Paola manana a las 10:30")
    assert datos["fecha"] == hoy + timedelta(days=1)
    assert datos["hora"] == "10:30"
    assert datos["nombre"] == "paola"
    assert datos["tipo"] == "VISITA"

    reunion = puente.parse_cita("agenda una reunion con Juan hoy a las 9")
    assert reunion["fecha"] == hoy
    assert reunion["hora"] == "09:00"
    assert reunion["tipo"] == "REUNION"


def test_parse_cita_deja_lo_que_falta() -> None:
    from app.asistente import comercial_bridge as puente

    datos = puente.parse_cita("agenda una visita")
    assert datos["fecha"] is None
    assert datos["hora"] is None
    assert datos["nombre"] is None
