"""Modulo 1 - Endpoints HTTP: webhook de Evolution y utilidades de operacion."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..auth import verificar_clave
from ..settings import Settings, get_settings
from .models import IncomingMessage, MediaAttachment
from .runtime import WhatsAppRuntime
from .webhook import normalizar_evento

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/whatsapp", tags=["whatsapp"])


def _settings(request: Request) -> Settings:
    configurada = getattr(request.app.state, "settings", None)
    if isinstance(configurada, Settings):
        return configurada
    return get_settings()


def _runtime(request: Request) -> WhatsAppRuntime:
    runtime = getattr(request.app.state, "whatsapp", None)
    if runtime is None or not hasattr(runtime, "accumulator"):
        raise HTTPException(
            status_code=503, detail="Modulo 1 (WhatsApp) no inicializado"
        )
    return runtime


class MediaSimulada(BaseModel):
    tipo: str = "imagen"
    mimetype: str | None = None
    nombre: str | None = None
    base64: str | None = None
    url_origen: str | None = None
    transcripcion: str | None = None


class MensajeSimulado(BaseModel):
    telefono: str = Field(min_length=5)
    texto: str = ""
    mensaje_id: str | None = None
    nombre_contacto: str | None = None
    media: list[MediaSimulada] = Field(default_factory=list)


@router.post("/webhook")
async def webhook(request: Request) -> dict[str, Any]:
    """Recibe eventos de Evolution API y los deja en la ventana de debounce.

    Responde 202 de inmediato: el procesamiento ocurre cuando pasa la ventana
    de silencio (14 s por defecto) y lo hace el worker de fondo.
    """
    runtime = _runtime(request)
    try:
        payload = await request.json()
    except Exception as exc:  # payload malformado: no se rompe el webhook
        raise HTTPException(status_code=422, detail="payload JSON invalido") from exc

    mensajes = normalizar_evento(payload if isinstance(payload, dict) else {})
    for mensaje in mensajes:
        await runtime.accumulator.agregar(mensaje)

    return {
        "recibidos": len(mensajes),
        "ventana_segundos": runtime.ventana_segundos,
    }


@router.post("/simulate")
async def simular(request: Request, body: MensajeSimulado) -> dict[str, Any]:
    """Inyecta un mensaje como si viniera de WhatsApp (requiere clave maestra).

    Existe para el Test de Candado del Hito 3 y para QA manual desde tres
    celulares sin conectar Evolution. No reemplaza al webhook real.
    """
    runtime = _runtime(request)
    verificar_clave(request, _settings(request))

    mensaje = IncomingMessage(
        mensaje_id=body.mensaje_id or f"sim-{datetime.now(timezone.utc).timestamp()}",
        telefono=body.telefono,
        texto=body.texto,
        recibido_at=datetime.now(timezone.utc),
        media=tuple(
            MediaAttachment(
                tipo=m.tipo,
                mimetype=m.mimetype,
                nombre=m.nombre,
                base64=m.base64,
                url_origen=m.url_origen,
                transcripcion=m.transcripcion,
            )
            for m in body.media
        ),
        nombre_contacto=body.nombre_contacto,
    )
    await runtime.accumulator.agregar(mensaje)
    return {
        "recibidos": 1,
        "telefono": mensaje.telefono_normalizado,
        "ventana_segundos": runtime.ventana_segundos,
    }


@router.post("/flush")
async def flush(request: Request) -> dict[str, Any]:
    """Fuerza el procesamiento de los lotes listos. Util para QA y candado."""
    runtime = _runtime(request)
    verificar_clave(request, _settings(request))
    resultados = await runtime.worker.tick()
    return {
        "lotes": len(resultados),
        "resultados": [r.a_dict() for r in resultados],
    }


@router.get("/health")
async def salud(request: Request) -> dict[str, Any]:
    """Estado de configuracion del Modulo 1 (sin secretos)."""
    runtime = _runtime(request)
    estado = runtime.estado()
    configurado = estado["store"] != "memoria" and estado["juez"] != "no_configurado"
    return {
        "modulo": "M1_WHATSAPP",
        "estado": "OK" if configurado else "NO_CONFIGURADO",
        **estado,
    }
