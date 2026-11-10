"""Gate del Custodio v1.3.0.

Punto unico de entrada para mutaciones, consultas y correcciones con testigo.

Contrato de operacion:

1. Valida la forma del contrato (``contracts.py``).
2. Autoriza por rol y dominio antes de tocar la base.
3. Es idempotente por ``request_id``: mismo payload devuelve la misma
   respuesta; un payload distinto con el mismo id se rechaza con
   ``PAYLOAD_HASH_MISMATCH_ON_RETRY``.
4. Ejecuta todo en una transaccion. Si una regla de negocio falla, la
   transaccion interna (savepoint) se revierte y se guarda un REJECT.
5. Escribe el asiento contable de cada documento aceptado.
6. Para anulaciones sin regla de reembolso confirmada devuelve
   ``PENDING_JULIO_APPROVAL`` sin tocar la orden.

No inventa datos: los precios, costos, tasas y saldos salen del payload o de
la base. Lo que falta queda pendiente y se reporta como riesgo residual.
"""

from __future__ import annotations

import calendar
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Mapping
from uuid import UUID, uuid4

import asyncpg

from ..db import setting
from ..m2_planta.kardex import anular_consumo_teorico, registrar_movimiento_real
from ..m3_secretaria.service import calcular_resumen_caja
from ..services.ordenes import (
    NuevaOrden,
    OrdenInvalidaError,
    crear_orden,
)
from . import catalog_hygiene, ledger, witness
from .contracts import (
    ContratoInvalido,
    validar_consulta,
    validar_mutacion,
    validar_respuesta_gate,
    validar_testigo,
)

CONTRACT_VERSION = "1.3.0"
UUID_NULO = "00000000-0000-4000-8000-000000000000"

ROLES = (
    "SUPERADMIN",
    "CONTADORA",
    "SECRETARIA",
    "BODEGA",
    "CHOFER",
    "CAJA_SECRETARIA",
    "BODEGA_PLANTA",
    "SYSTEM_CRON",
)

PERMISOS_MUTACION: dict[str, set[str]] = {
    "CREATE_CONCRETE_ORDER": {
        "SUPERADMIN",
        "CONTADORA",
        "SECRETARIA",
        "CAJA_SECRETARIA",
    },
    "CANCEL_CONCRETE_ORDER": {
        "SUPERADMIN",
        "CONTADORA",
        "SECRETARIA",
        "CAJA_SECRETARIA",
    },
    "REGISTER_CLIENT_PAYMENT": {
        "SUPERADMIN",
        "CONTADORA",
        "SECRETARIA",
        "CAJA_SECRETARIA",
    },
    "REGISTER_PURCHASE": {
        "SUPERADMIN",
        "CONTADORA",
        "SECRETARIA",
        "CAJA_SECRETARIA",
        "BODEGA",
        "BODEGA_PLANTA",
    },
    "RECEIVE_PURCHASED_MATERIAL": {"SUPERADMIN", "BODEGA", "BODEGA_PLANTA"},
    "REGISTER_EXPENSE": {
        "SUPERADMIN",
        "CONTADORA",
        "SECRETARIA",
        "CAJA_SECRETARIA",
    },
    "PAY_SUPPLIER_DEBT": {"SUPERADMIN", "CONTADORA"},
    "PAY_BANK_LOAN_INSTALLMENT": {"SUPERADMIN", "CONTADORA"},
    "RUN_MONTHLY_DEPRECIATION": {"SUPERADMIN", "CONTADORA", "SYSTEM_CRON"},
    "SET_OPENING_BALANCES": {"SUPERADMIN", "CONTADORA"},
    "RESOLVE_APPROVAL_REQUEST": {"SUPERADMIN"},
    "CREATE_SUPPLIER": {
        "SUPERADMIN",
        "CONTADORA",
        "SECRETARIA",
        "CAJA_SECRETARIA",
        "BODEGA",
        "BODEGA_PLANTA",
    },
    "CREATE_FIXED_ASSET": {"SUPERADMIN", "CONTADORA"},
    "CREATE_FINANCIAL_LIABILITY": {"SUPERADMIN", "CONTADORA"},
}

PERMISOS_CONSULTA: dict[str, set[str]] = {
    "GET_CLIENT_BALANCE": {
        "SUPERADMIN",
        "CONTADORA",
        "SECRETARIA",
        "CAJA_SECRETARIA",
    },
    "GET_DAILY_CASH_CLOSURE": {
        "SUPERADMIN",
        "CONTADORA",
        "SECRETARIA",
        "CAJA_SECRETARIA",
    },
    "GET_ACCOUNTS_PAYABLE": {"SUPERADMIN", "CONTADORA", "SYSTEM_CRON"},
    "GET_INVENTORY_AND_ALERTS": {
        "SUPERADMIN",
        "CONTADORA",
        "SECRETARIA",
        "BODEGA",
        "BODEGA_PLANTA",
        "CAJA_SECRETARIA",
        "SYSTEM_CRON",
    },
    "GET_DISPATCH_TIMELINE": {
        "SUPERADMIN",
        "CONTADORA",
        "SECRETARIA",
        "BODEGA",
        "BODEGA_PLANTA",
        "CAJA_SECRETARIA",
    },
    "GET_INCOME_STATEMENT_PL": {"SUPERADMIN", "CONTADORA", "SYSTEM_CRON"},
    "GET_BALANCE_SHEET_REALTIME": {"SUPERADMIN", "CONTADORA", "SYSTEM_CRON"},
    "GET_VALUATION_AND_10Y_PROJECTION": {
        "SUPERADMIN",
        "CONTADORA",
        "SYSTEM_CRON",
    },
    "GET_DEBT_CAPACITY_DSCR": {"SUPERADMIN", "CONTADORA", "SYSTEM_CRON"},
}

PERMISOS_TESTIGO: dict[str, set[str]] = {
    "CORRECT_MOVEMENT_WITH_WITNESS": {
        "SUPERADMIN",
        "CONTADORA",
        "SECRETARIA",
        "CAJA_SECRETARIA",
    },
    "CREATE_ACCOUNTING_CATEGORY": {"SUPERADMIN", "CONTADORA", "SECRETARIA"},
    "RENAME_ACCOUNTING_CATEGORY": {"SUPERADMIN", "CONTADORA"},
    "MERGE_ACCOUNTING_CATEGORIES": {"SUPERADMIN", "CONTADORA"},
}


class RechazoGate(Exception):
    """Rechazo de negocio con un codigo del contrato."""

    def __init__(
        self,
        codigo: str,
        data: Mapping[str, Any] | None = None,
        residual_risks: tuple[str, ...] = (),
    ) -> None:
        self.codigo = codigo
        self.data = dict(data or {})
        self.residual_risks = list(residual_risks)
        super().__init__(codigo)


@dataclass(frozen=True)
class Actor:
    role: str
    id: str


