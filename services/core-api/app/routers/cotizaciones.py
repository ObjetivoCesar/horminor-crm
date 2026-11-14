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
from collections.abc import Mapping
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg
from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..db import setting
from ..m1_whatsapp.bunny import BunnyError, BunnyHttpStorageClient
from ..m1_whatsapp.notifications import EvolutionNotifier
from ..m1_whatsapp.repositorio import PostgresRepositorio
from ..panel_acl import exigir_modulo
from ..sandbox import SandboxNotifier
from ..services import media as media_svc
from ..services.factura_pdf import generar_pdf
from ..services.ordenes import NuevaOrden, OrdenInvalidaError, crear_orden
from .chat_clientes import _cliente, _config_bunny, _settings

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
    forma_pago: str = Field(
        default="POR_DEFINIR",
        pattern="^(POR_DEFINIR|EFECTIVO|TRANSFERENCIA|ABONO|FIADO)$",
    )
    incluye_equipo: bool = True
    incluye_bombeo: bool = True
    acceso_notas: str | None = Field(default=None, max_length=500)
    validez_dias: int | None = Field(default=None, ge=1, le=90)
    extras: list[ExtraIn] = Field(default_factory=list)
    notas: str | None = Field(default=None, max_length=1000)
    creado_por: str | None = Field(default=None, max_length=120)


class AceptarIn(BaseModel):
    aprobado_por: str | None = Field(default=None, max_length=120)


class FacturaIn(BaseModel):
    razon_social: str | None = Field(default=None, max_length=200)
    ruc: str | None = Field(default=None, max_length=30)
    direccion: str | None = Field(default=None, max_length=300)
    email: str | None = Field(default=None, max_length=120)
    fecha_emision: date | None = None
    fecha_vencimiento: date | None = None


class ConvertirIn(BaseModel):
    forma_pago: str | None = Field(
        default=None, pattern="^(EFECTIVO|TRANSFERENCIA|ABONO|FIADO)$"
    )
    abono_inicial_monto: Decimal | None = Field(default=None, ge=0)
    abono_inicial_metodo: str | None = Field(
        default=None, pattern="^(EFECTIVO|TRANSFERENCIA)$"
    )
    factura: FacturaIn | None = None


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


