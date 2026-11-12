"""Memoria de Gato en PostgreSQL.

Cada turno se guarda en ``gato_turnos``. El historial se reconstruye por
``conversacion_id`` y se recorta a los últimos turnos para no inflar el prompt.
La conversación pertenece al actor que la inició; otro actor no puede leerla.
"""

from __future__ import annotations

import asyncpg

LIMITE_TURNOS = 8
MAX_TEXTO = 4000


async def cargar(
    pool: asyncpg.Pool,
    conversacion_id: str,
    actor_id: str,
    limite: int = LIMITE_TURNOS,
) -> list[dict[str, str]]:
    """Devuelve los turnos anteriores en formato de mensajes del LLM.

    Lanza ``PermissionError`` si la conversación es de otro actor.
    """
    filas = await pool.fetch(
        """
        SELECT actor_id, pregunta, respuesta
          FROM gato_turnos
         WHERE conversacion_id = $1::uuid
         ORDER BY created_at DESC
         LIMIT $2
        """,
        conversacion_id,
        max(1, min(int(limite), 20)),
    )
    if not filas:
        return []
    if any(str(fila["actor_id"]) != str(actor_id) for fila in filas):
        raise PermissionError("conversacion de otro actor")

    historial: list[dict[str, str]] = []
    for fila in reversed(filas):
        pregunta = str(fila["pregunta"] or "")[:MAX_TEXTO]
        respuesta = str(fila["respuesta"] or "")[:MAX_TEXTO]
        if pregunta:
            historial.append({"role": "user", "content": pregunta})
        if respuesta:
            historial.append({"role": "assistant", "content": respuesta})
    return historial


async def guardar(
    pool: asyncpg.Pool,
    conversacion_id: str,
    actor_id: str,
    rol_actor: str,
    pregunta: str,
    respuesta: str,
    estado: str,
) -> None:
    await pool.execute(
        """
        INSERT INTO gato_turnos (
            conversacion_id, actor_id, rol_actor, pregunta, respuesta, estado
        ) VALUES ($1::uuid, $2, $3, $4, $5, $6)
        """,
        conversacion_id,
        actor_id,
        rol_actor,
        str(pregunta or "")[:MAX_TEXTO],
        str(respuesta or "")[:MAX_TEXTO],
        estado,
    )
