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


# Una frase que solo pide confirmar, avisar o coordinar con alguien no es un
# asunto aparte: pertenece al encargo anterior. Sin esta fusión, «confírmame
# con el chofer y con Julio» se partía en dos encargos vacíos y el dictado
# terminaba con siete preguntas.
_COORDINACION = re.compile(
    r"^\s*(?:y\s+)?(?:que\s+)?(?:me\s+)?"
    r"(conf[ií]rmame|confirmenme|conf[ií]rma|confirmen|"
    r"av[ií]same|av[ií]sale|coordina|coordinen|"
    r"llama|llamen|contacta|contacten|"
    r"dile|diles|preg[uú]ntale|preg[uú]ntenle)\b",
    re.IGNORECASE,
)
_CLAVES_COORDINACION = {
    "tarea.destinatario",
    "tarea.mensaje",
    "tarea.cuando",
    "tarea.telefono",
}
# «… y con Julio» continúa la coordinación anterior; no introduce un asunto.
_CONTINUACION = re.compile(r"^\s*y\s+(?:con|a|para)\s+", re.IGNORECASE)


def _es_coordinacion(grupo: Sequence[HechoCitado]) -> bool:
    """True si el grupo solo coordina con alguien, sin datos propios."""
    utiles = [hecho for hecho in grupo if hecho.utilizable]
    if not utiles:
        return False
    if any(hecho.clave not in _CLAVES_COORDINACION for hecho in utiles):
        return False
    citas = [
        hecho.evidencia.cita
        for hecho in utiles
        if hecho.evidencia is not None and hecho.evidencia.cita
    ]
    return bool(citas) and all(
        _COORDINACION.search(cita) or _CONTINUACION.search(cita)
        for cita in citas
    )


def fusionar_coordinaciones(
    hechos: Sequence[HechoCitado],
) -> list[HechoCitado]:
    """Une al encargo anterior las frases que solo confirman o coordinan.

    El extractor entiende paráfrasis, pero a veces cuenta cada destinatario de
    una misma frase como un encargo. Este guardia determinístico evita que una
    instrucción como «prepara la entrega… confírmame con el chofer y con Julio»
    se convierta en tres asuntos con preguntas repetidas. No separa nada: solo
    fusiona grupos que no aportan datos propios.
    """
    encargos = sorted({hecho.encargo for hecho in hechos})
    if len(encargos) <= 1:
        return list(hechos)

    grupos = {
        encargo: [hecho for hecho in hechos if hecho.encargo == encargo]
        for encargo in encargos
    }
    fusiones: dict[int, int] = {}
    anterior = encargos[0]
    for encargo in encargos[1:]:
        if _es_coordinacion(grupos[encargo]):
            fusiones[encargo] = anterior
        else:
            anterior = encargo

    if not fusiones:
        return list(hechos)

    def raiz(encargo: int) -> int:
        while encargo in fusiones:
            encargo = fusiones[encargo]
        return encargo

    unidos = [
        replace(hecho, encargo=raiz(hecho.encargo)) for hecho in hechos
    ]
    orden = sorted({hecho.encargo for hecho in unidos})
    mapa = {viejo: nuevo for nuevo, viejo in enumerate(orden, start=1)}
    return [replace(hecho, encargo=mapa[hecho.encargo]) for hecho in unidos]
