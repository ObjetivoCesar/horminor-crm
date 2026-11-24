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
from decimal import Decimal, InvalidOperation
from typing import Any, Sequence
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
# «a las 15 y 27», «a las 3 y 30 de la tarde»: hora con minutos en palabras.
_RE_HORA_Y_MINUTOS = re.compile(
    r"\ba\s+las?\s+(\d{1,2})\s+y\s+(\d{1,2})\b"
    r"(?:\s*de\s+la\s+(manana|tarde|noche|madrugada))?"
)
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
    r"dec[ií]rle|dile|que\s+diga|indícale|indicale|diga|mande|"
    r"solicita|pid[eó]\s+que)\s+que\s+([^.!?]+[.!?]?)(?:\s|$)",
    re.IGNORECASE,
)
_RE_FACTURA = re.compile(
    r"\b(?:p[aá]sale|env[ií]ale|adjunta(?:le|r)?|m[aá]ndale|incluye)\b"
    r"[^.]{0,40}\bfactura\b",
    re.IGNORECASE,
)
_RE_MONTO = re.compile(
    r"(?:USD|\$)\s*[\d.,]+"
    r"|\b\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?\b"
    r"|\b\d+[.,]\d{2}\b"
    r"|\b(\d{1,6})\s*(?:d[oó]lares|usd)\b",
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

    hablada = _RE_HORA_Y_MINUTOS.findall(texto)
    if hablada:
        hora, minuto, momento = hablada[-1]
        valor = int(hora)
        if momento in ("tarde", "noche") and valor < 12:
            valor += 12
        elif momento == "madrugada" and valor == 12:
            valor = 0
        elif valor > 23:
            valor %= 24
        return valor, int(minuto)

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

    # Soportar "12 de diciembre", "5 de enero", etc. Una fecha sin hora se
    # programa a las 09:00 de Ecuador (hora visible en la ratificacion), nunca
    # a medianoche ni en UTC: eso correria el dia.
    mm = re.search(r"\b(\d+)\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b", texto, re.IGNORECASE)
    if mm:
        dia = int(mm.group(1))
        mes_nombre = mm.group(2).lower()
        meses = {"enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,"julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12}
        mes = meses.get(mes_nombre)
        if mes:
            from datetime import date
            try:
                target_date = date(ahora.year, mes, dia)
                if target_date < ahora.date():
                    target_date = date(ahora.year + 1, mes, dia)
                local = datetime(
                    target_date.year,
                    target_date.month,
                    target_date.day,
                    9,
                    0,
                    tzinfo=ahora.tzinfo or zona_local(),
                )
                return local.astimezone(timezone.utc)
            except ValueError:
                pass

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


def _a_decimal(token: str) -> Decimal | None:
    limpio = (
        token.replace("USD", "").replace("usd", "").replace("$", "").replace(" ", "")
    )
    if not limpio:
        return None
    if "," in limpio and "." in limpio:
        if limpio.rfind(",") > limpio.rfind("."):
            limpio = limpio.replace(".", "").replace(",", ".")
        else:
            limpio = limpio.replace(",", "")
    elif "," in limpio:
        partes = limpio.split(",")
        limpio = limpio.replace(",", ".") if len(partes[-1]) == 2 else limpio.replace(",", "")
    elif "." in limpio and len(limpio.split(".")[-1]) == 3:
        limpio = limpio.replace(".", "")
    try:
        return Decimal(limpio).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def cifras_de(texto: str) -> set[Decimal]:
    """Montos mencionados en un texto. '18:40' y 'orden 55' no cuentan."""
    valores: set[Decimal] = set()
    for match in _RE_MONTO.finditer(str(texto or "")):
        crudo = next((g for g in match.groups() if g), match.group(0))
        valor = _a_decimal(crudo)
        if valor is not None:
            valores.add(valor)
    return valores


async def _cifras_permitidas(
    biblio: Bibliotecario, cliente_id: str | None
) -> set[Decimal]:
    """Solo cifras que existen en la ficha del cliente."""
    if not cliente_id:
        return set()
    permitidas: set[Decimal] = set()

    saldo = await biblio.pool.fetchrow(
        """
        SELECT saldo_pendiente, total_fiado, total_cobrado
          FROM v_cliente_saldo
         WHERE id = $1
        """,
        cliente_id,
    )
    if saldo is not None:
        for clave in ("saldo_pendiente", "total_fiado", "total_cobrado"):
            if saldo[clave] is not None:
                permitidas.add(Decimal(str(saldo[clave])).quantize(Decimal("0.01")))

    facturas = await biblio.pool.fetch(
        "SELECT subtotal, iva_monto, total FROM client_invoices WHERE cliente_id = $1",
        cliente_id,
    )
    for factura in facturas:
        for clave in ("subtotal", "iva_monto", "total"):
            if factura[clave] is not None:
                permitidas.add(
                    Decimal(str(factura[clave])).quantize(Decimal("0.01"))
                )
    return permitidas


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
    destino = etiqueta if etiqueta == telefono else f"{etiqueta} ({telefono})"
    return (
        f"Voy a enviar a {destino} el "
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
        digitos = re.sub(r"\D", "", limpio)
        fila = await biblio.pool.fetchrow(
            """
            SELECT id, nombre, telefono_whatsapp
              FROM clients
             WHERE regexp_replace(coalesce(telefono_whatsapp, ''), '\\D', '', 'g')
                   LIKE '%' || right($1, 9)
             LIMIT 1
            """,
            digitos,
        )
        if fila is not None:
            return (
                formato_whatsapp(str(fila["telefono_whatsapp"] or limpio)),
                str(fila["id"]),
                str(fila["nombre"] or "") or None,
                "CRM",
                None,
            )
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
    confirmado_por: str | None = None,
    clave_externa: str | None = None,
    cifras_autorizadas: Sequence[Any] | None = None,
) -> Resultado:
    """Crea la fila del recordatorio.

    Nace en BORRADOR y espera la ratificacion en el chat. Si ``confirmado_por``
    viene con el id de un humano, la ratificacion ya ocurrio en la pantalla que
    mostro el mensaje y el destino exactos: la fila nace PENDIENTE.
    """
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
    clave = (clave_externa or "").strip() or _clave_idempotencia(
        actor_id, conversacion, telefono, cuerpo, programado
    )

    cifras = cifras_de(cuerpo)
    if cifras:
        permitidas = await _cifras_permitidas(biblio, cliente_id)
        # Una cifra dictada por el hablante y confirmada por un humano es una
        # cifra con sustento, aunque el cliente todavía no tenga ficha o el
        # monto no esté en una factura. Sin esto, un anticipo citado se perdía.
        for valor in cifras_autorizadas or ():
            try:
                permitidas.add(Decimal(str(valor)).quantize(Decimal("0.01")))
            except (InvalidOperation, ValueError, TypeError):
                continue
        sobrantes = cifras - permitidas
        if sobrantes:
            detalle = ", ".join(f"{valor:.2f}" for valor in sorted(sobrantes))
            return Resultado(
                "recordatorio_crear",
                "ERROR",
                nota=(
                    f"No puedo enviar una cifra que no esté en la ficha: {detalle}. "
                    "Dime el mensaje sin ese monto o usa el saldo verificado."
                ),
            )

    fila = await biblio.pool.fetchrow(
        """
        INSERT INTO gato_recordatorios (
            creado_por, rol_actor, conversacion_id, cliente_id,
            destinatario_nombre, telefono, mensaje, programado_at, zona,
            estado, origen_destino, clave_idempotencia, media_id,
            confirmado_por, confirmado_at
        )
        VALUES ($1, $2, $3::uuid, $4::uuid, $5, $6, $7, $8, $9,
                $13, $10, $11, $12::uuid,
                $14::text,
                CASE WHEN $14::text IS NULL THEN NULL ELSE now() END)
        ON CONFLICT (clave_idempotencia) WHERE clave_idempotencia IS NOT NULL
        DO NOTHING
        RETURNING id, destinatario_nombre, telefono, mensaje, programado_at,
                  origen_destino, estado
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
        "PENDIENTE" if confirmado_por else "BORRADOR",
        confirmado_por,
    )

    if fila is None:
        fila = await biblio.pool.fetchrow(
            """
            SELECT id, destinatario_nombre, telefono, mensaje, programado_at,
                   origen_destino, estado
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
    if confirmado_por:
        nota = (
            f"Recordatorio confirmado para {etiqueta} el "
            f"{_ahora_texto(fila['programado_at'], zona_obj)} ({zona_obj}): "
            f"«{fila['mensaje']}»."
        ) + _aviso_modo(getattr(actor, "modo_envio", ""))
    else:
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
            "estado": fila["estado"],
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


async def ultimo_de(biblio: Bibliotecario, *, actor: Any) -> dict[str, Any] | None:
    """Recordatorio mas reciente del actor que todavia se puede tocar."""
    fila = await biblio.pool.fetchrow(
        """
        SELECT id::text AS id, destinatario_nombre, telefono, mensaje,
               programado_at, estado
          FROM gato_recordatorios
         WHERE creado_por = $1
           AND estado IN ('BORRADOR', 'PENDIENTE')
         ORDER BY created_at DESC
         LIMIT 1
        """,
        str(getattr(actor, "actor_id", "") or ""),
    )
    return dict(fila) if fila is not None else None


async def actualizar(
    biblio: Bibliotecario,
    *,
    actor: Any,
    recordatorio_id: str | None = None,
    cuando: str | None = None,
    mensaje: str | None = None,
) -> Resultado:
    """Mueve la hora o corrige el texto de un recordatorio aun no enviado."""
    if getattr(actor, "rol", "") not in ROLES_ESCRITURA:
        return Resultado(
            "recordatorio_actualizar",
            "ACL",
            nota="Tu perfil no puede cambiar recordatorios.",
        )
    actual = (
        await ultimo_de(biblio, actor=actor)
        if not recordatorio_id
        else None
    )
    if recordatorio_id:
        fila = await biblio.pool.fetchrow(
            """
            SELECT id::text AS id, destinatario_nombre, telefono, mensaje,
                   programado_at, estado
              FROM gato_recordatorios
             WHERE id = $1::uuid
               AND (creado_por = $2 OR $3 = 'SUPERADMIN')
            """,
            recordatorio_id,
            str(getattr(actor, "actor_id", "") or ""),
            getattr(actor, "rol", ""),
        )
        actual = dict(fila) if fila is not None else None
    if actual is None:
        return Resultado(
            "recordatorio_actualizar",
            "VACIO",
            nota="No hay un recordatorio pendiente que pueda corregir.",
        )
    if str(actual["estado"]) not in ("BORRADOR", "PENDIENTE"):
        return Resultado(
            "recordatorio_actualizar",
            "ERROR",
            nota="Ese recordatorio ya se envió o se canceló; no se puede mover.",
        )

    nuevo_mensaje = " ".join(str(mensaje or "").split()) or actual["mensaje"]
    programado = actual["programado_at"]
    if cuando:
        calculado = parsear_cuando(cuando)
        if calculado is None:
            return Resultado(
                "recordatorio_actualizar",
                "FALTA_PARAMETRO",
                parametro_faltante="cuando",
                nota="¿Para qué hora lo muevo? Ejemplo: «a las 10:30».",
            )
        programado = calculado

    fila = await biblio.pool.fetchrow(
        """
        UPDATE gato_recordatorios
           SET mensaje = $2, programado_at = $3, updated_at = now()
         WHERE id = $1::uuid
           AND estado IN ('BORRADOR', 'PENDIENTE')
        RETURNING id::text AS id, destinatario_nombre, telefono, mensaje,
                  programado_at, estado
        """,
        str(actual["id"]),
        nuevo_mensaje,
        programado,
    )
    if fila is None:
        return Resultado(
            "recordatorio_actualizar",
            "ERROR",
            nota="No pude guardar el cambio del recordatorio.",
        )
    return Resultado(
        "recordatorio_actualizar",
        "OK",
        datos={
            "id": str(fila["id"]),
            "programado_local": _ahora_texto(fila["programado_at"], zona_local()),
            "estado": fila["estado"],
        },
        fuente=["gato_recordatorios"],
        filtros={"id": str(fila["id"])},
        nota=(
            f"Recordatorio movido para {_etiqueta(fila['destinatario_nombre'], fila['telefono'])} "
            f"el {_ahora_texto(fila['programado_at'], zona_local())}."
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
            cifras_autorizadas=cifras_de(
                getattr(actor, "texto_actual", "") or ""
            )
            or None,
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
