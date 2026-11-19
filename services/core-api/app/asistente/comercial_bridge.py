"""Puente Gato -> modulo comercial (leads y citas).

Gato no implementa reglas: solo pide al modulo comercial. La fecha sale de
``app/tiempo`` (America/Guayaquil), nunca del navegador.
"""

from __future__ import annotations

from typing import Any

import asyncpg

from ..comercial import citas as citas_svc
from ..comercial import leads as leads_svc
from ..comercial.intencion import es_peticion_cita, parse_cita


def es_leads_caidos(texto: str) -> bool:
    t = leads_svc.normalizar(texto)
    return "lead" in t and any(
        palabra in t for palabra in ("caido", "perdido", "sin respuesta")
    )


def es_agendar(texto: str) -> bool:
    return es_peticion_cita(texto)


async def listar_caidos(pool: asyncpg.Pool) -> str:
    filas = await leads_svc.listar(pool, estado="CAIDO")
    if not filas:
        return "No hay leads caidos ahora mismo."
    partes = []
    for fila in filas[:10]:
        detalle = fila.get("motivo_caida") or "sin motivo"
        partes.append(f"{fila.get('nombre') or fila.get('telefono_e164')} ({detalle})")
    return f"Hay {len(filas)} lead(s) caido(s): " + "; ".join(partes) + "."


async def agendar(
    pool: asyncpg.Pool, texto: str, *, actor: str | None = None
) -> dict[str, Any]:
    datos = parse_cita(texto)
    faltan = []
    if datos["fecha"] is None:
        faltan.append("el dia (hoy, manana o pasado manana)")
    if datos["hora"] is None:
        faltan.append("la hora (por ejemplo a las 10:30)")
    if not datos["nombre"]:
        faltan.append("a quien (nombre del lead)")
    if faltan:
        return {
            "estado": "FALTA",
            "mensaje": "Para agendar necesito " + ", ".join(faltan) + ".",
        }

    lead = await leads_svc.buscar(pool, str(datos["nombre"]))
    if lead is None:
        return {
            "estado": "SIN_LEAD",
            "mensaje": (
                f"No encontre un lead que coincida con '{datos['nombre']}'. "
                "Registralo primero en Secretaria y vuelvo a agendar."
            ),
        }

    cita = await citas_svc.crear(
        pool,
        tipo=str(datos["tipo"]),
        fecha=datos["fecha"],
        hora_inicio=str(datos["hora"]),
        origen="GATO",
        lead_id=str(lead["id"]),
        solicitada_por=actor,
        notas="Solicitada por Gato desde el chat interno.",
    )
    nombre = lead.get("nombre") or lead.get("telefono_e164")
    return {
        "estado": "OK",
        "mensaje": (
            f"Agende una {str(datos['tipo']).lower()} para {nombre} el "
            f"{datos['fecha'].isoformat()} a las {datos['hora']} "
            f"(cita {cita['id']}, SOLICITADA). Confirmala en Secretaria."
        ),
        "cita": cita,
    }
