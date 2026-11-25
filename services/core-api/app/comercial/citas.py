"""Citas: componente independiente (panel, Gato o Miau).

La entrega de hormigon sigue en ``dispatch_schedule``; aqui viven las citas
comerciales (visita, reunion, medicion).
"""

from __future__ import annotations

from datetime import date, time
from typing import Any

import asyncpg

from ..agenda.seguimiento import notificar_secretaria
from ..transacciones import transaccion

from .. import tiempo

TIPOS = ("VISITA", "REUNION", "MEDICION", "ENTREGA")
ORIGENES = ("PANEL", "WHATSAPP", "GATO", "MIAU")

# Maquina de estados: no se confirma una cita cancelada ni se cancela una
# realizada. REAGENDADA vuelve a solicitar confirmacion.
TRANSICIONES = {
    "SOLICITADA": ("CONFIRMADA", "CANCELADA", "REAGENDADA"),
    "CONFIRMADA": ("REALIZADA", "CANCELADA", "REAGENDADA"),
    "REAGENDADA": ("CONFIRMADA", "CANCELADA"),
    "REALIZADA": (),
    "CANCELADA": (),
}


def _hora(valor: str) -> time:
    partes = str(valor or "").strip().split(":")
    if len(partes) < 2:
        raise ValueError("hora_inicio debe tener formato HH:MM")
    hh, mm = int(partes[0]), int(partes[1])
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError("hora_inicio fuera de rango")
    return time(hh, mm)


def _minutos(hora: time) -> int:
    return hora.hour * 60 + hora.minute


def validar(*, tipo: str, fecha: date, origen: str, duracion_min: int) -> None:
    if tipo not in TIPOS:
        raise ValueError(f"tipo de cita invalido: {tipo}")
    if origen not in ORIGENES:
        raise ValueError(f"origen de cita invalido: {origen}")
    if fecha < tiempo.hoy():
        raise ValueError("no se agenda una cita en el pasado")
    if duracion_min < 15 or duracion_min > 480:
        raise ValueError("la duracion debe estar entre 15 y 480 minutos")


async def _evento(
    pool: asyncpg.Pool,
    cita_id: str,
    tipo: str,
    detalle: dict[str, Any] | None = None,
    actor: str | None = None,
) -> None:
    import json

    await pool.execute(
        """
        INSERT INTO cita_eventos (cita_id, tipo, detalle, actor)
        VALUES ($1::uuid, $2, $3::jsonb, $4)
        """,
        cita_id,
        tipo,
        json.dumps(detalle or {}, ensure_ascii=False),
        actor,
    )


async def _choque(
    pool: asyncpg.Pool,
    *,
    fecha: date,
    hora: time,
    duracion_min: int,
    lead_id: str | None,
    cliente_id: str | None,
    excluir_id: str | None = None,
    global_: bool = False,
) -> dict[str, Any] | None:
    """Cita que se solapa.

    Una cita comercial solo choca con las del mismo lead o cliente. Un
    compromiso personal de Julio choca con cualquier cita de ese día: su
    agenda es una sola. ``excluir_id`` evita que una reprogramación choque
    consigo misma.
    """
    if global_:
        filas = await pool.fetch(
            """
            SELECT id::text AS id, hora_inicio, duracion_min
              FROM citas
             WHERE fecha = $1
               AND estado <> 'CANCELADA'
               AND ($2::uuid IS NULL OR id <> $2::uuid)
            """,
            fecha,
            excluir_id,
        )
    else:
        filas = await pool.fetch(
            """
            SELECT id::text AS id, hora_inicio, duracion_min
              FROM citas
             WHERE fecha = $1
               AND estado <> 'CANCELADA'
               AND ($4::uuid IS NULL OR id <> $4::uuid)
               AND (($2::uuid IS NOT NULL AND lead_id = $2::uuid)
                    OR ($3::uuid IS NOT NULL AND cliente_id = $3::uuid))
            """,
            fecha,
            lead_id,
            cliente_id,
            excluir_id,
        )
    inicio = _minutos(hora)
    fin = inicio + duracion_min
    for fila in filas:
        otro_inicio = _minutos(fila["hora_inicio"])
        otro_fin = otro_inicio + int(fila["duracion_min"])
        if inicio < otro_fin and fin > otro_inicio:
            return dict(fila)
    return None


