"""Centro de Configuracion Superadmin - endpoints HTTP.

Ratificado 2026-11-08: **sin autenticacion en esta etapa**. Las rutas quedan
abiertas en local/desarrollo para no frenar el Frontend ni las pruebas de API.
El endpoint externo del Centinela conserva su ``X-Agency-Master-Key``.

Toda escritura avisa al Modulo 1 para que recargue su ventana de debounce y su
cache de identidad: el cambio se ve en la siguiente peticion, sin reiniciar el
servidor.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import asyncpg
from fastapi import APIRouter, Body, HTTPException, Query, Request

from .secciones import SECCIONES, SeccionDesconocidaError, normalizar_seccion
from .store import ConfigStore, PostgresConfigStore

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/superadmin", tags=["superadmin"])


def _store(request: Request) -> ConfigStore:
    """Store inyectado por los tests o construido sobre el pool real."""
    configurado = getattr(request.app.state, "config_store", None)
    if configurado is not None:
        return configurado
    pool = getattr(request.app.state, "pool", None)
    if not isinstance(pool, asyncpg.Pool):
        raise HTTPException(status_code=503, detail="base de datos no disponible")
    store = PostgresConfigStore(pool)
    request.app.state.config_store = store
    return store


async def _refrescar_modulo_1(request: Request) -> None:
    """Recarga en caliente de debounce e identidad. Nunca rompe el guardado."""
    runtime = getattr(request.app.state, "whatsapp", None)
    recargar = getattr(runtime, "recargar_config", None)
    if recargar is None:
        return
    try:
        await recargar()
    except Exception:  # el guardado ya ocurrio; solo se reporta
        log.warning("config guardada pero el Modulo 1 no pudo recargar", exc_info=True)


def _seccion(nombre: str) -> str:
    try:
        return normalizar_seccion(nombre)
    except SeccionDesconocidaError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


# ---------------------------------------------------------------------------
# Configuracion completa y por seccion
# ---------------------------------------------------------------------------
@router.get("/config")
async def leer_config(request: Request) -> dict[str, Any]:
    """Las 7 secciones en una sola llamada (lo que consume el Frontend)."""
    return await _store(request).leer_todo()


@router.get("/secciones")
async def listar_secciones() -> dict[str, Any]:
    return {"secciones": list(SECCIONES)}


@router.get("/config/{nombre}")
async def leer_seccion(request: Request, nombre: str) -> dict[str, Any]:
    return await _store(request).leer_seccion(_seccion(nombre))


@router.put("/config/{nombre}")
async def guardar_seccion(
    request: Request,
    nombre: str,
    datos: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    seccion = _seccion(nombre)
    try:
        resultado = await _store(request).guardar_seccion(seccion, datos)
    except ValueError as exc:
        raise _error(exc) from exc
    await _refrescar_modulo_1(request)
    return resultado


# ---------------------------------------------------------------------------
# CRUD directo de recetas
# ---------------------------------------------------------------------------
@router.get("/recetas")
async def listar_recetas(request: Request) -> dict[str, Any]:
    return {"recetas": await _store(request).listar_recetas()}


@router.post("/recetas", status_code=201)
async def crear_receta(
    request: Request, datos: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    try:
        receta = await _store(request).upsert_receta(datos)
    except ValueError as exc:
        raise _error(exc) from exc
    await _refrescar_modulo_1(request)
    return receta


@router.put("/recetas/{resistencia}")
async def actualizar_receta(
    request: Request,
    resistencia: str,
    datos: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    cuerpo = {**datos, "resistencia": resistencia}
    try:
        receta = await _store(request).upsert_receta(cuerpo)
    except ValueError as exc:
        raise _error(exc) from exc
    await _refrescar_modulo_1(request)
    return receta


@router.delete("/recetas/{resistencia}")
async def eliminar_receta(request: Request, resistencia: str) -> dict[str, Any]:
    eliminada = await _store(request).eliminar_receta(resistencia)
    if not eliminada:
        raise HTTPException(status_code=404, detail=f"receta inexistente: {resistencia}")
    await _refrescar_modulo_1(request)
    return {"eliminada": True, "resistencia": resistencia.upper()}


# ---------------------------------------------------------------------------
# CRUD directo de flota
# ---------------------------------------------------------------------------
@router.get("/flota")
async def listar_flota(request: Request) -> dict[str, Any]:
    return {"mixers": await _store(request).listar_flota()}


@router.post("/flota", status_code=201)
async def crear_mixer(
    request: Request, datos: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    try:
        mixer = await _store(request).upsert_mixer(datos)
    except ValueError as exc:
        raise _error(exc) from exc
    await _refrescar_modulo_1(request)
    return mixer


@router.put("/flota/{codigo}")
async def actualizar_mixer(
    request: Request,
    codigo: str,
    datos: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    cuerpo = {**datos, "codigo": codigo}
    try:
        mixer = await _store(request).upsert_mixer(cuerpo)
    except ValueError as exc:
        raise _error(exc) from exc
    await _refrescar_modulo_1(request)
    return mixer


@router.delete("/flota/{codigo}")
async def eliminar_mixer(request: Request, codigo: str) -> dict[str, Any]:
    eliminado = await _store(request).eliminar_mixer(codigo)
    if not eliminado:
        raise HTTPException(status_code=404, detail=f"mixer inexistente: {codigo}")
    await _refrescar_modulo_1(request)
    return {"eliminado": True, "codigo": codigo.upper()}


# ---------------------------------------------------------------------------
# Simulador de WhatsApp en pantalla (Directriz 2026-11-08)
# ---------------------------------------------------------------------------
def _runtime(request: Request) -> Any:
    runtime = getattr(request.app.state, "whatsapp", None)
    if runtime is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Modulo 1 no inicializado: no hay worker ni pipeline para simular. "
                "Revisar /health y las credenciales del entorno."
            ),
        )
    return runtime


@router.get("/simulador/remitentes")
async def remitentes_simulador(request: Request) -> dict[str, Any]:
    """Opciones del selector: staff real (o semilla) + lead nuevo."""
    directorio = await _store(request).leer_seccion("directorio_roles_whatsapp")
    staff = directorio.get("staff") or {}
    opciones: list[dict[str, Any]] = []
    for telefono, crudo in staff.items():
        if isinstance(crudo, dict):
            rol = crudo.get("rol")
            nombre = crudo.get("nombre") or telefono
            mixer = crudo.get("mixer")
        else:
            rol = crudo
            nombre = telefono
            mixer = None
        opciones.append(
            {
                "telefono": telefono,
                "nombre": nombre,
                "rol": rol,
                "mixer": mixer,
            }
        )
    opciones.append(
        {
            "telefono": "+593990000999",
            "nombre": "Lead Nuevo",
            "rol": "LEAD_DESCONOCIDO",
            "mixer": None,
        }
    )
    return {"remitentes": opciones}


@router.post("/simulador-whatsapp")
async def simular_whatsapp(
    request: Request, datos: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Dispara el webhook interno (pipeline completo) sin Evolution API."""
    from ..m1_whatsapp.models import IncomingMessage, MediaAttachment, MessageBatch

    telefono = str(datos.get("telefono") or "").strip()
    texto = str(datos.get("texto") or "")
    if not telefono:
        raise HTTPException(status_code=422, detail="telefono es obligatorio")

    media = tuple(
        MediaAttachment(
            tipo=str(adjunto.get("tipo") or "imagen"),
            mimetype=adjunto.get("mimetype"),
            nombre=adjunto.get("nombre"),
            url_origen=adjunto.get("url_origen"),
            base64=adjunto.get("base64"),
            transcripcion=adjunto.get("transcripcion"),
        )
        for adjunto in (datos.get("media") or [])
        if isinstance(adjunto, dict)
    )
    mensaje = IncomingMessage(
        mensaje_id=f"sim-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        telefono=telefono,
        texto=texto,
        media=media,
        nombre_contacto=datos.get("nombre_contacto"),
    )
    runtime = _runtime(request)
    resultado = await runtime.pipeline.procesar(
        MessageBatch(telefono=telefono, mensajes=(mensaje,))
    )
    salida = resultado.a_dict()
    salida["judge_mode"] = runtime.estado().get("judge_mode")
    salida["modo"] = runtime.estado().get("modo")
    return salida


@router.get("/sandbox/outbox")
async def leer_outbox(
    request: Request, limite: int = Query(default=50, ge=1, le=200)
) -> dict[str, Any]:
    """Mensajes que el modo SANDBOX encolo en lugar de enviar por WhatsApp."""
    runtime = _runtime(request)
    return {"outbox": await runtime.repo.listar_outbox(limite)}
