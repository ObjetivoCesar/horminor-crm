"""HTTP del asistente interno. El rol sale de la sesión, nunca del body."""

from __future__ import annotations

import json
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


def _quiere_crear_cliente(mensaje: str) -> bool:
    plano = _plano(mensaje)
    if "cliente" in plano and any(
        marca in plano for marca in ("crea", "crear", "confirmado", "dale", "hazlo", "ejecuta")
    ):
        return True
    return plano.strip() in ("confirmado", "confirmo", "dale", "hazlo", "crealo", "crea")


# Acciones del Cerebro que el chat puede ejecutar cuando el humano confirma.
_ACCIONES_CONFIRMABLES = (
    "crear_cliente",
    "crear_tarea_recordatorio",
    "crear_tarea_interna",
)


def _accion_a_confirmar(mensaje: str) -> str | None:
    """Que accion del borrador pide ejecutar este mensaje.

    ``*`` significa «la que siga en el borrador»: el usuario dijo solo
    «confirmado». Nunca se ejecuta dinero desde el chat.
    """
    plano = _plano(mensaje)
    if "cliente" in plano and any(
        marca in plano for marca in ("crea", "crear", "confirmado", "dale", "hazlo", "ejecuta")
    ):
        return "crear_cliente"
    if any(marca in plano for marca in ("recordatorio", "aviso", "mensaje")) and any(
        marca in plano
        for marca in ("confirma", "programa", "envia", "manda", "dale", "ejecuta")
    ):
        return "crear_tarea_recordatorio"
    if "tarea" in plano and any(
        marca in plano
        for marca in ("confirma", "crea", "ejecuta", "deja", "dale", "programa")
    ):
        return "crear_tarea_interna"
    if plano.strip() in (
        "confirmado",
        "confirmo",
        "dale",
        "hazlo",
        "ejecuta",
        "ejecuta el borrador",
        "crealo",
        "crea",
    ):
        return "*"
    return None


def _correccion_de_cita(mensaje: str, pendiente: bool) -> bool:
    """Con un borrador pendiente, solo se toca la cita si el texto la nombra."""
    if not comercial_bridge.es_correccion_cita(mensaje):
        return False
    if not pendiente:
        return True
    plano = _plano(mensaje)
    return any(
        marca in plano
        for marca in (
            "cita",
            "visita",
            "agenda",
            "eso",
            "rectifico",
            "corrijo",
            "no es a la",
            "no es a las",
        )
    )