async def crear(
    pool: asyncpg.Pool,
    *,
    tipo: str,
    fecha: date,
    hora_inicio: str,
    origen: str,
    duracion_min: int = 60,
    cliente_id: str | None = None,
    lead_id: str | None = None,
    solicitada_por: str | None = None,
    solicitada_por_id: str | None = None,
    notas: str | None = None,
    permite_sin_contacto: bool = False,
    contacto_agenda: str | None = None,
    clave_gato: str | None = None,
    rol_actor: str | None = None,
) -> dict[str, Any]:
    if not cliente_id and not lead_id and not permite_sin_contacto:
        raise ValueError("la cita necesita cliente_id o lead_id")
    validar(tipo=tipo, fecha=fecha, origen=origen, duracion_min=duracion_min)
    hora = _hora(hora_inicio)
    ahora = tiempo.ahora()
    if fecha == ahora.date():
        minutos_nuevos = hora.hour * 60 + hora.minute
        if minutos_nuevos < ahora.hour * 60 + ahora.minute:
            raise ValueError("la hora ya pasó hoy; elige una hora futura")

    async with transaccion(pool) as conn:
        # Dos solicitudes simultáneas de la misma fecha no pueden pasar
        # ambas la revisión de choque.
        await conn.fetchval(
            "SELECT pg_advisory_xact_lock(hashtext($1))",
            f"citas:{fecha.isoformat()}",
        )
        if clave_gato:
            existente = await conn.fetchrow(
                "SELECT *, id::text AS id FROM citas WHERE clave_gato = $1", clave_gato
            )
            if existente:
                return dict(existente)
        estado_inicial = "CONFIRMADA" if clave_gato else "SOLICITADA"
        choque = await _choque(
            conn,
            fecha=fecha,
            hora=hora,
            duracion_min=duracion_min,
            lead_id=lead_id,
            cliente_id=cliente_id,
            global_=permite_sin_contacto,
        )
        if choque is not None:
            raise ValueError(
                "ya hay una cita que se solapa a esa hora "
                f"(cita {choque['id']}, {choque['hora_inicio']})"
            )
        fila = await conn.fetchrow(
            """
            INSERT INTO citas (
                cliente_id, lead_id, tipo, fecha, hora_inicio, duracion_min,
                origen, solicitada_por, solicitada_por_id, notas,
                estado, contacto_agenda, clave_gato
            ) VALUES ($1, $2, $3, $4, $5::time, $6, $7, $8, $9::uuid, $10, $11, $12, $13)
            RETURNING id::text AS id, cliente_id::text, lead_id::text, tipo,
                      fecha, hora_inicio, duracion_min, estado, origen,
                      solicitada_por, solicitada_por_id::text, notas,
                      created_at
            """,
            cliente_id,
            lead_id,
            tipo,
            fecha,
            hora,
            duracion_min,
            origen,
            solicitada_por,
            solicitada_por_id,
            notas,
            estado_inicial,
            contacto_agenda,
            clave_gato,
        )
        datos = dict(fila)
        await _evento(
            conn,
            datos["id"],
            estado_inicial,
            {"origen": origen},
            solicitada_por,
        )
        if clave_gato:
            await notificar_secretaria(
                conn, tipo="julio", entidad_id=datos["id"], fecha=fecha.isoformat(),
                hora=hora.strftime("%H:%M"), referencia=contacto_agenda,
                actor_id=solicitada_por_id, actor=solicitada_por or "Gato",
                rol=rol_actor or "SUPERADMIN",
            )
    return datos


async def obtener(pool: asyncpg.Pool, cita_id: str) -> dict[str, Any] | None:
    fila = await pool.fetchrow(
        """
        SELECT id::text AS id, cliente_id::text, lead_id::text, tipo,
               fecha, hora_inicio, duracion_min, estado, origen,
               solicitada_por, solicitada_por_id::text, notas,
               created_at, updated_at
          FROM citas WHERE id = $1::uuid
        """,
        cita_id,
    )
    return dict(fila) if fila is not None else None


