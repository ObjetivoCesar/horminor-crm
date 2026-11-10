"""Configuracion operativa v6.2: caja chica y horarios de agenda.

Vive aparte de las 7 secciones historicas para no mezclar contratos. Lee y
escribe ``system_settings`` en caliente; el panel y el Gate consultan la misma
llave en cada peticion.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Protocol

import asyncpg
from fastapi import APIRouter, Body, HTTPException, Request

from ..agenda.parametros import normalizar_parametros, validar_parametros
from ..panel_acl import exigir_modulo

router = APIRouter(prefix="/api/v1/superadmin/operacion", tags=["superadmin"])

CAJA_DEFAULTS: dict[str, Any] = {
    "caja_chica_max_monto_usd": "100.00",
    "compras_efectivo_max_monto_usd": "300.00",
    "fondo_base_caja_chica_usd": "200.00",
}


def _decimal(valor: Any, campo: str, *, permitir_cero: bool = False) -> str:
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{campo} debe ser numerico") from exc
    if numero < 0 or (numero == 0 and not permitir_cero):
        raise ValueError(f"{campo} debe ser mayor que cero")
    return f"{numero:.2f}"


def normalizar_caja(valor: Any) -> dict[str, str]:
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except ValueError:
            valor = {}
    datos = valor if isinstance(valor, Mapping) else {}
    salida = dict(CAJA_DEFAULTS)
    for campo in CAJA_DEFAULTS:
        if datos.get(campo) not in (None, ""):
            try:
                salida[campo] = f"{Decimal(str(datos[campo])):.2f}"
            except (InvalidOperation, TypeError, ValueError):
                salida[campo] = CAJA_DEFAULTS[campo]
    return salida


def validar_caja(datos: Mapping[str, Any]) -> dict[str, str]:
    datos = dict(datos)
    return {
        "caja_chica_max_monto_usd": _decimal(
            datos.get("caja_chica_max_monto_usd", CAJA_DEFAULTS["caja_chica_max_monto_usd"]),
            "caja_chica_max_monto_usd",
        ),
        "compras_efectivo_max_monto_usd": _decimal(
            datos.get(
                "compras_efectivo_max_monto_usd",
                CAJA_DEFAULTS["compras_efectivo_max_monto_usd"],
            ),
            "compras_efectivo_max_monto_usd",
        ),
        "fondo_base_caja_chica_usd": _decimal(
            datos.get(
                "fondo_base_caja_chica_usd",
                CAJA_DEFAULTS["fondo_base_caja_chica_usd"],
            ),
            "fondo_base_caja_chica_usd",
            permitir_cero=True,
        ),
    }


class OperacionStore(Protocol):
    async def leer(self) -> dict[str, Any]: ...

    async def guardar(self, datos: Mapping[str, Any]) -> dict[str, Any]: ...


def _merge_dict(valor: Any) -> dict[str, Any]:
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except ValueError:
            return {}
    return dict(valor) if isinstance(valor, Mapping) else {}


class PostgresOperacionStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def _leer_clave(self, clave: str) -> dict[str, Any]:
        valor = await self._pool.fetchval(
            "SELECT value FROM system_settings WHERE key = $1", clave
        )
        return _merge_dict(valor)

    async def _guardar_clave(self, clave: str, valor: Mapping[str, Any]) -> None:
        await self._pool.execute(
            """
            INSERT INTO system_settings (key, value, descripcion)
            VALUES ($1, $2::jsonb, $3)
            ON CONFLICT (key) DO UPDATE
               SET value = EXCLUDED.value, actualizado_at = now()
            """,
            clave,
            json.dumps(dict(valor)),
            "Configuracion operativa v6.2 (caja chica y agenda)",
        )

    async def leer(self) -> dict[str, Any]:
        pagos = await self._leer_clave("secretaria.pagos")
        agenda = await self._leer_clave("agenda.parametros")
        return {
            "caja_chica": normalizar_caja(pagos),
            "agenda": normalizar_parametros(agenda),
        }

    async def guardar(self, datos: Mapping[str, Any]) -> dict[str, Any]:
        if "caja_chica" in datos:
            actual = await self._leer_clave("secretaria.pagos")
            actual.update(validar_caja(datos["caja_chica"]))
            await self._guardar_clave("secretaria.pagos", actual)
        if "agenda" in datos:
            actual_agenda = await self._leer_clave("agenda.parametros")
            actual_agenda.update(validar_parametros(datos["agenda"]))
            await self._guardar_clave("agenda.parametros", actual_agenda)
        return await self.leer()


class MemoryOperacionStore:
    def __init__(self) -> None:
        self.pagos: dict[str, Any] = {
            "monto_minimo": "0.01",
            "abono_parcial": True,
            "validar_saldo": True,
            "permitir_anticipo": True,
            **CAJA_DEFAULTS,
        }
        self.agenda: dict[str, Any] = normalizar_parametros({})

    async def leer(self) -> dict[str, Any]:
        return {
            "caja_chica": normalizar_caja(self.pagos),
            "agenda": normalizar_parametros(self.agenda),
        }

    async def guardar(self, datos: Mapping[str, Any]) -> dict[str, Any]:
        if "caja_chica" in datos:
            self.pagos.update(validar_caja(datos["caja_chica"]))
        if "agenda" in datos:
            self.agenda.update(validar_parametros(datos["agenda"]))
        return await self.leer()


def _store(request: Request) -> OperacionStore:
    configurado = getattr(request.app.state, "operacion_store", None)
    if configurado is not None:
        return configurado
    pool = getattr(request.app.state, "pool", None)
    if not isinstance(pool, asyncpg.Pool):
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "pool no disponible"},
        )
    store = PostgresOperacionStore(pool)
    request.app.state.operacion_store = store
    return store


@router.get("/config")
async def leer_operacion(request: Request) -> dict[str, Any]:
    await exigir_modulo(request, "superadmin_config")
    return await _store(request).leer()


@router.put("/config")
async def guardar_operacion(
    request: Request, datos: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    await exigir_modulo(request, "superadmin_config", mutacion=True)
    if not isinstance(datos, dict) or not ({"caja_chica", "agenda"} & set(datos)):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_OPERATION_CONFIG",
                "message": "envia caja_chica y/o agenda",
            },
        )
    try:
        return await _store(request).guardar(datos)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_OPERATION_CONFIG", "message": str(exc)},
        ) from exc
