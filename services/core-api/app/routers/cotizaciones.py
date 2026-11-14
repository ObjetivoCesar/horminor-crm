"""Cotizaciones: documento comercial previo a la orden (v6.20).

Reglas duras:
- Toda venta pasa primero por cotizacion.
- No se inventan precios ni extras: salen de la receta o los dicta el usuario.
- Aceptar asigna la etiqueta VENTA, pero no crea la orden.
- Convertir es un paso explicito y usa ``crear_orden``.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg
from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..db import setting
from ..panel_acl import exigir_modulo
from ..services.ordenes import NuevaOrden, OrdenInvalidaError, crear_orden

router = APIRouter(prefix="/api/v1/cotizaciones", tags=["cotizaciones"])

_DOS_DECIMALES = Decimal("0.01")


def _pool(request: Request) -> asyncpg.Pool:
    pool = getattr(request.app.state, "pool", None)
    if not isinstance(pool, asyncpg.Pool):
        raise HTTPException(status_code=503, detail="base de datos no disponible")
    return pool


def _d(valor: Any, por_defecto: str = "0") -> Decimal:
    if valor is None or valor == "":
        return Decimal(por_defecto)
    return Decimal(str(valor))


def _money(valor: Any) -> str | None:
    if valor is None:
        return None
    return str(_d(valor).quantize(_DOS_DECIMALES, rounding=ROUND_HALF_UP))


def _normalizar_busqueda(texto: str) -> str:
    """Minusculas sin tildes, para buscar nombres y apellidos como el Sabueso."""
    normal = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in normal if not unicodedata.combining(c)).lower().strip()


def _fecha(valor: Any) -> str | None:
    if valor is None:
        return None
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return str(valor)


def _fecha_local(valor: Any) -> str | None:
    """Fecha operativa de El Coca, no la fecha UTC del servidor."""
    if isinstance(valor, datetime):
        return valor.astimezone(ZoneInfo("America/Guayaquil")).date().isoformat()
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return str(valor) if valor is not None else None


def _uuid(valor: str, campo: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(valor))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{campo} invalido") from exc


def _snapshot(cot: dict[str, Any], extras: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "numero": cot.get("numero"),
        "cliente_id": str(cot.get("cliente_id")),
        "obra_direccion": cot.get("obra_direccion"),
        "volumen_m3": _money(cot.get("volumen_m3")),
        "resistencia": cot.get("resistencia"),
        "precio_m3": _money(cot.get("precio_m3")),
        "precio_estado": cot.get("precio_estado"),
        "incluye_equipo": bool(cot.get("incluye_equipo", True)),
        "incluye_bombeo": bool(cot.get("incluye_bombeo", True)),
        "forma_pago": cot.get("forma_pago"),
        "valida_hasta": _fecha(cot.get("valida_hasta")),
        "subtotal": _money(cot.get("subtotal")),
        "iva_pct": _money(cot.get("iva_pct")),
        "iva_monto": _money(cot.get("iva_monto")),
        "total": _money(cot.get("total")),
        "extras": [
            {
                "descripcion": e.get("descripcion"),
                "monto": _money(e.get("monto")),
                "cobrable": bool(e.get("cobrable")),
                "nota": e.get("nota"),
            }
            for e in extras
        ],
    }


def _hash(snapshot: dict[str, Any]) -> str:
    crudo = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


class ExtraIn(BaseModel):
    descripcion: str = Field(min_length=1, max_length=300)
    monto: Decimal | None = Field(default=None, ge=0)
    cobrable: bool = False
    nota: str | None = Field(default=None, max_length=500)


class CotizacionIn(BaseModel):
    cliente_id: str
    obra_direccion: str = Field(min_length=1, max_length=300)
    volumen_m3: Decimal = Field(gt=0)
    resistencia: str = Field(min_length=1, max_length=20)
    precio_m3: Decimal | None = Field(default=None, ge=0)
    forma_pago: str = Field(default="FIADO", pattern="^(EFECTIVO|TRANSFERENCIA|ABONO|FIADO)$")
    incluye_equipo: bool = True
    incluye_bombeo: bool = True
    acceso_notas: str | None = Field(default=None, max_length=500)
    validez_dias: int | None = Field(default=None, ge=1, le=90)
    extras: list[ExtraIn] = Field(default_factory=list)
    notas: str | None = Field(default=None, max_length=1000)
    creado_por: str | None = Field(default=None, max_length=120)


class AceptarIn(BaseModel):
    aprobado_por: str | None = Field(default=None, max_length=120)


def _resumen(fila: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": str(fila["id"]),
        "numero": fila["numero"],
        "cliente_id": str(fila["cliente_id"]),
        "cliente_nombre": fila["cliente_nombre"],
        "obra_direccion": fila["obra_direccion"],
        "volumen_m3": _money(fila["volumen_m3"]),
        "resistencia": fila["resistencia"],
        "precio_m3": _money(fila["precio_m3"]),
        "precio_estado": fila["precio_estado"],
        "forma_pago": fila["forma_pago"],
        "valida_hasta": _fecha(fila["valida_hasta"]),
        "estado": fila["estado"],
        "version": fila["version"],
        "subtotal": _money(fila["subtotal"]),
        "iva_pct": _money(fila["iva_pct"]),
        "iva_monto": _money(fila["iva_monto"]),
        "total": _money(fila["total"]),
        "orden_id": str(fila["orden_id"]) if fila["orden_id"] else None,
        "created_at": _fecha_local(fila["created_at"]),
    }


async def _detalle(pool: asyncpg.Pool, cotizacion_id: str) -> dict[str, Any]:
    fila = await pool.fetchrow(
        """
        SELECT c.*, cl.nombre AS cliente_nombre
          FROM cotizaciones c
          JOIN clients cl ON cl.id = c.cliente_id
         WHERE c.id = $1
        """,
        _uuid(cotizacion_id, "cotizacion_id"),
    )
    if fila is None:
        raise HTTPException(status_code=404, detail="cotizacion no encontrada")
    extras = await pool.fetch(
        """
        SELECT id, descripcion, monto, cobrable, nota, orden
          FROM cotizacion_extras
         WHERE cotizacion_id = $1
         ORDER BY orden, created_at
        """,
        fila["id"],
    )
    data = _resumen(fila)
    data["extras"] = [
        {
            "id": str(e["id"]),
            "descripcion": e["descripcion"],
            "monto": _money(e["monto"]),
            "cobrable": bool(e["cobrable"]),
            "nota": e["nota"],
        }
        for e in extras
    ]
    data["valida_hasta"] = _fecha(fila["valida_hasta"])
    if fila["valida_hasta"] and fila["created_at"]:
        data["validez_dias"] = max(
            1, (fila["valida_hasta"] - fila["created_at"].date()).days
        )
    else:
        data["validez_dias"] = None
    data["notas"] = fila["notas"]
    data["acceso_notas"] = fila["acceso_notas"]
    data["incluye_equipo"] = bool(fila["incluye_equipo"])
    data["incluye_bombeo"] = bool(fila["incluye_bombeo"])
    return data


async def _calcular(
    pool: asyncpg.Pool,
    body: CotizacionIn,
) -> dict[str, Any]:
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
    precio = _d(precio)
    if precio < 0:
        raise HTTPException(status_code=422, detail="precio_m3 no puede ser negativo")

    extras = [e.model_dump() for e in body.extras]
    subtotal = _d(body.volumen_m3) * precio
    for extra in extras:
        if extra.get("cobrable") and extra.get("monto") is not None:
            subtotal += _d(extra["monto"])
    subtotal = subtotal.quantize(_DOS_DECIMALES, rounding=ROUND_HALF_UP)
    iva_pct = _d(receta["iva_pct"])
    iva_monto = (subtotal * iva_pct / Decimal("100")).quantize(
        _DOS_DECIMALES, rounding=ROUND_HALF_UP
    )
    total = (subtotal + iva_monto).quantize(_DOS_DECIMALES, rounding=ROUND_HALF_UP)

    validez = body.validez_dias
    if validez is None:
        validez = int(_d(await setting(pool, "cotizaciones.validez_dias", 15), "15"))
    valida_hasta = date.today() + timedelta(days=max(1, validez))

    return {
        "cliente_id": cliente["id"],
        "cliente_nombre": cliente["nombre"],
        "obra_direccion": body.obra_direccion.strip(),
        "volumen_m3": _d(body.volumen_m3),
        "resistencia": body.resistencia.strip().upper(),
        "precio_m3": precio,
        "precio_estado": receta["precio_estado"] or "PROVISIONAL",
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


async def _insertar_version(
    conn: asyncpg.Connection,
    cotizacion_id: uuid.UUID,
    numero: str,
    version: int,
    snapshot: dict[str, Any],
) -> None:
    await conn.execute(
        """
        INSERT INTO cotizacion_versiones (cotizacion_id, version, snapshot, hash)
        VALUES ($1, $2, $3::jsonb, $4)
        """,
        cotizacion_id,
        version,
        json.dumps(snapshot, ensure_ascii=False, default=str),
        _hash(snapshot),
    )


async def _siguiente_numero(conn: asyncpg.Connection) -> str:
    fila = await conn.fetchrow("SELECT nextval('cotizaciones_numero_seq') AS n")
    anio = datetime.now().year
    return f"HORM-COT-{anio}-{int(fila['n']):04d}"


@router.get("")
async def listar(
    request: Request,
    q: str | None = Query(default=None, max_length=100),
    estado: str | None = Query(default=None, max_length=20),
    cliente_id: str | None = Query(default=None),
    limite: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Bandeja de cotizaciones con buscador.

    ``q`` busca por nombre/apellido, razon social, cedula/RUC, numero de
    cotizacion, obra, telefono o fecha (YYYY-MM-DD, DD/MM/YYYY o YYYY-MM).
    """
    await exigir_modulo(request, "cotizaciones")
    pool = _pool(request)
    filtros = []
    args: list[Any] = []
    if estado:
        args.append(estado.upper())
        filtros.append(f"c.estado = ${len(args)}")
    if cliente_id:
        args.append(_uuid(cliente_id, "cliente_id"))
        filtros.append(f"c.cliente_id = ${len(args)}")
    if q and q.strip():
        texto = _normalizar_busqueda(q)
        args.append(f"%{texto}%")
        patron = len(args)
        digitos = re.sub(r"\D", "", q)
        telefono_sql = "FALSE"
        if digitos:
            args.append(f"%{digitos}%")
            telefono_sql = (
                "regexp_replace(COALESCE(cl.telefono_whatsapp, ''), '\\D', '', 'g') "
                f"LIKE ${len(args)}"
            )
        filtros.append(
            f"""(
                translate(lower(c.numero), 'áéíóúüñ', 'aeiouun') LIKE ${patron}
                OR translate(lower(cl.nombre), 'áéíóúüñ', 'aeiouun') LIKE ${patron}
                OR translate(lower(COALESCE(cl.constructora, '')), 'áéíóúüñ', 'aeiouun') LIKE ${patron}
                OR lower(COALESCE(cl.cedula, '')) LIKE ${patron}
                OR lower(COALESCE(cl.ruc, '')) LIKE ${patron}
                OR translate(lower(COALESCE(c.obra_direccion, '')), 'áéíóúüñ', 'aeiouun') LIKE ${patron}
                OR to_char(c.created_at AT TIME ZONE 'America/Guayaquil', 'YYYY-MM-DD') LIKE ${patron}
                OR to_char(c.created_at AT TIME ZONE 'America/Guayaquil', 'DD/MM/YYYY') LIKE ${patron}
                OR to_char(c.valida_hasta, 'YYYY-MM-DD') LIKE ${patron}
                OR to_char(c.valida_hasta, 'DD/MM/YYYY') LIKE ${patron}
                OR {telefono_sql}
            )"""
        )
    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
    filas = await pool.fetch(
        f"""
        SELECT c.*, cl.nombre AS cliente_nombre
          FROM cotizaciones c
          JOIN clients cl ON cl.id = c.cliente_id
          {where}
         ORDER BY c.created_at DESC
         LIMIT {limite}
        """,
        *args,
    )
    return {"cotizaciones": [_resumen(f) for f in filas], "total": len(filas)}


