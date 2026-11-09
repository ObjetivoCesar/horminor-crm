"""Higiene del catalogo contable del Custodio.

Reglas:

- No se crean dos categorias con nombres practicamente iguales.
- Las cuentas del plan base (``is_system_locked = true``) no se renombran ni
  se fusionan: son la raiz del plan y el ledger historico apunta a ellas.
- Fusionar una cuenta no reescribe el pasado: se marca ``merged_into_id`` y
  ``deleted_at``; ``v_balance_general`` suma el historico en la cuenta destino.
- El codigo de una cuenta nueva se deriva del prefijo de su grupo contable y
  del ultimo codigo usado. No se inventa un numero fuera del plan.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping

import asyncpg

# Prefijo de codigo por grupo contable. Sale del plan base de la migracion 063
# (11xx activo corriente, 12xx activo no corriente, 21xx/22xx pasivo, etc.).
PREFIJOS_GRUPO = {
    "ACTIVO_CORRIENTE": "11",
    "ACTIVO_NO_CORRIENTE": "12",
    "PASIVO_CORRIENTE": "21",
    "PASIVO_LARGO_PLAZO": "22",
    "PATRIMONIO_NETO": "31",
    "INGRESO_OPERATIVO": "41",
    "COSTO_DIRECTO": "51",
    "CIF_PLANTA": "52",
    "GASTO_ADMIN_FIJO": "53",
    "CAJA_CHICA": "54",
    "FISCAL_FINANCIERO": "55",
}

# Dos nombres con similitud >= 0.88 se consideran duplicados. El umbral es una
# regla tecnica del catalogo, no un dato de negocio.
UMBRAL_SIMILITUD = 0.88


class ErrorCatalogo(ValueError):
    """Error de negocio del catalogo, con codigo del contrato del Gate."""

    def __init__(self, codigo: str, mensaje: str) -> None:
        self.codigo = codigo
        self.mensaje = mensaje
        super().__init__(mensaje)


def normalizar_nombre(nombre: str) -> str:
    """Minusculas, sin acentos y con separadores colapsados."""
    texto = unicodedata.normalize("NFKD", str(nombre or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def similitud_nombres(a: str, b: str) -> float:
    """Similitud deterministica entre dos nombres normalizados."""
    return SequenceMatcher(None, normalizar_nombre(a), normalizar_nombre(b)).ratio()


def generar_slug(nombre: str) -> str:
    """Slug tecnico ``[a-z0-9_]`` a partir del nombre."""
    texto = unicodedata.normalize("NFKD", str(nombre or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", texto).strip("_")
    slug = re.sub(r"_+", "_", slug)
    if not slug:
        raise ErrorCatalogo(
            "SCHEMA_VALIDATION_FAILED",
            "el nombre de la categoria no produce un slug valido",
        )
    return slug[:60]


def prefijo_de_grupo(parent_group: str) -> str:
    try:
        return PREFIJOS_GRUPO[parent_group]
    except KeyError as exc:
        raise ErrorCatalogo(
            "SCHEMA_VALIDATION_FAILED",
            f"parent_group sin prefijo contable: {parent_group}",
        ) from exc


def siguiente_codigo(codigos: Iterable[str], prefijo: str) -> str:
    """Siguiente codigo de cuatro digitos dentro de un prefijo.

    Solo considera codigos de la forma ``PPNN``. Si no hay, empieza en ``PP01``.
    """
    maximo = 0
    for codigo in codigos:
        texto = str(codigo or "")
        if len(texto) != 4 or not texto.isdigit() or not texto.startswith(prefijo):
            continue
        maximo = max(maximo, int(texto[2:]))
    if maximo >= 99:
        raise ErrorCatalogo(
            "SCHEMA_VALIDATION_FAILED",
            f"el prefijo {prefijo} agoto sus codigos de dos digitos",
        )
    return f"{prefijo}{maximo + 1:02d}"


async def nombre_similar(
    conn: asyncpg.Connection,
    nombre: str,
    *,
    excluir_id: str | None = None,
) -> asyncpg.Record | None:
    """Primera cuenta activa con nombre practicamente igual, si existe."""
    filas = await conn.fetch(
        """
        SELECT id::text, code, slug, name
          FROM accounting_accounts
         WHERE deleted_at IS NULL
           AND ($1::uuid IS NULL OR id <> $1::uuid)
         ORDER BY code
        """,
        excluir_id,
    )
    for fila in filas:
        if similitud_nombres(nombre, fila["name"]) >= UMBRAL_SIMILITUD:
            return fila
    return None


async def _slug_unico(conn: asyncpg.Connection, base: str) -> str:
    candidato = base
    sufijo = 2
    while await conn.fetchval(
        "SELECT 1 FROM accounting_accounts WHERE slug = $1", candidato
    ):
        candidato = f"{base[:56]}_{sufijo}"
        sufijo += 1
    return candidato


async def crear_categoria(
    conn: asyncpg.Connection,
    *,
    nombre: str,
    account_type: str,
    normal_balance: str,
    parent_group: str,
    default_bolsa: str,
    requires_voucher: bool,
    created_by: str,
) -> dict[str, Any]:
    """Crea una cuenta nueva del plan. Devuelve la fila creada como dict."""
    similar = await nombre_similar(conn, nombre)
    if similar is not None:
        raise ErrorCatalogo(
            "DUPLICATE_CATEGORY_SIMILARITY",
            f"ya existe la cuenta {similar['code']} {similar['name']}"
            f" con similitud suficiente a '{nombre}'",
        )

    prefijo = prefijo_de_grupo(parent_group)
    codigos = await conn.fetch(
        "SELECT code FROM accounting_accounts WHERE code LIKE $1", f"{prefijo}%"
    )
    codigo = siguiente_codigo((f["code"] for f in codigos), prefijo)
    slug = await _slug_unico(conn, generar_slug(nombre))

    fila = await conn.fetchrow(
        """
        INSERT INTO accounting_accounts
            (code, slug, name, account_type, normal_balance, parent_group,
             default_bolsa, requires_voucher, created_by)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id::text, code, slug, name, account_type, normal_balance,
                  parent_group, default_bolsa, requires_voucher,
                  is_system_locked, created_by, created_at
        """,
        codigo,
        slug,
        nombre,
        account_type,
        normal_balance,
        parent_group,
        default_bolsa,
        requires_voucher,
        created_by,
    )
    return dict(fila)


async def renombrar_categoria(
    conn: asyncpg.Connection,
    *,
    account_id: str,
    nombre: str,
) -> dict[str, Any]:
    """Renombra una cuenta. No cambia el slug ni el codigo."""
    fila = await conn.fetchrow(
        """
        SELECT id::text, code, slug, name, is_system_locked, deleted_at
          FROM accounting_accounts
         WHERE id = $1
         FOR UPDATE
        """,
        account_id,
    )
    if fila is None or fila["deleted_at"] is not None:
        raise ErrorCatalogo(
            "SCHEMA_VALIDATION_FAILED", f"categoria inexistente: {account_id}"
        )
    if fila["is_system_locked"]:
        raise ErrorCatalogo(
            "IMMUTABLE_ROOT_ACCOUNT",
            f"la cuenta base {fila['code']} no se puede renombrar",
        )

    similar = await nombre_similar(conn, nombre, excluir_id=account_id)
    if similar is not None:
        raise ErrorCatalogo(
            "DUPLICATE_CATEGORY_SIMILARITY",
            f"ya existe la cuenta {similar['code']} {similar['name']}",
        )

    actualizada = await conn.fetchrow(
        """
        UPDATE accounting_accounts
           SET name = $2
         WHERE id = $1
        RETURNING id::text, code, slug, name, account_type, normal_balance,
                  parent_group, default_bolsa, requires_voucher,
                  is_system_locked, created_by, created_at
        """,
        account_id,
        nombre,
    )
    return dict(actualizada)


async def fusionar_categorias(
    conn: asyncpg.Connection,
    *,
    source_account_id: str,
    target_account_id: str,
) -> dict[str, Any]:
    """Fusiona la cuenta origen en la destino sin reescribir el ledger."""
    if source_account_id == target_account_id:
        raise ErrorCatalogo(
            "SCHEMA_VALIDATION_FAILED",
            "source_account_id y target_account_id no pueden ser iguales",
        )

    origen = await conn.fetchrow(
        """
        SELECT id::text, code, slug, name, is_system_locked, merged_into_id,
               deleted_at
          FROM accounting_accounts
         WHERE id = $1
         FOR UPDATE
        """,
        source_account_id,
    )
    destino = await conn.fetchrow(
        """
        SELECT id::text, code, slug, name, is_system_locked, merged_into_id,
               deleted_at
          FROM accounting_accounts
         WHERE id = $1
         FOR UPDATE
        """,
        target_account_id,
    )
    if origen is None or origen["deleted_at"] is not None:
        raise ErrorCatalogo(
            "SCHEMA_VALIDATION_FAILED", "la cuenta origen no existe o esta borrada"
        )
    if destino is None or destino["deleted_at"] is not None:
        raise ErrorCatalogo(
            "SCHEMA_VALIDATION_FAILED", "la cuenta destino no existe o esta borrada"
        )
    if origen["is_system_locked"]:
        raise ErrorCatalogo(
            "IMMUTABLE_ROOT_ACCOUNT",
            f"la cuenta base {origen['code']} no se puede fusionar",
        )
    if origen["merged_into_id"] is not None:
        raise ErrorCatalogo(
            "SCHEMA_VALIDATION_FAILED",
            "la cuenta origen ya fue fusionada",
        )
    if destino["merged_into_id"] is not None:
        raise ErrorCatalogo(
            "SCHEMA_VALIDATION_FAILED",
            "la cuenta destino ya fue fusionada; use la cuenta final",
        )

    # Evitar cadenas o ciclos: si el destino apunta al origen, se rechaza.
    if str(destino["merged_into_id"] or "") == origen["id"]:
        raise ErrorCatalogo(
            "SCHEMA_VALIDATION_FAILED", "la fusion crearia un ciclo"
        )

    actualizada = await conn.fetchrow(
        """
        UPDATE accounting_accounts
           SET merged_into_id = $2,
               deleted_at = now()
         WHERE id = $1
        RETURNING id::text, code, slug, name, merged_into_id::text,
                  deleted_at
        """,
        source_account_id,
        target_account_id,
    )
    return {
        "origen": dict(origen),
        "destino": dict(destino),
        "resultado": dict(actualizada),
    }
