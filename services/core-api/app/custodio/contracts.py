"""Contratos v1.3.0 del Custodio: validacion deterministica.

No se usa un motor de JSON Schema externo para no agregar dependencias al
contenedor. Las reglas replican exactamente los contratos de
``.agents/skills/custodio-bd-horminor/contracts`` y se prueban con los mismos
casos validos e invalidos de la evidencia ``contracts_v13_2026-11-09.txt``.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from uuid import UUID

CONTRACT_VERSION = "1.3.0"

MUTATION_INTENTS = (
    "CREATE_CONCRETE_ORDER",
    "CANCEL_CONCRETE_ORDER",
    "REGISTER_CLIENT_PAYMENT",
    "REGISTER_PURCHASE",
    "RECEIVE_PURCHASED_MATERIAL",
    "REGISTER_EXPENSE",
    "PAY_SUPPLIER_DEBT",
    "PAY_BANK_LOAN_INSTALLMENT",
    "RUN_MONTHLY_DEPRECIATION",
    "SET_OPENING_BALANCES",
    "RESOLVE_APPROVAL_REQUEST",
    "CREATE_SUPPLIER",
    "CREATE_FIXED_ASSET",
    "CREATE_FINANCIAL_LIABILITY",
)

QUERY_INTENTS = (
    "GET_CLIENT_BALANCE",
    "GET_DAILY_CASH_CLOSURE",
    "GET_ACCOUNTS_PAYABLE",
    "GET_INVENTORY_AND_ALERTS",
    "GET_DISPATCH_TIMELINE",
    "GET_INCOME_STATEMENT_PL",
    "GET_BALANCE_SHEET_REALTIME",
    "GET_VALUATION_AND_10Y_PROJECTION",
    "GET_DEBT_CAPACITY_DSCR",
)

WITNESS_INTENTS = (
    "CORRECT_MOVEMENT_WITH_WITNESS",
    "CREATE_ACCOUNTING_CATEGORY",
    "RENAME_ACCOUNTING_CATEGORY",
    "MERGE_ACCOUNTING_CATEGORIES",
)

CHANNELS_MUTACION = ("WEB_PANEL", "WHATSAPP", "SYSTEM_CRON", "TEST")
CHANNELS_CONSULTA = ("WEB_PANEL", "WHATSAPP", "TEST")
CHANNELS_TESTIGO = ("WEB_PANEL", "WHATSAPP", "TEST")

FORMAS_PAGO = ("EFECTIVO", "TRANSFERENCIA", "ABONO", "FIADO")
METODOS_PAGO = ("EFECTIVO", "TRANSFERENCIA")
BOLSAS = ("CAJA_DIARIA", "BANCO_GERENCIA")
MATERIALES_ACTIVO = (
    "ACTIVO_CORRIENTE",
    "ACTIVO_NO_CORRIENTE",
    "PASIVO_CORRIENTE",
    "PASIVO_LARGO_PLAZO",
    "PATRIMONIO_NETO",
    "INGRESO_OPERATIVO",
    "COSTO_DIRECTO",
    "CIF_PLANTA",
    "GASTO_ADMIN_FIJO",
    "CAJA_CHICA",
    "FISCAL_FINANCIERO",
)

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
_DECIMAL_RE = re.compile(r"^[0-9]+(\.[0-9]{1,2})?$")
_DECIMAL4_RE = re.compile(r"^[0-9]+(\.[0-9]{1,4})?$")
_DECIMAL_POSITIVO_RE = re.compile(
    r"^(?!0+(\.0{1,4})?$)[0-9]+(\.[0-9]{1,4})?$"
)
_DECIMAL_POSITIVO2_RE = re.compile(
    r"^(?!0+(\.0{1,2})?$)[0-9]+(\.[0-9]{1,2})?$"
)
_SLUG_RE = re.compile(r"^[a-z0-9_]+$")
_FC_RE = re.compile(r"^FC-[0-9]{3}$")
_PERIODO_RE = re.compile(r"^[0-9]{4}-[0-9]{2}$")


class ContratoInvalido(ValueError):
    """El contrato no se cumple. ``errores`` explica cada campo."""

    def __init__(self, errores: list[str]) -> None:
        self.errores = errores
        super().__init__("; ".join(errores))


def _uuid(valor: Any) -> bool:
    return isinstance(valor, str) and bool(_UUID_RE.match(valor)) and _uuid_parse_ok(valor)


def _uuid_parse_ok(valor: str) -> bool:
    try:
        UUID(valor)
        return True
    except (ValueError, AttributeError):
        return False


def _fecha(valor: Any) -> bool:
    if not isinstance(valor, str):
        return False
    try:
        date.fromisoformat(valor)
        return True
    except ValueError:
        return False


def _campos(
    datos: Mapping[str, Any],
    *,
    requeridos: tuple[str, ...],
    permitidos: tuple[str, ...],
    errores: list[str],
    prefijo: str = "payload",
) -> None:
    for campo in requeridos:
        if campo not in datos:
            errores.append(f"{prefijo}.{campo} es obligatorio")
    for campo in datos:
        if campo not in permitidos:
            errores.append(f"{prefijo}.{campo} no esta permitido")


def _texto(
    datos: Mapping[str, Any],
    campo: str,
    *,
    errores: list[str],
    requerido: bool = False,
    nulo: bool = False,
    min_len: int | None = None,
    max_len: int | None = None,
    patron: re.Pattern[str] | None = None,
    enum: tuple[str, ...] | None = None,
    prefijo: str = "payload",
) -> str | None:
    nombre = f"{prefijo}.{campo}"
    if campo not in datos:
        if requerido:
            errores.append(f"{nombre} es obligatorio")
        return None
    valor = datos[campo]
    if valor is None:
        if requerido and not nulo:
            errores.append(f"{nombre} no puede ser null")
        return None
    if not isinstance(valor, str):
        errores.append(f"{nombre} debe ser texto")
        return None
    if min_len is not None and len(valor) < min_len:
        errores.append(f"{nombre} debe tener al menos {min_len} caracteres")
    if max_len is not None and len(valor) > max_len:
        errores.append(f"{nombre} supera {max_len} caracteres")
    if patron is not None and not patron.match(valor):
        errores.append(f"{nombre} no cumple el formato esperado")
    if enum is not None and valor not in enum:
        errores.append(f"{nombre} debe ser uno de: {', '.join(enum)}")
    return valor


def _booleano(
    datos: Mapping[str, Any],
    campo: str,
    *,
    errores: list[str],
    prefijo: str = "payload",
) -> bool | None:
    valor = datos.get(campo)
    if valor is None:
        return None
    if not isinstance(valor, bool):
        errores.append(f"{prefijo}.{campo} debe ser booleano")
        return None
    return valor


def _entero(
    datos: Mapping[str, Any],
    campo: str,
    *,
    errores: list[str],
    minimo: int | None = None,
    requerido: bool = False,
    prefijo: str = "payload",
) -> int | None:
    nombre = f"{prefijo}.{campo}"
    if campo not in datos:
        if requerido:
            errores.append(f"{nombre} es obligatorio")
        return None
    valor = datos[campo]
    if isinstance(valor, bool) or not isinstance(valor, int):
        errores.append(f"{nombre} debe ser entero")
        return None
    if minimo is not None and valor < minimo:
        errores.append(f"{nombre} debe ser mayor o igual a {minimo}")
    return valor


def _decimal(
    datos: Mapping[str, Any],
    campo: str,
    *,
    errores: list[str],
    requerido: bool = False,
    nulo: bool = False,
    positivo: bool = False,
    cuatro_decimales: bool = False,
    prefijo: str = "payload",
) -> Decimal | None:
    nombre = f"{prefijo}.{campo}"
    if campo not in datos:
        if requerido:
            errores.append(f"{nombre} es obligatorio")
        return None
    valor = datos[campo]
    if valor is None:
        if requerido and not nulo:
            errores.append(f"{nombre} no puede ser null")
        return None
    if not isinstance(valor, str):
        errores.append(f"{nombre} debe ser texto decimal")
        return None
    patron = _DECIMAL4_RE if cuatro_decimales else _DECIMAL_RE
    if positivo:
        patron = _DECIMAL_POSITIVO_RE if cuatro_decimales else _DECIMAL_POSITIVO2_RE
    if not patron.match(valor):
        errores.append(f"{nombre} no cumple el formato decimal esperado")
        return None
    try:
        numero = Decimal(valor)
    except InvalidOperation:
        errores.append(f"{nombre} no es un decimal valido")
        return None
    if positivo and numero <= 0:
        errores.append(f"{nombre} debe ser mayor que cero")
    return numero


def _objeto(
    datos: Mapping[str, Any],
    campo: str,
    *,
    errores: list[str],
    prefijo: str = "payload",
) -> Mapping[str, Any] | None:
    valor = datos.get(campo)
    if valor is None:
        return None
    if not isinstance(valor, Mapping):
        errores.append(f"{prefijo}.{campo} debe ser un objeto")
        return None
    return valor


# ---------------------------------------------------------------------------
# Mutaciones
# ---------------------------------------------------------------------------
def validar_mutacion(solicitud: Any) -> None:
    errores: list[str] = []
    if not isinstance(solicitud, Mapping):
        raise ContratoInvalido(["la solicitud debe ser un objeto JSON"])

    _campos(
        solicitud,
        requeridos=("contract_version", "request_id", "channel", "intent", "payload"),
        permitidos=("contract_version", "request_id", "channel", "intent", "payload"),
        errores=errores,
        prefijo="solicitud",
    )
    if solicitud.get("contract_version") != CONTRACT_VERSION:
        errores.append(f"contract_version debe ser {CONTRACT_VERSION}")
    if not _uuid(solicitud.get("request_id")):
        errores.append("request_id debe ser un UUID valido")
    if solicitud.get("channel") not in CHANNELS_MUTACION:
        errores.append(f"channel debe ser uno de: {', '.join(CHANNELS_MUTACION)}")
    intent = solicitud.get("intent")
    if intent not in MUTATION_INTENTS:
        errores.append(f"intent debe ser uno de: {', '.join(MUTATION_INTENTS)}")
        raise ContratoInvalido(errores)

    payload = _objeto(solicitud, "payload", errores=errores, prefijo="solicitud")
    if payload is None:
        raise ContratoInvalido(errores or ["payload es obligatorio"])
    _validar_payload_mutacion(intent, payload, errores)
    if errores:
        raise ContratoInvalido(errores)


def _validar_payload_mutacion(
    intent: str, payload: Mapping[str, Any], errores: list[str]
) -> None:
    if intent == "CREATE_CONCRETE_ORDER":
        _campos(
            payload,
            requeridos=(
                "cliente_id",
                "resistencia",
                "volumen_m3",
                "forma_pago",
                "planta_codigo",
            ),
            permitidos=(
                "cliente_id",
                "planta_codigo",
                "planta_id",
                "resistencia",
                "volumen_m3",
                "precio_m3_override",
                "aplica_iva",
                "forma_pago",
                "abono_inicial_monto",
                "abono_inicial_metodo",
                "politica_viajes",
                "mixer_codigo",
                "chofer_nombre",
                "permitir_receta_provisional",
                "notas",
            ),
            errores=errores,
        )
        if not _uuid(payload.get("cliente_id")):
            errores.append("payload.cliente_id debe ser un UUID valido")
        _texto(payload, "planta_codigo", requerido=True, min_len=1, max_len=40, errores=errores)
        _texto(payload, "planta_id", nulo=True, errores=errores)
        if payload.get("planta_id") is not None and not _uuid(payload["planta_id"]):
            errores.append("payload.planta_id debe ser un UUID valido")
        _texto(payload, "resistencia", requerido=True, patron=_FC_RE, errores=errores)
        _decimal(
            payload,
            "volumen_m3",
            requerido=True,
            positivo=True,
            errores=errores,
        )
        _decimal(
            payload,
            "precio_m3_override",
            nulo=True,
            cuatro_decimales=True,
            errores=errores,
        )
        _booleano(payload, "aplica_iva", errores=errores)
        forma = _texto(
            payload, "forma_pago", requerido=True, enum=FORMAS_PAGO, errores=errores
        )
        _decimal(payload, "abono_inicial_monto", nulo=True, errores=errores)
        _texto(
            payload,
            "abono_inicial_metodo",
            nulo=True,
            enum=METODOS_PAGO,
            errores=errores,
        )
        _texto(payload, "politica_viajes", nulo=True, max_len=40, errores=errores)
        _texto(payload, "mixer_codigo", nulo=True, max_len=40, errores=errores)
        _texto(payload, "chofer_nombre", nulo=True, max_len=120, errores=errores)
        _booleano(payload, "permitir_receta_provisional", errores=errores)
        _texto(payload, "notas", nulo=True, max_len=500, errores=errores)
        if forma == "ABONO":
            if payload.get("abono_inicial_monto") is None:
                errores.append("payload.abono_inicial_monto es obligatorio para ABONO")
            if payload.get("abono_inicial_metodo") is None:
                errores.append("payload.abono_inicial_metodo es obligatorio para ABONO")
        elif forma in ("EFECTIVO", "TRANSFERENCIA", "FIADO"):
            if payload.get("abono_inicial_monto") is not None:
                errores.append("payload.abono_inicial_monto solo aplica a ABONO")
            if payload.get("abono_inicial_metodo") is not None:
                errores.append("payload.abono_inicial_metodo solo aplica a ABONO")

    elif intent == "CANCEL_CONCRETE_ORDER":
        _campos(
            payload,
            requeridos=("order_id", "motivo"),
            permitidos=("order_id", "motivo"),
            errores=errores,
        )
        if not _uuid(payload.get("order_id")):
            errores.append("payload.order_id debe ser un UUID valido")
        _texto(payload, "motivo", requerido=True, min_len=10, max_len=300, errores=errores)

    elif intent == "REGISTER_CLIENT_PAYMENT":
        _campos(
            payload,
            requeridos=("cliente_id", "fecha", "metodo", "monto"),
            permitidos=(
                "cliente_id",
                "order_id",
                "fecha",
                "metodo",
                "bolsa",
                "monto",
                "es_anticipo",
                "referencia",
            ),
            errores=errores,
        )
        if not _uuid(payload.get("cliente_id")):
            errores.append("payload.cliente_id debe ser un UUID valido")
        if payload.get("order_id") is not None and not _uuid(payload["order_id"]):
            errores.append("payload.order_id debe ser un UUID valido")
        _texto(payload, "fecha", requerido=True, errores=errores)
        if payload.get("fecha") is not None and not _fecha(payload["fecha"]):
            errores.append("payload.fecha debe ser una fecha ISO (AAAA-MM-DD)")
        _texto(payload, "metodo", requerido=True, enum=METODOS_PAGO, errores=errores)
        _texto(payload, "bolsa", nulo=True, enum=BOLSAS, errores=errores)
        _decimal(payload, "monto", requerido=True, positivo=True, errores=errores)
        _booleano(payload, "es_anticipo", errores=errores)
        _texto(payload, "referencia", nulo=True, max_len=120, errores=errores)

    elif intent == "REGISTER_PURCHASE":
        _campos(
            payload,
            requeridos=(
                "supplier_id",
                "fecha_compra",
                "modalidad_pago",
                "modo_recepcion",
                "items",
            ),
            permitidos=(
                "supplier_id",
                "fecha_compra",
                "modalidad_pago",
                "bolsa_pago_hoy",
                "monto_pagado_hoy",
                "fecha_vencimiento",
                "iva_monto",
                "modo_recepcion",
                "referencia_comprobante",
                "items",
            ),
            errores=errores,
        )
        if not _uuid(payload.get("supplier_id")):
            errores.append("payload.supplier_id debe ser un UUID valido")
        _texto(payload, "fecha_compra", requerido=True, errores=errores)
        if payload.get("fecha_compra") is not None and not _fecha(payload["fecha_compra"]):
            errores.append("payload.fecha_compra debe ser una fecha ISO")
        modalidad = _texto(
            payload,
            "modalidad_pago",
            requerido=True,
            enum=(
                "CONTADO_EFECTIVO",
                "CONTADO_TRANSFERENCIA",
                "CREDITO_PROVEEDOR",
                "MIXTO_ABONO_CREDITO",
            ),
            errores=errores,
        )
        _texto(payload, "bolsa_pago_hoy", nulo=True, enum=BOLSAS, errores=errores)
        _decimal(payload, "monto_pagado_hoy", nulo=True, errores=errores)
        _texto(payload, "fecha_vencimiento", nulo=True, errores=errores)
        if payload.get("fecha_vencimiento") is not None and not _fecha(
            payload["fecha_vencimiento"]
        ):
            errores.append("payload.fecha_vencimiento debe ser una fecha ISO")
        _decimal(payload, "iva_monto", nulo=True, errores=errores)
        _texto(
            payload,
            "modo_recepcion",
            requerido=True,
            enum=("INMEDIATA", "EN_TRANSITO", "NO_APLICA"),
            errores=errores,
        )
        _texto(
            payload,
            "referencia_comprobante",
            nulo=True,
            max_len=120,
            errores=errores,
        )
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            errores.append("payload.items debe ser una lista con al menos un item")
        else:
            for indice, item in enumerate(items):
                prefijo = f"payload.items[{indice}]"
                if not isinstance(item, Mapping):
                    errores.append(f"{prefijo} debe ser un objeto")
                    continue
                _campos(
                    item,
                    requeridos=(
                        "account_slug",
                        "descripcion",
                        "cantidad",
                        "costo_unitario",
                    ),
                    permitidos=(
                        "material_id",
                        "account_slug",
                        "descripcion",
                        "cantidad",
                        "costo_unitario",
                    ),
                    errores=errores,
                    prefijo=prefijo,
                )
                if item.get("material_id") is not None and not _uuid(
                    item["material_id"]
                ):
                    errores.append(f"{prefijo}.material_id debe ser un UUID valido")
                _texto(
                    item,
                    "account_slug",
                    requerido=True,
                    patron=_SLUG_RE,
                    errores=errores,
                    prefijo=prefijo,
                )
                _texto(
                    item,
                    "descripcion",
                    requerido=True,
                    min_len=2,
                    max_len=160,
                    errores=errores,
                    prefijo=prefijo,
                )
                _decimal(
                    item,
                    "cantidad",
                    requerido=True,
                    positivo=True,
                    cuatro_decimales=True,
                    errores=errores,
                    prefijo=prefijo,
                )
                _decimal(
                    item,
                    "costo_unitario",
                    requerido=True,
                    cuatro_decimales=True,
                    errores=errores,
                    prefijo=prefijo,
                )
        if modalidad in ("CONTADO_EFECTIVO", "CONTADO_TRANSFERENCIA"):
            if payload.get("bolsa_pago_hoy") is None:
                errores.append("payload.bolsa_pago_hoy es obligatorio para contado")
            if payload.get("monto_pagado_hoy") is None:
                errores.append("payload.monto_pagado_hoy es obligatorio para contado")
        if modalidad in ("CREDITO_PROVEEDOR", "MIXTO_ABONO_CREDITO"):
            if payload.get("fecha_vencimiento") is None:
                errores.append("payload.fecha_vencimiento es obligatorio para credito")

    elif intent == "RECEIVE_PURCHASED_MATERIAL":
        _campos(
            payload,
            requeridos=("purchase_item_id", "cantidad_recibida"),
            permitidos=("purchase_item_id", "cantidad_recibida", "guia_remision"),
            errores=errores,
        )
        if not _uuid(payload.get("purchase_item_id")):
            errores.append("payload.purchase_item_id debe ser un UUID valido")
        _decimal(
            payload,
            "cantidad_recibida",
            requerido=True,
            positivo=True,
            cuatro_decimales=True,
            errores=errores,
        )
        _texto(payload, "guia_remision", nulo=True, max_len=100, errores=errores)

    elif intent == "REGISTER_EXPENSE":
        _campos(
            payload,
            requeridos=(
                "fecha",
                "account_slug",
                "metodo",
                "bolsa",
                "monto",
                "descripcion",
            ),
            permitidos=(
                "fecha",
                "account_slug",
                "metodo",
                "bolsa",
                "monto",
                "referencia_comprobante",
                "descripcion",
            ),
            errores=errores,
        )
        _texto(payload, "fecha", requerido=True, errores=errores)
        if payload.get("fecha") is not None and not _fecha(payload["fecha"]):
            errores.append("payload.fecha debe ser una fecha ISO")
        _texto(
            payload,
            "account_slug",
            requerido=True,
            patron=_SLUG_RE,
            errores=errores,
        )
        _texto(payload, "metodo", requerido=True, enum=METODOS_PAGO, errores=errores)
        _texto(payload, "bolsa", requerido=True, enum=BOLSAS, errores=errores)
        _decimal(payload, "monto", requerido=True, positivo=True, errores=errores)
        _texto(
            payload,
            "referencia_comprobante",
            nulo=True,
            max_len=120,
            errores=errores,
        )
        _texto(
            payload,
            "descripcion",
            requerido=True,
            min_len=3,
            max_len=250,
            errores=errores,
        )

    elif intent == "PAY_SUPPLIER_DEBT":
        _campos(
            payload,
            requeridos=(
                "supplier_id",
                "purchase_id",
                "fecha",
                "metodo",
                "bolsa",
                "monto",
            ),
            permitidos=(
                "supplier_id",
                "purchase_id",
                "fecha",
                "metodo",
                "bolsa",
                "monto",
                "referencia",
            ),
            errores=errores,
        )
        if not _uuid(payload.get("supplier_id")):
            errores.append("payload.supplier_id debe ser un UUID valido")
        if not _uuid(payload.get("purchase_id")):
            errores.append("payload.purchase_id debe ser un UUID valido")
        _texto(payload, "fecha", requerido=True, errores=errores)
        if payload.get("fecha") is not None and not _fecha(payload["fecha"]):
            errores.append("payload.fecha debe ser una fecha ISO")
        _texto(payload, "metodo", requerido=True, enum=METODOS_PAGO, errores=errores)
        _texto(payload, "bolsa", requerido=True, enum=BOLSAS, errores=errores)
        _decimal(payload, "monto", requerido=True, positivo=True, errores=errores)
        _texto(payload, "referencia", nulo=True, max_len=120, errores=errores)

    elif intent == "PAY_BANK_LOAN_INSTALLMENT":
        _campos(
            payload,
            requeridos=(
                "liability_id",
                "fecha",
                "bolsa",
                "monto_capital",
                "monto_interes",
            ),
            permitidos=(
                "liability_id",
                "fecha",
                "bolsa",
                "monto_capital",
                "monto_interes",
                "referencia",
            ),
            errores=errores,
        )
        if not _uuid(payload.get("liability_id")):
            errores.append("payload.liability_id debe ser un UUID valido")
        _texto(payload, "fecha", requerido=True, errores=errores)
        if payload.get("fecha") is not None and not _fecha(payload["fecha"]):
            errores.append("payload.fecha debe ser una fecha ISO")
        _texto(payload, "bolsa", requerido=True, enum=BOLSAS, errores=errores)
        capital = _decimal(
            payload, "monto_capital", requerido=True, errores=errores
        )
        interes = _decimal(
            payload, "monto_interes", requerido=True, errores=errores
        )
        if capital is not None and interes is not None and capital + interes <= 0:
            errores.append(
                "payload.monto_capital + payload.monto_interes debe ser mayor que cero"
            )
        _texto(payload, "referencia", nulo=True, max_len=120, errores=errores)

    elif intent == "RUN_MONTHLY_DEPRECIATION":
        _campos(
            payload,
            requeridos=("periodo_ym",),
            permitidos=("periodo_ym", "asset_id"),
            errores=errores,
        )
        _texto(
            payload,
            "periodo_ym",
            requerido=True,
            patron=_PERIODO_RE,
            errores=errores,
        )
        if payload.get("asset_id") is not None and not _uuid(payload["asset_id"]):
            errores.append("payload.asset_id debe ser un UUID valido")

    elif intent == "SET_OPENING_BALANCES":
        _campos(
            payload,
            requeridos=("fecha_corte", "saldos"),
            permitidos=("fecha_corte", "saldos"),
            errores=errores,
        )
        _texto(payload, "fecha_corte", requerido=True, errores=errores)
        if payload.get("fecha_corte") is not None and not _fecha(
            payload["fecha_corte"]
        ):
            errores.append("payload.fecha_corte debe ser una fecha ISO")
        saldos = payload.get("saldos")
        if not isinstance(saldos, list) or not saldos:
            errores.append("payload.saldos debe ser una lista con al menos un saldo")
        else:
            for indice, saldo in enumerate(saldos):
                prefijo = f"payload.saldos[{indice}]"
                if not isinstance(saldo, Mapping):
                    errores.append(f"{prefijo} debe ser un objeto")
                    continue
                _campos(
                    saldo,
                    requeridos=("account_slug", "monto"),
                    permitidos=("account_slug", "monto"),
                    errores=errores,
                    prefijo=prefijo,
                )
                _texto(
                    saldo,
                    "account_slug",
                    requerido=True,
                    patron=_SLUG_RE,
                    errores=errores,
                    prefijo=prefijo,
                )
                _decimal(
                    saldo,
                    "monto",
                    requerido=True,
                    positivo=True,
                    errores=errores,
                    prefijo=prefijo,
                )

    elif intent == "RESOLVE_APPROVAL_REQUEST":
        _campos(
            payload,
            requeridos=("approval_request_id", "decision", "comentario"),
            permitidos=(
                "approval_request_id",
                "decision",
                "comentario",
                "modo_resolucion_cobro",
            ),
            errores=errores,
        )
        _texto(
            payload,
            "modo_resolucion_cobro",
            requerido=False,
            nulo=True,
            enum=(
                "CONVERTIR_A_ANTICIPO_CLIENTE",
                "DEVOLVER_DINERO_CAJA_O_BANCO",
            ),
            errores=errores,
        )
        if not _uuid(payload.get("approval_request_id")):
            errores.append("payload.approval_request_id debe ser un UUID valido")
        _texto(
            payload,
            "decision",
            requerido=True,
            enum=("APPROVED", "REJECTED"),
            errores=errores,
        )
        _texto(
            payload,
            "comentario",
            requerido=True,
            min_len=3,
            max_len=250,
            errores=errores,
        )

    elif intent == "CREATE_SUPPLIER":
        _campos(
            payload,
            requeridos=("nombre",),
            permitidos=("nombre", "identificacion", "telefono"),
            errores=errores,
        )
        _texto(
            payload, "nombre", requerido=True, min_len=2, max_len=160, errores=errores
        )
        _texto(
            payload, "identificacion", nulo=True, max_len=40, errores=errores
        )
        _texto(payload, "telefono", nulo=True, max_len=40, errores=errores)

    elif intent == "CREATE_FIXED_ASSET":
        _campos(
            payload,
            requeridos=(
                "codigo",
                "nombre",
                "categoria",
                "fecha_adquisicion",
                "fecha_inicio_depreciacion",
                "costo_historico",
                "valor_residual",
                "vida_util_meses",
            ),
            permitidos=(
                "codigo",
                "nombre",
                "categoria",
                "fecha_adquisicion",
                "fecha_inicio_depreciacion",
                "costo_historico",
                "valor_residual",
                "vida_util_meses",
            ),
            errores=errores,
        )
        _texto(payload, "codigo", requerido=True, min_len=1, max_len=40, errores=errores)
        _texto(payload, "nombre", requerido=True, min_len=2, max_len=160, errores=errores)
        _texto(
            payload,
            "categoria",
            requerido=True,
            enum=(
                "VEHICULO_PESADO",
                "MAQUINARIA_PLANTA",
                "EQUIPO_OFICINA",
                "TERRENO_INFRAESTRUCTURA",
            ),
            errores=errores,
        )
        for campo in ("fecha_adquisicion", "fecha_inicio_depreciacion"):
            _texto(payload, campo, requerido=True, errores=errores)
            if payload.get(campo) is not None and not _fecha(payload[campo]):
                errores.append(f"payload.{campo} debe ser una fecha ISO")
        costo = _decimal(
            payload, "costo_historico", requerido=True, positivo=True, errores=errores
        )
        residual = _decimal(
            payload, "valor_residual", requerido=True, errores=errores
        )
        if costo is not None and residual is not None and residual > costo:
            errores.append("payload.valor_residual no puede superar costo_historico")
        _entero(
            payload,
            "vida_util_meses",
            requerido=True,
            minimo=1,
            errores=errores,
        )

    elif intent == "CREATE_FINANCIAL_LIABILITY":
        _campos(
            payload,
            requeridos=(
                "entidad_financiera",
                "numero_operacion",
                "fecha_desembolso",
                "monto_original",
                "saldo_capital_actual",
                "tasa_interes_anual_pct",
                "cuota_mensual_referencial",
                "plazo_restante_meses",
            ),
            permitidos=(
                "entidad_financiera",
                "numero_operacion",
                "fecha_desembolso",
                "monto_original",
                "saldo_capital_actual",
                "tasa_interes_anual_pct",
                "cuota_mensual_referencial",
                "plazo_restante_meses",
            ),
            errores=errores,
        )
        _texto(
            payload,
            "entidad_financiera",
            requerido=True,
            min_len=2,
            max_len=120,
            errores=errores,
        )
        _texto(
            payload,
            "numero_operacion",
            requerido=True,
            min_len=1,
            max_len=80,
            errores=errores,
        )
        _texto(payload, "fecha_desembolso", requerido=True, errores=errores)
        if payload.get("fecha_desembolso") is not None and not _fecha(
            payload["fecha_desembolso"]
        ):
            errores.append("payload.fecha_desembolso debe ser una fecha ISO")
        _decimal(
            payload, "monto_original", requerido=True, positivo=True, errores=errores
        )
        _decimal(
            payload,
            "saldo_capital_actual",
            requerido=True,
            errores=errores,
        )
        _decimal(
            payload,
            "tasa_interes_anual_pct",
            requerido=True,
            errores=errores,
        )
        _decimal(
            payload,
            "cuota_mensual_referencial",
            requerido=True,
            errores=errores,
        )
        _entero(
            payload,
            "plazo_restante_meses",
            requerido=True,
            minimo=0,
            errores=errores,
        )


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------
def validar_consulta(solicitud: Any) -> None:
    errores: list[str] = []
    if not isinstance(solicitud, Mapping):
        raise ContratoInvalido(["la solicitud debe ser un objeto JSON"])
    _campos(
        solicitud,
        requeridos=("contract_version", "request_id", "channel", "intent", "filters"),
        permitidos=("contract_version", "request_id", "channel", "intent", "filters"),
        errores=errores,
        prefijo="solicitud",
    )
    if solicitud.get("contract_version") != CONTRACT_VERSION:
        errores.append(f"contract_version debe ser {CONTRACT_VERSION}")
    if not _uuid(solicitud.get("request_id")):
        errores.append("request_id debe ser un UUID valido")
    if solicitud.get("channel") not in CHANNELS_CONSULTA:
        errores.append(f"channel debe ser uno de: {', '.join(CHANNELS_CONSULTA)}")
    intent = solicitud.get("intent")
    if intent not in QUERY_INTENTS:
        errores.append(f"intent debe ser uno de: {', '.join(QUERY_INTENTS)}")
        raise ContratoInvalido(errores)
    filtros = _objeto(solicitud, "filters", errores=errores, prefijo="solicitud")
    if filtros is None:
        raise ContratoInvalido(errores or ["filters es obligatorio"])
    _campos(
        filtros,
        requeridos=(),
        permitidos=(
            "cliente_id",
            "order_id",
            "supplier_id",
            "fecha_desde",
            "fecha_hasta",
            "horizon_years",
        ),
        errores=errores,
        prefijo="filters",
    )
    for campo in ("cliente_id", "order_id", "supplier_id"):
        if filtros.get(campo) is not None and not _uuid(filtros[campo]):
            errores.append(f"filters.{campo} debe ser un UUID valido")
    for campo in ("fecha_desde", "fecha_hasta"):
        if filtros.get(campo) is not None and not _fecha(filtros[campo]):
            errores.append(f"filters.{campo} debe ser una fecha ISO")
    horizonte = filtros.get("horizon_years")
    if horizonte is not None and horizonte not in (1, 3, 5, 10):
        errores.append("filters.horizon_years debe ser 1, 3, 5 o 10")

    requeridos: dict[str, tuple[str, ...]] = {
        "GET_CLIENT_BALANCE": ("cliente_id",),
        "GET_DAILY_CASH_CLOSURE": ("fecha_desde",),
        "GET_INCOME_STATEMENT_PL": ("fecha_desde", "fecha_hasta"),
        "GET_VALUATION_AND_10Y_PROJECTION": ("horizon_years",),
        "GET_DEBT_CAPACITY_DSCR": ("horizon_years",),
    }
    for campo in requeridos.get(intent, ()):
        if filtros.get(campo) is None:
            errores.append(f"filters.{campo} es obligatorio para {intent}")
    if errores:
        raise ContratoInvalido(errores)


# ---------------------------------------------------------------------------
# Testigo de correccion
# ---------------------------------------------------------------------------
def validar_testigo(solicitud: Any) -> None:
    errores: list[str] = []
    if not isinstance(solicitud, Mapping):
        raise ContratoInvalido(["la solicitud debe ser un objeto JSON"])
    _campos(
        solicitud,
        requeridos=(
            "contract_version",
            "request_id",
            "channel",
            "intent",
            "target_table",
            "motivo",
            "changes",
        ),
        permitidos=(
            "contract_version",
            "request_id",
            "channel",
            "intent",
            "target_table",
            "target_record_id",
            "motivo",
            "changes",
        ),
        errores=errores,
        prefijo="solicitud",
    )
    if solicitud.get("contract_version") != CONTRACT_VERSION:
        errores.append(f"contract_version debe ser {CONTRACT_VERSION}")
    if not _uuid(solicitud.get("request_id")):
        errores.append("request_id debe ser un UUID valido")
    if solicitud.get("channel") not in CHANNELS_TESTIGO:
        errores.append(f"channel debe ser uno de: {', '.join(CHANNELS_TESTIGO)}")
    intent = solicitud.get("intent")
    if intent not in WITNESS_INTENTS:
        errores.append(f"intent debe ser uno de: {', '.join(WITNESS_INTENTS)}")
        raise ContratoInvalido(errores)
    _texto(
        solicitud,
        "target_table",
        requerido=True,
        enum=(
            "payments",
            "purchases",
            "supplier_payments",
            "inventory_movements",
            "accounting_accounts",
        ),
        errores=errores,
        prefijo="solicitud",
    )
    _texto(
        solicitud,
        "target_record_id",
        nulo=True,
        min_len=1,
        max_len=40,
        errores=errores,
        prefijo="solicitud",
    )
    _texto(
        solicitud,
        "motivo",
        requerido=True,
        min_len=10,
        max_len=300,
        errores=errores,
        prefijo="solicitud",
    )
    cambios = _objeto(solicitud, "changes", errores=errores, prefijo="solicitud")
    if cambios is None:
        raise ContratoInvalido(errores or ["changes es obligatorio"])
    _campos(
        cambios,
        requeridos=(),
        permitidos=(
            "nuevo_monto",
            "nuevo_metodo",
            "nueva_bolsa",
            "nuevo_account_slug",
            "nuevo_nombre_categoria",
            "account_type",
            "normal_balance",
            "parent_group",
            "default_bolsa",
            "requires_voucher",
            "source_account_id",
            "target_account_id",
        ),
        errores=errores,
        prefijo="changes",
    )
    _decimal(cambios, "nuevo_monto", nulo=True, errores=errores, prefijo="changes")
    _texto(
        cambios,
        "nuevo_metodo",
        nulo=True,
        enum=METODOS_PAGO,
        errores=errores,
        prefijo="changes",
    )
    _texto(
        cambios,
        "nueva_bolsa",
        nulo=True,
        enum=BOLSAS,
        errores=errores,
        prefijo="changes",
    )
    _texto(
        cambios,
        "nuevo_account_slug",
        nulo=True,
        patron=_SLUG_RE,
        errores=errores,
        prefijo="changes",
    )
    _texto(
        cambios,
        "nuevo_nombre_categoria",
        nulo=True,
        min_len=3,
        max_len=80,
        errores=errores,
        prefijo="changes",
    )
    _texto(
        cambios,
        "account_type",
        nulo=True,
        enum=("ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE"),
        errores=errores,
        prefijo="changes",
    )
    _texto(
        cambios,
        "normal_balance",
        nulo=True,
        enum=("DEBIT", "CREDIT"),
        errores=errores,
        prefijo="changes",
    )
    _texto(
        cambios,
        "parent_group",
        nulo=True,
        enum=MATERIALES_ACTIVO,
        errores=errores,
        prefijo="changes",
    )
    _texto(
        cambios,
        "default_bolsa",
        nulo=True,
        enum=("CAJA_DIARIA", "BANCO_GERENCIA", "CARTERA_O_PASIVO", "NO_MONETARIO"),
        errores=errores,
        prefijo="changes",
    )
    if cambios.get("requires_voucher") is not None and not isinstance(
        cambios["requires_voucher"], bool
    ):
        errores.append("changes.requires_voucher debe ser booleano")
    for campo in ("source_account_id", "target_account_id"):
        if cambios.get(campo) is not None and not _uuid(cambios[campo]):
            errores.append(f"changes.{campo} debe ser un UUID valido")

    if intent == "CREATE_ACCOUNTING_CATEGORY":
        if solicitud.get("target_table") != "accounting_accounts":
            errores.append(
                "target_table debe ser accounting_accounts para crear categoria"
            )
        for campo in (
            "nuevo_nombre_categoria",
            "account_type",
            "normal_balance",
            "parent_group",
            "default_bolsa",
            "requires_voucher",
        ):
            if cambios.get(campo) is None:
                errores.append(f"changes.{campo} es obligatorio para crear categoria")
    elif intent == "RENAME_ACCOUNTING_CATEGORY":
        if solicitud.get("target_table") != "accounting_accounts":
            errores.append(
                "target_table debe ser accounting_accounts para renombrar categoria"
            )
        if solicitud.get("target_record_id") is None:
            errores.append("target_record_id es obligatorio para renombrar")
        if cambios.get("nuevo_nombre_categoria") is None:
            errores.append("changes.nuevo_nombre_categoria es obligatorio")
    elif intent == "MERGE_ACCOUNTING_CATEGORIES":
        if solicitud.get("target_table") != "accounting_accounts":
            errores.append(
                "target_table debe ser accounting_accounts para fusionar categorias"
            )
        if cambios.get("source_account_id") is None:
            errores.append("changes.source_account_id es obligatorio")
        if cambios.get("target_account_id") is None:
            errores.append("changes.target_account_id es obligatorio")
    elif intent == "CORRECT_MOVEMENT_WITH_WITNESS":
        if solicitud.get("target_table") not in (
            "payments",
            "purchases",
            "supplier_payments",
        ):
            errores.append(
                "target_table debe ser payments, purchases o supplier_payments"
            )
        if solicitud.get("target_record_id") is None:
            errores.append("target_record_id es obligatorio para corregir")
        if not any(
            cambios.get(campo) is not None
            for campo in (
                "nuevo_monto",
                "nuevo_metodo",
                "nueva_bolsa",
                "nuevo_account_slug",
            )
        ):
            errores.append("changes debe incluir al menos una correccion")
    if errores:
        raise ContratoInvalido(errores)

# ---------------------------------------------------------------------------
# Respuesta del Gate
# ---------------------------------------------------------------------------
RESPONSE_STATUSES = ("ACCEPT", "REJECT", "PENDING_JULIO_APPROVAL")
REJECTION_CODES = (
    "UNAUTHORIZED_ACTOR",
    "UNAUTHORIZED_DOMAIN_ACCESS",
    "UNKNOWN_CRITICAL_FIELD",
    "MISSING_VOUCHER_REFERENCE",
    "MISSING_INVENTORY_ITEM_DATA",
    "INSUFFICIENT_SILO_STOCK",
    "PAYMENT_EXCEEDS_PENDING_BALANCE",
    "BOLSA_METHOD_MISMATCH",
    "PURCHASE_REQUIRES_CREDIT_NOTE",
    "DUPLICATE_CATEGORY_SIMILARITY",
    "IMMUTABLE_ROOT_ACCOUNT",
    "WITNESS_REASON_TOO_SHORT",
    "DEPRECIATION_ALREADY_RUN_FOR_PERIOD",
    "PAYLOAD_HASH_MISMATCH_ON_RETRY",
    "SCHEMA_VALIDATION_FAILED",
    "INVALID_IVA_COHERENCE",
    "INVALID_PURCHASE_TOTAL",
    "INVALID_ASSET_VALUES",
    "MISSING_MASTER_DATA",
    "DUPLICATE_REQUEST",
)
RESIDUAL_RISKS = (
    "CREDIT_LIMIT_EXCEEDED_WARNING",
    "MATERIAL_COST_OR_STOCK_UNSET",
    "PROVISIONAL_RECIPE_USED",
    "USING_BASELINE_SEED_FOR_10Y_PROJECTION",
    "OPENING_BALANCES_NOT_SET",
    "UNCONFIRMED_FINANCIAL_RATES",
    "SILO_STOCK_CRITICAL_ALERT",
    "PENDING_PHYSICAL_INVENTORY_RECONCILIATION",
    "COUNT_DATE_NOT_CONFIRMED",
    "HISTORICAL_IVA_NOT_CONFIRMED",
    "VALUATION_FORMULA_NOT_CONFIRMED",
    "DSCR_DEFINITION_NOT_CONFIRMED",
)


def validar_respuesta_gate(respuesta: Any) -> None:
    """Valida la forma de ``custodio_gate_response`` v1.3.0."""
    errores: list[str] = []
    if not isinstance(respuesta, Mapping):
        raise ContratoInvalido(["la respuesta debe ser un objeto JSON"])
    _campos(
        respuesta,
        requeridos=(
            "contract_version",
            "request_id",
            "status",
            "rejection_codes",
            "residual_risks",
            "data",
        ),
        permitidos=(
            "contract_version",
            "request_id",
            "status",
            "rejection_codes",
            "residual_risks",
            "witness_id",
            "transaction_group_id",
            "approval_request_id",
            "data",
        ),
        errores=errores,
        prefijo="respuesta",
    )
    if respuesta.get("contract_version") != CONTRACT_VERSION:
        errores.append(f"contract_version debe ser {CONTRACT_VERSION}")
    if not _uuid(respuesta.get("request_id")):
        errores.append("request_id debe ser un UUID valido")
    status = respuesta.get("status")
    if status not in RESPONSE_STATUSES:
        errores.append(f"status debe ser uno de: {', '.join(RESPONSE_STATUSES)}")

    codigos = respuesta.get("rejection_codes")
    if not isinstance(codigos, list):
        errores.append("rejection_codes debe ser una lista")
    else:
        for codigo in codigos:
            if codigo not in REJECTION_CODES:
                errores.append(f"rejection_code desconocido: {codigo}")

    riesgos = respuesta.get("residual_risks")
    if not isinstance(riesgos, list):
        errores.append("residual_risks debe ser una lista")
    else:
        for riesgo in riesgos:
            if riesgo not in RESIDUAL_RISKS:
                errores.append(f"residual_risk desconocido: {riesgo}")

    for campo in (
        "witness_id",
        "transaction_group_id",
        "approval_request_id",
    ):
        valor = respuesta.get(campo)
        if valor is not None and not _uuid(valor):
            errores.append(f"{campo} debe ser un UUID valido o null")

    if not isinstance(respuesta.get("data"), Mapping):
        errores.append("data debe ser un objeto")

    if status == "REJECT" and not codigos:
        errores.append("REJECT requiere al menos un rejection_code")
    if status == "ACCEPT" and codigos:
        errores.append("ACCEPT no admite rejection_codes")
    if status == "PENDING_JULIO_APPROVAL":
        if codigos:
            errores.append("PENDING_JULIO_APPROVAL no admite rejection_codes")
        if respuesta.get("approval_request_id") is None:
            errores.append("PENDING_JULIO_APPROVAL requiere approval_request_id")
    if errores:
        raise ContratoInvalido(errores)
