"""Compilador determinístico: de hechos citados a acciones con invariantes.

El LLM no arma el borrador final. Este módulo toma hechos ya sostenidos por una
cita y aplica las reglas del dominio. Si falta un dato o una regla no se cumple,
no inventa: pregunta o deja la acción bloqueada.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .dinero import dinero_ya_entro, sin_tildes
from .encargos import segmentar, texto_de
from .hechos import Evidencia, HechoCitado, decimal_utilizable
from .internas import (
    detectar_intencion_tarea,
    detectar_prioridad,
    detectar_rol_interno,
    es_instruccion_interna,
    persona_dictada,
)
from .tiempo import normalizar_hora, sostiene_fecha

ROLES_ACCIONES: dict[str, tuple[str, ...]] = {
    "crear_cliente": ("SUPERADMIN", "SECRETARIA", "VENDEDOR"),
    "crear_cotizacion_borrador": ("SUPERADMIN", "SECRETARIA", "VENDEDOR"),
    "enviar_cotizacion_whatsapp": ("SUPERADMIN", "SECRETARIA", "VENDEDOR"),
    "solicitar_ubicacion_whatsapp": ("SUPERADMIN", "SECRETARIA", "VENDEDOR"),
    "registrar_abono_cliente": ("SUPERADMIN", "SECRETARIA", "CONTADORA"),
    "registrar_traslado_caja_banco": ("SUPERADMIN", "CONTADORA"),
    "registrar_gasto_caja": ("SUPERADMIN", "SECRETARIA", "CONTADORA"),
    # Mismos roles que `recordatorios.ROLES_ESCRITURA`: el Cerebro no puede
    # proponer una tarea que el servicio de Gato después rechace por ACL.
    "crear_tarea_recordatorio": ("SUPERADMIN", "SECRETARIA"),
    # Instrucción a alguien del equipo sin teléfono: el aviso y el seguimiento
    # viven en el panel, no en WhatsApp.
    "crear_tarea_interna": ("SUPERADMIN", "SECRETARIA"),
    "registrar_hecho_carpeta": ("SUPERADMIN", "SECRETARIA", "VENDEDOR", "CONTADORA"),
}

MAX_PREGUNTAS = 3

# Formas de pago que acepta el esquema (cotizaciones y caja).
FORMAS_COTIZACION: tuple[str, ...] = ("EFECTIVO", "TRANSFERENCIA", "ABONO", "FIADO")
# Un abono entra a caja: solo efectivo o transferencia. «ABONO» es condición de
# la cotización, no un método de pago.
FORMAS_PAGO: tuple[str, ...] = ("EFECTIVO", "TRANSFERENCIA")


@dataclass(frozen=True)
class Receta:
    resistencia: str
    precio_m3: Decimal
    precio_estado: str = "PROVISIONAL"
    iva_pct: Decimal = Decimal("15")


@dataclass(frozen=True)
class ClienteResuelto:
    id: str | None
    nombre: str
    existente: bool = True


@dataclass(frozen=True)
class Contexto:
    hoy: date
    sandbox: bool
    cliente: ClienteResuelto | None = None
    receta: Receta | None = None
    saldo_caja: Decimal | None = None
    rol_actor: str | None = None
    # Texto normalizado del dictado. Lo usa la guarda del dinero para leer la
    # frase alrededor de la cifra («ya me depositó» vs «nos van a depositar»);
    # la cita de un monto numérico es solo el número y no alcanza.
    texto: str | None = None


@dataclass(frozen=True)
class Pregunta:
    clave: str
    texto: str
    opciones: tuple[str, ...] = ()
    encargo: int = 1


@dataclass(frozen=True)
class Condicion:
    """Lo que el dictado dejó como condición y no cabe en una acción.

    Un plazo, una entrega contra pago o un encargo al expediente no son
    columnas de ninguna acción. Si la acción que los llevaba no se puede
    compilar, la condición no puede desaparecer: se conserva con su cita y se
    muestra tal cual. No autoriza nada por sí sola.
    """

    clave: str
    texto: str
    cita: str | None = None
    estado: str = "VIGENTE"  # VIGENTE | POR_ACLARAR
    encargo: int = 1

    def a_dict(self) -> dict[str, Any]:
        return {
            "clave": self.clave,
            "texto": self.texto,
            "cita": self.cita,
            "estado": self.estado,
            "encargo": self.encargo,
        }


@dataclass(frozen=True)
class AccionPropuesta:
    orden: int
    nombre: str
    parametros: Mapping[str, Any]
    rol_requerido: tuple[str, ...]
    requiere_doble_confirmacion: bool = False
    depende_de: int | None = None
    bloqueada_por: str | None = None
    encargo: int = 1

    def a_dict(self) -> dict[str, Any]:
        return {
            "orden": self.orden,
            "accion_nombre": self.nombre,
            "parametros": _jsonable(self.parametros),
            "rol_requerido": list(self.rol_requerido),
            "requiere_doble_confirmacion": self.requiere_doble_confirmacion,
            "depende_de_orden": self.depende_de,
            "bloqueada_por": self.bloqueada_por,
            "encargo": self.encargo,
        }


@dataclass(frozen=True)
class EncargoResumen:
    """Un asunto del dictado, con su estado propio.

    Tres instrucciones en un audio son tres encargos: cada uno tiene sus
    acciones, sus preguntas y su estado. Lo que se confirma o se cancela es el
    encargo, no el dictado entero.
    """

    encargo: int
    texto: str
    estado: str
    acciones: tuple[int, ...] = ()
    preguntas: tuple[str, ...] = ()

    def a_dict(self) -> dict[str, Any]:
        return {
            "encargo": self.encargo,
            "texto": self.texto,
            "estado": self.estado,
            "acciones": list(self.acciones),
            "preguntas": list(self.preguntas),
        }


@dataclass(frozen=True)
class Borrador:
    estado: str
    intencion: str
    acciones: tuple[AccionPropuesta, ...] = ()
    preguntas: tuple[Pregunta, ...] = ()
    hechos: tuple[HechoCitado, ...] = field(default_factory=tuple)
    condiciones: tuple[Condicion, ...] = ()
    encargos: tuple[EncargoResumen, ...] = ()

    def a_dict(self) -> dict[str, Any]:
        return {
            "estado": self.estado,
            "intencion": self.intencion,
            "acciones": [accion.a_dict() for accion in self.acciones],
            "preguntas": [
                {
                    "clave": p.clave,
                    "texto": p.texto,
                    "opciones": list(p.opciones),
                    "encargo": p.encargo,
                }
                for p in self.preguntas
            ],
            "hechos": [hecho.a_dict() for hecho in self.hechos],
            "condiciones": [condicion.a_dict() for condicion in self.condiciones],
            "encargos": [encargo.a_dict() for encargo in self.encargos],
        }


def _jsonable(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, Mapping):
        return {k: _jsonable(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_jsonable(v) for v in valor]
    return valor


def _hecho(hechos: Sequence[HechoCitado], clave: str) -> HechoCitado | None:
    """El último valor utilizable de esa clave es el que manda.

    Si el hablante se corrige dentro del mismo audio («380, bueno, 300 y
    pico»), el hecho posterior gana. Un TENTATIVO no es utilizable: no decide.
    """
    encontrado: HechoCitado | None = None
    for hecho in hechos:
        if hecho.clave == clave and hecho.utilizable:
            encontrado = hecho
    return encontrado


def _texto(hechos: Sequence[HechoCitado], clave: str) -> str | None:
    hecho = _hecho(hechos, clave)
    if hecho is None or hecho.valor is None:
        return None
    valor = str(hecho.valor).strip()
    return valor or None


def _decimal(hechos: Sequence[HechoCitado], clave: str) -> Decimal | None:
    hecho = _hecho(hechos, clave)
    if hecho is None:
        return None
    return decimal_utilizable(hecho.valor)


def _fecha(hechos: Sequence[HechoCitado], clave: str) -> date | None:
    hecho = _hecho(hechos, clave)
    if hecho is None:
        return None
    valor = hecho.valor
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor[:10])
        except ValueError:
            return None
    return None


def _booleano(hechos: Sequence[HechoCitado], clave: str) -> bool:
    hecho = _hecho(hechos, clave)
    if hecho is None:
        return False
    if isinstance(hecho.valor, bool):
        return hecho.valor
    return str(hecho.valor).strip().lower() in ("true", "si", "sí", "1", "yes")


def _booleano_opcional(hechos: Sequence[HechoCitado], clave: str) -> bool | None:
    """Tri-estado: True, False o None cuando el audio no lo dijo."""
    hecho = _hecho(hechos, clave)
    if hecho is None:
        return None
    if isinstance(hecho.valor, bool):
        return hecho.valor
    texto = str(hecho.valor).strip().lower()
    if texto in ("true", "si", "sí", "1", "yes"):
        return True
    if texto in ("false", "no", "0"):
        return False
    return None


def _dinero_ya_entro(
    hechos: Sequence[HechoCitado], texto: str | None = None
) -> bool:
    """Atajo: la regla vive en `dinero.py` y la comparte el resumen."""
    return dinero_ya_entro(hechos, texto, _decimal(hechos, "pago.monto"))


# ---------------------------------------------------------------------------
# Ficha de la tarea interna: qué se pide, con qué datos y qué se espera.
# La instrucción original se conserva tal cual; la ficha solo ordena lo que
# los hechos ya traen y marca lo que falta. No redacta ni inventa.
# ---------------------------------------------------------------------------
TIPO_VERIFICACION = "VERIFICACION"
ACCION_POR_TIPO: dict[str, str] = {
    "VERIFICACION": "Verificar el dato indicado",
    "REVISION": "Revisar lo indicado",
    "COMUNICACION": "Contactar y averiguar",
    "PREPARACION": "Preparar lo indicado",
    "OTRO": "Atender la instrucción",
}
RESULTADO_POR_TIPO: dict[str, str] = {
    "VERIFICACION": "Informar si se confirmó o no, y con qué referencia.",
    "REVISION": "Informar qué se revisó y qué quedó pendiente.",
    "COMUNICACION": "Informar a quién se contactó y qué respondió.",
    "PREPARACION": "Informar qué se preparó y qué falta para completarlo.",
    "OTRO": "Informar qué se hizo y qué queda pendiente.",
}
_MARCAS_TIPO = (
    (
        TIPO_VERIFICACION,
        (
            "verifica",
            "verifiquen",
            "confirmar",
            "confirmen",
            "comprobar",
            "comprueben",
            "revisen si",
            "revisar si",
            "revisa si",
            "si ya entro",
            "si entro",
        ),
    ),
    (
        "REVISION",
        ("revisen", "revisar", "revisa", "chequear", "chequeen", "controlen"),
    ),
    (
        "COMUNICACION",
        (
            "llamen",
            "llame",
            "llamar",
            "hablen",
            "hable",
            "hablar",
            "averiguen",
            "averigue",
            "pregunten",
            "pregunte",
            "coordinen",
            "coordine",
            "comuniquen",
            "comunique",
        ),
    ),
    (
        "PREPARACION",
        (
            "preparen",
            "prepare",
            "preparar",
            "armen",
            "arme",
            "armar",
            "cotizen",
            "cotice",
            "cotizar",
            "documentos",
        ),
    ),
)


def _tipo_de_tarea(texto: str | None) -> str:
    plano = sin_tildes(texto or "")
    for tipo, marcas in _MARCAS_TIPO:
        if any(marca in plano for marca in marcas):
            return tipo
    return "OTRO"


def _dicho_tentativo(
    hechos: Sequence[HechoCitado], clave: str
) -> str | None:
    """La frase exacta con la que se dudó, para preguntar citándola."""
    for hecho in reversed(list(hechos)):
        if hecho.clave == clave and hecho.es_tentativo:
            return (
                hecho.evidencia.cita
                if hecho.evidencia is not None
                else str(hecho.valor)
            )
    return None


def _ficha_tarea(
    hechos: Sequence[HechoCitado],
    *,
    texto: str | None,
    mensaje: str,
    rol: str,
    persona: str | None,
    telefono_referencia: str | None,
    cuando: str | None,
    nota: str | None = None,
) -> dict[str, Any]:
    """Ficha determinística: solo hechos, nunca texto redactado."""
    tipo = _tipo_de_tarea(f"{texto or ''} {mensaje}")
    monto = _decimal(hechos, "pago.monto")
    volumen = _decimal(hechos, "cotizacion.volumen_m3")
    pendientes = [
        {
            "clave": hecho.clave,
            "dicho": (
                hecho.evidencia.cita if hecho.evidencia is not None else str(hecho.valor)
            ),
            "motivo": "el hablante dudó o aproximó",
        }
        for hecho in hechos
        if hecho.es_tentativo
    ]
    return {
        "tipo": tipo,
        "accion": ACCION_POR_TIPO[tipo],
        "cliente": _texto(hechos, "cliente.nombre"),
        "monto_usd": str(monto) if monto is not None else None,
        "volumen_m3": str(volumen) if volumen is not None else None,
        "telefono_referencia": telefono_referencia,
        "responsable_rol": rol,
        "responsable": persona,
        "plazo_dicho": cuando,
        "datos_faltantes": pendientes,
        "resultado_esperado": RESULTADO_POR_TIPO[tipo],
        "nota": nota,
    }


# Revocación del dictado completo. No es lo mismo que negar un dato: acá el
# hablante cancela la orden («no hagas nada todavía», «mejor no», «déjalo»).
# Se lee antes de compilar: si revoca, no se propone ninguna acción.
_MARCAS_REVOCACION = (
    "no hagas nada",
    "no haga nada",
    "no hagan nada",
    "mejor no",
    "dejalo",
    "dejalo para",
    "olvidalo",
    "cancela eso",
    "cancelalo",
    "cancelala",
    "no lo hagas",
    "no la hagas",
    "no lo hagan",
    "no se lo manden",
    "no lo mandes",
    "no lo envies",
    "primero voy a hablar",
)


def dictado_revocado(texto: str | None) -> bool:
    """True si el dictado cancela la instrucción completa."""
    plano = sin_tildes(texto or "")
    return any(marca in plano for marca in _MARCAS_REVOCACION)


def normalizar_resistencia(valor: Any) -> str | None:
    """«210» dicho al pasar es la receta FC-210; el nombre del catálogo manda.

    Solo se completa el prefijo cuando el dictado trae el número solo. Si el
    audio ya dijo «FC-210» no se toca.
    """
    texto = " ".join(str(valor or "").split()).upper()
    if not texto:
        return None
    if texto.isdigit():
        return f"FC-{texto}"
    return texto


_VACIAS_PERSONA = {
    "de",
    "del",
    "la",
    "el",
    "los",
    "las",
    "y",
    "ing",
    "ingeniero",
    "sr",
    "sra",
    "senor",
    "senora",
    "jefe",
    "jefa",
    "obra",
}


def _tokens_persona(texto: Any) -> set[str]:
    base = unicodedata.normalize("NFD", str(texto or "").lower())
    plano = "".join(c for c in base if unicodedata.category(c) != "Mn")
    return {
        token
        for token in re.findall(r"[a-z0-9]+", plano)
        if token not in _VACIAS_PERSONA
    }


def _contactos(hechos: Sequence[HechoCitado]) -> list[dict[str, str | None]]:
    """Personas de contacto del dictado: la primera y las numeradas."""
    salida: list[dict[str, str | None]] = []
    for sufijo in ("", ".2", ".3", ".4"):
        nombre = _texto(hechos, f"contacto{sufijo}.nombre")
        telefono = _texto(hechos, f"contacto{sufijo}.telefono")
        rol = _texto(hechos, f"contacto{sufijo}.rol")
        if nombre or telefono or rol:
            salida.append({"nombre": nombre, "telefono": telefono, "rol": rol})
    return salida


def _contacto_por_nombre(
    contactos: Sequence[Mapping[str, Any]], dicho: str
) -> Mapping[str, Any] | None:
    """Coincidencia por nombre o rol; si hay dos, no se elige a ciegas."""
    buscado = _tokens_persona(dicho)
    if not buscado:
        return None
    encontrados = [
        contacto
        for contacto in contactos
        if buscado
        & (_tokens_persona(contacto.get("nombre")) | _tokens_persona(contacto.get("rol")))
    ]
    return encontrados[0] if len(encontrados) == 1 else None


_NEGACIONES_CONDICION = (
    "no le",
    "no se",
    "no lo",
    "no la",
    "no hagan",
    "no haga",
    "no aplicar",
    "no aplicarles",
    "todavia no",
    "aun no",
    "sin aplicar",
    "espera",
    "primero tengo que revisar",
)


def _condicion_negada(texto: str | None, *marcas: str) -> bool:
    """True si el dictado niega o condiciona el dato («no le hagan todavía»).

    El modelo puede extraer la cifra con cita perfecta y aun así equivocarse de
    intención; esta lectura determinística evita que una negación se convierta
    en una condición aplicada.
    """
    plano = sin_tildes(texto or "")
    for marca in marcas:
        inicio = plano.find(marca)
        while inicio >= 0:
            ventana = plano[max(0, inicio - 50) : inicio + len(marca) + 10]
            if any(neg in ventana for neg in _NEGACIONES_CONDICION):
                return True
            inicio = plano.find(marca, inicio + 1)
    return False


def _fragmento(texto: str, marca: str, *, margen: int = 90) -> str:
    """Devuelve la frase del dictado que contiene la marca, sin redactarla."""
    plano = sin_tildes(texto or "")
    posicion = plano.find(marca)
    if posicion < 0:
        return marca
    inicio = max(0, posicion - margen)
    cortes = [texto.rfind(sep, inicio, posicion) for sep in (".", ";", "!")]
    corte = max(cortes)
    if corte >= inicio:
        inicio = corte + 1
    else:
        espacio = texto.find(" ", inicio, posicion)
        if espacio > 0:
            inicio = espacio + 1
    fin = len(texto)
    for sep in (".", ";", "!", "?"):
        encontrado = texto.find(sep, posicion)
        if 0 <= encontrado < fin:
            fin = encontrado
    return texto[inicio:fin].strip(" ,;\n\t")


# El dictado condiciona la entrega al pago. No autoriza despachar: solo deja
# constancia de la condición para secretaría y para el área comercial.
_MARCAS_ENTREGA_CONTRA_PAGO = (
    "contra entrega de ese pago",
    "contra entrega del pago",
    "contra entrega",
    "contra el pago",
    "previo pago",
    "previo al pago",
    "contra pago",
    "despues de que nos pague",
    "despues que nos pague",
    "cuando nos pague",
    "una vez que nos pague",
    "sujeto a pago",
    "si nos pagan",
    "hasta que nos pague",
)

# Encargo de completar el expediente. No dice que los documentos ya llegaron.
_MARCAS_EXPEDIENTE = (
    "expediente",
    "especificaciones de la constructora",
)


def _condiciones(
    hechos: Sequence[HechoCitado], texto: str | None
) -> tuple[Condicion, ...]:
    """Condiciones y encargos que no caben en una acción ejecutable.

    Se leen de los hechos citados y, si el modelo no los capturó, del propio
    dictado (con su frase como cita). Nunca se convierten en una autorización:
    solo quedan visibles para que no se pierda el encargo.
    """
    condiciones: list[Condicion] = []
    plano = sin_tildes(texto or "")

    plazo = _texto(hechos, "cotizacion.plazo_entrega")
    cita_plazo = None
    if plazo:
        hecho_plazo = _hecho(hechos, "cotizacion.plazo_entrega")
        if hecho_plazo is not None and hecho_plazo.evidencia is not None:
            cita_plazo = hecho_plazo.evidencia.cita
    else:
        coincidencia = re.search(
            r"plazo de ([a-z0-9]+ (?:dias|semanas|meses|anos))", plano
        )
        if coincidencia:
            plazo = coincidencia.group(1)
            cita_plazo = _fragmento(texto or "", coincidencia.group(0))
    if plazo:
        condiciones.append(
            Condicion(
                clave="entrega.plazo",
                texto=(
                    f"Plazo de entrega: {plazo}. Falta precisar desde cuándo "
                    "se cuenta."
                ),
                cita=cita_plazo,
                estado="POR_ACLARAR",
            )
        )

    for marca in _MARCAS_ENTREGA_CONTRA_PAGO:
        if marca in plano:
            condiciones.append(
                Condicion(
                    clave="entrega.contra_pago",
                    texto=(
                        "La entrega queda condicionada a la recepción del pago. "
                        "No autoriza despachar."
                    ),
                    cita=_fragmento(texto or "", marca),
                    estado="VIGENTE",
                )
            )
            break

    for marca in _MARCAS_EXPEDIENTE:
        if marca in plano:
            condiciones.append(
                Condicion(
                    clave="expediente.completar",
                    texto=(
                        "Incorporar al expediente del cliente la información que "
                        "indique la constructora. Falta verificar qué documentos "
                        "son y si ya se recibieron."
                    ),
                    cita=_fragmento(texto or "", marca),
                    estado="POR_ACLARAR",
                )
            )
            break

    return tuple(condiciones)


# Una frase que el dictado dirige al destinatario es un mensaje final; una
# descripción («el recordatorio del pago que tiene que hacernos») es la
# instrucción, no el texto que se envía. El compilador no redacta: si no hay
# mensaje final, lo pide antes de ejecutar.
_MARCAS_MENSAJE_FINAL = (
    "dile ",
    "dile:",
    "digale",
    "dígale",
    "mandele",
    "mándele",
    "escribale",
    "escríbele",
    "ponle",
    "enviele",
    "envíele",
    "que diga",
    "con estas palabras",
    "el mensaje es",
    "texto:",
    "le dice",
    "le escribes",
    "le mandas",
    "le envias",
    "le envías",
    "que le diga",
)
_FORMAS_MENSAJE_DIRECTO = (
    "por favor",
    "licenciado",
    "licenciada",
    "ingeniero",
    "ingeniera",
    "estimado",
    "estimada",
    "buenas",
    "buenos dias",
    "buenas tardes",
    "hola ",
    "senor ",
    "senora ",
    "sr.",
    "sra.",
)
_VERBOS_MENSAJE = (
    "envie",
    "envíe",
    "confirme",
    "confírmeme",
    "confirmenos",
    "confírmenos",
    "remita",
    "comuniquese",
    "comuníquese",
    "avisenos",
    "avísenos",
    "avíseme",
    "adjunte",
    "adjuntenos",
    "deposite",
)


def mensaje_es_final(texto: str | None, mensaje: str | None) -> bool:
    """True si lo dictado ya es el texto que se puede enviar tal cual."""
    if not mensaje:
        return False
    plano = sin_tildes(texto or "")
    if any(marca in plano for marca in _MARCAS_MENSAJE_FINAL):
        return True
    cuerpo = sin_tildes(mensaje)
    if any(cuerpo.startswith(forma) for forma in _FORMAS_MENSAJE_DIRECTO):
        return True
    return any(verbo in cuerpo for verbo in _VERBOS_MENSAJE)


def _notas_cotizacion(
    hechos: Sequence[HechoCitado], *, descuento_negado: bool = False
) -> str | None:
    """Condiciones dictadas que no son columnas del esquema, sin inventar."""
    notas: list[str] = []
    descuento = _decimal(hechos, "cotizacion.descuento_pct")
    if descuento_negado:
        notas.append("Descuento NO aplicado: el dictado pidió esperar")
    elif descuento is not None:
        notas.append(f"Descuento acordado: {descuento.normalize()}%")
    plazo = _texto(hechos, "cotizacion.plazo_entrega")
    if plazo:
        notas.append(f"Plazo de entrega: {plazo}")
    dias = _texto(hechos, "cotizacion.dias_trabajo")
    if dias:
        notas.append(f"Dias de trabajo: {dias}")
    if _booleano(hechos, "operacion.planta_movil"):
        notas.append("Llevar la planta movil al sitio")
    return "; ".join(notas) or None


def _hablante(hechos: Sequence[HechoCitado], clave: str) -> str | None:
    hecho = _hecho(hechos, clave)
    if hecho is None or hecho.evidencia is None:
        return None
    return hecho.evidencia.hablante


def _forma(valor: Any, permitidas: Sequence[str]) -> str | None:
    """Devuelve la forma de pago si el dictado contiene una permitida.

    «de abono» no es una forma de pago: si no coincide con la lista, se ignora
    en vez de propagar un valor que el esquema no acepta.
    """
    texto = " ".join(str(valor or "").split()).upper()
    if not texto:
        return None
    for forma in permitidas:
        if forma in texto:
            return forma
    return None


def _sin_duplicados(preguntas: list[Pregunta]) -> tuple[Pregunta, ...]:
    vistas: set[str] = set()
    salida: list[Pregunta] = []
    for pregunta in preguntas:
        if pregunta.clave in vistas:
            continue
        vistas.add(pregunta.clave)
        salida.append(pregunta)
        if len(salida) >= MAX_PREGUNTAS:
            break
    return tuple(salida)


def _compilar_asunto(
    hechos: Sequence[HechoCitado],
    contexto: Contexto,
    *,
    intencion: str = "MUTACION",
) -> Borrador:
    """Compila UN asunto (los hechos de un solo encargo). No escribe nada."""
    hechos = tuple(hechos)
    if intencion == "CONSULTA":
        return Borrador("SIN_ACCIONES", "CONSULTA", hechos=hechos)
    if dictado_revocado(contexto.texto):
        # El hablante canceló la orden completa: los hechos quedan como
        # constancia, pero no se propone ni se ejecuta nada.
        return Borrador("SIN_ACCIONES", "MUTACION", hechos=hechos)

    acciones: list[AccionPropuesta] = []
    preguntas: list[Pregunta] = []
    bloqueos = False

    def agregar(
        nombre: str,
        parametros: Mapping[str, Any],
        *,
        doble: bool = False,
        depende: int | None = None,
        bloqueo: str | None = None,
    ) -> int:
        orden = len(acciones) + 1
        acciones.append(
            AccionPropuesta(
                orden=orden,
                nombre=nombre,
                parametros=parametros,
                rol_requerido=ROLES_ACCIONES[nombre],
                requiere_doble_confirmacion=doble,
                depende_de=depende,
                bloqueada_por=bloqueo,
            )
        )
        return orden

    # ------------------------------------------------------------------
    # Cliente
    # ------------------------------------------------------------------
    cliente = contexto.cliente
    orden_cliente: int | None = None
    # Un recordatorio a un número dictado no necesita cliente. Si el dictado
    # trae cliente, cotización, dinero o traslado, sí.
    necesita_cliente = not hechos or any(
        hecho.clave.startswith(("cliente.", "cotizacion.", "pago.", "traslado."))
        for hecho in hechos
    )
    if cliente is None and necesita_cliente:
        nombre = _texto(hechos, "cliente.nombre")
        if not nombre:
            preguntas.append(
                Pregunta("cliente.nombre", "¿Para qué cliente es la operación?")
            )
            bloqueos = True
        else:
            cedula_hecho = _hecho(hechos, "cliente.cedula")
            cedula = _texto(hechos, "cliente.cedula")
            if cedula_hecho is not None and cedula_hecho.checksum_valido is False:
                preguntas.append(
                    Pregunta(
                        "cliente.cedula",
                        f"Escuché la cédula {cedula}, pero el dígito verificador "
                        "no cuadra. ¿Cuál es el número correcto?",
                    )
                )
                bloqueos = True
            telefono_hecho = _hecho(hechos, "cliente.telefono")
            telefono = _texto(hechos, "cliente.telefono")
            if telefono_hecho is not None and telefono_hecho.estado == "INFERIDO":
                preguntas.append(
                    Pregunta(
                        "cliente.telefono",
                        f"¿El teléfono del cliente es {telefono}?",
                        ("Sí", "No"),
                    )
                )
                bloqueos = True
            orden_cliente = agregar(
                "crear_cliente",
                {
                    "nombre": nombre,
                    "cedula": cedula,
                    "telefono": telefono,
                    "ciudad": _texto(hechos, "cliente.ciudad"),
                    "referencia_obra": _texto(hechos, "cliente.referencia"),
                },
            )

    # ------------------------------------------------------------------
    # Cotización (solo si el audio habla de una)
    # ------------------------------------------------------------------
    hay_cotizacion = any(hecho.clave.startswith("cotizacion.") for hecho in hechos)
    orden_cotizacion: int | None = None
    precio_estado: str | None = None

    if hay_cotizacion:
        volumen = _decimal(hechos, "cotizacion.volumen_m3")
        descuento_negado = _condicion_negada(contexto.texto, "descuento", "rebaja")
        obra = _texto(hechos, "cotizacion.obra_direccion") or _texto(
            hechos, "cliente.referencia"
        )
        resistencia = normalizar_resistencia(
            _texto(hechos, "cotizacion.resistencia")
        ) or (contexto.receta.resistencia if contexto.receta else None)

        if volumen is None or volumen <= 0:
            dicho = _dicho_tentativo(hechos, "cotizacion.volumen_m3")
            preguntas.append(
                Pregunta(
                    "cotizacion.volumen_m3",
                    (
                        f"Dijiste «{dicho}». ¿Cuántos m³ exactos necesita la obra?"
                        if dicho
                        else "¿Cuántos m³ necesita la obra?"
                    ),
                )
            )
            bloqueos = True
        if not obra:
            preguntas.append(
                Pregunta(
                    "cotizacion.obra_direccion",
                    "¿Cuál es la dirección o referencia de la obra?",
                )
            )
            bloqueos = True
        if not resistencia:
            preguntas.append(
                Pregunta(
                    "cotizacion.resistencia", "¿Qué resistencia (FC-210, FC-350…)?"
                )
            )
            bloqueos = True

        precio = _decimal(hechos, "cotizacion.precio_m3")
        if precio is not None:
            hablante = _hablante(hechos, "cotizacion.precio_m3")
            if hablante != "SUPERADMIN":
                preguntas.append(
                    Pregunta(
                        "cotizacion.precio_m3",
                        "Solo Julio puede fijar el precio; se usará la lista vigente.",
                    )
                )
                precio = None
            else:
                precio_estado = "OFICIAL"
        if precio is None and contexto.receta is not None:
            precio = contexto.receta.precio_m3
            precio_estado = contexto.receta.precio_estado
        if precio is None:
            preguntas.append(
                Pregunta("cotizacion.precio_m3", "¿Qué precio por m³ se aplica?")
            )
            bloqueos = True

        if (
            volumen is not None
            and volumen > 0
            and obra
            and resistencia
            and precio is not None
            and precio_estado is not None
        ):
            forma_pago = (
                _forma(_texto(hechos, "cotizacion.forma_pago"), FORMAS_COTIZACION)
                or "POR_DEFINIR"
            )
            fecha_entrega = _fecha(hechos, "cotizacion.fecha_entrega")
            hecho_fecha = _hecho(hechos, "cotizacion.fecha_entrega")
            if (
                fecha_entrega is not None
                and hecho_fecha is not None
                and hecho_fecha.evidencia is not None
                and not sostiene_fecha(hecho_fecha.evidencia.cita)
            ):
                # Una hora no sostiene una fecha: no se arrastra el día de hoy.
                fecha_entrega = None
            orden_cotizacion = agregar(
                "crear_cotizacion_borrador",
                {
                    "cliente_id": cliente.id if cliente else None,
                    "obra_direccion": obra,
                    "volumen_m3": volumen,
                    "resistencia": resistencia,
                    "precio_m3": precio,
                    "precio_estado": precio_estado,
                    "forma_pago": forma_pago,
                    "fecha_entrega_tentativa": fecha_entrega,
                    "hora_entrega_tentativa": normalizar_hora(
                        _texto(hechos, "cotizacion.hora_entrega")
                    ),
                    "descuento_pct": (
                        None
                        if descuento_negado
                        else _decimal(hechos, "cotizacion.descuento_pct")
                    ),
                    "plazo_entrega": _texto(hechos, "cotizacion.plazo_entrega"),
                    "notas": _notas_cotizacion(
                        hechos, descuento_negado=descuento_negado
                    ),
                },
                depende=orden_cliente,
            )

    # ------------------------------------------------------------------
    # Dinero
    # ------------------------------------------------------------------
    monto = _decimal(hechos, "pago.monto")
    forma_pago = _forma(_texto(hechos, "pago.forma"), FORMAS_PAGO)
    pago_recibido = _booleano_opcional(hechos, "pago.recibido")
    hecho_recibido = _hecho(hechos, "pago.recibido")
    # Lo que corrigió una persona manda: si Julio dijo «sí, ya entró», no se
    # le vuelve a preguntar por una frase del audio.
    recibido_humano = (
        hecho_recibido is not None
        and hecho_recibido.estado == "CORREGIDO_POR_HUMANO"
    )
    pasado = _dinero_ya_entro(hechos, contexto.texto)
    if pago_recibido is True and not recibido_humano and not pasado:
        # El modelo afirmó que el dinero entró y el dictado no lo sostiene:
        # se degrada a «no lo sé» en vez de escribir en caja por su palabra.
        pago_recibido = None
    orden_abono: int | None = None
    # Si el dictado no dice si el dinero entró y la cita no habla en pasado,
    # no se registra el abono: se pregunta. Un abono toca caja y cartera. No se
    # cambia `pago_recibido` a False porque el audio no dijo eso: el hecho
    # sigue siendo «no lo sé» y así lo lee el resumen.
    abono_sin_confirmar = (
        monto is not None
        and pago_recibido is None
        and not recibido_humano
        and not pasado
    )
    if abono_sin_confirmar:
        preguntas.append(
            Pregunta(
                "pago.recibido",
                f"¿Los {monto} USD ya entraron? Sin esa confirmación no registro "
                "el abono; si todavía no, queda solo el recordatorio.",
                ("Sí, ya entró", "Todavía no"),
            )
        )
        bloqueos = True
    if monto is not None and pago_recibido is not False and not abono_sin_confirmar:
        if monto <= 0:
            preguntas.append(Pregunta("pago.monto", "El monto debe ser mayor que cero."))
            bloqueos = True
        else:
            if forma_pago is None:
                preguntas.insert(
                    0,
                    Pregunta(
                        "pago.forma",
                        "¿El abono entró en efectivo o por transferencia?",
                        ("Efectivo", "Transferencia"),
                    ),
                )
                bloqueos = True
                forma_pago = "POR_DEFINIR"
            orden_abono = agregar(
                "registrar_abono_cliente",
                {
                    "cliente_id": cliente.id if cliente else None,
                    "monto_usd": monto,
                    "forma_pago": forma_pago,
                    "referencia": _texto(hechos, "pago.referencia"),
                },
                doble=True,
                depende=orden_cliente,
            )

    cuenta = _texto(hechos, "traslado.cuenta_banco")
    if cuenta and (pago_recibido is False or abono_sin_confirmar):
        # Sin dinero recibido no hay efectivo que mover a la caja.
        cuenta = None
    if cuenta and forma_pago == "TRANSFERENCIA":
        # La transferencia del cliente ya entra al banco: no es un traslado
        # interno de caja a banco.
        cuenta = None
    if cuenta:
        if monto is None:
            preguntas.append(
                Pregunta("traslado.monto", "¿Qué monto se traslada al banco?")
            )
            bloqueos = True
        else:
            bloqueo = None
            if contexto.saldo_caja is not None and contexto.saldo_caja < monto:
                bloqueo = "SALDO_CAJA_INSUFICIENTE"
                preguntas.append(
                    Pregunta(
                        "traslado.saldo_caja",
                        f"La caja registra {contexto.saldo_caja} y el traslado es "
                        f"{monto}. ¿Se registra igual?",
                    )
                )
            agregar(
                "registrar_traslado_caja_banco",
                {
                    "monto_usd": monto,
                    "cuenta_destino": cuenta,
                    "referencia": _texto(hechos, "pago.referencia"),
                },
                doble=True,
                depende=orden_abono,
                bloqueo=bloqueo,
            )

    # ------------------------------------------------------------------
    # Envío por WhatsApp (después de la cotización y del abono)
    # ------------------------------------------------------------------
    if _booleano(hechos, "cotizacion.enviar"):
        if orden_cotizacion is None:
            preguntas.append(
                Pregunta(
                    "cotizacion.enviar",
                    "No se puede enviar una cotización que aún no se puede crear.",
                )
            )
            bloqueos = True
        else:
            bloqueo = None
            if precio_estado == "PROVISIONAL" and not contexto.sandbox:
                bloqueo = "PRECIO_PROVISIONAL"
                preguntas.append(
                    Pregunta(
                        "cotizacion.precio_estado",
                        "El precio es PROVISIONAL y no se puede enviar fuera de "
                        "SANDBOX. ¿Se marca OFICIAL antes de enviar?",
                        ("Marcar OFICIAL", "No enviar todavía"),
                    )
                )
            agregar(
                "enviar_cotizacion_whatsapp",
                {
                    "cotizacion": "nueva",
                    "cliente_id": cliente.id if cliente else None,
                },
                depende=orden_cotizacion,
                bloqueo=bloqueo,
            )

    # ------------------------------------------------------------------
    # Tarea / recordatorio. No es una cotización: es un mensaje a una persona
    # (el maestro, el ingeniero, el cliente). El texto lo dicta Julio; el
    # compilador no lo redacta ni le agrega cifras.
    # ------------------------------------------------------------------
    hay_tarea = any(hecho.clave.startswith("tarea.") for hecho in hechos)
    if hay_tarea:
        contactos = _contactos(hechos)
        telefono_dictado = _texto(hechos, "tarea.telefono")
        nombre_tarea = _texto(hechos, "tarea.destinatario")
        # Si el modelo citó mal el nombre del destinatario, el contacto con el
        # mismo teléfono es la misma persona: se recupera sin inventar.
        if not nombre_tarea and telefono_dictado:
            digitos = re.sub(r"\D", "", telefono_dictado)
            for contacto in contactos:
                telefono = re.sub(r"\D", "", str(contacto.get("telefono") or ""))
                if telefono and telefono == digitos and contacto.get("nombre"):
                    nombre_tarea = str(contacto["nombre"])
                    break
        mensaje_tarea = _texto(hechos, "tarea.mensaje")
        cuando_tarea = _texto(hechos, "tarea.cuando")
        rol_interno = detectar_rol_interno(contexto.texto)
        intencion_tarea = detectar_intencion_tarea(
            contexto.texto, tiene_telefono=bool(telefono_dictado)
        )
        prioridad = detectar_prioridad(contexto.texto)

        # La intención manda; el teléfono solo limita la capacidad de enviar.
        # Sin verbo claro, un dictado de tarea se trata como envío salvo que
        # nombre un área o un encargo al equipo.
        if intencion_tarea is None:
            if rol_interno is not None or es_instruccion_interna(contexto.texto):
                intencion_tarea = "DELEGAR"
            else:
                intencion_tarea = "ENVIAR"
        enviar = intencion_tarea == "ENVIAR"
        delegar = intencion_tarea == "DELEGAR"
        telefono_tarea = telefono_dictado if enviar else None
        contacto_cliente = None

        # Enviar: si nombraron a un contacto del cliente, se usa su teléfono.
        # Si ese contacto no tiene teléfono, se pide: es un tercero y Gato no
        # puede mandar un WhatsApp a un nombre.
        if enviar and nombre_tarea and not telefono_tarea:
            contacto_cliente = _contacto_por_nombre(contactos, nombre_tarea)
            if contacto_cliente is not None:
                if contacto_cliente.get("telefono"):
                    telefono_tarea = str(contacto_cliente["telefono"])
                else:
                    preguntas.append(
                        Pregunta(
                            "tarea.telefono",
                            f"¿Cuál es el teléfono de "
                            f"{contacto_cliente.get('nombre') or nombre_tarea}?",
                        )
                    )
                    bloqueos = True
            else:
                preguntas.append(
                    Pregunta(
                        "tarea.telefono",
                        f"¿A qué número le envío el mensaje a {nombre_tarea}? "
                        "Sin número no puedo enviarlo; si prefieres, lo dejo "
                        "como tarea interna para secretaría.",
                    )
                )
                bloqueos = True

        # Enviar sin destinatario: un solo contacto con teléfono o se pregunta.
        if enviar and not telefono_tarea and not nombre_tarea:
            con_telefono = [
                contacto for contacto in contactos if contacto.get("telefono")
            ]
            if len(con_telefono) == 1:
                telefono_tarea = str(con_telefono[0]["telefono"])
            elif len(con_telefono) > 1:
                opciones = tuple(
                    str(contacto.get("nombre") or contacto.get("telefono"))
                    for contacto in con_telefono
                )
                preguntas.append(
                    Pregunta(
                        "tarea.destinatario",
                        "¿A quién le envío el recordatorio: "
                        + " o ".join(opciones)
                        + "?",
                        opciones,
                    )
                )
                bloqueos = True

        # Delegar: no se envía nada, aunque el dictado mencione un teléfono
        # (ese número es dato de contacto, no canal). La tarea vive en el panel.
        destino = telefono_tarea or nombre_tarea
        if not destino and not delegar and not any(
            p.clave == "tarea.destinatario" for p in preguntas
        ):
            preguntas.append(
                Pregunta(
                    "tarea.destinatario",
                    "¿A quién le envío el recordatorio? Necesito el número o el nombre.",
                )
            )
            bloqueos = True
        if not mensaje_tarea:
            preguntas.append(
                Pregunta(
                    "tarea.mensaje",
                    "¿Qué le digo exactamente en el recordatorio?",
                )
            )
            bloqueos = True
        # Una descripción del encargo no es el texto que recibe la persona.
        # No se redacta: se pide el mensaje final antes de programar.
        mensaje_final = mensaje_es_final(contexto.texto, mensaje_tarea)
        if mensaje_tarea and not delegar and not mensaje_final:
            preguntas.append(
                Pregunta(
                    "tarea.mensaje",
                    "¿Con qué texto exacto le envío el recordatorio? Lo dictado "
                    f"fue «{mensaje_tarea}»: eso describe el encargo, no el "
                    "mensaje que va a leer el destinatario.",
                )
            )
            bloqueos = True
        if delegar and mensaje_tarea:
            # La instrucción se guarda tal cual se dictó: no se redacta.
            rol_final = rol_interno or "SECRETARIA"
            persona = persona_dictada(nombre_tarea, rol_final)
            agregar(
                "crear_tarea_interna",
                {
                    "instruccion": mensaje_tarea,
                    "asignado_rol": rol_final,
                    "asignado_a": persona,
                    "cuando": cuando_tarea,
                    "prioridad": prioridad,
                    "ficha": _ficha_tarea(
                        hechos,
                        texto=contexto.texto,
                        mensaje=mensaje_tarea,
                        rol=rol_final,
                        persona=persona,
                        telefono_referencia=telefono_dictado,
                        cuando=cuando_tarea,
                    ),
                },
            )
        elif enviar and destino and mensaje_tarea:
            agregar(
                "crear_tarea_recordatorio",
                {
                    "destinatario": destino,
                    # `mensaje` es lo que se envía; `instruccion` es lo dictado.
                    # Sin mensaje final, la ejecución lo exige antes de enviar.
                    "mensaje": mensaje_tarea if mensaje_final else None,
                    "instruccion": mensaje_tarea,
                    "mensaje_por_confirmar": not mensaje_final,
                    "cuando": cuando_tarea or "ahora",
                    "adjuntar_factura": _booleano(
                        hechos, "tarea.adjuntar_factura"
                    ),
                    "programado_inferido": cuando_tarea is None,
                    # Cifras dictadas y sostenidas por cita en este encargo:
                    # la guarda de cifras del mensaje las acepta sin abrir la
                    # puerta a números que nadie dijo.
                    "cifras_autorizadas": sorted(
                        {
                            str(hecho.valor)
                            for hecho in hechos
                            if hecho.utilizable
                            and hecho.tipo in ("DECIMAL", "ENTERO")
                            and hecho.valor is not None
                        }
                    ),
                },
                # Si el destino es un nombre, el cliente tiene que existir
                # antes; con un teléfono dictado no hace falta.
                depende=orden_cliente if (nombre_tarea and not telefono_tarea) else None,
            )

    # ------------------------------------------------------------------
    # Encargo al expediente: no es una acción comercial, es trabajo interno.
    # ------------------------------------------------------------------
    condiciones = _condiciones(hechos, contexto.texto)
    expediente = next(
        (c for c in condiciones if c.clave == "expediente.completar"), None
    )
    if expediente is not None and not any(
        accion.nombre == "crear_tarea_interna" for accion in acciones
    ):
        instruccion = expediente.cita or expediente.texto
        agregar(
            "crear_tarea_interna",
            {
                "instruccion": instruccion,
                "asignado_rol": "SECRETARIA",
                "asignado_a": None,
                "cuando": None,
                "prioridad": "NORMAL",
                "ficha": _ficha_tarea(
                    hechos,
                    texto=contexto.texto,
                    mensaje=instruccion,
                    rol="SECRETARIA",
                    persona=None,
                    telefono_referencia=None,
                    cuando=None,
                    nota=expediente.texto,
                ),
            },
            depende=orden_cliente,
        )

    if bloqueos:
        estado = "REQUIERE_ACLARACION"
    elif acciones:
        estado = "PENDIENTE_CONFIRMACION"
    else:
        estado = "SIN_ACCIONES"

    return Borrador(
        estado=estado,
        intencion=intencion,
        acciones=tuple(acciones),
        preguntas=_sin_duplicados(preguntas),
        hechos=hechos,
        condiciones=condiciones,
    )


def _texto_del_grupo(
    grupo: Sequence[HechoCitado],
    segmentos: Sequence[Any],
    indice: int,
    texto_completo: str | None,
) -> str:
    """Texto propio del encargo: su tramo o, si no hay ordinales, sus citas.

    Nunca se usa el dictado completo cuando hay más de un encargo: esa era la
    vía por la que «secretaría» de un asunto teñía otro.
    """
    del_segmento = texto_de(segmentos, indice)
    if del_segmento:
        return del_segmento
    citas = [
        hecho.evidencia.cita
        for hecho in grupo
        if hecho.evidencia is not None and hecho.evidencia.cita
    ]
    if citas:
        return " ".join(dict.fromkeys(citas))
    return texto_completo or ""


def textos_por_encargo(
    hechos: Sequence[HechoCitado], texto: str | None
) -> dict[int, str]:
    segmentos = segmentar(texto or "")
    grupos: dict[int, list[HechoCitado]] = {}
    for hecho in hechos:
        grupos.setdefault(hecho.encargo, []).append(hecho)
    return {
        indice: _texto_del_grupo(grupo, segmentos, indice, texto)
        for indice, grupo in grupos.items()
    }


def compilar(
    hechos: Sequence[HechoCitado],
    contexto: Contexto,
    *,
    intencion: str = "MUTACION",
) -> Borrador:
    """Compila el dictado completo: un asunto por encargo, sin mezclarlos.

    Cada encargo se compila por separado con **su propio texto**, para que el
    léxico de uno (por ejemplo, «secretaría») no cambie la intención de otro.
    Luego se unen las acciones en un solo borrador, numeradas y etiquetadas.
    """
    hechos = tuple(hechos)
    segmentos = segmentar(contexto.texto or "")

    if intencion == "CONSULTA":
        return Borrador(
            "SIN_ACCIONES",
            "CONSULTA",
            hechos=hechos,
            encargos=(_resumen_encargo(1, segmentos, "SIN_ACCIONES"),),
        )
    if dictado_revocado(contexto.texto):
        # El hablante canceló el dictado completo: los hechos quedan como
        # constancia, pero no se propone ni se ejecuta nada.
        return Borrador(
            "SIN_ACCIONES",
            "MUTACION",
            hechos=hechos,
            encargos=(_resumen_encargo(1, segmentos, "SIN_ACCIONES"),),
        )

    grupos: dict[int, list[HechoCitado]] = {}
    for hecho in hechos:
        grupos.setdefault(hecho.encargo, []).append(hecho)
    if not grupos:
        # Sin hechos: se compila un asunto vacío para que las preguntas de
        # siempre («¿para qué cliente?») sigan apareciendo.
        grupos[1] = []

    # Un tramo sin mensaje de tarea puede ser un encargo al equipo que el
    # modelo no extrajo (o extrajo solo el destinatario). Se copia el tramo tal
    # cual, con su cita: no se redacta ni se inventa.
    sinteticos: list[HechoCitado] = []
    for segmento in segmentos:
        del_grupo = grupos.get(segmento.indice)
        if del_grupo is not None and any(
            h.clave == "tarea.mensaje" for h in del_grupo
        ):
            continue
        if not (
            detectar_rol_interno(segmento.texto)
            or es_instruccion_interna(segmento.texto)
        ):
            continue
        if del_grupo is None:
            del_grupo = []
            grupos[segmento.indice] = del_grupo
        hecho = HechoCitado(
            clave="tarea.mensaje",
            valor=segmento.texto,
            estado="EXTRAIDO",
            tipo="TEXTO",
            evidencia=Evidencia(
                cita=segmento.texto,
                sostiene=segmento.texto,
                crudo_inicio=segmento.inicio,
                crudo_fin=segmento.fin,
                start_ms=None,
                end_ms=None,
                confianza=None,
                hablante="SUPERADMIN",
            ),
            encargo=segmento.indice,
        )
        del_grupo.append(hecho)
        sinteticos.append(hecho)

    acciones: list[AccionPropuesta] = []
    preguntas: list[Pregunta] = []
    condiciones: list[Condicion] = []
    resumenes: list[EncargoResumen] = []
    division_dudosa = False
    if len(grupos) == 1:
        # Si no hubo separación pero el dictado trae varias instrucciones, no
        # se agrupan a ciegas: se pregunta antes de proponer nada.
        mensajes = [
            h
            for h in hechos
            if h.clave == "tarea.mensaje" and h.utilizable
        ]
        clientes = {
            str(h.valor)
            for h in hechos
            if h.clave == "cliente.nombre" and h.utilizable
        }
        if len(mensajes) > 1 or len(clientes) > 1:
            division_dudosa = True
            dichos = [
                h.evidencia.cita if h.evidencia is not None else str(h.valor)
                for h in mensajes
            ]
            detalle = "; ".join(f"«{d}»" for d in dict.fromkeys(dichos))
            preguntas.append(
                Pregunta(
                    "encargo.division",
                    "Escuché varias instrucciones mezcladas"
                    + (f": {detalle}" if detalle else "")
                    + ". ¿Son encargos distintos o es uno solo?",
                    ("Son encargos distintos", "Es uno solo"),
                )
            )

    for indice in sorted(grupos):
        grupo = grupos[indice]
        texto_grupo = _texto_del_grupo(grupo, segmentos, indice, contexto.texto)
        parcial = _compilar_asunto(
            grupo,
            replace(contexto, texto=texto_grupo),
            intencion=intencion,
        )
        base = len(acciones)
        ordenes: list[int] = []
        for accion in parcial.acciones:
            orden = base + accion.orden
            ordenes.append(orden)
            acciones.append(
                replace(
                    accion,
                    orden=orden,
                    depende_de=(
                        base + accion.depende_de if accion.depende_de else None
                    ),
                    encargo=indice,
                )
            )
        preguntas.extend(replace(p, encargo=indice) for p in parcial.preguntas)
        condiciones.extend(
            replace(c, encargo=indice) for c in parcial.condiciones
        )
        resumenes.append(
            EncargoResumen(
                encargo=indice,
                texto=(texto_grupo or "").strip()[:180],
                estado=parcial.estado,
                acciones=tuple(ordenes),
                preguntas=tuple(p.clave for p in parcial.preguntas),
            )
        )

    acciones = _unificar_clientes(acciones)

    if any(encargo.estado == "REQUIERE_ACLARACION" for encargo in resumenes):
        estado = "REQUIERE_ACLARACION"
    elif acciones:
        estado = "PENDIENTE_CONFIRMACION"
    else:
        estado = "SIN_ACCIONES"
    if division_dudosa:
        estado = "REQUIERE_ACLARACION"

    return Borrador(
        estado=estado,
        intencion=intencion,
        acciones=tuple(acciones),
        preguntas=tuple(preguntas),
        hechos=hechos + tuple(sinteticos),
        condiciones=tuple(condiciones),
        encargos=tuple(resumenes),
    )


def _resumen_encargo(
    indice: int, segmentos: Sequence[Any], estado: str
) -> EncargoResumen:
    texto = texto_de(segmentos, indice) or ""
    return EncargoResumen(encargo=indice, texto=texto.strip()[:180], estado=estado)


def _unificar_clientes(
    acciones: Sequence[AccionPropuesta],
) -> list[AccionPropuesta]:
    """Un mismo cliente no se propone dos veces si aparece en dos encargos."""
    primero_por_nombre: dict[str, int] = {}
    reemplazos: dict[int, int] = {}
    salida: list[AccionPropuesta] = []
    for accion in acciones:
        if accion.nombre == "crear_cliente":
            nombre = sin_tildes(str(accion.parametros.get("nombre") or "")).strip()
            if nombre in primero_por_nombre:
                reemplazos[accion.orden] = primero_por_nombre[nombre]
                continue
            primero_por_nombre[nombre] = accion.orden
        salida.append(accion)
    if not reemplazos:
        return salida
    unificadas: list[AccionPropuesta] = []
    orden = 0
    for accion in salida:
        orden += 1
        dependencia = accion.depende_de
        if dependencia in reemplazos:
            dependencia = reemplazos[dependencia]
        unificadas.append(
            replace(accion, orden=orden, depende_de=dependencia)
        )
    return unificadas


def acciones_permitidas(
    borrador: Borrador, rol: str | None
) -> tuple[AccionPropuesta, ...]:
    """Filtro de rol en el backend; el LLM no decide permisos."""
    if rol is None:
        return ()
    return tuple(
        accion for accion in borrador.acciones if rol in accion.rol_requerido
    )