def _cancelacion_de_cita(mensaje: str, pendiente: bool) -> bool:
    """Con un borrador pendiente, «cancela eso» no debe tocar una cita."""
    if not comercial_bridge.es_cancelacion_cita(mensaje):
        return False
    if not pendiente:
        return True
    plano = _plano(mensaje)
    return any(
        marca in plano for marca in ("cita", "visita", "agenda", "compromiso")
    )


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
    historial: list[dict[str, str]] | None,
    mensaje: str,
    *,
    texto_previo: str | None = None,
    pendiente: bool = False,
) -> str | None:
    """Contexto deliberado: solo el dictado anterior si se está continuando.

    Si el borrador anterior quedó esperando una aclaración, se usa su texto
    completo (no el último mensaje suelto), aunque la respuesta sea larga.
    Si no hay pendiente, solo se continúa con una respuesta corta o una
    corrección explícita.
    """
    if pendiente and texto_previo:
        return texto_previo
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
    pendiente = False
    texto_previo: str | None = None
    estado_dialogo: dict[str, Any] = {}

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
            estado_crudo = conv.get("estado_dialogo_json") or "{}"
            if isinstance(estado_crudo, str):
                try:
                    estado_dialogo = json.loads(estado_crudo)
                except json.JSONDecodeError:
                    estado_dialogo = {}
            else:
                estado_dialogo = estado_crudo if isinstance(estado_crudo, dict) else {}
            pendiente = estado_dialogo.get("estado") in (
                "ESPERANDO_ACLARACION",
                "ESPERANDO_CONFIRMACION",
            )
            if pendiente:
                texto_previo = await conversaciones.texto_ultimo_borrador(
                    pool, conversacion_id
                )
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

    ultima_cita_id = str(estado_dialogo.get("ultima_cita_id") or "").strip() or None

    # Correccion de una cita recien agendada: «rectifico, no es a la 13:00
    # sino a las 14:00». Se resuelve antes del puente para que no responda
    # «no tengo herramienta».
    if _correccion_de_cita(body.mensaje, pendiente):
        try:
            resultado = await comercial_bridge.reagendar_ultima(
                pool,
                body.mensaje,
                cita_id=ultima_cita_id,
                actor=actor.nombre,
                actor_id=actor.actor_id,
            )
            estado = "OK" if resultado.get("estado") == "OK" else "FALTA"
            cita = resultado.get("cita") or {}
            if estado == "OK" and cita.get("id"):
                await conversaciones.actualizar_estado(
                    pool,
                    conversacion_id,
                    estado="LIBRE",
                    ultima_cita_id=str(cita["id"]),
                )
            elif resultado.get("limpiar_ultima"):
                await conversaciones.actualizar_estado(
                    pool,
                    conversacion_id,
                    estado="LIBRE",
                    limpiar_ultima_cita=True,
                )
            return await cerrar(str(resultado.get("mensaje") or "Listo."), estado)
        except Exception as exc:  # noqa: BLE001
            return await cerrar(f"No pude corregir la cita: {exc}", "ERROR")

    if _cancelacion_de_cita(body.mensaje, pendiente):
        try:
            resultado = await comercial_bridge.cancelar_ultima(
                pool,
                body.mensaje,
                cita_id=ultima_cita_id,
                actor=actor.nombre,
                actor_id=actor.actor_id,
            )
            estado = "OK" if resultado.get("estado") == "OK" else "FALTA"
            if estado == "OK":
                await conversaciones.actualizar_estado(
                    pool, conversacion_id, estado="LIBRE"
                )
            elif resultado.get("limpiar_ultima"):
                await conversaciones.actualizar_estado(
                    pool,
                    conversacion_id,
                    estado="LIBRE",
                    limpiar_ultima_cita=True,
                )
            return await cerrar(str(resultado.get("mensaje") or "Listo."), estado)
        except Exception as exc:  # noqa: BLE001
            return await cerrar(f"No pude cancelar la cita: {exc}", "ERROR")

    # Si el borrador esta esperando y el usuario confirma, se ejecuta la accion
    # real del Cerebro. No se responde "no tengo herramienta".
    objetivo = _accion_a_confirmar(body.mensaje)
    if memoria_activa and pendiente and objetivo is not None:
        borrador_id = str(estado_dialogo.get("borrador_id") or "").strip()
        if not borrador_id:
            borrador_id = await conversaciones.ultimo_borrador_id(
                pool, conversacion_id
            ) or ""
        if borrador_id:
            try:
                draft = await cerebro_bridge.obtener_borrador(
                    borrador_id,
                    usuario=actor.actor_id,
                    rol=actor.rol,
                    nombre=actor.nombre,
                )
                acciones = draft.get("acciones") or []
                accion = None
                if objetivo != "*":
                    accion = next(
                        (
                            item
                            for item in acciones
                            if item.get("accion_nombre") == objetivo
                        ),
                        None,
                    )
                if accion is None:
                    # «Confirmado» sin nombre: se ejecuta la que sigue, siempre
                    # que sea una accion con ejecutor. El dinero nunca entra aqui.
                    cerrados = {
                        int(encargo.get("encargo") or 1)
                        for encargo in (draft.get("encargos") or [])
                        if encargo.get("estado_actual")
                        in ("EJECUTADO", "CANCELADO")
                    }
                    siguiente = next(
                        (
                            item
                            for item in sorted(
                                acciones, key=lambda a: int(a.get("orden") or 0)
                            )
                            if int(item.get("encargo") or 1) not in cerrados
                        ),
                        None,
                    )
                    if (
                        siguiente is not None
                        and siguiente.get("accion_nombre") in _ACCIONES_CONFIRMABLES
                    ):
                        accion = siguiente
                    elif siguiente is not None and objetivo != "*":
                        accion = None
                if accion is not None:
                    parametros = accion.get("parametros") or {}
                    mensaje_final = None
                    if accion.get("accion_nombre") == "crear_tarea_recordatorio":
                        mensaje_final = str(parametros.get("mensaje") or "").strip() or None
                    resultado = await cerebro_bridge.confirmar_accion(
                        borrador_id,
                        int(accion.get("orden") or 1),
                        usuario=actor.actor_id,
                        rol=actor.rol,
                        nombre=actor.nombre,
                        mensaje_final=mensaje_final,
                    )
                    datos = resultado.get("datos") or {}
                    texto = str(resultado.get("nota") or "Accion ejecutada.")
                    if (
                        accion.get("accion_nombre") == "crear_cliente"
                        and datos.get("nombre")
                        and "cliente" not in texto.lower()
                    ):
                        texto = f"Cliente creado: {datos['nombre']}."
                    await memoria.guardar(
                        pool,
                        conversacion_id,
                        actor.actor_id,
                        actor.rol,
                        body.mensaje,
                        texto,
                        "OK",
                        client_turn_id=body.client_turn_id,
                    )
                    await conversaciones.tocar(pool, conversacion_id)
                    if int(resultado.get("preguntas_pendientes") or 0) > 0:
                        await conversaciones.actualizar_estado(
                            pool,
                            conversacion_id,
                            estado="ESPERANDO_ACLARACION",
                            borrador_id=borrador_id,
                        )
                    elif resultado.get("estado_borrador") == "EJECUTADO":
                        await conversaciones.actualizar_estado(
                            pool, conversacion_id, estado="LIBRE"
                        )
                    else:
                        await conversaciones.actualizar_estado(
                            pool,
                            conversacion_id,
                            estado="ESPERANDO_CONFIRMACION",
                            borrador_id=borrador_id,
                        )
                    return MensajeOut(
                        respuesta=texto,
                        estado="OK",
                        conversacion_id=conversacion_id,
                    )
            except HTTPException as exc:
                texto = f"No pude ejecutar la acción: {exc.detail}"
                await memoria.guardar(
                    pool,
                    conversacion_id,
                    actor.actor_id,
                    actor.rol,
                    body.mensaje,
                    texto,
                    "ERROR",
                    client_turn_id=body.client_turn_id,
                )
                await conversaciones.tocar(pool, conversacion_id)
                return MensajeOut(
                    respuesta=texto,
                    estado="ERROR",
                    conversacion_id=conversacion_id,
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
                contexto=_contexto_dictado(
                    historial,
                    body.mensaje,
                    texto_previo=texto_previo,
                    pendiente=pendiente,
                ),
                conversacion_id=conversacion_id,
            )
            texto = cerebro_bridge.mensaje_de_resumen(datos)
            estado = "OK"
            preguntas = (datos.get("borrador") or {}).get("preguntas") or []
            acciones = (datos.get("borrador") or {}).get("acciones") or []
            if datos.get("estado") == "REQUIERE_ACLARACION" or preguntas:
                await conversaciones.actualizar_estado(
                    pool,
                    conversacion_id,
                    estado="ESPERANDO_ACLARACION",
                    borrador_id=str(datos.get("borrador_id") or "") or None,
                    preguntas=preguntas,
                )
            elif acciones:
                await conversaciones.actualizar_estado(
                    pool,
                    conversacion_id,
                    estado="ESPERANDO_CONFIRMACION",
                    borrador_id=str(datos.get("borrador_id") or "") or None,
                )
            else:
                await conversaciones.actualizar_estado(
                    pool, conversacion_id, estado="LIBRE"
                )
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
                pool, body.mensaje, actor=actor.nombre, actor_id=actor.actor_id
            )
            cita = resultado.get("cita") or {}
            if resultado.get("estado") == "OK" and cita.get("id"):
                await conversaciones.actualizar_estado(
                    pool,
                    conversacion_id,
                    estado="LIBRE",
                    ultima_cita_id=str(cita["id"]),
                )
            elif resultado.get("estado") != "OK":
                # La creación falló: no dejes apuntando a una cita vieja.
                await conversaciones.actualizar_estado(
                    pool,
                    conversacion_id,
                    estado="LIBRE",
                    limpiar_ultima_cita=True,
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
