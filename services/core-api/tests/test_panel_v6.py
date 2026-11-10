"""Tests de las reglas nuevas del panel v6.0 (sin base de datos).

Cubren el tope de caja chica y el armado del payload de compras. La
persistencia real se verifica contra el clon con ``http_gate``/``panel``.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.custodio.contracts import REJECTION_CODES  # noqa: E402
from app.http_gate.panel import (  # noqa: E402
    CompraIn,
    CompraItemIn,
    _payload_compra,
    excede_tope_caja,
)

SUPPLIER = UUID("8a25a048-731b-40f9-b766-2c45aab27515")
MATERIAL = UUID("6482db53-c755-45a5-844d-8f6aefdff847")


def _compra(**overrides) -> CompraIn:
    datos = {
        "supplier_id": SUPPLIER,
        "fecha_compra": date(2026, 11, 9),
        "modalidad_pago": "CONTADO_EFECTIVO",
        "items": [
            CompraItemIn(
                material_id=MATERIAL,
                descripcion="Cemento",
                cantidad=Decimal("10"),
                costo_unitario=Decimal("8.2"),
            )
        ],
    }
    datos.update(overrides)
    return CompraIn(**datos)


def test_tope_caja_bloquea_solo_si_supera_y_no_hay_autorizacion() -> None:
    assert excede_tope_caja("100.00", Decimal("150.00")) == Decimal("100.00")
    assert excede_tope_caja("100.00", Decimal("150.00"), True) is None
    assert excede_tope_caja("100.00", Decimal("100.00")) is None
    assert excede_tope_caja(None, Decimal("500.00")) is None
    assert excede_tope_caja("no-numero", Decimal("500.00")) is None


def test_compra_contado_efectivo_paga_todo_en_caja() -> None:
    payload = _payload_compra(_compra(iva_monto=Decimal("12")))
    assert payload["modalidad_pago"] == "CONTADO_EFECTIVO"
    assert payload["monto_pagado_hoy"] == "94.00"
    assert payload["bolsa_pago_hoy"] == "CAJA_DIARIA"
    assert payload["items"][0]["cantidad"] == "10.0000"
    assert payload["items"][0]["account_slug"] == "inventario_insumos_silos"


def test_compra_contado_transferencia_usa_banco() -> None:
    payload = _payload_compra(_compra(modalidad_pago="CONTADO_TRANSFERENCIA"))
    assert payload["monto_pagado_hoy"] == "82.00"
    assert payload["bolsa_pago_hoy"] == "BANCO_GERENCIA"


def test_compra_credito_no_paga_hoy() -> None:
    payload = _payload_compra(
        _compra(
            modalidad_pago="CREDITO_PROVEEDOR",
            fecha_vencimiento=date(2026, 12, 9),
        )
    )
    assert payload["monto_pagado_hoy"] == "0.00"
    assert "bolsa_pago_hoy" not in payload
    assert payload["fecha_vencimiento"] == "2026-12-09"


def test_compra_mixta_respeta_abono_y_bolsa() -> None:
    payload = _payload_compra(
        _compra(
            modalidad_pago="MIXTO_ABONO_CREDITO",
            monto_pagado_hoy=Decimal("40"),
            bolsa_pago_hoy="CAJA_DIARIA",
            referencia_comprobante="FAC-001",
        )
    )
    assert payload["monto_pagado_hoy"] == "40.00"
    assert payload["bolsa_pago_hoy"] == "CAJA_DIARIA"
    assert payload["referencia_comprobante"] == "FAC-001"


def test_codigo_no_monetario_es_parte_del_contrato() -> None:
    assert "NON_MONETARY_ACCOUNT_IN_PAYMENT" in REJECTION_CODES
