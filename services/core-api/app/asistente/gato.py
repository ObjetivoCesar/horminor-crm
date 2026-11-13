"""Fachada de Gato: el loop y el futuro endpoint usan `responder`."""

from __future__ import annotations

from .bibliotecario import Bibliotecario
from .catalogo import permite as permitido
from .orquestador import Actor, Respuesta, responder as _responder
from .redactor import money, numero
from .texto import fecha_de, normalizar

__all__ = [
    "Actor",
    "Respuesta",
    "fecha_de",
    "money",
    "normalizar",
    "numero",
    "permitido",
    "responder",
    "responder_detallado",
]


def _actor(
    rol: str,
    nombre: str | None = None,
    actor_id: str = "panel",
    conversacion_id: str | None = None,
    modo_envio: str = "",
) -> Actor:
    rol = rol.upper()
    if rol == "JULIO":
        rol = "SUPERADMIN"
        nombre = nombre or "Julio"
    if not nombre:
        if rol == "SUPERADMIN":
            nombre = "Julio"
        elif rol == "SECRETARIA":
            nombre = "Secretaría"
        else:
            nombre = rol.title()
    return Actor(
        nombre=nombre,
        rol=rol,
        actor_id=actor_id,
        conversacion_id=conversacion_id,
        modo_envio=modo_envio,
    )


async def responder_detallado(
    pregunta: str,
    rol: str,
    biblio: Bibliotecario,
    nombre: str | None = None,
    historial: list[dict[str, str]] | None = None,
    actor_id: str = "panel",
    conversacion_id: str | None = None,
    modo_envio: str = "",
) -> Respuesta:
    return await _responder(
        pregunta,
        _actor(
            rol, nombre,
            actor_id=actor_id,
            conversacion_id=conversacion_id,
            modo_envio=modo_envio,
        ),
        biblio,
        historial=historial,
    )


async def responder(
    pregunta: str,
    rol: str,
    biblio: Bibliotecario,
    nombre: str | None = None,
    historial: list[dict[str, str]] | None = None,
    actor_id: str = "panel",
    conversacion_id: str | None = None,
    modo_envio: str = "",
) -> str:
    respuesta = await responder_detallado(
        pregunta, rol, biblio, nombre,
        historial=historial,
        actor_id=actor_id,
        conversacion_id=conversacion_id,
        modo_envio=modo_envio,
    )
    return respuesta.texto