def hash_solicitud(solicitud: Mapping[str, Any]) -> str:
    """SHA-256 canonico del payload completo, incluido el request_id."""
    texto = json.dumps(
        solicitud, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _uuid_valido(valor: Any) -> bool:
    if not isinstance(valor, str):
        return False
    try:
        UUID(valor)
        return True
    except (ValueError, AttributeError):
        return False


def _request_id(solicitud: Mapping[str, Any]) -> str:
    valor = solicitud.get("request_id") if isinstance(solicitud, Mapping) else None
    return valor if _uuid_valido(valor) else UUID_NULO


def _jsonable(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, UUID):
        return str(valor)
    if isinstance(valor, Mapping):
        return {str(k): _jsonable(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_jsonable(v) for v in valor]
    return valor


def respuesta_gate(
    request_id: str,
    status: str,
    *,
    rejection_codes: list[str] | None = None,
    residual_risks: list[str] | None = None,
    data: Mapping[str, Any] | None = None,
    witness_id: str | None = None,
    transaction_group_id: str | None = None,
    approval_request_id: str | None = None,
) -> dict[str, Any]:
    """Construye y autovalida una respuesta del contrato v1.3.0."""
    respuesta = {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "status": status,
        "rejection_codes": list(rejection_codes or []),
        "residual_risks": list(residual_risks or []),
        "witness_id": witness_id,
        "transaction_group_id": transaction_group_id,
        "approval_request_id": approval_request_id,
        "data": _jsonable(dict(data or {})),
    }
    validar_respuesta_gate(respuesta)
    return respuesta


def autorizar(
    actor: Actor,
    intent: str,
    channel: str,
    tipo: str,
) -> str | None:
    """Devuelve el codigo de rechazo o None si el actor puede ejecutar."""
    if actor is None or actor.role not in ROLES or not str(actor.id or "").strip():
        return "UNAUTHORIZED_ACTOR"
    if channel not in ("WEB_PANEL", "WHATSAPP", "SYSTEM_CRON", "TEST"):
        return "UNAUTHORIZED_DOMAIN_ACCESS"
    if actor.role == "SYSTEM_CRON" and channel != "SYSTEM_CRON":
        return "UNAUTHORIZED_ACTOR"
    if channel == "SYSTEM_CRON" and actor.role != "SYSTEM_CRON":
        return "UNAUTHORIZED_ACTOR"

    permisos = {
        "mutacion": PERMISOS_MUTACION,
        "consulta": PERMISOS_CONSULTA,
        "testigo": PERMISOS_TESTIGO,
    }[tipo]
    permitidos = permisos.get(intent)
    if permitidos is None:
        return "UNAUTHORIZED_DOMAIN_ACCESS"
    if actor.role not in permitidos:
        return "UNAUTHORIZED_DOMAIN_ACCESS"
    return None


def _decimal(valor: Any, campo: str, *, lugares: int = 2) -> Decimal:
    try:
        numero = valor if isinstance(valor, Decimal) else Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise RechazoGate(
            "SCHEMA_VALIDATION_FAILED", {"errores": [f"{campo} no es decimal"]}
        ) from exc
    cuantizado = numero.quantize(Decimal(1).scaleb(-lugares))
    if numero != cuantizado:
        raise RechazoGate(
            "SCHEMA_VALIDATION_FAILED",
            {"errores": [f"{campo} supera {lugares} decimales"]},
        )
    return cuantizado


def _decimal_opcional(valor: Any, campo: str, *, lugares: int = 2) -> Decimal | None:
    if valor is None:
        return None
    return _decimal(valor, campo, lugares=lugares)


def _fecha(valor: Any, campo: str) -> date:
    try:
        return date.fromisoformat(str(valor))
    except (TypeError, ValueError) as exc:
        raise RechazoGate(
            "SCHEMA_VALIDATION_FAILED",
            {"errores": [f"{campo} no es una fecha ISO"]},
        ) from exc


def _bolsa_coherente(metodo: str, bolsa: str | None, campo: str) -> str:
    """La bolsa fisica debe corresponder al metodo de pago.

    Efectivo entra a la caja diaria; una transferencia sale del banco. Si no
    se envia la bolsa, se deriva del metodo en lugar de adivinar otra.
    """
    esperada = "CAJA_DIARIA" if metodo == "EFECTIVO" else "BANCO_GERENCIA"
    if bolsa is None:
        return esperada
    if bolsa != esperada:
        raise RechazoGate(
            "BOLSA_METHOD_MISMATCH",
            {
                "errores": [
                    f"{campo}: el metodo {metodo} exige {esperada}, no {bolsa}"
                ]
            },
        )
    return bolsa


def _exigir_comprobante(
    cuenta: asyncpg.Record,
    referencia: Any,
    contexto: str,
) -> None:
    """Si la cuenta exige comprobante, la referencia no puede venir vacia."""
    if cuenta["requires_voucher"] and not str(referencia or "").strip():
        raise RechazoGate(
            "MISSING_VOUCHER_REFERENCE",
            {
                "cuenta": cuenta["slug"],
                "errores": [f"{contexto} requiere referencia de comprobante"],
            },
        )


def _json_cargado(valor: Any) -> Any:
    if isinstance(valor, str):
        try:
            return json.loads(valor)
        except json.JSONDecodeError:
            return {}
    return valor or {}


class Gate:
    """Ejecuta el contrato del Custodio contra un pool de PostgreSQL."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # ------------------------------------------------------------------
    # Mutaciones
    # ------------------------------------------------------------------
    async def mutar(
        self, solicitud: Mapping[str, Any], actor: Actor
    ) -> dict[str, Any]:
        request_id = _request_id(solicitud)
        try:
            validar_mutacion(solicitud)
        except ContratoInvalido as exc:
            return respuesta_gate(
                request_id,
                "REJECT",
                rejection_codes=["SCHEMA_VALIDATION_FAILED"],
                data={"errores": exc.errores},
            )

        codigo = autorizar(actor, solicitud["intent"], solicitud["channel"], "mutacion")
        if codigo is not None:
            return respuesta_gate(
                request_id,
                "REJECT",
                rejection_codes=[codigo],
                data={"actor_role": actor.role if actor else None,
                      "intent": solicitud.get("intent")},
            )

        sha = hash_solicitud(solicitud)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                previa = await conn.fetchrow(
                    "SELECT * FROM processed_requests WHERE request_id = $1 FOR UPDATE",
                    request_id,
                )
                if previa is not None:
                    return self._reintento(previa, sha, actor, request_id)

                await conn.execute(
                    """
                    INSERT INTO processed_requests
                        (request_id, payload_sha256, actor_role, actor_id,
                         channel, intent, response_status, response_payload)
                    VALUES ($1, $2, $3, $4, $5, $6, 'IN_PROGRESS', '{}'::jsonb)
                    """,
                    request_id,
                    sha,
                    actor.role,
                    str(actor.id),
                    solicitud["channel"],
                    solicitud["intent"],
                )

                try:
                    async with conn.transaction():
                        respuesta = await self._despachar_mutacion(
                            conn, solicitud, actor
                        )
                except RechazoGate as exc:
                    respuesta = respuesta_gate(
                        request_id,
                        "REJECT",
                        rejection_codes=[exc.codigo],
                        residual_risks=exc.residual_risks,
                        data=exc.data,
                    )
                except (
                    catalog_hygiene.ErrorCatalogo,
                    witness.ErrorTestigo,
                    ledger.AsientoInvalido,
                    ledger.CuentaNoExiste,
                ) as exc:
                    respuesta = respuesta_gate(
                        request_id,
                        "REJECT",
                        rejection_codes=[
                            getattr(exc, "codigo", "SCHEMA_VALIDATION_FAILED")
                        ],
                        data={"errores": [str(exc)]},
                    )
                except OrdenInvalidaError as exc:
                    respuesta = respuesta_gate(
                        request_id,
                        "REJECT",
                        rejection_codes=["SCHEMA_VALIDATION_FAILED"],
                        data={"errores": [str(exc)]},
                    )
                except asyncpg.UniqueViolationError as exc:
                    respuesta = respuesta_gate(
                        request_id,
                        "REJECT",
                        rejection_codes=["SCHEMA_VALIDATION_FAILED"],
                        data={"errores": [f"registro duplicado: {exc}" ]},
                    )

                await conn.execute(
                    """
                    UPDATE processed_requests
                       SET response_status = $2,
                           response_payload = $3::jsonb,
                           updated_at = now()
                     WHERE request_id = $1
                    """,
                    request_id,
                    respuesta["status"],
                    json.dumps(respuesta, ensure_ascii=False),
                )
                return respuesta

    def _reintento(
        self,
        previa: asyncpg.Record,
        sha: str,
        actor: Actor,
        request_id: str,
    ) -> dict[str, Any]:
        if previa["payload_sha256"] != sha:
            return respuesta_gate(
                request_id,
                "REJECT",
                rejection_codes=["PAYLOAD_HASH_MISMATCH_ON_RETRY"],
                data={"motivo": "el request_id ya se uso con otro payload"},
            )
        if previa["actor_role"] != actor.role or previa["actor_id"] != str(actor.id):
            return respuesta_gate(
                request_id,
                "REJECT",
                rejection_codes=["UNAUTHORIZED_ACTOR"],
                data={"motivo": "el request_id pertenece a otro actor"},
            )
        guardada = _json_cargado(previa["response_payload"])
        if not isinstance(guardada, Mapping) or not guardada:
            return respuesta_gate(
                request_id,
                "REJECT",
                rejection_codes=["DUPLICATE_REQUEST"],
                data={"motivo": "la solicitud sigue en proceso o no tiene respuesta"},
            )
        return dict(guardada)

    async def _despachar_mutacion(
        self,
        conn: asyncpg.Connection,
        solicitud: Mapping[str, Any],
        actor: Actor,
    ) -> dict[str, Any]:
        manejadores = {
            "CREATE_CONCRETE_ORDER": self._crear_orden,
            "CANCEL_CONCRETE_ORDER": self._cancelar_orden,
            "REGISTER_CLIENT_PAYMENT": self._pago_cliente,
            "REGISTER_PURCHASE": self._registrar_compra,
            "RECEIVE_PURCHASED_MATERIAL": self._recibir_material,
            "REGISTER_EXPENSE": self._registrar_gasto,
            "PAY_SUPPLIER_DEBT": self._pagar_proveedor,
            "PAY_BANK_LOAN_INSTALLMENT": self._pagar_prestamo,
            "RUN_MONTHLY_DEPRECIATION": self._depreciacion_mensual,
            "SET_OPENING_BALANCES": self._saldos_apertura,
            "RESOLVE_APPROVAL_REQUEST": self._resolver_aprobacion,
            "CREATE_SUPPLIER": self._crear_proveedor,
            "CREATE_FIXED_ASSET": self._crear_activo,
            "CREATE_FINANCIAL_LIABILITY": self._crear_pasivo,
        }
        manejador = manejadores.get(solicitud["intent"])
        if manejador is None:
            raise RechazoGate(
                "UNAUTHORIZED_DOMAIN_ACCESS",
                {"intent": solicitud["intent"]},
            )
        return await manejador(conn, solicitud, actor)

    # ------------------------------------------------------------------
    # 1. Ventas
    # ------------------------------------------------------------------
    async def _crear_orden(
        self,
        conn: asyncpg.Connection,
        solicitud: Mapping[str, Any],
        actor: Actor,
    ) -> dict[str, Any]:
        payload = solicitud["payload"]
        datos = NuevaOrden(
            cliente_id=payload["cliente_id"],
            resistencia=payload["resistencia"],
            volumen_m3=_decimal(payload["volumen_m3"], "volumen_m3", lugares=2),
            planta_codigo=payload["planta_codigo"],
            forma_pago=payload["forma_pago"],
            precio_m3=_decimal_opcional(
                payload.get("precio_m3_override"),
                "precio_m3_override",
                lugares=4,
            ),
            creada_por=actor.id,
            notas=payload.get("notas"),
            politica_viajes=payload.get("politica_viajes"),
            permitir_receta_provisional=payload.get(
                "permitir_receta_provisional", True
            ),
            mixer_codigo=payload.get("mixer_codigo"),
            chofer_nombre=payload.get("chofer_nombre"),
            aplica_iva=payload.get("aplica_iva"),
            abono_inicial_monto=_decimal_opcional(
                payload.get("abono_inicial_monto"),
                "abono_inicial_monto",
                lugares=2,
            ),
            abono_inicial_metodo=payload.get("abono_inicial_metodo"),
        )
        resultado = await crear_orden(self.pool, datos, conn=conn)

        grupo = None
        asiento = False
        if resultado.total_con_iva is not None and resultado.total_con_iva > 0:
            subtotal = resultado.total or Decimal("0")
            iva = resultado.iva_monto or Decimal("0")
            lineas = [
                ledger.linea_debe(ledger.CUENTAS_POR_COBRAR, resultado.total_con_iva),
                ledger.linea_haber(ledger.VENTAS, subtotal),
            ]
            if iva > 0:
                lineas.append(ledger.linea_haber(ledger.IVA_POR_LIQUIDAR, iva))
            if (
                resultado.cobro_inicial_monto is not None
                and resultado.cobro_inicial_monto > 0
            ):
                pago = await conn.fetchrow(
                    """
                    SELECT p.bolsa, aa.slug AS cuenta
                      FROM payments p
                      LEFT JOIN accounting_accounts aa ON aa.id = p.account_id
                     WHERE p.id = $1
                    """,
                    resultado.cobro_inicial_id,
                )
                cuenta_caja = (
                    pago["cuenta"]
                    if pago is not None and pago["cuenta"]
                    else ledger.slug_caja(pago["bolsa"] if pago else "CAJA_DIARIA")
                )
                lineas.append(
                    ledger.linea_debe(cuenta_caja, resultado.cobro_inicial_monto)
                )
                lineas.append(
                    ledger.linea_haber(
                        ledger.CUENTAS_POR_COBRAR, resultado.cobro_inicial_monto
                    )
                )
            fecha = await conn.fetchval("SELECT CURRENT_DATE")
            grupo = await ledger.registrar_asiento(
                conn,
                fecha=fecha,
                source_type="ORDER",
                source_id=resultado.orden_id,
                descripcion=f"Venta orden #{resultado.orden_numero}",
                created_by_role=actor.role,
                lineas=lineas,
            )
            asiento = True

        riesgos: list[str] = []
        if resultado.excede_cupo_credito:
            riesgos.append("CREDIT_LIMIT_EXCEEDED_WARNING")
        if (
            resultado.consumo_orden is not None
            and resultado.consumo_orden.get("provisional")
        ):
            riesgos.append("PROVISIONAL_RECIPE_USED")
        sin_dato = await conn.fetchval(
            """
            SELECT count(*)
              FROM inventory_movements im
              JOIN materials m ON m.id = im.material_id
             WHERE im.order_id = $1
               AND (im.costo_unitario_snapshot IS NULL OR m.stock_actual IS NULL)
            """,
            resultado.orden_id,
        )
        if sin_dato:
            riesgos.append("MATERIAL_COST_OR_STOCK_UNSET")

        return respuesta_gate(
            solicitud["request_id"],
            "ACCEPT",
            residual_risks=riesgos,
            transaction_group_id=grupo,
            data={
                "orden_id": resultado.orden_id,
                "orden_numero": resultado.orden_numero,
                "total_viajes": resultado.total_viajes,
                "subtotal": resultado.total,
                "iva_pct": resultado.iva_pct,
                "iva_monto": resultado.iva_monto,
                "total_con_iva": resultado.total_con_iva,
                "cobro_inicial_id": resultado.cobro_inicial_id,
                "cobro_inicial_monto": resultado.cobro_inicial_monto,
                "asiento_registrado": asiento,
                "advertencias": resultado.advertencias,
            },
        )

    async def _cancelar_orden(
        self,
        conn: asyncpg.Connection,
        solicitud: Mapping[str, Any],
        actor: Actor,
    ) -> dict[str, Any]:
        payload = solicitud["payload"]
        orden = await conn.fetchrow(
            """
            SELECT id::text, numero, estado, total_con_iva, total
              FROM orders
             WHERE id = $1
             FOR UPDATE
            """,
            payload["order_id"],
        )
        if orden is None:
            raise RechazoGate(
                "SCHEMA_VALIDATION_FAILED",
                {"errores": ["la orden no existe"]},
            )
        if orden["estado"] == "ANULADA":
            raise RechazoGate(
                "DUPLICATE_REQUEST",
                {"estado": "ANULADA", "orden_id": orden["id"]},
            )

        pendiente = await conn.fetchrow(
            """
            SELECT id::text
              FROM approval_requests
             WHERE status = 'PENDING'
               AND intent = 'CANCEL_CONCRETE_ORDER'
               AND contract_payload->>'order_id' = $1
             ORDER BY created_at
             LIMIT 1
            """,
            payload["order_id"],
        )
        if pendiente is not None:
            aprobacion_id = pendiente["id"]
        else:
            aprobacion_id = str(uuid4())
            await conn.execute(
                """
                INSERT INTO approval_requests
                    (id, original_request_id, requester_role, requester_id,
                     intent, contract_payload, motivo)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
                """,
                aprobacion_id,
                solicitud["request_id"],
                actor.role,
                str(actor.id),
                "CANCEL_CONCRETE_ORDER",
                json.dumps(dict(payload), ensure_ascii=False),
                payload["motivo"],
            )

        return respuesta_gate(
            solicitud["request_id"],
            "PENDING_JULIO_APPROVAL",
            approval_request_id=aprobacion_id,
            data={
                "orden_id": orden["id"],
                "orden_numero": orden["numero"],
                "estado_actual": orden["estado"],
                "aviso": (
                    "La anulacion queda pendiente de Julio: no hay regla de "
                    "reembolso confirmada. No se toco la orden ni sus pagos."
                ),
            },
        )

    # ------------------------------------------------------------------
    # 2. Cobros y gastos
    # ------------------------------------------------------------------
    async def _pago_cliente(
        self,
        conn: asyncpg.Connection,
        solicitud: Mapping[str, Any],
        actor: Actor,
    ) -> dict[str, Any]:
        payload = solicitud["payload"]
        cliente = await conn.fetchrow(
            "SELECT id::text, nombre FROM clients WHERE id = $1",
            payload["cliente_id"],
        )
        if cliente is None:
            raise RechazoGate(
                "MISSING_MASTER_DATA",
                {"errores": ["el cliente no existe"]},
            )

        monto = _decimal(payload["monto"], "monto", lugares=2)
        if monto <= 0:
            raise RechazoGate(
                "SCHEMA_VALIDATION_FAILED",
                {"errores": ["el monto debe ser mayor que cero"]},
            )
        order_id = payload.get("order_id")
        es_anticipo = bool(payload.get("es_anticipo", False))

        # v4.4.0: reglas de pagos parametrizadas. El default oficial permite
        # abono parcial y anticipo; el excedente se separa a 2102.
        cfg = await setting(self.pool, "secretaria.pagos", {}) or {}
        if not isinstance(cfg, dict):
            cfg = {}
        try:
            monto_minimo = Decimal(str(cfg.get("monto_minimo", "0.01")))
        except (InvalidOperation, ValueError):
            monto_minimo = Decimal("0.01")
        if monto < monto_minimo:
            raise RechazoGate(
                "SCHEMA_VALIDATION_FAILED",
                {
                    "errores": [f"el monto es menor al minimo {monto_minimo}"],
                    "monto_minimo": float(monto_minimo),
                },
            )
        if es_anticipo and not bool(cfg.get("permitir_anticipo", True)):
            raise RechazoGate(
                "SCHEMA_VALIDATION_FAILED",
                {"errores": ["los anticipos no estan habilitados"]},
            )
        abono_parcial = bool(cfg.get("abono_parcial", True))

        # Bloquea la fila del cliente para que dos cobros concurrentes no
        # sobrepasen el saldo. La vista no se puede bloquear; el cliente si.
        cliente = await conn.fetchrow(
            "SELECT id::text, nombre FROM clients WHERE id = $1 FOR UPDATE",
            payload["cliente_id"],
        )
        if cliente is None:
            raise RechazoGate(
                "MISSING_MASTER_DATA",
                {"errores": ["el cliente no existe"]},
            )
        saldo_cliente = Decimal(
            str(
                await conn.fetchval(
                    """
                    SELECT COALESCE(saldo_pendiente, 0)
                      FROM v_cliente_saldo
                     WHERE id = $1
                    """,
                    payload["cliente_id"],
                )
                or "0"
            )
        )

        parte_cxc = Decimal("0")
        parte_anticipo = Decimal("0")
        if order_id is not None:
            orden = await conn.fetchrow(
                """
                SELECT id::text, cliente_id::text, estado,
                       COALESCE(total_con_iva, total) AS total_bruto
                  FROM orders
                 WHERE id = $1
                 FOR UPDATE
                """,
                order_id,
            )
            if orden is None or orden["cliente_id"] != payload["cliente_id"]:
                raise RechazoGate(
                    "MISSING_MASTER_DATA",
                    {"errores": ["la orden no existe o no pertenece al cliente"]},
                )
            if orden["estado"] == "ANULADA":
                raise RechazoGate(
                    "SCHEMA_VALIDATION_FAILED",
                    {"errores": ["la orden esta anulada"]},
                )
            pagado = await conn.fetchval(
                """
                SELECT COALESCE(sum(monto), 0)
                  FROM payments
                 WHERE order_id = $1
                   AND tipo_movimiento = 'COBRO'
                   AND deleted_at IS NULL
                """,
                order_id,
            )
            total = Decimal(str(orden["total_bruto"] or "0"))
            saldo_orden = total - Decimal(str(pagado))
            if monto > saldo_orden + Decimal("0.01") and not es_anticipo:
                raise RechazoGate(
                    "PAYMENT_EXCEEDS_PENDING_BALANCE",
                    {
                        "errores": [
                            "el cobro supera el saldo de la orden; "
                            "marque es_anticipo=true para el excedente"
                        ],
                        "saldo_pendiente": float(max(saldo_orden, Decimal("0"))),
                        "monto": float(monto),
                    },
                )
            if not abono_parcial and not es_anticipo and monto < saldo_orden - Decimal("0.01"):
                raise RechazoGate(
                    "SCHEMA_VALIDATION_FAILED",
                    {
                        "errores": [
                            "el abono parcial esta deshabilitado; "
                            "el cobro debe cubrir el saldo de la orden"
                        ],
                        "saldo_orden": float(max(saldo_orden, Decimal("0"))),
                        "monto": float(monto),
                    },
                )
            parte_cxc = min(monto, max(saldo_orden, Decimal("0")))
            parte_anticipo = monto - parte_cxc
        else:
            if monto > saldo_cliente + Decimal("0.01") and not es_anticipo:
                raise RechazoGate(
                    "PAYMENT_EXCEEDS_PENDING_BALANCE",
                    {
                        "errores": [
                            "el cobro supera el saldo pendiente del cliente; "
                            "marque es_anticipo=true para el excedente"
                        ],
                        "saldo_pendiente": float(saldo_cliente),
                        "monto": float(monto),
                    },
                )
            if not abono_parcial and not es_anticipo and monto < saldo_cliente - Decimal("0.01"):
                raise RechazoGate(
                    "SCHEMA_VALIDATION_FAILED",
                    {
                        "errores": [
                            "el abono parcial esta deshabilitado; "
                            "el cobro debe cubrir el saldo del cliente"
                        ],
                        "saldo_pendiente": float(saldo_cliente),
                        "monto": float(monto),
                    },
                )
            parte_cxc = min(monto, max(saldo_cliente, Decimal("0")))
            parte_anticipo = monto - parte_cxc

        metodo = payload["metodo"]
        bolsa = _bolsa_coherente(metodo, payload.get("bolsa"), "bolsa")
        cuenta_slug = ledger.slug_caja(bolsa)
        cuenta = await ledger.cuenta(conn, cuenta_slug, bloquear=True)
        _exigir_comprobante(cuenta, payload.get("referencia"), "el cobro")
        fecha = _fecha(payload["fecha"], "fecha")
        pago = await conn.fetchrow(
            """
            INSERT INTO payments
                (order_id, cliente_id, fecha, tipo_movimiento, metodo, monto,
                 referencia, account_id, bolsa, es_anticipo)
            VALUES ($1, $2, $3, 'COBRO', $4, $5, $6, $7, $8, $9)
            RETURNING id::text, monto, fecha
            """,
            order_id,
            payload["cliente_id"],
            fecha,
            metodo,
            monto,
            payload.get("referencia"),
            cuenta["id"],
            bolsa,
            es_anticipo,
        )
        lineas = [ledger.linea_debe(cuenta_slug, monto)]
        if parte_cxc > 0:
            lineas.append(
                ledger.linea_haber(ledger.CUENTAS_POR_COBRAR, parte_cxc)
            )
        if parte_anticipo > 0:
            lineas.append(
                ledger.linea_haber(ledger.ANTICIPOS_CLIENTES, parte_anticipo)
            )
        grupo = await ledger.registrar_asiento(
            conn,
            fecha=fecha,
            source_type="CLIENT_PAYMENT",
            source_id=pago["id"],
            descripcion=(
                f"Cobro cliente {cliente['nombre']}"
                + (" (anticipo)" if parte_anticipo > 0 else "")
            ),
            created_by_role=actor.role,
            lineas=lineas,
        )
        saldo_actual = await conn.fetchrow(
            """
            SELECT COALESCE(saldo_pendiente, 0) AS saldo_pendiente,
                   COALESCE(total_cobrado, 0) AS total_cobrado,
                   COALESCE(saldo_a_favor, 0) AS saldo_a_favor
              FROM v_cliente_saldo
             WHERE id = $1
            """,
            payload["cliente_id"],
        )
        return respuesta_gate(
            solicitud["request_id"],
            "ACCEPT",
            transaction_group_id=grupo,
            data={
                "payment_id": pago["id"],
                "cliente_id": cliente["id"],
                "order_id": order_id,
                "monto": monto,
                "metodo": payload["metodo"],
                "bolsa": bolsa,
                "es_anticipo": es_anticipo,
                "parte_cxc": parte_cxc,
                "parte_anticipo": parte_anticipo,
                "saldo_pendiente": (
                    Decimal(str(saldo_actual["saldo_pendiente"]))
                    if saldo_actual is not None
                    else None
                ),
                "total_cobrado": (
                    Decimal(str(saldo_actual["total_cobrado"]))
                    if saldo_actual is not None
                    else None
                ),
                "saldo_a_favor": (
                    Decimal(str(saldo_actual["saldo_a_favor"]))
                    if saldo_actual is not None
                    else None
                ),
            },
        )

    async def _registrar_gasto(
        self,
        conn: asyncpg.Connection,
        solicitud: Mapping[str, Any],
        actor: Actor,
    ) -> dict[str, Any]:
        payload = solicitud["payload"]
        try:
            cuenta = await ledger.cuenta(
                conn, payload["account_slug"], bloquear=True
            )
        except ledger.CuentaNoExiste as exc:
            raise RechazoGate(
                "MISSING_MASTER_DATA", {"errores": [str(exc)]}
            ) from exc
        if str(cuenta["default_bolsa"] or "").upper() == "NO_MONETARIO":
            raise RechazoGate(
                "NON_MONETARY_ACCOUNT_IN_PAYMENT",
                {
                    "cuenta": cuenta["slug"],
                    "errores": [
                        "una cuenta NO_MONETARIO (depreciacion, merma) no se "
                        "paga en ventanilla"
                    ],
                },
            )
        # El anticipo de sueldo es un ACTIVO: se entrega dinero hoy y se cruza
        # contra la nomina. No es un gasto, pero si un movimiento de ventanilla.
        if (
            cuenta["account_type"] != "EXPENSE"
            and cuenta["slug"] != "anticipos_sueldo_personal"
        ):
            raise RechazoGate(
                "SCHEMA_VALIDATION_FAILED",
                {"errores": ["la cuenta del gasto debe ser de tipo EXPENSE"]},
            )
        if cuenta["requires_voucher"] and not payload.get("referencia_comprobante"):
            raise RechazoGate(
                "MISSING_VOUCHER_REFERENCE",
                {"cuenta": cuenta["slug"]},
            )

        monto = _decimal(payload["monto"], "monto", lugares=2)
        bolsa = _bolsa_coherente(payload["metodo"], payload["bolsa"], "bolsa")
        fecha = _fecha(payload["fecha"], "fecha")
        tipo = (
            "GASTO_CAJA_CHICA" if bolsa == "CAJA_DIARIA" else "GASTO_BANCARIO"
        )
        pago = await conn.fetchrow(
            """
            INSERT INTO payments
                (cliente_id, fecha, tipo_movimiento, metodo, monto, referencia,
                 account_id, bolsa)
            VALUES (NULL, $1, $2, $3, $4, $5, $6, $7)
            RETURNING id::text
            """,
            fecha,
            tipo,
            payload["metodo"],
            monto,
            payload.get("referencia_comprobante"),
            cuenta["id"],
            bolsa,
        )
        grupo = await ledger.registrar_asiento(
            conn,
            fecha=fecha,
            source_type="EXPENSE",
            source_id=pago["id"],
            descripcion=payload["descripcion"],
            created_by_role=actor.role,
            lineas=[
                ledger.linea_debe(cuenta["slug"], monto),
                ledger.linea_haber(ledger.slug_caja(bolsa), monto),
            ],
        )
        return respuesta_gate(
            solicitud["request_id"],
            "ACCEPT",
            transaction_group_id=grupo,
            data={
                "payment_id": pago["id"],
                "account_slug": cuenta["slug"],
                "monto": monto,
                "bolsa": bolsa,
                "tipo_movimiento": tipo,
            },
        )

    # ------------------------------------------------------------------
    # 3. Compras y proveedores
    # ------------------------------------------------------------------
    async def _registrar_compra(
        self,
        conn: asyncpg.Connection,
        solicitud: Mapping[str, Any],
        actor: Actor,
    ) -> dict[str, Any]:
        payload = solicitud["payload"]
        proveedor = await conn.fetchrow(
            "SELECT id::text, nombre, activo FROM suppliers WHERE id = $1",
            payload["supplier_id"],
        )
        if proveedor is None or not proveedor["activo"]:
            raise RechazoGate(
                "MISSING_MASTER_DATA",
                {"errores": ["el proveedor no existe o esta inactivo"]},
            )

        items: list[dict[str, Any]] = []
        subtotal = Decimal("0")
        for indice, item in enumerate(payload["items"]):
            cuenta = await ledger.cuenta(
                conn, item["account_slug"], bloquear=True
            )
            if cuenta["requires_voucher"] and not str(
                payload.get("referencia_comprobante") or ""
            ).strip():
                raise RechazoGate(
                    "MISSING_VOUCHER_REFERENCE",
                    {
                        "cuenta": cuenta["slug"],
                        "errores": [
                            f"la cuenta {cuenta['slug']} exige referencia "
                            "de comprobante en la compra"
                        ],
                    },
                )
            material = None
            if item.get("material_id") is not None:
                material = await conn.fetchrow(
                    "SELECT id::text, codigo, nombre FROM materials WHERE id = $1",
                    item["material_id"],
                )
                if material is None:
                    raise RechazoGate(
                        "MISSING_INVENTORY_ITEM_DATA",
                        {"errores": [f"material inexistente en item {indice}"]},
                    )
                if item["account_slug"] != ledger.INVENTARIO:
                    raise RechazoGate(
                        "MISSING_INVENTORY_ITEM_DATA",
                        {
                            "errores": [
                                "un material inventariable debe debitar "
                                f"{ledger.INVENTARIO}, no {item['account_slug']}"
                            ]
                        },
                    )
            cantidad = _decimal(
                item["cantidad"], f"items[{indice}].cantidad", lugares=4
            )
            costo = _decimal(
                item["costo_unitario"],
                f"items[{indice}].costo_unitario",
                lugares=4,
            )
            subtotal_item = (cantidad * costo).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            subtotal += subtotal_item
            items.append(
                {
                    "material_id": item.get("material_id"),
                    "material_codigo": material["codigo"] if material else None,
                    "account_id": cuenta["id"],
                    "account_slug": cuenta["slug"],
                    "descripcion": item["descripcion"],
                    "cantidad": cantidad,
                    "costo_unitario": costo,
                    "subtotal_item": subtotal_item,
                }
            )

        iva = _decimal(payload.get("iva_monto", "0.00"), "iva_monto", lugares=2)
        monto_total = subtotal + iva
        if monto_total <= 0:
            raise RechazoGate(
                "INVALID_PURCHASE_TOTAL",
                {"subtotal": float(subtotal), "iva_monto": float(iva)},
            )

        modalidad = payload["modalidad_pago"]
        pagado_hoy = _decimal(
            payload.get("monto_pagado_hoy") or "0.00",
            "monto_pagado_hoy",
            lugares=2,
        )
        bolsa_pago = payload.get("bolsa_pago_hoy")
        metodo_pago: str | None = None
        if modalidad in ("CONTADO_EFECTIVO", "CONTADO_TRANSFERENCIA"):
            if pagado_hoy != monto_total:
                raise RechazoGate(
                    "INVALID_PURCHASE_TOTAL",
                    {
                        "errores": ["una compra de contado debe pagarse completa"],
                        "monto_total": float(monto_total),
                        "monto_pagado_hoy": float(pagado_hoy),
                    },
                )
        elif modalidad == "MIXTO_ABONO_CREDITO":
            if pagado_hoy <= 0 or pagado_hoy >= monto_total:
                raise RechazoGate(
                    "INVALID_PURCHASE_TOTAL",
                    {
                        "errores": [
                            "un abono mixto debe ser mayor que cero y menor "
                            "que el total"
                        ],
                        "monto_total": float(monto_total),
                        "monto_pagado_hoy": float(pagado_hoy),
                    },
                )
        elif modalidad == "CREDITO_PROVEEDOR":
            if pagado_hoy != 0:
                raise RechazoGate(
                    "INVALID_PURCHASE_TOTAL",
                    {"errores": ["una compra a credito no se paga hoy"]},
                )
        if pagado_hoy > 0 and bolsa_pago is None:
            raise RechazoGate(
                "SCHEMA_VALIDATION_FAILED",
                {"errores": ["bolsa_pago_hoy es obligatoria si hay pago hoy"]},
            )
        if pagado_hoy > monto_total:
            raise RechazoGate(
                "INVALID_PURCHASE_TOTAL",
                {"errores": ["el pago supera el total de la compra"]},
            )
        if pagado_hoy > 0:
            if modalidad == "CONTADO_EFECTIVO":
                bolsa_pago = _bolsa_coherente(
                    "EFECTIVO", bolsa_pago, "bolsa_pago_hoy"
                )
                metodo_pago = "EFECTIVO"
            elif modalidad == "CONTADO_TRANSFERENCIA":
                bolsa_pago = _bolsa_coherente(
                    "TRANSFERENCIA", bolsa_pago, "bolsa_pago_hoy"
                )
                metodo_pago = "TRANSFERENCIA"
            else:
                # En el abono mixto la bolsa decide como salio el dinero.
                metodo_pago = (
                    "EFECTIVO"
                    if bolsa_pago == "CAJA_DIARIA"
                    else "TRANSFERENCIA"
                )
            referencia = payload.get("referencia_comprobante")
            if not str(referencia or "").strip():
                if iva > 0 or metodo_pago == "TRANSFERENCIA":
                    raise RechazoGate(
                        "MISSING_VOUCHER_REFERENCE",
                        {
                            "errores": [
                                "una compra con IVA o pagada por banco exige "
                                "referencia_comprobante"
                            ]
                        },
                    )

        fecha_compra = _fecha(payload["fecha_compra"], "fecha_compra")
        compra = await conn.fetchrow(
            """
            INSERT INTO purchases
                (supplier_id, fecha_compra, modalidad_pago, subtotal, iva_monto,
                 monto_total, monto_pagado, fecha_vencimiento, estado_recepcion,
                 referencia_comprobante)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'PENDIENTE', $9)
            RETURNING id::text, estado_recepcion
            """,
            proveedor["id"],
            fecha_compra,
            modalidad,
            subtotal,
            iva,
            monto_total,
            pagado_hoy,
            _fecha(payload["fecha_vencimiento"], "fecha_vencimiento")
            if payload.get("fecha_vencimiento")
            else None,
            payload.get("referencia_comprobante"),
        )

        for item in items:
            fila = await conn.fetchrow(
                """
                INSERT INTO purchase_items
                    (purchase_id, material_id, account_id, descripcion,
                     cantidad_comprada, cantidad_recibida, costo_unitario,
                     subtotal_item)
                VALUES ($1, $2, $3, $4, $5, 0, $6, $7)
                RETURNING id::text
                """,
                compra["id"],
                item["material_id"],
                item["account_id"],
                item["descripcion"],
                item["cantidad"],
                item["costo_unitario"],
                item["subtotal_item"],
            )
            item["purchase_item_id"] = fila["id"]

        recibidos = 0
        if payload["modo_recepcion"] == "INMEDIATA":
            for item in items:
                if item["material_id"] is None:
                    continue
                movimiento = await registrar_movimiento_real(
                    conn,
                    codigo=item["material_codigo"],
                    cantidad=item["cantidad"],
                    referencia=f"COMPRA:{compra['id']}",
                    tipo="COMPRA",
                    costo_unitario=item["costo_unitario"],
                )
                await conn.execute(
                    """
                    INSERT INTO goods_receipts
                        (purchase_item_id, inventory_movement_id,
                         cantidad_recibida, recibido_por, guia_remision)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    item["purchase_item_id"],
                    movimiento["movimiento_id"],
                    item["cantidad"],
                    actor.id,
                    None,
                )
                await conn.execute(
                    """
                    UPDATE purchase_items
                       SET cantidad_recibida = cantidad_comprada
                     WHERE id = $1
                    """,
                    item["purchase_item_id"],
                )
                recibidos += 1
            estado = "COMPLETA" if recibidos > 0 else "NO_APLICA"
        elif payload["modo_recepcion"] == "EN_TRANSITO":
            estado = "PENDIENTE" if any(i["material_id"] for i in items) else "NO_APLICA"
        else:
            estado = "NO_APLICA"

        await conn.execute(
            "UPDATE purchases SET estado_recepcion = $2 WHERE id = $1",
            compra["id"],
            estado,
        )

        lineas = [
            ledger.linea_debe(item["account_slug"], item["subtotal_item"])
            for item in items
            if item["subtotal_item"] > 0
        ]
        if iva > 0:
            lineas.append(ledger.linea_debe(ledger.IVA_CREDITO, iva))
        lineas.append(ledger.linea_haber(ledger.CUENTAS_POR_PAGAR, monto_total))

        grupo = await ledger.registrar_asiento(
            conn,
            fecha=fecha_compra,
            source_type="PURCHASE",
            source_id=compra["id"],
            descripcion=f"Compra a {proveedor['nombre']}",
            created_by_role=actor.role,
            lineas=lineas,
        )

        # El pago va en su propio asiento, igual que PAY_SUPPLIER_DEBT. Asi la
        # correccion con testigo del pago revierte solo el pago y no la compra.
        pago_proveedor_id = None
        pago_grupo = None
        if pagado_hoy > 0:
            pago_proveedor = await conn.fetchrow(
                """
                INSERT INTO supplier_payments
                    (supplier_id, purchase_id, fecha, metodo, bolsa, monto,
                     referencia)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id::text
                """,
                proveedor["id"],
                compra["id"],
                fecha_compra,
                metodo_pago,
                bolsa_pago,
                pagado_hoy,
                payload.get("referencia_comprobante"),
            )
            pago_proveedor_id = pago_proveedor["id"]
            pago_grupo = await ledger.registrar_asiento(
                conn,
                fecha=fecha_compra,
                source_type="SUPPLIER_PAYMENT",
                source_id=pago_proveedor_id,
                descripcion=f"Pago inicial de la compra a {proveedor['nombre']}",
                created_by_role=actor.role,
                lineas=[
                    ledger.linea_debe(ledger.CUENTAS_POR_PAGAR, pagado_hoy),
                    ledger.linea_haber(
                        ledger.slug_caja(bolsa_pago), pagado_hoy
                    ),
                ],
            )

        return respuesta_gate(
            solicitud["request_id"],
            "ACCEPT",
            transaction_group_id=grupo,
            data={
                "purchase_id": compra["id"],
                "supplier_id": proveedor["id"],
                "subtotal": subtotal,
                "iva_monto": iva,
                "monto_total": monto_total,
                "monto_pagado": pagado_hoy,
                "saldo_pendiente": monto_total - pagado_hoy,
                "estado_recepcion": estado,
                "items": len(items),
                "recepciones_inmediatas": recibidos,
                "supplier_payment_id": pago_proveedor_id,
                "supplier_payment_group_id": pago_grupo,
            },
        )

    async def _recibir_material(
        self,
        conn: asyncpg.Connection,
        solicitud: Mapping[str, Any],
        actor: Actor,
    ) -> dict[str, Any]:
        payload = solicitud["payload"]
        item = await conn.fetchrow(
            """
            SELECT pi.id::text, pi.purchase_id::text, pi.material_id::text,
                   pi.cantidad_comprada, pi.cantidad_recibida, pi.costo_unitario,
                   pi.descripcion, p.deleted_at, m.codigo, m.nombre
              FROM purchase_items pi
              JOIN purchases p ON p.id = pi.purchase_id
              LEFT JOIN materials m ON m.id = pi.material_id
             WHERE pi.id = $1
             FOR UPDATE OF pi, p
            """,
            payload["purchase_item_id"],
        )
        if item is None or item["deleted_at"] is not None:
            raise RechazoGate(
                "MISSING_MASTER_DATA",
                {"errores": ["el item de compra no existe"]},
            )
        if item["material_id"] is None or item["codigo"] is None:
            raise RechazoGate(
                "MISSING_INVENTORY_ITEM_DATA",
                {"errores": ["el item no tiene material inventariable"]},
            )
        cantidad = _decimal(
            payload["cantidad_recibida"], "cantidad_recibida", lugares=4
        )
        comprada = _decimal(item["cantidad_comprada"], "cantidad_comprada", lugares=4)
        recibida = _decimal(
            item["cantidad_recibida"], "cantidad_recibida_actual", lugares=4
        )
        if recibida + cantidad > comprada:
            raise RechazoGate(
                "SCHEMA_VALIDATION_FAILED",
                {
                    "errores": ["la recepcion supera la cantidad comprada"],
                    "pendiente": float(comprada - recibida),
                },
            )
        movimiento = await registrar_movimiento_real(
            conn,
            codigo=item["codigo"],
            cantidad=cantidad,
            referencia=f"COMPRA:{item['purchase_id']}",
            tipo="COMPRA",
            costo_unitario=_decimal(
                item["costo_unitario"], "costo_unitario", lugares=4
            ),
        )
        recibo = await conn.fetchrow(
            """
            INSERT INTO goods_receipts
                (purchase_item_id, inventory_movement_id, cantidad_recibida,
                 recibido_por, guia_remision)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id::text
            """,
            item["id"],
            movimiento["movimiento_id"],
            cantidad,
            actor.id,
            payload.get("guia_remision"),
        )
        await conn.execute(
            """
            UPDATE purchase_items
               SET cantidad_recibida = cantidad_recibida + $2
             WHERE id = $1
            """,
            item["id"],
            cantidad,
        )
        pendientes = await conn.fetchval(
            """
            SELECT count(*)
              FROM purchase_items
             WHERE purchase_id = $1
               AND material_id IS NOT NULL
               AND cantidad_recibida < cantidad_comprada
            """,
            item["purchase_id"],
        )
        estado = "COMPLETA" if pendientes == 0 else "PARCIAL"
        await conn.execute(
            "UPDATE purchases SET estado_recepcion = $2 WHERE id = $1",
            item["purchase_id"],
            estado,
        )
        return respuesta_gate(
            solicitud["request_id"],
            "ACCEPT",
            data={
                "purchase_id": item["purchase_id"],
                "purchase_item_id": item["id"],
                "goods_receipt_id": recibo["id"],
                "inventory_movement_id": movimiento["movimiento_id"],
                "cantidad_recibida": cantidad,
                "estado_recepcion": estado,
                "material": item["codigo"],
            },
        )

    async def _pagar_proveedor(
        self,
        conn: asyncpg.Connection,
        solicitud: Mapping[str, Any],
        actor: Actor,
    ) -> dict[str, Any]:
        payload = solicitud["payload"]
        compra = await conn.fetchrow(
            """
            SELECT id::text, supplier_id::text, monto_total, monto_pagado,
                   (monto_total - monto_pagado) AS saldo_pendiente,
                   deleted_at
              FROM purchases
             WHERE id = $1
             FOR UPDATE
            """,
            payload["purchase_id"],
        )
        if (
            compra is None
            or compra["deleted_at"] is not None
            or compra["supplier_id"] != payload["supplier_id"]
        ):
            raise RechazoGate(
                "MISSING_MASTER_DATA",
                {"errores": ["la compra no existe o no pertenece al proveedor"]},
            )
        monto = _decimal(payload["monto"], "monto", lugares=2)
        saldo = _decimal(compra["saldo_pendiente"], "saldo_pendiente", lugares=2)
        if monto <= 0 or monto > saldo:
            raise RechazoGate(
                "SCHEMA_VALIDATION_FAILED",
                {
                    "errores": ["el pago debe ser mayor que cero y no superar el saldo"],
                    "saldo_pendiente": float(saldo),
                    "monto": float(monto),
                },
            )
        fecha = _fecha(payload["fecha"], "fecha")
        bolsa = _bolsa_coherente(payload["metodo"], payload["bolsa"], "bolsa")
        cuenta_caja = await ledger.cuenta(
            conn, ledger.slug_caja(bolsa), bloquear=True
        )
        _exigir_comprobante(
            cuenta_caja, payload.get("referencia"), "el pago a proveedor"
        )
        pago = await conn.fetchrow(
            """
            INSERT INTO supplier_payments
                (supplier_id, purchase_id, fecha, metodo, bolsa, monto,
                 referencia)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id::text
            """,
            payload["supplier_id"],
            payload["purchase_id"],
            fecha,
            payload["metodo"],
            bolsa,
            monto,
            payload.get("referencia"),
        )
        await conn.execute(
            "UPDATE purchases SET monto_pagado = monto_pagado + $2 WHERE id = $1",
            payload["purchase_id"],
            monto,
        )
        grupo = await ledger.registrar_asiento(
            conn,
            fecha=fecha,
            source_type="SUPPLIER_PAYMENT",
            source_id=pago["id"],
            descripcion=f"Pago a proveedor de compra {payload['purchase_id']}",
            created_by_role=actor.role,
            lineas=[
                ledger.linea_debe(ledger.CUENTAS_POR_PAGAR, monto),
                ledger.linea_haber(ledger.slug_caja(bolsa), monto),
            ],
        )
        return respuesta_gate(
            solicitud["request_id"],
            "ACCEPT",
            transaction_group_id=grupo,
            data={
                "supplier_payment_id": pago["id"],
                "purchase_id": payload["purchase_id"],
                "monto": monto,
                "saldo_pendiente": saldo - monto,
            },
        )

    # ------------------------------------------------------------------
    # 4. Activos fijos y prestamos
    # ------------------------------------------------------------------
    async def _pagar_prestamo(
        self,
        conn: asyncpg.Connection,
        solicitud: Mapping[str, Any],
        actor: Actor,
    ) -> dict[str, Any]:
        payload = solicitud["payload"]
        pasivo = await conn.fetchrow(
            """
            SELECT id::text, entidad_financiera, saldo_capital_actual,
                   deleted_at
              FROM financial_liabilities
             WHERE id = $1
             FOR UPDATE
            """,
            payload["liability_id"],
        )
        if pasivo is None or pasivo["deleted_at"] is not None:
            raise RechazoGate(
                "MISSING_MASTER_DATA",
                {"errores": ["el pasivo financiero no existe"]},
            )
        capital = _decimal(payload["monto_capital"], "monto_capital", lugares=2)
        interes = _decimal(payload["monto_interes"], "monto_interes", lugares=2)
        if capital < 0 or interes < 0 or capital + interes <= 0:
            raise RechazoGate(
                "SCHEMA_VALIDATION_FAILED",
                {"errores": ["la cuota debe tener un monto positivo"]},
            )
        saldo = _decimal(
            pasivo["saldo_capital_actual"], "saldo_capital_actual", lugares=2
        )
        if capital > saldo:
            raise RechazoGate(
                "SCHEMA_VALIDATION_FAILED",
                {
                    "errores": ["el capital pagado supera el saldo del prestamo"],
                    "saldo_capital_actual": float(saldo),
                },
            )
        nuevo_saldo = saldo - capital
        fecha = _fecha(payload["fecha"], "fecha")
        cuenta_caja = await ledger.cuenta(
            conn, ledger.slug_caja(payload["bolsa"]), bloquear=True
        )
        _exigir_comprobante(
            cuenta_caja, payload.get("referencia"), "la cuota del prestamo"
        )
        grupo = str(uuid4())
        pago = await conn.fetchrow(
            """
            INSERT INTO loan_payments
                (liability_id, fecha, bolsa, monto_capital, monto_interes,
                 saldo_restante_snapshot, referencia, transaction_group_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id::text
            """,
            pasivo["id"],
            fecha,
            payload["bolsa"],
            capital,
            interes,
            nuevo_saldo,
            payload.get("referencia"),
            grupo,
        )
        await conn.execute(
            """
            UPDATE financial_liabilities
               SET saldo_capital_actual = $2
             WHERE id = $1
            """,
            pasivo["id"],
            nuevo_saldo,
        )
        lineas = []
        if capital > 0:
            lineas.append(ledger.linea_debe(ledger.PRESTAMOS_BANCARIOS, capital))
        if interes > 0:
            lineas.append(ledger.linea_debe(ledger.GASTO_INTERESES, interes))
        lineas.append(
            ledger.linea_haber(
                ledger.slug_caja(payload["bolsa"]), capital + interes
            )
        )
        await ledger.registrar_asiento(
            conn,
            fecha=fecha,
            source_type="LOAN_PAYMENT",
            source_id=pago["id"],
            descripcion=f"Cuota prestamo {pasivo['entidad_financiera']}",
            created_by_role=actor.role,
            lineas=lineas,
            transaction_group_id=grupo,
        )
        return respuesta_gate(
            solicitud["request_id"],
            "ACCEPT",
            transaction_group_id=grupo,
            data={
                "loan_payment_id": pago["id"],
                "liability_id": pasivo["id"],
                "monto_capital": capital,
                "monto_interes": interes,
                "saldo_capital_actual": nuevo_saldo,
            },
        )

    async def _depreciacion_mensual(
        self,
        conn: asyncpg.Connection,
        solicitud: Mapping[str, Any],
        actor: Actor,
    ) -> dict[str, Any]:
        payload = solicitud["payload"]
        periodo = payload["periodo_ym"]
        anio, mes = (int(parte) for parte in periodo.split("-"))
        if not 1 <= mes <= 12:
            raise RechazoGate(
                "SCHEMA_VALIDATION_FAILED",
                {"errores": ["periodo_ym debe tener un mes valido"]},
            )
        fin_mes = date(anio, mes, calendar.monthrange(anio, mes)[1])

        filtro = "AND id = $1" if payload.get("asset_id") else ""
        parametros = [payload["asset_id"]] if payload.get("asset_id") else []
        activos = await conn.fetch(
            f"""
            SELECT id::text, codigo, nombre, costo_historico, valor_residual,
                   vida_util_meses, depreciacion_acumulada, estado,
                   fecha_inicio_depreciacion
              FROM fixed_assets
             WHERE deleted_at IS NULL
               AND estado <> 'DADO_DE_BAJA'
               {filtro}
             ORDER BY codigo
            """,
            *parametros,
        )
        if not activos:
            return respuesta_gate(
                solicitud["request_id"],
                "ACCEPT",
                data={"periodo_ym": periodo, "cuotas": [], "aviso": "sin activos"},
            )

        ya_corridos = await conn.fetch(
            """
            SELECT asset_id::text, periodo_ym
              FROM depreciation_runs
             WHERE periodo_ym = $1
               AND asset_id = ANY($2::uuid[])
            """,
            periodo,
            [a["id"] for a in activos],
        )
        if ya_corridos:
            raise RechazoGate(
                "DEPRECIATION_ALREADY_RUN_FOR_PERIOD",
                {
                    "periodo_ym": periodo,
                    "assets": [f["asset_id"] for f in ya_corridos],
                },
            )

        cuotas: list[dict[str, Any]] = []
        for activo in activos:
            inicio = activo["fecha_inicio_depreciacion"]
            if inicio > fin_mes:
                continue
            costo = _decimal(activo["costo_historico"], "costo_historico", lugares=2)
            residual = _decimal(
                activo["valor_residual"], "valor_residual", lugares=2
            )
            base = costo - residual
            acumulada = _decimal(
                activo["depreciacion_acumulada"], "depreciacion_acumulada", lugares=2
            )
            restante = base - acumulada
            if restante <= 0:
                await conn.execute(
                    "UPDATE fixed_assets SET estado = 'DEPRECIADO_TOTAL' WHERE id = $1",
                    activo["id"],
                )
                continue
            cuota = (base / Decimal(activo["vida_util_meses"])).quantize(
                Decimal("0.01")
            )
            if cuota > restante:
                cuota = restante
            if cuota <= 0:
                continue
            grupo = str(uuid4())
            corrida = await conn.fetchrow(
                """
                INSERT INTO depreciation_runs
                    (asset_id, periodo_ym, cuota_depreciada,
                     transaction_group_id, executed_by)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id::text
                """,
                activo["id"],
                periodo,
                cuota,
                grupo,
                actor.id,
            )
            nueva_acumulada = acumulada + cuota
            estado = (
                "DEPRECIADO_TOTAL"
                if nueva_acumulada >= base
                else "ACTIVO"
            )
            await conn.execute(
                """
                UPDATE fixed_assets
                   SET depreciacion_acumulada = $2, estado = $3
                 WHERE id = $1
                """,
                activo["id"],
                nueva_acumulada,
                estado,
            )
            await ledger.registrar_asiento(
                conn,
                fecha=fin_mes,
                source_type="DEPRECIATION",
                source_id=corrida["id"],
                descripcion=f"Depreciacion {periodo} activo {activo['codigo']}",
                created_by_role=actor.role,
                lineas=[
                    ledger.linea_debe(ledger.GASTO_DEPRECIACION, cuota),
                    ledger.linea_haber(ledger.DEPRECIACION_ACUMULADA, cuota),
                ],
                transaction_group_id=grupo,
            )
            cuotas.append(
                {
                    "asset_id": activo["id"],
                    "codigo": activo["codigo"],
                    "cuota": cuota,
                    "depreciacion_acumulada": nueva_acumulada,
                    "estado": estado,
                    "transaction_group_id": grupo,
                }
            )
        return respuesta_gate(
            solicitud["request_id"],
            "ACCEPT",
            data={"periodo_ym": periodo, "cuotas": cuotas},
        )

    async def _crear_activo(
        self,
        conn: asyncpg.Connection,
        solicitud: Mapping[str, Any],
        actor: Actor,
    ) -> dict[str, Any]:
        payload = solicitud["payload"]
        adquisicion = _fecha(payload["fecha_adquisicion"], "fecha_adquisicion")
        inicio = _fecha(
            payload["fecha_inicio_depreciacion"], "fecha_inicio_depreciacion"
        )
        if inicio < adquisicion:
            raise RechazoGate(
                "INVALID_ASSET_VALUES",
                {"errores": ["la depreciacion no puede iniciar antes de la compra"]},
            )
        costo = _decimal(payload["costo_historico"], "costo_historico", lugares=2)
        residual = _decimal(payload["valor_residual"], "valor_residual", lugares=2)
        if residual > costo:
            raise RechazoGate(
                "INVALID_ASSET_VALUES",
                {"errores": ["el valor residual supera el costo"]},
            )
        activo = await conn.fetchrow(
            """
            INSERT INTO fixed_assets
                (codigo, nombre, categoria, fecha_adquisicion,
                 fecha_inicio_depreciacion, costo_historico, valor_residual,
                 vida_util_meses)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id::text, codigo, nombre, categoria, costo_historico,
                      valor_residual, vida_util_meses, estado
            """,
            payload["codigo"],
            payload["nombre"],
            payload["categoria"],
            adquisicion,
            inicio,
            costo,
            residual,
            payload["vida_util_meses"],
        )
        return respuesta_gate(
            solicitud["request_id"],
            "ACCEPT",
            data={"fixed_asset": dict(activo)},
        )

    async def _crear_pasivo(
        self,
        conn: asyncpg.Connection,
        solicitud: Mapping[str, Any],
        actor: Actor,
    ) -> dict[str, Any]:
        payload = solicitud["payload"]
        monto = _decimal(payload["monto_original"], "monto_original", lugares=2)
        saldo = _decimal(
            payload["saldo_capital_actual"], "saldo_capital_actual", lugares=2
        )
        if saldo > monto:
            raise RechazoGate(
                "SCHEMA_VALIDATION_FAILED",
                {"errores": ["el saldo actual no puede superar el monto original"]},
            )
        pasivo = await conn.fetchrow(
            """
            INSERT INTO financial_liabilities
                (entidad_financiera, numero_operacion, fecha_desembolso,
                 monto_original, saldo_capital_actual,
                 tasa_interes_anual_pct, cuota_mensual_referencial,
                 plazo_restante_meses)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id::text, entidad_financiera, numero_operacion,
                      fecha_desembolso, monto_original, saldo_capital_actual,
                      tasa_interes_anual_pct, cuota_mensual_referencial,
                      plazo_restante_meses
            """,
            payload["entidad_financiera"],
            payload["numero_operacion"],
            _fecha(payload["fecha_desembolso"], "fecha_desembolso"),
            monto,
            saldo,
            _decimal(
                payload["tasa_interes_anual_pct"],
                "tasa_interes_anual_pct",
                lugares=2,
            ),
            _decimal(
                payload["cuota_mensual_referencial"],
                "cuota_mensual_referencial",
                lugares=2,
            ),
            payload["plazo_restante_meses"],
        )
        return respuesta_gate(
            solicitud["request_id"],
            "ACCEPT",
            data={"financial_liability": dict(pasivo)},
        )

    # ------------------------------------------------------------------
    # 5. Datos maestros y apertura
    # ------------------------------------------------------------------
    async def _crear_proveedor(
        self,
        conn: asyncpg.Connection,
        solicitud: Mapping[str, Any],
        actor: Actor,
    ) -> dict[str, Any]:
        payload = solicitud["payload"]
        proveedor = await conn.fetchrow(
            """
            INSERT INTO suppliers (nombre, identificacion, telefono)
            VALUES ($1, $2, $3)
            RETURNING id::text, nombre, identificacion, telefono, activo
            """,
            payload["nombre"],
            payload.get("identificacion"),
            payload.get("telefono"),
        )
        return respuesta_gate(
            solicitud["request_id"],
            "ACCEPT",
            data={"supplier": dict(proveedor)},
        )

    async def _saldos_apertura(
        self,
        conn: asyncpg.Connection,
        solicitud: Mapping[str, Any],
        actor: Actor,
    ) -> dict[str, Any]:
        payload = solicitud["payload"]
        existente = await conn.fetchval(
            "SELECT count(*) FROM ledger_entries WHERE source_type = 'OPENING_BALANCE'"
        )
        if existente:
            raise RechazoGate(
                "DUPLICATE_REQUEST",
                {"errores": ["los saldos de apertura ya fueron registrados"]},
            )

        lineas: list[ledger.Linea] = []
        total_debe = Decimal("0")
        total_haber = Decimal("0")
        for indice, saldo in enumerate(payload["saldos"]):
            if saldo["account_slug"] == ledger.CAPITAL_APERTURA:
                raise RechazoGate(
                    "SCHEMA_VALIDATION_FAILED",
                    {
                        "errores": [
                            "capital_social_y_apertura es la contrapartida "
                            "automatica; no se envia en saldos"
                        ]
                    },
                )
            cuenta = await ledger.cuenta(
                conn, saldo["account_slug"], bloquear=True
            )
            if cuenta["account_type"] not in ("ASSET", "LIABILITY", "EQUITY"):
                raise RechazoGate(
                    "SCHEMA_VALIDATION_FAILED",
                    {
                        "errores": [
                            "los saldos de apertura solo admiten cuentas de "
                            f"balance; {cuenta['slug']} es {cuenta['account_type']}"
                        ]
                    },
                )
            monto = _decimal(
                saldo["monto"], f"saldos[{indice}].monto", lugares=2
            )
            if cuenta["normal_balance"] == "DEBIT":
                lineas.append(ledger.linea_debe(cuenta["slug"], monto))
                total_debe += monto
            else:
                lineas.append(ledger.linea_haber(cuenta["slug"], monto))
                total_haber += monto

        diferencia = total_debe - total_haber
        if diferencia > 0:
            lineas.append(ledger.linea_haber(ledger.CAPITAL_APERTURA, diferencia))
        elif diferencia < 0:
            lineas.append(ledger.linea_debe(ledger.CAPITAL_APERTURA, -diferencia))

        grupo = await ledger.registrar_asiento(
            conn,
            fecha=_fecha(payload["fecha_corte"], "fecha_corte"),
            source_type="OPENING_BALANCE",
            source_id=solicitud["request_id"],
            descripcion="Saldos de apertura",
            created_by_role=actor.role,
            lineas=lineas,
        )
        return respuesta_gate(
            solicitud["request_id"],
            "ACCEPT",
            transaction_group_id=grupo,
            data={
                "fecha_corte": payload["fecha_corte"],
                "total_debe": total_debe,
                "total_haber": total_haber,
                "contrapartida_capital": abs(diferencia),
            },
        )

    # ------------------------------------------------------------------
    # 6. Aprobaciones
    # ------------------------------------------------------------------
    async def _resolver_aprobacion(
        self,
        conn: asyncpg.Connection,
        solicitud: Mapping[str, Any],
        actor: Actor,
    ) -> dict[str, Any]:
        payload = solicitud["payload"]
        aprobacion = await conn.fetchrow(
            """
            SELECT id::text, original_request_id::text, intent,
                   contract_payload, motivo, status
              FROM approval_requests
             WHERE id = $1
             FOR UPDATE
            """,
            payload["approval_request_id"],
        )
        if aprobacion is None:
            raise RechazoGate(
                "SCHEMA_VALIDATION_FAILED",
                {"errores": ["la solicitud de aprobacion no existe"]},
            )
        if aprobacion["status"] != "PENDING":
            raise RechazoGate(
                "DUPLICATE_REQUEST",
                {"estado": aprobacion["status"]},
            )
        decision = payload["decision"]
        modo = payload.get("modo_resolucion_cobro")
        contrato = _json_cargado(aprobacion["contract_payload"])
        order_id = None
        if isinstance(contrato, Mapping) and contrato.get("order_id") is not None:
            order_id = str(contrato["order_id"])

        # v4.4.0: si hay cobros activos, Julio debe indicar como resolverlos
        # antes de aprobar. Si falta, la solicitud sigue PENDING.
        if (
            decision == "APPROVED"
            and aprobacion["intent"] == "CANCEL_CONCRETE_ORDER"
            and order_id is not None
        ):
            cobros = await conn.fetchval(
                """
                SELECT COALESCE(sum(monto), 0)
                  FROM payments
                 WHERE order_id = $1
                   AND tipo_movimiento = 'COBRO'
                   AND deleted_at IS NULL
                """,
                order_id,
            )
            if Decimal(str(cobros)) > 0 and not modo:
                raise RechazoGate(
                    "SCHEMA_VALIDATION_FAILED",
                    {
                        "errores": [
                            "la orden tiene cobros activos; indique "
                            "modo_resolucion_cobro=CONVERTIR_A_ANTICIPO_CLIENTE "
                            "o DEVOLVER_DINERO_CAJA_O_BANCO"
                        ]
                    },
                )

        await conn.execute(
            """
            UPDATE approval_requests
               SET status = $2,
                   resolution_comment = $3,
                   resolved_by = $4,
                   resolved_at = now()
             WHERE id = $1
            """,
            aprobacion["id"],
            decision,
            payload["comentario"],
            actor.id,
        )
        if decision == "REJECTED":
            return respuesta_gate(
                solicitud["request_id"],
                "ACCEPT",
                data={
                    "approval_request_id": aprobacion["id"],
                    "decision": "REJECTED",
                    "ejecutada": False,
                },
            )

        if aprobacion["intent"] != "CANCEL_CONCRETE_ORDER":
            return respuesta_gate(
                solicitud["request_id"],
                "ACCEPT",
                data={
                    "approval_request_id": aprobacion["id"],
                    "decision": "APPROVED",
                    "ejecutada": False,
                    "motivo": "intent sin ejecucion automatica",
                },
            )

        if order_id is None:
            raise RechazoGate(
                "SCHEMA_VALIDATION_FAILED",
                {"errores": ["la aprobacion no tiene order_id"]},
            )
        resultado = await self._ejecutar_cancelacion(
            conn,
            order_id=order_id,
            motivo=aprobacion["motivo"],
            actor=actor,
            approval_request_id=aprobacion["id"],
            modo_resolucion_cobro=modo,
        )
        return respuesta_gate(
            solicitud["request_id"],
            "ACCEPT",
            witness_id=resultado.get("witness_id"),
            transaction_group_id=resultado.get("transaction_group_id"),
            data=resultado,
        )

    async def _ejecutar_cancelacion(
        self,
        conn: asyncpg.Connection,
        *,
        order_id: str,
        motivo: str,
        actor: Actor,
        approval_request_id: str,
        modo_resolucion_cobro: str | None = None,
    ) -> dict[str, Any]:
        orden = await conn.fetchrow(
            """
            SELECT id::text, numero, estado
              FROM orders
             WHERE id = $1
             FOR UPDATE
            """,
            order_id,
        )
        if orden is None:
            raise RechazoGate(
                "MISSING_MASTER_DATA",
                {"errores": ["la orden a anular no existe"]},
            )
        if orden["estado"] == "ANULADA":
            return {
                "approval_request_id": approval_request_id,
                "orden_id": order_id,
                "ejecutada": True,
                "motivo": "la orden ya estaba anulada",
            }

        pagos = await conn.fetch(
            """
            SELECT id::text, monto, metodo, bolsa, account_id::text, fecha
              FROM payments
             WHERE order_id = $1
               AND tipo_movimiento = 'COBRO'
               AND deleted_at IS NULL
             ORDER BY fecha, id
            """,
            order_id,
        )
        total_cobros = sum(
            (Decimal(str(p["monto"])) for p in pagos), Decimal("0")
        )
        reembolsos: list[str] = []
        if total_cobros > 0:
            if modo_resolucion_cobro == "CONVERTIR_A_ANTICIPO_CLIENTE":
                await ledger.registrar_asiento(
                    conn,
                    fecha=date.today(),
                    source_type="ORDER_CANCELLATION_RECLASSIFICATION",
                    source_id=order_id,
                    descripcion=(
                        "Reclasificacion de cobros de la orden anulada a "
                        "anticipo del cliente"
                    ),
                    created_by_role=actor.role,
                    lineas=[
                        ledger.linea_debe(
                            ledger.CUENTAS_POR_COBRAR, total_cobros
                        ),
                        ledger.linea_haber(
                            ledger.ANTICIPOS_CLIENTES, total_cobros
                        ),
                    ],
                )
            elif modo_resolucion_cobro == "DEVOLVER_DINERO_CAJA_O_BANCO":
                for pago in pagos:
                    monto_pago = Decimal(str(pago["monto"]))
                    cuenta_slug = ledger.slug_caja(pago["bolsa"])
                    reembolso = await conn.fetchrow(
                        """
                        INSERT INTO payments
                            (order_id, cliente_id, fecha, tipo_movimiento,
                             metodo, monto, referencia, account_id, bolsa,
                             es_anticipo)
                        SELECT order_id, cliente_id, $2, 'REEMBOLSO_CAJA',
                               metodo, monto, $3, account_id, bolsa, false
                          FROM payments
                         WHERE id = $1
                        RETURNING id::text
                        """,
                        pago["id"],
                        date.today(),
                        f"REEMBOLSO:{pago['id']}",
                    )
                    await ledger.registrar_asiento(
                        conn,
                        fecha=date.today(),
                        source_type="CLIENT_REFUND",
                        source_id=reembolso["id"],
                        descripcion=(
                            "Reembolso al cliente por anulacion de la orden"
                        ),
                        created_by_role=actor.role,
                        lineas=[
                            ledger.linea_debe(
                                ledger.CUENTAS_POR_COBRAR, monto_pago
                            ),
                            ledger.linea_haber(cuenta_slug, monto_pago),
                        ],
                    )
                    await conn.execute(
                        "UPDATE payments SET deleted_at = now() WHERE id = $1",
                        pago["id"],
                    )
                    reembolsos.append(reembolso["id"])
            else:
                return {
                    "approval_request_id": approval_request_id,
                    "orden_id": order_id,
                    "ejecutada": False,
                    "motivo": "REFUND_RULE_NOT_CONFIRMED",
                    "cobros_activos": float(total_cobros),
                    "aviso": (
                        "Julio aprobo la anulacion, pero no indico "
                        "modo_resolucion_cobro. La orden y sus cobros siguen "
                        "intactos."
                    ),
                }

        await conn.execute(
            "UPDATE orders SET estado = 'ANULADA' WHERE id = $1", order_id
        )
        movimientos = await conn.fetch(
            """
            SELECT id
              FROM inventory_movements
             WHERE order_id = $1 AND tipo = 'TEORICO'
             ORDER BY id
            """,
            order_id,
        )
        anulados = 0
        for movimiento in movimientos:
            await anular_consumo_teorico(conn, movimiento_id=movimiento["id"])
            anulados += 1

        grupos = await ledger.revertir_documento(
            conn,
            source_type="ORDER",
            source_id=order_id,
            descripcion=f"Reversa por anulacion de la orden #{orden['numero']}",
            created_by_role=actor.role,
            source_type_reversa="ORDER_CANCELLATION",
        )
        witness_id = await witness.registrar_testigo(
            conn,
            target_table="orders",
            target_record_id=order_id,
            action_type=witness.ACCION_ANULACION,
            valor_anterior={"estado": orden["estado"]},
            valor_nuevo={
                "estado": "ANULADA",
                "movimientos_anulados": anulados,
                "modo_resolucion_cobro": modo_resolucion_cobro,
                "reembolsos": reembolsos,
            },
            motivo=motivo,
            autor_role=actor.role,
            autor_id=str(actor.id),
            approved_by_superadmin=str(actor.id),
            reversal_transaction_group_id=grupos[-1] if grupos else None,
        )
        return {
            "approval_request_id": approval_request_id,
            "orden_id": order_id,
            "orden_numero": orden["numero"],
            "ejecutada": True,
            "movimientos_anulados": anulados,
            "modo_resolucion_cobro": modo_resolucion_cobro,
            "cobros_activos": float(total_cobros),
            "reembolsos": reembolsos,
            "grupos_revertidos": grupos,
            "witness_id": witness_id,
            "transaction_group_id": grupos[-1] if grupos else None,
        }

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    async def consultar(
        self, solicitud: Mapping[str, Any], actor: Actor
    ) -> dict[str, Any]:
        request_id = _request_id(solicitud)
        try:
            validar_consulta(solicitud)
        except ContratoInvalido as exc:
            return respuesta_gate(
                request_id,
                "REJECT",
                rejection_codes=["SCHEMA_VALIDATION_FAILED"],
                data={"errores": exc.errores},
            )
        codigo = autorizar(actor, solicitud["intent"], solicitud["channel"], "consulta")
        if codigo is not None:
            return respuesta_gate(
                request_id,
                "REJECT",
                rejection_codes=[codigo],
                data={"actor_role": actor.role if actor else None},
            )

        async with self.pool.acquire() as conn:
            riesgos = await self._riesgos_base(conn)
            manejadores = {
                "GET_CLIENT_BALANCE": self._q_cliente,
                "GET_DAILY_CASH_CLOSURE": self._q_cierre,
                "GET_ACCOUNTS_PAYABLE": self._q_por_pagar,
                "GET_INVENTORY_AND_ALERTS": self._q_inventario,
                "GET_DISPATCH_TIMELINE": self._q_despachos,
                "GET_INCOME_STATEMENT_PL": self._q_resultados,
                "GET_BALANCE_SHEET_REALTIME": self._q_balance,
                "GET_VALUATION_AND_10Y_PROJECTION": self._q_valoracion,
                "GET_DEBT_CAPACITY_DSCR": self._q_dscr,
            }
            manejador = manejadores.get(solicitud["intent"])
            if manejador is None:
                return respuesta_gate(
                    request_id,
                    "REJECT",
                    rejection_codes=["UNAUTHORIZED_DOMAIN_ACCESS"],
                    data={"intent": solicitud["intent"]},
                )
            try:
                datos, riesgos_extra = await manejador(conn, solicitud["filters"])
            except RechazoGate as exc:
                return respuesta_gate(
                    request_id,
                    "REJECT",
                    rejection_codes=[exc.codigo],
                    residual_risks=riesgos + exc.residual_risks,
                    data=exc.data,
                )
            return respuesta_gate(
                request_id,
                "ACCEPT",
                residual_risks=riesgos + riesgos_extra,
                data=datos,
            )

    async def _riesgos_base(self, conn: asyncpg.Connection) -> list[str]:
        riesgos: list[str] = []
        confirmado = await setting(
            self.pool, "finanzas.iva_historico_confirmado", False
        )
        if not confirmado:
            riesgos.append("HISTORICAL_IVA_NOT_CONFIRMED")
        sin_fecha = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM materials WHERE ultimo_levantamiento_at IS NULL)"
        )
        if sin_fecha:
            riesgos.append("COUNT_DATE_NOT_CONFIRMED")
        apertura = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM ledger_entries WHERE source_type = 'OPENING_BALANCE')"
        )
        if not apertura:
            riesgos.append("OPENING_BALANCES_NOT_SET")
        return riesgos

    async def _q_cliente(
        self, conn: asyncpg.Connection, filtros: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        fila = await conn.fetchrow(
            "SELECT * FROM v_cliente_saldo WHERE id = $1",
            filtros["cliente_id"],
        )
        if fila is None:
            raise RechazoGate(
                "MISSING_MASTER_DATA",
                {"errores": ["el cliente no existe"]},
            )
        ordenes = await conn.fetch(
            """
            SELECT id::text, numero, fecha::text, forma_pago, estado,
                   COALESCE(total_con_iva, total) AS total_bruto
              FROM (
                    SELECT id, numero, created_at::date AS fecha, forma_pago,
                           estado, total_con_iva, total
                      FROM orders
                     WHERE cliente_id = $1
                   ) o
             ORDER BY numero DESC
             LIMIT 50
            """,
            filtros["cliente_id"],
        )
        pagos = await conn.fetch(
            """
            SELECT id::text, fecha::text, tipo_movimiento, metodo, monto, bolsa,
                   es_anticipo
              FROM payments
             WHERE cliente_id = $1
               AND deleted_at IS NULL
             ORDER BY fecha DESC, created_at DESC
             LIMIT 50
            """,
            filtros["cliente_id"],
        )
        return {
            "cliente": dict(fila),
            "ordenes": [dict(o) for o in ordenes],
            "pagos": [dict(p) for p in pagos],
        }, []

    async def _q_cierre(
        self, conn: asyncpg.Connection, filtros: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        fecha = _fecha(filtros["fecha_desde"], "fecha_desde")
        ordenes = await conn.fetch(
            """
            SELECT id::text, numero, forma_pago, estado,
                   COALESCE(total_con_iva, total) AS total_con_iva,
                   total
              FROM orders
             WHERE created_at::date = $1
               AND estado <> 'ANULADA'
             ORDER BY numero
            """,
            fecha,
        )
        movimientos = await conn.fetch(
            """
            SELECT id::text, tipo_movimiento, metodo, monto, referencia,
                   created_at::text
              FROM payments
             WHERE fecha = $1
               AND deleted_at IS NULL
             ORDER BY created_at
            """,
            fecha,
        )
        resumen = calcular_resumen_caja(
            fecha=fecha,
            ordenes=[dict(o) for o in ordenes],
            movimientos=[dict(m) for m in movimientos],
        )
        return resumen, []

    async def _q_por_pagar(
        self, conn: asyncpg.Connection, filtros: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        filas = await conn.fetch(
            """
            SELECT p.id::text, s.nombre AS proveedor, p.fecha_compra::text,
                   p.monto_total, p.monto_pagado, p.saldo_pendiente,
                   p.fecha_vencimiento::text, p.estado_recepcion
              FROM purchases p
              JOIN suppliers s ON s.id = p.supplier_id
             WHERE p.deleted_at IS NULL
               AND p.saldo_pendiente > 0
               AND ($1::uuid IS NULL OR p.supplier_id = $1::uuid)
             ORDER BY p.fecha_vencimiento NULLS LAST, p.fecha_compra
            """,
            filtros.get("supplier_id"),
        )
        total = sum(
            Decimal(str(f["saldo_pendiente"] or "0")) for f in filas
        )
        return {
            "cuentas_por_pagar": [dict(f) for f in filas],
            "total": total,
            "cantidad": len(filas),
        }, []

    async def _q_inventario(
        self, conn: asyncpg.Connection, filtros: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        filas = await conn.fetch(
            "SELECT * FROM v_stock_proyectado ORDER BY codigo"
        )
        riesgos: list[str] = []
        if any(f["estado_alerta_proyectada"] == "CRITICO" for f in filas):
            riesgos.append("SILO_STOCK_CRITICAL_ALERT")
        if any(
            f["estado_alerta_proyectada"] in ("SIN_LEVANTAR", "SIN_FECHA_CONTEO")
            for f in filas
        ):
            riesgos.append("PENDING_PHYSICAL_INVENTORY_RECONCILIATION")
        return {"materiales": [dict(f) for f in filas]}, riesgos

    async def _q_despachos(
        self, conn: asyncpg.Connection, filtros: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        filas = await conn.fetch(
            """
            SELECT *
              FROM v_dispatch_timeline
             WHERE ($1::uuid IS NULL OR order_id = $1::uuid)
             ORDER BY orden_numero DESC, viaje_numero
             LIMIT 100
            """,
            filtros.get("order_id"),
        )
        return {"despachos": [dict(f) for f in filas]}, []

    async def _q_resultados(
        self, conn: asyncpg.Connection, filtros: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        desde = _fecha(filtros["fecha_desde"], "fecha_desde")
        hasta = _fecha(filtros["fecha_hasta"], "fecha_hasta")
        if hasta < desde:
            raise RechazoGate(
                "SCHEMA_VALIDATION_FAILED",
                {"errores": ["fecha_hasta no puede ser anterior a fecha_desde"]},
            )
        filas = await conn.fetch(
            """
            SELECT *
              FROM v_estado_resultados
             WHERE periodo >= date_trunc('month', $1::date)::date
               AND periodo <= date_trunc('month', $2::date)::date
             ORDER BY periodo, code
            """,
            desde,
            hasta,
        )
        ingresos = sum(
            Decimal(str(f["saldo"] or "0"))
            for f in filas
            if f["account_type"] == "REVENUE"
        )
        gastos = sum(
            Decimal(str(f["saldo"] or "0"))
            for f in filas
            if f["account_type"] == "EXPENSE"
        )
        return {
            "periodo_desde": desde,
            "periodo_hasta": hasta,
            "lineas": [dict(f) for f in filas],
            "ingresos": ingresos,
            "gastos": gastos,
            "resultado": ingresos - gastos,
        }, []

    async def _q_balance(
        self, conn: asyncpg.Connection, filtros: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        filas = await conn.fetch("SELECT * FROM v_balance_general ORDER BY code")
        totales = ledger.sumar_por_naturaleza(filas)
        activo = totales["ASSET"]
        pasivo = totales["LIABILITY"]
        patrimonio = totales["EQUITY"]
        resultado = totales["REVENUE"] - totales["EXPENSE"]
        return {
            "cuentas": [dict(f) for f in filas],
            "activo": activo,
            "pasivo": pasivo,
            "patrimonio": patrimonio,
            "resultado_ejercicio": resultado,
            "descuadre": activo - pasivo - patrimonio - resultado,
        }, []

    async def _foto_financiera(self, conn: asyncpg.Connection) -> dict[str, Any]:
        """Foto real actual. No proyecta: solo lee el libro mayor."""
        filas = await conn.fetch("SELECT * FROM v_balance_general ORDER BY code")
        totales = ledger.sumar_por_naturaleza(filas)
        resultado = totales["REVENUE"] - totales["EXPENSE"]
        caja = await conn.fetchval(
            """
            SELECT COALESCE(SUM(le.debe - le.haber), 0)
              FROM ledger_entries le
              JOIN accounting_accounts aa ON aa.id = le.account_id
             WHERE aa.slug IN ('caja_diaria_secretaria', 'bancos_gerencia')
            """
        )
        servicio = await conn.fetchval(
            """
            SELECT COALESCE(SUM(cuota_mensual_referencial * 12), 0)
              FROM financial_liabilities
             WHERE deleted_at IS NULL
               AND saldo_capital_actual > 0
            """
        )
        return {
            "activo": totales["ASSET"],
            "pasivo": totales["LIABILITY"],
            "patrimonio": totales["EQUITY"],
            "resultado_ejercicio": resultado,
            "patrimonio_neto_hoy": totales["EQUITY"] + resultado,
            "ebitda_acumulado_real": resultado,
            "deuda_total_actual": totales["LIABILITY"],
            "flujo_caja_operativo_real": resultado,
            "caja_y_bancos": Decimal(str(caja or "0")),
            "servicio_deuda_anual": Decimal(str(servicio or "0")),
            "definiciones": (
                "SALDO_REAL_ACTUAL: EBITDA=ingresos-gastos; "
                "flujo=resultado del ejercicio; deuda=pasivo total"
            ),
        }

    @staticmethod
    def _tasas(parametros: Mapping[str, Any]) -> dict[str, Decimal] | None:
        nombres = (
            "wacc_anual_pct",
            "crecimiento_anual_pct",
            "participacion_trabajadores_pct",
            "impuesto_renta_pct",
        )
        if any(parametros.get(n) is None for n in nombres):
            return None
        return {n: Decimal(str(parametros[n])) / Decimal("100") for n in nombres}

    @staticmethod
    def _dcf(
        tasas: Mapping[str, Decimal],
        foto: Mapping[str, Any],
        horizon: int,
    ) -> dict[str, Any]:
        wacc = tasas["wacc_anual_pct"]
        g = tasas["crecimiento_anual_pct"]
        trab = tasas["participacion_trabajadores_pct"]
        imp = tasas["impuesto_renta_pct"]
        ebitda0 = Decimal(str(foto["ebitda_acumulado_real"]))
        filas: list[dict[str, Any]] = []
        pv = Decimal("0")
        for anio in range(1, horizon + 1):
            ebitda = ebitda0 * (Decimal("1") + g) ** anio
            fcf = ebitda * (Decimal("1") - trab - imp)
            factor = (Decimal("1") + wacc) ** anio
            vp = fcf / factor if factor else Decimal("0")
            pv += vp
            filas.append(
                {
                    "anio": anio,
                    "ebitda": ebitda,
                    "fcf": fcf,
                    "vp": vp,
                }
            )
        terminal = Decimal("0")
        pv_terminal = Decimal("0")
        if wacc > g:
            terminal = filas[-1]["fcf"] * (Decimal("1") + g) / (wacc - g)
            pv_terminal = terminal / (Decimal("1") + wacc) ** horizon
        enterprise = pv + pv_terminal
        return {
            "filas": filas,
            "enterprise_value": enterprise,
            "equity_value": enterprise - Decimal(str(foto["deuda_total_actual"])),
            "terminal_value": terminal,
            "pv_terminal": pv_terminal,
            "wacc": wacc,
            "crecimiento": g,
        }

    async def _q_valoracion(
        self, conn: asyncpg.Connection, filtros: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        parametros = await setting(
            self.pool, "finanzas.parametros_contables", {}
        ) or {}
        if not isinstance(parametros, Mapping):
            parametros = {}
        foto = await self._foto_financiera(conn)
        horizon = int(filtros["horizon_years"])
        tasas = self._tasas(parametros)
        if tasas is None:
            return {
                **foto,
                "estado": "PENDIENTE",
                "horizon_years": horizon,
                "proyeccion_10y": None,
                "capacidad_endeudamiento_max": None,
                "motivo": (
                    "faltan tasas en finanzas.parametros_contables; se "
                    "devuelve la foto real y no se inventa la proyeccion"
                ),
            }, ["UNCONFIRMED_FINANCIAL_RATES"]
        dcf = self._dcf(tasas, foto, horizon)
        return {
            **foto,
            "estado": "CALCULADA",
            "horizon_years": horizon,
            "proyeccion_10y": dcf["filas"],
            "enterprise_value": dcf["enterprise_value"],
            "equity_value": dcf["equity_value"],
            "terminal_value": dcf["terminal_value"],
            "capacidad_endeudamiento_max": dcf["equity_value"],
        }, []

    async def _q_dscr(
        self, conn: asyncpg.Connection, filtros: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        parametros = await setting(
            self.pool, "finanzas.parametros_contables", {}
        ) or {}
        if not isinstance(parametros, Mapping):
            parametros = {}
        foto = await self._foto_financiera(conn)
        horizon = int(filtros["horizon_years"])
        requeridos = (
            "wacc_anual_pct",
            "crecimiento_anual_pct",
            "participacion_trabajadores_pct",
            "impuesto_renta_pct",
            "dscr_minimo_banco",
        )
        if any(parametros.get(n) is None for n in requeridos):
            return {
                **foto,
                "estado": "PENDIENTE",
                "horizon_years": horizon,
                "dscr_actual": None,
                "capacidad_endeudamiento_max": None,
                "motivo": (
                    "faltan tasas o dscr_minimo_banco en "
                    "finanzas.parametros_contables; no se inventa el ratio"
                ),
            }, ["UNCONFIRMED_FINANCIAL_RATES"]
        servicio = Decimal(str(foto["servicio_deuda_anual"]))
        flujo = Decimal(str(foto["flujo_caja_operativo_real"]))
        dscr = flujo / servicio if servicio > 0 else None
        minimo = Decimal(str(parametros["dscr_minimo_banco"]))
        capacidad = flujo / minimo if minimo > 0 else None
        return {
            **foto,
            "estado": "CALCULADA",
            "horizon_years": horizon,
            "dscr_actual": dscr,
            "dscr_minimo_banco": minimo,
            "capacidad_endeudamiento_max": capacidad,
        }, []

    # ------------------------------------------------------------------
    # Testigo: correcciones y categorias
    # ------------------------------------------------------------------
    async def testigo(
        self, solicitud: Mapping[str, Any], actor: Actor
    ) -> dict[str, Any]:
        request_id = _request_id(solicitud)
        try:
            validar_testigo(solicitud)
        except ContratoInvalido as exc:
            return respuesta_gate(
                request_id,
                "REJECT",
                rejection_codes=["SCHEMA_VALIDATION_FAILED"],
                data={"errores": exc.errores},
            )
        codigo = autorizar(actor, solicitud["intent"], solicitud["channel"], "testigo")
        if codigo is not None:
            return respuesta_gate(
                request_id,
                "REJECT",
                rejection_codes=[codigo],
                data={"actor_role": actor.role if actor else None},
            )

        sha = hash_solicitud(solicitud)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                previa = await conn.fetchrow(
                    "SELECT * FROM processed_requests WHERE request_id = $1 FOR UPDATE",
                    request_id,
                )
                if previa is not None:
                    return self._reintento(previa, sha, actor, request_id)

                await conn.execute(
                    """
                    INSERT INTO processed_requests
                        (request_id, payload_sha256, actor_role, actor_id,
                         channel, intent, response_status, response_payload)
                    VALUES ($1, $2, $3, $4, $5, $6, 'IN_PROGRESS', '{}'::jsonb)
                    """,
                    request_id,
                    sha,
                    actor.role,
                    str(actor.id),
                    solicitud["channel"],
                    solicitud["intent"],
                )
                try:
                    async with conn.transaction():
                        respuesta = await self._despachar_testigo(
                            conn, solicitud, actor
                        )
                except RechazoGate as exc:
                    respuesta = respuesta_gate(
                        request_id,
                        "REJECT",
                        rejection_codes=[exc.codigo],
                        data=exc.data,
                    )
                except (
                    catalog_hygiene.ErrorCatalogo,
                    witness.ErrorTestigo,
                    ledger.AsientoInvalido,
                    ledger.CuentaNoExiste,
                ) as exc:
                    respuesta = respuesta_gate(
                        request_id,
                        "REJECT",
                        rejection_codes=[
                            getattr(exc, "codigo", "SCHEMA_VALIDATION_FAILED")
                        ],
                        data={"errores": [str(exc)]},
                    )
                except asyncpg.UniqueViolationError as exc:
                    respuesta = respuesta_gate(
                        request_id,
                        "REJECT",
                        rejection_codes=["SCHEMA_VALIDATION_FAILED"],
                        data={"errores": [f"registro duplicado: {exc}"]},
                    )

                await conn.execute(
                    """
                    UPDATE processed_requests
                       SET response_status = $2,
                           response_payload = $3::jsonb,
                           updated_at = now()
                     WHERE request_id = $1
                    """,
                    request_id,
                    respuesta["status"],
                    json.dumps(respuesta, ensure_ascii=False),
                )
                return respuesta

    async def _despachar_testigo(
        self,
        conn: asyncpg.Connection,
        solicitud: Mapping[str, Any],
        actor: Actor,
    ) -> dict[str, Any]:
        intent = solicitud["intent"]
        changes = solicitud["changes"]
        if intent == "CORRECT_MOVEMENT_WITH_WITNESS":
            if solicitud["target_table"] == "payments":
                resultado = await witness.corregir_pago(
                    conn,
                    payment_id=solicitud["target_record_id"],
                    changes=changes,
                    motivo=solicitud["motivo"],
                    actor_role=actor.role,
                    actor_id=str(actor.id),
                )
            elif solicitud["target_table"] == "supplier_payments":
                resultado = await witness.corregir_pago_proveedor(
                    conn,
                    supplier_payment_id=solicitud["target_record_id"],
                    changes=changes,
                    motivo=solicitud["motivo"],
                    actor_role=actor.role,
                    actor_id=str(actor.id),
                )
            elif solicitud["target_table"] == "purchases":
                resultado = await witness.corregir_compra(
                    conn,
                    purchase_id=solicitud["target_record_id"],
                    changes=changes,
                    motivo=solicitud["motivo"],
                    actor_role=actor.role,
                    actor_id=str(actor.id),
                )
            else:
                raise RechazoGate(
                    "SCHEMA_VALIDATION_FAILED",
                    {"errores": ["target_table no corregible por esta via"]},
                )
            return respuesta_gate(
                solicitud["request_id"],
                "ACCEPT",
                witness_id=resultado["witness_id"],
                transaction_group_id=resultado.get("transaction_group_id"),
                data=resultado,
            )

        if intent == "CREATE_ACCOUNTING_CATEGORY":
            if actor.role == "SECRETARIA":
                parametros = await setting(
                    self.pool, "finanzas.parametros_contables", {}
                ) or {}
                if not (
                    isinstance(parametros, Mapping)
                    and parametros.get("secretaria_can_create_categories", False)
                ):
                    raise RechazoGate(
                        "UNAUTHORIZED_DOMAIN_ACCESS",
                        {
                            "errores": [
                                "SECRETARIA no puede crear rubros: "
                                "secretaria_can_create_categories=false"
                            ]
                        },
                    )
            cuenta = await catalog_hygiene.crear_categoria(
                conn,
                nombre=changes["nuevo_nombre_categoria"],
                account_type=changes["account_type"],
                normal_balance=changes["normal_balance"],
                parent_group=changes["parent_group"],
                default_bolsa=changes["default_bolsa"],
                requires_voucher=bool(changes["requires_voucher"]),
                created_by=str(actor.id),
            )
            witness_id = await witness.registrar_testigo(
                conn,
                target_table="accounting_accounts",
                target_record_id=cuenta["id"],
                action_type=witness.ACCION_CORRECCION,
                valor_anterior={},
                valor_nuevo=cuenta,
                motivo=solicitud["motivo"],
                autor_role=actor.role,
                autor_id=str(actor.id),
            )
            return respuesta_gate(
                solicitud["request_id"],
                "ACCEPT",
                witness_id=witness_id,
                data={"account": cuenta},
            )

        if intent == "RENAME_ACCOUNTING_CATEGORY":
            antes = await conn.fetchrow(
                "SELECT * FROM accounting_accounts WHERE id = $1",
                solicitud["target_record_id"],
            )
            if antes is None:
                raise RechazoGate(
                    "SCHEMA_VALIDATION_FAILED",
                    {"errores": ["la categoria no existe"]},
                )
            cuenta = await catalog_hygiene.renombrar_categoria(
                conn,
                account_id=solicitud["target_record_id"],
                nombre=changes["nuevo_nombre_categoria"],
            )
            witness_id = await witness.registrar_testigo(
                conn,
                target_table="accounting_accounts",
                target_record_id=cuenta["id"],
                action_type=witness.ACCION_CORRECCION,
                valor_anterior={"name": antes["name"]},
                valor_nuevo={"name": cuenta["name"]},
                motivo=solicitud["motivo"],
                autor_role=actor.role,
                autor_id=str(actor.id),
            )
            return respuesta_gate(
                solicitud["request_id"],
                "ACCEPT",
                witness_id=witness_id,
                data={"account": cuenta},
            )

        if intent == "MERGE_ACCOUNTING_CATEGORIES":
            resultado = await catalog_hygiene.fusionar_categorias(
                conn,
                source_account_id=changes["source_account_id"],
                target_account_id=changes["target_account_id"],
            )
            witness_id = await witness.registrar_testigo(
                conn,
                target_table="accounting_accounts",
                target_record_id=resultado["origen"]["id"],
                action_type=witness.ACCION_FUSION,
                valor_anterior=resultado["origen"],
                valor_nuevo={
                    "merged_into_id": changes["target_account_id"],
                    "destino": resultado["destino"]["slug"],
                },
                motivo=solicitud["motivo"],
                autor_role=actor.role,
                autor_id=str(actor.id),
            )
            return respuesta_gate(
                solicitud["request_id"],
                "ACCEPT",
                witness_id=witness_id,
                data=resultado,
            )

        raise RechazoGate(
            "UNAUTHORIZED_DOMAIN_ACCESS", {"intent": intent}
        )


async def ejecutar_mutacion(
    pool: asyncpg.Pool, solicitud: Mapping[str, Any], actor: Actor
) -> dict[str, Any]:
    return await Gate(pool).mutar(solicitud, actor)


async def ejecutar_consulta(
    pool: asyncpg.Pool, solicitud: Mapping[str, Any], actor: Actor
) -> dict[str, Any]:
    return await Gate(pool).consultar(solicitud, actor)


async def ejecutar_testigo(
    pool: asyncpg.Pool, solicitud: Mapping[str, Any], actor: Actor
) -> dict[str, Any]:
    return await Gate(pool).testigo(solicitud, actor)
