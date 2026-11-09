"""Tests puros del Custodio v4.3.

No tocan la base. La integracion completa (14 mutaciones, 9 consultas y las
correcciones con testigo) se verifica con ``scripts/custodio_v43_check.py``
contra el clon ``orminorth_v43`` y con ``ROLLBACK`` al final.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.custodio.catalog_hygiene import (  # noqa: E402
    ErrorCatalogo,
    normalizar_nombre,
    prefijo_de_grupo,
    siguiente_codigo,
    similitud_nombres,
)
from app.custodio.contracts import (  # noqa: E402
    ContratoInvalido,
    validar_consulta,
    validar_mutacion,
    validar_respuesta_gate,
    validar_testigo,
)
from app.custodio.gate import (  # noqa: E402
    Actor,
    autorizar,
    hash_solicitud,
    respuesta_gate,
)
from app.custodio.ledger import (  # noqa: E402
    AsientoInvalido,
    Linea,
    sumar_por_naturaleza,
    validar_lineas,
)


def _mutacion(intent: str, payload: dict) -> dict:
    return {
        "contract_version": "1.3.0",
        "request_id": str(uuid4()),
        "channel": "TEST",
        "intent": intent,
        "payload": payload,
    }


def _testigo(intent: str, target_table: str, changes: dict) -> dict:
    return {
        "contract_version": "1.3.0",
        "request_id": str(uuid4()),
        "channel": "TEST",
        "intent": intent,
        "target_table": target_table,
        "target_record_id": str(uuid4()),
        "motivo": "Correccion solicitada por Julio con evidencia",
        "changes": changes,
    }


# ---------------------------------------------------------------------------
# Contratos
# ---------------------------------------------------------------------------
def test_mutacion_valida_se_acepta() -> None:
    validar_mutacion(_mutacion("CREATE_SUPPLIER", {"nombre": "Proveedor de prueba"}))


def test_mutacion_rechaza_campo_desconocido() -> None:
    with pytest.raises(ContratoInvalido):
        validar_mutacion(
            _mutacion(
                "CREATE_SUPPLIER",
                {"nombre": "Proveedor de prueba", "precio_inventado": "1.00"},
            )
        )


def test_mutacion_rechaza_requerido_ausente() -> None:
    with pytest.raises(ContratoInvalido):
        validar_mutacion(_mutacion("CREATE_SUPPLIER", {}))


def test_mutacion_rechaza_intent_desconocido() -> None:
    with pytest.raises(ContratoInvalido):
        validar_mutacion(_mutacion("BORRAR_TODO", {}))


def test_consulta_cliente_exige_cliente_id() -> None:
    base = {
        "contract_version": "1.3.0",
        "request_id": str(uuid4()),
        "channel": "TEST",
        "intent": "GET_CLIENT_BALANCE",
    }
    with pytest.raises(ContratoInvalido):
        validar_consulta({**base, "filters": {}})
    validar_consulta({**base, "filters": {"cliente_id": str(uuid4())}})


def test_testigo_rechaza_motivo_corto() -> None:
    solicitud = _testigo(
        "CORRECT_MOVEMENT_WITH_WITNESS",
        "payments",
        {"nuevo_monto": "150.00"},
    )
    solicitud["motivo"] = "corto"
    with pytest.raises(ContratoInvalido):
        validar_testigo(solicitud)


def test_testigo_rechaza_correccion_vacia() -> None:
    with pytest.raises(ContratoInvalido):
        validar_testigo(
            _testigo("CORRECT_MOVEMENT_WITH_WITNESS", "payments", {})
        )


def test_testigo_correccion_valida() -> None:
    validar_testigo(
        _testigo(
            "CORRECT_MOVEMENT_WITH_WITNESS",
            "payments",
            {"nuevo_monto": "150.00"},
        )
    )


# ---------------------------------------------------------------------------
# Respuesta del Gate
# ---------------------------------------------------------------------------
def test_respuesta_aceptada_se_autovalida() -> None:
    respuesta = respuesta_gate(
        str(uuid4()),
        "ACCEPT",
        residual_risks=["PROVISIONAL_RECIPE_USED"],
        data={"monto": Decimal("10.50")},
    )
    validar_respuesta_gate(respuesta)
    assert respuesta["status"] == "ACCEPT"
    assert isinstance(respuesta["data"]["monto"], float)


def test_respuesta_rechazo_exige_codigo() -> None:
    with pytest.raises(ContratoInvalido):
        respuesta_gate(str(uuid4()), "REJECT")


def test_respuesta_pendiente_exige_aprobacion() -> None:
    with pytest.raises(ContratoInvalido):
        respuesta_gate(str(uuid4()), "PENDING_JULIO_APPROVAL")


def test_respuesta_rechaza_riesgo_desconocido() -> None:
    with pytest.raises(ContratoInvalido):
        respuesta_gate(
            str(uuid4()),
            "ACCEPT",
            residual_risks=["RIESGO_INVENTADO"],
        )


def test_respuesta_aceptada_no_admite_codigos() -> None:
    with pytest.raises(ContratoInvalido):
        respuesta_gate(
            str(uuid4()),
            "ACCEPT",
            rejection_codes=["SCHEMA_VALIDATION_FAILED"],
        )


# ---------------------------------------------------------------------------
# Partida doble
# ---------------------------------------------------------------------------
def test_asiento_balanceado() -> None:
    total = validar_lineas(
        [
            Linea("caja_diaria_secretaria", debe=Decimal("100.00")),
            Linea("ventas_hormigon", haber=Decimal("100.00")),
        ]
    )
    assert total == Decimal("100.00")


def test_asiento_descuadrado_se_rechaza() -> None:
    with pytest.raises(AsientoInvalido):
        validar_lineas(
            [
                Linea("caja_diaria_secretaria", debe=Decimal("100.00")),
                Linea("ventas_hormigon", haber=Decimal("99.99")),
            ]
        )


def test_linea_con_dos_lados_se_rechaza() -> None:
    with pytest.raises(AsientoInvalido):
        validar_lineas(
            [
                Linea(
                    "caja_diaria_secretaria",
                    debe=Decimal("100.00"),
                    haber=Decimal("100.00"),
                )
            ]
        )


def test_linea_con_mas_de_dos_decimales_se_rechaza() -> None:
    with pytest.raises(AsientoInvalido):
        validar_lineas(
            [
                Linea("caja_diaria_secretaria", debe=Decimal("100.001")),
                Linea("ventas_hormigon", haber=Decimal("100.001")),
            ]
        )


def test_asiento_vacio_se_rechaza() -> None:
    with pytest.raises(AsientoInvalido):
        validar_lineas([])


def test_balance_respeta_cuentas_contra() -> None:
    filas = [
        {
            "account_type": "ASSET",
            "normal_balance": "DEBIT",
            "saldo_neto": "100.00",
        },
        {
            "account_type": "ASSET",
            "normal_balance": "CREDIT",
            "saldo_neto": "30.00",
        },
        {
            "account_type": "LIABILITY",
            "normal_balance": "CREDIT",
            "saldo_neto": "50.00",
        },
        {
            "account_type": "EQUITY",
            "normal_balance": "CREDIT",
            "saldo_neto": "20.00",
        },
        {
            "account_type": "REVENUE",
            "normal_balance": "CREDIT",
            "saldo_neto": "40.00",
        },
        {
            "account_type": "EXPENSE",
            "normal_balance": "DEBIT",
            "saldo_neto": "10.00",
        },
    ]
    totales = sumar_por_naturaleza(filas)
    assert totales["ASSET"] == Decimal("70.00")
    assert totales["LIABILITY"] == Decimal("50.00")
    assert totales["EQUITY"] == Decimal("20.00")
    assert totales["REVENUE"] == Decimal("40.00")
    assert totales["EXPENSE"] == Decimal("10.00")


# ---------------------------------------------------------------------------
# Higiene del catalogo
# ---------------------------------------------------------------------------
def test_normalizacion_ignora_acentos_y_separadores() -> None:
    assert normalizar_nombre("  Gastos   de Oficina!  ") == "gastos de oficina"
    assert normalizar_nombre("Depreciación") == "depreciacion"


def test_similitud_detecta_duplicado() -> None:
    assert similitud_nombres("Gastos de Oficina", "gastos  de oficina") >= 0.88
    assert similitud_nombres("Combustible", "Sueldos administrativos") < 0.88


def test_siguiente_codigo_usa_el_prefijo_del_grupo() -> None:
    assert siguiente_codigo(["1101", "1105", "1109"], "11") == "1110"
    assert siguiente_codigo([], "53") == "5301"
    assert siguiente_codigo(["1101", "basura"], "53") == "5301"


def test_prefijo_de_grupo_desconocido_se_rechaza() -> None:
    with pytest.raises(ErrorCatalogo):
        prefijo_de_grupo("GRUPO_INVENTADO")


# ---------------------------------------------------------------------------
# Autorizacion e idempotencia
# ---------------------------------------------------------------------------
def test_roles_del_gate() -> None:
    assert (
        autorizar(
            Actor(role="SUPERADMIN", id="julio"),
            "REGISTER_EXPENSE",
            "WEB_PANEL",
            "mutacion",
        )
        is None
    )
    assert (
        autorizar(
            Actor(role="BODEGA_PLANTA", id="bodega"),
            "REGISTER_EXPENSE",
            "WEB_PANEL",
            "mutacion",
        )
        == "UNAUTHORIZED_DOMAIN_ACCESS"
    )
    assert (
        autorizar(
            Actor(role="SYSTEM_CRON", id="cron"),
            "RUN_MONTHLY_DEPRECIATION",
            "WEB_PANEL",
            "mutacion",
        )
        == "UNAUTHORIZED_ACTOR"
    )
    assert (
        autorizar(
            Actor(role="SYSTEM_CRON", id="cron"),
            "RUN_MONTHLY_DEPRECIATION",
            "SYSTEM_CRON",
            "mutacion",
        )
        is None
    )


def test_actor_sin_id_se_rechaza() -> None:
    assert (
        autorizar(
            Actor(role="SUPERADMIN", id="   "),
            "REGISTER_EXPENSE",
            "WEB_PANEL",
            "mutacion",
        )
        == "UNAUTHORIZED_ACTOR"
    )


def test_hash_es_canonico() -> None:
    a = {"b": 1, "a": [1, 2], "request_id": "x"}
    b = {"a": [1, 2], "request_id": "x", "b": 1}
    assert hash_solicitud(a) == hash_solicitud(b)
    assert hash_solicitud(a) != hash_solicitud({**a, "b": 2})
