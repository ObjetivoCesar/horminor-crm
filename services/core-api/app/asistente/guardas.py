"""Guarda de cifras: ningún número del texto puede faltar en las fichas.

Acepta formato ecuatoriano/estadounidense ($63.619,60 y $63,619.60),
negativos (-$20.00), ignora códigos FC-210 y exige ficha para conteos.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .fichas import Ficha


class CifraNoVerificada(ValueError):
    def __init__(self, valores: list[str]) -> None:
        self.valores = valores
        super().__init__("Cifras sin ficha: " + ", ".join(valores))


_FC = re.compile(r"FC-\d{3}", re.IGNORECASE)
_MONEY = re.compile(r"-?\$[\d.,]+")
_QTY = re.compile(r"([\d.,]+)\s*(m³|m3|sacos?|litros?)", re.IGNORECASE)
_CLIENTES = re.compile(r"(\d+)\s+clientes?", re.IGNORECASE)


def _candidatos(crudo: str) -> set[Decimal]:
    limpio = crudo.replace("$", "").replace(" ", "").strip()
    negativo = limpio.startswith("-")
    limpio = limpio.lstrip("-")
    candidatos: set[Decimal] = set()

    if "," in limpio and "." in limpio:
        # US: 63,619.60 | EU: 63.619,60
        for texto in (limpio.replace(",", ""), limpio.replace(".", "").replace(",", ".")):
            try:
                candidatos.add(Decimal(texto))
            except InvalidOperation:
                pass
    elif "," in limpio:
        parte = limpio.split(",")[-1]
        if len(parte) in (1, 2):
            try:
                candidatos.add(Decimal(limpio.replace(".", "").replace(",", ".")))
            except InvalidOperation:
                pass
        try:
            candidatos.add(Decimal(limpio.replace(",", "")))
        except InvalidOperation:
            pass
    elif "." in limpio:
        parte = limpio.split(".")[-1]
        if len(parte) in (1, 2):
            try:
                candidatos.add(Decimal(limpio))
            except InvalidOperation:
                pass
        else:
            try:
                candidatos.add(Decimal(limpio.replace(".", "")))
            except InvalidOperation:
                pass
            try:
                candidatos.add(Decimal(limpio))
            except InvalidOperation:
                pass
    else:
        try:
            candidatos.add(Decimal(limpio))
        except InvalidOperation:
            pass

    if negativo:
        candidatos = {-c for c in candidatos}
    return candidatos


def _valores_de_fichas(fichas: list[Ficha]) -> set[Decimal]:
    valores: set[Decimal] = set()
    for f in fichas:
        if f.tipo_valor not in ("DECIMAL", "ENTERO"):
            continue
        if f.valor is None:
            continue
        try:
            valores.add(Decimal(str(f.valor)))
        except InvalidOperation:
            continue
    return valores


def _coincide(valor: Decimal, permitidos: set[Decimal]) -> bool:
    for p in permitidos:
        try:
            if abs(valor - p) <= Decimal("0.01"):
                return True
        except InvalidOperation:
            continue
    return False


def verificar(texto: str, fichas: list[Ficha]) -> None:
    permitidos = _valores_de_fichas(fichas)
    sin_codigos = _FC.sub(" ", texto)
    faltantes: list[str] = []

    for match in _MONEY.finditer(sin_codigos):
        crudo = match.group(0).rstrip(".,")
        if not any(_coincide(c, permitidos) for c in _candidatos(crudo)):
            faltantes.append(crudo)

    for match in _QTY.finditer(sin_codigos):
        crudo = match.group(1).rstrip(".,")
        if not any(_coincide(c, permitidos) for c in _candidatos(crudo)):
            faltantes.append(match.group(0))

    conteos = {int(f.valor) for f in fichas if f.dato == "clientes_con_saldo" and f.valor is not None}
    for match in _CLIENTES.finditer(sin_codigos):
        if int(match.group(1)) not in conteos:
            faltantes.append(match.group(0))

    if faltantes:
        raise CifraNoVerificada(faltantes)
