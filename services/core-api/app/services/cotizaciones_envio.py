"""Servicio compartido de envío y programación de cotizaciones por WhatsApp.

Un solo camino para el panel (`routers/cotizaciones.py`) y Gato (`skills`):
- Genera el PDF con la versión vigente (incluyendo notas/descuento/extras).
- Archiva el PDF en Bunny o sandbox (`media_assets`).
- Si hay hora futura (`cuando`), programa el envío en `gato_recordatorios`
  reconciliando cualquier programación previa abierta de esa cotización.
- Si es envío inmediato, envía por Evolution o Sandbox y **solo** marca la
  cotización `ENVIADA` cuando `enviado=True` (nunca finge envío en `PANEL`).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg
from fastapi import HTTPException

from .. import tiempo
from ..db import setting
from ..m1_whatsapp.bunny import BunnyError, BunnyHttpStorageClient
from ..m1_whatsapp.models import formato_whatsapp
from ..m1_whatsapp.notifications import EvolutionNotifier
from ..m1_whatsapp.repositorio import PostgresRepositorio
from ..routers.cotizaciones import _config_bunny
from ..sandbox import SandboxNotifier
from ..services import media as media_svc
from .cotizaciones import coordenada, fecha, money
from .factura_pdf import generar_pdf


def _campo(fila: Any, nombre: str, defecto: Any = None) -> Any:
    try:
        return fila[nombre]
    except (KeyError, IndexError, TypeError):
        return defecto


def _maps_url(lat: Any, lng: Any) -> str | None:
    latitud = coordenada(lat)
    longitud = coordenada(lng)
    if latitud is None or longitud is None:
        return None
    return f"https://www.google.com/maps?q={latitud},{longitud}"


async def notifier_activo(pool: asyncpg.Pool) -> tuple[Any, bool]:
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


async def archivar_pdf(
    pool: asyncpg.Pool,
    settings: Any,
    cliente_id: str,
    cliente: dict[str, Any],
    pdf: bytes,
    numero: str,
) -> tuple[str, str | None]:
    cfg = await _config_bunny(pool, settings)
    carpeta = media_svc.carpeta_cliente(
        cliente["nombre"], cliente.get("cedula"), cliente.get("ruc"), cliente_id
    )
    storage_path = media_svc.ruta_media(f"{carpeta}/cotizaciones", "DOCUMENTO", "pdf")
    if not cfg.get("configurado"):
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


def _nota_pdf(fila: Any) -> str | None:
    partes: list[str] = []
    if _campo(fila, "notas"):
        partes.append(str(fila["notas"]).strip())
    if _campo(fila, "acceso_notas"):
        partes.append(f"Acceso: {str(fila['acceso_notas']).strip()}")
    return "; ".join(p for p in partes if p) or None


async def enviar_cotizacion(
    pool: asyncpg.Pool,
    settings: Any,
    cotizacion_id: str,
    *,
    actor: Any = None,
    telefono_destino: str | None = None,
    destinatario_nombre: str | None = None,
    cuando: datetime | None = None,
    clave_idempotencia: str | None = None,
) -> dict[str, Any]:
    """Genera/archiva PDF y envía o programa la cotización por WhatsApp."""
    try:
        cot_uuid = uuid.UUID(str(cotizacion_id))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="cotizacion_id invalido") from exc

    fila = await pool.fetchrow(
        """
        SELECT c.*, cl.nombre AS cliente_nombre, cl.telefono_whatsapp,
               cl.cedula, cl.ruc, cl.ciudad
          FROM cotizaciones c
          JOIN clients cl ON cl.id = c.cliente_id
         WHERE c.id = $1
        """,
        cot_uuid,
    )
    if fila is None:
        raise HTTPException(status_code=404, detail="cotizacion no encontrada")
    if fila["estado"] in ("CONVERTIDA", "RECHAZADA", "VENCIDA"):
        raise HTTPException(
            status_code=422, detail=f"cotizacion en estado {fila['estado']} no se envia"
        )

    telefono_crudo = str(telefono_destino or fila["telefono_whatsapp"] or "").strip()
    if not telefono_crudo:
        raise HTTPException(
            status_code=422,
            detail="TELEFONO_REQUERIDO: agrega el telefono del cliente antes de enviar",
        )
    telefono = formato_whatsapp(telefono_crudo) if any(c.isdigit() for c in telefono_crudo) else telefono_crudo

    empresa = dict(await setting(pool, "empresa.bot_publico", {}) or {})
    extras = await pool.fetch(
        "SELECT descripcion, monto, cobrable FROM cotizacion_extras WHERE cotizacion_id = $1 ORDER BY orden",
        fila["id"],
    )
    pdf = generar_pdf(
        {
            "tipo_documento": "COTIZACION",
            "numero": fila["numero"],
            "fecha": tiempo.hoy(),
            "referencia": f"Cotizacion {fila['numero']}",
            "obra_direccion": fila["obra_direccion"],
            "ubicacion": {
                "texto": _campo(fila, "ubicacion_texto"),
                "lat": coordenada(_campo(fila, "ubicacion_lat")),
                "lng": coordenada(_campo(fila, "ubicacion_lng")),
                "origen": _campo(fila, "ubicacion_origen"),
                "maps_url": _maps_url(
                    _campo(fila, "ubicacion_lat"), _campo(fila, "ubicacion_lng")
                ),
            },
            "cliente_nombre": fila["cliente_nombre"],
            "cliente_ruc": fila["ruc"],
            "cliente_ciudad": fila["ciudad"],
            "resistencia": fila["resistencia"],
            "volumen_m3": money(fila["volumen_m3"]),
            "precio_m3": money(fila["precio_m3"]),
            "precio_estado": fila["precio_estado"],
            "forma_pago": "POR DEFINIR" if fila["forma_pago"] == "POR_DEFINIR" else fila["forma_pago"],
            "validez": fecha(fila["valida_hasta"]),
            "subtotal": money(fila["subtotal"]),
            "iva_pct": money(fila["iva_pct"]),
            "iva_monto": money(fila["iva_monto"]),
            "total": money(fila["total"]),
            "nota": _nota_pdf(fila),
            "empresa": empresa,
            "extras": [
                {
                    "descripcion": e["descripcion"],
                    "monto": money(e["monto"]),
                    "cobrable": bool(e["cobrable"]),
                }
                for e in extras
            ],
        }
    )
    try:
        media_id, cdn_url = await archivar_pdf(
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

    actor_nombre = getattr(actor, "nombre", None) or (
        actor.get("nombre") if isinstance(actor, dict) else None
    ) or "panel"
    actor_id = getattr(actor, "actor_id", None) or (
        actor.get("id") if isinstance(actor, dict) else None
    ) or actor_nombre
    actor_rol = getattr(actor, "rol", None) or (
        actor.get("rol_base") if isinstance(actor, dict) else None
    ) or "SUPERADMIN"
    conv_id = getattr(actor, "conversacion_id", None)

    texto = (
        f"Cotizacion {fila['numero']} de "
        f"{empresa.get('trade_name') or 'Horminor'}. "
        "Revisa el PDF y responde CONFIRMO si estas de acuerdo."
    )
    notifier, sandbox = await notifier_activo(pool)

    # Programación diferida: archiva el PDF exacto y lo encola en el programador,
    # reconciliando cualquier programación pendiente previa de la misma cotización.
    if cuando is not None:
        if cuando.tzinfo is None:
            cuando = cuando.replace(tzinfo=tiempo.ZONA)
        programado_utc = cuando.astimezone(timezone.utc)
        destino_nombre = destinatario_nombre or fila["cliente_nombre"]
        origen_dest = "DICTADO" if telefono_destino else "CRM"
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE gato_recordatorios
                       SET estado = 'CANCELADO',
                           ultimo_error = 'Reemplazado por nueva programación',
                           updated_at = now()
                     WHERE cotizacion_id = $1 AND estado = 'PENDIENTE'
                    """,
                    fila["id"],
                )
                if clave_idempotencia:
                    ya = await conn.fetchrow(
                        """
                        SELECT id::text AS id, estado, programado_at
                          FROM gato_recordatorios
                         WHERE clave_idempotencia = $1
                        """,
                        clave_idempotencia,
                    )
                    if ya is not None:
                        local = ya["programado_at"].astimezone(tiempo.ZONA)
                        return {
                            "enviado": False,
                            "programada": True,
                            "recordatorio_id": ya["id"],
                            "programado_local": local.isoformat(),
                            "modo": "SANDBOX" if sandbox else "EVOLUTION",
                            "media_id": media_id,
                            "pdf_url": cdn_url,
                            "version": int(fila["version"]),
                            "telefono": telefono,
                            "destinatario": destino_nombre,
                            "repetido": True,
                        }
                rec = await conn.fetchrow(
                    """
                    INSERT INTO gato_recordatorios (
                        creado_por, rol_actor, conversacion_id, cliente_id,
                        destinatario_nombre, telefono, mensaje, programado_at,
                        zona, estado, origen_destino, confirmado_por,
                        confirmado_at, clave_idempotencia, media_id,
                        cotizacion_id, cotizacion_version
                    ) VALUES (
                        $1, $2, $3::uuid, $4::uuid,
                        $5, $6, $7, $8,
                        $9, 'PENDIENTE', $10, $1,
                        now(), $11, $12::uuid,
                        $13::uuid, $14
                    )
                    RETURNING id::text AS id, programado_at
                    """,
                    str(actor_id),
                    str(actor_rol),
                    conv_id,
                    str(fila["cliente_id"]),
                    destino_nombre,
                    telefono,
                    texto,
                    programado_utc,
                    str(tiempo.ZONA),
                    origen_dest,
                    clave_idempotencia,
                    media_id,
                    str(fila["id"]),
                    int(fila["version"]),
                )
                await conn.execute(
                    """
                    UPDATE cotizaciones
                       SET pdf_media_id = $2::uuid, updated_at = now()
                     WHERE id = $1
                    """,
                    fila["id"],
                    media_id,
                )
                await conn.execute(
                    """
                    INSERT INTO cotizacion_eventos
                        (cotizacion_id, tipo, canal, mensaje, actor, payload)
                    VALUES ($1, 'NOTA', 'WHATSAPP', $2, $3, $4::jsonb)
                    """,
                    fila["id"],
                    f"Envío de PDF v{fila['version']} programado para {cuando.astimezone(tiempo.ZONA):%Y-%m-%d %H:%M} a {telefono}.",
                    actor_nombre,
                    json.dumps(
                        {
                            "accion": "PROGRAMADA",
                            "recordatorio_id": rec["id"],
                            "version": int(fila["version"]),
                            "telefono": telefono,
                            "destinatario": destino_nombre,
                            "media_id": media_id,
                            "sandbox": sandbox,
                        },
                        ensure_ascii=False,
                    ),
                )
        return {
            "enviado": False,
            "programada": True,
            "recordatorio_id": rec["id"],
            "programado_local": cuando.astimezone(tiempo.ZONA).isoformat(),
            "modo": "SANDBOX" if sandbox else "EVOLUTION",
            "media_id": media_id,
            "pdf_url": cdn_url,
            "version": int(fila["version"]),
            "telefono": telefono,
            "destinatario": destino_nombre,
        }

    # Envío inmediato
    detalle_envio: dict[str, Any] = {"ok": False, "message_id": None, "estado": "FALLIDO"}
    try:
        if hasattr(notifier, "enviar_documento_detalle"):
            detalle_envio = await notifier.enviar_documento_detalle(
                telefono, f"{fila['numero']}.pdf", "application/pdf", pdf, texto
            )
            enviado = bool(detalle_envio.get("ok"))
        else:
            enviado = bool(
                await notifier.enviar_documento(
                    telefono, f"{fila['numero']}.pdf", "application/pdf", pdf, texto
                )
            )
            detalle_envio["ok"] = enviado
            detalle_envio["estado"] = "ACEPTADA" if enviado else "FALLIDO"
    except Exception as exc:
        enviado = False
        detalle_envio["detalle"] = f"{type(exc).__name__}: {exc}"

    msg_id = detalle_envio.get("message_id")
    async with pool.acquire() as conn:
        async with conn.transaction():
            if enviado:
                await conn.execute(
                    """
                    UPDATE gato_recordatorios
                       SET estado = 'CANCELADO',
                           ultimo_error = 'Enviado inmediatamente',
                           updated_at = now()
                     WHERE cotizacion_id = $1 AND estado = 'PENDIENTE'
                    """,
                    fila["id"],
                )
                await conn.execute(
                    """
                    UPDATE cotizaciones
                       SET estado = 'ENVIADA',
                           enviada_at = now(),
                           enviada_por = $2,
                           canal_envio = 'WHATSAPP',
                           pdf_media_id = $3::uuid,
                           whatsapp_msg_id = COALESCE($4, whatsapp_msg_id),
                           updated_at = now()
                     WHERE id = $1
                    """,
                    fila["id"],
                    actor_nombre,
                    media_id,
                    msg_id,
                )
                await conn.execute(
                    """
                    INSERT INTO cotizacion_eventos
                        (cotizacion_id, tipo, canal, mensaje, whatsapp_msg_id, actor, payload)
                    VALUES ($1, 'ENVIO', 'WHATSAPP', $2, $3, $4, $5::jsonb)
                    """,
                    fila["id"],
                    f"PDF v{fila['version']} enviado a {telefono}.",
                    msg_id,
                    actor_nombre,
                    json.dumps(
                        {
                            "enviado": True,
                            "sandbox": sandbox,
                            "media_id": media_id,
                            "version": int(fila["version"]),
                            "telefono": telefono,
                            "destinatario": destinatario_nombre or fila["cliente_nombre"],
                            "estado_proveedor": detalle_envio.get("estado"),
                        },
                        ensure_ascii=False,
                    ),
                )
            else:
                await conn.execute(
                    """
                    UPDATE cotizaciones
                       SET pdf_media_id = $2::uuid, updated_at = now()
                     WHERE id = $1
                    """,
                    fila["id"],
                    media_id,
                )
                await conn.execute(
                    """
                    INSERT INTO cotizacion_eventos
                        (cotizacion_id, tipo, canal, mensaje, actor, payload)
                    VALUES ($1, 'NOTA', 'WHATSAPP', $2, $3, $4::jsonb)
                    """,
                    fila["id"],
                    f"Fallo el envio por WhatsApp a {telefono}; el estado sigue {fila['estado']}.",
                    actor_nombre,
                    json.dumps(
                        {
                            "enviado": False,
                            "sandbox": sandbox,
                            "media_id": media_id,
                            "telefono": telefono,
                            "detalle": detalle_envio.get("detalle"),
                        },
                        ensure_ascii=False,
                    ),
                )

    return {
        "enviado": enviado,
        "programada": False,
        "modo": "SANDBOX" if sandbox else "EVOLUTION",
        "media_id": media_id,
        "pdf_url": cdn_url,
        "version": int(fila["version"]),
        "telefono": telefono,
        "destinatario": destinatario_nombre or fila["cliente_nombre"],
        "message_id": msg_id,
        "estado_proveedor": detalle_envio.get("estado"),
    }


