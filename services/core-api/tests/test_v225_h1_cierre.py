"""H1: cierre del nucleo comercial (leads y citas).

Cubre los defectos detectados en la revision: origen elegido por el cliente,
respuesta de la empresa interpretada como intencion del lead, lead caido que
no revive, citas sin choque ni trazabilidad, y el enganche de WhatsApp.
"""

from __future__ import annotations

import sys
from collections import deque
from datetime import time, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app import tiempo  # noqa: E402
from app.comercial import citas, leads  # noqa: E402
from app.comercial.router import CitaIn, LeadIn  # noqa: E402


class _TxGuion:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _ConnGuion:
    """Conexión falsa que delega en el pool y simula la transacción."""

    def __init__(self, pool: "PoolGuion"):
        self._pool = pool

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def fetchrow(self, sql, *args):
        return await self._pool.fetchrow(sql, *args)

    async def fetch(self, sql, *args):
        return await self._pool.fetch(sql, *args)

    async def execute(self, sql, *args):
        return await self._pool.execute(sql, *args)

    async def fetchval(self, sql, *args):
        self._pool.consultas.append((sql, args))
        return None

    def transaction(self):
        return _TxGuion()


class PoolGuion:
    """Pool falso: devuelve respuestas en el orden en que se piden."""

    def __init__(self, fetchrows=None, fetchs=None):
        self._fetchrows = deque(fetchrows or [])
        self._fetchs = deque(fetchs or [])
        self.consultas: list[tuple[str, tuple]] = []

    def acquire(self) -> _ConnGuion:
        return _ConnGuion(self)

    async def fetchrow(self, sql, *args):
        self.consultas.append((sql, args))
        return self._fetchrows.popleft() if self._fetchrows else None

    async def fetch(self, sql, *args):
        self.consultas.append((sql, args))
        return self._fetchs.popleft() if self._fetchs else []

    async def execute(self, sql, *args):
        self.consultas.append((sql, args))
        return "INSERT 0 1"


def _eventos(pool: PoolGuion) -> list[tuple[str, tuple]]:
    return [c for c in pool.consultas if "INSERT INTO lead_eventos" in c[0]]


def _eventos_cita(pool: PoolGuion) -> list[tuple[str, tuple]]:
    return [c for c in pool.consultas if "INSERT INTO cita_eventos" in c[0]]


@pytest.mark.asyncio
async def test_lead_nuevo_nace_contacto_y_deja_evento() -> None:
    pool = PoolGuion(
        fetchrows=[
            None,
            {
                "id": "lead-1",
                "telefono_e164": "593990000000",
                "nombre": None,
                "origen": "PANEL",
                "estado": "CONTACTO",
                "motivo_caida": None,
                "recontactar_at": None,
                "intentos_recontacto": 0,
                "created_at": None,
                "updated_at": None,
            },
        ]
    )

    resultado = await leads.crear_o_reutilizar(
        pool, telefono_lead="+593 99 000 0000", origen="PANEL"
    )

    assert resultado["creado"] is True
    assert resultado["estado"] == "CONTACTO"
    assert _eventos(pool)[0][1][1] == "CREADO"


@pytest.mark.asyncio
async def test_reingreso_reutiliza_y_actualiza_ultimo_contacto() -> None:
    pool = PoolGuion(
        fetchrows=[
            {"id": "lead-1", "estado": "LEAD", "nombre": None},
            {"id": "lead-1", "estado": "LEAD", "nombre": "Paola"},
        ]
    )

    resultado = await leads.crear_o_reutilizar(
        pool, telefono_lead="0990000000", origen="WHATSAPP", nombre="Paola"
    )

    assert resultado["creado"] is False
    assert resultado["nombre"] == "Paola"
    assert _eventos(pool)[0][1][1] == "REINGRESO"
    actualizacion = [c for c in pool.consultas if "ultimo_contacto_at  = now()" in c[0]]
    assert actualizacion, "el reingreso debe actualizar ultimo_contacto_at"


@pytest.mark.asyncio
async def test_respuesta_de_la_empresa_no_marca_competencia() -> None:
    """«ya tengo listo su pedido» es una respuesta de la empresa, no del lead."""
    pool = PoolGuion(
        fetchrows=[
            {"id": "lead-1", "estado": "CONTACTO"},
            {"id": "lead-1", "estado": "LEAD", "motivo_caida": None, "recontactar_at": None},
        ]
    )

    resultado = await leads.registrar_respuesta(
        pool, lead_id="lead-1", texto="ya tengo listo su pedido"
    )

    assert resultado["estado"] == "LEAD"
    assert not any("lead_reglas_caida" in sql for sql, _ in pool.consultas)
    # El estado enviado al UPDATE es LEAD, nunca CAIDO.
    update = [args for sql, args in pool.consultas if "UPDATE leads" in sql][0]
    assert update[1] == "LEAD"


