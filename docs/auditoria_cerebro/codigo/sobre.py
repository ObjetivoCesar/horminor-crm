"""Contrato del sobre de extracción que devuelve el LLM.

El modelo no devuelve acciones: devuelve hechos con una cita textual. El
compilador decide después si esos hechos se convierten en algo ejecutable.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

TIPOS = (
    "TEXTO",
    "ENTERO",
    "DECIMAL",
    "FECHA",
    "HORA",
    "TELEFONO",
    "CEDULA",
    "BOOLEANO",
)
ESTADOS = (
    "EXTRAIDO",
    "TENTATIVO",
    "NO_DIJO",
    "INAUDIBLE_NO_ENTENDI",
    "BAJA_CONFIANZA_STT",
    "CORREGIDO_EN_AUDIO",
)
HABLANTES = (
    "SUPERADMIN",
    "SECRETARIA",
    "VENDEDOR",
    "CONTADORA",
    "CHOFER",
    "CLIENTE",
    "TERCERO",
    "NO_DETERMINADO",
)


class HechoIn(BaseModel):
    clave: str = Field(min_length=1, max_length=80)
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
    cita: str | None = Field(default=None, max_length=500)
    # Asunto independiente al que pertenece el hecho. El modelo es el único
    # que entiende paráfrasis; el compilador valida el número y, si no es
    # fiable, pide aclaración en vez de agrupar a ciegas.
    encargo: int | None = Field(default=None, ge=1, le=8)
    hablante: Literal[
        "SUPERADMIN",
        "SECRETARIA",
        "VENDEDOR",
        "CONTADORA",
        "CHOFER",
        "CLIENTE",
        "TERCERO",
        "NO_DETERMINADO",
    ] = "NO_DETERMINADO"

    @field_validator("cita")
    @classmethod
    def _cita_limpia(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        limpio = " ".join(valor.split())
        return limpio or None


class SobreIn(BaseModel):
    intencion: Literal["MUTACION", "CONSULTA", "MIXTA"] = "MUTACION"
    hechos: list[HechoIn] = Field(default_factory=list)
    faltantes: list[str] = Field(default_factory=list)
    ambiguedades: list[str] = Field(default_factory=list)
    preguntas: list[str] = Field(default_factory=list)

    @field_validator("faltantes", "ambiguedades", "preguntas")
    @classmethod
    def _lista_limpia(cls, valores: list[str]) -> list[str]:
        salida: list[str] = []
        for valor in valores:
            limpio = " ".join(str(valor).split())
            if limpio and limpio not in salida:
                salida.append(limpio)
        return salida[:3]


def validar_sobre(payload: Any) -> SobreIn:
    if not isinstance(payload, dict):
        raise ValueError("el sobre debe ser un objeto JSON")
    return SobreIn.model_validate(payload)
