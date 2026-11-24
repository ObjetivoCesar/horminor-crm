"""Ejecutores de acciones del Cerebro que escriben en el CRM.

El primer ejecutor real es **crear_cliente** (momento cero): se apoya en el
servicio compartido `app.services.clients.crear_cliente` para no duplicar la
unicidad de teléfono/cédula ni el estado inicial.

Reglas:
- Solo se llama después de una ratificación humana (el router lo garantiza).
- Si el cliente ya existe (teléfono o cédula repetidos), no se duplica: se
  devuelve el existente y se deja constancia.
- Ningún dato se inventa: lo que no venga en el borrador queda en NULL.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

import asyncpg
from fastapi import HTTPException

from ..asistente.fichas import Resultado
from ..m1_whatsapp.bunny import BunnyError, BunnyHttpStorageClient
from ..services import media as media_svc
from ..services.clients import crear_cliente

CONSULTA = "crear_cliente"
COTIZACION = "crear_cotizacion_borrador"


def _texto(valor: Any) -> str | None:
    limpio = str(valor or "").strip()
    return limpio or None


def _telefono(valor: Any) -> str | None:
    digitos = re.sub(r"\D", "", str(valor or ""))
    return digitos or None


def datos_cliente(parametros: dict[str, Any], borrador_id: str) -> dict[str, Any]:
    """Traduce los parámetros del borrador al alta del cliente."""
    return {
        "nombre": str(parametros.get("nombre") or "").strip(),
        "cedula": _telefono(parametros.get("cedula")),
        "telefono_whatsapp": _telefono(parametros.get("telefono")),
        "ciudad": _texto(parametros.get("ciudad")),
        "direccion_obra": _texto(parametros.get("referencia_obra")),
        "notas": (
            "Alta desde Miau (Cerebro) con ratificación humana. "
            f"Borrador {borrador_id}."
        ),
    }


async def _cliente_existente(
    pool: asyncpg.Pool, datos: dict[str, Any]
) -> dict[str, Any] | None:
    fila = await pool.fetchrow(
        """
        SELECT id::text AS id, nombre
          FROM clients
         WHERE ($1::text IS NOT NULL AND telefono_whatsapp = $1)
            OR ($2::text IS NOT NULL AND cedula = $2)
         LIMIT 1
        """,
        datos.get("telefono_whatsapp"),
        datos.get("cedula"),
    )
    return dict(fila) if fila else None


async def _config_bunny(
    pool: asyncpg.Pool, settings: Any
) -> dict[str, Any] | None:
    """Lee la configuracion de Bunny sin romper si la tabla no responde."""
    cfg: dict[str, Any] = {}
    try:
        crudo = await pool.fetchval(
            "SELECT value FROM system_settings WHERE key = $1",
            "integraciones.bunny",
        )
        if crudo:
            cfg = json.loads(crudo) if isinstance(crudo, str) else dict(crudo)
    except Exception:
        cfg = {}
    for campo, attr in (
        ("storage_zone", "bunny_storage_zone"),
        ("api_key", "bunny_storage_api_key"),
        ("cdn_host", "bunny_cdn_host"),
        ("endpoint", "bunny_storage_endpoint"),
    ):
        if not cfg.get(campo) and settings is not None:
            cfg[campo] = getattr(settings, attr, None)
    if not (cfg.get("storage_zone") and cfg.get("api_key") and cfg.get("cdn_host")):
        return None
    if str(cfg.get("sandbox")).lower() == "true":
        return None
    return cfg


def ruta_manifiesto(carpeta: str, prefijo: str | None) -> str:
    """Ruta estable del manifiesto de alta dentro de la carpeta del cliente."""
    marca = re.sub(r"[^A-Za-z0-9._/-]", "", (prefijo or "")).strip("/")
    relativa = f"clientes/{carpeta}/_momento_cero.json"
    return f"{marca}/{relativa}" if marca else relativa


# Dos buckets, no una carpeta por tipo: la base de datos ya sabe el tipo.
_EXT_MEDIA = {
    "jpg", "jpeg", "png", "webp", "gif", "bmp", "tif", "tiff", "heic", "heif",
    "mp4", "mov", "m4v", "webm", "3gp", "avi", "mkv",
    "ogg", "opus", "oga", "mp3", "m4a", "wav", "aac", "amr", "flac",
}


def bucket_de(nombre: str) -> str:
    """Clasifica por extensión: media (visual/audio) o documentos."""
    ext = (nombre or "").rsplit(".", 1)[-1].lower() if "." in (nombre or "") else ""
    return "media" if ext in _EXT_MEDIA else "documentos"


def destino_cliente(
    prefijo: str | None, carpeta: str, nombre_archivo: str
) -> dict[str, str]:
    """Destino final de un archivo dentro de la carpeta del cliente."""
    nombre = re.sub(r"[^A-Za-z0-9._-]", "_", (nombre_archivo or "").strip()) or "archivo"
    bucket = bucket_de(nombre)
    marca = re.sub(r"[^A-Za-z0-9._/-]", "", (prefijo or "")).strip("/")
    relativa = f"clientes/{carpeta}/{bucket}/{nombre}"
    ruta = f"{marca}/{relativa}" if marca else relativa
    return {"ruta": ruta, "bucket": bucket, "nombre": nombre}


def plan_mover_a_cliente(
    prefijo: str | None, carpeta: str, rutas: list[str]
) -> list[dict[str, str]]:
    """Plan (dry-run) de mover archivos a la carpeta del cliente."""
    plan = []
    for origen in rutas:
        limpia = (origen or "").strip().strip("/")
        if not limpia or ".." in limpia.split("/"):
            continue
        nombre = limpia.rsplit("/", 1)[-1]
        destino = destino_cliente(prefijo, carpeta, nombre)
        plan.append({"origen": limpia, "destino": destino["ruta"], "bucket": destino["bucket"]})
    return plan


async def archivos_de_media(
    pool: asyncpg.Pool, media_ids: list[str]
) -> list[dict[str, Any]]:
    """Filas de media_assets por id (la base manda: Bunny solo guarda bytes)."""
    ids = [str(m or "").strip() for m in (media_ids or []) if str(m or "").strip()]
    if not ids:
        return []
    filas = await pool.fetch(
        """
        SELECT id::text AS id, storage_path, tipo, mime_final, nombre_original
          FROM media_assets
         WHERE id::text = ANY($1::text[])
        """,
        ids,
    )
    return [dict(fila) for fila in filas]


def plan_alta(
    prefijo: str | None, carpeta: str, filas: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Plan del paquete de alta: cada media con su destino y su bucket."""
    plan: list[dict[str, Any]] = []
    for fila in filas:
        origen = str(fila.get("storage_path") or "").strip()
        if not origen or ".." in origen.split("/"):
            continue
        nombre = origen.rsplit("/", 1)[-1]
        destino = destino_cliente(prefijo, carpeta, nombre)
        plan.append(
            {
                "media_id": fila.get("id"),
                "tipo": fila.get("tipo"),
                "nombre": fila.get("nombre_original") or nombre,
                "origen": origen,
                "destino": destino["ruta"],
                "bucket": destino["bucket"],
            }
        )
    return plan


