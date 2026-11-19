"""HTTP del asistente interno. El rol sale de la sesión, nunca del body."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import asyncpg
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from . import cerebro_bridge, comercial_bridge, memoria, recordatorios
from ..db import setting
from ..panel_acl import exigir_modulo
from ..services import media as media_svc
from ..voz.ingesta import ingestar_audio
from .bibliotecario import Bibliotecario
from .gato import responder_detallado
from .orquestador import Actor, Respuesta

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
    transcripcion: str | None = None


class RecordatorioIn(BaseModel):
    """Alta directa de un recordatorio (el chat usa la misma via)."""

    model_config = ConfigDict(extra="forbid")

    destinatario: str = Field(min_length=1, max_length=120)
    mensaje: str = Field(min_length=1, max_length=900)
    cuando: str = Field(min_length=1, max_length=120)


class RecordatorioOut(BaseModel):
    estado: str
    nota: str | None = None
    datos: Any = None


async def actor_actual(request: Request) -> Actor:
    """Resuelve el actor desde la sesión. El body nunca aporta el rol."""
    rol_crudo = (request.headers.get("X-Panel-Role") or "").strip().lower()
    if rol_crudo in ROLES:
        nombre = request.headers.get("X-Panel-Name") or ROLES[rol_crudo].title()
        actor_id = request.headers.get("X-Panel-User") or rol_crudo
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


def _modo_envio(request: Request) -> str:
    """Canal real de salida: 'evolution' o 'sandbox'.

    No se usa `modo` porque ese campo tambien cambia cuando Bunny esta en
    sandbox; para el aviso lo que importa es quien envia el WhatsApp.
    """
    runtime = getattr(request.app.state, "whatsapp", None)
    if runtime is None:
        return ""
    try:
        return str(runtime.estado().get("envio") or "")
    except Exception:  # un runtime raro no debe romper el chat
        return ""


async def _respuesta_con_ratificacion(
    mensaje: str,
    actor: Actor,
    biblio: Bibliotecario,
    historial: list[dict[str, str]] | None,
) -> Respuesta:
    """Si hay un borrador pendiente, "si"/"no" lo confirman sin pasar por el LLM.

    Es determinista a propósito: la ratificación no depende del modelo.
    """
    if not isinstance(biblio.pool, asyncpg.Pool):
        return await responder_detallado(
            mensaje, actor.rol, biblio, actor.nombre, historial=historial,
            actor_id=actor.actor_id, conversacion_id=actor.conversacion_id,
            modo_envio=actor.modo_envio,
        )
    pendiente = await recordatorios.pendiente_de(biblio, actor=actor)
    if pendiente is not None:
        if recordatorios.es_afirmacion(mensaje):
            r = await recordatorios.confirmar(
                biblio, actor=actor, recordatorio_id=str(pendiente["id"])
            )
            return Respuesta(r.nota or "Listo.", "OK", [r])
        if recordatorios.es_negacion(mensaje):
            r = await recordatorios.descartar(
                biblio, actor=actor, recordatorio_id=str(pendiente["id"])
            )
            return Respuesta(r.nota or "Descartado.", "OK", [r])
    return await responder_detallado(
        mensaje, actor.rol, biblio, actor.nombre, historial=historial,
        actor_id=actor.actor_id, conversacion_id=actor.conversacion_id,
        modo_envio=actor.modo_envio,
    )


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
    actor.conversacion_id = conversacion_id
    actor.modo_envio = _modo_envio(request)

    async def cerrar(texto: str, estado: str) -> MensajeOut:
        if memoria_activa:
            await memoria.guardar(
                pool,
                conversacion_id,
                actor.actor_id,
                actor.rol,
                body.mensaje,
                texto,
                estado,
            )
        return MensajeOut(
            respuesta=texto, estado=estado, conversacion_id=conversacion_id
        )

    # Modulo comercial: Gato solo pide, no reimplementa reglas.
    if comercial_bridge.es_leads_caidos(body.mensaje):
        texto = await comercial_bridge.listar_caidos(pool)
        return await cerrar(texto, "OK")
    if comercial_bridge.es_agendar(body.mensaje):
        try:
            resultado = await comercial_bridge.agendar(
                pool, body.mensaje, actor=actor.nombre
            )
            return await cerrar(
                str(resultado.get("mensaje") or "Listo."),
                "OK" if resultado.get("estado") == "OK" else "FALTA",
            )
        except Exception as exc:  # noqa: BLE001
            return await cerrar(f"No pude agendar: {exc}", "ERROR")

    # Puente controlado con el Cerebro: solo si el mensaje lo pide explicito.
    if cerebro_bridge.es_dictado(body.mensaje):
        try:
            datos = await cerebro_bridge.interpretar(
                body.mensaje,
                usuario=actor.actor_id,
                rol=actor.rol,
                nombre=actor.nombre,
            )
            texto = cerebro_bridge.mensaje_de_resumen(datos)
            estado = "OK"
        except HTTPException as exc:
            texto = f"No pude pasarlo al Cerebro: {exc.detail}"
            estado = "ERROR"
        if memoria_activa:
            await memoria.guardar(
                pool,
                conversacion_id,
                actor.actor_id,
                actor.rol,
                body.mensaje,
                texto,
                estado,
            )
        return MensajeOut(
            respuesta=texto, estado=estado, conversacion_id=conversacion_id
        )

    respuesta = await _respuesta_con_ratificacion(
        body.mensaje, actor, biblio, historial
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


@router.post("/audio", response_model=MensajeOut)
async def chat_audio(
    request: Request,
    archivo: UploadFile = File(...),
    conversacion_id: str | None = Form(default=None),
    modo: str = Form(default="dictado"),
) -> MensajeOut:
    """Nota de voz para Gato: reutiliza el componente de voz (no lo duplica).

    Por defecto el audio es un **dictado** y se entrega al Cerebro (mismo
    puente que el prefijo escrito). Si el usuario elige ``modo=pregunta``, se
    responde como una consulta normal de Gato.
    """
    if modo not in ("dictado", "pregunta"):
        raise HTTPException(status_code=422, detail="modo invalido: dictado|pregunta")
    perfil = await exigir_modulo(request, "voz", mutacion=True)
    pool = getattr(request.app.state, "pool", None)
    if not isinstance(pool, asyncpg.Pool):
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    settings = getattr(request.app.state, "settings", None)
    if settings is None or not await setting(pool, "voz.enabled"):
        raise HTTPException(
            status_code=503,
            detail="el componente de voz esta apagado (voz.enabled)",
        )
    limite = media_svc.limite_bytes("AUDIO", settings)
    datos = await archivo.read(limite + 1)
    try:
        ingesta = await ingestar_audio(
            pool,
            settings,
            datos=datos,
            nombre=archivo.filename or "audio.ogg",
            mime=archivo.content_type,
            canal_origen="PANEL_WEB",
            emisor_usuario=str(perfil.get("nombre") or "") or None,
        )
    except media_svc.MediaInvalido as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except media_svc.MediaNoDisponible as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    texto = str(ingesta.get("texto_crudo") or "").strip()
    if not texto:
        raise HTTPException(
            status_code=422,
            detail=(
                "no se pudo transcribir el audio: "
                f"{ingesta.get('estado')} {ingesta.get('error') or ''}".strip()
            ),
        )
    actor = await actor_actual(request)
    # El audio es dictado por defecto: el Cerebro es quien interpreta
    # instrucciones. Escribir en Gato sigue siendo una consulta normal.
    mensaje = f"dictado: {texto}" if modo == "dictado" else texto
    salida = await chat(
        MensajeIn(mensaje=mensaje[:1000], conversacion_id=conversacion_id),
        request,
        actor,
    )
    return MensajeOut(
        respuesta=salida.respuesta,
        estado=salida.estado,
        conversacion_id=salida.conversacion_id,
        transcripcion=texto,
    )


@router.get("/recordatorios", response_model=RecordatorioOut)
async def listar_recordatorios(
    request: Request,
    incluir_historicos: bool = False,
    actor: Actor = Depends(actor_actual),
) -> RecordatorioOut:
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    resultado = await recordatorios.listar(
        Bibliotecario(pool), actor=actor, incluir_historicos=incluir_historicos
    )
    return RecordatorioOut(
        estado=resultado.estado, nota=resultado.nota, datos=resultado.datos
    )


@router.post("/recordatorios", response_model=RecordatorioOut)
async def crear_recordatorio(
    body: RecordatorioIn,
    request: Request,
    actor: Actor = Depends(actor_actual),
) -> RecordatorioOut:
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    resultado = await recordatorios.crear(
        Bibliotecario(pool),
        actor=actor,
        destinatario=body.destinatario,
        mensaje=body.mensaje,
        cuando=body.cuando,
    )
    if resultado.estado in ("ACL",):
        raise HTTPException(status_code=403, detail=resultado.nota)
    if resultado.estado in ("FALTA_PARAMETRO", "VACIO"):
        raise HTTPException(status_code=422, detail=resultado.nota)
    return RecordatorioOut(
        estado=resultado.estado, nota=resultado.nota, datos=resultado.datos
    )


@router.post("/recordatorios/{recordatorio_id}/cancelar", response_model=RecordatorioOut)
async def cancelar_recordatorio(
    recordatorio_id: str,
    request: Request,
    actor: Actor = Depends(actor_actual),
) -> RecordatorioOut:
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    try:
        UUID(recordatorio_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="id inválido") from exc
    resultado = await recordatorios.cancelar(
        Bibliotecario(pool), actor=actor, recordatorio_id=recordatorio_id
    )
    if resultado.estado == "VACIO":
        raise HTTPException(status_code=404, detail=resultado.nota)
    return RecordatorioOut(
        estado=resultado.estado, nota=resultado.nota, datos=resultado.datos
    )