@pytest.mark.asyncio
async def test_mensaje_entrante_revive_un_lead_caido() -> None:
    pool = PoolGuion(
        fetchrows=[
            {"id": "lead-1", "estado": "CAIDO"},
            {"id": "lead-1", "estado": "LEAD", "motivo_caida": None, "recontactar_at": None},
        ],
        fetchs=[[]],
    )

    resultado = await leads.registrar_mensaje(
        pool, lead_id="lead-1", texto="hola, sigo interesado"
    )

    assert resultado["estado"] == "LEAD"
    assert _eventos(pool)[0][1][1] == "REACTIVADO"


@pytest.mark.asyncio
async def test_mensaje_entrante_con_rechazo_sigue_caido() -> None:
    pool = PoolGuion(
        fetchrows=[
            {"id": "lead-1", "estado": "LEAD"},
            {"id": "lead-1", "estado": "CAIDO", "motivo_caida": "NO_INTERESADO", "recontactar_at": None},
        ],
        fetchs=[
            [
                {
                    "clave": "RECHAZO",
                    "patrones": ["no me interesa"],
                    "estado_destino": "CAIDO",
                    "motivo": "NO_INTERESADO",
                    "gracia_dias": None,
                }
            ]
        ],
    )

    resultado = await leads.registrar_mensaje(
        pool, lead_id="lead-1", texto="no me interesa, gracias"
    )

    assert resultado["estado"] == "CAIDO"
    assert _eventos(pool)[0][1][1] == "INTENCION"


@pytest.mark.asyncio
async def test_un_contacto_no_es_lead_sin_respuesta_de_la_empresa() -> None:
    pool = PoolGuion(
        fetchrows=[
            {"id": "lead-1", "estado": "CONTACTO"},
            {"id": "lead-1", "estado": "CONTACTO", "motivo_caida": None, "recontactar_at": None},
        ],
        fetchs=[[]],
    )

    resultado = await leads.registrar_mensaje(pool, lead_id="lead-1", texto="hola")

    assert resultado["estado"] == "CONTACTO"


@pytest.mark.asyncio
async def test_lead_se_puede_revertir_a_mano() -> None:
    pool = PoolGuion(
        fetchrows=[
            {"id": "lead-1", "estado": "CAIDO"},
            {"id": "lead-1", "estado": "LEAD"},
        ]
    )

    resultado = await leads.cambiar_estado(
        pool, lead_id="lead-1", estado="LEAD", motivo="volvio a llamar", actor="secretaria"
    )

    assert resultado["estado"] == "LEAD"
    assert _eventos(pool)[0][1][1] == "ESTADO_CAMBIADO"


def test_origen_no_lo_elige_el_cliente() -> None:
    LeadIn(telefono="0990000000", nombre="Paola")
    with pytest.raises(ValidationError):
        LeadIn(telefono="0990000000", origen="WHATSAPP")

    manana = tiempo.hoy()
    CitaIn(tipo="VISITA", fecha=manana, hora_inicio="10:00", lead_id="l-1")
    with pytest.raises(ValidationError):
        CitaIn(
            tipo="VISITA",
            fecha=manana,
            hora_inicio="10:00",
            lead_id="l-1",
            origen="WHATSAPP",
        )


@pytest.mark.asyncio
async def test_cita_que_se_solapa_se_rechaza() -> None:
    pool = PoolGuion(
        fetchs=[[{"id": "cita-1", "hora_inicio": time(10, 0), "duracion_min": 60}]]
    )

    with pytest.raises(ValueError, match="se solapa"):
        await citas.crear(
            pool,
            tipo="VISITA",
            fecha=tiempo.hoy() + timedelta(days=1),
            hora_inicio="10:30",
            origen="PANEL",
            lead_id="lead-1",
        )


@pytest.mark.asyncio
async def test_cita_creada_deja_evento_solicitada() -> None:
    pool = PoolGuion(
        fetchs=[[]],
        fetchrows=[
            {
                "id": "cita-1",
                "tipo": "VISITA",
                "fecha": tiempo.hoy(),
                "hora_inicio": time(10, 0),
                "estado": "SOLICITADA",
                "origen": "PANEL",
            }
        ],
    )

    resultado = await citas.crear(
        pool,
        tipo="VISITA",
        fecha=tiempo.hoy() + timedelta(days=1),
        hora_inicio="10:00",
        origen="PANEL",
        lead_id="lead-1",
    )

    assert resultado["estado"] == "SOLICITADA"
    assert _eventos_cita(pool)[0][1][1] == "SOLICITADA"


