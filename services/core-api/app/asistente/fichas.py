"""Fichas de dato y resultados del bibliotecario (contrato v1.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Ficha:
    ficha_id: str
    consulta_id: str
    dato: str
    valor: Any
    tipo_valor: str
    unidad: str | None
    fuente_vista_tabla: list[str]
    filtros_aplicados: dict[str, Any]
    consultado_en: str
    vacio: bool
    nota: str | None
    vigencia_hash: str | None
    esquema_version: str = "1.1.0"

    def a_dict(self) -> dict[str, Any]:
        return {
            "ficha_id": self.ficha_id,
            "consulta_id": self.consulta_id,
            "dato": self.dato,
            "valor": self.valor,
            "tipo_valor": self.tipo_valor,
            "unidad": self.unidad,
            "fuente_vista_tabla": self.fuente_vista_tabla,
            "filtros_aplicados": self.filtros_aplicados,
            "consultado_en": self.consultado_en,
            "vacio": self.vacio,
            "nota": self.nota,
            "vigencia_hash": self.vigencia_hash,
            "esquema_version": self.esquema_version,
        }


def ficha(
    consulta_id: str,
    dato: str,
    valor: Any,
    *,
    unidad: str | None = None,
    fuente: list[str] | None = None,
    filtros: dict[str, Any] | None = None,
    tipo_valor: str = "DECIMAL",
    vacio: bool = False,
    nota: str | None = None,
    vigencia_hash: str | None = None,
) -> Ficha:
    return Ficha(
        ficha_id=str(uuid4()),
        consulta_id=consulta_id,
        dato=dato,
        valor=valor,
        tipo_valor=tipo_valor,
        unidad=unidad,
        fuente_vista_tabla=fuente or [],
        filtros_aplicados=filtros or {},
        consultado_en=_iso(),
        vacio=vacio,
        nota=nota,
        vigencia_hash=vigencia_hash,
    )


ESTADOS = (
    "OK",
    "VACIO",
    "FALTA_PARAMETRO",
    "ACL",
    "PROPUESTA",
    "NO_CONECTADA",
    "ERROR",
)


@dataclass
class Resultado:
    consulta_id: str
    estado: str
    datos: Any = None
    fichas: list[Ficha] = field(default_factory=list)
    fuente: list[str] = field(default_factory=list)
    filtros: dict[str, Any] = field(default_factory=dict)
    consultado_en: str = field(default_factory=_iso)
    nota: str | None = None
    parametro_faltante: str | None = None

    @property
    def ok(self) -> bool:
        return self.estado == "OK"

    @property
    def vacio(self) -> bool:
        return self.estado == "VACIO"
