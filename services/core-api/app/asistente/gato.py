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


def _actor(rol: str, nombre: str | None = None) -> Actor:
    rol = rol.upper()
    if rol == "JULIO":
        rol = "SUPERADMIN"
        nombre = nombre or "Julio"
    if nombre:
        return Actor(nombre=nombre, rol=rol)
    if rol == "SUPERADMIN":
        return Actor(nombre="Julio", rol=rol)
    if rol == "SECRETARIA":
        return Actor(nombre="Secretaría", rol=rol)
    return Actor(nombre=rol.title(), rol=rol)


async def responder_detallado(
    pregunta: str,
    rol: str,
    biblio: Bibliotecario,
    nombre: str | None = None,
    historial: list[dict[str, str]] | None = None,
) -> Respuesta:
    return await _responder(
        pregunta, _actor(rol, nombre), biblio, historial=historial
    )


async def responder(
    pregunta: str,
    rol: str,
    biblio: Bibliotecario,
    nombre: str | None = None,
    historial: list[dict[str, str]] | None = None,
) -> str:
    respuesta = await responder_detallado(
        pregunta, rol, biblio, nombre, historial=historial
    )
    return respuesta.texto
