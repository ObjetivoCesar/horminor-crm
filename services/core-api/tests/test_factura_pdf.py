"""Tests puros del PDF de factura interna."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.services.factura_pdf import generar_pdf  # noqa: E402

DATOS = {
    "numero": "PRUEBA-0001",
    "fecha": date(2026, 11, 12),
    "cliente_nombre": "Ing. Reyes (prueba Hito 1)",
    "cliente_ruc": None,
    "cliente_ciudad": "El Coca",
    "orden_numero": 55,
    "resistencia": "FC-210",
    "volumen_m3": "320.00",
    "precio_m3": "118.00",
    "forma_pago": "FIADO",
    "subtotal": "37760.00",
    "iva_pct": "15.00",
    "iva_monto": "5664.00",
    "total": "43424.00",
    "empresa": {
        "company_name": "HORMINOR HORMIGONES Y PREFABRICADOS S.A.S.",
        "ruc": "2290000000001",
        "main_plant_address": "El Coca, Orellana",
    },
    "es_ficticia": True,
    "nota": "Factura ficticia de prueba.",
}


def test_pdf_factura_es_un_pdf_real() -> None:
    contenido = generar_pdf(DATOS)
    assert contenido.startswith(b"%PDF")
    assert len(contenido) > 3000


def test_pdf_sin_ficticia_tambien_se_genera() -> None:
    datos = {**DATOS, "es_ficticia": False, "numero": "001-001-000000001"}
    contenido = generar_pdf(datos)
    assert contenido.startswith(b"%PDF")
