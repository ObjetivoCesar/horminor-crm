"""Pruebas del ejecutor del momento cero (crear_cliente)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.cerebro import ejecutores  # noqa: E402


class PoolFalso:
    def __init__(self, filas):
        self.filas = list(filas)
        self.consultas: list[tuple] = []

    async def fetchrow(self, sql, *args):
        self.consultas.append(args)
        return self.filas.pop(0) if self.filas else None


def test_datos_cliente_no_inventa_y_limpia() -> None:
    datos = ejecutores.datos_cliente(
        {
            "nombre": "  Constructora Prueba ",
            "cedula": "09-1234-5678",
            "telefono": "+593 99 000 0000",
            "ciudad": "",
            "referencia_obra": "  Vía Auca km 3 ",
        },
        "borrador-1",
    )
    assert datos["nombre"] == "Constructora Prueba"
    assert datos["cedula"] == "0912345678"
    assert datos["telefono_whatsapp"] == "593990000000"
    assert datos["ciudad"] is None
    assert datos["direccion_obra"] == "Vía Auca km 3"
    assert "borrador-1" in datos["notas"]


@pytest.mark.asyncio
async def test_crear_cliente_escribe_una_vez() -> None:
    pool = PoolFalso([{"id": "cli-1", "nombre": "Constructora Prueba"}])

    resultado = await ejecutores.crear_cliente_desde_accion(
        pool,
        parametros={"nombre": "Constructora Prueba", "telefono": "0990000000"},
        borrador_id="b-1",
    )

    assert resultado.estado == "OK"
    assert resultado.datos["id"] == "cli-1"
    assert resultado.datos["existente"] is False
    assert "Constructora Prueba" in (resultado.nota or "")


@pytest.mark.asyncio
async def test_cliente_repetido_devuelve_el_existente(monkeypatch) -> None:
    pool = PoolFalso([{"id": "cli-9", "nombre": "Ya Existe"}])

    async def duplicado(*args, **kwargs):
        raise HTTPException(status_code=409, detail="telefono_whatsapp ya registrado")

    monkeypatch.setattr(ejecutores, "crear_cliente", duplicado)

    resultado = await ejecutores.crear_cliente_desde_accion(
        pool,
        parametros={"nombre": "Otro Nombre", "telefono": "0990000000"},
        borrador_id="b-2",
    )

    assert resultado.estado == "OK"
    assert resultado.datos["existente"] is True
    assert resultado.datos["id"] == "cli-9"
    assert "no se creó un duplicado" in (resultado.nota or "").lower()


@pytest.mark.asyncio
async def test_sin_nombre_no_escribe_nada() -> None:
    pool = PoolFalso([])

    resultado = await ejecutores.crear_cliente_desde_accion(
        pool, parametros={"telefono": "0990000000"}, borrador_id="b-3"
    )

    assert resultado.estado == "ERROR"
    assert pool.consultas == []
