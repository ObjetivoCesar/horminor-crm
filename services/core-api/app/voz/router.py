"""HTTP del componente de voz.

El panel y M1 llaman al mismo servicio. Sin proveedor STT el audio se guarda y
se responde con ``DEGRADADO_SIN_CREDENCIAL``: nunca se inventa texto.
"""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from ..db import setting
from ..panel_acl import exigir_modulo
from ..services import media as media_svc
from .ingesta import CANALES, ingestar_audio, obtener_ingesta

router = APIRouter(prefix="/api/v1/voz", tags=["voz"])


def _pool(request: Request) -> asyncpg.Pool:
    pool = getattr(request.app.state, "pool", None)
    if not isinstance(pool, asyncpg.Pool):
        raise HTTPException(status_code=503, detail="base de datos no disponible")
    return pool


def _settings(request: Request) -> Any:
    return request.app.state.settings


async def _habilitado(pool: asyncpg.Pool, clave: str) -> bool:
    return bool(await setting(pool, clave, False))


@router.post("/transcribir", status_code=201)
async def transcribir(
    request: Request,
    archivo: UploadFile = File(...),
    canal_origen: str = Form("PANEL_WEB"),
    emisor_telefono: str | None = Form(default=None),
) -> dict[str, Any]:
    perfil = await exigir_modulo(request, "voz", mutacion=True)
    pool = _pool(request)
    settings = _settings(request)
    if not await _habilitado(pool, "voz.enabled"):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "VOZ_DESHABILITADA",
                "message": "voz.enabled esta apagado; activelo cuando el proveedor este configurado",
            },
        )
    canal = (canal_origen or "").upper()
    if canal not in CANALES:
        raise HTTPException(
            status_code=422, detail=f"canal_origen invalido: {canal_origen}"
        )
    limite = media_svc.limite_bytes("AUDIO", settings)
    datos = await archivo.read(limite + 1)
    try:
        return await ingestar_audio(
            pool,
            settings,
            datos=datos,
            nombre=archivo.filename or "audio.ogg",
            mime=archivo.content_type,
            canal_origen=canal,
            emisor_usuario=perfil.get("nombre"),
            emisor_telefono=(emisor_telefono or "").strip() or None,
        )
    except media_svc.MediaInvalido as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except media_svc.MediaNoDisponible as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/ingestas/{ingesta_id}")
async def consultar(request: Request, ingesta_id: str) -> dict[str, Any]:
    await exigir_modulo(request, "voz")
    try:
        uuid.UUID(ingesta_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="ingesta_id invalido") from exc
    pool = _pool(request)
    datos = await obtener_ingesta(pool, ingesta_id)
    if datos is None:
        raise HTTPException(status_code=404, detail="ingesta no encontrada")
    return datos
