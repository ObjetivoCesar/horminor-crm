"""Segmentación de un dictado en encargos independientes.

Un mismo audio puede traer varias instrucciones («primero… segundo…
tercero…»). El motor anterior trataba el dictado como un solo asunto: los
hechos de dos encargos se pisaban y el texto completo contaminaba la lectura de
cada uno (por ejemplo, «secretaría» de un encargo convertía otro recordatorio
externo en tarea interna).

Este módulo no interpreta: solo corta el texto por conectores ordinales y
asigna cada hecho al tramo donde está su cita. Si no hay marcas, hay un solo
encargo y todo sigue como antes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Sequence

from .hechos import HechoCitado

# Los conectores deben abrir oración: «Primero, … Segundo, … Y tercero, …».
# «también» y «además» no cortan porque suelen aparecer dentro de una frase.
_MARCA = re.compile(
    r"(?:^|(?<=[.;:\n]))\s*(?:y\s+|luego\s+|despues\s+)?"
    r"(primero|segundo|tercero|cuarto|quinto|por\s+[uú]ltimo|finalmente)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Segmento:
    indice: int
    inicio: int
    fin: int
    texto: str


def segmentar(texto: str) -> tuple[Segmento, ...]:
    """Corta el dictado por ordinales. Sin marcas devuelve un solo tramo."""
    texto = texto or ""
    marcas = [
        (m.start(), m.end())
        for m in _MARCA.finditer(texto)
        # Dos marcas en el mismo punto (o solapadas) no aportan un corte.
        if m.start() < m.end()
    ]
    if len(marcas) <= 1:
        limpio = texto.strip()
        return (Segmento(1, 0, len(texto), limpio),)

    # El texto anterior al primer ordinal es preámbulo («tengo tres cosas
    # pendientes»): no es un encargo y no se compila solo.
    segmentos: list[Segmento] = []
    for posicion, (inicio, _fin_marca) in enumerate(marcas):
        fin = marcas[posicion + 1][0] if posicion + 1 < len(marcas) else len(texto)
        tramo = texto[inicio:fin].strip(" ,;\n\t")
        if not tramo:
            continue
        segmentos.append(
            Segmento(
                indice=len(segmentos) + 1,
                inicio=inicio,
                fin=fin,
                texto=tramo,
            )
        )
    return tuple(segmentos) or (Segmento(1, 0, len(texto), texto.strip()),)


def texto_de(segmentos: Sequence[Segmento], indice: int) -> str | None:
    for segmento in segmentos:
        if segmento.indice == indice:
            return segmento.texto
    return None


def asignar(
    hechos: Sequence[HechoCitado], segmentos: Sequence[Segmento]
) -> list[HechoCitado]:
    """Fija el encargo de cada hecho.

    Manda la separación que propuso el extractor (es el único que entiende
    paráfrasis). Los ordinales son solo el respaldo determinístico: si el
    modelo dijo que todo es un encargo pero el dictado dice «primero… segundo…»,
    se corta por posición.
    """
    propuestos = sorted({h.encargo for h in hechos})
    if len(propuestos) > 1:
        # Se renumera 1..N para que no queden huecos (1 y 3 -> 1 y 2).
        mapa = {viejo: nuevo for nuevo, viejo in enumerate(propuestos, start=1)}
        return [replace(h, encargo=mapa[h.encargo]) for h in hechos]

    if len(segmentos) <= 1:
        return [replace(h, encargo=1) for h in hechos]

    salida: list[HechoCitado] = []
    for hecho in hechos:
        inicio = (
            hecho.evidencia.crudo_inicio if hecho.evidencia is not None else None
        )
        encargo = 1
        if inicio is not None:
            for segmento in segmentos:
                if segmento.inicio <= inicio < segmento.fin:
                    encargo = segmento.indice
                    break
        salida.append(replace(hecho, encargo=encargo))
    return salida