async def mover_archivos_a_cliente(
    pool: asyncpg.Pool,
    settings: Any,
    *,
    carpeta: str,
    media_ids: list[str],
    confirmado: bool,
) -> dict[str, Any]:
    """Mueve la media del alta a la carpeta del cliente y actualiza la base.

    Con ``confirmado=False`` solo devuelve el plan (el pasito).
    """
    cfg = await _config_bunny(pool, settings)
    if cfg is None:
        return {
            "plan": [],
            "resultados": [],
            "advertencia": "Bunny no esta configurado; no se movio nada.",
        }
    prefijo = str(cfg.get("prefijo") or "")
    filas = await archivos_de_media(pool, media_ids)
    plan = plan_alta(prefijo, carpeta, filas)
    if not confirmado or not plan:
        return {"plan": plan, "resultados": []}

    cliente_bunny = BunnyHttpStorageClient(
        storage_zone=str(cfg["storage_zone"]),
        api_key=str(cfg["api_key"]),
        cdn_host=str(cfg["cdn_host"]),
        endpoint=str(cfg.get("endpoint") or "https://storage.bunnycdn.com"),
    )
    resultados = []
    for paso in plan:
        try:
            nueva = await cliente_bunny.mover(paso["origen"], paso["destino"])
            cambiados = await pool.execute(
                """
                UPDATE media_assets
                   SET storage_path = $2, cdn_url = $3
                 WHERE storage_path = $1
                """,
                paso["origen"],
                paso["destino"],
                nueva,
            )
            resultados.append(
                {
                    **paso,
                    "ok": True,
                    "url": nueva,
                    "media_actualizada": cambiados.endswith(" 1"),
                }
            )
        except BunnyError as exc:
            resultados.append({**paso, "ok": False, "error": str(exc)})
    return {"plan": plan, "resultados": resultados}


