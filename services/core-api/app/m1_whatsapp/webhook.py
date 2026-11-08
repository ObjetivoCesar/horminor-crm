"""Modulo 1 - Normalizacion del webhook de Evolution API.

Evolution manda variantes distintas segun la version y el tipo de mensaje.
Aqui se traduce todo a :class:`IncomingMessage`, que es lo unico que conoce el
resto del modulo. Ninguna otra parte del bot sabe como viene el JSON crudo.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .models import IncomingMessage, MediaAttachment

log = logging.getLogger(__name__)

EVENTOS_ACEPTADOS = {
    "messages.upsert",
    "message",
    "MESSAGES_UPSERT",
    "messages.set",
}


def _texto_del_mensaje(mensaje: dict[str, Any]) -> str:
    """Extrae el texto de las variantes conocidas de WhatsApp/Evolution."""
    if not isinstance(mensaje, dict):
        return ""
    for clave in ("conversation",):
        valor = mensaje.get(clave)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    for clave in (
        "extendedTextMessage",
        "imageMessage",
        "videoMessage",
        "documentMessage",
        "templateButtonReplyMessage",
        "buttonsResponseMessage",
        "listResponseMessage",
    ):
        bloque = mensaje.get(clave)
        if not isinstance(bloque, dict):
            continue
        for campo in ("text", "caption", "selectedDisplayText", "title"):
            valor = bloque.get(campo)
            if isinstance(valor, str) and valor.strip():
                return valor.strip()
    # Algunos despliegues mandan la transcripcion del audio ya resuelta.
    for clave in ("transcription", "transcript", "texto"):
        valor = mensaje.get(clave)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    return ""


def _media_del_mensaje(
    mensaje: dict[str, Any], datos: dict[str, Any]
) -> tuple[MediaAttachment, ...]:
    if not isinstance(mensaje, dict):
        return ()
    adjuntos: list[MediaAttachment] = []
    tipos = {
        "imageMessage": ("imagen", "image/jpeg"),
        "videoMessage": ("video", "video/mp4"),
        "audioMessage": ("audio", "audio/ogg"),
        "documentMessage": ("documento", "application/octet-stream"),
        "stickerMessage": ("imagen", "image/webp"),
    }
    base64_crudo = datos.get("base64") or mensaje.get("base64")
    url_cruda = (
        datos.get("mediaUrl")
        or mensaje.get("mediaUrl")
        or datos.get("url")
        or mensaje.get("url")
    )
    for clave, (tipo, mimetype_por_defecto) in tipos.items():
        bloque = mensaje.get(clave)
        if not isinstance(bloque, dict):
            continue
        mimetype = bloque.get("mimetype") or mimetype_por_defecto
        nombre = bloque.get("fileName") or bloque.get("file_name")
        transcripcion = (
            bloque.get("transcription")
            or bloque.get("transcript")
            or datos.get("transcription")
        )
        adjuntos.append(
            MediaAttachment(
                tipo=tipo,
                mimetype=str(mimetype) if mimetype else mimetype_por_defecto,
                nombre=str(nombre) if nombre else None,
                url_origen=str(url_cruda) if url_cruda else None,
                base64=str(base64_crudo) if base64_crudo else None,
                transcripcion=str(transcripcion) if transcripcion else None,
            )
        )
    return tuple(adjuntos)


def normalizar_evento(payload: dict[str, Any]) -> list[IncomingMessage]:
    """Convierte un POST de Evolution en cero o mas mensajes normalizados."""
    if not isinstance(payload, dict):
        return []

    evento = str(payload.get("event") or payload.get("type") or "").strip()
    if evento and evento not in EVENTOS_ACEPTADOS:
        return []

    crudos = payload.get("data")
    if crudos is None:
        crudos = payload.get("messages")
    if isinstance(crudos, dict):
        crudos = [crudos]
    if not isinstance(crudos, list):
        return []

    salida: list[IncomingMessage] = []
    for datos in crudos:
        mensaje = _normalizar_uno(datos)
        if mensaje is not None:
            salida.append(mensaje)
    return salida


def _normalizar_uno(datos: Any) -> IncomingMessage | None:
    if not isinstance(datos, dict):
        return None

    clave = datos.get("key") if isinstance(datos.get("key"), dict) else {}
    if bool(clave.get("fromMe") or datos.get("fromMe")):
        return None  # eco de un mensaje enviado por la propia empresa

    jid = str(
        clave.get("remoteJid")
        or datos.get("remoteJid")
        or datos.get("from")
        or datos.get("chatId")
        or ""
    )
    if not jid:
        return None

    es_grupo = jid.endswith("@g.us")
    telefono = jid
    if es_grupo:
        telefono = str(clave.get("participant") or datos.get("participant") or jid)
    telefono = telefono.split("@", 1)[0]

    mensaje = datos.get("message")
    if not isinstance(mensaje, dict):
        mensaje = datos.get("messages") if isinstance(datos.get("messages"), dict) else {}

    texto = _texto_del_mensaje(mensaje)
    media = _media_del_mensaje(mensaje, datos)
    if not texto and not media:
        return None

    mensaje_id = str(
        clave.get("id")
        or datos.get("id")
        or datos.get("messageId")
        or f"{telefono}-{datetime.now(timezone.utc).timestamp()}"
    )

    momento = _timestamp(
        clave.get("messageTimestamp")
        or datos.get("messageTimestamp")
        or datos.get("timestamp")
    )

    return IncomingMessage(
        mensaje_id=mensaje_id,
        telefono=telefono,
        texto=texto,
        recibido_at=momento,
        media=media,
        nombre_contacto=datos.get("pushName") or datos.get("senderName"),
        es_grupo=es_grupo,
    )


def _timestamp(valor: Any) -> datetime:
    """Evolution manda segundos (int) o milisegundos; se normaliza a UTC."""
    if valor is None:
        return datetime.now(timezone.utc)
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)
    if numero > 10_000_000_000:  # milisegundos
        numero = numero / 1000.0
    if numero <= 0:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(numero, tz=timezone.utc)
