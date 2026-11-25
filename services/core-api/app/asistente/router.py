"""HTTP del asistente interno. El rol sale de la sesión, nunca del body."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

import asyncpg
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from . import (
    agenda_bridge,
    asuntos_operativos,
    cerebro_bridge,
    comercial_bridge,
    conversaciones,
    memoria,
    razonador,
    recordatorios,
    redactor_historial,
)
from .skills.agenda import AgendaSkill
from .skills.avisos_dinero import PostgresAvisosDinero
from .skills.contrato import (
    EJECUTADA,
    ESPERANDO_CONFIRMACION,
    FALTAN_DATOS,
    NO_PERMITIDO,
    ContextoSkill,
    Puertos,
)
from .skills.cotizaciones_skill import CotizacionesSkill
from .skills.politica import huella_texto
from ..agenda.service import PostgresAgendaStore, ReservaMixerInvalida, plan_reserva_mixer
from ..cerebro.compilador import pide_reserva_mixer
from ..comercial import citas as citas_svc
from ..db import setting
from ..panel_acl import exigir_modulo, resolver_perfil
from ..services import media as media_svc
from ..voz.ingesta import ingestar_audio
from .bibliotecario import Bibliotecario
from .gato import responder_detallado
from .orquestador import Actor, Respuesta
from ..comercial.intencion import _fecha_dicha, _horas_dichas
from .. import tiempo

router = APIRouter(prefix="/api/v1/asistente", tags=["asistente"])
gato_router = APIRouter(prefix="/api/v1/gato", tags=["gato"])


# ---------------------------------------------------------------------------
# Adaptadores de puertos para las skills de Gato (usan el pool de BD directamente)
# ---------------------------------------------------------------------------

class _PoolConfigPort:
    """Lee system_settings desde el pool."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def valor(self, clave: str, defecto: Any = None) -> Any:
        if not isinstance(self._pool, asyncpg.Pool):
            return defecto
        try:
            v = await setting(self._pool, clave)
            return v if v is not None else defecto
        except Exception:
            return defecto


class _PoolCotizacionesPort:
    """Implementa CotizacionesPort contra la BD existente."""

    def __init__(self, pool: asyncpg.Pool, settings: Any = None) -> None:
        self._pool = pool
        self._settings = settings

    async def obtener(self, cotizacion_id: str) -> dict[str, Any] | None:
        if not isinstance(self._pool, asyncpg.Pool):
            return None
        try:
            fila = await self._pool.fetchrow(
                """
                SELECT c.id::text, c.numero, c.estado, c.precio_estado,
                       cl.nombre AS cliente_nombre, cl.telefono AS cliente_telefono
                  FROM cotizaciones c
                  LEFT JOIN clientes cl ON cl.id = c.cliente_id
                 WHERE c.id = $1::uuid
                """,
                cotizacion_id,
            )
            return dict(fila) if fila else None
        except Exception:
            return None

    async def abiertas(
        self, *, ids: Any = None, cliente_id: str | None = None
    ) -> list[dict[str, Any]]:
        if not isinstance(self._pool, asyncpg.Pool):
            return []
        try:
            if ids:
                filas = await self._pool.fetch(
                    "SELECT id::text, numero, estado FROM cotizaciones WHERE id = ANY($1::uuid[]) AND estado NOT IN ('CANCELADA')",
                    [str(i) for i in ids],
                )
            elif cliente_id:
                filas = await self._pool.fetch(
                    "SELECT id::text, numero, estado FROM cotizaciones WHERE cliente_id = $1::uuid AND estado NOT IN ('CANCELADA') ORDER BY creada_en DESC LIMIT 10",
                    cliente_id,
                )
            else:
                return []
            return [dict(f) for f in filas]
        except Exception:
            return []

    async def enviar(
        self,
        cotizacion_id: str,
        *,
        actor: Any,
        telefono_destino: str | None = None,
        destinatario_nombre: str | None = None,
        cuando: datetime | None = None,
        clave_idempotencia: str | None = None,
    ) -> dict[str, Any]:
        from ..services import cotizaciones_envio
        return await cotizaciones_envio.enviar_cotizacion(
            self._pool,
            self._settings,
            cotizacion_id=cotizacion_id,
            actor=actor,
            telefono_destino=telefono_destino,
            destinatario_nombre=destinatario_nombre,
            cuando=cuando,
            clave_idempotencia=clave_idempotencia,
        )

    async def consultar_envio(self, cotizacion_id: str) -> dict[str, Any] | None:
        if not isinstance(self._pool, asyncpg.Pool):
            return None
        try:
            fila = await self._pool.fetchrow(
                """
                SELECT id::text, estado, programado_at
                  FROM gato_recordatorios
                 WHERE cotizacion_id = $1::uuid
                   AND estado IN ('BORRADOR', 'PENDIENTE', 'AGENDADO')
                 ORDER BY creado_en DESC LIMIT 1
                """,
                cotizacion_id,
            )
            return dict(fila) if fila else None
        except Exception:
            return None

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

    mensaje: str = Field(min_length=1, max_length=8010)
    conversacion_id: str | None = Field(default=None, max_length=80)
    client_turn_id: str | None = Field(default=None, max_length=80)


class OperacionAgendaOut(BaseModel):
    tipo: Literal["mixers", "julio", "recordatorios"]
    id: UUID
    fecha: date
    estado: str


class MensajeOut(BaseModel):
    respuesta: str
    estado: str
    conversacion_id: str
    transcripcion: str | None = None
    operacion_agenda: OperacionAgendaOut | None = None


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
    "crear_cotizacion_borrador",
    "reservar_mixer",
    "crear_tarea_recordatorio",
    "crear_tarea_interna",
)


