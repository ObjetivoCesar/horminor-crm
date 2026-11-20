"""Agenda visual: normalizacion y reparto por pestañas (sin base de datos)."""

from __future__ import annotations

from app.agenda import eventos as eventos_svc
from app.agenda.router import _tipos_permitidos


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
