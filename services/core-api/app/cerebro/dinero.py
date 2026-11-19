"""¿El dictado dice que el dinero YA entró? Una sola respuesta para todos.

Registrar un abono toca caja y cartera: no se hace porque el modelo lo afirme.
Solo se hace si el audio habla en pasado («ya me depositó», «nos transfirió»).
Este módulo lo usan el compilador (para decidir si propone el abono) y el
resumen que se le lee a Julio (para no decir «ya entró» cuando está en duda).
"""

from __future__ import annotations

import unicodedata
from decimal import Decimal
from typing import Sequence

from .hechos import HechoCitado

# Marcas de dinero que ya entró.
PAGO_EN_PASADO = (
    "ya me",
    "ya nos",
    "ya le",
    "ya lo",
    "me acaba de dar",
    "nos acaba de dar",
    "me acaba de pagar",
    "me acaba de transferir",
    "me dio",
    "nos dio",
    "recibi",
    "recibimos",
    "me deposito",
    "nos deposito",
    "me transfirio",
    "nos transfirio",
    "me pago",
    "nos pago",
    "cancelo",
    "entro el",
    "entro la",
    "ingreso el",
    "abono recibido",
    "pago recibido",
)


def sin_tildes(texto: object) -> str:
    base = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in base if unicodedata.category(c) != "Mn")


def _ventanas(texto: str, buscado: str, margen: int = 120) -> list[str]:
    salida: list[str] = []
    if not buscado:
        return salida
    inicio = texto.find(buscado)
    while inicio >= 0:
        salida.append(texto[max(0, inicio - margen) : inicio + len(buscado) + margen])
        inicio = texto.find(buscado, inicio + 1)
    return salida


def dinero_ya_entro(
    hechos: Sequence[HechoCitado],
    texto: str | None = None,
    monto: Decimal | None = None,
) -> bool:
    """True solo si el dictado habla del dinero en pasado.

    La cita de un monto numérico es solo la cifra, así que también se mira la
    frase del texto normalizado alrededor de esa cifra. Sin esta lectura, un
    «nos van a transferir» se confundiría con dinero ya recibido.
    """
    fragmentos: list[str] = []
    for hecho in hechos:
        if hecho.clave in ("pago.recibido", "pago.monto", "pago.forma"):
            if hecho.evidencia is not None:
                fragmentos.append(
                    f"{hecho.evidencia.cita} {hecho.evidencia.sostiene}"
                )

    plano = sin_tildes(texto or "")
    if plano and monto is not None:
        cifra = format(monto.normalize(), "f")
        candidatos = {cifra, cifra.rstrip("0").rstrip(".") if "." in cifra else cifra}
        for buscado in candidatos:
            if len(buscado) >= 2:
                fragmentos.extend(_ventanas(plano, buscado))

    for fragmento in fragmentos:
        limpio = sin_tildes(fragmento)
        if any(marca in limpio for marca in PAGO_EN_PASADO):
            return True
    return False
