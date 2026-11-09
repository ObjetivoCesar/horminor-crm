"""Libro mayor de partida doble del Custodio.

Reglas duras:

- Solo INSERT. El trigger ``trg_ledger_entries_immutable`` bloquea UPDATE y
  DELETE; una correccion se hace con una reversa (``is_reversal = true``) y un
  asiento nuevo.
- Cada asiento debe cuadrar: suma de ``debe`` = suma de ``haber`` > 0.
- Cada linea lleva un solo lado: ``debe`` o ``haber``, nunca ambos.
- Las cuentas se identifican por ``slug``; el plan de cuentas vive en la base.
- Los montos se guardan a dos decimales. No se redondea en silencio: un monto
  con mas precision se rechaza.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping
from uuid import UUID, uuid4

import asyncpg

CENTAVO = Decimal("0.01")

# Slugs del plan de cuentas (migracion 063). No son datos de negocio: son
# identificadores tecnicos del catalogo contable.
CAJA_DIARIA = "caja_diaria_secretaria"
BANCO_GERENCIA = "bancos_gerencia"
CUENTAS_POR_COBRAR = "cuentas_por_cobrar_clientes"
INVENTARIO = "inventario_insumos_silos"
IVA_CREDITO = "iva_credito_tributario"
ACTIVO_FIJO = "propiedad_planta_equipo"
DEPRECIACION_ACUMULADA = "depreciacion_acumulada_activos"
CUENTAS_POR_PAGAR = "cuentas_por_pagar_proveedores"
ANTICIPOS_CLIENTES = "anticipos_de_clientes"
IVA_POR_LIQUIDAR = "iva_interno_por_liquidar"
PRESTAMOS_BANCARIOS = "prestamos_bancarios_lp"
CAPITAL_APERTURA = "capital_social_y_apertura"
VENTAS = "ventas_hormigon"
COSTO_DIRECTO = "costo_directo_produccion_cogs"
GASTO_DEPRECIACION = "gasto_depreciacion_planta_flota"
GASTO_INTERESES = "intereses_comisiones_bancarias"


class AsientoInvalido(ValueError):
    """El asiento no cumple partida doble o trae montos invalidos."""


class CuentaNoExiste(ValueError):
    """El slug no existe en ``accounting_accounts``."""


@dataclass(frozen=True)
class Linea:
    """Una linea del asiento. Exactamente un lado debe ser positivo."""

    account_slug: str
    debe: Decimal = Decimal("0")
    haber: Decimal = Decimal("0")


def _monto(valor: Any, campo: str) -> Decimal:
    if isinstance(valor, bool):
        raise AsientoInvalido(f"{campo} debe ser un monto, no booleano")
    try:
        numero = valor if isinstance(valor, Decimal) else Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AsientoInvalido(f"{campo} no es un decimal valido: {valor!r}") from exc
    if numero != numero.quantize(CENTAVO):
        raise AsientoInvalido(
            f"{campo} tiene mas de dos decimales ({numero}); el ledger guarda centavos"
        )
    return numero.quantize(CENTAVO)


def validar_lineas(lineas: Iterable[Linea]) -> Decimal:
    """Valida partida doble y devuelve el total del asiento.

    Se usa tanto en el Gate como en las pruebas puras. No toca la base.
    """
    lista = list(lineas)
    if not lista:
        raise AsientoInvalido("el asiento no puede estar vacio")

    total_debe = Decimal("0")
    total_haber = Decimal("0")
    for indice, linea in enumerate(lista):
        if not isinstance(linea, Linea):
            raise AsientoInvalido(f"linea {indice} no es una Linea")
        if not linea.account_slug or not str(linea.account_slug).strip():
            raise AsientoInvalido(f"linea {indice} no tiene account_slug")
        debe = _monto(linea.debe, f"linea {indice}.debe")
        haber = _monto(linea.haber, f"linea {indice}.haber")
        if debe < 0 or haber < 0:
            raise AsientoInvalido(f"linea {indice} tiene un monto negativo")
        if (debe > 0) == (haber > 0):
            raise AsientoInvalido(
                f"linea {indice} debe llevar exactamente un lado positivo "
                f"(debe={debe}, haber={haber})"
            )
        total_debe += debe
        total_haber += haber

    if total_debe != total_haber:
        raise AsientoInvalido(
            f"el asiento no cuadra: debe {total_debe} != haber {total_haber}"
        )
    if total_debe <= 0:
        raise AsientoInvalido("el asiento debe tener un total mayor que cero")
    return total_debe


async def cuenta(
    conn: asyncpg.Connection, slug: str, *, bloquear: bool = False
) -> asyncpg.Record:
    """Devuelve la cuenta activa por slug. Falla si no existe o esta borrada."""
    fila = await conn.fetchrow(
        """
        SELECT id, code, slug, name, account_type, normal_balance,
               parent_group, default_bolsa, requires_voucher, is_system_locked
          FROM accounting_accounts
         WHERE slug = $1 AND deleted_at IS NULL
        """ + (" FOR UPDATE" if bloquear else ""),
        slug,
    )
    if fila is None:
        raise CuentaNoExiste(f"cuenta contable inexistente o borrada: {slug}")
    return fila


async def registrar_asiento(
    conn: asyncpg.Connection,
    *,
    fecha: date,
    source_type: str,
    source_id: str | None,
    descripcion: str,
    created_by_role: str,
    lineas: Iterable[Linea],
    transaction_group_id: str | UUID | None = None,
    is_reversal: bool = False,
    reverses_group_id: str | UUID | None = None,
) -> str:
    """Inserta un asiento balanceado y devuelve su ``transaction_group_id``."""
    lista = list(lineas)
    validar_lineas(lista)
    if not source_type or not str(source_type).strip():
        raise AsientoInvalido("source_type es obligatorio")
    if not descripcion or not str(descripcion).strip():
        raise AsientoInvalido("descripcion es obligatoria")
    if not created_by_role or not str(created_by_role).strip():
        raise AsientoInvalido("created_by_role es obligatorio")
    if is_reversal and reverses_group_id is None:
        raise AsientoInvalido("una reversa requiere reverses_group_id")

    grupo = str(transaction_group_id or uuid4())
    for linea in lista:
        fila = await cuenta(conn, linea.account_slug, bloquear=True)
        debe = _monto(linea.debe, "debe")
        haber = _monto(linea.haber, "haber")
        await conn.execute(
            """
            INSERT INTO ledger_entries
                (transaction_group_id, fecha_asiento, account_id, debe, haber,
                 source_type, source_id, descripcion, is_reversal,
                 reverses_group_id, created_by_role)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            grupo,
            fecha,
            fila["id"],
            debe,
            haber,
            source_type,
            None if source_id is None else str(source_id),
            descripcion,
            is_reversal,
            None if reverses_group_id is None else str(reverses_group_id),
            created_by_role,
        )
    return grupo


