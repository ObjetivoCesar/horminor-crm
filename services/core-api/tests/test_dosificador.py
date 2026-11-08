"""Pruebas del motor determinista (Modulo 2). Sin base de datos."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.m2_planta import (
    Receta,
    RecetaIncompletaError,
    RecetaNoConfirmadaError,
    VolumenInvalidoError,
    calcular_consumo,
    dividir_en_viajes,
    estado_termico,
    limite_termico,
)
from app.m2_planta.dosificador import PoliticaViajeInvalidaError

FC210 = Receta(
    resistencia="FC-210",
    cemento_sacos_m3=Decimal("7.5"),
    arena_m3_m3=None,
    ripio_m3_m3=None,
    agua_litros_m3=None,
    retardante_litros_m3=Decimal("1.2"),
    saco_kg=None,
    confirmado=True,
    fuente="test",
)

FC210_PROVISIONAL = Receta(**{**FC210.__dict__, "confirmado": False})


def test_320_m3_se_dividen_en_40_viajes_de_8():
    plan = dividir_en_viajes(Decimal("320"), Decimal("8"))
    assert plan.total_viajes == 40
    assert all(v == Decimal("8") for v in plan.viajes)
    assert sum(plan.viajes) == Decimal("320")
    assert plan.excedente_m3 == 0


def test_52_m3_ultimo_viaje_parcial():
    plan = dividir_en_viajes(Decimal("52"), Decimal("8"))
    assert plan.total_viajes == 7
    assert plan.viajes == tuple([Decimal("8")] * 6 + [Decimal("4")])
    assert sum(plan.viajes) == Decimal("52")


def test_ultimo_completo_reporta_excedente():
    plan = dividir_en_viajes(Decimal("52"), Decimal("8"), "ultimo_completo")
    assert plan.total_viajes == 7
    assert sum(plan.viajes) == Decimal("56")
    assert plan.excedente_m3 == Decimal("4")


def test_distribucion_uniforme_conserva_el_total():
    plan = dividir_en_viajes(Decimal("52"), Decimal("8"), "distribucion_uniforme")
    assert plan.total_viajes == 7
    assert sum(plan.viajes) == Decimal("52")


@pytest.mark.parametrize("volumen", [0, -1])
def test_volumen_invalido(volumen):
    with pytest.raises(VolumenInvalidoError):
        dividir_en_viajes(Decimal(volumen), Decimal("8"))


def test_politica_invalida():
    with pytest.raises(PoliticaViajeInvalidaError):
        dividir_en_viajes(Decimal("10"), Decimal("8"), "lo_que_sea")


def test_consumo_receta_confirmada():
    consumo = calcular_consumo(FC210, Decimal("8"))
    assert consumo.cemento_sacos == Decimal("60.000")
    assert consumo.retardante_litros == Decimal("9.600")
    assert consumo.provisional is False


def test_receta_no_confirmada_bloquea_el_calculo():
    with pytest.raises(RecetaNoConfirmadaError):
        calcular_consumo(FC210_PROVISIONAL, Decimal("8"))


def test_receta_no_confirmada_con_permiso_explicito():
    consumo = calcular_consumo(FC210_PROVISIONAL, Decimal("8"), permitir_provisional=True)
    assert consumo.provisional is True
    assert consumo.cemento_sacos == Decimal("60.000")


def test_receta_sin_cemento_es_incompleta():
    vacia = Receta(**{**FC210.__dict__, "cemento_sacos_m3": None})
    with pytest.raises(RecetaIncompletaError):
        calcular_consumo(vacia, Decimal("8"))


def test_limite_termico_150_minutos():
    salida = datetime(2026, 5, 15, 8, 52, tzinfo=timezone(timedelta(hours=-5)))
    limite = limite_termico(salida, 150)
    assert limite == salida + timedelta(minutes=150)


def test_estado_termico():
    ahora = datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc)
    assert estado_termico(ahora, ahora + timedelta(minutes=60)) == "OK"
    assert estado_termico(ahora, ahora + timedelta(minutes=10)) == "POR_VENCER"
    assert estado_termico(ahora, ahora - timedelta(minutes=1)) == "VENCIDO"
