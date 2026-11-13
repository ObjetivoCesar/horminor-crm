"""Recordatorios de Gato: la parte en la que deja de solo consultar y actua.

Un recordatorio es una fila en `gato_recordatorios`: destino, mensaje y hora.
Nace en **BORRADOR**: Gato lo lee de vuelta en el chat y solo pasa a
**PENDIENTE** cuando Julio o Secretaria ratifican con un "si". El despachador
(`despachador.py`) envia lo ratificado cuando llega la hora.

Reglas duras:
- Nada se agenda sin ratificacion explicita.
- El mensaje lo dicta el usuario; no se completa por cuenta propia.
- El telefono sale de `clients.telefono_whatsapp`. Si el cliente no lo tiene,
  no se crea nada. Un numero dictado se acepta, pero queda marcado como
  `DICTADO` para que nadie lo confunda con un dato del CRM.
- `programado_at` se guarda en UTC; `zona` es solo para mostrar.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from ..m1_whatsapp.models import formato_whatsapp
from .bibliotecario import Bibliotecario
from .fichas import Resultado

log = logging.getLogger(__name__)

ZONA_DEFECTO = "America/Guayaquil"
MAX_INTENTOS = 3
ROLES_ESCRITURA = ("SUPERADMIN", "SECRETARIA")

AFIRMACIONES = {
    "si", "s", "dale", "ok", "okay", "confirmo", "confirmado", "confirmalo",
    "correcto", "de acuerdo", "adelante", "hazlo", "mandalo", "envialo",
    "programalo", "yes",
}
NEGACIONES = {
    "no", "nop", "nel", "cancela", "cancelalo", "descarta", "descartalo",
    "mejor no", "dejalo", "olvidalo",
}

_RE_HORA_COMPLETA = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_RE_HORA_AMPM = re.compile(r"\b(\d{1,2})\s*(am|pm)\b")
_RE_A_LAS = re.compile(r"\ba\s+las?\s+(\d{1,2})\b(?!:)(?:\s*(am|pm))?")
_RE_EN = re.compile(r"\ben\s+(\d+)\s*(minuto|minutos|hora|horas|dia|dias)\b")
_RE_AHORA = re.compile(
    r"\b(ahora(?:\s+mismo)?|ya|de\s+una|en\s+este\s+momento|inmediat\w*|"
    r"cuanto\s+antes|a\s+la\s+brevedad)\b"
)
_RE_TELEFONO = re.compile(r"^\+?\d{7,15}$")
_RE_MANANA_HORA = re.compile(r"(?:de|por|en)\s+la\s+manana")
_RE_DESTINATARIO = re.compile(
    r"\b(?:al|a\s+la|a)\s+"
    r"([A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ.'\- ]+?)"
    r"(?=\s*(?:\ba\s+las?\b|\bma[nñ]ana\b|\bhoy\b|\ben\s+\d|\by\b|\bque\b|\bpara\b|,|$))",
    re.IGNORECASE,
)
_RE_MENSAJE = re.compile(
    r"(?:record[aá]rle|recu[eé]rdale|recordar|recu[eé]rde(?:me)?|"
    r"avis[aá]le|avis[aá]rle|notif[ií]cale|notif[ií]carle|"
    r"com[eé]ntale|p[ií]dele|solic[ií]tale|p[aá]sale|"
    r"dec[ií]rle|dile|que\s+diga)\s+que\s+(.+)$",
    re.IGNORECASE,
)
_RE_FACTURA = re.compile(
    r"\b(?:p[aá]sale|env[ií]ale|adjunta(?:le|r)?|m[aá]ndale|incluye)\b"
    r"[^.]{0,40}\bfactura\b",
    re.IGNORECASE,
)


def normalizar(texto: str) -> str:
    base = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in base if unicodedata.category(c) != "Mn")


def zona_local(nombre: str | None = None) -> ZoneInfo:
    for candidato in ((nombre or "").strip(), ZONA_DEFECTO):
        if not candidato:
            continue
        try:
            return ZoneInfo(candidato)
        except Exception:  # zona invalida en configuracion
            continue
    return ZoneInfo("UTC")


def ahora_local(zona: ZoneInfo | None = None) -> datetime:
    return datetime.now(timezone.utc).astimezone(zona or zona_local())


def es_afirmacion(texto: str) -> bool:
    t = normalizar(texto).strip(" .!¡?¿,")
    if t in AFIRMACIONES:
        return True
    return t.startswith(("si ", "dale ", "confirm", "ok ")) and len(t.split()) <= 3


def es_negacion(texto: str) -> bool:
    t = normalizar(texto).strip(" .!¡?¿,")
    if t in NEGACIONES:
        return True
    if t.startswith("no ") and len(t.split()) <= 3:
        return True
    return t.startswith(("cancela", "descarta", "olvidalo", "dejalo"))


def _con_sufijo(hora: int, sufijo: str | None) -> tuple[int, int]:
    sufijo = (sufijo or "").lower()
    if sufijo == "pm" and hora < 12:
        hora += 12
    if sufijo == "am" and hora == 12:
        hora = 0
    return hora, 0


def _hora(texto: str) -> tuple[int, int] | None:
    """Hora declarada en la frase. Si hay varias, toma la ultima.

    La ultima es la del recordatorio: en "la cita es a las 18:40 y recuerdame
    a las 17:00" manda 17:00.
    """
    completas = _RE_HORA_COMPLETA.findall(texto)
    if completas:
        hora, minuto = completas[-1]
        return int(hora), int(minuto)

    ampm = _RE_HORA_AMPM.findall(texto)
    if ampm:
        hora, sufijo = ampm[-1]
        return _con_sufijo(int(hora), sufijo)

    a_las = _RE_A_LAS.findall(texto)
    if a_las:
        crudo, sufijo = a_las[-1]
        hora = int(crudo)
        if sufijo:
            return _con_sufijo(hora, sufijo)
        if _RE_MANANA_HORA.search(texto) or "de la madrugada" in texto:
            return hora, 0
        if "de la tarde" in texto or "de la noche" in texto:
            return (hora % 12) + 12, 0
        # 1..7 sin sufijo se leen como tarde/noche; 8..23 como tal.
        return (hora + 12 if 1 <= hora <= 7 else hora), 0
    return None


def parsear_cuando(valor: str, ahora: datetime | None = None) -> datetime | None:
    """Devuelve el instante en UTC o None si la frase no trae hora.

    Acepta ISO 8601 (lo que manda el LLM) y frases: "a las 18:40",
    "manana a las 9", "a las 7 de la manana", "en 30 minutos", "a las 6 pm".
    """
    if not valor:
        return None
    crudo = str(valor).strip()
    ahora = ahora or ahora_local()
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=zona_local())

    try:
        iso = datetime.fromisoformat(crudo.replace("Z", "+00:00"))
        if iso.tzinfo is None:
            iso = iso.replace(tzinfo=ahora.tzinfo)
        return iso.astimezone(timezone.utc)
    except ValueError:
        pass

    texto = normalizar(crudo)

    if _RE_AHORA.search(texto):
        return (ahora + timedelta(seconds=30)).astimezone(timezone.utc)

    m = _RE_EN.search(texto)
    if m:
        cantidad = int(m.group(1))
        unidad = m.group(2)
        if unidad.startswith("minuto"):
            delta = timedelta(minutes=cantidad)
        elif unidad.startswith("hora"):
            delta = timedelta(hours=cantidad)
        else:
            delta = timedelta(days=cantidad)
        return (ahora + delta).astimezone(timezone.utc)

    hora = _hora(texto)
    if hora is None:
        return None

    h, minuto = hora
    if not (0 <= h <= 23 and 0 <= minuto <= 59):
        return None

    base = ahora.replace(hour=h, minute=minuto, second=0, microsecond=0)
    # "de la manana" es hora, no dia: se descarta antes de buscar el dia.
    texto_dia = _RE_MANANA_HORA.sub(" ", texto)
    if "pasado manana" in texto_dia:
        base += timedelta(days=2)
    elif "manana" in texto_dia:
        base += timedelta(days=1)
    elif "hoy" not in texto_dia and base <= ahora:
        # "a las 18:40" dicho a las 20:00 es para manana, no para ayer.
        base += timedelta(days=1)
    return base.astimezone(timezone.utc)


def extraer_destinatario(texto: str) -> str | None:
    m = _RE_DESTINATARIO.search(str(texto or ""))
    if not m:
        return None
    nombre = m.group(1).strip(" .,")
    if not nombre or normalizar(nombre) in {"gato", "ti", "mi", "el", "la"}:
        return None
    return nombre


def extraer_mensaje(texto: str) -> str | None:
    m = _RE_MENSAJE.search(str(texto or ""))
    if not m:
        return None
    mensaje = m.group(1).strip(" .")
    return mensaje or None


def interpretar(texto: str, ahora: datetime | None = None) -> dict[str, Any]:
    """Lectura best-effort de una orden en lenguaje natural."""
    normal = normalizar(texto)
    return {
        "destinatario": extraer_destinatario(texto),
        "mensaje": extraer_mensaje(texto),
        "cuando": parsear_cuando(texto, ahora),
        "adjuntar_factura": bool(_RE_FACTURA.search(normal)),
    }


def _ahora_texto(momento: datetime, zona: ZoneInfo) -> str:
    return momento.astimezone(zona).strftime("%d/%m/%Y %H:%M")


def _aviso_modo(modo: str | None) -> str:
    """Evita que 'Confirmado' se lea como 'ya le llego al cliente'."""
    if str(modo or "").strip().upper() in {"SANDBOX", "MEMORIA", "NO_CONFIGURADO"}:
        return (
            "\n\nModo SANDBOX: en local el mensaje queda en el outbox del panel; "
            "no sale a un teléfono real."
        )
    return ""


def _etiqueta(nombre: str | None, telefono: str) -> str:
    return nombre or telefono


def _ratificacion(
    *,
    etiqueta: str,
    telefono: str,
    origen: str,
    mensaje: str,
    programado: datetime,
    zona: ZoneInfo,
    adjunto: str | None = None,
    adjunto_ficticio: bool = False,
) -> str:
    aviso = (
        " Ojo: ese número no está registrado en el CRM."
        if origen == "DICTADO"
        else ""
    )
    if adjunto:
        prueba = (
            " (documento de prueba; no es comprobante del SRI)"
            if adjunto_ficticio
            else ""
        )
        aviso += f" Va con la factura {adjunto} adjunta{prueba}."
    return (
        f"Voy a enviar a {etiqueta} ({telefono}) el "
        f"{_ahora_texto(programado, zona)} ({zona}): «{mensaje}».{aviso}\n"
        "Responde «sí» para programarlo o «no» para descartarlo."
    )


async def _resolver_destino(
    biblio: Bibliotecario, destinatario: str
) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    """(telefono, cliente_id, nombre, origen, error)."""
    limpio = (destinatario or "").strip()
    if not limpio:
        return None, None, None, None, (
            "Necesito el nombre del cliente o el número con código de país."
        )
    if _RE_TELEFONO.fullmatch(limpio.replace(" ", "")):
        return formato_whatsapp(limpio), None, None, "DICTADO", None

    encontrados = await biblio.buscar_clientes(limpio, limite=5)
    filas = encontrados.get("datos") or []
    if not filas:
        return None, None, None, None, f"No encontré un cliente que coincida con «{limpio}»."
    if len(filas) > 1:
        nombres = ", ".join(str(f["nombre"]) for f in filas)
        return None, None, None, None, f"Hay varios clientes: {nombres}. ¿A cuál?"

    fila = filas[0]
    datos = await biblio.pool.fetchrow(
        "SELECT id, nombre, telefono_whatsapp FROM clients WHERE id = $1",
        fila["id"],
    )
    if datos is None:
        return None, None, None, None, "El cliente no está disponible."
    telefono = (datos["telefono_whatsapp"] or "").strip()
    if not telefono:
        return (
            None,
            None,
            str(datos["nombre"]),
            None,
            (
                f"{datos['nombre']} no tiene teléfono registrado en el CRM. "
                "Cárgalo antes de programar el mensaje."
            ),
        )
    return formato_whatsapp(telefono), str(datos["id"]), str(datos["nombre"]), "CRM", None


async def _resolver_factura(
    biblio: Bibliotecario, referencia: str | None
) -> tuple[str | None, str | None, bool, str | None]:
    """(media_id, numero, es_ficticia, error) de la factura mas reciente."""
    if not referencia:
        return None, None, False, (
            "¿De qué cliente es la factura? Necesito el nombre."
        )
    encontrados = await biblio.buscar_clientes(referencia, limite=5)
    filas = encontrados.get("datos") or []
    if not filas:
        return None, None, False, (
            f"No encontré el cliente «{referencia}» para la factura."
        )
    if len(filas) > 1:
        nombres = ", ".join(str(f["nombre"]) for f in filas)
        return None, None, False, f"Hay varios clientes: {nombres}. ¿De cuál es la factura?"

    fila = await biblio.pool.fetchrow(
        """
        SELECT f.numero, f.media_id, f.es_ficticia
          FROM client_invoices f
          JOIN media_assets m ON m.id = f.media_id
         WHERE f.cliente_id = $1 AND f.media_id IS NOT NULL
         ORDER BY f.fecha DESC, f.created_at DESC
         LIMIT 1
        """,
        filas[0]["id"],
    )
    if fila is None:
        return None, None, False, (
            f"{filas[0]['nombre']} no tiene una factura adjunta en el CRM."
        )
    return str(fila["media_id"]), str(fila["numero"]), bool(fila["es_ficticia"]), None


def _clave_idempotencia(
    actor_id: str,
    conversacion_id: str | None,
    telefono: str,
    mensaje: str,
    programado: datetime,
) -> str:
    base = "|".join(
        [
            actor_id,
            conversacion_id or "",
            telefono,
            mensaje.strip(),
            programado.astimezone(timezone.utc).isoformat(),
        ]
    )
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


async def crear(
    biblio: Bibliotecario,
    *,
    actor: Any,
    destinatario: str,
    mensaje: str,
    cuando: str,
    conversacion_id: str | None = None,
    zona: str = ZONA_DEFECTO,
    adjuntar_factura: bool = False,
    factura_de: str | None = None,
) -> Resultado:
    if getattr(actor, "rol", "") not in ROLES_ESCRITURA:
        return Resultado(
            "recordatorio_crear",
            "ACL",
            nota="Tu perfil no puede programar mensajes a clientes.",
        )

    actor_id = str(getattr(actor, "actor_id", "") or "")
    if not actor_id or actor_id == "panel":
        return Resultado(
            "recordatorio_crear",
            "FALTA_PARAMETRO",
            parametro_faltante="usuario",
            nota=(
                "No sé quién lo pide: falta el usuario de la sesión. "
                "Vuelve a entrar al panel."
            ),
        )

    cuerpo = (mensaje or "").strip()
    if not cuerpo:
        return Resultado(
            "recordatorio_crear",
            "FALTA_PARAMETRO",
            parametro_faltante="mensaje",
            nota="¿Qué le digo al cliente? Necesito el texto exacto.",
        )

    zona_obj = zona_local(zona)
    programado = parsear_cuando(cuando, ahora_local(zona_obj))
    if programado is None:
        return Resultado(
            "recordatorio_crear",
            "FALTA_PARAMETRO",
            parametro_faltante="cuando",
            nota="¿A qué hora lo envío? Ejemplo: 18:40 o mañana a las 9:00.",
        )

    telefono, cliente_id, nombre, origen, error = await _resolver_destino(
        biblio, destinatario
    )
    if error:
        estado = "FALTA_PARAMETRO" if ("No encontré" in error or "varios" in error) else "VACIO"
        return Resultado(
            "recordatorio_crear",
            estado,
            nota=error,
            parametro_faltante="destinatario" if estado == "FALTA_PARAMETRO" else None,
        )

    media_id: str | None = None
    factura_numero: str | None = None
    factura_ficticia = False
    if adjuntar_factura:
        referencia = factura_de or (nombre if cliente_id else None)
        media_id, factura_numero, factura_ficticia, error_factura = (
            await _resolver_factura(biblio, referencia)
        )
        if error_factura:
            return Resultado(
                "recordatorio_crear",
                "FALTA_PARAMETRO",
                parametro_faltante="factura",
                nota=error_factura,
            )

    conversacion = conversacion_id or getattr(actor, "conversacion_id", None)
    clave = _clave_idempotencia(actor_id, conversacion, telefono, cuerpo, programado)

    fila = await biblio.pool.fetchrow(
        """
        INSERT INTO gato_recordatorios (
            creado_por, rol_actor, conversacion_id, cliente_id,
            destinatario_nombre, telefono, mensaje, programado_at, zona,
            estado, origen_destino, clave_idempotencia, media_id
        )
        VALUES ($1, $2, $3::uuid, $4::uuid, $5, $6, $7, $8, $9,
                'BORRADOR', $10, $11, $12::uuid)
        ON CONFLICT (clave_idempotencia) WHERE clave_idempotencia IS NOT NULL
        DO NOTHING
        RETURNING id, destinatario_nombre, telefono, mensaje, programado_at,
                  origen_destino
        """,
        actor_id,
        getattr(actor, "rol", ""),
        conversacion,
        cliente_id,
        nombre,
        telefono,
        cuerpo,
        programado,
        str(zona_obj),
        origen,
        clave,
        media_id,
    )

    if fila is None:
        fila = await biblio.pool.fetchrow(
            """
            SELECT id, destinatario_nombre, telefono, mensaje, programado_at,
                   origen_destino
              FROM gato_recordatorios
             WHERE clave_idempotencia = $1
            """,
            clave,
        )
        if fila is None:
            return Resultado(
                "recordatorio_crear", "ERROR", nota="No pude guardar el recordatorio."
            )

    etiqueta = _etiqueta(fila["destinatario_nombre"], fila["telefono"])
    nota = _ratificacion(
        etiqueta=etiqueta,
        telefono=fila["telefono"],
        origen=fila["origen_destino"],
        mensaje=fila["mensaje"],
        programado=fila["programado_at"],
        zona=zona_obj,
        adjunto=factura_numero,
        adjunto_ficticio=factura_ficticia,
    ) + _aviso_modo(getattr(actor, "modo_envio", ""))
    return Resultado(
        "recordatorio_crear",
        "OK",
        datos={
            "id": str(fila["id"]),
            "destinatario": etiqueta,
            "telefono": fila["telefono"],
            "origen_destino": fila["origen_destino"],
            "mensaje": fila["mensaje"],
            "adjunto": factura_numero,
            "programado_at": fila["programado_at"].astimezone(timezone.utc).isoformat(),
            "programado_local": _ahora_texto(fila["programado_at"], zona_obj),
            "estado": "BORRADOR",
        },
        fuente=["gato_recordatorios"],
        filtros={"telefono": fila["telefono"]},
        nota=nota,
    )


async def pendiente_de(biblio: Bibliotecario, *, actor: Any) -> dict[str, Any] | None:
    """Borrador mas reciente del actor en su conversacion, si existe."""
    fila = await biblio.pool.fetchrow(
        """
        SELECT id, destinatario_nombre, telefono, mensaje, programado_at,
               origen_destino
          FROM gato_recordatorios
         WHERE estado = 'BORRADOR'
           AND creado_por = $1
           AND ($2::uuid IS NULL OR conversacion_id = $2::uuid)
         ORDER BY created_at DESC
         LIMIT 1
        """,
        str(getattr(actor, "actor_id", "") or ""),
        getattr(actor, "conversacion_id", None),
    )
    return dict(fila) if fila else None


async def confirmar(
    biblio: Bibliotecario, *, actor: Any, recordatorio_id: str | None = None
) -> Resultado:
    pendiente = None
    if recordatorio_id:
        pendiente = await biblio.pool.fetchrow(
            """
            SELECT id, programado_at FROM gato_recordatorios
             WHERE id = $1::uuid AND estado = 'BORRADOR'
            """,
            recordatorio_id,
        )
    if pendiente is None:
        actual = await pendiente_de(biblio, actor=actor)
        if actual is None:
            return Resultado(
                "recordatorio_confirmar",
                "VACIO",
                nota="No hay ningún mensaje pendiente de tu confirmación.",
            )
        recordatorio_id = str(actual["id"])
        pendiente = {"programado_at": actual["programado_at"], "id": actual["id"]}

    ahora = datetime.now(timezone.utc)
    tarde = pendiente["programado_at"] < ahora

    fila = await biblio.pool.fetchrow(
        """
        UPDATE gato_recordatorios
           SET estado = 'PENDIENTE',
               confirmado_por = $2,
               confirmado_at = now(),
               programado_at = GREATEST(programado_at, now()),
               updated_at = now()
         WHERE id = $1::uuid AND estado = 'BORRADOR'
        RETURNING id, destinatario_nombre, telefono, mensaje, programado_at
        """,
        recordatorio_id,
        str(getattr(actor, "actor_id", "") or ""),
    )
    if fila is None:
        return Resultado(
            "recordatorio_confirmar",
            "VACIO",
            nota="Ese recordatorio ya no está pendiente de confirmación.",
        )

    zona_obj = zona_local()
    etiqueta = _etiqueta(fila["destinatario_nombre"], fila["telefono"])
    nota = (
        f"Confirmado: a {etiqueta} le llega «{fila['mensaje']}» el "
        f"{_ahora_texto(fila['programado_at'], zona_obj)}."
    )
    if tarde:
        nota += " La hora ya había pasado, así que sale en el próximo tick."
    nota += _aviso_modo(getattr(actor, "modo_envio", ""))
    return Resultado(
        "recordatorio_confirmar",
        "OK",
        datos={
            "id": str(fila["id"]),
            "destinatario": etiqueta,
            "telefono": fila["telefono"],
            "mensaje": fila["mensaje"],
            "programado_local": _ahora_texto(fila["programado_at"], zona_obj),
            "estado": "PENDIENTE",
        },
        fuente=["gato_recordatorios"],
        filtros={"id": recordatorio_id},
        nota=nota,
    )


async def descartar(
    biblio: Bibliotecario, *, actor: Any, recordatorio_id: str | None = None
) -> Resultado:
    objetivo = recordatorio_id
    if objetivo is None:
        actual = await pendiente_de(biblio, actor=actor)
        if actual is None:
            return Resultado(
                "recordatorio_descartar",
                "VACIO",
                nota="No hay ningún mensaje pendiente de tu confirmación.",
            )
        objetivo = str(actual["id"])

    fila = await biblio.pool.fetchrow(
        """
        UPDATE gato_recordatorios
           SET estado = 'CANCELADO', updated_at = now()
         WHERE id = $1::uuid
           AND estado = 'BORRADOR'
           AND (creado_por = $2 OR $3 = 'SUPERADMIN')
        RETURNING id, destinatario_nombre, telefono
        """,
        objetivo,
        str(getattr(actor, "actor_id", "") or ""),
        getattr(actor, "rol", ""),
    )
    if fila is None:
        return Resultado(
            "recordatorio_descartar",
            "VACIO",
            nota="Ese mensaje ya no estaba pendiente.",
        )
    return Resultado(
        "recordatorio_descartar",
        "OK",
        datos={"id": str(fila["id"])},
        fuente=["gato_recordatorios"],
        filtros={"id": objetivo},
        nota=(
            f"Descartado. No se enviará nada a "
            f"{_etiqueta(fila['destinatario_nombre'], fila['telefono'])}."
        ),
    )


async def listar(
    biblio: Bibliotecario,
    *,
    actor: Any,
    incluir_historicos: bool = False,
    limite: int = 20,
) -> Resultado:
    where = "" if incluir_historicos else "WHERE estado IN ('BORRADOR', 'PENDIENTE')"
    filas = await biblio.pool.fetch(
        f"""
        SELECT id, destinatario_nombre, telefono, mensaje, programado_at,
               estado, intentos, enviado_at
          FROM gato_recordatorios
          {where}
         ORDER BY programado_at ASC
         LIMIT $1
        """,
        max(1, min(int(limite or 20), 100)),
    )
    datos = [
        {
            "id": str(f["id"]),
            "destinatario": _etiqueta(f["destinatario_nombre"], f["telefono"]),
            "telefono": f["telefono"],
            "mensaje": f["mensaje"],
            "programado_local": _ahora_texto(f["programado_at"], zona_local()),
            "estado": f["estado"],
            "intentos": f["intentos"],
        }
        for f in filas
    ]
    if not datos:
        return Resultado(
            "recordatorio_listar",
            "VACIO",
            fuente=["gato_recordatorios"],
            nota="No hay recordatorios pendientes.",
        )
    return Resultado(
        "recordatorio_listar",
        "OK",
        datos=datos,
        fuente=["gato_recordatorios"],
        filtros={"estado": "TODOS" if incluir_historicos else "BORRADOR+PENDIENTE"},
    )


async def cancelar(biblio: Bibliotecario, *, actor: Any, recordatorio_id: str) -> Resultado:
    fila = await biblio.pool.fetchrow(
        """
        UPDATE gato_recordatorios
           SET estado = 'CANCELADO', updated_at = now()
         WHERE id = $1::uuid
           AND estado IN ('BORRADOR', 'PENDIENTE')
           AND (creado_por = $2 OR $3 = 'SUPERADMIN')
        RETURNING id, destinatario_nombre, telefono, programado_at
        """,
        recordatorio_id,
        str(getattr(actor, "actor_id", "") or ""),
        getattr(actor, "rol", ""),
    )
    if fila is None:
        saliendo = await biblio.pool.fetchrow(
            "SELECT estado FROM gato_recordatorios WHERE id = $1::uuid",
            recordatorio_id,
        )
        if saliendo is not None and saliendo["estado"] == "ENVIANDO":
            return Resultado(
                "recordatorio_cancelar",
                "ERROR",
                nota="Ese mensaje ya está saliendo; no se puede cancelar.",
            )
        return Resultado(
            "recordatorio_cancelar",
            "VACIO",
            nota="No encontré ese recordatorio pendiente, o no es tuyo.",
        )
    return Resultado(
        "recordatorio_cancelar",
        "OK",
        datos={
            "id": str(fila["id"]),
            "destinatario": _etiqueta(fila["destinatario_nombre"], fila["telefono"]),
            "programado_local": _ahora_texto(fila["programado_at"], zona_local()),
        },
        fuente=["gato_recordatorios"],
        filtros={"id": recordatorio_id},
        nota=(
            f"Cancelado: el mensaje a "
            f"{_etiqueta(fila['destinatario_nombre'], fila['telefono'])} del "
            f"{_ahora_texto(fila['programado_at'], zona_local())} no se enviará."
        ),
    )


async def ejecutar(
    nombre: str, params: dict[str, Any], biblio: Bibliotecario, actor: Any
) -> Resultado:
    """Punto de entrada único para el orquestador y el LLM."""
    if nombre == "recordatorio_crear":
        return await crear(
            biblio,
            actor=actor,
            destinatario=str(params.get("destinatario") or ""),
            mensaje=str(params.get("mensaje") or ""),
            cuando=str(params.get("cuando") or ""),
            conversacion_id=params.get("conversacion_id"),
            adjuntar_factura=bool(params.get("adjuntar_factura")),
            factura_de=params.get("factura_de"),
        )
    if nombre == "recordatorio_confirmar":
        return await confirmar(
            biblio, actor=actor, recordatorio_id=params.get("recordatorio_id")
        )
    if nombre == "recordatorio_descartar":
        return await descartar(
            biblio, actor=actor, recordatorio_id=params.get("recordatorio_id")
        )
    if nombre == "recordatorio_listar":
        return await listar(
            biblio,
            actor=actor,
            incluir_historicos=bool(params.get("incluir_historicos")),
        )
    if nombre == "recordatorio_cancelar":
        return await cancelar(
            biblio,
            actor=actor,
            recordatorio_id=str(params.get("recordatorio_id") or ""),
        )
    return Resultado(nombre, "NO_CONECTADA", nota=f"Acción {nombre} no implementada.")


__all__ = [
    "AFIRMACIONES",
    "MAX_INTENTOS",
    "NEGACIONES",
    "ROLES_ESCRITURA",
    "ahora_local",
    "cancelar",
    "confirmar",
    "crear",
    "descartar",
    "ejecutar",
    "es_afirmacion",
    "es_negacion",
    "extraer_destinatario",
    "extraer_mensaje",
    "interpretar",
    "listar",
    "normalizar",
    "parsear_cuando",
    "pendiente_de",
    "zona_local",
]