async def consultar_estado_envio(pool: asyncpg.Pool, cotizacion_id: str) -> dict[str, Any] | None:
    """Devuelve el estado real del envío: programada, aceptada, entregada o borrador."""
    try:
        cot_uuid = uuid.UUID(str(cotizacion_id))
    except (TypeError, ValueError):
        return None
    cot = await pool.fetchrow(
        """
        SELECT c.id::text AS id, c.numero, c.estado, c.version, c.canal_envio,
               c.enviada_at, c.whatsapp_msg_id, cl.nombre AS cliente_nombre,
               cl.telefono_whatsapp
          FROM cotizaciones c
          JOIN clients cl ON cl.id = c.cliente_id
         WHERE c.id = $1
        """,
        cot_uuid,
    )
    if cot is None:
        return None
    prog = await pool.fetchrow(
        """
        SELECT id::text AS id, estado, telefono, destinatario_nombre,
               programado_at, enviado_at, proveedor_msg_id, cotizacion_version,
               ultimo_error
          FROM gato_recordatorios
         WHERE cotizacion_id = $1
         ORDER BY created_at DESC
         LIMIT 1
        """,
        cot_uuid,
    )
    ev = await pool.fetchrow(
        """
        SELECT tipo, canal, mensaje, whatsapp_msg_id, payload, created_at
          FROM cotizacion_eventos
         WHERE cotizacion_id = $1 AND tipo IN ('ENVIO', 'NOTA')
         ORDER BY created_at DESC
         LIMIT 1
        """,
        cot_uuid,
    )
    acuse_entregada = False
    msg_id = cot["whatsapp_msg_id"] or (prog["proveedor_msg_id"] if prog else None)
    if msg_id:
        estado_chat = await pool.fetchval(
            "SELECT estado FROM chat_mensajes WHERE whatsapp_msg_id = $1 LIMIT 1",
            msg_id,
        )
        acuse_entregada = str(estado_chat or "").upper() in ("ENTREGADO", "LEIDO")

    estado_envio = "SIN_ENVIAR"
    if acuse_entregada:
        estado_envio = "ENTREGADA"
    elif cot["estado"] == "ENVIADA" and cot["canal_envio"] == "WHATSAPP":
        estado_envio = "ACEPTADA"
    elif prog is not None:
        if prog["estado"] == "PENDIENTE":
            estado_envio = "PROGRAMADA"
        elif prog["estado"] == "ENVIADO":
            estado_envio = "ACEPTADA"
        elif prog["estado"] == "FALLIDO":
            estado_envio = "FALLIDA"

    return {
        "cotizacion_id": cot["id"],
        "numero": cot["numero"],
        "version": int(cot["version"]),
        "estado_cotizacion": cot["estado"],
        "estado_envio": estado_envio,
        "telefono": (prog["telefono"] if prog else None) or cot["telefono_whatsapp"],
        "destinatario": (prog["destinatario_nombre"] if prog else None) or cot["cliente_nombre"],
        "programado_at": prog["programado_at"].isoformat() if prog and prog["programado_at"] else None,
        "enviada_at": cot["enviada_at"].isoformat() if cot["enviada_at"] else None,
        "message_id": msg_id,
        "ultimo_evento": ev["mensaje"] if ev else None,
    }
