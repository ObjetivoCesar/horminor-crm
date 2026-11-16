"""Referencia del experimento: carga y adaptación.

La guía entregada es PRELIMINAR y NO HUMANA. Este módulo la marca como no
validada y la convierte a tipos de orden gruesos solo para probar el arnés.
La referencia definitiva debe ser la interpretación humana revisada.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .contracts import TIPOS_ORDEN, plano

CORPUS = Path(__file__).resolve().parents[2] / "docs" / "HORMINOR_CORPUS_D_VS_DMAS_40"
ARCHIVO_CORPUS = CORPUS / "corpus_nuevo_40.jsonl"
ARCHIVO_REFERENCIA = CORPUS / "guia_referencia_preliminar_NO_HUMANA.jsonl"

_MAPA = {
    "delegar": "DELEGAR",
    "verificar": "VERIFICAR",
    "revisar": "VERIFICAR",
    "consultar": "CONSULTAR",
    "informe": "CONSULTAR",
    "enviar": "ENVIAR_MENSAJE",
    "recordar": "ENVIAR_MENSAJE",
    "cotizar": "COTIZAR",
    "llamar": "LLAMAR",
    "coordinar": "COORDINAR",
    "registrar": "REGISTRAR",
    "constancia": "CONSTANCIA",
}


@dataclass
class Caso:
    id: str
    categoria: str
    dictado: str


@dataclass
class ReferenciaCaso:
    id: str
    tipos: Counter = field(default_factory=Counter)
    prohibidas: list[str] = field(default_factory=list)
    validada: bool = False
    fuente: str = "preliminar_no_humana"
    crudo: list[str] = field(default_factory=list)


def cargar_corpus(ruta: Path | None = None) -> list[Caso]:
    ruta = ruta or ARCHIVO_CORPUS
    casos: list[Caso] = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        datos = json.loads(linea)
        casos.append(
            Caso(
                id=str(datos["id"]),
                categoria=str(datos.get("categoria") or ""),
                dictado=str(datos["dictado"]),
            )
        )
    return casos


def _tipo_de(frase: str) -> str | None:
    texto = plano(frase)
    for palabra, tipo in _MAPA.items():
        if re.search(rf"\b{palabra}", texto):
            return tipo
    for tipo in TIPOS_ORDEN:
        if plano(tipo) in texto:
            return tipo
    return None


def cargar_referencia(ruta: Path | None = None) -> dict[str, ReferenciaCaso]:
    """Carga referencia preliminar o estructurada (revisión humana).

    Estructurada: {"id","ordenes":[{"tipo":...}],"prohibidas":[],"revisor_1":...}
    Preliminar:  {"id","esperado_preliminar":[frases],"acciones_prohibidas":[]}
    """
    ruta = ruta or ARCHIVO_REFERENCIA
    salida: dict[str, ReferenciaCaso] = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        datos = json.loads(linea)
        if "ordenes" in datos:
            caso = ReferenciaCaso(
                id=str(datos["id"]),
                prohibidas=[str(x) for x in datos.get("prohibidas") or []],
                validada=bool(str(datos.get("revisor_1") or "").strip()),
                fuente="humana" if datos.get("revisor_1") else "estructurada_sin_firmar",
            )
            for orden in datos.get("ordenes") or []:
                tipo = str(orden.get("tipo") or "").upper()
                if tipo in TIPOS_ORDEN:
                    caso.tipos[tipo] += 1
            salida[caso.id] = caso
            continue

        caso = ReferenciaCaso(
            id=str(datos["id"]),
            prohibidas=[str(x) for x in datos.get("acciones_prohibidas") or []],
            crudo=[str(x) for x in datos.get("esperado_preliminar") or []],
            validada=False,
            fuente="preliminar_no_humana",
        )
        for frase in caso.crudo:
            tipo = _tipo_de(frase)
            if tipo:
                caso.tipos[tipo] += 1
        salida[caso.id] = caso
    return salida


def comparar(esperados: Counter, propuestos: Counter) -> dict[str, int]:
    omitidas = sum(max(0, esperados[t] - propuestos[t]) for t in esperados)
    duplicadas = sum(
        max(0, propuestos[t] - esperados[t]) for t in esperados if propuestos[t] > esperados[t]
    )
    inventadas = sum(propuestos[t] for t in propuestos if t not in esperados)
    coinciden = sum(min(esperados[t], propuestos[t]) for t in esperados)
    return {
        "coinciden": coinciden,
        "omitidas": omitidas,
        "inventadas": inventadas,
        "duplicadas": duplicadas,
        "esperadas": sum(esperados.values()),
        "propuestas": sum(propuestos.values()),
    }