def _accion_a_confirmar(mensaje: str) -> str | None:
    """Que accion del borrador pide ejecutar este mensaje.

    ``*`` significa «la que siga en el borrador»: el usuario dijo solo
    «confirmado». Nunca se ejecuta dinero desde el chat.
    """
    # Un dictado nuevo NO confirma el borrador anterior: es otra instruccion.
    # Sin esta guarda, «enviarle un recordatorio a las 15 y 27» se leia como
    # «confirma el recordatorio pendiente» y consumia el dictado equivocado.
    if cerebro_bridge.es_dictado(mensaje):
        return None
    plano = _plano(mensaje)
    palabras = len(plano.split())
    # «Confírmame el recordatorio de mañana y pásale la factura a Juan por el
    # anticipo de la obra» es una orden nueva, no la ratificacion de un
    # borrador viejo: la confirmacion se dice en pocas palabras.
    if palabras > 10:
        return None
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
    # Respuesta a «¿a qué hora lo envío?»: sigue siendo la misma confirmacion,
    # ahora con el dato que faltaba.
    if _cuando_dictado(mensaje) or _autoriza_envio_ahora(mensaje):
        return "*"
    return None


_RE_ENVIO_AHORA = re.compile(
    r"\b(ahora(?:\s+mismo)?|ya|de\s+una|inmediat\w*|en\s+este\s+momento|"
    r"hoy\s+mismo|al\s+toque)\b"
)


def _autoriza_envio_ahora(mensaje: str) -> bool:
    """El humano dijo que salga ya, no solo «confirmado»."""
    return bool(
        _RE_ENVIO_AHORA.search(recordatorios.normalizar(mensaje or ""))
    )


def _cuando_dictado(mensaje: str) -> str | None:
    """Hora o fecha que el humano dicta al confirmar («a las 15 y 27»).

    Se devuelve el texto tal cual lo dijo: el Cerebro lo vuelve a leer con su
    propio parser al programar y asi queda registrado que la hora la autorizo
    una persona, no una inferencia.
    """
    if recordatorios.parsear_cuando(mensaje or "") is None:
        return None
    return str(mensaje or "").strip() or None


def _mensaje_de_error(codigo: str | None, detalle: Any, mensaje: str) -> str:
    """Traduce la negativa del Cerebro a una frase o a una pregunta util.

    Pegar el JSON crudo en el chat deja al usuario sin saber que hacer; el
    mismo motivo se dice como pregunta cuando falta un dato.
    """
    if isinstance(detalle, dict):
        detalle = detalle.get("message") or detalle.get("detail") or detalle
    if codigo == "CONFIRMAR_ENVIO_INMEDIATO":
        return (
            "El dictado no dijo la hora del envío. ¿Lo mando ahora o a qué hora "
            "lo programo? Ejemplo: «a las 15:27» o «mañana a las 9»."
        )
    if codigo == "MENSAJE_POR_CONFIRMAR":
        return (
            "Lo dictado describe el encargo, no el texto que va a leer la "
            "persona. Dime el mensaje exacto y lo programo."
        )
    if isinstance(detalle, str) and detalle.strip():
        return f"No pude ejecutar la acción: {detalle.strip()}"
    return f"No pude ejecutar la acción: {mensaje}"


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


def _correccion_recordatorio(mensaje: str) -> bool:
    plano = _plano(mensaje)
    if "recordatorio" not in plano:
        return False
    if not any(
        marca in plano
        for marca in ("mueve", "mover", "cambia", "cambiar", "reprograma", "reagenda")
    ):
        return False
    return recordatorios.parsear_cuando(mensaje) is not None


