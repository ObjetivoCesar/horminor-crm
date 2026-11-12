"""Facturas internas del cliente: subir PDF/foto, listar y descargar.

La facturacion electronica del SRI esta fuera de alcance. Este router solo
adjunta un documento interno (PDF o imagen) a un cliente y, si se indica una
orden, toma los montos de esa orden. Nunca inventa importes: si no hay orden,
el usuario debe enviar el total.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import asyncpg
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from ..m1_whatsapp.bunny import BunnyError, BunnyHttpStorageClient
from ..panel_acl import exigir_modulo
from ..services import media as media_svc
from .chat_clientes import (
    _cliente,
    _config_bunny,
    _id_cliente,
    _limitar,
    _pool,
    _settings,
)

router = APIRouter(prefix="/api/v1", tags=["facturas"])

EXT_FACTURA = {"pdf", "jpg", "jpeg", "png", "webp"}
MAX_NUMERO = 60


def _decimal(valor: Any, campo: str) -> Decimal:
    try:
        numero = Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, AttributeError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{campo} invalido") from exc
    if numero < 0:
        raise HTTPException(status_code=422, detail=f"{campo} no puede ser negativo")
    return numero


def _url_media(media_id: str | None) -> str | None:
    if not media_id:
        return None
    return f"/api/v1/media/{media_id}/archivo"


def _fila_a_dict(fila: asyncpg.Record) -> dict[str, Any]:
    return {
        "factura_id": fila["id"],
        "numero": fila["numero"],
        "fecha": fila["fecha"].isoformat() if fila["fecha"] else None,
        "subtotal": str(fila["subtotal"]),
        "iva_pct": str(fila["iva_pct"]),
        "iva_monto": str(fila["iva_monto"]),
        "total": str(fila["total"]),
        "estado": fila["estado"],
        "es_ficticia": bool(fila["es_ficticia"]),
        "nota": fila["nota"],
        "orden_numero": fila["orden_numero"],
        "media_id": fila["media_id"],
        "archivo": fila["nombre_original"],
        "mime": fila["mime_final"],
        "url": _url_media(fila["media_id"]),
    }


_CAMPOS = """
    f.id::text, f.numero, f.fecha, f.subtotal, f.iva_pct, f.iva_monto,
    f.total, f.estado, f.es_ficticia, f.nota, f.media_id::text,
    o.numero AS orden_numero, m.nombre_original, m.mime_final
