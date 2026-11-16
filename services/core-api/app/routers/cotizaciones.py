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
from ..services.cotizaciones import (
    DOS_DECIMALES as _DOS_DECIMALES,
    calcular as _calcular,
    coordenada as _coordenada,
    crear_cotizacion_borrador,
    d as _d,
    fecha as _fecha,
    hash_snapshot as _hash,
    insertar_version as _insertar_version,
    money as _money,
    snapshot as _snapshot,
)
from ..services.factura_pdf import generar_pdf
from ..services.ordenes import NuevaOrden, OrdenInvalidaError, crear_orden
from .chat_clientes import _cliente, _config_bunny, _settings

router = APIRouter(prefix="/api/v1/cotizaciones", tags=["cotizaciones"])

def _pool(request: Request) -> asyncpg.Pool:
    pool = getattr(request.app.state, "pool", None)
    if not isinstance(pool, asyncpg.Pool):
        raise HTTPException(status_code=503, detail="base de datos no disponible")
    return pool


def _campo(fila: Any, nombre: str, defecto: Any = None) -> Any:
    """Lee un campo sin romper si el driver entrega un mapping incompleto."""
    try:
        return fila[nombre]
    except (KeyError, IndexError, TypeError):
        return defecto


def _maps_url(lat: Any, lng: Any) -> str | None:
    """Enlace de Google Maps con el pin real. Sin pin no hay enlace."""
    latitud = _coordenada(lat)
    longitud = _coordenada(lng)
    if latitud is None or longitud is None:
        return None
    return f"https://www.google.com/maps?q={latitud},{longitud}"