def _cancelacion_recordatorio(mensaje: str) -> bool:
    plano = _plano(mensaje)
    return "recordatorio" in plano and any(
        marca in plano for marca in ("cancela", "cancelar", "anula", "descarta")
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


def _es_ruido_o_saludo(mensaje: str) -> bool:
    """True si el dictado es solo un saludo, agradecimiento o prueba de sonido."""
    limpio = _plano(cerebro_bridge.texto_limpio(mensaje)).strip(".,!?¡¿ ")
    if not limpio:
        return True
    ruido = (
        "hola",
        "gracias",
        "muchas gracias",
        "ok",
        "okay",
        "listo",
        "prueba",
        "prueba de sonido",
        "hola esta es una prueba de sonido",
        "probando",
    )
    if limpio in ruido:
        return True
    if "prueba de sonido" in limpio and len(limpio.split()) <= 8:
        return True
    return False


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
    if _es_ruido_o_saludo(mensaje):
        return None
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


def _estado_del_pedido(borrador: dict[str, Any]) -> str:
    """Presenta el estado registrado por el Cerebro para el pedido activo."""
    ejecutadas = set(borrador.get("ordenes_ejecutadas") or ())
    canceladas = {item["encargo"] for item in borrador.get("encargos_cancelados") or ()}
    etiquetas = {
        "crear_cliente": "Alta del cliente",
        "reservar_mixer": "Reserva de mixer",
        "crear_cotizacion_borrador": "Borrador de cotización",
        "enviar_cotizacion_whatsapp": "Envío de la cotización",
        "crear_tarea_recordatorio": "Programación del recordatorio",
        "crear_tarea_interna": "Registro de la tarea",
        "registrar_abono_cliente": "Registro del anticipo",
        "registrar_traslado_caja_banco": "Traslado al banco",
    }
    lineas = []
    if cliente := borrador.get("cliente_confirmado"):
        lineas.append(f"- Alta del cliente ({cliente}): completada.")
    for accion in borrador.get("acciones") or ():
        nombre = accion.get("accion_nombre")
        etiqueta = etiquetas.get(nombre)
        if not etiqueta:
            continue
        orden = accion.get("orden")
        if orden in ejecutadas:
            estado = "completado"
        elif accion.get("encargo") in canceladas:
            estado = "cancelado"
        else:
            estado = "pendiente"
        if nombre == "crear_cliente":
            cliente = (accion.get("parametros") or {}).get("nombre")
            if cliente:
                etiqueta += f" ({cliente})"
        lineas.append(f"- {etiqueta}: {estado}.")
    preguntas = [item["texto"] for item in borrador.get("preguntas") or () if item.get("texto")]
    if preguntas:
        lineas.extend(["", "Datos pendientes:", *(f"- {texto}" for texto in preguntas)])
    return "\n".join(lineas).strip() or "El borrador aún no tiene acciones registradas."


def _vista_asunto(asunto: razonador.Asunto) -> str:
    datos = asunto.datos or {}
    if asunto.tipo == "visita":
        texto = f"Visita a {datos.get('nombre') or 'un posible cliente'}"
        if datos.get("fecha"):
            texto += f" el {datos['fecha']}"
        if datos.get("hora"):
            texto += f" a las {datos['hora']}"
    else:
        texto = "Recordatorio para ti"
        if datos.get("mensaje"):
            texto += f" para «{datos['mensaje']}»"
        if datos.get("cuando"):
            momento = datetime.fromisoformat(datos["cuando"])
            texto += f" el {momento:%Y-%m-%d} a las {momento:%H:%M}"
            texto += " (hora de Ecuador)"
    if asunto.preguntas:
        return texto + ".\n\n" + "\n".join(asunto.preguntas)
    return texto + ".\n\nResponde «Confirmado» para guardarlo."


def _huella_vista(texto: str) -> str:
    return hashlib.sha256(texto[:memoria.MAX_TEXTO].encode("utf-8")).hexdigest()


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
    actor.texto_actual = body.mensaje
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
                    pool, conversacion_id, estado_dialogo.get("borrador_id")
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

    async def cerrar(
        texto: str, estado: str, operacion_agenda: OperacionAgendaOut | None = None
    ) -> MensajeOut:
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
            respuesta=texto, estado=estado, conversacion_id=conversacion_id,
            operacion_agenda=operacion_agenda,
        )

    es_dictado = cerebro_bridge.es_dictado(body.mensaje)
    if _es_ruido_o_saludo(body.mensaje) and (es_dictado or pendiente):
        return await cerrar("Te escucho." if pendiente else "Dictado recibido.", "OK")

    dicho = _plano(cerebro_bridge.texto_limpio(body.mensaje)).strip(" .?!¿¡")
    asuntos = razonador.asuntos_guardados(estado_dialogo)
    foco = estado_dialogo.get("foco_asunto")
    # Los borradores abiertos anteriores a este cambio se incorporan al
    # primer seguimiento, sin perder la referencia que ya vio el usuario.
    if not asuntos and pendiente and estado_dialogo.get("borrador_id") and texto_previo:
        anterior = estado_dialogo["borrador_id"]
        tipo = "encargo"
        foco = anterior
        asuntos[foco] = razonador.Asunto(
            tipo, razonador.NOMBRES[tipo], estado_dialogo["estado"], anterior,
            tuple(p["texto"] for p in estado_dialogo.get("preguntas") or () if p.get("texto")),
        )
    decision = await razonador.decidir(
        body.mensaje, asuntos, foco=foco, rol=actor.rol, historial=historial,
    ) if memoria_activa else razonador.Decision("legado")
    if decision.modo == "aclarar":
        return await cerrar(decision.pregunta or "¿A qué pedido te refieres?", "FALTA")
    asunto_id = decision.asunto
    asunto = asuntos.get(asunto_id or "")
    ultima_respuesta = next((
        turno["content"] for turno in reversed(historial) if turno["role"] == "assistant"
    ), "")
    huella = (asunto.datos or {}).get("vista_confirmada") if asunto else None
    ratificacion_visible = bool(huella and huella == _huella_vista(ultima_respuesta))
    if decision.modo == "confirmar" and (
        not ratificacion_visible
        or dicho not in {"confirmado", "confirmo", "si", "dale", "hazlo", "crealo"}
    ):
        if asunto:
            texto = f"¿Confirmas «{asunto.etiqueta}»? Responde «Confirmado» para autorizar el paso mostrado."
            asunto = replace(asunto, datos={**(asunto.datos or {}), "vista_confirmada": _huella_vista(texto)})
            await conversaciones.actualizar_estado(
                pool, conversacion_id, estado=asunto.estado, borrador_id=asunto.borrador_id,
                asunto_id=asunto_id, asunto=asunto.a_dict(),
            )
            return await cerrar(texto, "FALTA")

    if asunto and asunto.borrador_id:
        texto_previo = await conversaciones.texto_ultimo_borrador(
            pool, conversacion_id, asunto.borrador_id,
        )
        estado_dialogo = {
            **estado_dialogo, "borrador_id": asunto.borrador_id, "estado": asunto.estado,
        }
        pendiente = asunto.estado != "LIBRE"

    async def guardar_asunto(
        identificador: str, registro: razonador.Asunto, *, vista: str | None = None, **cambios: Any,
    ) -> None:
        registro = replace(registro, actualizado_en=tiempo.iso())
        if vista and registro.estado == "ESPERANDO_CONFIRMACION":
            registro = replace(registro, datos={**(registro.datos or {}), "vista_confirmada": _huella_vista(vista)})
        kwargs = {
            "estado": registro.estado, "borrador_id": registro.borrador_id,
            "asunto_id": identificador, "asunto": registro.a_dict(), **cambios,
        }
        await conversaciones.actualizar_estado(pool, conversacion_id, **kwargs)

    if decision.modo == "estado" and asunto:
        if asunto.borrador_id:
            borrador = await cerebro_bridge.obtener_borrador(
                asunto.borrador_id, usuario=actor.actor_id, rol=actor.rol, nombre=actor.nombre,
            )
            return await cerrar(_estado_del_pedido(borrador), "OK")
        datos = asunto.datos or {}
        if datos.get("cita_id"):
            cita = await citas_svc.obtener(pool, datos["cita_id"])
            if cita:
                estado_cita = str(cita["estado"])
                return await cerrar(
                    f"Visita del {cita['fecha']} a las {cita['hora_inicio']} · {estado_cita}.",
                    "OK", OperacionAgendaOut(
                        tipo="julio", id=cita["id"], fecha=cita["fecha"], estado=estado_cita,
                    ),
                )
            return await cerrar("La visita ya no está disponible en Agenda.", "FALTA")
        if datos.get("recordatorio_id"):
            recordatorio = await pool.fetchrow(
                "SELECT estado, programado_at FROM gato_recordatorios WHERE id = $1::uuid AND creado_por = $2",
                datos["recordatorio_id"], actor.actor_id,
            )
            if recordatorio:
                if recordatorio["estado"] == "AGENDADO":
                    momento = recordatorio["programado_at"].astimezone(tiempo.ZONA)
                    return await cerrar(
                        f"Tu recordatorio está agendado el {momento:%Y-%m-%d} a las {momento:%H:%M}.",
                        "OK", OperacionAgendaOut(
                            tipo="recordatorios", id=datos["recordatorio_id"],
                            fecha=momento.date(), estado=recordatorio["estado"],
                        ),
                    )
                return await cerrar(f"Estado del recordatorio: {recordatorio['estado']}.", "OK")
            return await cerrar("El recordatorio ya no está disponible en el programador.", "FALTA")
        if datos.get("resultado"):
            return await cerrar(datos["resultado"], "OK")
        return await cerrar(_vista_asunto(asunto), "OK")

    visita = decision.tipo == "visita"
    recordatorio_personal = decision.tipo == "recordatorio" and (
        bool(asunto and (asunto.datos or {}).get("personal"))
        or bool(decision.datos and decision.datos.personal)
    )
    if memoria_activa and (visita or recordatorio_personal) and decision.modo in (
        "nuevo", "continuar", "confirmar",
    ):
        asunto_id = asunto_id or str(uuid4())
        datos = (asunto.datos or {}) if asunto else {}
        try:
            if decision.modo != "confirmar" or not asunto:
                literal = cerebro_bridge.texto_limpio(body.mensaje)
                if visita:
                    await exigir_modulo(request, "clientes_cartera", mutacion=True)
                    registro = await asuntos_operativos.preparar_visita(
                        pool, literal, decision.datos or razonador.DatosTurno(), datos,
                    )
                else:
                    registro = asuntos_operativos.preparar_recordatorio(
                        decision.datos or razonador.DatosTurno(), datos,
                    )
                    registro.datos["personal"] = True
                    await exigir_modulo(request, "cerebro", mutacion=True)
                    registro.datos.pop("telefono", None)
                vista = _vista_asunto(registro)
                await guardar_asunto(asunto_id, registro, vista=vista)
                return await cerrar(vista, "FALTA" if registro.preguntas else "OK")
            if asunto.estado != "ESPERANDO_CONFIRMACION":
                return await cerrar(datos.get("resultado") or _vista_asunto(asunto), "OK")
            if visita:
                await exigir_modulo(request, "clientes_cartera", mutacion=True)
                texto_visita = datos["motivo"]
                resultado = await comercial_bridge.agendar(
                    pool, texto_visita, actor=actor.nombre, actor_id=actor.actor_id,
                    datos_confirmados={**datos, "fecha": date.fromisoformat(datos["fecha"])},
                    clave_gato=asunto_id, rol=actor.rol,
                )
                if resultado["estado"] != "OK":
                    return await cerrar(resultado["mensaje"], "FALTA")
                cita = resultado["cita"]
                texto = resultado["mensaje"]
                registro = replace(asunto, estado="LIBRE", datos={**datos, "resultado": texto, "cita_id": str(cita["id"])})
                await guardar_asunto(asunto_id, registro, ultima_cita_id=str(cita["id"]))
                return await cerrar(texto, "OK", OperacionAgendaOut(
                    tipo="julio", id=cita["id"], fecha=cita["fecha"], estado=cita["estado"],
                ))
            await exigir_modulo(request, "cerebro", mutacion=True)
            if datetime.fromisoformat(datos["cuando"]) <= tiempo.ahora():
                registro = replace(
                    asunto, estado="ESPERANDO_ACLARACION",
                    preguntas=("Esa hora ya pasó. ¿A qué hora quieres el recordatorio?",),
                    datos={k: v for k, v in datos.items() if k not in {"hora", "cuando"}},
                )
                await guardar_asunto(asunto_id, registro)
                return await cerrar(registro.preguntas[0], "FALTA")
            resultado = await recordatorios.agendar_personal(
                pool, actor=actor, asunto_id=asunto_id, mensaje=datos["mensaje"],
                cuando=datetime.fromisoformat(datos["cuando"]),
            )
            texto = resultado.nota or "Estado del recordatorio no disponible."
            if not resultado.ok:
                return await cerrar(texto, "FALTA")
            await guardar_asunto(asunto_id, replace(
                asunto, estado="LIBRE",
                datos={**datos, "resultado": texto, "recordatorio_id": resultado.datos["id"]},
            ))
            return await cerrar(texto, "OK", OperacionAgendaOut(
                tipo="recordatorios", id=resultado.datos["id"], fecha=resultado.datos["fecha"],
                estado=resultado.datos["estado"],
            ))
        except (HTTPException, ValueError) as exc:
            return await cerrar(str(getattr(exc, "detail", exc)), "FALTA")

    pide_estado_mixer = bool(re.search(r"\b(?:ya reservaste|quedo reservado|esta reservado)\b", dicho))
    pide_confirmar_mixer = bool(re.fullmatch(
        r"(?:te digo que reserves|reserva(?:lo)? (?:el |los )?mixers?|"
        r"confirma (?:la )?reserva(?: (?:del|de los) mixers?)?)", dicho
    ))
    borrador_activo = estado_dialogo.get("borrador_id")
    if memoria_activa and decision.modo == "legado" and not asuntos and pide_estado_mixer and borrador_activo:
        reserva_id = await pool.fetchval(
            """
            SELECT entidad_destino_id::text FROM cerebro_ejecuciones
             WHERE borrador_id = $1::uuid AND accion_nombre = 'reservar_mixer'
               AND estado = 'EXITOSO'
             ORDER BY ejecutado_en DESC LIMIT 1
            """, borrador_activo,
        )
        fila = await PostgresAgendaStore(pool).obtener(reserva_id) if reserva_id else None
        if fila and fila["estado"] not in ("CANCELADO", "REAGENDADO"):
            return await cerrar(
                f"Reserva en Agenda el {fila['fecha_entrega']} a las {fila['hora_inicio']}.",
                "OK", OperacionAgendaOut(
                    tipo="mixers", id=fila["id"], fecha=fila["fecha_entrega"], estado=fila["estado"]
                ),
            )
        return await cerrar("El pedido todavía no tiene una reserva activa en Agenda.", "OK")

    if memoria_activa and decision.modo == "legado" and not asuntos and re.fullmatch(
        r"(?:que paso|(?:ya )?registraste|(?:ya )?(?:lo )?creaste|(?:ya )?creaste el cliente"
        r"|quedo registrado|ya quedo)", dicho
    ):
        if not borrador_activo:
            return await cerrar("Todavía no hay un borrador activo en esta conversación.", "OK")
        borrador = await cerebro_bridge.obtener_borrador(
            borrador_activo, usuario=actor.actor_id, rol=actor.rol, nombre=actor.nombre,
        )
        return await cerrar(_estado_del_pedido(borrador), "OK")

    iniciar_reserva_pendiente = False
    continuar_reserva = bool(
        pendiente and texto_previo and pide_reserva_mixer(texto_previo)
        and not pide_confirmar_mixer
        and (_es_continuacion(dicho) or (
            len(dicho.split()) <= 16
            and (_horas_dichas(dicho) or _fecha_dicha(dicho, tiempo.hoy()) or dicho.startswith("la direccion"))
        ))
    )

    ultima_cita_id = str(estado_dialogo.get("ultima_cita_id") or "").strip() or None

    # Mixer: crear, mover o cancelar desde el chat. Es la pestana Mixers.
    if decision.modo == "legado" and agenda_bridge.es_cancelacion_mixer(body.mensaje):
        try:
            resultado = await agenda_bridge.cancelar_ultimo(
                pool,
                body.mensaje,
                actor=actor.nombre,
                actor_id=actor.actor_id,
            )
            return await cerrar(
                str(resultado.get("mensaje") or "Listo."),
                "OK" if resultado.get("estado") == "OK" else "FALTA",
            )
        except Exception as exc:  # noqa: BLE001
            return await cerrar(f"No pude cancelar el mixer: {exc}", "ERROR")
    if decision.modo == "legado" and agenda_bridge.es_correccion_mixer(body.mensaje):
        try:
            resultado = await agenda_bridge.reagendar_ultimo(
                pool,
                body.mensaje,
                actor=actor.nombre,
                actor_id=actor.actor_id,
            )
            return await cerrar(
                str(resultado.get("mensaje") or "Listo."),
                "OK" if resultado.get("estado") == "OK" else "FALTA",
            )
        except Exception as exc:  # noqa: BLE001
            return await cerrar(f"No pude mover el mixer: {exc}", "ERROR")

    nota_mixer = ""
    _plano_msg = _plano(body.mensaje)
    _es_dictado_negocio = cerebro_bridge.es_dictado(body.mensaje) and (
        "mixer" not in _plano_msg
        or any(
            k in _plano_msg
            for k in ("hormigon", "cliente", "cotizacion", "resistencia")
        )
    )
    if (
        decision.modo == "legado" and not _es_dictado_negocio and not continuar_reserva
        and not (pendiente and pide_confirmar_mixer)
        and agenda_bridge.es_peticion_mixer(body.mensaje)
    ):
        try:
            resultado = await agenda_bridge.crear(
                pool,
                body.mensaje,
                actor=actor.nombre,
                actor_id=actor.actor_id,
                rol=actor.rol,
            )
            if resultado.get("estado") != "OK":
                return await cerrar(
                    str(resultado.get("mensaje") or "No pude agendar el mixer."),
                    "FALTA",
                )
            nota_mixer = str(resultado.get("mensaje") or "")
            # Una accion por mensaje: el mixer ya quedo. Si el mismo dictado
            # pide un recordatorio, se prepara aparte para no mezclar cifras.
            if "recordatorio" in _plano(body.mensaje):
                nota_mixer += (
                    "\n\nEl recordatorio lo preparo en el siguiente mensaje: "
                    "dime el texto exacto y la hora."
                )
            reserva = resultado["agenda"]
            return await cerrar(
                nota_mixer, "OK",
                OperacionAgendaOut(
                    tipo="mixers", id=reserva["id"], fecha=reserva["fecha_entrega"],
                    estado=reserva["estado"],
                ),
            )
        except Exception as exc:  # noqa: BLE001
            return await cerrar(f"No pude agendar el mixer: {exc}", "ERROR")

    # Recordatorio: mover o cancelar sin depender del LLM.
    if decision.modo == "legado" and _correccion_recordatorio(body.mensaje):
        resultado = await recordatorios.actualizar(
            Bibliotecario(pool),
            actor=actor,
            cuando=body.mensaje,
        )
        return await cerrar(
            resultado.nota or "Recordatorio movido.",
            "OK" if resultado.estado == "OK" else "FALTA",
        )
    if decision.modo == "legado" and _cancelacion_recordatorio(body.mensaje):
        actual = await recordatorios.ultimo_de(Bibliotecario(pool), actor=actor)
        if actual is None:
            return await cerrar(
                "No hay un recordatorio pendiente que pueda cancelar.", "VACIO"
            )
        resultado = await recordatorios.cancelar(
            Bibliotecario(pool),
            actor=actor,
            recordatorio_id=str(actual["id"]),
        )
        return await cerrar(
            resultado.nota or "Recordatorio cancelado.",
            "OK" if resultado.estado == "OK" else "FALTA",
        )

    # Tarea interna: mover el plazo o cancelarla (pestana Equipo).
    if decision.modo == "legado" and agenda_bridge.es_correccion_tarea(body.mensaje):
        try:
            resultado = await agenda_bridge.reprogramar_tarea(
                pool,
                body.mensaje,
                actor=actor.nombre,
                actor_id=actor.actor_id,
                rol=actor.rol,
            )
            return await cerrar(
                str(resultado.get("mensaje") or "Listo."),
                "OK" if resultado.get("estado") == "OK" else "FALTA",
            )
        except Exception as exc:  # noqa: BLE001
            return await cerrar(f"No pude mover la tarea: {exc}", "ERROR")
    if decision.modo == "legado" and agenda_bridge.es_cancelacion_tarea(body.mensaje):
        try:
            resultado = await agenda_bridge.cancelar_tarea(
                pool,
                body.mensaje,
                actor=actor.nombre,
                actor_id=actor.actor_id,
                rol=actor.rol,
            )
            return await cerrar(
                str(resultado.get("mensaje") or "Listo."),
                "OK" if resultado.get("estado") == "OK" else "FALTA",
            )
        except Exception as exc:  # noqa: BLE001
            return await cerrar(f"No pude cancelar la tarea: {exc}", "ERROR")

    # Correccion de una cita recien agendada: «rectifico, no es a la 13:00
    # sino a las 14:00». Se resuelve antes del puente para que no responda
    # «no tengo herramienta».
    if decision.modo == "legado" and _correccion_de_cita(body.mensaje, pendiente):
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

    if decision.modo == "legado" and _cancelacion_de_cita(body.mensaje, pendiente):
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
    objetivo = "reservar_mixer" if pide_confirmar_mixer and pendiente else _accion_a_confirmar(body.mensaje)
    if decision.modo == "confirmar":
        objetivo = "*"
    elif decision.modo != "legado" or asuntos:
        objetivo = None
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
                ejecutadas = set(draft.get("ordenes_ejecutadas") or ())
                cancelados = {
                    int(item.get("encargo") or 1)
                    for item in draft.get("encargos_cancelados") or ()
                }
                acciones = [
                    item for item in sorted(
                        draft.get("acciones") or [], key=lambda a: int(a.get("orden") or 0)
                    )
                    if item.get("orden") not in ejecutadas
                    and int(item.get("encargo") or 1) not in cancelados
                ]
                listas = [
                    item for item in acciones
                    if item.get("accion_nombre") in _ACCIONES_CONFIRMABLES
                    and (objetivo == "*" or item.get("accion_nombre") == objetivo)
                    and not item.get("bloqueada_por")
                    and (not item.get("depende_de_orden") or item["depende_de_orden"] in ejecutadas)
                ]
                if len({item.get("encargo", 1) for item in listas}) > 1:
                    return await cerrar(
                        "Hay varios encargos listos. Indica cuál quieres confirmar o elígelo en Cerebro.",
                        "FALTA",
                    )
                accion = listas[0] if listas else None
                if accion is None and decision.modo == "confirmar" and objetivo != "reservar_mixer":
                    return await cerrar(_estado_del_pedido(draft), "FALTA")
                if objetivo == "reservar_mixer" and accion is None:
                    preguntas = [p.get("texto") for p in draft.get("preguntas") or []
                                 if str(p.get("clave") or "").startswith(("cotizacion.", "cliente."))]
                    reserva_propuesta = any(
                        item.get("accion_nombre") == "reservar_mixer" for item in acciones
                    )
                    if texto_previo and not reserva_propuesta and not pide_reserva_mixer(texto_previo):
                        iniciar_reserva_pendiente = True
                    else:
                        return await cerrar(
                            " ".join(filter(None, preguntas))
                            or "Confirma primero el alta del cliente del pedido.",
                            "FALTA",
                        )
                if accion is not None:
                    parametros = accion.get("parametros") or {}
                    mensaje_final = None
                    enviar_ahora = False
                    cuando_dictado = None
                    if accion.get("accion_nombre") == "crear_tarea_recordatorio":
                        mensaje_final = str(parametros.get("mensaje") or "").strip() or None
                        # Lo que el humano autoriza en este mismo turno: el
                        # texto exacto, la hora y si sale ya. Sin esto, el
                        # chat no tenia como responder al Cerebro y el guard
                        # devolvia siempre el mismo 422.
                        enviar_ahora = _autoriza_envio_ahora(body.mensaje)
                        cuando_dictado = _cuando_dictado(body.mensaje)
                        if (
                            parametros.get("mensaje_por_confirmar")
                            and not mensaje_final
                            and not recordatorios.es_afirmacion(body.mensaje)
                            and not recordatorios.es_negacion(body.mensaje)
                            and len(_plano(body.mensaje).split()) > 2
                            and not cuando_dictado
                        ):
                            # El humano está dictando el texto que leerá la
                            # persona: eso es exactamente lo que faltaba.
                            mensaje_final = body.mensaje.strip()
                    resultado = await cerebro_bridge.confirmar_accion(
                        borrador_id,
                        int(accion.get("orden") or 1),
                        usuario=actor.actor_id,
                        rol=actor.rol,
                        nombre=actor.nombre,
                        mensaje_final=mensaje_final,
                        enviar_ahora=enviar_ahora,
                        cuando=cuando_dictado,
                    )
                    datos = resultado.get("datos") or {}
                    texto = str(resultado.get("nota") or "Accion ejecutada.")
                    if (
                        accion.get("accion_nombre") == "crear_cliente"
                        and datos.get("nombre")
                        and "cliente" not in texto.lower()
                    ):
                        texto = f"Cliente creado: {datos['nombre']}."
                    if any(item.get("accion_nombre") == "reservar_mixer" for item in acciones
                           if item is not accion):
                        texto += "\n\nLa reserva de mixer sigue pendiente."
                    operacion = None
                    if accion.get("accion_nombre") == "reservar_mixer" and datos.get("id"):
                        operacion = OperacionAgendaOut(
                            tipo="mixers", id=datos["id"],
                            fecha=parametros["fecha_entrega"], estado="RESERVA_CAMPO",
                        )
                    preguntas_pendientes = int(resultado.get("preguntas_pendientes") or 0)
                    if preguntas_pendientes:
                        estado_siguiente = "ESPERANDO_ACLARACION"
                    elif resultado.get("estado_borrador") == "EJECUTADO":
                        estado_siguiente = "LIBRE"
                    else:
                        estado_siguiente = "ESPERANDO_CONFIRMACION"
                        restantes = {a["accion_nombre"] for a in acciones if a is not accion}
                        if restantes.intersection(_ACCIONES_CONFIRMABLES):
                            siguiente = next(
                                a for a in acciones
                                if a is not accion and a["accion_nombre"] in _ACCIONES_CONFIRMABLES
                            )
                            texto += (
                                "\n\nSiguiente paso: " + siguiente["accion_nombre"].replace("_", " ") + "."
                                " Responde «Confirmado» para autorizarlo."
                            )
                        elif "enviar_cotizacion_whatsapp" in restantes:
                            texto += "\n\nAbre la cotización en el panel para revisar el envío por WhatsApp."
                    if asunto_id and asunto:
                        await guardar_asunto(asunto_id, replace(asunto, estado=estado_siguiente), vista=texto)
                    else:
                        await conversaciones.actualizar_estado(
                            pool, conversacion_id, estado=estado_siguiente, borrador_id=borrador_id,
                        )
                    return await cerrar(texto, "OK", operacion)
            except HTTPException as exc:
                codigo = None
                if isinstance(exc.detail, dict):
                    codigo = str(exc.detail.get("code") or "") or None
                texto = _mensaje_de_error(codigo, exc.detail, str(exc.detail))
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

    # El razonador elige el asunto. El prefijo sigue disponible para el
    # dictado libre y para clientes que llaman directamente a este endpoint.
    retomar_pedido = (
        decision.modo == "legado" and (
            continuar_reserva or iniciar_reserva_pendiente
            or bool(pendiente and texto_previo and re.match(r"^(?:te dije|ya te dije)\b", dicho))
        )
    )
    if decision.modo == "consulta":
        respuesta = await responder_detallado(
            body.mensaje, actor.rol, biblio, actor.nombre, historial=historial,
            actor_id=actor.actor_id, conversacion_id=conversacion_id,
            modo_envio=actor.modo_envio, solo_lectura=True,
        )
        return await cerrar(respuesta.texto, respuesta.estado)
    puente = "cerebro" if retomar_pedido or decision.modo in ("nuevo", "continuar") else _puente(body.mensaje)
    # ------------------------------------------------------------------ #
    # Skill de cotizaciones: envío por WhatsApp desde Gato                #
    # Solo intercepta cuando YA existe una cotización en BD para este     #
    # asunto/borrador (o cuando se está confirmando un envío ya           #
    # preparado). Si aún no existe cotización, pasa al Cerebro para       #
    # crear primero el cliente/borrador/cotización.                       #
    # ------------------------------------------------------------------ #
    _plano_msg = _plano(body.mensaje)
    _es_envio_cotizacion = (
        memoria_activa
        and (decision.tipo == "cotizacion" or (asunto is not None and asunto.tipo == "cotizacion"))
        and decision.modo in ("nuevo", "continuar", "confirmar")
        and (
            (decision.modo == "confirmar" and asunto is not None and asunto.estado == "ESPERANDO_CONFIRMACION" and bool((asunto.datos or {}).get("cotizacion_id")))
            or any(
                marca in _plano_msg
                for marca in ("envia", "enviale", "mandale", "manda", "enviar", "mandar")
            )
        )
    )
    if _es_envio_cotizacion:
        _borrador_id_sk = (asunto.borrador_id if asunto else None) or estado_dialogo.get("borrador_id")
        _hilo_cots: tuple[str, ...] = ()
        if _borrador_id_sk and isinstance(pool, asyncpg.Pool):
            _hilo_cots = tuple(
                str(r["id"])
                for r in await pool.fetch(
                    "SELECT id::text FROM cotizaciones WHERE borrador_id = $1::text ORDER BY creada_en DESC LIMIT 5",
                    str(_borrador_id_sk),
                )
            )
        _cot_dep = (asunto.datos or {}).get("cotizacion_id") if asunto else None
        if _hilo_cots or _cot_dep:
            try:
                await exigir_modulo(request, "cotizaciones", mutacion=True)
            except HTTPException:
                pass
            else:
                _settings_sk = getattr(request.app.state, "settings", None)
                _puertos = Puertos(
                    config=_PoolConfigPort(pool),
                    cotizaciones=_PoolCotizacionesPort(pool, _settings_sk),
                    avisos_dinero=PostgresAvisosDinero(pool) if isinstance(pool, asyncpg.Pool) else None,
                )
                _ctx_sk = ContextoSkill(
                    actor=actor,
                    asunto_id=asunto_id or str(uuid4()),
                    puertos=_puertos,
                    accion={},
                    borrador_id=_borrador_id_sk,
                    datos=dict(asunto.datos or {}) if asunto else {},
                    cliente_nombre=(asunto.datos or {}).get("nombre") if asunto else None,
                    cotizaciones_hilo=_hilo_cots,
                    cotizacion_dependencia=_cot_dep,
                    sandbox=_modo_envio(request) != "evolution",
                )
                _skill_cot = CotizacionesSkill()
                if decision.modo == "confirmar" and asunto and asunto.estado == "ESPERANDO_CONFIRMACION":
                    _huella_confirmar = huella_texto(
                        actor.actor_id, "enviar_cotizacion", dict(asunto.datos or {})
                    )
                    from .skills.contrato import Autorizacion
                    _res = await _skill_cot.ejecutar_envio(
                        _ctx_sk,
                        Autorizacion(actor_id=actor.actor_id, rol=actor.rol, huella=_huella_confirmar),
                    )
                    if _res.estado == EJECUTADA:
                        if asunto_id:
                            await guardar_asunto(
                                asunto_id,
                                replace(asunto, estado="LIBRE", datos={**(asunto.datos or {}), "resultado": _res.nota}),
                            )
                        return await cerrar(_res.nota, "OK")
                    return await cerrar(_res.nota, "ERROR")
                _prep = await _skill_cot.preparar_envio(_ctx_sk)
                if _prep.estado == ESPERANDO_CONFIRMACION:
                    _sid = asunto_id or str(uuid4())
                    _datos_asunto = {
                        **dict(asunto.datos or {} if asunto else {}),
                        **dict(_prep.parametros),
                        "vista_confirmada": _huella_vista(_prep.vista),
                    }
                    await guardar_asunto(
                        _sid,
                        razonador.Asunto(
                            "cotizacion",
                            f"Envío cotización {_prep.parametros.get('cotizacion_id', '')[:8]}",
                            "ESPERANDO_CONFIRMACION",
                            _borrador_id_sk,
                            (),
                            _datos_asunto,
                        ),
                        vista=_prep.vista,
                    )
                    return await cerrar(_prep.vista, "FALTA")
                if _prep.estado in (FALTAN_DATOS, NO_PERMITIDO):
                    return await cerrar(_prep.motivo or _prep.vista or "No pude preparar el envío.", "FALTA")

    if puente == "cerebro":
        try:
            if decision.modo == "continuar" and asunto and asunto.borrador_id and not texto_previo:
                return await cerrar("El borrador cambió. Abre el pedido en Cerebro para revisar su versión vigente.", "FALTA")
            contexto = texto_previo if decision.modo == "continuar" or retomar_pedido else None
            if decision.modo == "legado" and not retomar_pedido and not asuntos:
                contexto = _contexto_dictado(
                    historial, body.mensaje, texto_previo=texto_previo,
                    pendiente=estado_dialogo.get("estado") == "ESPERANDO_ACLARACION",
                )
            padre = asunto.borrador_id if asunto and contexto else None
            intencion_tarea = (
                (decision.datos.accion_tarea if decision.datos else None)
                or ((asunto.datos or {}).get("accion_tarea") if asunto else None)
            )
            datos = await cerebro_bridge.interpretar(
                "dictado: reserva el mixer" if iniciar_reserva_pendiente
                else body.mensaje if es_dictado else f"dictado: {body.mensaje}",
                usuario=actor.actor_id,
                rol=actor.rol,
                nombre=actor.nombre,
                contexto=contexto,
                **({"borrador_previo_id": padre} if padre else {}),
                **({"intencion_tarea": intencion_tarea} if intencion_tarea else {}),
                conversacion_id=conversacion_id,
            )
            texto = cerebro_bridge.mensaje_de_resumen(datos)
            estado = "OK"
            preguntas = (datos.get("borrador") or {}).get("preguntas") or []
            acciones = (datos.get("borrador") or {}).get("acciones") or []
            if cliente_confirmado := datos.get("cliente_confirmado"):
                texto += f"\n\n{cliente_confirmado} ya está registrado para este pedido."
            primer_paso = acciones[0].get("accion_nombre") if acciones else None
            solo_bloqueo_de_envio = primer_paso == "crear_cotizacion_borrador" and all(
                p.get("clave") == "cotizacion.precio_estado" for p in preguntas
            )
            puede_confirmar = primer_paso in _ACCIONES_CONFIRMABLES and (
                not preguntas or solo_bloqueo_de_envio
            )
            if puede_confirmar:
                paso = "preparar la cotización" if primer_paso == "crear_cotizacion_borrador" else (
                    primer_paso.replace("_", " ")
                )
                texto += f"\n\nResponde «Confirmado» para autorizar el siguiente paso: {paso}."
            if any(a.get("accion_nombre") == "enviar_cotizacion_whatsapp" for a in acciones):
                texto += "\n\nEl envío por WhatsApp se revisa desde Cotizaciones cuando el documento esté listo."
            for accion in acciones:
                if accion.get("accion_nombre", accion.get("nombre")) != "reservar_mixer":
                    continue
                parametros = accion["parametros"]
                try:
                    _, cargas = await plan_reserva_mixer(
                        pool, fecha=date.fromisoformat(parametros["fecha_entrega"]),
                        hora=parametros["hora_inicio"],
                        volumen=Decimal(str(parametros["volumen_m3"])),
                        unidades=parametros.get("unidades"),
                    )
                    unidades = ", ".join(item["codigo"] for item, _ in cargas)
                    texto += f"\n\nHay cupo en Agenda con {unidades}. Confirma para guardar la reserva."
                except ReservaMixerInvalida as exc:
                    texto += f"\n\n{exc}"
            if memoria_activa and datos.get("borrador_id") and (preguntas or acciones):
                tipo = decision.tipo or (asunto.tipo if asunto else "encargo")
                nombre_cliente = next((
                    h.get("valor") for h in reversed(datos.get("hechos") or [])
                    if h.get("clave") == "cliente.nombre" and h.get("valor")
                    and h.get("estado") in ("EXTRAIDO", "CORREGIDO_EN_AUDIO", "CORREGIDO_POR_HUMANO")
                ), None)
                etiqueta = razonador.NOMBRES[tipo]
                if nombre_cliente:
                    etiqueta += f" de {nombre_cliente}"
                elif asunto:
                    etiqueta = asunto.etiqueta
                estado_asunto = (
                    "ESPERANDO_CONFIRMACION" if puede_confirmar or not preguntas
                    else "ESPERANDO_ACLARACION"
                )
                await guardar_asunto(
                    asunto_id or str(datos["borrador_id"]),
                    razonador.Asunto(
                        tipo, etiqueta, estado_asunto, str(datos["borrador_id"]),
                        tuple(p["texto"] for p in preguntas if p.get("texto")),
                        {"accion_tarea": intencion_tarea} if intencion_tarea else None,
                    ),
                    vista=texto,
                    preguntas=preguntas,
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
                OperacionAgendaOut(
                    tipo="julio", id=cita["id"], fecha=cita["fecha"], estado=cita["estado"]
                ) if resultado.get("estado") == "OK" and cita.get("id") else None,
            )
        except Exception as exc:  # noqa: BLE001
            return await cerrar(f"No pude agendar: {exc}", "ERROR")

    respuesta = await _respuesta_con_ratificacion(
        body.mensaje, actor, biblio, historial
    )
    if nota_mixer:
        respuesta = Respuesta(
            nota_mixer + "\n\n" + respuesta.texto,
            respuesta.estado,
            respuesta.resultados,
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
    if len(texto) > 8000:
        raise HTTPException(
            status_code=422, detail="El audio supera el límite de 8.000 caracteres. Divide el dictado en dos turnos."
        )
    salida = await chat(
        MensajeIn(
            mensaje=mensaje,
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
        operacion_agenda=salida.operacion_agenda,
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