async def asientos_de(
    conn: asyncpg.Connection, source_type: str, source_id: str
) -> list[asyncpg.Record]:
    """Asientos originales de un documento, ordenados para reversa estable."""
    return await conn.fetch(
        """
        SELECT le.id, le.transaction_group_id, le.fecha_asiento, le.debe,
               le.haber, le.descripcion, le.is_reversal,
               le.reverses_group_id, aa.slug AS account_slug
          FROM ledger_entries le
          JOIN accounting_accounts aa ON aa.id = le.account_id
         WHERE le.source_type = $1
           AND le.source_id = $2
           AND le.is_reversal = false
           AND NOT EXISTS (
                SELECT 1
                  FROM ledger_entries r
                 WHERE r.reverses_group_id = le.transaction_group_id
                   AND r.is_reversal = true
           )
         ORDER BY le.created_at, le.id
        """,
        source_type,
        str(source_id),
    )


async def revertir_grupo(
    conn: asyncpg.Connection,
    *,
    transaction_group_id: str,
    source_type: str,
    source_id: str,
    descripcion: str,
    created_by_role: str,
    fecha: date | None = None,
) -> str | None:
    """Crea la reversa de un grupo. Devuelve el grupo nuevo o None si no habia.

    La reversa intercambia debe y haber y conserva la referencia al grupo
    original. No modifica las filas originales.
    """
    filas = await conn.fetch(
        """
        SELECT le.debe, le.haber, le.fecha_asiento, aa.slug AS account_slug
          FROM ledger_entries le
          JOIN accounting_accounts aa ON aa.id = le.account_id
         WHERE le.transaction_group_id = $1
         ORDER BY le.created_at, le.id
        """,
        transaction_group_id,
    )
    if not filas:
        return None

    lineas = [
        Linea(
            account_slug=fila["account_slug"],
            debe=Decimal(fila["haber"]),
            haber=Decimal(fila["debe"]),
        )
        for fila in filas
    ]
    return await registrar_asiento(
        conn,
        fecha=fecha or filas[0]["fecha_asiento"],
        source_type=source_type,
        source_id=source_id,
        descripcion=descripcion,
        created_by_role=created_by_role,
        lineas=lineas,
        is_reversal=True,
        reverses_group_id=transaction_group_id,
    )