@router.get("/{cotizacion_id}")
async def obtener(request: Request, cotizacion_id: str) -> dict[str, Any]:
    await exigir_modulo(request, "cotizaciones")
    return await _detalle(_pool(request), cotizacion_id)


@router.post("", status_code=201)
async def crear(request: Request, body: CotizacionIn) -> dict[str, Any]:
    await exigir_modulo(request, "cotizaciones", mutacion=True)
    pool = _pool(request)
    datos = await _calcular(pool, body)
    async with pool.acquire() as conn:
        async with conn.transaction():
            numero = await _siguiente_numero(conn)
            cot = await conn.fetchrow(
                """
                INSERT INTO cotizaciones (
                    numero, cliente_id, obra_direccion, volumen_m3, resistencia,
                    precio_m3, precio_estado, incluye_equipo, incluye_bombeo,
                    acceso_notas, forma_pago, valida_hasta, subtotal, iva_pct,
                    iva_monto, total, creado_por, notas
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                    $13, $14, $15, $16, $17, $18
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
            snapshot = _snapshot(dict(cot), datos["extras"])
            await _insertar_version(conn, cot["id"], numero, 1, snapshot)
    return await _detalle(pool, str(cot["id"]))


@router.put("/{cotizacion_id}")
async def actualizar(
    request: Request, cotizacion_id: str, body: CotizacionIn
) -> dict[str, Any]:
    await exigir_modulo(request, "cotizaciones", mutacion=True)
    pool = _pool(request)
    actual = await pool.fetchrow(
        "SELECT id, estado, version FROM cotizaciones WHERE id = $1",
        _uuid(cotizacion_id, "cotizacion_id"),
    )
    if actual is None:
        raise HTTPException(status_code=404, detail="cotizacion no encontrada")
    if actual["estado"] != "BORRADOR":
        raise HTTPException(
            status_code=422,
            detail="solo una cotizacion BORRADOR se puede editar; use una version nueva",
        )
    datos = await _calcular(pool, body)
    version = int(actual["version"]) + 1
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE cotizaciones
                   SET cliente_id = $2, obra_direccion = $3, volumen_m3 = $4,
                       resistencia = $5, precio_m3 = $6, precio_estado = $7,
                       incluye_equipo = $8, incluye_bombeo = $9, acceso_notas = $10,
                       forma_pago = $11, valida_hasta = $12, subtotal = $13,
                       iva_pct = $14, iva_monto = $15, total = $16, notas = $17,
                       version = $18, updated_at = now()
                 WHERE id = $1
                """,
                actual["id"],
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
                datos["notas"],
                version,
            )
            await conn.execute(
                "DELETE FROM cotizacion_extras WHERE cotizacion_id = $1", actual["id"]
            )
            for indice, extra in enumerate(datos["extras"]):
                await conn.execute(
                    """
                    INSERT INTO cotizacion_extras
                        (cotizacion_id, descripcion, monto, cobrable, nota, orden)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    actual["id"],
                    extra["descripcion"],
                    extra.get("monto"),
                    bool(extra.get("cobrable")),
                    extra.get("nota"),
                    indice,
                )
            fila = await conn.fetchrow(
                "SELECT c.*, cl.nombre AS cliente_nombre FROM cotizaciones c "
                "JOIN clients cl ON cl.id = c.cliente_id WHERE c.id = $1",
                actual["id"],
            )
            snapshot = _snapshot(dict(fila), datos["extras"])
            await _insertar_version(conn, actual["id"], fila["numero"], version, snapshot)
    return await _detalle(pool, cotizacion_id)


@router.post("/{cotizacion_id}/marcar-enviada")
async def marcar_enviada(request: Request, cotizacion_id: str) -> dict[str, Any]:
    """Registra que la cotizacion salio (panel/impresa). El PDF/WhatsApp es Q4."""
    await exigir_modulo(request, "cotizaciones", mutacion=True)
    pool = _pool(request)
    fila = await pool.fetchrow(
        "SELECT id, numero, estado FROM cotizaciones WHERE id = $1",
        _uuid(cotizacion_id, "cotizacion_id"),
    )
    if fila is None:
        raise HTTPException(status_code=404, detail="cotizacion no encontrada")
    if fila["estado"] != "BORRADOR":
        raise HTTPException(
            status_code=422,
            detail="solo una cotizacion BORRADOR se marca como enviada",
        )
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE cotizaciones
                   SET estado = 'ENVIADA', enviada_at = now(),
                       enviada_por = COALESCE(enviada_por, 'panel'),
                       canal_envio = COALESCE(canal_envio, 'PANEL'),
                       updated_at = now()
                 WHERE id = $1
                """,
                fila["id"],
            )
            await conn.execute(
                """
                INSERT INTO cotizacion_eventos
                    (cotizacion_id, tipo, canal, mensaje, actor)
                VALUES ($1, 'ENVIO', 'PANEL', 'Cotizacion marcada como enviada desde el panel.', 'panel')
                """,
                fila["id"],
            )
    return await _detalle(pool, cotizacion_id)


