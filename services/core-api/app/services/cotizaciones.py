"""Servicio de cotizaciones: alta y cálculos compartidos.

El router y el Cerebro deben crear cotizaciones por el **mismo** camino:
numeración, IVA con ``Decimal``, versión 1 y evento inicial. Si el Cerebro
hiciera su propio ``INSERT`` duplicaría la cadena comercial.

Este módulo no conoce FastAPI más allá de ``HTTPException`` para conservar los
mismos códigos de error que ya devuelve el panel.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import asyncpg
from fastapi import HTTPException

from ..db import setting

DOS_DECIMALES = Decimal("0.01")


# ---------------------------------------------------------------------------
# Formato y conversión (mismos valores que el panel ya mostraba)
# ---------------------------------------------------------------------------
def d(valor: Any, por_defecto: str = "0") -> Decimal:
    if valor is None or valor == "":
        return Decimal(por_defecto)
    return Decimal(str(valor))


def money(valor: Any) -> str | None:
    if valor is None:
        return None
    return str(d(valor).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP))


def coordenada(valor: Any) -> float | None:
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def fecha(valor: Any) -> str | None:
    if valor is None:
        return None
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return str(valor)


def pin(valor: Any) -> Decimal | None:
    """Coordenada lista para ``numeric(10, 7)``. Sin dato sigue siendo NULL."""
    if valor is None or valor == "":
        return None
    try:
        return Decimal(str(valor)).quantize(Decimal("0.0000001"), rounding=ROUND_HALF_UP)
    except (ArithmeticError, TypeError, ValueError):
        return None


def _uuid(valor: str, campo: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(valor))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{campo} invalido") from exc


# ---------------------------------------------------------------------------
# Snapshot y versiones
# ---------------------------------------------------------------------------
def snapshot(cot: dict[str, Any], extras: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "numero": cot.get("numero"),
        "cliente_id": str(cot.get("cliente_id")),
        "obra_direccion": cot.get("obra_direccion"),
        "ubicacion": {
            "texto": cot.get("ubicacion_texto"),
            "lat": coordenada(cot.get("ubicacion_lat")),
            "lng": coordenada(cot.get("ubicacion_lng")),
            "origen": cot.get("ubicacion_origen"),
        },
        "volumen_m3": money(cot.get("volumen_m3")),
        "resistencia": cot.get("resistencia"),
        "precio_m3": money(cot.get("precio_m3")),
        "precio_estado": cot.get("precio_estado"),
        "incluye_equipo": bool(cot.get("incluye_equipo", True)),
        "incluye_bombeo": bool(cot.get("incluye_bombeo", True)),
        "forma_pago": cot.get("forma_pago"),
        "valida_hasta": fecha(cot.get("valida_hasta")),
        "subtotal": money(cot.get("subtotal")),
        "iva_pct": money(cot.get("iva_pct")),
        "iva_monto": money(cot.get("iva_monto")),
        "total": money(cot.get("total")),
        "extras": [
            {
                "descripcion": e.get("descripcion"),
                "monto": money(e.get("monto")),
                "cobrable": bool(e.get("cobrable")),
                "nota": e.get("nota"),
            }
            for e in extras
        ],
    }


def hash_snapshot(datos: dict[str, Any]) -> str:
    crudo = json.dumps(datos, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


async def insertar_version(
    conn: asyncpg.Connection,
    cotizacion_id: uuid.UUID,
    numero: str,
    version: int,
    datos: dict[str, Any],
) -> None:
    await conn.execute(
        """
        INSERT INTO cotizacion_versiones (cotizacion_id, version, snapshot, hash)
        VALUES ($1, $2, $3::jsonb, $4)
        """,
        cotizacion_id,
        version,
        json.dumps(datos, ensure_ascii=False, default=str),
        hash_snapshot(datos),
    )


async def siguiente_numero(conn: asyncpg.Connection) -> str:
    fila = await conn.fetchrow("SELECT nextval('cotizaciones_numero_seq') AS n")
    anio = datetime.now().year
    return f"HORM-COT-{anio}-{int(fila['n']):04d}"


# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------
async def calcular(pool: asyncpg.Pool, body: Any) -> dict[str, Any]:
    """Valida y calcula la cotización. No escribe nada."""
    cliente = await pool.fetchrow(
        "SELECT id, nombre FROM clients WHERE id = $1",
        _uuid(body.cliente_id, "cliente_id"),
    )
    if cliente is None:
        raise HTTPException(status_code=422, detail="cliente no encontrado")
    receta = await pool.fetchrow(
        "SELECT precio_m3, iva_pct, precio_estado FROM concrete_recipes WHERE resistencia = $1",
        body.resistencia.strip().upper(),
    )
    if receta is None:
        raise HTTPException(status_code=422, detail="resistencia no registrada")

    precio = body.precio_m3 if body.precio_m3 is not None else receta["precio_m3"]
    if precio is None:
        raise HTTPException(
            status_code=422,
            detail="PRECIO_REQUERIDO: la receta no tiene precio; Julio debe cargarlo en Superadmin.",
        )
    precio = d(precio)
    if precio < 0:
        raise HTTPException(status_code=422, detail="precio_m3 no puede ser negativo")

    extras = [e.model_dump() for e in body.extras]
    subtotal = d(body.volumen_m3) * precio
    for extra in extras:
        if extra.get("cobrable") and extra.get("monto") is not None:
            subtotal += d(extra["monto"])
    subtotal = subtotal.quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)
    iva_pct = d(receta["iva_pct"])
    iva_monto = (subtotal * iva_pct / Decimal("100")).quantize(
        DOS_DECIMALES, rounding=ROUND_HALF_UP
    )
    total = (subtotal + iva_monto).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)

    validez = body.validez_dias
    if validez is None:
        validez = int(d(await setting(pool, "cotizaciones.validez_dias", 15), "15"))
    valida_hasta = date.today() + timedelta(days=max(1, validez))

    texto_ubicacion = (body.ubicacion_texto or "").strip() or None
    lat = pin(body.ubicacion_lat)
    lng = pin(body.ubicacion_lng)
    if (lat is None) != (lng is None):
        raise HTTPException(
            status_code=422,
            detail="UBICACION_INCOMPLETA: el pin necesita latitud y longitud juntas",
        )
    origen = (body.ubicacion_origen or "").upper() or None
    if lat is not None and origen is None:
        raise HTTPException(
            status_code=422,
            detail="UBICACION_ORIGEN_REQUERIDO: indica si el pin vino por GPS, WhatsApp o mapa",
        )
    if lat is None and origen == "WHATSAPP":
        raise HTTPException(
            status_code=422,
            detail="UBICACION_SIN_PIN: el origen WhatsApp exige coordenadas",
        )

    precio_estado_body = getattr(body, "precio_estado", None)
    precio_estado = (
        precio_estado_body
        if precio_estado_body in ("PROVISIONAL", "OFICIAL")
        else (receta["precio_estado"] or "PROVISIONAL")
    )

    return {
        "cliente_id": cliente["id"],
        "cliente_nombre": cliente["nombre"],
        "obra_direccion": body.obra_direccion.strip(),
        "ubicacion_texto": texto_ubicacion,
        "ubicacion_lat": lat,
        "ubicacion_lng": lng,
        "ubicacion_origen": origen,
        "volumen_m3": d(body.volumen_m3),
        "resistencia": body.resistencia.strip().upper(),
        "precio_m3": precio,
        "precio_estado": precio_estado,
        "incluye_equipo": body.incluye_equipo,
        "incluye_bombeo": body.incluye_bombeo,
        "acceso_notas": body.acceso_notas,
        "forma_pago": body.forma_pago.upper(),
        "valida_hasta": valida_hasta,
        "subtotal": subtotal,
        "iva_pct": iva_pct,
        "iva_monto": iva_monto,
        "total": total,
        "extras": extras,
        "notas": body.notas,
        "creado_por": body.creado_por,
    }


# ---------------------------------------------------------------------------
# Alta
# ---------------------------------------------------------------------------
async def crear_cotizacion_borrador(pool: asyncpg.Pool, body: Any) -> str:
    """Crea la cotización en ``BORRADOR`` y devuelve su id.

    Es el único camino de alta: el panel y el Cerebro llaman aquí.
    """
    datos = await calcular(pool, body)
    async with pool.acquire() as conn:
        async with conn.transaction():
            numero = await siguiente_numero(conn)
            cot = await conn.fetchrow(
                """
                INSERT INTO cotizaciones (
                    numero, cliente_id, obra_direccion, volumen_m3, resistencia,
                    precio_m3, precio_estado, incluye_equipo, incluye_bombeo,
                    acceso_notas, forma_pago, valida_hasta, subtotal, iva_pct,
                    iva_monto, total, creado_por, notas,
                    ubicacion_texto, ubicacion_lat, ubicacion_lng, ubicacion_origen
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                    $13, $14, $15, $16, $17, $18, $19, $20, $21, $22
                ) RETURNING *
                """,
                numero,
                datos["cliente_id"],
                datos["obra_direccion"],
                datos["volumen_m3"],
                datos["resistencia"],
                datos["precio_m3"],
                datos["precio_estado"],
                datos["incluye_equipo"],
                datos["incluye_bombeo"],
                datos["acceso_notas"],
                datos["forma_pago"],
                datos["valida_hasta"],
                datos["subtotal"],
                datos["iva_pct"],
                datos["iva_monto"],
                datos["total"],
                datos["creado_por"],
                datos["notas"],
                datos["ubicacion_texto"],
                datos["ubicacion_lat"],
                datos["ubicacion_lng"],
                datos["ubicacion_origen"],
            )
            for indice, extra in enumerate(datos["extras"]):
                await conn.execute(
                    """
                    INSERT INTO cotizacion_extras
                        (cotizacion_id, descripcion, monto, cobrable, nota, orden)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    cot["id"],
                    extra["descripcion"],
                    extra.get("monto"),
                    bool(extra.get("cobrable")),
                    extra.get("nota"),
                    indice,
                )
            await insertar_version(
                conn, cot["id"], numero, 1, snapshot(dict(cot), datos["extras"])
            )
    return str(cot["id"])
