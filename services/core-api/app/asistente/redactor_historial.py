"""Redactor del historial: estado determinístico de un asunto para el razonador.

NO usa LLM. Consulta las tablas que ya existen y devuelve una estructura
que el razonador puede leer sin inventar nada:

  - cotizaciones del asunto
  - citas comerciales vinculadas
  - recordatorios de Gato
  - tareas internas
  - avisos de dinero abiertos
  - hechos confirmados en client_facts

El contrato con el razonador es simple: si el campo existe y no es None,
el sistema lo sabe con evidencia. Si es None, no lo sabe todavía.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import asyncpg

_LOG = logging.getLogger(__name__)


@dataclass
class AsuntoRegistros:
    """Vista compacta del estado de un asunto para el razonador."""

    asunto_id: str
    # Identificadores que el razonador puede usar en la siguiente acción
    cotizacion_id: str | None = None
    cotizacion_numero: str | None = None
    cotizacion_estado: str | None = None
    cotizacion_precio_estado: str | None = None
    cotizacion_enviada: bool = False
    cotizacion_envio_pendiente: bool = False
    cotizacion_envio_programado_at: str | None = None
    cotizacion_cliente_nombre: str | None = None
    cotizacion_cliente_telefono: str | None = None
    # Citas comerciales
    cita_id: str | None = None
    cita_fecha: str | None = None
    cita_hora: str | None = None
    cita_estado: str | None = None
    # Recordatorios de Gato
    recordatorio_id: str | None = None
    recordatorio_estado: str | None = None
    recordatorio_programado_at: str | None = None
    recordatorio_mensaje: str | None = None
    # Avisos de dinero abiertos
    aviso_dinero_id: str | None = None
    aviso_dinero_monto: str | None = None
    aviso_dinero_estado: str | None = None
    # Hechos confirmados más recientes (máx. 5)
    hechos_confirmados: list[str] = field(default_factory=list)


async def contexto_para_razonador(
    pool: asyncpg.Pool,
    actor_id: str,
    asunto_id: str,
    *,
    borrador_id: str | None = None,
    cliente_id: str | None = None,
) -> AsuntoRegistros:
    """Consulta el estado real de un asunto desde base de datos.

    Nunca inventa ni infiere: si el dato no está en base de datos, el campo es None.
    """
    reg = AsuntoRegistros(asunto_id=asunto_id)

    async with pool.acquire() as conn:
        # 1. Cotización más reciente del asunto (vía borrador o clave_gato)
        if borrador_id:
            cot = await conn.fetchrow(
                """
                SELECT c.id::text, c.numero, c.estado, c.precio_estado,
                       cl.nombre AS cliente_nombre, cl.telefono AS cliente_telefono
                  FROM cotizaciones c
                  LEFT JOIN clientes cl ON cl.id = c.cliente_id
                 WHERE c.borrador_id = $1::text
                 ORDER BY c.creada_en DESC
                 LIMIT 1
                """,
                borrador_id,
            )
            if cot:
                reg.cotizacion_id = cot["id"]
                reg.cotizacion_numero = str(cot["numero"] or "")
                reg.cotizacion_estado = cot["estado"]
                reg.cotizacion_precio_estado = cot["precio_estado"]
                reg.cotizacion_cliente_nombre = cot["cliente_nombre"]
                reg.cotizacion_cliente_telefono = cot["cliente_telefono"]

        # 2. Estado de envío de la cotización
        if reg.cotizacion_id:
            reg.cotizacion_enviada = reg.cotizacion_estado == "ENVIADA"
            rec_envio = await conn.fetchrow(
                """
                SELECT id::text, estado, programado_at, cotizacion_version
                  FROM gato_recordatorios
                 WHERE cotizacion_id = $1::uuid
                   AND estado IN ('BORRADOR', 'PENDIENTE', 'AGENDADO')
                 ORDER BY creado_en DESC
                 LIMIT 1
                """,
                reg.cotizacion_id,
            )
            if rec_envio:
                reg.cotizacion_envio_pendiente = True
                if rec_envio["programado_at"]:
                    reg.cotizacion_envio_programado_at = rec_envio["programado_at"].isoformat()

        # 3. Cita comercial vinculada al asunto
        cita = await conn.fetchrow(
            """
            SELECT id::text, fecha::text, hora_inicio::text, estado
              FROM citas_comerciales
             WHERE clave_gato = $1
             ORDER BY creada_en DESC
             LIMIT 1
            """,
            asunto_id,
        )
        if cita:
            reg.cita_id = cita["id"]
            reg.cita_fecha = cita["fecha"]
            reg.cita_hora = cita["hora_inicio"]
            reg.cita_estado = cita["estado"]

        # 4. Recordatorio personal de Gato
        recordatorio = await conn.fetchrow(
            """
            SELECT id::text, estado, programado_at,
                   (metadatos->>'mensaje')::text AS mensaje
              FROM gato_recordatorios
             WHERE asunto_id = $1
               AND cotizacion_id IS NULL
               AND creado_por = $2
               AND estado NOT IN ('ENVIADO', 'CANCELADO')
             ORDER BY creado_en DESC
             LIMIT 1
            """,
            asunto_id,
            actor_id,
        )
        if recordatorio:
            reg.recordatorio_id = recordatorio["id"]
            reg.recordatorio_estado = recordatorio["estado"]
            reg.recordatorio_mensaje = recordatorio["mensaje"]
            if recordatorio["programado_at"]:
                reg.recordatorio_programado_at = recordatorio["programado_at"].isoformat()

        # 5. Aviso de dinero abierto (para Secretaría)
        if cliente_id:
            aviso = await conn.fetchrow(
                """
                SELECT id::text, estado,
                       (ficha_json->>'monto_usd')::text AS monto
                  FROM cerebro_tareas_internas
                 WHERE tipo = 'aviso_dinero'
                   AND estado NOT IN ('CERRADA', 'CANCELADA')
                   AND (ficha_json->>'cliente_id')::text = $1
                 ORDER BY creada_en DESC
                 LIMIT 1
                """,
                cliente_id,
            )
            if aviso:
                reg.aviso_dinero_id = aviso["id"]
                reg.aviso_dinero_estado = aviso["estado"]
                reg.aviso_dinero_monto = aviso["monto"]

        # 6. Hechos confirmados recientes del cliente
        if cliente_id:
            hechos = await conn.fetch(
                """
                SELECT hecho_texto
                  FROM client_facts
                 WHERE cliente_id = $1::uuid
                 ORDER BY creado_en DESC
                 LIMIT 5
                """,
                cliente_id,
            )
            reg.hechos_confirmados = [str(h["hecho_texto"]) for h in hechos]

    return reg


def ficha_de_asunto(reg: AsuntoRegistros) -> dict[str, Any]:
    """Dict compacto con el estado del asunto, sin valores None, para el prompt."""
    datos: dict[str, Any] = {}
    if reg.cotizacion_id:
        datos["cotizacion"] = {
            "id": reg.cotizacion_id,
            "numero": reg.cotizacion_numero,
            "estado": reg.cotizacion_estado,
            "precio_estado": reg.cotizacion_precio_estado,
            "enviada": reg.cotizacion_enviada,
            "envio_pendiente": reg.cotizacion_envio_pendiente,
            "envio_programado_at": reg.cotizacion_envio_programado_at,
            "cliente": reg.cotizacion_cliente_nombre,
            "telefono_cliente": reg.cotizacion_cliente_telefono,
        }
    if reg.cita_id:
        datos["cita"] = {
            "id": reg.cita_id,
            "fecha": reg.cita_fecha,
            "hora": reg.cita_hora,
            "estado": reg.cita_estado,
        }
    if reg.recordatorio_id:
        datos["recordatorio"] = {
            "id": reg.recordatorio_id,
            "estado": reg.recordatorio_estado,
            "programado_at": reg.recordatorio_programado_at,
            "mensaje": reg.recordatorio_mensaje,
        }
    if reg.aviso_dinero_id:
        datos["aviso_dinero"] = {
            "id": reg.aviso_dinero_id,
            "monto": reg.aviso_dinero_monto,
            "estado": reg.aviso_dinero_estado,
        }
    if reg.hechos_confirmados:
        datos["hechos"] = reg.hechos_confirmados
    return datos


def nota_de_contexto(reg: AsuntoRegistros) -> str:
    """Una frase que informa al LLM qué está resuelto.

    Regla: sin verbos de acción, sin montos inventados.
    Solo describe el estado tal como está en base de datos.
    """
    partes: list[str] = []
    if reg.cotizacion_enviada:
        partes.append(f"La cotización #{reg.cotizacion_numero} ya fue enviada.")
    elif reg.cotizacion_envio_pendiente and reg.cotizacion_envio_programado_at:
        partes.append(
            f"El envío de la cotización #{reg.cotizacion_numero} "
            f"está programado para {reg.cotizacion_envio_programado_at[:16]}."
        )
    elif reg.cotizacion_id and not reg.cotizacion_enviada:
        partes.append(f"Hay una cotización #{reg.cotizacion_numero} ({reg.cotizacion_estado}) sin enviar.")
    if reg.cita_id:
        partes.append(f"Visita el {reg.cita_fecha} a las {reg.cita_hora} ({reg.cita_estado}).")
    if reg.recordatorio_id and reg.recordatorio_programado_at:
        partes.append(f"Recordatorio agendado para {reg.recordatorio_programado_at[:16]}.")
    if reg.aviso_dinero_id:
        partes.append(f"Aviso de pago ({reg.aviso_dinero_monto} USD) pendiente para Secretaría.")
    return " ".join(partes)
