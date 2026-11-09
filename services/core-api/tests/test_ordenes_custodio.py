"""Tests de la regla v4.3: IVA de la venta y COBRO inicial.

La aritmetica es pura y se prueba sin PostgreSQL. La integracion real
(orden + payments + v_cliente_saldo) se verifica con
``scripts/refactor_v43_check.py`` contra la base clon.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.services.ordenes import (  # noqa: E402
    NuevaOrden,
    OrdenInvalidaError,
    calcular_iva,
    validar_abono_inicial,
)


def test_iva_15_sobre_total_neto() -> None:
    iva, bruto = calcular_iva(Decimal("37760.00"), Decimal("15.00"), aplica_iva=True)

    assert iva == Decimal("5664.00")
    assert bruto == Decimal("43424.00")


def test_iva_redondea_al_centavo_como_postgresql() -> None:
    iva, bruto = calcular_iva(Decimal("100.05"), Decimal("15.00"), aplica_iva=True)

    assert iva == Decimal("15.01")
    assert bruto == Decimal("115.06")


def test_orden_sin_precio_no_inventa_iva_ni_total() -> None:
    iva, bruto = calcular_iva(None, Decimal("15.00"), aplica_iva=True)

    assert iva == Decimal("0")
    assert bruto is None


def test_venta_exenta_no_cobra_iva() -> None:
    iva, bruto = calcular_iva(Decimal("100.00"), Decimal("15.00"), aplica_iva=False)

    assert iva == Decimal("0")
    assert bruto == Decimal("100.00")


def test_abono_inicial_valido() -> None:
    monto, metodo = validar_abono_inicial(
        forma_pago="ABONO",
        monto=Decimal("500.00"),
        metodo="transferencia",
        total_con_iva=Decimal("920.00"),
    )

    assert monto == Decimal("500.00")
    assert metodo == "TRANSFERENCIA"


def test_abono_inicial_no_puede_superar_el_total() -> None:
    with pytest.raises(OrdenInvalidaError, match="supera el total"):
        validar_abono_inicial(
            forma_pago="ABONO",
            monto=Decimal("921.00"),
            metodo="EFECTIVO",
            total_con_iva=Decimal("920.00"),
        )


def test_abono_inicial_exige_monto_y_metodo() -> None:
    with pytest.raises(OrdenInvalidaError, match="abono_inicial_monto"):
        validar_abono_inicial(
            forma_pago="ABONO",
            monto=None,
            metodo="EFECTIVO",
            total_con_iva=Decimal("920.00"),
        )

    with pytest.raises(OrdenInvalidaError, match="abono_inicial_metodo"):
        validar_abono_inicial(
            forma_pago="ABONO",
            monto=Decimal("100.00"),
            metodo="FIADO",
            total_con_iva=Decimal("920.00"),
        )


def test_abono_inicial_exige_precio_de_venta() -> None:
    with pytest.raises(OrdenInvalidaError, match="sin precio de venta"):
        validar_abono_inicial(
            forma_pago="ABONO",
            monto=Decimal("100.00"),
            metodo="EFECTIVO",
            total_con_iva=None,
        )


def test_fiado_no_genera_cobro_inicial() -> None:
    assert validar_abono_inicial(
        forma_pago="FIADO",
        monto=None,
        metodo=None,
        total_con_iva=Decimal("920.00"),
    ) == (None, None)


def test_contado_no_admite_abono_inicial() -> None:
    with pytest.raises(OrdenInvalidaError, match="solo aplican a forma_pago ABONO"):
        validar_abono_inicial(
            forma_pago="EFECTIVO",
            monto=Decimal("100.00"),
            metodo="EFECTIVO",
            total_con_iva=Decimal("920.00"),
        )


def test_nueva_orden_usa_defaults_dinamicos_de_iva() -> None:
    orden = NuevaOrden(
        cliente_id="11111111-1111-1111-1111-111111111111",
        resistencia="FC-210",
        volumen_m3=Decimal("8"),
        planta_codigo="PLANTA-COCA",
        forma_pago="EFECTIVO",
    )

    # None = leer finanzas.iva_default_aplica en crear_orden.
    assert orden.aplica_iva is None
    assert orden.abono_inicial_monto is None
    assert orden.abono_inicial_metodo is None
