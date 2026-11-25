"""Aviso de Secretaría sobre un evento que ya quedó en Agenda."""
from __future__ import annotations

from uuid import UUID

from ..cerebro import internas


async def notificar_secretaria(
    conn, *, tipo: str, entidad_id: str, fecha: str, hora: str,
    actor_id: str | None, actor: str, rol: str, referencia: str | None = None,
) -> None:
    titulo = {
        "julio": "la visita",
        "recordatorios": "el recordatorio interno",
        "mixers": "la reserva de mixers",
    }[tipo]
    detalle = f" de {referencia}" if referencia else ""
    try:
        usuario_id = str(UUID(str(actor_id)))
    except (ValueError, TypeError):
        usuario_id = None
    resultado = await internas.crear(
        conn,
        instruccion=(
            f"Revisar {titulo}{detalle} que quedó en Agenda el {fecha} a las {hora}. "
            "Corrige el registro en Agenda si hace falta."
        ),
        asignado_rol="SECRETARIA", creado_por=actor, rol_actor=rol, actor_id=usuario_id,
        clave_externa=f"agenda:{tipo}:{entidad_id}",
        metadatos={
            "agenda": {"tipo": tipo, "id": entidad_id, "fecha": fecha, "hora": hora},
        },
    )
    if not resultado.ok:
        raise RuntimeError(resultado.nota or "No se pudo registrar el seguimiento de Secretaría.")
