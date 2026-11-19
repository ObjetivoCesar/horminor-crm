"""Ciclo de vida de las conversaciones de Gato.

La conversación es la dueña del hilo; los turnos viven en ``gato_turnos``. Una
sola conversación abierta por actor. El refresh cierra y abre en una
transacción corta; el trabajo pesado (STT/LLM) ocurre fuera.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg

ESTADO_LIBRE = '{"estado":"LIBRE"}'


class ConversacionNoEncontrada(LookupError):
    pass


class ConversacionCerrada(RuntimeError):
    pass


def _uuid_o_none(valor: str | None) -> str | None:
    try:
        return str(uuid.UUID(str(valor)))
    except (ValueError, TypeError):
        return None


def _recorte(texto: Any, limite: int = 120) -> str | None:
    limpio = " ".join(str(texto or "").split())
    if not limpio:
        return None
    return limpio if len(limpio) <= limite else limpio[:limite].rstrip() + "…"


def _fila(row: asyncpg.Record | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


async def _crear(
    pool: asyncpg.Pool,
    *,
    actor_id: str,
    rol_actor: str,
    perfil_id: str | None,
) -> dict[str, Any]:
    fila = await pool.fetchrow(
        """
        INSERT INTO gato_conversaciones (
            actor_id, perfil_id, rol_actor, estado_dialogo_json
        ) VALUES ($1, $2::uuid, $3, $4::jsonb)
        RETURNING id::text AS id, actor_id, perfil_id::text AS perfil_id,
                  rol_actor, abierta_en, cerrada_en, ultimo_turno_en,
                  titulo, resumen, estado_dialogo_json, lock_version
        """,
        actor_id,
        perfil_id,
        rol_actor,
        ESTADO_LIBRE,
    )
    return dict(fila)


async def actual(
    pool: asyncpg.Pool,
    *,
    actor_id: str,
    rol_actor: str,
    perfil_id: str | None = None,
) -> dict[str, Any]:
    """Última conversación del actor; si no existe, crea una."""
    fila = await pool.fetchrow(
        """
        SELECT id::text AS id, actor_id, perfil_id::text AS perfil_id,
               rol_actor, abierta_en, cerrada_en, ultimo_turno_en,
               titulo, resumen, estado_dialogo_json, lock_version
          FROM gato_conversaciones
         WHERE actor_id = $1
         ORDER BY (cerrada_en IS NULL) DESC, ultimo_turno_en DESC
         LIMIT 1
        """,
        actor_id,
    )
    if fila is not None:
        return dict(fila)
    return await _crear(
        pool,
        actor_id=actor_id,
        rol_actor=rol_actor,
        perfil_id=perfil_id or _uuid_o_none(actor_id),
    )


async def asegurar_abierta(
    pool: asyncpg.Pool, *, conversacion_id: str, actor_id: str
) -> dict[str, Any]:
    fila = await pool.fetchrow(
        """
        SELECT id::text AS id, actor_id, perfil_id::text AS perfil_id,
               rol_actor, abierta_en, cerrada_en, ultimo_turno_en,
               titulo, resumen, estado_dialogo_json, lock_version
          FROM gato_conversaciones
         WHERE id = $1::uuid AND actor_id = $2
        """,
        conversacion_id,
        actor_id,
    )
    if fila is None:
        raise ConversacionNoEncontrada("conversacion no encontrada")
    datos = dict(fila)
    if datos.get("cerrada_en") is not None:
        raise ConversacionCerrada("la conversacion esta cerrada")
    return datos


async def cerrar_y_abrir(
    pool: asyncpg.Pool,
    *,
    actor_id: str,
    rol_actor: str,
    perfil_id: str | None = None,
) -> dict[str, Any]:
    """Cierra la abierta del actor y crea una nueva, en una transacción."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            abierta = await conn.fetchrow(
                """
                SELECT id::text AS id
                  FROM gato_conversaciones
                 WHERE actor_id = $1 AND cerrada_en IS NULL
                 FOR UPDATE
                """,
                actor_id,
            )
            if abierta is not None:
                primera = await conn.fetchval(
                    """
                    SELECT pregunta FROM gato_turnos
                     WHERE conversacion_id = $1::uuid
                     ORDER BY created_at ASC LIMIT 1
                    """,
                    abierta["id"],
                )
                ultima = await conn.fetchval(
                    """
                    SELECT respuesta FROM gato_turnos
                     WHERE conversacion_id = $1::uuid
                     ORDER BY created_at DESC LIMIT 1
                    """,
                    abierta["id"],
                )
                await conn.execute(
                    """
                    UPDATE gato_conversaciones
                       SET cerrada_en = now(),
                           titulo = COALESCE(titulo, $2),
                           resumen = COALESCE(resumen, $3),
                           estado_dialogo_json = $4::jsonb,
                           lock_version = lock_version + 1
                     WHERE id = $1::uuid
                    """,
                    abierta["id"],
                    _recorte(primera),
                    _recorte(ultima, 300),
                    ESTADO_LIBRE,
                )
            fila = await conn.fetchrow(
                """
                INSERT INTO gato_conversaciones (
                    actor_id, perfil_id, rol_actor, estado_dialogo_json
                ) VALUES ($1, $2::uuid, $3, $4::jsonb)
                RETURNING id::text AS id, actor_id, perfil_id::text AS perfil_id,
                          rol_actor, abierta_en, cerrada_en, ultimo_turno_en,
                          titulo, resumen, estado_dialogo_json, lock_version
                """,
                actor_id,
                perfil_id or _uuid_o_none(actor_id),
                rol_actor,
                ESTADO_LIBRE,
            )
            return dict(fila)


