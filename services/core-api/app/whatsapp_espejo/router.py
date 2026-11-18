"""Espejo de WhatsApp - endpoints de lista blanca y sincronizacion.

Toda la configuracion vive en la base, no en el codigo: agregar o retirar un
numero no altera el historial ya importado.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, AsyncIterator

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ..panel_acl import exigir_modulo
from .espejo import (
    EspejoNoAutorizado,
    EspejoWhatsApp,
    ResultadoSincronizacion,
)
from .eventos import BusEventos
from .evolution import EvolutionError
from .identidad import es_ecuador_movil, jid_de_telefono, telefono_canonico

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/whatsapp/espejo", tags=["whatsapp-espejo"])


class NumeroIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cliente_id: str
    telefono: str = Field(min_length=7, max_length=30)
    etiqueta: str | None = Field(default=None, max_length=120)
    # Corte de historial. Si no se indica, se usa el alta del cliente en el CRM.
    desde: datetime | None = None


def _espejo(request: Request) -> EspejoWhatsApp:
    servicio = getattr(request.app.state, "espejo", None)
    if servicio is None:
        raise HTTPException(
            status_code=503, detail="el espejo de WhatsApp no esta inicializado"
        )
    return servicio


def _cliente_id(valor: str) -> str:
    from ..routers.chat_clientes import _id_cliente

    return _id_cliente(valor)


@router.get("/numeros")
async def listar_numeros(request: Request) -> dict[str, Any]:
    await exigir_modulo(request, "clientes_cartera")
    servicio = _espejo(request)
    return {"numeros": await servicio.repo.listar_numeros()}


@router.post("/numeros")
async def autorizar_numero(request: Request, payload: NumeroIn = Body(...)) -> dict[str, Any]:
    await exigir_modulo(request, "clientes_cartera", mutacion=True)
    servicio = _espejo(request)
    cliente_id = _cliente_id(payload.cliente_id)
    if not await servicio.repo.cliente_existe(cliente_id):
        raise HTTPException(status_code=404, detail="cliente no encontrado")
    telefono = telefono_canonico(payload.telefono)
    if telefono is None:
        raise HTTPException(
            status_code=422,
            detail="telefono invalido: usa el numero con codigo de pais",
        )
    desde = payload.desde or await servicio.repo.cliente_creado_at(cliente_id)
    await servicio.repo.upsert_numero(
        telefono=telefono,
        cliente_id=cliente_id,
        etiqueta=payload.etiqueta,
        desde=desde,
    )
    # El JID de telefono siempre esta disponible; el LID se aprende al vuelo.
    await servicio.repo.registrar_jid(jid_de_telefono(telefono), telefono, "PN")
    return {
        "telefono": telefono,
        "cliente_id": cliente_id,
        "desde": desde,
        "advertencia": (
            None
            if es_ecuador_movil(telefono)
            else "el numero no tiene forma de movil ecuatoriano (593 9 xxxxxxx)"
        ),
    }


@router.post("/numeros/{telefono}/activar")
async def activar_numero(request: Request, telefono: str) -> dict[str, Any]:
    await exigir_modulo(request, "clientes_cartera", mutacion=True)
    servicio = _espejo(request)
    canonico = telefono_canonico(telefono) or telefono
    if not await servicio.repo.activar_numero(canonico, True):
        raise HTTPException(status_code=404, detail="numero no registrado")
    return {"telefono": canonico, "activo": True}


@router.post("/numeros/{telefono}/desactivar")
async def desactivar_numero(request: Request, telefono: str) -> dict[str, Any]:
    """Retira el numero de la lista blanca sin borrar el historial."""
    await exigir_modulo(request, "clientes_cartera", mutacion=True)
    servicio = _espejo(request)
    canonico = telefono_canonico(telefono) or telefono
    if not await servicio.repo.activar_numero(canonico, False):
        raise HTTPException(status_code=404, detail="numero no registrado")
    return {"telefono": canonico, "activo": False}


@router.get("/pendientes")
async def listar_pendientes(request: Request) -> dict[str, Any]:
    await exigir_modulo(request, "clientes_cartera")
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="base de datos no disponible")
    filas = await pool.fetch(
        """
        SELECT id, jid, remote_jid_alt, mensaje_id, motivo, from_me,
               mensaje_tipo, created_at
          FROM whatsapp_espejo_pendientes
         WHERE revisado_at IS NULL
         ORDER BY created_at DESC
         LIMIT 200
        """
    )
    return {"pendientes": [dict(fila) for fila in filas]}


@router.get("/eventos")
async def avisos_en_vivo(
    request: Request, usuario: str | None = Query(default=None)
) -> StreamingResponse:
    """Aviso inmediato de mensajes nuevos para el chat del panel (SSE).

    ``EventSource`` no puede mandar cabeceras, asi que el perfil simulado
    puede venir por ``?usuario=``. Los permisos se aplican igual que en
    cualquier lectura de cartera; el aviso solo lleva identificadores, nunca
    el contenido del mensaje.
    """
    await exigir_modulo(request, "clientes_cartera", usuario=usuario)
    bus = getattr(request.app.state, "eventos_espejo", None)
    if not isinstance(bus, BusEventos):
        raise HTTPException(
            status_code=503, detail="el aviso en vivo no esta inicializado"
        )

    async def flujo() -> AsyncIterator[str]:
        cola = bus.suscribir()
        try:
            async for trozo in bus.transmitir(cola):
                yield trozo
        finally:
            bus.desuscribir(cola)

    return StreamingResponse(
        flujo(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Caddy/Nginx: no acumular el stream en el proxy.
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/clientes/{cliente_id}/sincronizar")
async def sincronizar_cliente(
    request: Request,
    cliente_id: str,
    max_paginas: int | None = None,
    tamano_pagina: int | None = None,
) -> dict[str, Any]:
    """Importa el historial disponible del numero autorizado del cliente."""
    await exigir_modulo(request, "clientes_cartera", mutacion=True)
    servicio = _espejo(request)
    cliente_id = _cliente_id(cliente_id)
    try:
        resultado: ResultadoSincronizacion = await servicio.sincronizar(
            cliente_id=cliente_id,
            max_paginas=max_paginas,
            tamano_pagina=tamano_pagina,
        )
    except EspejoNoAutorizado as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EvolutionError as exc:
        raise HTTPException(
            status_code=502, detail=f"Evolution no respondio: {exc}"
        ) from exc
    return resultado.a_dict()
