"""Tests del motor de agenda v6.0 (calculo puro, sin base de datos).

Cubren la regla de choque de mixers, la disponibilidad y la normalizacion de
la flota configurada en ``system_settings``.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.m3_secretaria.agenda import (  # noqa: E402
    a_hhmm,
    a_minutos,
    conflicto_mixer,
    evaluar_disponibilidad,
    mixers_activos,
    se_solapan,
)

FECHA = date(2026, 11, 12)
MIXERS = [
    {"codigo": "MIXER-01", "capacidad_m3": 8},
    {"codigo": "MIXER-02", "capacidad_m3": 8},
]


def _fila(
    *,
    id_: str = "a1",
    mixer: str = "MIXER-01",
    inicio: str = "08:00",
    fin: str = "09:30",
    estado: str = "PROGRAMADO",
    fecha: date = FECHA,
    deleted_at=None,
) -> dict:
    return {
        "id": id_,
        "fecha_entrega": fecha.isoformat(),
        "hora_inicio": inicio,
        "hora_fin_estimada": fin,
        "mixer_codigo": mixer,
        "estado": estado,
        "deleted_at": deleted_at,
    }


def test_conversion_de_horas() -> None:
    assert a_minutos("08:15") == 495
    assert a_minutos("08:15:00") == 495
    assert a_hhmm(495) == "08:15"
    assert a_hhmm(-10) == "00:00"


def test_solapamiento_es_estricto_en_los_bordes() -> None:
    assert se_solapan(480, 570, 480, 570)
    assert se_solapan(480, 570, 540, 630)
    assert not se_solapan(480, 570, 570, 660)
    assert not se_solapan(570, 660, 480, 570)


def test_disponibilidad_reporta_mixer_ocupado_y_libre() -> None:
    resultado = evaluar_disponibilidad(
        filas=[_fila()],
        mixers=MIXERS,
        fecha=FECHA,
        hora="08:30",
        duracion_min=90,
    )
    estados = {m["codigo"]: m["estado"] for m in resultado["mixers"]}
    assert estados == {"MIXER-01": "OCUPADO", "MIXER-02": "LIBRE"}
    assert resultado["mixers_libres"] == ["MIXER-02"]
    assert resultado["hay_disponible"] is True


def test_disponibilidad_ignora_cancelados_y_eliminados() -> None:
    resultado = evaluar_disponibilidad(
        filas=[
            _fila(id_="a1", estado="CANCELADO"),
            _fila(id_="a2", estado="REAGENDADO"),
            _fila(id_="a3", mixer="MIXER-02", deleted_at="2026-11-01"),
        ],
        mixers=MIXERS,
        fecha=FECHA,
        hora="08:30",
        duracion_min=90,
    )
    assert resultado["mixers_libres"] == ["MIXER-01", "MIXER-02"]


def test_disponibilidad_sugiere_proxima_hora_cuando_todos_ocupados() -> None:
    filas = [
        _fila(id_="a1", mixer="MIXER-01"),
        _fila(id_="a2", mixer="MIXER-02"),
    ]
    resultado = evaluar_disponibilidad(
        filas=filas,
        mixers=MIXERS,
        fecha=FECHA,
        hora="08:30",
        duracion_min=90,
    )
    assert resultado["hay_disponible"] is False
    assert resultado["proxima_hora_disponible"] is not None
    assert a_minutos(resultado["proxima_hora_disponible"]) >= 570


def test_conflicto_devuelve_el_bloque_que_choca() -> None:
    choque = conflicto_mixer(
        filas=[_fila()],
        mixer_codigo="MIXER-01",
        fecha=FECHA,
        hora="09:00",
        duracion_min=90,
    )
    assert choque is not None
    assert choque["id"] == "a1"
    assert choque["hora_inicio"] == "08:00"
    assert choque["hora_fin"] == "09:30"


def test_conflicto_permite_agendar_al_borde_y_en_otro_mixer() -> None:
    assert (
        conflicto_mixer(
            filas=[_fila()],
            mixer_codigo="MIXER-01",
            fecha=FECHA,
            hora="09:30",
            duracion_min=60,
        )
        is None
    )
    assert (
        conflicto_mixer(
            filas=[_fila()],
            mixer_codigo="MIXER-02",
            fecha=FECHA,
            hora="08:30",
            duracion_min=60,
        )
        is None
    )


def test_conflicto_excluye_el_mismo_agendamiento_al_editar() -> None:
    assert (
        conflicto_mixer(
            filas=[_fila(id_="a1")],
            mixer_codigo="MIXER-01",
            fecha=FECHA,
            hora="08:30",
            duracion_min=90,
            excluir_id="a1",
        )
        is None
    )


def test_sin_mixer_asignado_no_bloquea_maquina() -> None:
    assert (
        conflicto_mixer(
            filas=[_fila(mixer="")],
            mixer_codigo="MIXER-01",
            fecha=FECHA,
            hora="08:30",
            duracion_min=90,
        )
        is None
    )


def test_mixers_activos_normaliza_y_filtra() -> None:
    flota = [
        {"codigo": "MIXER-01", "activo": True, "capacidad_m3": 8},
        {"codigo": "MIXER-02", "activo": False, "capacidad_m3": 8},
        {"codigo": "", "activo": True},
        {"activo": True},
    ]
    assert [m["codigo"] for m in mixers_activos(flota)] == ["MIXER-01"]


def test_mixers_activos_acepta_json_texto() -> None:
    assert mixers_activos('[{"codigo": "MIXER-01"}]')[0]["codigo"] == "MIXER-01"
    assert mixers_activos("no-json") == []
