"""Calendario y precedencia de Gato (2026-11-19).

Caso real: un dictado con «agendar» y «entrega» lo capturo el atajo comercial
antes que el Cerebro, y el seguimiento «este sábado y domingo» fallo porque la
herramienta de disponibilidad recibio la fecha como texto.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app import tiempo
from app.asistente.bibliotecario import Bibliotecario
from app.asistente.guardas import CifraNoVerificada, verificar
from app.asistente.persona import render_prompt
from app.asistente.router import _contexto_dictado, _puente
from app.cerebro import Evidencia, HechoCitado
from app.cerebro.dinero import dinero_ya_entro
from app.cerebro.extractor import _CONFIRMA_PAGO
from app.comercial.intencion import parse_cita


class PoolFalso:
    def __init__(self) -> None:
        self.fecha = None

    async def fetch(self, _sql: str, fecha):
        self.fecha = fecha
        return []

    async def fetchval(self, _sql: str):
        return [{"codigo": "MIXER-01", "activo": True}]


def test_el_dictado_gana_sobre_el_atajo_comercial() -> None:
    texto = (
        "dictado: tenemos que agendar este sábado y este domingo "
        "la entrega de 70 m3"
    )

    assert _puente(texto) == "cerebro"


def test_el_atajo_comercial_sigue_funcionando_sin_prefijo() -> None:
    assert _puente("agenda una visita a Paola mañana a las 10:30") == "agenda"
    assert _puente("dame los leads caídos") == "leads"


async def test_la_disponibilidad_acepta_una_fecha_iso() -> None:
    pool = PoolFalso()
    biblio = Bibliotecario(pool)

    await biblio.disponibilidad_agenda("2026-11-21")

    assert pool.fecha == date(2026, 11, 21)


def test_parse_cita_entiende_este_sabado_y_domingo() -> None:
    hoy = tiempo.hoy()
    sabado = hoy + timedelta(days=(5 - hoy.weekday()) % 7)
    domingo = hoy + timedelta(days=(6 - hoy.weekday()) % 7)

    datos_sabado = parse_cita("agenda una visita este sábado a las 10:30")
    datos_domingo = parse_cita("agenda una medición el domingo a las 8:00")

    assert datos_sabado["fecha"] == sabado
    assert datos_sabado["hora"] == "10:30"
    assert datos_domingo["fecha"] == domingo
    assert datos_domingo["hora"] == "08:00"


def test_el_prompt_de_gato_dice_hoy_y_el_pais() -> None:
    prompt = render_prompt(
        "Julio",
        "SUPERADMIN",
        datetime(2026, 11, 19, 15, 0, tzinfo=timezone.utc),
    )

    assert "Ecuador (America/Guayaquil)" in prompt
    assert "Hoy: 2026-11-19" in prompt


def test_la_guarda_acepta_cifras_del_dictado() -> None:
    verificar(
        "El dictado habla de 70 m³ y 4000 USD.",
        [],
        ["dictado: 70 metros cúbicos y 4 mil dólares"],
    )


def test_la_guarda_sigue_bloqueando_una_cifra_sin_fuente() -> None:
    with pytest.raises(CifraNoVerificada):
        verificar("Son 70 m³.", [], ["hola, ¿cómo va todo?"])


def test_el_contexto_lleva_solo_el_dictado_anterior_si_se_continua() -> None:
    historial = [
        {"role": "user", "content": "dictado: cliente Pastrana, 7 m3"},
        {"role": "assistant", "content": "Antes de ejecutar necesito: ¿los 300 USD ya entraron?"},
        {"role": "user", "content": "dictado: me dio 300 en efectivo"},
        {"role": "assistant", "content": "Antes de ejecutar necesito: ¿qué cliente es?"},
    ]

    contexto = _contexto_dictado(historial, "si, me acaba de dar 300")

    assert contexto is not None
    assert "me dio 300" in contexto
    assert "Pastrana" not in contexto
    assert _contexto_dictado(historial, "nueva operacion: escuela 7 m3 para mañana") is None
    assert _contexto_dictado([], "si") is None


def test_la_confirmacion_de_efectivo_se_reconoce() -> None:
    assert _CONFIRMA_PAGO.search("si efectivamente me acaba de dar en efectivo")
    assert _CONFIRMA_PAGO.search("ya me dio el dinero en contado")
    assert not _CONFIRMA_PAGO.search("todavia no me ha dado nada")


def test_el_dinero_ya_entro_con_me_acaba_de_dar() -> None:
    hechos = [
        HechoCitado(
            clave="pago.recibido",
            valor=True,
            estado="EXTRAIDO",
            tipo="BOOLEANO",
            evidencia=Evidencia(
                cita="me acaba de dar en efectivo",
                sostiene="me acaba de dar en efectivo",
                crudo_inicio=0,
                crudo_fin=28,
                start_ms=None,
                end_ms=None,
                confianza=None,
                hablante="SUPERADMIN",
            ),
        )
    ]

    assert dinero_ya_entro(
        hechos,
        "si efectivamente me acaba de dar en efectivo 300",
        Decimal("300"),
    )