async def _archivar_pdf(
    pool: asyncpg.Pool,
    settings: Any,
    cliente_id: str,
    cliente: Mapping[str, Any],
    pdf: bytes,
    numero: str,
) -> tuple[str, str | None]:
    cfg = await _config_bunny(pool, settings)
    carpeta = media_svc.carpeta_cliente(
        cliente["nombre"], cliente["cedula"], cliente["ruc"], cliente_id
    )
    storage_path = media_svc.ruta_media(f"{carpeta}/cotizaciones", "DOCUMENTO", "pdf")
    if not cfg["configurado"]:
        media_svc.guardar_sandbox(settings.media_dir, storage_path, pdf)
        backend = "SANDBOX"
        cdn_url = None
    else:
        cliente_bunny = BunnyHttpStorageClient(
            storage_zone=str(cfg["storage_zone"]),
            api_key=str(cfg["api_key"]),
            cdn_host=str(cfg["cdn_host"]),
            endpoint=settings.bunny_storage_endpoint,
        )
        cdn_url = await cliente_bunny.subir(
            nombre_archivo=storage_path,
            contenido=pdf,
            mimetype="application/pdf",
        )
        backend = "BUNNY"
    media_id = str(uuid.uuid4())
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO media_assets (
                id, cliente_id, tipo, backend, storage_path, cdn_url,
                nombre_original, mime_original, mime_final, bytes_original,
                bytes_final, sha256, etiquetas, metadata
            ) VALUES (
                $1::uuid, $2::uuid, 'DOCUMENTO', $3, $4, $5,
                $6, 'application/pdf', 'application/pdf', $7,
                $8, $9, $10::jsonb, $11::jsonb
            )
            """,
            media_id,
            cliente_id,
            backend,
            storage_path,
            cdn_url,
            f"{numero}.pdf",
            len(pdf),
            len(pdf),
            media_svc.sha256(pdf),
            json.dumps(["cotizacion"], ensure_ascii=False),
            json.dumps({"numero": numero}, ensure_ascii=False),
        )
    return media_id, cdn_url


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
    factura_datos = fila["factura_datos"] or {}
    if isinstance(factura_datos, str):
        try:
            factura_datos = json.loads(factura_datos)
        except json.JSONDecodeError:
            factura_datos = {}
    data["factura_datos"] = dict(factura_datos) if isinstance(factura_datos, Mapping) else {}
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


@router.post("/{cotizacion_id}/enviar")
async def enviar(request: Request, cotizacion_id: str) -> dict[str, Any]:
    """Genera el PDF, lo archiva y lo envia por WhatsApp (o SANDBOX)."""
    await exigir_modulo(request, "cotizaciones", mutacion=True)
    pool = _pool(request)
    settings = _settings(request)
    fila = await pool.fetchrow(
        """
        SELECT c.*, cl.nombre AS cliente_nombre, cl.telefono_whatsapp,
               cl.cedula, cl.ruc, cl.ciudad
          FROM cotizaciones c
          JOIN clients cl ON cl.id = c.cliente_id
         WHERE c.id = $1
        """,
        _uuid(cotizacion_id, "cotizacion_id"),
    )
    if fila is None:
        raise HTTPException(status_code=404, detail="cotizacion no encontrada")
    if fila["estado"] in ("CONVERTIDA", "RECHAZADA", "VENCIDA"):
        raise HTTPException(
            status_code=422, detail=f"cotizacion en estado {fila['estado']} no se envia"
        )
    telefono = str(fila["telefono_whatsapp"] or "").strip()
    if not telefono:
        raise HTTPException(
            status_code=422,
            detail="TELEFONO_REQUERIDO: agrega el telefono del cliente antes de enviar",
        )
    empresa = dict(await setting(pool, "empresa.bot_publico", {}) or {})
    extras = await pool.fetch(
        "SELECT descripcion, monto, cobrable FROM cotizacion_extras WHERE cotizacion_id = $1 ORDER BY orden",
        fila["id"],
    )
    pdf = generar_pdf(
        {
            "tipo_documento": "COTIZACION",
            "numero": fila["numero"],
            "fecha": date.today(),
            "referencia": f"Cotizacion {fila['numero']}",
            "cliente_nombre": fila["cliente_nombre"],
            "cliente_ruc": fila["ruc"],
            "cliente_ciudad": fila["ciudad"],
            "resistencia": fila["resistencia"],
            "volumen_m3": _money(fila["volumen_m3"]),
            "precio_m3": _money(fila["precio_m3"]),
            "precio_estado": fila["precio_estado"],
            "forma_pago": "POR DEFINIR" if fila["forma_pago"] == "POR_DEFINIR" else fila["forma_pago"],
            "validez": _fecha(fila["valida_hasta"]),
            "subtotal": _money(fila["subtotal"]),
            "iva_pct": _money(fila["iva_pct"]),
            "iva_monto": _money(fila["iva_monto"]),
            "total": _money(fila["total"]),
            "empresa": empresa,
            "extras": [
                {
                    "descripcion": e["descripcion"],
                    "monto": _money(e["monto"]),
                    "cobrable": bool(e["cobrable"]),
                }
                for e in extras
            ],
        }
    )
    try:
        media_id, cdn_url = await _archivar_pdf(
            pool,
            settings,
            str(fila["cliente_id"]),
            {
                "nombre": fila["cliente_nombre"],
                "cedula": fila["cedula"],
                "ruc": fila["ruc"],
            },
            pdf,
            fila["numero"],
        )
    except BunnyError as exc:
        raise HTTPException(status_code=502, detail=f"Bunny.net rechazo el PDF: {exc}") from exc

    evolution = dict(await setting(pool, "integraciones.evolution", {}) or {})
    sandbox = bool(evolution.get("sandbox", True)) or not (
        evolution.get("url") and evolution.get("instancia") and evolution.get("api_key")
    )
    notifier = (
        SandboxNotifier(PostgresRepositorio(pool))
        if sandbox
        else EvolutionNotifier(
            base_url=evolution.get("url"),
            instancia=evolution.get("instancia"),
            api_key=evolution.get("api_key"),
        )
    )
    texto = (
        f"Cotizacion {fila['numero']} de "
        f"{empresa.get('trade_name') or 'Horminor'}. "
        "Revisa el PDF y responde CONFIRMO si estas de acuerdo."
    )
    try:
        enviado = await notifier.enviar_documento(
            telefono, f"{fila['numero']}.pdf", "application/pdf", pdf, texto
        )
    except Exception:
        enviado = False
    canal = "WHATSAPP" if enviado else "PANEL"
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE cotizaciones
                   SET estado = 'ENVIADA', enviada_at = now(),
                       enviada_por = COALESCE(enviada_por, 'panel'),
                       canal_envio = $2, pdf_media_id = $3::uuid,
                       updated_at = now()
                 WHERE id = $1
                """,
                fila["id"],
                canal,
                media_id,
            )
            await conn.execute(
                """
                INSERT INTO cotizacion_eventos
                    (cotizacion_id, tipo, canal, mensaje, actor, payload)
                VALUES ($1, 'ENVIO', $2, $3, 'panel', $4::jsonb)
                """,
                fila["id"],
                canal,
                f"PDF enviado a {telefono}.",
                json.dumps(
                    {"enviado": enviado, "sandbox": sandbox, "media_id": media_id},
                    ensure_ascii=False,
                ),
            )
    return {
        "cotizacion": await _detalle(pool, cotizacion_id),
        "enviado": enviado,
        "modo": "SANDBOX" if sandbox else "EVOLUTION",
        "media_id": media_id,
        "pdf_url": cdn_url,
    }


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
async def convertir(
    request: Request,
    cotizacion_id: str,
    body: ConvertirIn = Body(default=ConvertirIn()),
) -> dict[str, Any]:
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
    if fila["estado"] not in ("ENVIADA", "ACEPTADA"):
        raise HTTPException(
            status_code=422,
            detail="marca la cotizacion como enviada o aceptada antes de convertirla",
        )
    if fila["precio_m3"] is None:
        raise HTTPException(status_code=422, detail="la cotizacion no tiene precio")
    forma_pago = (body.forma_pago or fila["forma_pago"] or "").upper()
    if forma_pago not in ("EFECTIVO", "TRANSFERENCIA", "ABONO", "FIADO"):
        raise HTTPException(
            status_code=422,
            detail="FORMA_PAGO_REQUERIDA: elige efectivo, transferencia, abono o fiado",
        )
    factura_datos = body.factura.model_dump(mode="json") if body.factura else {}
    try:
        resultado = await crear_orden(
            pool,
            NuevaOrden(
                cliente_id=str(fila["cliente_id"]),
                resistencia=fila["resistencia"],
                volumen_m3=_d(fila["volumen_m3"]),
                planta_codigo="PLANTA-COCA",
                forma_pago=forma_pago,
                precio_m3=_d(fila["precio_m3"]),
                creada_por=fila["creado_por"] or "cotizacion",
                notas=f"Desde cotizacion {fila['numero']}. {fila['notas'] or ''}".strip(),
                aplica_iva=True,
                abono_inicial_monto=body.abono_inicial_monto,
                abono_inicial_metodo=body.abono_inicial_metodo,
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
                       orden_id = $2, factura_datos = $3::jsonb,
                       aceptada_at = COALESCE(aceptada_at, now()),
                       updated_at = now()
                 WHERE id = $1
                """,
                fila["id"],
                resultado.orden_id,
                json.dumps(factura_datos, ensure_ascii=False, default=str),
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
    return {
        "cotizacion": await _detalle(pool, cotizacion_id),
        "orden": asdict(resultado),
        "ya_convertida": False,
    }
