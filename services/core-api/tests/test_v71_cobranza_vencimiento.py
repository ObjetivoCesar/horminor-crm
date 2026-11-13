"""Tests de la migracion 079: vencimiento de documentos por cobrar (v6.18)."""

from __future__ import annotations

from pathlib import Path

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]


def _migracion(numero: str) -> Path:
    for base in (RAIZ_SERVICIO, *RAIZ_SERVICIO.parents):
        candidato = base / "db" / "migrations" / numero
        if candidato.is_file():
            return candidato
    raise FileNotFoundError(numero)


def test_079_agrega_vencimiento_a_ordenes_y_facturas() -> None:
    sql = _migracion("079_vencimiento_cobranza.sql").read_text(encoding="utf-8")
    assert "ALTER TABLE orders" in sql
    assert "ALTER TABLE client_invoices" in sql
    assert sql.count("ADD COLUMN IF NOT EXISTS fecha_vencimiento date") == 2
    assert "NULL = pendiente de capturar" in sql


def test_079_crea_vista_de_cobranza_con_cuatro_cubos() -> None:
    sql = _migracion("079_vencimiento_cobranza.sql").read_text(encoding="utf-8")
    assert "CREATE OR REPLACE VIEW v_cobranza_documentos" in sql
    for cubo in ("SIN_VENCIMIENTO", "VENCIDA", "POR_VENCER_7", "CORRIENTE"):
        assert cubo in sql
    assert "monto_documento es el total del documento, NO el saldo pendiente" in sql


def test_079_no_inventa_fechas() -> None:
    sql = _migracion("079_vencimiento_cobranza.sql").read_text(encoding="utf-8")
    assert "DEFAULT CURRENT_DATE" not in sql
    assert "NOT NULL" not in sql.split("fecha_vencimiento", 1)[1].split(";", 1)[0]
