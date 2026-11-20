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


def es_agenda_personal(texto: str) -> bool:
    """«Registra en mi agenda»: compromiso de Julio, no cita comercial."""
    t = leads_svc.normalizar(texto)
    return any(
        marca in t
        for marca in (
            "mi agenda",
            "agenda personal",
            "agendame",
            "para mi agenda",
            "en mi agenda",
        )
    )


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
    # «Registra en mi agenda» es un compromiso de Julio, no una cita comercial
    # atada a un lead. Se permite sin contacto y se guarda el dictado tal cual.
    personal = es_agenda_personal(texto)
    faltan = []
    if datos["fecha"] is None:
        faltan.append("el dia (hoy, manana o pasado manana)")
    if datos["hora"] is None:
        faltan.append("la hora (por ejemplo a las 10:30)")
    if not datos["nombre"] and not personal:
        faltan.append("a quien (nombre del lead)")
    if faltan:
        return {
            "estado": "FALTA",
            "mensaje": "Para agendar necesito " + ", ".join(faltan) + ".",
        }

    lead = None
    if datos["nombre"]:
        lead = await leads_svc.buscar(pool, str(datos["nombre"]))
        if lead is None and not personal:
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
        lead_id=str(lead["id"]) if lead else None,
        solicitada_por=actor,
        notas=(
            "Agenda de Julio desde Gato: " + " ".join(str(texto).split())
            if personal
            else "Solicitada por Gato desde el chat interno."
        ),
        permite_sin_contacto=personal,
    )
    nombre = (lead or {}).get("nombre") or (lead or {}).get("telefono_e164")
    if personal and not nombre:
        nombre = "Agenda de Julio"
    return {
        "estado": "OK",
        "mensaje": (
            f"Agende una {str(datos['tipo']).lower()} para {nombre} el "
            f"{datos['fecha'].isoformat()} a las {datos['hora']} "
            f"(cita {cita['id']}, SOLICITADA)."
            + (" Confirmala en Secretaria." if lead else " Queda en tu agenda.")
        ),
        "cita": cita,
    }
