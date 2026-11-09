"""Testigo forense del Custodio.

Toda correccion deja dos rastros en la misma transaccion:

1. ``audit_witness_log``: valor anterior, valor nuevo, motivo y autor.
2. ``ledger_entries``: si el documento tenia asiento, se revierte el grupo
   original y se registra el asiento corregido. El historico no se edita.

El testigo es inmutable por trigger: solo se inserta.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Mapping
from uuid import UUID

import asyncpg

from . import ledger

ACCION_CORRECCION = "CORRECTION_WITH_WITNESS"
ACCION_FUSION = "CATEGORY_MERGE"
ACCION_ANULACION = "ORDER_CANCELLATION"


class ErrorTestigo(ValueError):
    """Correccion rechazada, con codigo del contrato del Gate."""

    def __init__(self, codigo: str, mensaje: str) -> None:
        self.codigo = codigo
        self.mensaje = mensaje
        super().__init__(mensaje)


def _jsonable(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, UUID):
        return str(valor)
    if isinstance(valor, Mapping):
        return {str(k): _jsonable(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_jsonable(v) for v in valor]
    return valor


async def registrar_testigo(
    conn: asyncpg.Connection,
    *,
    target_table: str,
    target_record_id: str,
    action_type: str,
    valor_anterior: Mapping[str, Any],
    valor_nuevo: Mapping[str, Any],
    motivo: str,
    autor_role: str,
    autor_id: str,
    approved_by_superadmin: str | None = None,
    reversal_transaction_group_id: str | None = None,
) -> str:
    """Inserta un testigo y devuelve su id."""
    if action_type not in (
        ACCION_CORRECCION,
        ACCION_FUSION,
        ACCION_ANULACION,
    ):
        raise ErrorTestigo(
            "SCHEMA_VALIDATION_FAILED", f"action_type invalido: {action_type}"
        )
    if not motivo or len(motivo.strip()) < 10:
        raise ErrorTestigo(
            "WITNESS_REASON_TOO_SHORT",
            "el motivo debe tener al menos 10 caracteres",
        )
    fila = await conn.fetchrow(
        """
        INSERT INTO audit_witness_log
            (target_table, target_record_id, action_type, valor_anterior,
             valor_nuevo, motivo, autor_role, autor_id,
             approved_by_superadmin, reversal_transaction_group_id)
        VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8, $9, $10)
        RETURNING id::text
        """,
        target_table,
        str(target_record_id),
        action_type,
        json.dumps(_jsonable(dict(valor_anterior)), ensure_ascii=False),
        json.dumps(_jsonable(dict(valor_nuevo)), ensure_ascii=False),
        motivo.strip(),
        autor_role,
        autor_id,
        approved_by_superadmin,
        reversal_transaction_group_id,
    )
    return fila["id"]


def _decimal(valor: Any, campo: str) -> Decimal:
    try:
        numero = Decimal(str(valor))
    except Exception as exc:  # noqa: BLE001 - se convierte en error de negocio
        raise ErrorTestigo(
            "SCHEMA_VALIDATION_FAILED", f"{campo} no es un decimal valido"
        ) from exc
    if numero != numero.quantize(ledger.CENTAVO):
        raise ErrorTestigo(
            "SCHEMA_VALIDATION_FAILED", f"{campo} tiene mas de dos decimales"
        )
    return numero.quantize(ledger.CENTAVO)


async def _cuenta_por_slug(
    conn: asyncpg.Connection, slug: str
) -> asyncpg.Record:
    try:
        return await ledger.cuenta(conn, slug, bloquear=True)
    except ledger.CuentaNoExiste as exc:
        raise ErrorTestigo("SCHEMA_VALIDATION_FAILED", str(exc)) from exc


async def corregir_pago(
    conn: asyncpg.Connection,
    *,
    payment_id: str,
    changes: Mapping[str, Any],
    motivo: str,
    actor_role: str,
    actor_id: str,
) -> dict[str, Any]:
    """Corrige un pago/gasto y rehace su asiento si existia."""
    pago = await conn.fetchrow(
        """
        SELECT id::text, order_id::text, cliente_id::text, fecha,
               tipo_movimiento, metodo, monto, referencia, account_id::text,
               bolsa, es_anticipo, deleted_at
          FROM payments
         WHERE id = $1
         FOR UPDATE
        """,
        payment_id,
    )
    if pago is None or pago["deleted_at"] is not None:
        raise ErrorTestigo(
            "SCHEMA_VALIDATION_FAILED", f"pago inexistente: {payment_id}"
        )

    anterior = dict(pago)
    monto = (
        _decimal(changes["nuevo_monto"], "nuevo_monto")
        if changes.get("nuevo_monto") is not None
        else _decimal(pago["monto"], "monto actual")
    )
    metodo = changes.get("nuevo_metodo") or pago["metodo"]
    bolsa = changes.get("nueva_bolsa") or pago["bolsa"]

    if monto <= 0:
        raise ErrorTestigo(
            "SCHEMA_VALIDATION_FAILED", "el monto corregido debe ser mayor que cero"
        )
    if metodo not in ("EFECTIVO", "TRANSFERENCIA", "FIADO"):
        raise ErrorTestigo(
            "SCHEMA_VALIDATION_FAILED", f"metodo invalido: {metodo}"
        )
    if bolsa not in ("CAJA_DIARIA", "BANCO_GERENCIA"):
        raise ErrorTestigo(
            "SCHEMA_VALIDATION_FAILED", f"bolsa invalida: {bolsa}"
        )

    account_id = pago["account_id"]
    if changes.get("nuevo_account_slug") is not None:
        cuenta = await _cuenta_por_slug(conn, changes["nuevo_account_slug"])
        account_id = cuenta["id"]
    elif changes.get("nueva_bolsa") is not None:
        cuenta = await _cuenta_por_slug(conn, ledger.slug_caja(bolsa))
        account_id = cuenta["id"]

    await conn.execute(
        """
        UPDATE payments
           SET monto = $2, metodo = $3, bolsa = $4, account_id = $5
         WHERE id = $1
        """,
        payment_id,
        monto,
        metodo,
        bolsa,
        account_id,
    )

    tipo = pago["tipo_movimiento"]
    source_type = "CLIENT_PAYMENT" if tipo == "COBRO" else "EXPENSE"
    originales = await ledger.asientos_de(conn, source_type, str(payment_id))
    grupos = await ledger.revertir_documento(
        conn,
        source_type=source_type,
        source_id=str(payment_id),
        descripcion=f"Reversa por correccion del pago {payment_id}",
        created_by_role=actor_role,
    )

    nuevo_grupo = None
    if originales:
        if tipo == "COBRO":
            contrapartida = _cuenta_contrapartida(
                originales, lado="haber"
            ) or (
                ledger.ANTICIPOS_CLIENTES
                if pago["es_anticipo"]
                else ledger.CUENTAS_POR_COBRAR
            )
            lineas = [
                ledger.linea_debe(ledger.slug_caja(bolsa), monto),
                ledger.linea_haber(contrapartida, monto),
            ]
        else:
            gasto_slug = changes.get("nuevo_account_slug")
            if gasto_slug is None:
                gasto_slug = _cuenta_contrapartida(originales, lado="debe")
            if gasto_slug is None and pago["account_id"] is not None:
                fila_cuenta = await conn.fetchval(
                    "SELECT slug FROM accounting_accounts WHERE id = $1",
                    pago["account_id"],
                )
                gasto_slug = fila_cuenta
            if gasto_slug is None:
                raise ErrorTestigo(
                    "SCHEMA_VALIDATION_FAILED",
                    "no se puede reconstruir el asiento: falta la cuenta de gasto",
                )
            lineas = [
                ledger.linea_debe(gasto_slug, monto),
                ledger.linea_haber(ledger.slug_caja(bolsa), monto),
            ]
        nuevo_grupo = await ledger.registrar_asiento(
            conn,
            fecha=pago["fecha"],
            source_type=source_type,
            source_id=str(payment_id),
            descripcion=f"Correccion del pago {payment_id}",
            created_by_role=actor_role,
            lineas=lineas,
        )

    nuevo = dict(anterior)
    nuevo.update(
        {
            "monto": str(monto),
            "metodo": metodo,
            "bolsa": bolsa,
            "account_id": str(account_id) if account_id else None,
        }
    )
    witness_id = await registrar_testigo(
        conn,
        target_table="payments",
        target_record_id=str(payment_id),
        action_type=ACCION_CORRECCION,
        valor_anterior=anterior,
        valor_nuevo=nuevo,
        motivo=motivo,
        autor_role=actor_role,
        autor_id=actor_id,
        reversal_transaction_group_id=nuevo_grupo,
    )
    return {
        "witness_id": witness_id,
        "anterior": anterior,
        "nuevo": nuevo,
        "grupos_revertidos": grupos,
        "transaction_group_id": nuevo_grupo,
        "ledger_ajustado": bool(originales),
    }


def _cuenta_contrapartida(
    asientos: list[asyncpg.Record], *, lado: str
) -> str | None:
    """Cuenta con mayor monto en el lado indicado (haber o debe)."""
    candidatos = [
        fila
        for fila in asientos
        if Decimal(str(fila[lado])) > 0 and not fila["is_reversal"]
    ]
    if not candidatos:
        return None
    return max(
        candidatos, key=lambda fila: Decimal(str(fila[lado]))
    )["account_slug"]


async def corregir_pago_proveedor(
    conn: asyncpg.Connection,
    *,
    supplier_payment_id: str,
    changes: Mapping[str, Any],
    motivo: str,
    actor_role: str,
    actor_id: str,
) -> dict[str, Any]:
    """Corrige un pago a proveedor y el saldo de su compra."""
    pago = await conn.fetchrow(
        """
        SELECT id::text, supplier_id::text, purchase_id::text, fecha, metodo,
               bolsa, monto, referencia, deleted_at
          FROM supplier_payments
         WHERE id = $1
         FOR UPDATE
        """,
        supplier_payment_id,
    )
    if pago is None or pago["deleted_at"] is not None:
        raise ErrorTestigo(
            "SCHEMA_VALIDATION_FAILED",
            f"pago a proveedor inexistente: {supplier_payment_id}",
        )

    anterior = dict(pago)
    monto = (
        _decimal(changes["nuevo_monto"], "nuevo_monto")
        if changes.get("nuevo_monto") is not None
        else _decimal(pago["monto"], "monto actual")
    )
    metodo = changes.get("nuevo_metodo") or pago["metodo"]
    bolsa = changes.get("nueva_bolsa") or pago["bolsa"]
    if monto <= 0:
        raise ErrorTestigo(
            "SCHEMA_VALIDATION_FAILED", "el monto corregido debe ser mayor que cero"
        )
    if metodo not in ("EFECTIVO", "TRANSFERENCIA"):
        raise ErrorTestigo("SCHEMA_VALIDATION_FAILED", f"metodo invalido: {metodo}")
    if bolsa not in ("CAJA_DIARIA", "BANCO_GERENCIA"):
        raise ErrorTestigo("SCHEMA_VALIDATION_FAILED", f"bolsa invalida: {bolsa}")

    delta = monto - _decimal(pago["monto"], "monto actual")
    if pago["purchase_id"] is not None:
        compra = await conn.fetchrow(
            """
            SELECT id::text, monto_total, monto_pagado
              FROM purchases
             WHERE id = $1
             FOR UPDATE
            """,
            pago["purchase_id"],
        )
        if compra is None:
            raise ErrorTestigo(
                "SCHEMA_VALIDATION_FAILED", "la compra del pago no existe"
            )
        nuevo_pagado = _decimal(compra["monto_pagado"], "monto_pagado") + delta
        total = _decimal(compra["monto_total"], "monto_total")
        if nuevo_pagado < 0 or nuevo_pagado > total:
            raise ErrorTestigo(
                "SCHEMA_VALIDATION_FAILED",
                "la correccion deja el pago fuera del rango de la compra",
            )
        await conn.execute(
            "UPDATE purchases SET monto_pagado = $2 WHERE id = $1",
            compra["id"],
            nuevo_pagado,
        )

    await conn.execute(
        """
        UPDATE supplier_payments
           SET monto = $2, metodo = $3, bolsa = $4
         WHERE id = $1
        """,
        supplier_payment_id,
        monto,
        metodo,
        bolsa,
    )

    grupos = await ledger.revertir_documento(
        conn,
        source_type="SUPPLIER_PAYMENT",
        source_id=str(supplier_payment_id),
        descripcion=f"Reversa por correccion del pago a proveedor {supplier_payment_id}",
        created_by_role=actor_role,
    )
    nuevo_grupo = None
    if grupos:
        nuevo_grupo = await ledger.registrar_asiento(
            conn,
            fecha=pago["fecha"],
            source_type="SUPPLIER_PAYMENT",
            source_id=str(supplier_payment_id),
            descripcion=f"Correccion del pago a proveedor {supplier_payment_id}",
            created_by_role=actor_role,
            lineas=[
                ledger.linea_debe(ledger.CUENTAS_POR_PAGAR, monto),
                ledger.linea_haber(ledger.slug_caja(bolsa), monto),
            ],
        )

    nuevo = dict(anterior)
    nuevo.update({"monto": str(monto), "metodo": metodo, "bolsa": bolsa})
    witness_id = await registrar_testigo(
        conn,
        target_table="supplier_payments",
        target_record_id=str(supplier_payment_id),
        action_type=ACCION_CORRECCION,
        valor_anterior=anterior,
        valor_nuevo=nuevo,
        motivo=motivo,
        autor_role=actor_role,
        autor_id=actor_id,
        reversal_transaction_group_id=nuevo_grupo,
    )
    return {
        "witness_id": witness_id,
        "anterior": anterior,
        "nuevo": nuevo,
        "grupos_revertidos": grupos,
        "transaction_group_id": nuevo_grupo,
        "ledger_ajustado": bool(grupos),
    }


async def corregir_compra(
    conn: asyncpg.Connection,
    *,
    purchase_id: str,
    changes: Mapping[str, Any],
    motivo: str,
    actor_role: str,
    actor_id: str,
) -> dict[str, Any]:
    """Corrige el monto de una compra de un solo renglon contable.

    Una compra con varios renglones de debito no se corrige por esta via:
    requiere una nota de credito detallada. Se rechaza para no inventar la
    distribucion entre items.
    """
    compra = await conn.fetchrow(
        """
        SELECT id::text, supplier_id::text, fecha_compra, modalidad_pago,
               subtotal, iva_monto, monto_total, monto_pagado,
               estado_recepcion, referencia_comprobante, notas
          FROM purchases
         WHERE id = $1 AND deleted_at IS NULL
         FOR UPDATE
        """,
        purchase_id,
    )
    if compra is None:
        raise ErrorTestigo(
            "SCHEMA_VALIDATION_FAILED", f"compra inexistente: {purchase_id}"
        )

    anterior = dict(compra)
    if changes.get("nuevo_metodo") is not None or changes.get("nueva_bolsa") is not None:
        raise ErrorTestigo(
            "SCHEMA_VALIDATION_FAILED",
            "una compra no tiene metodo/bolsa; corrija el pago a proveedor",
        )

    monto_total = (
        _decimal(changes["nuevo_monto"], "nuevo_monto")
        if changes.get("nuevo_monto") is not None
        else _decimal(compra["monto_total"], "monto_total")
    )
    iva = _decimal(compra["iva_monto"], "iva_monto")
    subtotal = monto_total - iva
    if monto_total <= 0 or subtotal < 0:
        raise ErrorTestigo(
            "SCHEMA_VALIDATION_FAILED",
            "el monto corregido no cubre el IVA registrado",
        )
    if monto_total < _decimal(compra["monto_pagado"], "monto_pagado"):
        raise ErrorTestigo(
            "SCHEMA_VALIDATION_FAILED",
            "el monto corregido es menor que lo ya pagado al proveedor",
        )

    # La correccion de cabecera no redistribuye inventario. Si la compra ya
    # tiene material recibido, el kardex y el costo promedio quedarian
    # desalineados: eso exige una nota de credito detallada.
    items = await conn.fetch(
        """
        SELECT id::text, material_id::text, cantidad_comprada
          FROM purchase_items
         WHERE purchase_id = $1
         ORDER BY id
        """,
        purchase_id,
    )
    if len(items) > 1:
        raise ErrorTestigo(
            "PURCHASE_REQUIRES_CREDIT_NOTE",
            "la compra tiene varias lineas de detalle; registre una nota de credito",
        )
    item_unico = items[0] if items else None
    if item_unico is not None and item_unico["material_id"] is not None:
        raise ErrorTestigo(
            "PURCHASE_REQUIRES_CREDIT_NOTE",
            "la compra tiene material inventariable; registre una nota de credito",
        )

    item_costo = None
    item_subtotal = None
    if item_unico is not None:
        cantidad_item = _decimal(
            item_unico["cantidad_comprada"], "cantidad_comprada"
        )
        if cantidad_item <= 0:
            raise ErrorTestigo(
                "SCHEMA_VALIDATION_FAILED",
                "la linea de compra tiene cantidad cero",
            )
        item_costo = (subtotal / cantidad_item).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        item_subtotal = (cantidad_item * item_costo).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if item_subtotal != subtotal:
            raise ErrorTestigo(
                "SCHEMA_VALIDATION_FAILED",
                "el monto no es representable con la cantidad y el costo "
                "de cuatro decimales de la linea",
            )

    originales = await ledger.asientos_de(conn, "PURCHASE", str(purchase_id))
    debitos = [
        fila
        for fila in originales
        if Decimal(str(fila["debe"])) > 0 and fila["account_slug"] != ledger.IVA_CREDITO
    ]
    cuentas_debito = {fila["account_slug"] for fila in debitos}
    if len(cuentas_debito) > 1:
        raise ErrorTestigo(
            "PURCHASE_REQUIRES_CREDIT_NOTE",
            "la compra tiene varios renglones de debito; registre una nota de credito",
        )
    cuenta_debito = (
        changes.get("nuevo_account_slug")
        or (debitos[0]["account_slug"] if debitos else None)
    )

    await conn.execute(
        """
        UPDATE purchases
           SET subtotal = $2, monto_total = $3
         WHERE id = $1
        """,
        purchase_id,
        subtotal,
        monto_total,
    )
    if item_unico is not None:
        await conn.execute(
            """
            UPDATE purchase_items
               SET costo_unitario = $2, subtotal_item = $3
             WHERE id = $1
            """,
            item_unico["id"],
            item_costo,
            item_subtotal,
        )

    grupos = await ledger.revertir_documento(
        conn,
        source_type="PURCHASE",
        source_id=str(purchase_id),
        descripcion=f"Reversa por correccion de la compra {purchase_id}",
        created_by_role=actor_role,
        fecha=compra["fecha_compra"],
    )
    nuevo_grupo = None
    if grupos:
        if cuenta_debito is None:
            raise ErrorTestigo(
                "SCHEMA_VALIDATION_FAILED",
                "no se puede reconstruir el asiento: falta la cuenta de debito",
            )
        lineas = [ledger.linea_debe(cuenta_debito, subtotal)]
        if iva > 0:
            lineas.append(ledger.linea_debe(ledger.IVA_CREDITO, iva))
        lineas.append(ledger.linea_haber(ledger.CUENTAS_POR_PAGAR, monto_total))
        nuevo_grupo = await ledger.registrar_asiento(
            conn,
            fecha=compra["fecha_compra"],
            source_type="PURCHASE",
            source_id=str(purchase_id),
            descripcion=f"Correccion de la compra {purchase_id}",
            created_by_role=actor_role,
            lineas=lineas,
        )

    nuevo = dict(anterior)
    nuevo.update({"subtotal": str(subtotal), "monto_total": str(monto_total)})
    witness_id = await registrar_testigo(
        conn,
        target_table="purchases",
        target_record_id=str(purchase_id),
        action_type=ACCION_CORRECCION,
        valor_anterior=anterior,
        valor_nuevo=nuevo,
        motivo=motivo,
        autor_role=actor_role,
        autor_id=actor_id,
        reversal_transaction_group_id=nuevo_grupo,
    )
    return {
        "witness_id": witness_id,
        "anterior": anterior,
        "nuevo": nuevo,
        "grupos_revertidos": grupos,
        "transaction_group_id": nuevo_grupo,
        "ledger_ajustado": bool(grupos),
    }
