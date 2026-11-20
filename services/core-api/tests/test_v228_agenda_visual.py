"""Agenda visual: normalizacion y reparto por pestañas (sin base de datos)."""

from __future__ import annotations

from datetime import timedelta

from decimal import Decimal

from app.agenda import eventos as eventos_svc
from app.agenda.router import _tipos_permitidos
from app.asistente.comercial_bridge import es_agenda_personal
from app.comercial.intencion import (
    es_cancelacion_cita,
    es_correccion_cita,
    es_peticion_cita,
    parse_cita,
    parse_correccion,
)
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


def test_la_correccion_toma_la_ultima_hora_dicha() -> None:
    texto = "rectifico no es a la 13:00 es a las 14:00"
    assert es_correccion_cita(texto)
    cambio = parse_correccion(
        texto,
        fecha_base=tiempo.hoy() + timedelta(days=1),
        hora_base="13:00",
    )
    assert cambio["hora"] == "14:00"
    assert cambio["dijo_hora"] is True
    assert cambio["dijo_fecha"] is False


def test_la_correccion_puede_cambiar_solo_la_fecha() -> None:
    texto = "cambia la cita al domingo"
    assert es_correccion_cita(texto)
    cambio = parse_correccion(
        texto, fecha_base=tiempo.hoy(), hora_base="13:00"
    )
    assert cambio["hora"] == "13:00"
    assert cambio["dijo_fecha"] is True
    assert cambio["fecha"].weekday() == 6


def test_una_cita_nueva_no_se_confunde_con_una_correccion() -> None:
    assert not es_correccion_cita(
        "mejor agenda una visita con Prueba Agenda mañana a las 9:00"
    )
    assert es_cancelacion_cita("cancela la cita")
    assert not es_cancelacion_cita("cancela el recordatorio")


def test_las_horas_del_dia_no_se_confunden() -> None:
    assert parse_cita("Agenda una visita mañana a las 2 de la tarde")["hora"] == "14:00"
    assert parse_cita("Agenda una visita mañana a las 12 de la noche")["hora"] == "00:00"
    assert parse_cita("Agenda una visita mañana a las 2")["hora"] is None


def test_de_la_manana_no_es_el_dia_siguiente() -> None:
    datos = parse_cita("Agenda una visita hoy a las 9 de la mañana")
    assert datos["fecha"] == tiempo.hoy()
    datos2 = parse_cita("Agenda una visita mañana a las 9 de la mañana")
    assert datos2["fecha"] == tiempo.hoy() + timedelta(days=1)


def test_media_hora_y_verbos_de_movimiento() -> None:
    assert parse_cita("Agenda una visita mañana a las 2 y media")["hora"] == "02:30"
    assert es_correccion_cita("movamos la cita al viernes")
    assert not es_cancelacion_cita("cancela este pedido")
    assert not es_cancelacion_cita("cancela este despacho")


def test_las_cifras_dictadas_en_dolares_se_autorizan() -> None:
    from app.asistente.recordatorios import cifras_de

    assert Decimal("300.00") in cifras_de("nos debe un abono de 300 dólares")


def test_el_mixer_encuentra_cliente_y_telefono() -> None:
    from app.asistente.agenda_bridge import (
        _nombre,
        _telefono,
        es_correccion_tarea,
        es_peticion_mixer,
    )

    texto = (
        "Agenda el mixer para mañana a las 14:00 con 6 metros cúbicos de 210 "
        "para Manuel Minga en la entrada a Orellana"
    )
    assert es_peticion_mixer(texto)
    assert _nombre(texto) == "manuel minga"
    assert _telefono("Manuel Minga 0963410092") == "593963410092"
    assert es_correccion_tarea("cambia la tarea para el viernes a las 9")