def _normalizar_busqueda(texto: str) -> str:
    """Minusculas sin tildes, para buscar nombres y apellidos como el Sabueso."""
    normal = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in normal if not unicodedata.combining(c)).lower().strip()


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
    # Ubicacion de la obra: texto libre y/o pin real. Sin dato queda NULL.
    ubicacion_texto: str | None = Field(default=None, max_length=500)
    ubicacion_lat: Decimal | None = Field(default=None, ge=-90, le=90)
    ubicacion_lng: Decimal | None = Field(default=None, ge=-180, le=180)
    ubicacion_origen: str | None = Field(
        default=None, pattern="^(MANUAL|GPS|WHATSAPP|MAPA)$"
    )


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
    resumen = {
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
    lat = _campo(fila, "ubicacion_lat")
    lng = _campo(fila, "ubicacion_lng")
    resumen.update(
        {
            "ubicacion_texto": _campo(fila, "ubicacion_texto"),
            "ubicacion_lat": _coordenada(lat),
            "ubicacion_lng": _coordenada(lng),
            "ubicacion_origen": _campo(fila, "ubicacion_origen"),
            "ubicacion_maps_url": _maps_url(lat, lng),
            "ubicacion_solicitada_at": _fecha(_campo(fila, "ubicacion_solicitada_at")),
            "ubicacion_recibida_at": _fecha(_campo(fila, "ubicacion_recibida_at")),
        }
    )
    return resumen


async def _notifier(pool: asyncpg.Pool) -> tuple[Any, bool]:
    """Notificador de WhatsApp activo (Evolution real o SANDBOX)."""
    evolution = dict(await setting(pool, "integraciones.evolution", {}) or {})
    sandbox = bool(evolution.get("sandbox", True)) or not (
        evolution.get("url") and evolution.get("instancia") and evolution.get("api_key")
    )
    if sandbox:
        return SandboxNotifier(PostgresRepositorio(pool)), True
    return (
        EvolutionNotifier(
            base_url=evolution.get("url"),
            instancia=evolution.get("instancia"),
            api_key=evolution.get("api_key"),
        ),
        False,
    )


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
    cotizacion_id = await crear_cotizacion_borrador(pool, body)
    return await _detalle(pool, cotizacion_id)


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
    # Solo se toca la ubicacion si el cliente la envio: un PUT parcial no debe
    # borrar el pin que el cliente compartio por WhatsApp.
    toca_ubicacion = bool(
        {"ubicacion_texto", "ubicacion_lat", "ubicacion_lng", "ubicacion_origen"}
        & body.model_fields_set
    )
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
                       version = $18,
                       ubicacion_texto = CASE WHEN $23::boolean THEN $19 ELSE ubicacion_texto END,
                       ubicacion_lat = CASE WHEN $23::boolean THEN $20 ELSE ubicacion_lat END,
                       ubicacion_lng = CASE WHEN $23::boolean THEN $21 ELSE ubicacion_lng END,
                       ubicacion_origen = CASE WHEN $23::boolean THEN $22 ELSE ubicacion_origen END,
                       updated_at = now()
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
                datos["ubicacion_texto"],
                datos["ubicacion_lat"],
                datos["ubicacion_lng"],
                datos["ubicacion_origen"],
                toca_ubicacion,
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
            "obra_direccion": fila["obra_direccion"],
            "ubicacion": {
                "texto": _campo(fila, "ubicacion_texto"),
                "lat": _coordenada(_campo(fila, "ubicacion_lat")),
                "lng": _coordenada(_campo(fila, "ubicacion_lng")),
                "origen": _campo(fila, "ubicacion_origen"),
                "maps_url": _maps_url(
                    _campo(fila, "ubicacion_lat"), _campo(fila, "ubicacion_lng")
                ),
            },
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

    notifier, sandbox = await _notifier(pool)
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


@router.post("/{cotizacion_id}/pedir-ubicacion")
async def pedir_ubicacion(request: Request, cotizacion_id: str) -> dict[str, Any]:
    """Pide el pin de la obra por WhatsApp y deja constancia del pedido.

    El texto vive en ``system_settings`` (``cotizaciones.pedir_ubicacion``):
    Julio lo edita en caliente y no se escribe negocio en el codigo.
    """
    await exigir_modulo(request, "cotizaciones", mutacion=True)
    pool = _pool(request)
    fila = await pool.fetchrow(
        """
        SELECT c.id, c.numero, c.estado, cl.telefono_whatsapp
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
            status_code=422,
            detail=f"cotizacion en estado {fila['estado']} no pide ubicacion",
        )
    telefono = str(fila["telefono_whatsapp"] or "").strip()
    if not telefono:
        raise HTTPException(
            status_code=422,
            detail="TELEFONO_REQUERIDO: agrega el telefono del cliente antes de pedir el pin",
        )
    plantilla = dict(await setting(pool, "cotizaciones.pedir_ubicacion", {}) or {})
    texto = str(plantilla.get("texto") or "").strip()
    if not texto:
        raise HTTPException(
            status_code=503,
            detail="PLANTILLA_UBICACION_NO_CONFIGURADA: revisa cotizaciones.pedir_ubicacion",
        )
    notifier, sandbox = await _notifier(pool)
    try:
        enviado = await notifier.enviar_texto(telefono, texto)
    except Exception:
        enviado = False
    canal = "WHATSAPP" if enviado else "PANEL"
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE cotizaciones
                   SET ubicacion_solicitada_at = now(), updated_at = now()
                 WHERE id = $1
                """,
                fila["id"],
            )
            await conn.execute(
                """
                INSERT INTO cotizacion_eventos
                    (cotizacion_id, tipo, canal, mensaje, actor, payload)
                VALUES ($1, 'UBICACION_SOLICITADA', $2, $3, 'panel', $4::jsonb)
                """,
                fila["id"],
                canal,
                f"Se pidio la ubicacion de la obra a {telefono}.",
                json.dumps(
                    {"enviado": enviado, "sandbox": sandbox, "telefono": telefono},
                    ensure_ascii=False,
                ),
            )
    return {
        "cotizacion": await _detalle(pool, cotizacion_id),
        "enviado": enviado,
        "modo": "SANDBOX" if sandbox else "EVOLUTION",
        "mensaje": texto,
    }


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
