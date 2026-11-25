"""Puente de Gato con las otras agendas: mixers y tareas internas.

La cita comercial vive en ``comercial_bridge``. Aqui se resuelve lo que el
calendario muestra en las pestanas **Mixers** y **Equipo**, con las mismas
reglas que el panel: no se agenda en el pasado, no se inventan datos y una
accion sin cliente o sin direccion se pregunta, no se completa sola.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg

from .. import tiempo
from ..agenda import (
    PostgresAgendaStore,
    conflicto_mixer,
    normalizar_parametros,
    validar_ventana,
)
from ..agenda.service import ReservaMixerInvalida, reservar_mixers
from ..cerebro import internas as tareas_svc
from ..comercial import leads as leads_svc
from ..comercial.intencion import _fecha_dicha, _horas_dichas, parse_cita
from ..services.clients import crear_cliente

ZONA = ZoneInfo("America/Guayaquil")
_RE_VERBO = re.compile(
    r"\b(agenda|agendar|programa|programar|contrata|contratar|contrato|"
    r"reserva|reservar|despacha|despachar|coordina|coordinar|mueve|mover|"
    r"cambia|cambiar|cancela|cancelar)\b",
    re.IGNORECASE,
)
_RE_MIXER = re.compile(
    r"\b(mixer|fundicion|despacho|hormigon|m3|metros?\s+cubicos?)\b",
    re.IGNORECASE,
)
_RE_VOLUMEN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:m3|m³|metros?\s+c[uú]bicos?)", re.IGNORECASE
)
_RE_RECETA = re.compile(r"\bfc[-\s]?(\d{3})\b|\bhormigon\s+de\s+(\d{3})\b", re.I)
_RE_TELEFONO = re.compile(r"(?:\+?593|0)?\s*9\d{2}\s*\d{3}\s*\d{3}")
_RE_DIRECCION = re.compile(
    r"\ben\s+(.+?)(?=\s+(?:a\s+las|para|con|el|la)\b|,|$)", re.IGNORECASE
)


def _plano(texto: str) -> str:
    return leads_svc.normalizar(texto)


def _telefono(texto: str) -> str | None:
    m = _RE_TELEFONO.search(texto)
    if not m:
        return None
    digitos = re.sub(r"\D", "", m.group(0))
    if digitos.startswith("593"):
        return digitos
    if digitos.startswith("0"):
        return "593" + digitos[1:]
    return "593" + digitos


def _nombre(texto: str) -> str | None:
    t = _plano(texto)
    patrones = (
        r"cliente(?:\s+nuevo)?(?:\s+se\s+llama|\s+es|:)?\s+"
        r"([a-z]+(?:\s+[a-z]+){1,3})",
        r"\bpara\s+([a-z]+(?:\s+[a-z]+){0,3})",
    )
    for patron in patrones:
        for m in re.finditer(patron, t):
            candidato = m.group(1)
            candidato = re.split(
                r"\b(?:telefono|celular|con|en|para|a)\b",
                candidato,
                maxsplit=1,
            )[0].strip()
            if not candidato or re.search(r"\d", candidato):
                continue
            if any(
                re.search(rf"\b{palabra}\b", candidato)
                for palabra in (
                    "manana",
                    "hoy",
                    "lunes",
                    "martes",
                    "miercoles",
                    "jueves",
                    "viernes",
                    "sabado",
                    "domingo",
                    "el",
                    "la",
                    "las",
                    "los",
                    "mixer",
                    "fundicion",
                )
            ):
                continue
            if len(candidato) >= 2:
                return candidato.strip()
    return None


def _direccion(texto: str) -> str | None:
    m = _RE_DIRECCION.search(texto)
    if not m:
        return None
    valor = " ".join(m.group(1).split()).strip(" .,")
    if not valor or _plano(valor) in ("manana", "hoy", "el sitio", "la obra"):
        return valor or None
    return valor


def _error_texto(error: Any) -> str:
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(error)


def _ya_paso(fecha: Any, hora: str) -> bool:
    ahora = tiempo.ahora()
    return str(fecha)[:10] == ahora.date().isoformat() and hora <= ahora.strftime("%H:%M")


def es_peticion_mixer(texto: str) -> bool:
    t = _plano(texto)
    if not _RE_MIXER.search(t) or not _RE_VERBO.search(t):
        return False
    return bool(_fecha_dicha(texto, tiempo.hoy()) or _horas_dichas(t))


def es_correccion_mixer(texto: str) -> bool:
    t = _plano(texto)
    if not _RE_MIXER.search(t):
        return False
    return bool(
        re.search(r"\b(mueve|mover|muevelo|cambia|cambiar|reagenda|reprograma)\b", t)
    ) and bool(_horas_dichas(t) or _fecha_dicha(texto, tiempo.hoy()))


def es_cancelacion_mixer(texto: str) -> bool:
    t = _plano(texto)
    return bool(
        _RE_MIXER.search(t)
        and re.search(r"\b(cancela|cancelar|anula|anular)\b", t)
    )


async def _cliente(
    pool: asyncpg.Pool, texto: str
) -> tuple[dict[str, Any] | None, str | None]:
    telefono = _telefono(texto)
    nombre = _nombre(texto)
    if telefono:
        fila = await pool.fetchrow(
            """
            SELECT id::text AS id, nombre, telefono_whatsapp
              FROM clients
             WHERE regexp_replace(coalesce(telefono_whatsapp, ''), '\\D', '', 'g')
                   LIKE '%' || right($1, 9)
             LIMIT 1
            """,
            telefono,
        )
        if fila is not None:
            return dict(fila), telefono
    if nombre:
        fila = await pool.fetchrow(
            """
            SELECT id::text AS id, nombre, telefono_whatsapp
              FROM clients
             WHERE nombre ILIKE $1
             ORDER BY created_at DESC
             LIMIT 1
            """,
            nombre,
        )
        if fila is not None:
            return dict(fila), telefono
    if "cliente nuevo" in _plano(texto) and nombre and telefono:
        try:
            creado = await crear_cliente(
                pool,
                nombre=nombre.title(),
                telefono_whatsapp=telefono,
                notas="Alta desde Gato al agendar un mixer.",
            )
        except Exception:
            creado = None
        if creado:
            return creado, telefono
    return None, telefono


async def _parametros(pool: asyncpg.Pool) -> dict[str, Any]:
    valor = await pool.fetchval(
        "SELECT value FROM system_settings WHERE key = 'agenda.parametros'"
    )
    return normalizar_parametros(valor)


async def crear(
    pool: asyncpg.Pool,
    texto: str,
    *,
    actor: str | None = None,
    actor_id: str | None = None,
    rol: str | None = None,
) -> dict[str, Any]:
    datos = parse_cita(texto)
    volumen = _RE_VOLUMEN.search(texto)
    if datos["fecha"] is None or datos["hora"] is None:
        return {
            "estado": "FALTA",
            "mensaje": (
                "Para agendar el mixer necesito la fecha y la hora. "
                "Ejemplo: «agenda el mixer para mañana a las 14:00»."
            ),
        }
    if volumen is None:
        return {
            "estado": "FALTA",
            "mensaje": "¿Cuántos metros cúbicos lleva el mixer?",
        }
    direccion = _direccion(texto)
    if not direccion:
        return {
            "estado": "FALTA",
            "mensaje": "Vuelve a indicar la reserva del mixer con la dirección o referencia de la obra.",
        }
    cliente, telefono = await _cliente(pool, texto)
    if cliente is None:
        quien = _nombre(texto) or telefono or "el cliente"
        return {
            "estado": "FALTA",
            "mensaje": (
                f"No encontré a {quien} en el CRM. Dime el nombre exacto o "
                "créalo con «crea el cliente …» y vuelvo a agendar el mixer."
            ),
        }

    m3 = float(volumen.group(1).replace(",", "."))
    receta = _RE_RECETA.search(_plano(texto))
    receta_codigo = (
        f"FC-{receta.group(1) or receta.group(2)}" if receta else None
    )
    try:
        filas = await reservar_mixers(pool, {
            "cliente_id": cliente["id"],
            "receta_codigo": receta_codigo,
            "volumen_m3": m3,
            "fecha_entrega": datos["fecha"].isoformat(),
            "hora_inicio": datos["hora"],
            "direccion_obra": direccion,
            "contacto_obra_telefono": telefono or cliente.get("telefono_whatsapp"),
            "creado_por_rol": (rol or "SECRETARIA").upper(),
            "creado_por_id": actor_id or actor or "gato",
            "notas": "Creado desde Gato.",
        })
    except ReservaMixerInvalida as exc:
        return {"estado": "FALTA", "mensaje": str(exc)}
    fila = filas[0]
    etiqueta = cliente.get("nombre") or cliente.get("telefono_whatsapp")
    return {
        "estado": "OK",
        "mensaje": (
            f"Mixer agendado para {etiqueta} el {datos['fecha'].isoformat()} "
            f"a las {datos['hora']}: {m3:g} m3"
            + (f" {receta_codigo}" if receta_codigo else "")
            + f" en {direccion}. Unidades: {', '.join(item['mixer_codigo'] for item in filas)}."
        ),
        "agenda": fila,
    }


async def _ultimo_mixer(
    pool: asyncpg.Pool, *, actor_id: str | None, actor: str | None
) -> dict[str, Any] | None:
    fila = await pool.fetchrow(
        """
        SELECT id::text AS id
          FROM dispatch_schedule
         WHERE deleted_at IS NULL
           AND estado NOT IN ('CANCELADO', 'COMPLETADO', 'REAGENDADO')
           AND (
                ($1::text IS NOT NULL AND creado_por_id = $1)
                OR ($2::text IS NOT NULL
                    AND (creado_por_id = $2 OR creado_por_id = 'gato'))
                OR ($1::text IS NULL AND $2::text IS NULL)
           )
         ORDER BY created_at DESC
         LIMIT 1
        """,
        actor_id,
        actor,
    )
    if fila is None:
        return None
    return await PostgresAgendaStore(pool).obtener(str(fila["id"]))


async def reagendar_ultimo(
    pool: asyncpg.Pool,
    texto: str,
    *,
    actor: str | None = None,
    actor_id: str | None = None,
) -> dict[str, Any]:
    actual = await _ultimo_mixer(pool, actor_id=actor_id, actor=actor)
    if actual is None:
        return {
            "estado": "SIN_MIXER",
            "mensaje": "No tengo un mixer reciente para mover.",
        }
    cambios = parse_cita(texto)
    nueva_fecha = cambios["fecha"] or date.fromisoformat(
        str(actual["fecha_entrega"])[:10]
    )
    nueva_hora = cambios["hora"] or actual["hora_inicio"]
    if cambios["fecha"] is None and cambios["hora"] is None:
        return {
            "estado": "FALTA",
            "mensaje": "¿A qué fecha u hora muevo el mixer?",
        }
    params = await _parametros(pool)
    duracion = actual.get("duracion_estimada_min") or params[
        "duracion_entrega_default_min"
    ]
    error = validar_ventana(
        parametros=params,
        fecha=nueva_fecha,
        hora=nueva_hora,
        duracion_min=int(duracion),
    )
    if error:
        return {"estado": "FALTA", "mensaje": _error_texto(error)}
    if _ya_paso(nueva_fecha, nueva_hora):
        return {
            "estado": "FALTA",
            "mensaje": "Esa hora ya pasó; dime una hora futura para el mixer.",
        }
    fila = await PostgresAgendaStore(pool).actualizar(
        str(actual["id"]),
        {
            "fecha_entrega": nueva_fecha.isoformat(),
            "hora_inicio": nueva_hora,
            "motivo_reagendamiento": " ".join(texto.split())[:300],
        },
    )
    return {
        "estado": "OK",
        "mensaje": (
            f"Mixer movido a {nueva_fecha.isoformat()} a las {nueva_hora} "
            f"(antes {actual['fecha_entrega']} {actual['hora_inicio']})."
        ),
        "agenda": fila,
    }


async def cancelar_ultimo(
    pool: asyncpg.Pool,
    texto: str,
    *,
    actor: str | None = None,
    actor_id: str | None = None,
) -> dict[str, Any]:
    actual = await _ultimo_mixer(pool, actor_id=actor_id, actor=actor)
    if actual is None:
        return {
            "estado": "SIN_MIXER",
            "mensaje": "No tengo un mixer reciente para cancelar.",
        }
    ok = await PostgresAgendaStore(pool).cancelar(str(actual["id"]))
    if not ok:
        return {"estado": "ERROR", "mensaje": "No pude cancelar el mixer."}
    return {
        "estado": "OK",
        "mensaje": (
            f"Mixer cancelado: {actual['fecha_entrega']} "
            f"{actual['hora_inicio']} ({actual['cliente']})."
        ),
    }


# ---------------------------------------------------------------------------
# Tareas internas (pestana Equipo)
# ---------------------------------------------------------------------------
def es_correccion_tarea(texto: str) -> bool:
    t = _plano(texto)
    if "tarea" not in t:
        return False
    if not re.search(r"\b(mueve|mover|cambia|cambiar|reprograma|plazo)\b", t):
        return False
    return bool(_fecha_dicha(texto, tiempo.hoy()) or _horas_dichas(t))


def es_cancelacion_tarea(texto: str) -> bool:
    t = _plano(texto)
    return bool(
        "tarea" in t
        and re.search(r"\b(cancela|cancelar|anula|anular|ya\s+no)\b", t)
    )


async def _ultima_tarea(
    pool: asyncpg.Pool, *, actor: str | None
) -> dict[str, Any] | None:
    fila = await pool.fetchrow(
        """
        SELECT id::text AS id, instruccion, asignado_rol, asignado_a,
               estado, plazo_en, notificada_en
          FROM cerebro_tareas_internas
         WHERE estado = 'NOTIFICADA'
           AND ($1::text IS NULL OR creado_por = $1)
         ORDER BY creado_en DESC
         LIMIT 1
        """,
        actor,
    )
    return dict(fila) if fila is not None else None


async def reprogramar_tarea(
    pool: asyncpg.Pool,
    texto: str,
    *,
    actor: str | None = None,
    actor_id: str | None = None,
    rol: str | None = None,
) -> dict[str, Any]:
    tarea = await _ultima_tarea(pool, actor=actor)
    if tarea is None:
        return {
            "estado": "SIN_TAREA",
            "mensaje": "No tengo una tarea interna abierta para mover.",
        }
    datos = parse_cita(texto)
    if datos["fecha"] is None or datos["hora"] is None:
        return {
            "estado": "FALTA",
            "mensaje": "¿Para qué fecha y hora muevo la tarea?",
        }
    plazo = datetime.combine(datos["fecha"], time.fromisoformat(datos["hora"]))
    plazo = plazo.replace(tzinfo=ZONA)
    ahora = datetime.now(ZONA)
    if plazo <= ahora:
        if re.search(
            r"\b(lunes|martes|miercoles|jueves|viernes|sabado|domingo)\b",
            _plano(texto),
        ):
            plazo = plazo + timedelta(days=7)
        else:
            return {
                "estado": "FALTA",
                "mensaje": "Esa hora ya pasó; dime una hora futura para la tarea.",
            }
    fila = await tareas_svc.reprogramar(
        pool,
        str(tarea["id"]),
        plazo_en=plazo,
        actor_id=actor_id,
        actor_nombre=actor or "Gato",
        rol_actor=(rol or "SUPERADMIN").upper(),
        nota=" ".join(texto.split())[:500],
    )
    return {
        "estado": "OK",
        "mensaje": (
            f"Tarea movida para {datos['fecha'].isoformat()} a las "
            f"{datos['hora']} ({fila['asignado_rol']})."
        ),
        "tarea": fila,
    }


async def cancelar_tarea(
    pool: asyncpg.Pool,
    texto: str,
    *,
    actor: str | None = None,
    actor_id: str | None = None,
    rol: str | None = None,
) -> dict[str, Any]:
    tarea = await _ultima_tarea(pool, actor=actor)
    if tarea is None:
        return {
            "estado": "SIN_TAREA",
            "mensaje": "No tengo una tarea interna abierta para cancelar.",
        }
    await tareas_svc.resolver(
        pool,
        str(tarea["id"]),
        resolucion="JUSTIFICADA",
        nota="Cancelada desde Gato: " + " ".join(texto.split())[:400],
        actor_id=actor_id,
        actor_nombre=actor or "Gato",
        rol_actor=(rol or "SUPERADMIN").upper(),
        metadatos={"origen": "GATO", "motivo": " ".join(texto.split())[:400]},
    )
    return {
        "estado": "OK",
        "mensaje": (
            f"Tarea cancelada ({tarea['asignado_rol']}): "
            f"{tarea['instruccion'][:90]}."
        ),
    }
