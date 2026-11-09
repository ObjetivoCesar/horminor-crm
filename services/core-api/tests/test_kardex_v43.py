"""Tests puros del kardex v4.3: costo promedio ponderado.

La integracion (COMPRA -> costo, TEORICO -> snapshot, ANULACION -> reversa)
se verifica con ``scripts/kardex_v43_check.py`` contra el clon.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.m2_planta.kardex import costo_promedio_ponderado  # noqa: E402


def test_promedio_ponderado_dos_compras() -> None:
    costo = costo_promedio_ponderado(
        stock_actual=Decimal("100"),
        costo_actual=Decimal("8.2000"),
        cantidad_comprada=Decimal("100"),
        costo_compra=Decimal("10.0000"),
    )

    assert costo == Decimal("9.1000")


def test_sin_stock_previo_usa_el_costo_de_compra() -> None:
    assert costo_promedio_ponderado(
        stock_actual=None,
        costo_actual=None,
        cantidad_comprada=Decimal("50"),
        costo_compra=Decimal("7.5000"),
    ) == Decimal("7.5000")

    assert costo_promedio_ponderado(
        stock_actual=Decimal("0"),
        costo_actual=Decimal("8.2000"),
        cantidad_comprada=Decimal("50"),
        costo_compra=Decimal("7.5000"),
    ) == Decimal("7.5000")


def test_promedio_redondea_a_cuatro_decimales() -> None:
    costo = costo_promedio_ponderado(
        stock_actual=Decimal("1"),
        costo_actual=Decimal("1.0000"),
        cantidad_comprada=Decimal("2"),
        costo_compra=Decimal("1.0001"),
    )

    assert costo == Decimal("1.0001")


def test_promedio_rechaza_cantidad_no_positiva() -> None:
    with pytest.raises(ValueError, match="mayor que cero"):
        costo_promedio_ponderado(
            stock_actual=Decimal("10"),
            costo_actual=Decimal("8.0000"),
            cantidad_comprada=Decimal("0"),
            costo_compra=Decimal("9.0000"),
        )


def test_promedio_rechaza_costo_negativo() -> None:
    with pytest.raises(ValueError, match="no puede ser negativo"):
        costo_promedio_ponderado(
            stock_actual=Decimal("10"),
            costo_actual=Decimal("8.0000"),
            cantidad_comprada=Decimal("1"),
            costo_compra=Decimal("-1"),
        )
