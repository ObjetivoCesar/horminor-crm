"""Agenda visual: normalizacion y reparto por pestañas (sin base de datos)."""

from __future__ import annotations

from datetime import timedelta

from app.agenda import eventos as eventos_svc
from app.agenda.router import _tipos_permitidos
from app.asistente.comercial_bridge import es_agenda_personal
from app.comercial.intencion import es_peticion_cita, parse_cita
from app import tiempo


def test_conteo_suma_por_tipo() -> None:
    lista = [
        {"tipo": "mixers"},
        {"tipo": "recordatorios"},
        {"tipo": "recordatorios"},
        {"tipo": "julio"},
        {"tipo": "equipo"},
    ]
    assert eventos_svc.conteo(lista) == {
        "mixers": 1,
        "recordatorios": 2,
        "julio": 1,
        "equipo": 1,
    }


def test_tipos_permitidos_respeta_modulos_del_perfil() -> None:
    perfil = {
        "modulos_permitidos": {
            "agenda_despachos": True,
            "clientes_cartera": True,
            "cerebro": False,
            "secretaria_ventanilla": False,
        }
    }
    assert _tipos_permitidos(perfil) == ["mixers", "julio"]


def test_evento_normaliza_hora_y_texto() -> None:
    evento = eventos_svc._evento(
        identificador="abc",
        tipo="recordatorios",
        fecha="2026-11-21",
        hora="10:00:00",
        titulo="  Recordatorio   a Pedro ",
        detalle="  hola  ",
        estado="pendiente",
    )
    assert evento["hora"] == "10:00"
    assert evento["titulo"] == "Recordatorio a Pedro"
    assert evento["detalle"] == "hola"
    assert evento["estado"] == "PENDIENTE"
    assert evento["zona"] == "America/Guayaquil"


def test_un_compromiso_en_mi_agenda_no_exige_lead() -> None:
    texto = (
        "Tengo un cliente que visitar el día de mañana a las 13:00 "
        "en la entrada a Orellana, registra en mi agenda"
    )
    assert es_peticion_cita(texto)
    assert es_agenda_personal(texto)
    datos = parse_cita(texto)
    assert datos["tipo"] == "VISITA"
    assert datos["hora"] == "13:00"
    assert datos["fecha"] == tiempo.hoy() + timedelta(days=1)
    assert datos["nombre"] is None


def test_una_visita_con_nombre_no_es_agenda_personal() -> None:
    texto = "Agenda una visita con Prueba Agenda mañana a las 11 de la mañana"
    assert es_peticion_cita(texto)
    assert not es_agenda_personal(texto)