async def config_bunny(pool: asyncpg.Pool, settings: Any) -> dict[str, Any] | None:
    """Configuracion efectiva de Bunny (publica para el router)."""
    return await _config_bunny(pool, settings)


async def crear_carpeta_cliente(
    pool: asyncpg.Pool,
    settings: Any,
    *,
    cliente: dict[str, Any],
    borrador_id: str,
) -> dict[str, Any]:
    """Deja la carpeta del cliente creada en Bunny con su manifiesto de alta.

    Es best-effort: si Bunny falla, el cliente ya creado no se deshace y se
    devuelve la advertencia para que la secretaría lo resuelva.
    """
    carpeta = media_svc.carpeta_cliente(
        str(cliente.get("nombre") or ""),
        cliente.get("cedula"),
        cliente.get("ruc"),
        str(cliente.get("id") or ""),
    )
    cfg = await _config_bunny(pool, settings)
    prefijo = str((cfg or {}).get("prefijo") or "") if cfg else ""
    ruta = ruta_manifiesto(carpeta, prefijo)
    manifiesto = {
        "cliente_id": cliente.get("id"),
        "nombre": cliente.get("nombre"),
        "borrador_id": borrador_id,
        "creado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "origen": "momento_cero",
        "archivos": [],
    }
    datos = json.dumps(manifiesto, ensure_ascii=False, indent=2).encode("utf-8")

    if cfg is None:
        try:
            media_svc.guardar_sandbox(settings.media_dir, ruta, datos)
            return {
                "carpeta": carpeta,
                "ruta": ruta,
                "backend": "SANDBOX",
                "url": None,
                "advertencia": "Bunny no esta configurado; la carpeta quedo en el sandbox.",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "carpeta": carpeta,
                "ruta": ruta,
                "backend": "SIN_ALMACENAMIENTO",
                "url": None,
                "advertencia": f"no se pudo crear la carpeta: {exc}",
            }

    try:
        cliente_bunny = BunnyHttpStorageClient(
            storage_zone=str(cfg["storage_zone"]),
            api_key=str(cfg["api_key"]),
            cdn_host=str(cfg["cdn_host"]),
            endpoint=str(cfg.get("endpoint") or "https://storage.bunnycdn.com"),
        )
        url = await cliente_bunny.subir(
            nombre_archivo=ruta,
            contenido=datos,
            mimetype="application/json",
        )
        return {
            "carpeta": carpeta,
            "ruta": ruta,
            "backend": "BUNNY",
            "url": url,
            "advertencia": None,
        }
    except (BunnyError, Exception) as exc:  # noqa: BLE001
        return {
            "carpeta": carpeta,
            "ruta": ruta,
            "backend": "ERROR_BUNNY",
            "url": None,
            "advertencia": f"no se pudo crear la carpeta en Bunny: {exc}",
        }


