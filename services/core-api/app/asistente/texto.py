"""Utilidades de texto del Gato."""

from __future__ import annotations

import unicodedata
from datetime import date, timedelta


def normalizar(texto: str) -> str:
    base = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in base if unicodedata.category(c) != "Mn")


def fecha_de(texto: str) -> date | None:
    t = normalizar(texto)
    if "ayer" in t:
        return date.today() - timedelta(days=1)
    if "manana" in t:
        return date.today() + timedelta(days=1)
    if "hoy" in t or "ahora" in t:
        return date.today()
    return None


def extraer_cliente(texto: str) -> str | None:
    t = normalizar(texto).strip(" ?¿.!")
    for marca in ("cliente ", "como va ", "ficha de ", "cupo de ", "debe ", "de "):
        if marca in t:
            resto = t.split(marca, 1)[1].strip(" ?¿.!")
            resto = resto.split(" y ", 1)[0].strip(" ?¿.!")
            if resto:
                return resto
    return None
