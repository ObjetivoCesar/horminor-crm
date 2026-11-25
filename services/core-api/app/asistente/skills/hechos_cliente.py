"""Hechos del cliente: lo que el extractor entendió y NO tiene columna propia.

Se escribe en client_facts (append-only) sin confirmación: no mueve dinero, no
sale a terceros y se anota a la vista («Anoté en la ficha…»). Solo con cliente
EXISTENTE y atribuido por encargo: si un audio habla de dos clientes, cada
hecho va exclusivamente al dueño de su encargo.
Solo hechos firmes: nunca TENTATIVO ni INFERIDO.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from ...cerebro.compilador import ClienteResuelto, dictado_revocado
from ...cerebro.hechos import HechoCitado

FIRMES = ("EXTRAIDO", "CORREGIDO_EN_AUDIO", "CORREGIDO_POR_HUMANO")
HABLANTES_FACT = {
    "CLIENTE",
    "SUPERADMIN",
    "SECRETARIA",
    "VENDEDOR",
    "CHOFER",
    "TERCERO",
    "NO_DETERMINADO",
}
_VACIAS = {
    "de",
    "del",
    "la",
    "el",
    "los",
    "las",
    "y",
    "don",
    "dona",
    "sr",
    "sra",
    "ing",
    "inge",
}


@dataclass(frozen=True)
class FilaHecho:
    cliente_id: str
    categoria: str
    hablante: str
    texto: str
    hash: str
    fecha_evento: date | None
    provenance: Mapping[str, Any]
    confianza: Decimal


def _plano(t: Any) -> str:
    b = unicodedata.normalize("NFD", str(t or "").lower())
    return "".join(c for c in b if unicodedata.category(c) != "Mn")


def _compatibles(dicho: str, registrado: str) -> bool:
    a = {t for t in re.findall(r"[a-z0-9]+", _plano(dicho)) if t not in _VACIAS}
    b = {t for t in re.findall(r"[a-z0-9]+", _plano(registrado)) if t not in _VACIAS}
    if not a or not b:
        return True
    corto, largo = (a, b) if len(a) <= len(b) else (b, a)
    return corto <= largo


def _hablante(h: HechoCitado, defecto: str) -> str:
    v = h.evidencia.hablante if h.evidencia else defecto
    return v if v in HABLANTES_FACT else "NO_DETERMINADO"


def _confianza(h: HechoCitado) -> Decimal:
    ev = h.evidencia
    if ev is not None and ev.confianza is not None:
        return Decimal(str(ev.confianza)).quantize(Decimal("0.001"))
    return Decimal("1.000") if ev is None or ev.start_ms is None else Decimal("0.500")


def _fila(
    cliente: ClienteResuelto,
    categoria: str,
    texto: str,
    hechos: Sequence[HechoCitado],
    fuente: str,
    fecha: date | None,
    defecto: str,
) -> FilaHecho:
    base = f"{categoria}|{texto}|{fecha.isoformat() if fecha else ''}|{fuente}"
    prov = {
        "claves": [h.clave for h in hechos],
        "citas": [h.evidencia.cita for h in hechos if h.evidencia],
        "encargo": hechos[0].encargo,
        "fuente": fuente,
    }
    return FilaHecho(
        str(cliente.id),
        categoria,
        _hablante(hechos[0], defecto),
        texto,
        hashlib.sha256(base.encode("utf-8")).hexdigest(),
        fecha,
        prov,
        min(_confianza(h) for h in hechos),
    )


def planificar(
    hechos: Sequence[HechoCitado],
    *,
    clientes: Mapping[int, ClienteResuelto],
    texto: str | None,
    fuente: str,
    hoy: date,
    hablante_defecto: str = "NO_DETERMINADO",
) -> list[FilaHecho]:
    if dictado_revocado(texto):
        return []
    firmes = [h for h in hechos if h.estado in FIRMES and h.valor not in (None, "")]
    filas: list[FilaHecho] = []
    for encargo, cliente in sorted(clientes.items()):
        if cliente is None or not cliente.id:
            continue
        del_encargo = [h for h in firmes if h.encargo == encargo]
        if not del_encargo:
            continue
        nombre = next((str(h.valor) for h in del_encargo if h.clave == "cliente.nombre"), None)
        if nombre and not _compatibles(nombre, cliente.nombre):
            continue
        for h in del_encargo:
            if h.clave == "cliente.referencia":
                filas.append(
                    _fila(
                        cliente,
                        "REFERENCIA_OBRA",
                        f"Referencia de obra: {h.valor}",
                        [h],
                        fuente,
                        None,
                        hablante_defecto,
                    )
                )
        for sufijo in ("", ".2", ".3", ".4"):
            grupo = [
                h
                for h in del_encargo
                if h.clave.startswith(f"contacto{sufijo}.")
                and h.clave.count(".") == (1 if not sufijo else 2)
            ]
            if not grupo:
                continue
            campo = {h.clave.rsplit(".", 1)[1]: str(h.valor) for h in grupo}
            partes = campo.get("nombre") or "contacto"
            if campo.get("rol"):
                partes += f" ({campo['rol']})"
            if campo.get("telefono"):
                partes += f", {campo['telefono']}"
            filas.append(
                _fila(
                    cliente,
                    "DATO_CONTACTO",
                    f"Contacto de obra: {partes}",
                    grupo,
                    fuente,
                    None,
                    hablante_defecto,
                )
            )
        monto = next((h for h in del_encargo if h.clave == "pago.monto"), None)
        recibido = next((h for h in del_encargo if h.clave == "pago.recibido"), None)
        if monto and recibido and recibido.valor is False:
            try:
                valor = Decimal(str(monto.valor)).quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError):
                continue
            filas.append(
                _fila(
                    cliente,
                    "COMPROMISO_PAGO",
                    f"Compromiso de pago: {valor} USD, aún sin recibir",
                    [monto, recibido],
                    fuente,
                    hoy,
                    hablante_defecto,
                )
            )
    return filas


async def registrar(
    db: Any,
    filas: Sequence[FilaHecho],
    *,
    extraccion_id: str | None,
    creado_por: str,
) -> list[dict[str, str]]:
    """INSERT idempotente (uq cliente+categoria+hash). Devuelve lo anotado."""
    anotados: list[dict[str, str]] = []
    for f in filas:
        fila = await db.fetchrow(
            """
            INSERT INTO client_facts (cliente_id, extraccion_id, categoria,
                   hablante_atribuido, hecho_texto, hecho_hash, fecha_evento,
                   provenance_json, confianza, creado_por)
            VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8::jsonb, $9, $10)
            ON CONFLICT (cliente_id, categoria, hecho_hash) DO NOTHING
            RETURNING id::text AS id
            """,
            f.cliente_id,
            extraccion_id,
            f.categoria,
            f.hablante,
            f.texto,
            f.hash,
            f.fecha_evento,
            json.dumps(f.provenance, ensure_ascii=False, default=str),
            f.confianza,
            creado_por,
        )
        if fila:
            anotados.append({"id": fila["id"], "cliente_id": f.cliente_id, "texto": f.texto})
    return anotados


def nota_de_registro(
    anotados: Sequence[Mapping[str, str]],
    *,
    nombres_por_cliente: Mapping[str, str] | None = None,
    cliente_nombre: str | None = None,
) -> str | None:
    if not anotados:
        return None
    agrupado: dict[str, list[str]] = {}
    for a in anotados:
        cid = str(a.get("cliente_id") or "")
        nombre = (
            (nombres_por_cliente or {}).get(cid)
            or cliente_nombre
            or "el cliente"
        )
        agrupado.setdefault(nombre, []).append(a["texto"])
    partes = [
        f"Anoté en la ficha de {nombre}: " + "; ".join(textos) + "."
        for nombre, textos in agrupado.items()
    ]
    return " ".join(partes)