async def revertir_documento(
    conn: asyncpg.Connection,
    *,
    source_type: str,
    source_id: str,
    descripcion: str,
    created_by_role: str,
    fecha: date | None = None,
    source_type_reversa: str | None = None,
) -> list[str]:
    """Revierte todos los grupos originales de un documento.

    Devuelve los ``transaction_group_id`` de las reversas creadas.
    """
    filas = await conn.fetch(
        """
        SELECT DISTINCT le.transaction_group_id
          FROM ledger_entries le
         WHERE le.source_type = $1
           AND le.source_id = $2
           AND le.is_reversal = false
           AND NOT EXISTS (
                SELECT 1
                  FROM ledger_entries r
                 WHERE r.reverses_group_id = le.transaction_group_id
                   AND r.is_reversal = true
           )
        """,
        source_type,
        str(source_id),
    )
    grupos: list[str] = []
    for fila in filas:
        grupo = await revertir_grupo(
            conn,
            transaction_group_id=str(fila["transaction_group_id"]),
            source_type=source_type_reversa or f"{source_type}_REVERSAL",
            source_id=str(source_id),
            descripcion=descripcion,
            created_by_role=created_by_role,
            fecha=fecha,
        )
        if grupo is not None:
            grupos.append(grupo)
    return grupos


def slug_caja(bolsa: str) -> str:
    """Mapea la bolsa fisica a su cuenta contable."""
    if bolsa == "CAJA_DIARIA":
        return CAJA_DIARIA
    if bolsa == "BANCO_GERENCIA":
        return BANCO_GERENCIA
    raise AsientoInvalido(f"bolsa desconocida: {bolsa}")


def linea_debe(slug: str, monto: Any) -> Linea:
    return Linea(account_slug=slug, debe=_monto(monto, f"{slug}.debe"))


def linea_haber(slug: str, monto: Any) -> Linea:
    return Linea(account_slug=slug, haber=_monto(monto, f"{slug}.haber"))


def sumar_por_naturaleza(
    filas: Iterable[Mapping[str, Any]],
) -> dict[str, Decimal]:
    """Suma saldos de ``v_balance_general`` por tipo de cuenta.

    ``saldo_neto`` ya viene orientado a la naturaleza propia de cada cuenta:
    las cuentas DEBIT suman debe-haber y las CREDIT suman haber-debe. Para
    obtener el total del grupo hay que respetar las cuentas contra:
    depreciacion acumulada es un ASSET de naturaleza CREDIT y resta del activo.
    """
    totales = {
        "ASSET": Decimal("0"),
        "LIABILITY": Decimal("0"),
        "EQUITY": Decimal("0"),
        "REVENUE": Decimal("0"),
        "EXPENSE": Decimal("0"),
    }
    for fila in filas:
        tipo = str(fila.get("account_type") or "")
        if tipo not in totales:
            continue
        naturaleza = str(fila.get("normal_balance") or "")
        saldo = Decimal(str(fila.get("saldo_neto") or "0"))
        if (tipo in ("ASSET", "EXPENSE")) == (naturaleza == "DEBIT"):
            totales[tipo] += saldo
        else:
            totales[tipo] -= saldo
    return totales
