"""Extractor: sobre del LLM verificado contra el texto y el audio."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from decimal import Decimal

import pytest

from app.cerebro.extractor import (
    ExtractorNoDisponible,
    construir_hechos,
    interpretar,
)
from app.cerebro.sobre import validar_sobre
from app.voz import normalizar_con_mapa


TEXTO = (
    "Jorge Bailon cedula 1710034065 quiere 25 m3 de FC-210 en la Joya "
    "y ya me dio 1000 de abono en efectivo"
)


def _sobre() -> dict:
    return {
        "intencion": "MUTACION",
        "hechos": [
            {
                "clave": "cliente.nombre",
                "valor": "Jorge Bailon",
                "tipo": "TEXTO",
                "cita": "Jorge Bailon",
                "hablante": "SUPERADMIN",
            },
            {
                "clave": "cliente.cedula",
                "valor": "1710034065",
                "tipo": "CEDULA",
                "cita": "1710034065",
                "hablante": "CLIENTE",
            },
            {
                "clave": "cotizacion.volumen_m3",
                "valor": 25,
                "tipo": "ENTERO",
                "cita": "25",
                "hablante": "CLIENTE",
            },
            {
                "clave": "cotizacion.obra_direccion",
                "valor": "la Joya",
                "tipo": "TEXTO",
                "cita": "la Joya",
                "hablante": "CLIENTE",
            },
            {
                "clave": "cotizacion.resistencia",
                "valor": "FC-210",
                "tipo": "TEXTO",
                "cita": "FC-210",
                "hablante": "CLIENTE",
            },
            {
                "clave": "pago.monto",
                "valor": 1000,
                "tipo": "DECIMAL",
                "cita": "1000",
                "hablante": "SUPERADMIN",
            },
            {
                "clave": "pago.forma",
                "valor": "efectivo",
                "tipo": "TEXTO",
                "cita": "en efectivo",
                "hablante": "SUPERADMIN",
            },
        ],
        "faltantes": [],
        "ambiguedades": [],
        "preguntas": [],
    }


class _Respuesta:
    def __init__(self, contenido: str, status_code: int = 200) -> None:
        self.status_code = status_code
        self.text = contenido
        self._contenido = contenido

    def json(self):
        return {"choices": [{"message": {"content": self._contenido}}]}


class _Cliente:
    def __init__(self, contenido: str, status_code: int = 200) -> None:
        self.respuesta = _Respuesta(contenido, status_code)

    async def post(self, *args, **kwargs):
        return self.respuesta

    async def aclose(self) -> None:
        return None


class _Pool:
    async def fetchrow(self, sql, *args):
        if "concrete_recipes" in sql:
            return {
                "resistencia": "FC-210",
                "precio_m3": Decimal("118"),
                "precio_estado": "PROVISIONAL",
                "iva_pct": Decimal("15"),
            }
        return None

    async def fetch(self, sql, *args):
        return []


def test_interpretar_texto_produce_borrador_y_hechos(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "clave-de-prueba")
    cliente = _Cliente(json.dumps(_sobre()))

    resultado = asyncio.run(
        interpretar(
            _Pool(),
            texto_crudo=TEXTO,
            sandbox=True,
            hoy=date(2026, 11, 14),
            http_client=cliente,
        )
    )

    borrador = resultado["borrador"]
    assert borrador.estado == "PENDIENTE_CONFIRMACION", [
        p.clave for p in borrador.preguntas
    ]
    assert [a.nombre for a in borrador.acciones] == [
        "crear_cliente",
        "crear_cotizacion_borrador",
        "registrar_abono_cliente",
    ]
    cedula = next(h for h in resultado["hechos"] if h.clave == "cliente.cedula")
    assert cedula.valor == "1710034065"
    assert cedula.checksum_valido is True
    assert cedula.evidencia is not None


def test_cita_inventada_se_descarta(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "clave-de-prueba")
    sobre = _sobre()
    sobre["hechos"][1]["cita"] = "9999999999"
    cliente = _Cliente(json.dumps(sobre))

    resultado = asyncio.run(
        interpretar(
            _Pool(),
            texto_crudo=TEXTO,
            sandbox=True,
            hoy=date(2026, 11, 14),
            http_client=cliente,
        )
    )

    claves = {h.clave for h in resultado["hechos"]}
    assert "cliente.cedula" not in claves
    assert any("no esta en el texto" in nota for nota in resultado["notas"])


def test_json_invalido_agota_reintento(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "clave-de-prueba")
    cliente = _Cliente("esto no es json")

    with pytest.raises(ExtractorNoDisponible):
        asyncio.run(
            interpretar(
                _Pool(),
                texto_crudo=TEXTO,
                sandbox=True,
                hoy=date(2026, 11, 14),
                http_client=cliente,
            )
        )


def test_sin_clave_no_llama_al_llm(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ExtractorNoDisponible):
        asyncio.run(
            interpretar(
                _Pool(),
                texto_crudo=TEXTO,
                sandbox=True,
                hoy=date(2026, 11, 14),
                http_client=_Cliente(json.dumps(_sobre())),
            )
        )


def test_construir_hechos_rechaza_cita_ausente() -> None:
    mapa = normalizar_con_mapa(TEXTO)
    sobre = validar_sobre(
        {
            "intencion": "MUTACION",
            "hechos": [
                {
                    "clave": "cliente.nombre",
                    "valor": "Otra Persona",
                    "tipo": "TEXTO",
                    "cita": "Otra Persona",
                    "hablante": "CLIENTE",
                }
            ],
        }
    )
    hechos, notas = construir_hechos(
        sobre, texto_crudo=TEXTO, mapa=mapa, palabras=[]
    )
    assert hechos == []
    assert notas


def test_cita_dicha_como_se_escucho_se_normaliza_antes_de_descartar() -> None:
    """«mil dólares» se normaliza a «1000 USD»: la cita del LLM debe sobrevivir."""
    texto = "Jorge Bailon quiere 25 m3 y ya me dio mil dolares de abono"
    mapa = normalizar_con_mapa(texto)
    sobre = validar_sobre(
        {
            "intencion": "MUTACION",
            "hechos": [
                {
                    "clave": "pago.monto",
                    "valor": 1000,
                    "tipo": "DECIMAL",
                    "cita": "mil dolares de abono",
                    "hablante": "SUPERADMIN",
                }
            ],
        }
    )

    hechos, notas = construir_hechos(
        sobre, texto_crudo=texto, mapa=mapa, palabras=[]
    )

    assert notas == []
    assert [h.clave for h in hechos] == ["pago.monto"]
    assert hechos[0].valor == 1000
    assert "1000" in (hechos[0].evidencia.sostiene or "")


# ---------------------------------------------------------------------------
# Caso Joaquín: teléfono en grupos y hora sin fecha
# ---------------------------------------------------------------------------
def test_telefono_citado_sin_espacios_se_encuentra_en_el_audio() -> None:
    texto = "Hay que enviarle el recibo al 0965 555 555"
    mapa = normalizar_con_mapa(texto)
    sobre = validar_sobre(
        {
            "intencion": "MUTACION",
            "hechos": [
                {
                    "clave": "cliente.telefono",
                    "valor": "0965555555",
                    "tipo": "TELEFONO",
                    "cita": "0965555555",
                    "hablante": "SUPERADMIN",
                }
            ],
        }
    )

    hechos, notas = construir_hechos(
        sobre, texto_crudo=texto, mapa=mapa, palabras=[]
    )

    (telefono,) = hechos
    assert telefono.valor == "0965555555"
    assert telefono.estado == "EXTRAIDO"
    assert "0965 555 555" in (telefono.evidencia.cita or "")
    assert notas == []


def test_telefono_no_captado_por_el_llm_se_infiere_y_hay_que_confirmarlo() -> None:
    texto = "Hay que enviarle el recibo al 0965 555 555"
    mapa = normalizar_con_mapa(texto)
    sobre = validar_sobre({"intencion": "MUTACION", "hechos": []})

    hechos, notas = construir_hechos(
        sobre, texto_crudo=texto, mapa=mapa, palabras=[]
    )

    (telefono,) = hechos
    assert telefono.clave == "cliente.telefono"
    assert telefono.valor == "0965555555"
    assert telefono.estado == "INFERIDO"
    assert telefono.tipo == "TELEFONO"
    assert any("confirmarlo" in nota for nota in notas)


def test_fecha_de_entrega_sostenida_solo_por_una_hora_se_rechaza() -> None:
    texto = "Va a empezar la fundición a las 6 de la mañana"
    mapa = normalizar_con_mapa(texto)
    sobre = validar_sobre(
        {
            "intencion": "MUTACION",
            "hechos": [
                {
                    "clave": "cotizacion.fecha_entrega",
                    "valor": "2026-11-15",
                    "tipo": "FECHA",
                    "cita": "a las 6 de la mañana",
                    "hablante": "SUPERADMIN",
                }
            ],
        }
    )

    hechos, notas = construir_hechos(
        sobre, texto_crudo=texto, mapa=mapa, palabras=[]
    )

    claves = {h.clave: h for h in hechos}
    assert "cotizacion.fecha_entrega" not in claves
    assert claves["cotizacion.hora_entrega"].valor == "06:00"
    assert claves["cotizacion.hora_entrega"].tipo == "HORA"
    assert any("no se usa como fecha" in nota for nota in notas)


def test_fecha_con_dia_y_mes_se_conserva() -> None:
    texto = "La entrega es el 21 de noviembre"
    mapa = normalizar_con_mapa(texto)
    sobre = validar_sobre(
        {
            "intencion": "MUTACION",
            "hechos": [
                {
                    "clave": "cotizacion.fecha_entrega",
                    "valor": "2026-11-21",
                    "tipo": "FECHA",
                    "cita": "el 21 de noviembre",
                    "hablante": "SUPERADMIN",
                }
            ],
        }
    )

    hechos, notas = construir_hechos(
        sobre, texto_crudo=texto, mapa=mapa, palabras=[]
    )

    assert [h.clave for h in hechos] == ["cotizacion.fecha_entrega"]
    assert hechos[0].valor == "2026-11-21"
    assert notas == []


class _PoolConflicto(_Pool):
    async def fetchrow(self, sql, *args):
        if "clients" in sql:
            return {"id": "cli-palo", "nombre": "Palo Velez"}
        return await super().fetchrow(sql, *args)


def test_telefono_registrado_a_otro_nombre_pregunta_antes_de_resolver(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "clave-de-prueba")
    texto = "Estoy cotizando para el señor Joaquín Olmedo. Hay que enviarle al 0965 555 555"
    sobre = {
        "intencion": "MUTACION",
        "hechos": [
            {
                "clave": "cliente.nombre",
                "valor": "Joaquín Olmedo",
                "tipo": "TEXTO",
                "cita": "Joaquín Olmedo",
                "hablante": "SUPERADMIN",
            },
            {
                "clave": "cliente.telefono",
                "valor": "0965555555",
                "tipo": "TELEFONO",
                "cita": "0965555555",
                "hablante": "SUPERADMIN",
            },
        ],
    }

    resultado = asyncio.run(
        interpretar(
            _PoolConflicto(),
            texto_crudo=texto,
            sandbox=True,
            hoy=date(2026, 11, 14),
            http_client=_Cliente(json.dumps(sobre)),
        )
    )

    assert resultado["cliente"] is None
    pregunta = resultado["borrador"].preguntas[0]
    assert pregunta.clave == "cliente.identidad"
    assert "Palo Velez" in pregunta.texto
    assert "Joaquín Olmedo" in pregunta.texto
    assert pregunta.opciones == ("Sí, es el mismo", "No, crear cliente nuevo")
