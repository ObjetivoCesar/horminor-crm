"""Crea una factura interna FICTICIA para probar a Gato.

Toma los montos reales de una orden (no los inventa), arma un PDF marcado
``FICTICIA`` y lo adjunta al cliente. Es idempotente por cliente + numero.

Uso:
    docker compose run --rm --no-deps core-api python scripts/factura_prueba.py
    docker compose run --rm --no-deps core-api python scripts/factura_prueba.py --orden 55 --numero PRUEBA-0001

Sale con codigo 1 si no puede crear la factura. No crea datos de negocio
nuevos: solo el documento de prueba y su indice.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import _path  # noqa: F401

import asyncpg

from app.services import factura_pdf
from app.services import media as media_svc
from app.settings import get_settings


def _money(valor: object) -> str:
    return f"{Decimal(str(valor)):,.2f}"


async def main() -> int:
    parser = argparse.ArgumentParser(description="Factura interna ficticia de prueba")
    parser.add_argument("--orden", type=int, default=55, help="Numero de orden (default 55)")
    parser.add_argument("--numero", default="PRUEBA-0001", help="Numero de factura de prueba")
    parser.add_argument("--nota", default="Factura ficticia creada para probar a Gato. No valida para cobro.")
    args = parser.parse_args()

    settings = get_settings()
    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=2)
    try:
        orden = await pool.fetchrow(
            """
            SELECT o.id::text, o.numero, o.cliente_id::text, o.resistencia,
                   o.volumen_m3, o.precio_m3, o.total, o.iva_pct, o.iva_monto,
                   o.total_con_iva, o.forma_pago,
                   c.nombre AS cliente_nombre, c.ruc AS cliente_ruc,
                   c.ciudad AS cliente_ciudad
              FROM orders o
              JOIN clients c ON c.id = o.cliente_id
             WHERE o.numero = $1 AND o.estado <> 'ANULADA'
            """,
            args.orden,
        )
        if orden is None:
            print(f"[FALLO] no existe la orden #{args.orden}")
            return 1
        if orden["total"] is None:
            print(f"[FALLO] la orden #{args.orden} no tiene precio; no se inventa un total")
            return 1

        existente = await pool.fetchrow(
            """
            SELECT id::text, media_id::text
              FROM client_invoices
             WHERE cliente_id = $1::uuid AND numero = $2
            """,
            orden["cliente_id"],
            args.numero,
        )
        if existente:
            print(
                f"[OK] ya existe la factura {args.numero} para "
                f"{orden['cliente_nombre']} (id {existente['id']})"
            )
            print(f"     media_id: {existente['media_id']}")
            print(f"     Pregunta a Gato: ¿Qué facturas tiene {orden['cliente_nombre']}?")
            return 0

        empresa = await pool.fetchval(
            "SELECT value FROM system_settings WHERE key = 'empresa.bot_publico'"
        )
        if isinstance(empresa, str):
            try:
                empresa = json.loads(empresa)
            except ValueError:
                empresa = {}
        empresa = empresa or {}

        subtotal = Decimal(str(orden["total"]))
        iva_pct = Decimal(str(orden["iva_pct"] or 0))
        iva_monto = Decimal(str(orden["iva_monto"] or 0))
        total = Decimal(str(orden["total_con_iva"] or subtotal))
        if total != subtotal + iva_monto:
            print("[FALLO] los montos de la orden son incoherentes")
            return 1

        datos_pdf = {
            "numero": args.numero,
            "fecha": date.today(),
            "cliente_nombre": orden["cliente_nombre"],
            "cliente_ruc": orden["cliente_ruc"],
            "cliente_ciudad": orden["cliente_ciudad"],
            "orden_numero": orden["numero"],
            "resistencia": orden["resistencia"],
            "volumen_m3": orden["volumen_m3"],
            "precio_m3": orden["precio_m3"],
            "forma_pago": orden["forma_pago"],
            "subtotal": subtotal,
            "iva_pct": iva_pct,
            "iva_monto": iva_monto,
            "total": total,
            "empresa": empresa,
            "es_ficticia": True,
            "nota": args.nota,
        }
        contenido = factura_pdf.generar_pdf(datos_pdf)

        carpeta = media_svc.carpeta_cliente(
            orden["cliente_nombre"],
            None,
            orden["cliente_ruc"],
            orden["cliente_id"],
        )
        storage_path = media_svc.ruta_media(
            f"{carpeta}/facturas", "DOCUMENTO", "pdf"
        )
        Path(settings.media_dir).mkdir(parents=True, exist_ok=True)
        media_svc.guardar_sandbox(settings.media_dir, storage_path, contenido)

        media_id = str(uuid4())
        digest = media_svc.sha256(contenido)
        nombre = f"factura_{args.numero}.pdf"

        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO media_assets (
                        id, cliente_id, tipo, backend, storage_path,
                        nombre_original, mime_original, mime_final,
                        bytes_original, bytes_final, sha256, etiquetas, metadata
                    ) VALUES (
                        $1::uuid, $2::uuid, 'DOCUMENTO', 'SANDBOX', $3,
                        $4, 'application/pdf', 'application/pdf',
                        $5, $6, $7, $8::jsonb, $9::jsonb
                    )
                    """,
                    media_id,
                    orden["cliente_id"],
                    storage_path,
                    nombre,
                    len(contenido),
                    len(contenido),
                    digest,
                    json.dumps(["factura", "ficticia"]),
                    json.dumps(
                        {
                            "origen": "script_prueba",
                            "documento": "FACTURA",
                            "ficticia": True,
                        }
                    ),
                )
                factura_id = await conn.fetchval(
                    """
                    INSERT INTO client_invoices (
                        cliente_id, orden_id, numero, fecha, subtotal,
                        iva_pct, iva_monto, total, es_ficticia, nota, media_id
                    ) VALUES (
                        $1::uuid, $2::uuid, $3, CURRENT_DATE, $4,
                        $5, $6, $7, true, $8, $9::uuid
                    )
                    RETURNING id::text
                    """,
                    orden["cliente_id"],
                    orden["id"],
                    args.numero,
                    subtotal,
                    iva_pct,
                    iva_monto,
                    total,
                    args.nota,
                    media_id,
                )

        print("[OK] factura ficticia creada")
        print(f"     factura_id: {factura_id}")
        print(f"     cliente:    {orden['cliente_nombre']}")
        print(f"     orden:      #{orden['numero']}")
        print(f"     numero:     {args.numero}")
        print(f"     total:      ${_money(total)}")
        print(f"     media_id:   {media_id}")
        print(f"     archivo:    {storage_path}")
        print(f"     URL:        /api/v1/media/{media_id}/archivo")
        print(f"     Pregunta a Gato: ¿Qué facturas tiene {orden['cliente_nombre']}?")
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