async def reagendar(
    pool: asyncpg.Pool,
    *,
    cita_id: str,
    fecha: date | None = None,
    hora_inicio: str | None = None,
    duracion_min: int | None = None,
    motivo: str | None = None,
    actor: str | None = None,
    mantener_confirmada: bool = False,
) -> dict[str, Any]:
    """Mueve una cita existente. Solo cambia lo que se pide.

    Mantiene la regla de no agendar en el pasado y de no solapar. Si la cita es
    personal (sin lead ni cliente), el choque se revisa contra toda la agenda de
    Julio; si es comercial, solo contra el mismo lead o cliente.
    """
    actual = await obtener(pool, cita_id)
    if actual is None:
        raise LookupError("cita no encontrada")
    if actual["estado"] in ("CANCELADA", "REALIZADA"):
        raise ValueError(
            f"no se mueve una cita {str(actual['estado']).lower()}"
        )

    nueva_fecha = fecha or actual["fecha"]
    nueva_hora = _hora(hora_inicio) if hora_inicio else actual["hora_inicio"]
    nueva_duracion = int(duracion_min or actual["duracion_min"])
    if nueva_fecha < tiempo.hoy():
        raise ValueError("no se agenda una cita en el pasado")
    ahora = tiempo.ahora()
    if nueva_fecha == ahora.date():
        minutos_nuevos = nueva_hora.hour * 60 + nueva_hora.minute
        if minutos_nuevos < ahora.hour * 60 + ahora.minute:
            raise ValueError("la hora ya pasó hoy; elige una hora futura")

    personal = not actual["lead_id"] and not actual["cliente_id"]
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.fetchval(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                f"citas:{nueva_fecha.isoformat()}",
            )
            choque = await _choque(
                conn,
                fecha=nueva_fecha,
                hora=nueva_hora,
                duracion_min=nueva_duracion,
                lead_id=actual["lead_id"],
                cliente_id=actual["cliente_id"],
                excluir_id=cita_id,
                global_=personal,
            )
            if choque is not None:
                raise ValueError(
                    "ya hay una cita que se solapa a esa hora "
                    f"(cita {choque['id']}, {choque['hora_inicio']})"
                )

            nuevo_estado = "CONFIRMADA" if mantener_confirmada else "REAGENDADA"
            fila = await conn.fetchrow(
                """
                UPDATE citas
                   SET fecha = $2, hora_inicio = $3::time, duracion_min = $4,
                       estado = $5, updated_at = now()
                 WHERE id = $1::uuid AND estado NOT IN ('CANCELADA', 'REALIZADA')
                RETURNING id::text AS id, cliente_id::text, lead_id::text, tipo,
                          fecha, hora_inicio, duracion_min, estado, origen,
                          solicitada_por, solicitada_por_id::text, notas,
                          created_at, updated_at
                """,
                cita_id,
                nueva_fecha,
                nueva_hora,
                nueva_duracion,
                nuevo_estado,
            )
            if fila is None:
                raise ValueError("La cita cambió mientras se revisaba. Consulta su estado.")
            datos = dict(fila)
            await _evento(
                conn,
                cita_id,
                "REAGENDADA",
                {
                    "antes": {
                        "fecha": actual["fecha"].isoformat(),
                        "hora": actual["hora_inicio"].strftime("%H:%M"),
                    },
                    "despues": {
                        "fecha": nueva_fecha.isoformat(),
                        "hora": nueva_hora.strftime("%H:%M"),
                    },
                    "motivo": motivo,
                },
                actor,
            )
    return datos


async def listar(
    pool: asyncpg.Pool, *, fecha: date | None = None, desde: date | None = None
) -> list[dict[str, Any]]:
    if fecha is not None:
        filas = await pool.fetch(
            """
            SELECT id::text AS id, cliente_id::text, lead_id::text, tipo,
                   fecha, hora_inicio, duracion_min, estado, origen,
                   solicitada_por, notas
              FROM citas WHERE fecha = $1
             ORDER BY hora_inicio
            """,
            fecha,
        )
    else:
        desde = desde or tiempo.hoy()
        filas = await pool.fetch(
            """
            SELECT id::text AS id, cliente_id::text, lead_id::text, tipo,
                   fecha, hora_inicio, duracion_min, estado, origen,
                   solicitada_por, notas
              FROM citas WHERE fecha >= $1
             ORDER BY fecha, hora_inicio
            """,
            desde,
        )
    return [dict(fila) for fila in filas]


async def cambiar_estado(
    pool: asyncpg.Pool,
    *,
    cita_id: str,
    nuevo: str,
    motivo: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    if nuevo not in ("CONFIRMADA", "CANCELADA", "REALIZADA", "REAGENDADA"):
        raise ValueError("estado de cita invalido")
    actual = await pool.fetchrow(
        "SELECT id::text AS id, estado FROM citas WHERE id = $1::uuid", cita_id
    )
    if actual is None:
        raise LookupError("cita no encontrada")
    anterior = str(actual["estado"])
    if nuevo not in TRANSICIONES.get(anterior, ()):
        raise ValueError(f"no se puede pasar de {anterior} a {nuevo}")
    fila = await pool.fetchrow(
        """
        UPDATE citas SET estado = $2, updated_at = now()
         WHERE id = $1::uuid
        RETURNING id::text AS id, estado, fecha, hora_inicio
        """,
        cita_id,
        nuevo,
    )
    if fila is None:
        raise LookupError("cita no encontrada")
    await _evento(
        pool,
        cita_id,
        nuevo,
        {"estado_anterior": anterior, "motivo": motivo},
        actor,
    )
    return dict(fila)


async def disponibilidad(pool: asyncpg.Pool, *, fecha: date) -> dict[str, Any]:
    citas = await listar(pool, fecha=fecha)
    fila = await pool.fetchrow(
        """
        SELECT
          (SELECT value FROM system_settings WHERE key = 'agenda.citas_horario_inicio') AS inicio,
          (SELECT value FROM system_settings WHERE key = 'agenda.citas_horario_fin') AS fin,
          (SELECT value FROM system_settings WHERE key = 'agenda.citas_duracion_min') AS duracion
        """
    )
    return {
        "fecha": fecha.isoformat(),
        "zona": "America/Guayaquil",
        "citas": citas,
        "horario": {
            "inicio": (dict(fila) if fila else {}).get("inicio"),
            "fin": (dict(fila) if fila else {}).get("fin"),
            "duracion_min": (dict(fila) if fila else {}).get("duracion"),
        },
        "horario_configurado": bool(
            fila and dict(fila).get("inicio") and dict(fila).get("fin")
        ),
    }