@router.post("/{cotizacion_id}/aceptar")
async def aceptar(
    request: Request, cotizacion_id: str, body: AceptarIn = Body(default=AceptarIn())
) -> dict[str, Any]:
    await exigir_modulo(request, "cotizaciones", mutacion=True)
    pool = _pool(request)
    fila = await pool.fetchrow(
        "SELECT id, cliente_id, estado, valida_hasta FROM cotizaciones WHERE id = $1",
        _uuid(cotizacion_id, "cotizacion_id"),
    )
    if fila is None:
        raise HTTPException(status_code=404, detail="cotizacion no encontrada")
    if fila["estado"] not in ("BORRADOR", "ENVIADA"):
        raise HTTPException(
            status_code=422,
            detail=f"no se puede aceptar una cotizacion en estado {fila['estado']}",
        )
    if fila["valida_hasta"] is not None and fila["valida_hasta"] < date.today():
        raise HTTPException(status_code=422, detail="COTIZACION_VENCIDA")
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE cotizaciones
                   SET estado = 'ACEPTADA', aceptada_at = now(),
                       aprobado_por = COALESCE($2, aprobado_por), updated_at = now()
                 WHERE id = $1
                """,
                fila["id"],
                body.aprobado_por,
            )
            await conn.execute(
                """
                INSERT INTO cliente_etiquetas (cliente_id, etiqueta, origen, origen_id)
                VALUES ($1, 'VENTA', 'COTIZACION', $2)
                ON CONFLICT (cliente_id, etiqueta) DO NOTHING
                """,
                fila["cliente_id"],
                fila["id"],
            )
    return await _detalle(pool, cotizacion_id)


@router.post("/{cotizacion_id}/convertir", status_code=201)
async def convertir(request: Request, cotizacion_id: str) -> dict[str, Any]:
    await exigir_modulo(request, "cotizaciones", mutacion=True)
    pool = _pool(request)
    fila = await pool.fetchrow(
        """
        SELECT c.*, cl.nombre AS cliente_nombre
          FROM cotizaciones c
          JOIN clients cl ON cl.id = c.cliente_id
         WHERE c.id = $1
        """,
        _uuid(cotizacion_id, "cotizacion_id"),
    )
    if fila is None:
        raise HTTPException(status_code=404, detail="cotizacion no encontrada")
    if fila["estado"] == "CONVERTIDA" and fila["orden_id"]:
        return {
            "cotizacion": await _detalle(pool, cotizacion_id),
            "orden_id": str(fila["orden_id"]),
            "ya_convertida": True,
        }
    if fila["estado"] != "ACEPTADA":
        raise HTTPException(
            status_code=422,
            detail="solo una cotizacion ACEPTADA se convierte en orden",
        )
    if fila["precio_m3"] is None:
        raise HTTPException(status_code=422, detail="la cotizacion no tiene precio")
    try:
        resultado = await crear_orden(
            pool,
            NuevaOrden(
                cliente_id=str(fila["cliente_id"]),
                resistencia=fila["resistencia"],
                volumen_m3=_d(fila["volumen_m3"]),
                planta_codigo="PLANTA-COCA",
                forma_pago=fila["forma_pago"],
                precio_m3=_d(fila["precio_m3"]),
                creada_por=fila["creado_por"] or "cotizacion",
                notas=f"Desde cotizacion {fila['numero']}. {fila['notas'] or ''}".strip(),
                aplica_iva=True,
            ),
        )
    except OrdenInvalidaError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    extras = await pool.fetch(
        "SELECT descripcion, monto, cobrable FROM cotizacion_extras WHERE cotizacion_id = $1 AND cobrable AND monto IS NOT NULL",
        fila["id"],
    )
    async with pool.acquire() as conn:
        async with conn.transaction():
            for extra in extras:
                await conn.execute(
                    """
                    INSERT INTO orden_extras (orden_id, descripcion, monto, cobrable)
                    VALUES ($1, $2, $3, true)
                    """,
                    resultado.orden_id,
                    extra["descripcion"],
                    extra["monto"],
                )
            await conn.execute(
                """
                UPDATE cotizaciones
                   SET estado = 'CONVERTIDA', convertida_at = now(),
                       orden_id = $2, updated_at = now()
                 WHERE id = $1
                """,
                fila["id"],
                resultado.orden_id,
            )
    return {
        "cotizacion": await _detalle(pool, cotizacion_id),
        "orden": asdict(resultado),
        "ya_convertida": False,
    }