async def crear_cliente_desde_accion(
    pool: asyncpg.Pool,
    *,
    parametros: dict[str, Any],
    borrador_id: str,
    settings: Any = None,
) -> Resultado:
    """Crea el cliente o devuelve el existente, sin duplicar."""
    datos = datos_cliente(parametros, borrador_id)
    if not datos["nombre"]:
        return Resultado(
            CONSULTA,
            "ERROR",
            None,
            nota="El borrador no trae el nombre del cliente; no se escribió nada.",
        )

    try:
        fila = await crear_cliente(
            pool,
            nombre=datos["nombre"],
            cedula=datos["cedula"],
            telefono_whatsapp=datos["telefono_whatsapp"],
            ciudad=datos["ciudad"],
            direccion_obra=datos["direccion_obra"],
            notas=datos["notas"],
            estado="ACTIVO",
        )
    except HTTPException as exc:
        if exc.status_code != 409:
            return Resultado(CONSULTA, "ERROR", None, nota=str(exc.detail))
        existente = await _cliente_existente(pool, datos)
        if existente is None:
            return Resultado(
                CONSULTA,
                "ERROR",
                None,
                nota="El teléfono o la cédula ya existen, pero no se encontró el cliente.",
            )
        return Resultado(
            CONSULTA,
            "OK",
            {"id": existente["id"], "nombre": existente["nombre"], "existente": True},
            nota=(
                f"El cliente ya existía: {existente['nombre']}. "
                "No se creó un duplicado."
            ),
        )

    carpeta = await crear_carpeta_cliente(
        pool, settings, cliente=fila, borrador_id=borrador_id
    )
    nota = f"Cliente creado: {fila['nombre']}."
    if carpeta.get("advertencia"):
        nota += f" {carpeta['advertencia']}"
    else:
        nota += " Carpeta del cliente creada en Bunny."
    return Resultado(
        CONSULTA,
        "OK",
        {
            "id": fila["id"],
            "nombre": fila["nombre"],
            "existente": False,
            "carpeta": carpeta,
        },
        nota=nota,
    )


# ---------------------------------------------------------------------------
# Cotizacion: el Cerebro propone, el panel confirma, el servicio calcula
# ---------------------------------------------------------------------------
# Campos del borrador que no son del alta (son rastro de como se armo).
_CAMPOS_NO_COTIZACION = (
    "precio_estado",
    "descuento_pct",
    "plazo_entrega",
    "fecha_entrega_tentativa",
    "hora_entrega_tentativa",
)


async def crear_cotizacion_desde_accion(
    pool: asyncpg.Pool,
    *,
    parametros: dict[str, Any],
    creado_por: str | None = None,
) -> Resultado:
    """Da de alta la cotizacion en BORRADOR por el servicio compartido.

    El precio, el subtotal y el IVA los calcula `app.services.cotizaciones`
    con `Decimal`: el Cerebro no suma ni inventa cifras. Si falta un dato de
    negocio, el servicio responde 422 y no se escribe nada.
    """
    from pydantic import ValidationError

    from ..routers.cotizaciones import CotizacionIn
    from ..services.cotizaciones import crear_cotizacion_borrador

    datos = {
        clave: valor
        for clave, valor in parametros.items()
        if clave not in _CAMPOS_NO_COTIZACION
    }
    datos["creado_por"] = creado_por or datos.get("creado_por")
    try:
        cuerpo = CotizacionIn(**datos)
    except ValidationError as exc:
        primero = exc.errors()[0]
        campo = ".".join(str(parte) for parte in primero.get("loc") or ())
        return Resultado(
            COTIZACION,
            "ERROR",
            None,
            nota=(
                f"La cotización no se puede armar: {campo} "
                f"{primero.get('msg') or 'no es válido'}."
            ),
        )

    try:
        cotizacion_id = await crear_cotizacion_borrador(pool, cuerpo)
    except HTTPException as exc:
        return Resultado(COTIZACION, "ERROR", None, nota=str(exc.detail))

    fila = await pool.fetchrow(
        """
        SELECT c.numero, c.total, cl.nombre AS cliente_nombre
          FROM cotizaciones c
          LEFT JOIN clients cl ON cl.id = c.cliente_id
         WHERE c.id = $1::uuid
        """,
        cotizacion_id,
    )
    numero = str(fila["numero"]) if fila is not None else ""
    total = str(fila["total"]) if fila is not None else ""
    cliente = str(fila["cliente_nombre"] or "") if fila is not None else ""
    nota = f"Cotización {numero} creada en BORRADOR"
    if cliente:
        nota += f" para {cliente}"
    if total:
        nota += f" por USD {total}"
    return Resultado(
        COTIZACION,
        "OK",
        {
            "id": cotizacion_id,
            "numero": numero,
            "cliente": cliente,
            "total": total,
            "estado": "BORRADOR",
        },
        nota=nota + ".",
    )
