"""Contratos del experimento D vs D+. Congelado: contracts-1.0.

No importa ni modifica el motor productivo. Solo define estructuras y
validaciones para comparar lecturas.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, Field

CONTRACT_VERSION = "contracts-1.0"

TIPOS_ORDEN = (
    "COTIZAR",
    "ENVIAR_MENSAJE",
    "DELEGAR",
    "VERIFICAR",
    "REGISTRAR",
    "CONSTANCIA",
    "CONSULTAR",
    "LLAMAR",
    "COORDINAR",
)
CANALES = ("WHATSAPP", "LLAMADA", "CRM", "PRESENCIAL", "NINGUNO")
AMBITOS = ("INTERNO", "EXTERNO", "MIXTO")
EJECUTORES = ("HUMANO", "MODULO_CRM")
TIPOS_RESTRICCION = (
    "PROHIBICION",
    "CONDICION",
    "DEPENDENCIA",
    "PLAZO",
    "RECTIFICACION",
    "REVOCACION",
    "ACLARACION",
)
ALCANCES = ("ORDEN", "ASUNTO", "GLOBAL")
TIPOS_REFERENCIA = ("DIRECTO", "DEMOSTRATIVO", "ORDINAL", "ANAFORA", "IMPLICITO")

ESTADOS_ORDEN = (
    "LISTA",
    "INCOMPLETA",
    "BLOQUEADA",
    "RECHAZADA",
    "POR_ACLARAR",
)


def plano(texto: str | None) -> str:
    base = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in base if unicodedata.category(c) != "Mn").lower()


class Cita(BaseModel):
    texto: str = Field(min_length=1, max_length=500)


class HechoExp(BaseModel):
    clave: str
    valor: str | int | float | bool | None = None
    tipo: Literal[
        "TEXTO",
        "ENTERO",
        "DECIMAL",
        "FECHA",
        "HORA",
        "TELEFONO",
        "CEDULA",
        "BOOLEANO",
    ] = "TEXTO"
    estado: Literal[
        "EXTRAIDO",
        "TENTATIVO",
        "NO_DIJO",
        "INAUDIBLE_NO_ENTENDI",
        "BAJA_CONFIANZA_STT",
        "CORREGIDO_EN_AUDIO",
    ] = "EXTRAIDO"
    cita: str | None = None
    hablante: str = "NO_DETERMINADO"


class SobreHechos(BaseModel):
    hechos: list[HechoExp] = Field(default_factory=list)
    faltantes: list[str] = Field(default_factory=list)
    ambiguedades: list[str] = Field(default_factory=list)


class OrdenPropuesta(BaseModel):
    asunto: str = Field(min_length=1, max_length=40)
    tipo: Literal[
        "COTIZAR",
        "ENVIAR_MENSAJE",
        "DELEGAR",
        "VERIFICAR",
        "REGISTRAR",
        "CONSTANCIA",
        "CONSULTAR",
        "LLAMAR",
        "COORDINAR",
    ]
    # Quién hace el trabajo (rol o persona). No es a quién se le escribe.
    responsable_ejecucion: str | None = None
    # Quién recibe la comunicación, si la hay.
    destinatario_comunicacion: str | None = None
    ambito: Literal["INTERNO", "EXTERNO", "MIXTO"] = "INTERNO"
    medio: Literal["WHATSAPP", "LLAMADA", "CRM", "PRESENCIAL", "NINGUNO"] = "NINGUNO"
    ejecutor: Literal["HUMANO", "MODULO_CRM"] = "HUMANO"
    datos_requeridos: list[str] = Field(default_factory=list)
    citas: list[str] = Field(default_factory=list)
    confianza: float = Field(default=0.5, ge=0, le=1)


class AsuntoPropuesto(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    citas: list[str] = Field(default_factory=list)


class SobreOrdenes(BaseModel):
    asuntos: list[AsuntoPropuesto] = Field(default_factory=list)
    ordenes: list[OrdenPropuesta] = Field(default_factory=list)


class RestriccionPropuesta(BaseModel):
    tipo: Literal[
        "PROHIBICION",
        "CONDICION",
        "DEPENDENCIA",
        "PLAZO",
        "RECTIFICACION",
        "REVOCACION",
        "ACLARACION",
    ]
    alcance: Literal["ORDEN", "ASUNTO", "GLOBAL"] = "ASUNTO"
    sujeto: str | None = None
    referente_texto: str | None = None
    referente_tipo: Literal[
        "DIRECTO", "DEMOSTRATIVO", "ORDINAL", "ANAFORA", "IMPLICITO"
    ] = "DIRECTO"
    antes_de: str | None = None
    texto: str | None = None
    citas: list[str] = Field(default_factory=list)
    ambiguo: bool = False


class SobreRestricciones(BaseModel):
    restricciones: list[RestriccionPropuesta] = Field(default_factory=list)
    rectificaciones: list[RestriccionPropuesta] = Field(default_factory=list)


class SobreUnico(BaseModel):
    """Salida del brazo D: órdenes y restricciones en una sola lectura."""

    asuntos: list[AsuntoPropuesto] = Field(default_factory=list)
    ordenes: list[OrdenPropuesta] = Field(default_factory=list)
    restricciones: list[RestriccionPropuesta] = Field(default_factory=list)
    rectificaciones: list[RestriccionPropuesta] = Field(default_factory=list)


class Hallazgo(BaseModel):
    codigo: str
    detalle: str
    orden: int | None = None
    cita: str | None = None


class OrdenConciliada(BaseModel):
    indice: int
    asunto: str
    tipo: str
    responsable_ejecucion: str | None = None
    destinatario_comunicacion: str | None = None
    ambito: str = "INTERNO"
    medio: str = "NINGUNO"
    ejecutor: str = "HUMANO"
    datos_requeridos: list[str] = Field(default_factory=list)
    citas: list[str] = Field(default_factory=list)
    hechos: dict[str, Any] = Field(default_factory=dict)
    restricciones: list[str] = Field(default_factory=list)
    estado: str = "LISTA"
    motivo_estado: str | None = None


class ResultadoConciliacion(BaseModel):
    ordenes: list[OrdenConciliada] = Field(default_factory=list)
    conflictos: list[Hallazgo] = Field(default_factory=list)
    hallazgos: list[Hallazgo] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Utilidades determinísticas
# ---------------------------------------------------------------------------
_GLOBALES = (
    "no hagas nada",
    "no hagan nada",
    "ninguna de esas",
    "nada de eso",
    "todo queda suspendido",
    "todo suspendido",
    "no se autoriza nada",
    "quedan suspendidas",
)

_SOPORTE: dict[str, tuple[str, ...]] = {
    "COTIZAR": ("cotiz", "prepar", "preparen", "prepara"),
    "ENVIAR_MENSAJE": (
        "enviar",
        "envia",
        "envie",
        "mandar",
        "manda",
        "mande",
        "whatsapp",
        "mensaje",
        "recordatorio",
        "avisa",
        "avise",
        "notifica",
    ),
    "DELEGAR": (
        "que ",
        "encarg",
        "revis",
        "verific",
        "confirm",
        "coordine",
        "coordinen",
        "gestione",
        "gestionen",
        "prepare",
        "preparen",
    ),
    "VERIFICAR": ("revis", "verific", "confirm", "comprueb", "cheque"),
    "REGISTRAR": ("registr", "anot", "asient"),
    "CONSTANCIA": ("constancia", "dejar registro", "quede constancia"),
    "CONSULTAR": ("?", "cuanto", "cuantos", "cual", "cuales", "como", "saber", "informe", "informen"),
    "LLAMAR": ("llamar", "llame", "llamen", "telefon"),
    "COORDINAR": ("coordine", "coordinen", "coordinacion", "coordinar"),
}

_ANAFORAS = (
    "eso",
    "esto",
    "lo anterior",
    "lo mismo",
    "dicho",
    "esa",
    "ese",
    "aquella",
    "aquel",
    "lo primero",
    "lo segundo",
    "lo tercero",
)


def cita_en_texto(cita: str, texto: str) -> tuple[int, int] | None:
    """Posición de la cita en el texto normalizado (exacta; si no, normalizada)."""
    if not cita:
        return None
    pos = texto.find(cita)
    if pos >= 0:
        return (pos, pos + len(cita))
    buscada = plano(cita).strip()
    if not buscada:
        return None
    pos = plano(texto).find(buscada)
    if pos < 0:
        return None
    return (pos, pos + len(cita))


def sostiene(tipo: str, cita: str) -> bool:
    """¿La cita justifica el tipo de orden? No basta con que exista la palabra."""
    texto = plano(cita)
    marcas = _SOPORTE.get(tipo, ())
    if not marcas:
        return False
    if tipo == "CONSULTAR":
        return ("?" in cita) or any(m in texto for m in marcas if m != "?")
    return any(m in texto for m in marcas)


def es_global(cita: str) -> bool:
    texto = plano(cita)
    return any(m in texto for m in _GLOBALES)


def es_anafora(texto: str | None) -> bool:
    plano_txt = plano(texto)
    return any(a in plano_txt for a in _ANAFORAS)


def normalizar_orden_tipo(valor: str) -> str | None:
    v = plano(valor).upper()
    return v if v in TIPOS_ORDEN else None
