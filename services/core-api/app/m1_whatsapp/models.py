"""Modulo 1 - Contratos de datos del motor de comunicaciones.

Todo lo de este archivo es puro: no toca base de datos, Redis ni red. Asi se
puede probar el comportamiento sin levantar infraestructura.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

MODULO = "m1_whatsapp"


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
class Rol(str, Enum):
    """Roles ratificados 2026-11-08 para el router de identidad."""

    SUPERADMIN = "SUPERADMIN"
    CAJA_SECRETARIA = "CAJA_SECRETARIA"
    BODEGA_PLANTA = "BODEGA_PLANTA"
    CHOFER_MIXER = "CHOFER_MIXER"
    CLIENTE = "CLIENTE"
    LEAD_DESCONOCIDO = "LEAD_DESCONOCIDO"

    @classmethod
    def desde_texto(cls, valor: Any) -> "Rol | None":
        """Normaliza un rol escrito en base de datos."""
        texto = str(valor or "").strip().upper().replace(" ", "_")
        alias = {
            "BODEGUERO": cls.BODEGA_PLANTA,
            "BODEGA": cls.BODEGA_PLANTA,
            "CHOFER": cls.CHOFER_MIXER,
            "SECRETARIA": cls.CAJA_SECRETARIA,
            "CAJA": cls.CAJA_SECRETARIA,
            "CLIENTE_ACTIVO": cls.CLIENTE,
            "CLIENTE": cls.CLIENTE,
            "GERENCIA": cls.SUPERADMIN,
            "ADMIN": cls.SUPERADMIN,
            "LEAD": cls.LEAD_DESCONOCIDO,
            "PROSPECTO": cls.LEAD_DESCONOCIDO,
        }
        if texto in alias:
            return alias[texto]
        try:
            return cls(texto)
        except ValueError:
            return None


# ---------------------------------------------------------------------------
# Normalizacion de telefonos (convencion de formato, no dato de negocio)
# ---------------------------------------------------------------------------
def normalizar_telefono(valor: Any) -> str:
    """Deja un telefono comparable: solo digitos, sin 0 inicial ni prefijo 593.

    Ejemplos (Ecuador): ``+593 99 123 4567``, ``0991234567`` y ``593991234567``
    producen todos ``991234567``.
    """
    digitos = re.sub(r"\D", "", str(valor or ""))
    if not digitos:
        return ""
    while digitos.startswith("00"):
        digitos = digitos[2:]
    if digitos.startswith("593") and len(digitos) > 9:
        digitos = digitos[3:]
    if digitos.startswith("0") and len(digitos) > 9:
        digitos = digitos[1:]
    return digitos


def formato_whatsapp(valor: Any) -> str:
    """Devuelve el telefono como lo espera Evolution: digitos con codigo de pais.

    Ecuador: ``0991234567``, ``991234567``, ``+593 99 123 4567`` y
    ``00593991234567`` producen todos ``593991234567``. Si el formato no es
    reconocible, devuelve los digitos tal cual: no inventa un pais.
    """
    digitos = re.sub(r"\D", "", str(valor or ""))
    if not digitos:
        return ""
    while digitos.startswith("00"):
        digitos = digitos[2:]
    if digitos.startswith("593"):
        return digitos
    if digitos.startswith("0") and len(digitos) in (9, 10):
        return "593" + digitos[1:]
    if len(digitos) == 9:
        return "593" + digitos
    return digitos


def normalizar_codigo_mixer(valor: Any) -> str:
    """Normaliza el codigo de un mixer a la forma ``MIXER-01``.

    Es una convencion de formato para comparar ``#M1``, ``M1``, ``mixer 1`` y
    ``MIXER-01`` contra ``system_settings.flota.mixers``. No inventa flota:
    si el mixer no existe en la configuracion, el viaje no se resuelve.
    """
    texto = str(valor or "").strip().upper()
    if not texto:
        return ""
    coincidencia = re.search(r"(\d{1,3})", texto)
    if not coincidencia:
        return texto
    return f"MIXER-{int(coincidencia.group(1)):02d}"


# ---------------------------------------------------------------------------
# Referencias dentro del mensaje (#104, V2, #M1)
# ---------------------------------------------------------------------------
_PREFIJO_MIXER = re.compile(r"#\s*M\s*(\d{1,3})\b", re.IGNORECASE)
_PREFIJO_ORDEN = re.compile(r"#\s*(?:ORD(?:EN)?[-\s]?)?(\d{1,9})\b", re.IGNORECASE)
_PREFIJO_VIAJE = re.compile(r"\bV\s*(\d{1,4})\b", re.IGNORECASE)


@dataclass(frozen=True)
class ReferenciaViaje:
    """Pistas de destinatario que el remitente escribe en el mensaje."""

    orden_numero: int | None = None
    viaje_numero: int | None = None
    mixer_codigo: str | None = None

    @property
    def vacia(self) -> bool:
        return (
            self.orden_numero is None
            and self.viaje_numero is None
            and self.mixer_codigo is None
        )


def extraer_referencia(texto: str | None) -> ReferenciaViaje:
    """Extrae ``#<orden>``, ``V<n>`` y ``#M<n>`` del texto.

    Regla documentada: el mensaje puede apuntar explicitamente a una orden o a
    un viaje; si no lo hace, el pipeline usa el siguiente viaje pendiente de la
    orden activa mas reciente.
    """
    crudo = texto or ""
    mixer = _PREFIJO_MIXER.search(crudo)
    orden = _PREFIJO_ORDEN.search(crudo)
    viaje = _PREFIJO_VIAJE.search(crudo)
    return ReferenciaViaje(
        orden_numero=int(orden.group(1)) if orden else None,
        viaje_numero=int(viaje.group(1)) if viaje else None,
        mixer_codigo=normalizar_codigo_mixer(mixer.group(1)) if mixer else None,
    )


# ---------------------------------------------------------------------------
# Mensajes
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MediaAttachment:
    """Adjunto recibido por WhatsApp (imagen, video, audio o documento)."""

    tipo: str  # imagen | video | audio | documento
    mimetype: str | None = None
    nombre: str | None = None
    url_origen: str | None = None
    base64: str | None = None
    transcripcion: str | None = None

    def a_dict(self) -> dict[str, Any]:
        return {
            "tipo": self.tipo,
            "mimetype": self.mimetype,
            "nombre": self.nombre,
            "url_origen": self.url_origen,
            "base64": self.base64,
            "transcripcion": self.transcripcion,
        }

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> "MediaAttachment":
        return cls(
            tipo=str(datos.get("tipo") or "documento"),
            mimetype=datos.get("mimetype"),
            nombre=datos.get("nombre"),
            url_origen=datos.get("url_origen"),
            base64=datos.get("base64"),
            transcripcion=datos.get("transcripcion"),
        )

    def extension(self) -> str:
        """Extension de archivo derivada del mimetype (sin datos de negocio)."""
        mapa = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            "video/mp4": "mp4",
            "video/3gpp": "3gp",
            "audio/ogg": "ogg",
            "audio/mpeg": "mp3",
            "audio/mp4": "m4a",
            "application/pdf": "pdf",
        }
        if self.mimetype and self.mimetype.lower() in mapa:
            return mapa[self.mimetype.lower()]
        if self.nombre and "." in self.nombre:
            return self.nombre.rsplit(".", 1)[-1][:5].lower()
        return "bin"


@dataclass(frozen=True)
class IncomingMessage:
    """Mensaje normalizado, independiente del formato de Evolution API."""

    mensaje_id: str
    telefono: str
    texto: str = ""
    recibido_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    media: tuple[MediaAttachment, ...] = ()
    nombre_contacto: str | None = None
    es_grupo: bool = False

    @property
    def telefono_normalizado(self) -> str:
        return normalizar_telefono(self.telefono)

    def texto_util(self) -> str:
        """Texto + transcripciones de audio: lo que ve el Juez Binario."""
        partes = [self.texto or ""]
        for adjunto in self.media:
            if adjunto.transcripcion:
                partes.append(adjunto.transcripcion)
        return " ".join(p for p in partes if p).strip()

    def a_json(self) -> str:
        return json.dumps(
            {
                "mensaje_id": self.mensaje_id,
                "telefono": self.telefono,
                "texto": self.texto,
                "recibido_at": self.recibido_at.isoformat(),
                "media": [m.a_dict() for m in self.media],
                "nombre_contacto": self.nombre_contacto,
                "es_grupo": self.es_grupo,
            },
            ensure_ascii=False,
        )

    @classmethod
    def desde_json(cls, crudo: str | bytes) -> "IncomingMessage":
        datos = json.loads(crudo)
        fecha = datos.get("recibido_at")
        return cls(
            mensaje_id=str(datos["mensaje_id"]),
            telefono=str(datos.get("telefono") or ""),
            texto=datos.get("texto") or "",
            recibido_at=(
                datetime.fromisoformat(fecha)
                if fecha
                else datetime.now(timezone.utc)
            ),
            media=tuple(
                MediaAttachment.desde_dict(m) for m in datos.get("media") or []
            ),
            nombre_contacto=datos.get("nombre_contacto"),
            es_grupo=bool(datos.get("es_grupo", False)),
        )


@dataclass(frozen=True)
class MessageBatch:
    """Grupo de mensajes del mismo remitente tras la ventana de silencio."""

    telefono: str
    mensajes: tuple[IncomingMessage, ...]

    @property
    def texto(self) -> str:
        """Texto concatenado del lote, tal como lo analiza el Juez Binario."""
        return " ".join(m.texto_util() for m in self.mensajes if m.texto_util()).strip()

    @property
    def ultimo_id(self) -> str:
        return self.mensajes[-1].mensaje_id if self.mensajes else ""

    @property
    def nombre_contacto(self) -> str | None:
        for mensaje in self.mensajes:
            if mensaje.nombre_contacto:
                return mensaje.nombre_contacto
        return None

    @property
    def media(self) -> tuple[MediaAttachment, ...]:
        return tuple(a for m in self.mensajes for a in m.media)

    @property
    def recibido_at(self) -> datetime:
        return self.mensajes[-1].recibido_at if self.mensajes else datetime.now(timezone.utc)


def normalizar_texto(texto: str | None) -> str:
    """Minusculas sin acentos: base de los jueces deterministicos."""
    crudo = unicodedata.normalize("NFKD", texto or "")
    sin_acentos = "".join(c for c in crudo if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_acentos).strip().lower()
