"""Puente Gato -> modulo comercial (leads y citas).

Gato no implementa reglas: solo pide al modulo comercial. La fecha sale de
``app/tiempo`` (America/Guayaquil), nunca del navegador.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, time
from typing import Any

import asyncpg

from .. import tiempo
from ..comercial import citas as citas_svc
from ..comercial import leads as leads_svc
from ..comercial.intencion import (
    _fecha_dicha,
    _horas_dichas,
    es_cancelacion_cita,
    es_correccion_cita,
    es_peticion_cita,
    parse_cita,
    parse_correccion,
)


def _uuid_o_none(valor: str | None) -> str | None:
    try:
        return str(uuid.UUID(str(valor)))
    except (ValueError, TypeError, AttributeError):
        return None


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


async def ultima_cita(
    pool: asyncpg.Pool,
    *,
    cita_id: str | None = None,
    actor: str | None = None,
    actor_id: str | None = None,
) -> dict[str, Any] | None:
    """La cita que se acaba de crear: la del hilo o la última del mismo actor."""
    if cita_id:
        return await citas_svc.obtener(pool, cita_id)
    fila = await pool.fetchrow(
        """
        SELECT id::text AS id
          FROM citas
         WHERE origen = 'GATO'
           AND estado IN ('SOLICITADA', 'CONFIRMADA', 'REAGENDADA')
           AND created_at > now() - interval '12 hours'
           AND (
                ($1::uuid IS NOT NULL AND solicitada_por_id = $1::uuid)
                OR ($1::uuid IS NULL
                    AND ($2::text IS NULL OR solicitada_por = $2))
           )
         ORDER BY created_at DESC
         LIMIT 1
        """,
        _uuid_o_none(actor_id),
        actor,
    )
    return await citas_svc.obtener(pool, str(fila["id"])) if fila else None


async def _citas_que_coinciden(
    pool: asyncpg.Pool,
    texto: str,
    *,
    actor: str | None,
    actor_id: str | None,
) -> list[dict[str, Any]]:
    """Citas activas que coinciden con la fecha u hora dichas en el texto."""
    fecha = _fecha_dicha(texto, tiempo.hoy())
    horas = _horas_dichas(texto)
    if fecha is None and not horas:
        return []
    filas = await pool.fetch(
        """
        SELECT id::text AS id
          FROM citas
         WHERE estado IN ('SOLICITADA', 'CONFIRMADA', 'REAGENDADA')
           AND ($1::date IS NULL OR fecha = $1)
           AND ($2::time IS NULL OR hora_inicio = $2::time)
           AND (
                ($3::uuid IS NOT NULL AND solicitada_por_id = $3::uuid)
                OR ($3::uuid IS NULL
                    AND ($4::text IS NULL OR solicitada_por = $4))
           )
         ORDER BY fecha, hora_inicio
         LIMIT 5
        """,
        fecha,
        time.fromisoformat(horas[-1]) if horas else None,
        _uuid_o_none(actor_id),
        actor,
    )
    return [await citas_svc.obtener(pool, str(f["id"])) for f in filas]


async def _citas_en_fecha(
    pool: asyncpg.Pool,
    fecha: date,
    *,
    actor: str | None,
    actor_id: str | None,
) -> list[dict[str, Any]]:
    filas = await pool.fetch(
        """
        SELECT id::text AS id
          FROM citas
         WHERE estado IN ('SOLICITADA', 'CONFIRMADA', 'REAGENDADA')
           AND fecha = $1
           AND (
                ($2::uuid IS NOT NULL AND solicitada_por_id = $2::uuid)
                OR ($2::uuid IS NULL
                    AND ($3::text IS NULL OR solicitada_por = $3))
           )
         ORDER BY hora_inicio
         LIMIT 5
        """,
        fecha,
        _uuid_o_none(actor_id),
        actor,
    )
    return [await citas_svc.obtener(pool, str(f["id"])) for f in filas]


async def _citas_en_hora(
    pool: asyncpg.Pool,
    hora: time,
    *,
    actor: str | None,
    actor_id: str | None,
) -> list[dict[str, Any]]:
    filas = await pool.fetch(
        """
        SELECT id::text AS id
          FROM citas
         WHERE estado IN ('SOLICITADA', 'CONFIRMADA', 'REAGENDADA')
           AND hora_inicio = $1::time
           AND (
                ($2::uuid IS NOT NULL AND solicitada_por_id = $2::uuid)
                OR ($2::uuid IS NULL
                    AND ($3::text IS NULL OR solicitada_por = $3))
           )
         ORDER BY fecha
         LIMIT 5
        """,
        hora,
        _uuid_o_none(actor_id),
        actor,
    )
    return [await citas_svc.obtener(pool, str(f["id"])) for f in filas]


async def reagendar_ultima(
    pool: asyncpg.Pool,
    texto: str,
    *,
    cita_id: str | None = None,
    actor: str | None = None,
    actor_id: str | None = None,
) -> dict[str, Any]:
    objetivo = None
    # «Rectifico la cita de mañana»: el día nombrado elige la cita; si hay
    # varias ese día, se pregunta en vez de mover la última a ciegas.
    marca = re.search(r"\b(?:la|esa)\s+cita\s+(?:de|del|para)\s+(.+)", texto, re.I)
    if marca:
        fecha_objetivo = _fecha_dicha(marca.group(1), tiempo.hoy())
        if fecha_objetivo is not None:
            candidatas = await _citas_en_fecha(
                pool, fecha_objetivo, actor=actor, actor_id=actor_id
            )
            if not candidatas:
                return {
                    "estado": "SIN_CITA",
                    "mensaje": (
                        "No hay una cita activa ese día. Dime la fecha y la "
                        "hora exactas de la que quieres mover."
                    ),
                }
            if len(candidatas) > 1:
                detalle = "; ".join(
                    f"{c['hora_inicio'].strftime('%H:%M')} ({c['tipo'].lower()})"
                    for c in candidatas
                )
                return {
                    "estado": "FALTA",
                    "mensaje": (
                        f"Ese día hay {len(candidatas)} citas: {detalle}. "
                        "Dime la hora de la que quieres corregir; por ejemplo: "
                        "«mueve la cita de las 13:00 a las 16:00»."
                    ),
                }
            objetivo = candidatas[0]
    if objetivo is None and _fecha_dicha(texto, tiempo.hoy()) is None:
        # «Mueve la cita de las 13:00 a las 16:00»: la primera hora elige,
        # la última es el nuevo valor.
        marca_hora = re.search(
            r"\b(?:la|esa)\s+cita\s+(?:de\s+)?(?:a\s+)?las?\s+"
            r"(\d{1,2})(?::(\d{2}))?",
            texto,
            re.I,
        )
        if marca_hora:
            hh = int(marca_hora.group(1))
            mm = int(marca_hora.group(2) or 0)
            if 0 <= hh <= 23 and 0 <= mm <= 59:
                candidatas = await _citas_en_hora(
                    pool,
                    time(hh, mm),
                    actor=actor,
                    actor_id=actor_id,
                )
                if not candidatas:
                    return {
                        "estado": "SIN_CITA",
                        "mensaje": (
                            "No hay una cita activa a esa hora. No moví nada."
                        ),
                    }
                if len(candidatas) > 1:
                    detalle = "; ".join(
                        f"{c['fecha'].isoformat()} "
                        f"({c['tipo'].lower()})"
                        for c in candidatas
                    )
                    return {
                        "estado": "FALTA",
                        "mensaje": (
                            f"Hay {len(candidatas)} citas a esa hora: {detalle}. "
                            "Dime también la fecha."
                        ),
                    }
                objetivo = candidatas[0]
    cita = objetivo or await ultima_cita(
        pool, cita_id=cita_id, actor=actor, actor_id=actor_id
    )
    if cita is None:
        return {
            "estado": "SIN_CITA",
            "mensaje": (
                "No tengo una cita reciente para corregir. Dime cuál o "
                "vuelve a dictarla completa."
            ),
        }
    if str(cita["estado"]).upper() in ("CANCELADA", "REALIZADA"):
        return {
            "estado": "SIN_CITA",
            "limpiar_ultima": True,
            "mensaje": (
                "Esa cita ya está cancelada. Si quieres, dicta una nueva "
                "con la fecha y la hora."
            ),
        }
    cambio = parse_correccion(
        texto,
        fecha_base=cita["fecha"],
        hora_base=cita["hora_inicio"].strftime("%H:%M"),
    )
    if not cambio["dijo_fecha"] and not cambio["dijo_hora"]:
        return {
            "estado": "FALTA",
            "mensaje": (
                "Entendí que quieres corregir la cita, pero no me dijiste la "
                "nueva hora o fecha. Por ejemplo: «mejor a las 14:00»."
            ),
        }
    try:
        nueva = await citas_svc.reagendar(
            pool,
            cita_id=str(cita["id"]),
            fecha=cambio["fecha"],
            hora_inicio=cambio["hora"],
            motivo=texto,
            actor=actor,
        )
    except ValueError as exc:
        return {"estado": "ERROR", "mensaje": f"No pude mover la cita: {exc}"}
    return {
        "estado": "OK",
        "mensaje": (
            "Cita corregida: "
            f"{nueva['fecha'].isoformat()} a las "
            f"{nueva['hora_inicio'].strftime('%H:%M')} "
            f"(antes {cita['fecha'].isoformat()} "
            f"{cita['hora_inicio'].strftime('%H:%M')}). "
            f"Cita {nueva['id']}."
        ),
        "cita": nueva,
    }


async def cancelar_ultima(
    pool: asyncpg.Pool,
    texto: str,
    *,
    cita_id: str | None = None,
    actor: str | None = None,
    actor_id: str | None = None,
) -> dict[str, Any]:
    coincidencias = await _citas_que_coinciden(
        pool, texto, actor=actor, actor_id=actor_id
    )
    nombra_fecha_u_hora = (
        _fecha_dicha(texto, tiempo.hoy()) is not None
        or bool(_horas_dichas(texto))
    )
    if len(coincidencias) > 1:
        detalle = "; ".join(
            f"{c['fecha'].isoformat()} {c['hora_inicio'].strftime('%H:%M')} "
            f"({c['tipo'].lower()})"
            for c in coincidencias
        )
        return {
            "estado": "FALTA",
            "mensaje": (
                f"Hay {len(coincidencias)} citas que coinciden: {detalle}. "
                "Dime la hora exacta o cancélala desde el panel."
            ),
        }
    if coincidencias:
        cita = coincidencias[0]
    elif nombra_fecha_u_hora:
        return {
            "estado": "SIN_CITA",
            "mensaje": (
                "No hay una cita activa que coincida con esa fecha u hora. "
                "No cancelé nada."
            ),
        }
    else:
        cita = await ultima_cita(
            pool, cita_id=cita_id, actor=actor, actor_id=actor_id
        )
    if cita is None:
        return {
            "estado": "SIN_CITA",
            "mensaje": (
                "No tengo una cita reciente para cancelar. Dime cuál o "
                "indícame la fecha y la hora."
            ),
        }
    if str(cita["estado"]).upper() == "CANCELADA":
        return {
            "estado": "OK",
            "limpiar_ultima": True,
            "mensaje": "Esa cita ya estaba cancelada.",
        }
    try:
        cancelada = await citas_svc.cambiar_estado(
            pool,
            cita_id=str(cita["id"]),
            nuevo="CANCELADA",
            motivo=texto,
            actor=actor,
        )
    except ValueError as exc:
        return {"estado": "ERROR", "mensaje": f"No pude cancelarla: {exc}"}
    return {
        "estado": "OK",
        "limpiar_ultima": True,
        "mensaje": (
            "Cita cancelada: "
            f"{cita['fecha'].isoformat()} a las "
            f"{cita['hora_inicio'].strftime('%H:%M')}. "
            f"Cita {cancelada['id']}."
        ),
        "cita": cancelada,
    }


async def agendar(
    pool: asyncpg.Pool,
    texto: str,
    *,
    actor: str | None = None,
    actor_id: str | None = None,
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
    if datos["nombre"] and not personal:
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
        lead_id=str(lead["id"]) if lead else None,
        solicitada_por=actor,
        solicitada_por_id=_uuid_o_none(actor_id),
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