@pytest.mark.asyncio
async def test_no_se_confirma_una_cita_cancelada() -> None:
    pool = PoolGuion(fetchrows=[{"id": "cita-1", "estado": "CANCELADA"}])

    with pytest.raises(ValueError, match="CANCELADA"):
        await citas.cambiar_estado(pool, cita_id="cita-1", nuevo="CONFIRMADA")


@pytest.mark.asyncio
async def test_cancelar_guarda_el_motivo() -> None:
    pool = PoolGuion(
        fetchrows=[
            {"id": "cita-1", "estado": "SOLICITADA"},
            {"id": "cita-1", "estado": "CANCELADA"},
        ]
    )

    await citas.cambiar_estado(
        pool, cita_id="cita-1", nuevo="CANCELADA", motivo="el cliente no asistio"
    )

    detalle = _eventos_cita(pool)[0][1][2]
    assert "el cliente no asistio" in detalle


class RepoFalso:
    def __init__(self):
        self.lead_creado = None

    async def crear_lead(self, *, telefono, nombre, mensaje):
        self.lead_creado = (telefono, nombre, mensaje)
        return {"id": "cliente-1"}

    async def parametro(self, clave, por_defecto):
        return por_defecto

    async def recetas_publicas(self):
        return []


class NotifierFalso:
    def __init__(self):
        self.mensajes: list[tuple[str, str]] = []

    async def enviar_texto(self, telefono, texto):
        self.mensajes.append((telefono, texto))
        return True


class AlerterFalso:
    async def alertar(self, **kwargs):
        return True


class VeredictoFalso:
    cumple = True

    def a_dict(self):
        return {"cumple": True}


class JuezFalso:
    async def evaluar(self, *, compuerta, texto, contexto=None):
        return VeredictoFalso()


class ComercialFalso:
    def __init__(self):
        self.entrantes: list[dict] = []
        self.respuestas: list[dict] = []
        self.citas: list[dict] = []

    async def entrante(self, **kwargs):
        self.entrantes.append(kwargs)
        return {"id": "lead-1", "creado": True}

    async def respuesta(self, **kwargs):
        self.respuestas.append(kwargs)
        return {"estado": "LEAD"}

    async def solicitar_cita(self, **kwargs):
        self.citas.append(kwargs)
        return {"id": "cita-1", "estado": "SOLICITADA"}


@pytest.mark.asyncio
async def test_whatsapp_pide_al_modulo_y_no_crea_por_su_cuenta() -> None:
    from app.m1_whatsapp.models import IncomingMessage, MessageBatch
    from app.m1_whatsapp.pipeline import ResultadoLote, WhatsAppPipeline

    comercial = ComercialFalso()
    notifier = NotifierFalso()
    repo = RepoFalso()
    pipeline = WhatsAppPipeline(
        repo=repo,
        identidad=None,
        juez=JuezFalso(),
        bunny=None,
        notifier=notifier,
        alerter=AlerterFalso(),
        comercial=comercial,
    )
    lote = MessageBatch(
        telefono="593990000000",
        mensajes=(
            IncomingMessage(
                mensaje_id="m-1",
                telefono="593990000000",
                texto="quiero agendar una visita a Paola manana a las 10:30",
                nombre_contacto="Paola",
            ),
        ),
    )
    resultado = ResultadoLote(telefono=lote.telefono, rol="LEAD_DESCONOCIDO", origen_identidad="telefono")

    await pipeline._gate_lead(lote, None, None, resultado)

    assert comercial.entrantes[0]["telefono"] == "593990000000"
    assert comercial.entrantes[0]["nombre"] == "Paola"
    assert comercial.citas and comercial.citas[0]["lead_id"] == "lead-1"
    assert comercial.respuestas and comercial.respuestas[0]["lead_id"] == "lead-1"
    assert notifier.mensajes, "el bot sigue respondiendo"
    assert "LEAD_COMERCIAL_CREADO" in resultado.acciones
    assert "CITA_SOLICITADA" in resultado.acciones
    assert "LEAD_COMERCIAL_RESPONDIDO" in resultado.acciones


@pytest.mark.asyncio
async def test_adaptador_whatsapp_sin_fecha_no_inventa_cita() -> None:
    from app.comercial.whatsapp import ComercialWhatsApp

    pool = PoolGuion()
    adaptador = ComercialWhatsApp(pool)

    assert await adaptador.solicitar_cita(lead_id="lead-1", texto="quiero agendar una visita") is None
    assert pool.consultas == [], "sin fecha ni hora no se toca la base"
