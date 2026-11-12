"""HTTP del asistente interno. El rol sale de la sesión, nunca del body."""

from __future__ import annotations

from uuid import UUID, uuid4

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from . import memoria
from .bibliotecario import Bibliotecario
from .gato import responder_detallado
from .orquestador import Actor

router = APIRouter(prefix="/api/v1/asistente", tags=["asistente"])

ROLES = {
    "julio": "SUPERADMIN",
    "superadmin": "SUPERADMIN",
    "secretaria": "SECRETARIA",
    "contadora": "CONTADORA",
    "bodega": "BODEGA",
}


class MensajeIn(BaseModel):
    """El body NO admite actor_context: el rol se resuelve en el backend."""

    model_config = ConfigDict(extra="forbid")

    mensaje: str = Field(min_length=1, max_length=1000)
    conversacion_id: str | None = Field(default=None, max_length=80)


class MensajeOut(BaseModel):
    respuesta: str
    estado: str
    conversacion_id: str


async def actor_actual(request: Request) -> Actor:
    """Resuelve el actor desde la sesión. El body nunca aporta el rol."""
    rol_crudo = (request.headers.get("X-Panel-Role") or "").strip().lower()
    if rol_crudo in ROLES:
        nombre = request.headers.get("X-Panel-Name") or ROLES[rol_crudo].title()
        actor_id = request.headers.get("X-Panel-User") or "panel"
        return Actor(nombre=nombre, rol=ROLES[rol_crudo], actor_id=actor_id)

    usuario = (request.headers.get("X-Panel-User") or "").strip()
    if not usuario:
        raise HTTPException(status_code=401, detail="Sesión no autenticada")

    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")

    fila = await pool.fetchrow(
        """
        SELECT nombre, rol_base
          FROM panel_users_acl
         WHERE id = $1 AND activo AND deleted_at IS NULL
        """,
        usuario,
    )
    if not fila:
        raise HTTPException(status_code=401, detail="Sesión no autenticada")
    if fila["rol_base"] not in ROLES.values():
        raise HTTPException(status_code=403, detail="Tu perfil no tiene acceso a Gato")
    return Actor(nombre=fila["nombre"], rol=fila["rol_base"], actor_id=usuario)


@router.post("/chat", response_model=MensajeOut)
async def chat(
    body: MensajeIn,
    request: Request,
    actor: Actor = Depends(actor_actual),
) -> MensajeOut:
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")

    memoria_activa = isinstance(pool, asyncpg.Pool)
    conversacion_id = (body.conversacion_id or "").strip()
    if conversacion_id:
        try:
            UUID(conversacion_id)
        except ValueError:
            conversacion_id = ""
    if not conversacion_id:
        conversacion_id = str(uuid4())

    historial: list[dict[str, str]] = []
    if memoria_activa:
        try:
            historial = await memoria.cargar(pool, conversacion_id, actor.actor_id)
        except PermissionError as exc:
            raise HTTPException(
                status_code=403, detail="La conversación pertenece a otro usuario"
            ) from exc

    biblio = Bibliotecario(pool)
    respuesta = await responder_detallado(
        body.mensaje, actor.rol, biblio, actor.nombre, historial=historial
    )
    if memoria_activa:
        await memoria.guardar(
            pool,
            conversacion_id,
            actor.actor_id,
            actor.rol,
            body.mensaje,
            respuesta.texto,
            respuesta.estado,
        )
    return MensajeOut(
        respuesta=respuesta.texto,
        estado=respuesta.estado,
        conversacion_id=conversacion_id,
    )
