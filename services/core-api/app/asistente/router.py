"""HTTP del asistente interno. El rol sale de la sesión, nunca del body."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID, uuid4

import asyncpg
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from . import cerebro_bridge, comercial_bridge, conversaciones, memoria, recordatorios
from ..db import setting
from ..panel_acl import exigir_modulo, resolver_perfil
from ..services import media as media_svc
from ..voz.ingesta import ingestar_audio
from .bibliotecario import Bibliotecario
from .gato import responder_detallado
from .orquestador import Actor, Respuesta

router = APIRouter(prefix="/api/v1/asistente", tags=["asistente"])
gato_router = APIRouter(prefix="/api/v1/gato", tags=["gato"])

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
    client_turn_id: str | None = Field(default=None, max_length=80)


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


def _puente(mensaje: str) -> str | None:
    """Precedencia de los puentes de Gato.

    El prefijo explícito del Cerebro gana sobre los atajos comerciales: un
    dictado puede decir «agendar» o «entrega» sin ser una cita comercial.
    """
    if cerebro_bridge.es_dictado(mensaje):
        return "cerebro"
    if comercial_bridge.es_leads_caidos(mensaje):
        return "leads"
    if comercial_bridge.es_agendar(mensaje):
        return "agenda"
    return None


def _perfil_id(actor: Actor) -> str | None:
    try:
        return str(UUID(str(actor.actor_id)))
    except (ValueError, TypeError):
        return None


def _plano(texto: str) -> str:
    import unicodedata

    base = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in base if unicodedata.category(c) != "Mn")


def _es_continuacion(mensaje: str) -> bool:
    """True si el mensaje parece una respuesta corta o una corrección."""
    plano = _plano(mensaje)
    palabras = plano.split()
    if not palabras or len(palabras) > 30:
        return False
    if any(
        marca in plano
        for marca in ("me acaba de", "es el mismo", "agregale", "corrige", "continua")
    ):
        return True
    return bool(re.match(r"^(si|no|correcto|ya|efectivamente)\b", plano))


def _contexto_dictado(
    historial: list[dict[str, str]] | None, mensaje: str
) -> str | None:
    """Contexto deliberado: solo el dictado anterior si se está continuando.

    No se arrastran los últimos cinco dictados. Un dictado nuevo, largo o con
    otro cliente abre una operación nueva. Se conserva el hilo solo cuando el
    mensaje responde una pregunta pendiente o pide corregir/agregar.
    """
    if not _es_continuacion(mensaje):
        return None

    previo: str | None = None
    ultima_respuesta = ""
    for turno in historial or []:
        rol = turno.get("role")
        contenido = str(turno.get("content") or "").strip()
        if rol == "user" and contenido.lower().startswith(
            ("dictado:", "cerebro:", "dicta:")
        ):
            limpio = cerebro_bridge.texto_limpio(contenido)
            if limpio:
                previo = limpio
        elif rol == "assistant" and contenido:
            ultima_respuesta = contenido

    if not previo:
        return None

    explícito = any(
        marca in _plano(mensaje)
        for marca in ("es el mismo", "agregale", "corrige", "continua")
    )
    hay_pregunta = (
        "?" in ultima_respuesta
        or "antes de ejecutar" in ultima_respuesta.lower()
        or "necesito" in ultima_respuesta.lower()
    )
    if explícito or hay_pregunta:
        return previo
    return None


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
    perfil_id = _perfil_id(actor)

    if memoria_activa:
        try:
            if conversacion_id:
                conv = await conversaciones.asegurar_abierta(
                    pool, conversacion_id=conversacion_id, actor_id=actor.actor_id
                )
            else:
                conv = await conversaciones.actual(
                    pool,
                    actor_id=actor.actor_id,
                    rol_actor=actor.rol,
                    perfil_id=perfil_id,
                )
            conversacion_id = str(conv["id"])
        except conversaciones.ConversacionCerrada as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CONVERSACION_CERRADA",
                    "message": "la conversacion esta cerrada; recarga la activa",
                },
            ) from exc
        except conversaciones.ConversacionNoEncontrada as exc:
            raise HTTPException(
                status_code=404, detail="conversacion no encontrada"
            ) from exc

        if body.client_turn_id:
            existente = await conversaciones.turno_por_client_id(
                pool,
                conversacion_id=conversacion_id,
                client_turn_id=body.client_turn_id,
            )
            if existente is not None:
                return MensajeOut(
                    respuesta=str(existente["respuesta"]),
                    estado=str(existente["estado"]),
                    conversacion_id=conversacion_id,
                )
    else:
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
                client_turn_id=body.client_turn_id,
            )
            await conversaciones.tocar(pool, conversacion_id)
        return MensajeOut(
            respuesta=texto, estado=estado, conversacion_id=conversacion_id
        )

    # Puente controlado con el Cerebro: el prefijo explicito manda. Debe ir
    # antes del atajo comercial porque un dictado puede contener «agendar» y
    # «entrega» sin ser una cita comercial.
    puente = _puente(body.mensaje)
    if puente == "cerebro":
        try:
            datos = await cerebro_bridge.interpretar(
                body.mensaje,
                usuario=actor.actor_id,
                rol=actor.rol,
                nombre=actor.nombre,
                contexto=_contexto_dictado(historial, body.mensaje),
                conversacion_id=conversacion_id,
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
                client_turn_id=body.client_turn_id,
            )
            await conversaciones.tocar(pool, conversacion_id)
        return MensajeOut(
            respuesta=texto, estado=estado, conversacion_id=conversacion_id
        )

    # Modulo comercial: Gato solo pide, no reimplementa reglas.
    if puente == "leads":
        texto = await comercial_bridge.listar_caidos(pool)
        return await cerrar(texto, "OK")
    if puente == "agenda":
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
            client_turn_id=body.client_turn_id,
        )
        await conversaciones.tocar(pool, conversacion_id)
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
    client_turn_id: str | None = Form(default=None),
    modo: str = Form(default="dictado"),
) -> MensajeOut:
    """Nota de voz para Gato: reutiliza el componente de voz (no lo duplica).

    Por defecto el audio es un **dictado** y se entrega al Cerebro (mismo
    puente que el prefijo escrito). Si el usuario elige ``modo=pregunta``, se
    responde como una consulta normal de Gato.
    """
    if modo not in ("dictado", "pregunta"):
        raise HTTPException(status_code=422, detail="modo invalido: dictado|pregunta")
    try:
        perfil = await exigir_modulo(request, "voz", mutacion=True)
    except HTTPException as exc:
        detalle = exc.detail if isinstance(exc.detail, dict) else {}
        if exc.status_code == 403 and detalle.get("code") == "MODULE_NOT_ALLOWED":
            try:
                quien = await resolver_perfil(request)
                nombre = str(quien.get("nombre") or "el perfil seleccionado")
            except HTTPException:
                nombre = "el perfil seleccionado"
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "VOZ_NO_HABILITADA",
                    "message": (
                        f"«{nombre}» no tiene el módulo Voz. Cambia a Julio en "
                        "«Viendo como» o pide que habiliten Voz y Cerebro."
                    ),
                    "perfil": nombre,
                },
            ) from exc
        raise
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
        MensajeIn(
            mensaje=mensaje[:1000],
            conversacion_id=conversacion_id,
            client_turn_id=client_turn_id,
        ),
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


@gato_router.get("/conversacion/actual")
async def conversacion_actual(
    request: Request,
    actor: Actor = Depends(actor_actual),
) -> dict[str, Any]:
    """Última conversación del actor, con sus turnos."""
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    conv = await conversaciones.actual(
        pool,
        actor_id=actor.actor_id,
        rol_actor=actor.rol,
        perfil_id=_perfil_id(actor),
    )
    return {
        "conversacion": conv,
        "turnos": await conversaciones.turnos(pool, str(conv["id"])),
    }


@gato_router.post("/conversacion/refresh")
async def conversacion_refresh(
    request: Request,
    actor: Actor = Depends(actor_actual),
) -> dict[str, Any]:
    """Cierra la conversación abierta y devuelve una nueva vacía."""
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    conv = await conversaciones.cerrar_y_abrir(
        pool,
        actor_id=actor.actor_id,
        rol_actor=actor.rol,
        perfil_id=_perfil_id(actor),
    )
    return {"conversacion": conv, "turnos": []}
