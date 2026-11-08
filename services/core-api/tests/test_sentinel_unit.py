"""Tests unitarios del Modulo 5 - Nodo Centinela (sin base de datos real)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

# services/core-api debe estar en sys.path para importar el paquete `app`.
RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.m5_sentinel import audit  # noqa: E402
from app.m5_sentinel.checks import CheckResult  # noqa: E402
from app.m5_sentinel.router import router as sentinel_router  # noqa: E402
from app.settings import Settings  # noqa: E402

URL = "/api/v1/sentinel/daily-audit"
CLAVE_VALIDA = "clave-segura-de-prueba"


def _settings(clave: str = CLAVE_VALIDA) -> Settings:
    """Settings aisladas del .env local."""
    return Settings(_env_file=None, agency_master_key=clave)


def _app(settings: Settings, pool: object | None = None) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings
    app.state.pool = object() if pool is None else pool
    app.include_router(sentinel_router)
    return app


def _check(
    check_id: str,
    estado: str,
    datos: dict | None = None,
    categoria: str = "OPERACION",
) -> CheckResult:
    return CheckResult(
        id=check_id,
        categoria=categoria,  # type: ignore[arg-type]
        estado=estado,  # type: ignore[arg-type]
        detalle=f"detalle {check_id}",
        latencia_ms=1.0,
        datos=datos or {},
    )


# ---------------------------------------------------------------------------
# Agregacion de estados (logica pura)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("estados", "esperado"),
    [
        ([], "NO_CONFIGURADO"),
        (["OK"], "OK"),
        (["OK", "OK", "OK"], "OK"),
        (["OK", "NO_CONFIGURADO"], "OK"),
        (["WARN"], "WARN"),
        (["OK", "WARN"], "WARN"),
        (["NO_CONFIGURADO", "WARN"], "WARN"),
        (["CRITICO"], "CRITICO"),
        (["WARN", "CRITICO"], "CRITICO"),
        (["OK", "WARN", "CRITICO"], "CRITICO"),
        (["NO_CONFIGURADO", "NO_CONFIGURADO"], "NO_CONFIGURADO"),
        (
            ["NO_CONFIGURADO", "NO_CONFIGURADO", "NO_CONFIGURADO"],
            "NO_CONFIGURADO",
        ),
    ],
)
def test_agregacion_de_estados(estados: list[str], esperado: str) -> None:
    assert audit.agregar_estado_global(estados) == esperado  # type: ignore[arg-type]


def test_resumen_operativo_extrae_datos_de_los_checks() -> None:
    resultados = [
        _check("despachos_ayer", "OK", {"total": 7}),
        _check("viajes_en_ruta", "WARN", {"total_en_ruta": 3}),
        _check("riesgo_termico", "CRITICO", {"total": 2}),
        _check("caja", "WARN", {"faltantes": 1}),
        _check("errores", "WARN", {"total": 5}),
        _check("infra", "OK", {"cpu_pct": 10}),
    ]

    resumen = audit.construir_resumen_operativo(resultados)

    assert resumen == {
        "viajes_despachados_ayer": 7,
        "viajes_en_ruta": 3,
        "viajes_en_riesgo_termico": 2,
        "cajas_sin_cerrar": 1,
        "errores_24h": 5,
    }


def test_resumen_operativo_ignora_checks_ausentes_o_incompletos() -> None:
    resultados = [
        _check("despachos_ayer", "CRITICO", {}),
        _check("viajes_en_ruta", "CRITICO", {"total_en_ruta": None}),
    ]

    resumen = audit.construir_resumen_operativo(resultados)

    assert resumen["viajes_despachados_ayer"] == 0
    assert resumen["viajes_en_ruta"] == 0
    assert resumen["cajas_sin_cerrar"] == 0
    assert resumen["errores_24h"] == 0


# ---------------------------------------------------------------------------
# Autenticacion del endpoint
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sin_header_responde_401() -> None:
    app = _app(_settings())
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        respuesta = await client.get(URL)

    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": "no autorizado"}


@pytest.mark.asyncio
async def test_header_incorrecto_responde_401() -> None:
    app = _app(_settings())
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        respuesta = await client.get(
            URL, headers={"X-Agency-Master-Key": "clave-equivocada"}
        )

    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": "no autorizado"}


@pytest.mark.asyncio
async def test_clave_por_defecto_responde_503() -> None:
    app = _app(_settings("change-me"))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        respuesta = await client.get(
            URL, headers={"X-Agency-Master-Key": "change-me"}
        )

    assert respuesta.status_code == 503
    assert "no configurada" in respuesta.json()["detail"]


@pytest.mark.asyncio
async def test_sin_pool_responde_503() -> None:
    app = _app(_settings())
    app.state.pool = None
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        respuesta = await client.get(
            URL, headers={"X-Agency-Master-Key": CLAVE_VALIDA}
        )

    assert respuesta.status_code == 503


# ---------------------------------------------------------------------------
# Camino feliz (auditoria simulada, sin base de datos)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_clave_valida_responde_200(monkeypatch: pytest.MonkeyPatch) -> None:
    pool_enviado: object | None = None

    async def auditoria_falsa(pool: object, settings: Settings) -> dict:
        nonlocal pool_enviado
        pool_enviado = pool
        resultados = [
            _check("db", "OK", {"latencia_ms": 2.0}, "INFRAESTRUCTURA"),
            _check("redis", "NO_CONFIGURADO", {}, "INFRAESTRUCTURA"),
            _check("infra", "OK", {}, "INFRAESTRUCTURA"),
            _check("evolution", "NO_CONFIGURADO", {}, "CANAL"),
            _check("bunny", "NO_CONFIGURADO", {}, "CANAL"),
            _check("viajes_en_ruta", "WARN", {"total_en_ruta": 4}),
            _check("riesgo_termico", "OK", {"total": 0}),
            _check("recetas_provisionales", "WARN", {"total": 2}),
            _check("caja", "WARN", {"faltantes": 1}),
            _check("merma", "NO_CONFIGURADO", {}),
            _check("errores", "OK", {"total": 0}),
            _check("despachos_ayer", "OK", {"total": 6}),
        ]
        return {
            "cliente": "ORMINORTH",
            "generado_at": "2026-11-08T10:15:00-05:00",
            "latencia_total_ms": 12.5,
            "estado_global": audit.agregar_estado_global(
                [r.estado for r in resultados]
            ),
            "checks": [r.to_dict() for r in resultados],
            "resumen_operativo": audit.construir_resumen_operativo(resultados),
        }

    monkeypatch.setattr(audit, "ejecutar_auditoria", auditoria_falsa)

    app = _app(_settings())
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        respuesta = await client.get(
            URL, headers={"X-Agency-Master-Key": CLAVE_VALIDA}
        )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["cliente"] == "ORMINORTH"
    assert cuerpo["estado_global"] == "WARN"
    assert len(cuerpo["checks"]) == 12
    assert {c["id"] for c in cuerpo["checks"]} >= {"db", "redis", "infra"}
    assert cuerpo["resumen_operativo"] == {
        "viajes_despachados_ayer": 6,
        "viajes_en_ruta": 4,
        "viajes_en_riesgo_termico": 0,
        "cajas_sin_cerrar": 1,
        "errores_24h": 0,
    }
    assert pool_enviado is app.state.pool


def test_ejecutar_check_captura_excepciones() -> None:
    """Un check que revienta se transforma en CRITICO, nunca propaga."""

    async def revienta() -> CheckResult:
        raise RuntimeError("fallo simulado")

    resultado = asyncio.run(
        audit._ejecutar_check("x", "OPERACION", revienta, 1.0)
    )

    assert resultado.estado == "CRITICO"
    assert "fallo simulado" in resultado.detalle
