"""Tests de los dos ajustes ratificados por Direccion (2026-11-08) - Hito 3.

Cubre:

1. Receta PROVISIONAL no bloquea la venta y queda marcada en el contrato JSON.
2. Dos umbrales termicos: ALERTA_TEMPRANA (60 min antes) y
   POR_VENCER_CRITICO (30 min antes) sobre el limite de 150 min.
3. El Centinela expone el check nuevo ``recetas_provisionales`` (12 en total).
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.m2_planta import (  # noqa: E402
    ESTADOS_TERMICOS,
    estado_termico,
    evaluar_ventana_termica,
)
from app.m5_sentinel import audit, checks  # noqa: E402
from app.m5_sentinel.checks import CRITICO, OK, WARN  # noqa: E402
from app.routers.orders import OrdenCreate  # noqa: E402
from app.services.ordenes import NuevaOrden, _payload_base  # noqa: E402
from app.settings import Settings  # noqa: E402

LIMITE_MINUTOS = 150


def _limite(ahora: datetime) -> datetime:
    return ahora + timedelta(minutes=LIMITE_MINUTOS)


# ---------------------------------------------------------------------------
# Ajuste 2: reloj termico con dos avisos
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("minutos_restantes", "esperado"),
    [
        (150, "OK"),
        (91, "OK"),
        (61, "OK"),
        (60, "ALERTA_TEMPRANA"),
        (45, "ALERTA_TEMPRANA"),
        (31, "ALERTA_TEMPRANA"),
        (30, "POR_VENCER_CRITICO"),
        (10, "POR_VENCER_CRITICO"),
        (0.5, "POR_VENCER_CRITICO"),
        (0, "VENCIDO"),
        (-1, "VENCIDO"),
        (-120, "VENCIDO"),
    ],
)
def test_ventana_termica_dos_umbrales(
    minutos_restantes: float, esperado: str
) -> None:
    ahora = datetime(2026, 11, 8, 9, 0, tzinfo=timezone.utc)
    limite = ahora + timedelta(minutes=minutos_restantes)

    assert evaluar_ventana_termica(ahora, limite) == esperado


def test_ventana_termica_normaliza_umbrales_invertidos() -> None:
    """Un dato mal cargado en system_settings no rompe el procesamiento."""
    ahora = datetime(2026, 11, 8, 9, 0, tzinfo=timezone.utc)

    # Llega 30/60 al reves: se normaliza a temprana=60, critico=30.
    assert (
        evaluar_ventana_termica(
            ahora,
            ahora + timedelta(minutes=45),
            alerta_temprana_minutos=30,
            por_vencer_critico_minutos=60,
        )
        == "ALERTA_TEMPRANA"
    )
    assert (
        evaluar_ventana_termica(
            ahora,
            ahora + timedelta(minutes=20),
            alerta_temprana_minutos=30,
            por_vencer_critico_minutos=60,
        )
        == "POR_VENCER_CRITICO"
    )


def test_estados_termicos_declara_las_cuatro_bandas() -> None:
    assert ESTADOS_TERMICOS == (
        "OK",
        "ALERTA_TEMPRANA",
        "POR_VENCER_CRITICO",
        "VENCIDO",
    )


def test_estado_termico_legado_no_cambio() -> None:
    """El Hito 2 se queda congelado: la firma antigua sigue igual."""
    ahora = datetime(2026, 11, 8, 9, 0, tzinfo=timezone.utc)

    assert estado_termico(ahora, ahora + timedelta(minutes=40)) == "OK"
    assert estado_termico(ahora, ahora + timedelta(minutes=20)) == "POR_VENCER"
    assert estado_termico(ahora, ahora - timedelta(minutes=1)) == "VENCIDO"


# ---------------------------------------------------------------------------
# Ajuste 1: receta provisional no bloquea la venta
# ---------------------------------------------------------------------------
def test_nueva_orden_permite_provisional_por_defecto() -> None:
    orden = NuevaOrden(
        cliente_id=str(uuid4()),
        resistencia="FC-210",
        volumen_m3=Decimal("8"),
        planta_codigo="PLANTA-COCA",
        forma_pago="EFECTIVO",
    )

    assert orden.permitir_receta_provisional is True


def test_api_order_create_permite_provisional_por_defecto() -> None:
    cuerpo = OrdenCreate(
        cliente_id=str(uuid4()),
        resistencia="FC-210",
        volumen_m3=Decimal("8"),
        planta_codigo="PLANTA-COCA",
        forma_pago="EFECTIVO",
    )

    assert cuerpo.permitir_receta_provisional is True


@pytest.mark.parametrize("provisional", [True, False])
def test_payload_de_viaje_declara_receta_provisional(provisional: bool) -> None:
    payload = _payload_base(
        dispatch_id=uuid4(),
        viaje_numero=1,
        total_viajes=3,
        volumen=Decimal("8"),
        resistencia="FC-210",
        mixer_codigo="MIXER-01",
        chofer_nombre=None,
        receta_provisional=provisional,
    )

    assert payload["receta_provisional"] is provisional
    # El contrato del Hito 2 no se altera: las llaves siguen ahi.
    assert payload["estado_actual"] == "PROGRAMADO"
    assert "tiempos_forenses" in payload
    assert "juez_binario_jeb" in payload


# ---------------------------------------------------------------------------
# Centinela: logica de los dos checks nuevos
# ---------------------------------------------------------------------------
class _PoolFalso:
    """Pool minimo para probar los checks sin PostgreSQL."""

    def __init__(
        self,
        *,
        valores: dict[str, object] | None = None,
        fila: dict[str, object] | None = None,
    ) -> None:
        self.valores = valores or {}
        self.fila = fila or {}
        self.consultas: list[str] = []

    async def fetchrow(self, consulta: str, *args: object) -> dict[str, object]:
        self.consultas.append(consulta)
        if "system_settings" in consulta:
            clave = str(args[0])
            return {"value": self.valores.get(clave, args[1] if len(args) > 1 else None)}
        return self.fila


@pytest.mark.parametrize(
    ("vencidos", "criticos", "tempranos", "esperado"),
    [
        (0, 0, 0, OK),
        (0, 0, 2, WARN),
        (0, 1, 0, CRITICO),
        (1, 0, 0, CRITICO),
        (2, 3, 4, CRITICO),
    ],
)
@pytest.mark.asyncio
async def test_check_riesgo_termico_dos_bandas(
    vencidos: int, criticos: int, tempranos: int, esperado: str
) -> None:
    pool = _PoolFalso(
        valores={
            "operacion.alerta_temprana_minutos_antes": 60,
            "operacion.por_vencer_critico_minutos_antes": 30,
        },
        fila={
            "vencidos": vencidos,
            "por_vencer_criticos": criticos,
            "alerta_temprana": tempranos,
        },
    )

    resultado = await checks.check_riesgo_termico(pool)  # type: ignore[arg-type]

    assert resultado.id == "riesgo_termico"
    assert resultado.estado == esperado
    assert resultado.datos["vencidos"] == vencidos
    assert resultado.datos["por_vencer_criticos"] == criticos
    assert resultado.datos["alerta_temprana"] == tempranos
    assert resultado.datos["umbral_alerta_temprana_min"] == 60
    assert resultado.datos["umbral_por_vencer_critico_min"] == 30


@pytest.mark.parametrize(
    ("total", "esperado"), [(0, OK), (1, WARN), (7, WARN)]
)
@pytest.mark.asyncio
async def test_check_recetas_provisionales(total: int, esperado: str) -> None:
    pool = _PoolFalso(fila={"total": total})

    resultado = await checks.check_recetas_provisionales(pool)  # type: ignore[arg-type]

    assert resultado.id == "recetas_provisionales"
    assert resultado.estado == esperado
    assert resultado.datos["total"] == total
    assert resultado.datos["ventana_dias"] == 7


def test_centinela_registra_doce_checks() -> None:
    settings = Settings(_env_file=None)
    fabricas = audit.construir_fabricas(
        object(),  # type: ignore[arg-type]
        settings,
        date(2026, 11, 7),
        ZoneInfo("America/Guayaquil"),
    )

    ids = [check_id for check_id, _, _ in fabricas]
    assert len(fabricas) == 12
    assert ids == [
        "db",
        "redis",
        "infra",
        "evolution",
        "bunny",
        "viajes_en_ruta",
        "riesgo_termico",
        "recetas_provisionales",
        "caja",
        "merma",
        "errores",
        "despachos_ayer",
    ]
    assert all(callable(fabrica) for _, _, fabrica in fabricas)


def test_centinela_no_incluye_recetas_en_el_resumen_operativo() -> None:
    """El resumen del contrato no cambia: sigue con las mismas 5 llaves."""
    resultados = [
        checks.CheckResult(
            id="recetas_provisionales",
            categoria="OPERACION",
            estado=WARN,
            detalle="x",
            latencia_ms=1.0,
            datos={"total": 3},
        )
    ]

    resumen = audit.construir_resumen_operativo(resultados)

    assert set(resumen) == {
        "viajes_despachados_ayer",
        "viajes_en_ruta",
        "viajes_en_riesgo_termico",
        "cajas_sin_cerrar",
        "errores_24h",
    }