async def turnos(pool: asyncpg.Pool, conversacion_id: str) -> list[dict[str, Any]]:
    filas = await pool.fetch(
        """
        SELECT id::text AS id, pregunta, respuesta, estado, created_at
          FROM gato_turnos
         WHERE conversacion_id = $1::uuid
         ORDER BY created_at ASC
        """,
        conversacion_id,
    )
    return [dict(fila) for fila in filas]


async def tocar(pool: asyncpg.Pool, conversacion_id: str) -> None:
    await pool.execute(
        """
        UPDATE gato_conversaciones
           SET ultimo_turno_en = now()
         WHERE id = $1::uuid
        """,
        conversacion_id,
    )


async def turno_por_client_id(
    pool: asyncpg.Pool, *, conversacion_id: str, client_turn_id: str
) -> dict[str, Any] | None:
    fila = await pool.fetchrow(
        """
        SELECT id::text AS id, pregunta, respuesta, estado, created_at
          FROM gato_turnos
         WHERE conversacion_id = $1::uuid AND client_turn_id = $2
        """,
        conversacion_id,
        client_turn_id,
    )
    return _fila(fila)


async def texto_ultimo_borrador(
    pool: asyncpg.Pool, conversacion_id: str
) -> str | None:
    """Texto completo del último borrador de la conversación.

    Se usa como contexto cuando el borrador anterior quedó esperando una
    aclaración. No es el último mensaje suelto: es el texto acumulado que el
    Cerebro ya compiló.
    """
    fila = await pool.fetchrow(
        """
        SELECT e.texto_directo
          FROM cerebro_borradores b
          JOIN cerebro_extracciones e ON e.id = b.extraccion_id
         WHERE b.conversacion_id = $1::uuid
         ORDER BY b.creado_en DESC
         LIMIT 1
        """,
        conversacion_id,
    )
    if fila is None or not fila["texto_directo"]:
        return None
    return str(fila["texto_directo"])


async def actualizar_estado(
    pool: asyncpg.Pool,
    conversacion_id: str,
    *,
    estado: str,
    borrador_id: str | None = None,
    preguntas: Any = None,
) -> None:
    payload: dict[str, Any] = {"estado": estado}
    if borrador_id:
        payload["borrador_id"] = borrador_id
    if preguntas:
        payload["preguntas"] = preguntas
    await pool.execute(
        """
        UPDATE gato_conversaciones
           SET estado_dialogo_json = $2::jsonb,
               lock_version = lock_version + 1
         WHERE id = $1::uuid
        """,
        conversacion_id,
        json.dumps(payload, ensure_ascii=False),
    )


__all__ = [
    "ConversacionCerrada",
    "ConversacionNoEncontrada",
    "actual",
    "actualizar_estado",
    "asegurar_abierta",
    "cerrar_y_abrir",
    "texto_ultimo_borrador",
    "tocar",
    "turno_por_client_id",
    "turnos",
]