"""


async def _listar(pool: asyncpg.Pool, cliente_id: str) -> list[dict[str, Any]]:
    filas = await pool.fetch(
        f"""
        SELECT {_CAMPOS}
          FROM client_invoices f
          LEFT JOIN orders o ON o.id = f.orden_id
          LEFT JOIN media_assets m ON m.id = f.media_id
         WHERE f.cliente_id = $1::uuid
         ORDER BY f.fecha DESC, f.created_at DESC
        """,
        cliente_id,
    )
    return [_fila_a_dict(f) for f in filas]


@router.get("/clients/{cliente_id}/facturas")
async def listar_facturas(request: Request, cliente_id: str) -> dict[str, Any]:
    await exigir_modulo(request, "clientes_cartera")
    pool = _pool(request)
    cliente_id = _id_cliente(cliente_id)
    if await _cliente(pool, cliente_id) is None:
        raise HTTPException(status_code=404, detail="cliente no encontrado")
    return {"facturas": await _listar(pool, cliente_id)}


@router.post("/clients/{cliente_id}/facturas")
async def subir_factura(
    request: Request,
    cliente_id: str,
    archivo: UploadFile = File(...),
    numero: str = Form(...),
    orden_numero: int | None = Form(default=None),
    total: str | None = Form(default=None),
    fecha: str | None = Form(default=None),
    nota: str = Form(default=""),
    es_ficticia: bool = Form(default=False),
) -> dict[str, Any]:
    """Adjunta un PDF o foto. Con orden, los montos salen de la orden."""
    await exigir_modulo(request, "clientes_cartera", mutacion=True)
    _limitar(request, "facturas", 30)
    settings = _settings(request)
    pool = _pool(request)
    cliente_id = _id_cliente(cliente_id)
    cliente = await _cliente(pool, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="cliente no encontrado")

    numero = " ".join(str(numero or "").split())
    if not numero or len(numero) > MAX_NUMERO:
        raise HTTPException(
            status_code=422,
            detail=f"numero es obligatorio y admite hasta {MAX_NUMERO} caracteres",
        )
    if await pool.fetchval(
        "SELECT 1 FROM client_invoices WHERE cliente_id = $1::uuid AND numero = $2",
        cliente_id,
        numero,
    ):
        raise HTTPException(
            status_code=409,
            detail="ya existe una factura con ese numero para este cliente",
        )

    nombre = archivo.filename or "factura"
    ext = media_svc.extension(nombre)
    if ext not in EXT_FACTURA:
        raise HTTPException(
            status_code=422,
            detail="la factura debe ser PDF, JPG, PNG o WEBP",
        )

    orden: asyncpg.Record | None = None
    if orden_numero is not None:
        orden = await pool.fetchrow(
            """
            SELECT id::text, numero, total, iva_pct, iva_monto, total_con_iva
              FROM orders
             WHERE numero = $1 AND cliente_id = $2::uuid AND estado <> 'ANULADA'
            """,
            int(orden_numero),
            cliente_id,
        )
        if orden is None:
            raise HTTPException(
                status_code=404,
                detail=f"la orden #{orden_numero} no existe para este cliente",
            )
        if orden["total"] is None:
            raise HTTPException(
                status_code=422,
                detail="la orden no tiene precio; no se puede facturar un monto inexistente",
            )
        subtotal = Decimal(str(orden["total"]))
        iva_pct = Decimal(str(orden["iva_pct"] or 0))
        iva_monto = Decimal(str(orden["iva_monto"] or 0))
        total_factura = Decimal(str(orden["total_con_iva"] or subtotal))
        if total_factura != subtotal + iva_monto:
            raise HTTPException(status_code=422, detail="la orden tiene montos incoherentes")
    else:
        if total is None:
            raise HTTPException(
                status_code=422,
                detail="sin orden, envia el total de la factura",
            )
        total_factura = _decimal(total, "total")
        subtotal = total_factura
        iva_pct = Decimal("0")
        iva_monto = Decimal("0")

    try:
        fecha_factura = date.fromisoformat(fecha) if fecha else date.today()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="fecha invalida (YYYY-MM-DD)") from exc

    try:
        tipo_detectado = media_svc.detectar_tipo(nombre, archivo.content_type)
    except media_svc.MediaInvalido as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if tipo_detectado not in ("IMAGEN", "DOCUMENTO"):
        raise HTTPException(status_code=422, detail="la factura debe ser PDF o imagen")

    limite = media_svc.limite_bytes(tipo_detectado, settings)
    if archivo.size is not None and archivo.size > limite:
        raise HTTPException(
            status_code=413,
            detail=f"el archivo supera el limite de {limite // (1024 * 1024)} MB",
        )

    with media_svc.directorio_temporal() as tmp:
        ruta_tmp = Path(tmp) / "entrada.bin"
        tamano = 0
        with ruta_tmp.open("wb") as destino:
            while True:
                bloque = await archivo.read(1024 * 1024)
                if not bloque:
                    break
                tamano += len(bloque)
                if tamano > limite:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            "el archivo supera el limite de "
                            f"{limite // (1024 * 1024)} MB"
                        ),
                    )
                destino.write(bloque)
        try:
            media_svc.validar_tamano(tipo_detectado, tamano, settings)
            procesado = await media_svc.procesar(
                nombre=nombre,
                mime=archivo.content_type,
                datos=ruta_tmp.read_bytes(),
                ruta=None,
                settings=settings,
            )
        except media_svc.MediaInvalido as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except media_svc.MediaNoDisponible as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    cfg = await _config_bunny(pool, settings)
    carpeta = media_svc.carpeta_cliente(
        cliente["nombre"], cliente["cedula"], cliente["ruc"], cliente_id
    )
    storage_path = media_svc.ruta_media(
        f"{carpeta}/facturas", procesado.tipo, procesado.extension
    )
    if not cfg["configurado"]:
        try:
            media_svc.guardar_sandbox(settings.media_dir, storage_path, procesado.datos)
        except OSError as exc:
            raise HTTPException(
                status_code=503, detail=f"no se pudo guardar el archivo: {exc}"
            ) from exc
        backend = "SANDBOX"
        cdn_url = None
    else:
        cliente_bunny = BunnyHttpStorageClient(
            storage_zone=str(cfg["storage_zone"]),
            api_key=str(cfg["api_key"]),
            cdn_host=str(cfg["cdn_host"]),
            endpoint=settings.bunny_storage_endpoint,
        )
        try:
            cdn_url = await cliente_bunny.subir(
                nombre_archivo=storage_path,
                contenido=procesado.datos,
                mimetype=procesado.mime,
            )
        except BunnyError as exc:
            raise HTTPException(
                status_code=502, detail=f"Bunny.net rechazo el archivo: {exc}"
            ) from exc
        backend = "BUNNY"

    media_id = str(uuid4())
    digest = media_svc.sha256(procesado.datos)
    etiquetas = ["factura"] + (["ficticia"] if es_ficticia else [])

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO media_assets (
                    id, cliente_id, tipo, backend, storage_path, cdn_url,
                    nombre_original, mime_original, mime_final, bytes_original,
                    bytes_final, ancho, alto, duracion_seg, sha256, etiquetas,
                    metadata
                ) VALUES (
                    $1::uuid, $2::uuid, $3, $4, $5, $6,
                    $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16::jsonb,
                    $17::jsonb
                )
                """,
                media_id,
                cliente_id,
                procesado.tipo,
                backend,
                storage_path,
                cdn_url,
                nombre,
                archivo.content_type,
                procesado.mime,
                tamano,
                len(procesado.datos),
                procesado.ancho,
                procesado.alto,
                Decimal(str(procesado.duracion_seg)) if procesado.duracion_seg is not None else None,
                digest,
                json.dumps(etiquetas),
                json.dumps({"origen": "panel", "documento": "FACTURA"}),
            )
            fila = await conn.fetchrow(
                f"""
                INSERT INTO client_invoices (
                    cliente_id, orden_id, numero, fecha, subtotal, iva_pct,
                    iva_monto, total, es_ficticia, nota, media_id
                ) VALUES (
                    $1::uuid, $2::uuid, $3, $4, $5, $6,
                    $7, $8, $9, $10, $11::uuid
                )
                RETURNING id::text
                """,
                cliente_id,
                orden["id"] if orden else None,
                numero,
                fecha_factura,
                subtotal,
                iva_pct,
                iva_monto,
                total_factura,
                bool(es_ficticia),
                nota.strip() or None,
                media_id,
            )
            assert fila is not None

    facturas = await _listar(pool, cliente_id)
    creada = next((f for f in facturas if f["numero"] == numero), None)
    if creada is None:
        raise HTTPException(status_code=500, detail="no se pudo leer la factura creada")
    return creada
