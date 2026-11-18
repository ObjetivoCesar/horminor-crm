"""Espejo de WhatsApp - normalizacion de mensajes de Evolution.

El webhook y el backfill entregan el mismo registro (``key`` + ``message``),
asi que una sola funcion pura los convierte en :class:`MensajeEspejo`.
No se descarta el eco ``fromMe``: el espejo debe ver lo que Julio o
secretaria escriben desde el telefono.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

# Tipos que no son contenido conversacional util para el espejo.
TIPOS_IGNORADOS = (
    "protocolMessage",
    "reactionMessage",
    "senderKeyDistributionMessage",
    "messageContextInfo",
    "keepInChatMessage",
    "pollUpdateMessage",
)

_TIPOS_MEDIA: dict[str, tuple[str, str, str]] = {
    # clave whatsapp: (tipo media, mime por defecto, texto de respaldo)
    "imageMessage": ("IMAGEN", "image/jpeg", "[imagen]"),
    "videoMessage": ("VIDEO", "video/mp4", "[video]"),
    "audioMessage": ("AUDIO", "audio/ogg", "[audio]"),
    "documentMessage": ("DOCUMENTO", "application/octet-stream", "[documento]"),
    "stickerMessage": ("IMAGEN", "image/webp", "[sticker]"),
}

_ESTADOS = {
    "PENDING": "PENDIENTE",
    "SERVER_ACK": "ENVIADO",
    "DELIVERY_ACK": "ENTREGADO",
    "READ": "LEIDO",
    "PLAYED": "LEIDO",
    "ERROR": "FALLIDO",
}

_TEXTO_ALTERNATIVO = (
    "extendedTextMessage",
    "imageMessage",
    "videoMessage",
    "documentMessage",
    "templateButtonReplyMessage",
    "buttonsResponseMessage",
    "listResponseMessage",
)


@dataclass(frozen=True)
class MensajeEspejo:
    """Un mensaje listo para persistir en ``chat_mensajes``."""

    mensaje_id: str
    jid: str
    remote_jid_alt: str | None
    direccion: str  # ENTRANTE | SALIENTE
    cuerpo: str
    enviado_at: datetime
    nombre_contacto: str | None = None
    adjuntos: tuple[dict[str, Any], ...] = ()
    estado_entrega: str = "ENTREGADO"
    from_me: bool = False
    tipo: str | None = None

    @property
    def autor_tipo(self) -> str:
        return "OPERADOR" if self.from_me else "CLIENTE"


def estado_entrega(valor: Any, *, from_me: bool = False) -> str:
    """Traduce el status de Evolution; un valor raro no se adivina.

    El historial de ``findMessages`` no trae ``status``. Para un mensaje
    entrante, el hecho de estar en el hilo ya significa que llego; para uno
    saliente sin estado, el estado real conocido es ENVIADO (no consta
    confirmacion de entrega).
    """
    texto = str(valor or "").strip().upper()
    if not texto:
        return "ENVIADO" if from_me else "ENTREGADO"
    return _ESTADOS.get(texto, "PENDIENTE")


def _timestamp(valor: Any) -> datetime:
    if valor is None:
        return datetime.now(timezone.utc)
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)
    if numero > 10_000_000_000:  # milisegundos
        numero /= 1000.0
    if numero <= 0:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromtimestamp(numero, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return datetime.now(timezone.utc)


def _texto(mensaje: dict[str, Any]) -> str:
    if not isinstance(mensaje, dict):
        return ""
    valor = mensaje.get("conversation")
    if isinstance(valor, str) and valor.strip():
        return valor.strip()
    for clave in _TEXTO_ALTERNATIVO:
        bloque = mensaje.get(clave)
        if not isinstance(bloque, dict):
            continue
        for campo in ("text", "caption", "selectedDisplayText", "title"):
            limpio = bloque.get(campo)
            if isinstance(limpio, str) and limpio.strip():
                return limpio.strip()
    return ""


def _adjuntos(mensaje: dict[str, Any]) -> tuple[tuple[dict[str, Any], ...], str | None]:
    """Describe la multimedia sin descargarla (fase 1: solo texto)."""
    if not isinstance(mensaje, dict):
        return (), None
    salida: list[dict[str, Any]] = []
    respaldo: str | None = None
    for clave, (tipo, mime, etiqueta) in _TIPOS_MEDIA.items():
        bloque = mensaje.get(clave)
        if not isinstance(bloque, dict):
            continue
        salida.append(
            {
                "tipo": tipo,
                "mime": str(bloque.get("mimetype") or mime),
                "nombre": bloque.get("fileName"),
                "bytes": bloque.get("fileLength"),
                "whatsapp_media": clave,
                "pendiente_descarga": True,
            }
        )
        if respaldo is None:
            respaldo = etiqueta
    if isinstance(mensaje.get("locationMessage"), dict):
        respaldo = respaldo or "[ubicación]"
    if isinstance(mensaje.get("contactMessage"), dict):
        respaldo = respaldo or "[contacto]"
    return tuple(salida), respaldo


def desde_registro(registro: Any) -> MensajeEspejo | None:
    """Convierte un registro de Evolution (webhook o findMessages).

    Devuelve ``None`` cuando el registro no es un mensaje util (protocolo,
    reaccion, sin contenido). No decide si el numero esta autorizado: eso lo
    hace el servicio contra la lista blanca.
    """
    if not isinstance(registro, dict):
        return None

    clave = registro.get("key") if isinstance(registro.get("key"), dict) else {}
    mensaje_id = str(clave.get("id") or registro.get("id") or "").strip()
    jid = str(clave.get("remoteJid") or registro.get("remoteJid") or "").strip()
    if not mensaje_id or not jid:
        return None

    mensaje = registro.get("message")
    if not isinstance(mensaje, dict):
        mensaje = {}

    tipo_mensaje = str(registro.get("messageType") or "").strip() or None

    texto = _texto(mensaje)
    adjuntos, respaldo = _adjuntos(mensaje)
    cuerpo = texto or respaldo
    if not cuerpo:
        # Protocolo, reacciones, recibos y demas tramas sin contenido util.
        return None

    from_me = bool(clave.get("fromMe") or registro.get("fromMe"))
    estado = estado_entrega(
        registro.get("status") or clave.get("status"), from_me=from_me
    )

    return MensajeEspejo(
        mensaje_id=mensaje_id,
        jid=jid,
        remote_jid_alt=(
            str(clave.get("remoteJidAlt") or registro.get("remoteJidAlt") or "").strip()
            or None
        ),
        direccion="SALIENTE" if from_me else "ENTRANTE",
        cuerpo=cuerpo,
        enviado_at=_timestamp(
            clave.get("messageTimestamp")
            or registro.get("messageTimestamp")
            or registro.get("timestamp")
        ),
        nombre_contacto=(
            str(registro.get("pushName") or registro.get("senderName") or "").strip()
            or None
        ),
        adjuntos=adjuntos,
        estado_entrega=estado,
        from_me=from_me,
        tipo=tipo_mensaje,
    )


def eventos_del_payload(payload: Any) -> tuple[str, list[dict[str, Any]]]:
    """Devuelve ``("upsert"|"update"|"otro", registros)`` desde el webhook."""
    if not isinstance(payload, dict):
        return "otro", []
    evento = str(payload.get("event") or payload.get("type") or "").strip().lower()
    crudos = payload.get("data")
    if crudos is None:
        crudos = payload.get("messages")
    if isinstance(crudos, dict):
        crudos = [crudos]
    if not isinstance(crudos, list):
        return "otro", []
    registros = [item for item in crudos if isinstance(item, dict)]
    if evento in {"messages.upsert", "messages_upsert", "message", "messages.set"}:
        return "upsert", registros
    if evento in {"messages.update", "messages_update", "message.updated"}:
        return "update", registros
    return "otro", registros
