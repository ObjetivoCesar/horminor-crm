"""Historial de conversaciones por cliente (v6.8 / multimedia v6.9).

El chat es un **espejo del WhatsApp del cliente**: el canal oficial es
``WHATSAPP``; el panel lee el mismo hilo y, cuando Evolution esta conectado,
responde por ahi. ``PANEL`` queda para notas internas que no se envian.

La multimedia se comprime y sube a Bunny.net; PostgreSQL solo guarda el
indice (``media_assets``) y las etiquetas. Sin credenciales, el archivo cae
al sandbox local para poder probar el flujo. Nada se inventa: si el cliente
no existe, 404.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

import asyncpg
from fastapi import (
    APIRouter,
    Body,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from ..m1_whatsapp.bunny import BunnyError, BunnyHttpStorageClient
from ..panel_acl import exigir_modulo
from ..services import media as media_svc

router = APIRouter(prefix="/api/v1", tags=["chat"])

CANALES = ("PANEL", "WHATSAPP", "CRM", "NOTA")
DIRECCIONES = ("ENTRANTE", "SALIENTE")
AUTORES = ("CLIENTE", "OPERADOR", "BOT", "SISTEMA")
ESTADOS_ENTREGA = ("PENDIENTE", "ENVIADO", "ENTREGADO", "LEIDO", "FALLIDO")

_CAMPOS_MENSAJE = """
    id::text, direccion, autor_tipo, autor_nombre, autor_usuario_id,
    cuerpo, adjuntos, estado_entrega, leido_panel_at, whatsapp_msg_id,
    created_at
"""

_CAMPOS_MEDIA = """
    id::text, tipo, backend, storage_path, cdn_url, nombre_original,
    mime_final, bytes_final, ancho, alto, duracion_seg, etiquetas
"""


def _pool(request: Request) -> asyncpg.Pool:
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="base de datos no disponible")
    return pool


def _settings(request: Request) -> Any:
    return request.app.state.settings


def _id_cliente(valor: str) -> str:
    """Normaliza el UUID; si no lo es, el cliente no existe."""
    try:
        return str(UUID(str(valor)))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=404, detail="cliente no encontrado")


# Limite simple en memoria para frenar bucles o intentos de saturar la subida.
# En produccion detras de un proxy conviene moverlo a Redis/API gateway.
_RATE: dict[str, list[float]] = {}


def _limitar(request: Request, cubo: str, limite: int, ventana_seg: int = 3600) -> None:
    ip = request.client.host if request.client else "desconocido"
    clave = f"{cubo}:{ip}"
    ahora = time.monotonic()
    marcas = [m for m in _RATE.get(clave, []) if ahora - m < ventana_seg]
    if len(marcas) >= limite:
        raise HTTPException(
            status_code=429,
            detail="demasiadas solicitudes seguidas; espera unos minutos",
        )
    marcas.append(ahora)
    _RATE[clave] = marcas


def _jsonb(valor: Any, defecto: Any) -> Any:
    """asyncpg entrega jsonb como texto: lo devolvemos como objeto."""
    if valor is None:
        return defecto
    if isinstance(valor, str):
        try:
            return json.loads(valor)
        except ValueError:
            return defecto
    return valor


def limpiar_cuerpo(texto: Any) -> str:
    """Recorta y valida el cuerpo de un mensaje (funcion pura, testeable)."""
    cuerpo = " ".join(str(texto or "").split())
    if not cuerpo:
        raise ValueError("el mensaje no puede estar vacio")
    if len(cuerpo) > 8000:
        raise ValueError("el mensaje supera los 8000 caracteres")
    return cuerpo


def _mensaje(fila: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": fila["id"],
        "direccion": fila["direccion"],
        "autor_tipo": fila["autor_tipo"],
        "autor_nombre": fila["autor_nombre"],
        "cuerpo": fila["cuerpo"],
        "adjuntos": _jsonb(fila["adjuntos"], []),
        "estado_entrega": fila["estado_entrega"],
        "leido_panel_at": fila["leido_panel_at"],
        "whatsapp_msg_id": fila["whatsapp_msg_id"],
        "created_at": fila["created_at"],
    }


class MensajeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cuerpo: str = Field(min_length=1, max_length=8000)
    canal: Literal["PANEL", "WHATSAPP", "CRM", "NOTA"] = "WHATSAPP"
    direccion: Literal["ENTRANTE", "SALIENTE"] = "SALIENTE"
    autor_tipo: Literal["CLIENTE", "OPERADOR", "BOT", "SISTEMA"] = "OPERADOR"
    autor_nombre: str | None = Field(default=None, max_length=120)
    adjuntos: list[dict[str, Any]] = Field(default_factory=list)
    whatsapp_msg_id: str | None = Field(default=None, max_length=200)
    estado_entrega: Literal[
        "PENDIENTE", "ENVIADO", "ENTREGADO", "LEIDO", "FALLIDO"
    ] | None = None


async def _cliente(pool: asyncpg.Pool, cliente_id: str) -> asyncpg.Record | None:
    return await pool.fetchrow(
        """
        SELECT id::text, nombre, cedula, ruc, telefono_whatsapp
          FROM clients
         WHERE id = $1::uuid
        """,
        cliente_id,
    )


async def _conversacion_existente(
    pool: asyncpg.Pool, cliente_id: str, canal: str
) -> str | None:
    """Lee el hilo sin crearlo: abrir una carpeta no debe ensuciar la base."""
    return await pool.fetchval(
        "SELECT id::text FROM chat_conversaciones WHERE cliente_id = $1::uuid AND canal = $2",
        cliente_id,
        canal,
    )


async def _conversacion(pool: asyncpg.Pool, cliente_id: str, canal: str) -> str:
    """Devuelve el hilo del cliente+canal, creandolo la primera vez."""
    if not await pool.fetchval("SELECT 1 FROM clients WHERE id = $1::uuid", cliente_id):
        raise HTTPException(status_code=404, detail="cliente no encontrado")
    fila = await pool.fetchrow(
        """
        INSERT INTO chat_conversaciones (cliente_id, canal)
        VALUES ($1::uuid, $2)
        ON CONFLICT (cliente_id, canal) DO NOTHING
        RETURNING id::text
        """,
        cliente_id,
        canal,
    )
    if fila is not None:
        return fila["id"]
    existente = await pool.fetchval(
        "SELECT id::text FROM chat_conversaciones WHERE cliente_id = $1::uuid AND canal = $2",
        cliente_id,
        canal,
    )
    if existente is None:  # carrera perdida contra un borrado; improbable
        raise HTTPException(status_code=409, detail="no se pudo abrir la conversacion")
    return existente


async def _resumen(pool: asyncpg.Pool, conversacion_id: str) -> dict[str, Any]:
    fila = await pool.fetchrow(
        """
        SELECT total_mensajes, no_leidos, ultimo_mensaje_at, ultimo_mensaje_preview
          FROM v_chat_conversacion
         WHERE conversacion_id = $1::uuid
        """,
        conversacion_id,
    )
    if fila is None:
        return {
            "total_mensajes": 0,
            "no_leidos": 0,
            "ultimo_mensaje_at": None,
            "ultimo_mensaje_preview": None,
        }
    return {
        "total_mensajes": int(fila["total_mensajes"] or 0),
        "no_leidos": int(fila["no_leidos"] or 0),
        "ultimo_mensaje_at": fila["ultimo_mensaje_at"],
        "ultimo_mensaje_preview": fila["ultimo_mensaje_preview"],
    }


def _bunny_cfg(settings: Any) -> dict[str, Any]:
    return {
        "storage_zone": settings.bunny_storage_zone,
        "api_key": settings.bunny_storage_api_key,
        "cdn_host": settings.bunny_cdn_host,
        "token_key": settings.bunny_token_key,
        "sandbox": True,
    }


async def _config_bunny(pool: asyncpg.Pool, settings: Any) -> dict[str, Any]:
    cfg = _bunny_cfg(settings)
    try:
        fila = await pool.fetchval("SELECT value FROM system_settings WHERE key = $1", "integraciones.bunny")
        datos = _jsonb(fila, {})
        if isinstance(datos, dict):
            for campo in ("storage_zone", "api_key", "cdn_host", "token_key", "sandbox"):
                if datos.get(campo) not in (None, ""):
                    cfg[campo] = datos[campo]
    except Exception:
        pass
    cfg["sandbox"] = bool(cfg.get("sandbox", True))
    # Respetar el interruptor: credenciales cargadas con sandbox=true siguen
    # usando el sandbox local para no subir archivos reales por accidente.
    cfg["configurado"] = bool(
        cfg.get("storage_zone")
        and cfg.get("api_key")
        and cfg.get("cdn_host")
        and not cfg["sandbox"]
    )
    return cfg


def _url_media(fila: asyncpg.Record | dict[str, Any], cfg: dict[str, Any]) -> str:
    backend = fila["backend"]
    if backend == "BUNNY":
        return media_svc.firmar_url_bunny(
            str(cfg.get("cdn_host") or ""),
            str(fila["storage_path"]),
            cfg.get("token_key"),
        )
    return f"/api/v1/media/{fila['id']}/archivo"


async def _enriquecer_adjuntos(
    pool: asyncpg.Pool, mensajes: list[dict[str, Any]], settings: Any
) -> None:
    """Agrega la URL vigente a cada adjunto sin guardarla en la base."""
    ids: list[str] = []
    for mensaje in mensajes:
        for adjunto in mensaje.get("adjuntos") or []:
            if isinstance(adjunto, dict) and adjunto.get("media_id"):
                ids.append(str(adjunto["media_id"]))
    if not ids:
        return
    cfg = await _config_bunny(pool, settings)
    filas = await pool.fetch(
        f"SELECT {_CAMPOS_MEDIA} FROM media_assets WHERE id = ANY($1::uuid[])",
        list(dict.fromkeys(ids)),
    )
    por_id = {fila["id"]: fila for fila in filas}
    for mensaje in mensajes:
        adjuntos = []
        for adjunto in mensaje.get("adjuntos") or []:
            if not isinstance(adjunto, dict):
                continue
            fila = por_id.get(str(adjunto.get("media_id")))
            if fila is None:
                adjuntos.append(adjunto)
                continue
            adjuntos.append(
                {
                    "media_id": fila["id"],
                    "tipo": fila["tipo"],
                    "mime": fila["mime_final"],
                    "bytes": int(fila["bytes_final"] or 0),
                    "nombre": fila["nombre_original"],
                    "ancho": fila["ancho"],
                    "alto": fila["alto"],
                    "duracion_seg": float(fila["duracion_seg"]) if fila["duracion_seg"] is not None else None,
                    "etiquetas": _jsonb(fila["etiquetas"], []),
                    "url": _url_media(fila, cfg),
                }
            )
        mensaje["adjuntos"] = adjuntos


def _whatsapp_estado(request: Request) -> dict[str, Any]:
    runtime = getattr(request.app.state, "whatsapp", None)
    if runtime is None:
        return {"conectado": False, "modo": "NO_INICIADO"}
    try:
        estado = runtime.estado()
    except Exception:
        return {"conectado": False, "modo": "DESCONOCIDO"}
    notifier = str(estado.get("notifier") or "")
    return {
        "conectado": notifier == "evolution",
        "modo": estado.get("modo") or "DESCONOCIDO",
        "juez": estado.get("juez"),
    }


@router.get("/clients/{cliente_id}/chat")
async def leer_chat(
    request: Request,
    cliente_id: str,
    canal: str = Query(default="WHATSAPP"),
    limite: int = Query(default=80, ge=1, le=200),
    antes_de: datetime | None = Query(default=None),
) -> dict[str, Any]:
    await exigir_modulo(request, "clientes_cartera")
    if canal not in CANALES:
        raise HTTPException(status_code=422, detail="canal invalido")
    pool = _pool(request)
    cliente_id = _id_cliente(cliente_id)
    if await _cliente(pool, cliente_id) is None:
        raise HTTPException(status_code=404, detail="cliente no encontrado")
    conversacion_id = await _conversacion_existente(pool, cliente_id, canal)
    if conversacion_id is None:
        return {
            "cliente_id": cliente_id,
            "conversacion_id": None,
            "canal": canal,
            "resumen": {
                "total_mensajes": 0,
                "no_leidos": 0,
                "ultimo_mensaje_at": None,
                "ultimo_mensaje_preview": None,
            },
            "mensajes": [],
            "hay_mas": False,
            "siguiente_antes_de": None,
            "whatsapp": _whatsapp_estado(request),
        }

    parametros: list[Any] = [conversacion_id]
    filtro = ""
    if antes_de is not None:
        parametros.append(antes_de)
        filtro = f" AND created_at < ${len(parametros)}"
    filas = await pool.fetch(
        f"""
        SELECT {_CAMPOS_MENSAJE}
          FROM chat_mensajes
         WHERE conversacion_id = $1::uuid{filtro}
         ORDER BY created_at DESC, id DESC
         LIMIT ${len(parametros) + 1}
        """,
        *parametros,
        limite + 1,
    )
    hay_mas = len(filas) > limite
    visibles = list(reversed(filas[:limite]))
    mensajes = [_mensaje(f) for f in visibles]
    await _enriquecer_adjuntos(pool, mensajes, _settings(request))
    return {
        "cliente_id": cliente_id,
        "conversacion_id": conversacion_id,
        "canal": canal,
        "resumen": await _resumen(pool, conversacion_id),
        "mensajes": mensajes,
        "hay_mas": hay_mas,
        "siguiente_antes_de": visibles[0]["created_at"] if hay_mas and visibles else None,
        "whatsapp": _whatsapp_estado(request),
    }


@router.post("/clients/{cliente_id}/chat/mensajes")
async def enviar_mensaje(
    request: Request,
    cliente_id: str,
    payload: MensajeIn = Body(...),
) -> dict[str, Any]:
    perfil = await exigir_modulo(request, "clientes_cartera", mutacion=True)
    _limitar(request, "mensajes", 180)
    try:
        cuerpo = limpiar_cuerpo(payload.cuerpo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    pool = _pool(request)
    cliente_id = _id_cliente(cliente_id)
    cliente = await _cliente(pool, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="cliente no encontrado")
    conversacion_id = await _conversacion(pool, cliente_id, payload.canal)

    if payload.whatsapp_msg_id:
        existente = await pool.fetchrow(
            f"""
            SELECT {_CAMPOS_MENSAJE}
              FROM chat_mensajes
             WHERE whatsapp_msg_id = $1
            """,
            payload.whatsapp_msg_id,
        )
        if existente is not None:
            mensaje = _mensaje(existente)
            await _enriquecer_adjuntos(pool, [mensaje], _settings(request))
            return {
                "conversacion_id": conversacion_id,
                "mensaje": mensaje,
                "duplicado": True,
                "resumen": await _resumen(pool, conversacion_id),
            }

    saliente = payload.direccion == "SALIENTE"
    estado = payload.estado_entrega
    metadata: dict[str, Any] = {}
    if saliente and payload.canal == "WHATSAPP" and estado is None:
        runtime = getattr(request.app.state, "whatsapp", None)
        telefono = (cliente["telefono_whatsapp"] or "").strip()
        conectado = bool(runtime and getattr(runtime.notifier, "nombre", "") == "evolution")
        if not telefono:
            estado = "FALLIDO"
            metadata["motivo"] = "cliente_sin_whatsapp"
        elif conectado:
            enviado = await runtime.notifier.enviar_texto(telefono, cuerpo)
            estado = "ENVIADO" if enviado else "FALLIDO"
            if not enviado:
                metadata["motivo"] = "evolution_rechazo"
        else:
            estado = "PENDIENTE"
            metadata["motivo"] = "whatsapp_no_conectado"
    if estado is None:
        estado = "ENVIADO" if saliente else "ENTREGADO"

    autor_nombre = payload.autor_nombre or perfil.get("nombre")
    autor_usuario_id = perfil.get("id") if payload.autor_tipo == "OPERADOR" else None

    fila = await pool.fetchrow(
        f"""
        INSERT INTO chat_mensajes (
            conversacion_id, direccion, autor_tipo, autor_nombre,
            autor_usuario_id, cuerpo, adjuntos, whatsapp_msg_id,
            estado_entrega, leido_panel_at, metadata
        ) VALUES (
            $1::uuid, $2, $3, $4,
            $5, $6, $7::jsonb, $8,
            $9, CASE WHEN $2 = 'SALIENTE' THEN now() ELSE NULL END, $10::jsonb
        )
        RETURNING {_CAMPOS_MENSAJE}
        """,
        conversacion_id,
        payload.direccion,
        payload.autor_tipo,
        autor_nombre,
        autor_usuario_id,
        cuerpo,
        json.dumps(payload.adjuntos or []),
        payload.whatsapp_msg_id,
        estado,
        json.dumps(metadata),
    )
    assert fila is not None
    mensaje = _mensaje(fila)
    await _enriquecer_adjuntos(pool, [mensaje], _settings(request))
    return {
        "conversacion_id": conversacion_id,
        "mensaje": mensaje,
        "duplicado": False,
        "resumen": await _resumen(pool, conversacion_id),
    }


@router.post("/clients/{cliente_id}/chat/adjuntos")
async def enviar_adjunto(
    request: Request,
    cliente_id: str,
    archivo: UploadFile = File(...),
    cuerpo: str = Form(default=""),
    canal: str = Form(default="WHATSAPP"),
    etiquetas: str = Form(default="[]"),
    tipo: str | None = Form(default=None),
) -> dict[str, Any]:
    """Sube un archivo: valida, comprime, guarda y lo cuelga del hilo."""
    perfil = await exigir_modulo(request, "clientes_cartera", mutacion=True)
    _limitar(request, "subidas", 30)
    if canal not in CANALES:
        raise HTTPException(status_code=422, detail="canal invalido")
    settings = _settings(request)
    pool = _pool(request)
    cliente_id = _id_cliente(cliente_id)
    cliente = await _cliente(pool, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="cliente no encontrado")

    nombre = archivo.filename or "archivo"
    try:
        tipo_detectado = media_svc.detectar_tipo(nombre, archivo.content_type, tipo)
    except media_svc.MediaInvalido as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    limite = media_svc.limite_bytes(tipo_detectado, settings)
    if archivo.size is not None and archivo.size > limite:
        raise HTTPException(
            status_code=413,
            detail=f"el archivo supera el limite de {limite // (1024 * 1024)} MB",
        )

    try:
        lista_etiquetas = json.loads(etiquetas) if etiquetas else []
        if not isinstance(lista_etiquetas, list):
            lista_etiquetas = []
    except ValueError:
        lista_etiquetas = []

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
                datos=None if tipo_detectado == "VIDEO" else ruta_tmp.read_bytes(),
                ruta=ruta_tmp if tipo_detectado == "VIDEO" else None,
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
    storage_path = media_svc.ruta_media(carpeta, procesado.tipo, procesado.extension)
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

    conversacion_id = await _conversacion(pool, cliente_id, canal)
    media_id = str(uuid4())
    digest = media_svc.sha256(procesado.datos)
    saliente = True
    estado = "PENDIENTE" if canal == "WHATSAPP" else "ENVIADO"
    metadata = (
        {"motivo": "envio_multimedia_pendiente_evolution"}
        if canal == "WHATSAPP"
        else {}
    )
    autor_nombre = perfil.get("nombre")
    autor_usuario_id = perfil.get("id")
    caption = cuerpo.strip() or f"[{procesado.tipo.lower()}] {nombre}"
    adjunto = {
        "media_id": media_id,
        "tipo": procesado.tipo,
        "mime": procesado.mime,
        "bytes": len(procesado.datos),
        "nombre": nombre,
        "ancho": procesado.ancho,
        "alto": procesado.alto,
        "duracion_seg": procesado.duracion_seg,
        "etiquetas": lista_etiquetas,
    }

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO media_assets (
                    id, cliente_id, conversacion_id, tipo, backend,
                    storage_path, cdn_url, nombre_original, mime_original,
                    mime_final, bytes_original, bytes_final, ancho, alto,
                    duracion_seg, sha256, etiquetas, metadata
                ) VALUES (
                    $1::uuid, $2::uuid, $3::uuid, $4, $5,
                    $6, $7, $8, $9,
                    $10, $11, $12, $13, $14,
                    $15, $16, $17::jsonb, $18::jsonb
                )
                """,
                media_id,
                cliente_id,
                conversacion_id,
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
                json.dumps(lista_etiquetas),
                json.dumps({"origen": "panel"}),
            )
            fila = await conn.fetchrow(
                f"""
                INSERT INTO chat_mensajes (
                    conversacion_id, direccion, autor_tipo, autor_nombre,
                    autor_usuario_id, cuerpo, adjuntos, estado_entrega,
                    leido_panel_at, metadata
                ) VALUES (
                    $1::uuid, 'SALIENTE', 'OPERADOR', $2,
                    $3, $4, $5::jsonb, $6,
                    now(), $7::jsonb
                )
                RETURNING {_CAMPOS_MENSAJE}
                """,
                conversacion_id,
                autor_nombre,
                autor_usuario_id,
                caption,
                json.dumps([adjunto]),
                estado,
                json.dumps(metadata),
            )
            assert fila is not None
            await conn.execute(
                "UPDATE media_assets SET mensaje_id = $1::uuid WHERE id = $2::uuid",
                fila["id"],
                media_id,
            )

    mensaje = _mensaje(fila)
    await _enriquecer_adjuntos(pool, [mensaje], settings)
    return {
        "conversacion_id": conversacion_id,
        "mensaje": mensaje,
        "duplicado": False,
        "resumen": await _resumen(pool, conversacion_id),
    }


@router.get("/media/{media_id}")
async def datos_media(
    request: Request, media_id: str, ttl: int = Query(default=3600, ge=60, le=86400)
) -> dict[str, Any]:
    await exigir_modulo(request, "clientes_cartera")
    pool = _pool(request)
    try:
        media_id = str(UUID(media_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="archivo no encontrado")
    fila = await pool.fetchrow(
        f"SELECT {_CAMPOS_MEDIA} FROM media_assets WHERE id = $1::uuid", media_id
    )
    if fila is None:
        raise HTTPException(status_code=404, detail="archivo no encontrado")
    cfg = await _config_bunny(pool, _settings(request))
    if fila["backend"] == "BUNNY":
        url = media_svc.firmar_url_bunny(
            str(cfg.get("cdn_host") or ""),
            str(fila["storage_path"]),
            cfg.get("token_key"),
            ttl_segundos=ttl,
        )
    else:
        url = f"/api/v1/media/{fila['id']}/archivo"
    return {
        "id": fila["id"],
        "tipo": fila["tipo"],
        "mime": fila["mime_final"],
        "bytes": int(fila["bytes_final"] or 0),
        "url": url,
        "etiquetas": _jsonb(fila["etiquetas"], []),
    }


@router.get("/media/{media_id}/archivo")
async def archivo_media(request: Request, media_id: str):
    """Solo para el sandbox local; en Bunny se redirige a la URL firmada."""
    await exigir_modulo(request, "clientes_cartera")
    pool = _pool(request)
    try:
        media_id = str(UUID(media_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="archivo no encontrado")
    fila = await pool.fetchrow(
        f"SELECT {_CAMPOS_MEDIA} FROM media_assets WHERE id = $1::uuid", media_id
    )
    if fila is None:
        raise HTTPException(status_code=404, detail="archivo no encontrado")
    settings = _settings(request)
    cfg = await _config_bunny(pool, settings)
    if fila["backend"] == "BUNNY":
        destino = media_svc.firmar_url_bunny(
            str(cfg.get("cdn_host") or ""),
            str(fila["storage_path"]),
            cfg.get("token_key"),
        )
        return RedirectResponse(destino, status_code=302)
    try:
        ruta = media_svc.ruta_sandbox(settings.media_dir, str(fila["storage_path"]))
    except media_svc.MediaInvalido as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not ruta.is_file():
        raise HTTPException(status_code=404, detail="el archivo ya no esta en el sandbox")
    return FileResponse(
        ruta,
        media_type=str(fila["mime_final"] or "application/octet-stream"),
        filename=str(fila["nombre_original"] or ruta.name),
    )


@router.post("/clients/{cliente_id}/chat/leido")
async def marcar_leido(
    request: Request,
    cliente_id: str,
    canal: str = Query(default="WHATSAPP"),
) -> dict[str, Any]:
    await exigir_modulo(request, "clientes_cartera", mutacion=True)
    if canal not in CANALES:
        raise HTTPException(status_code=422, detail="canal invalido")
    pool = _pool(request)
    cliente_id = _id_cliente(cliente_id)
    conversacion_id = await _conversacion_existente(pool, cliente_id, canal)
    if conversacion_id is None:
        return {
            "marcados": 0,
            "resumen": {
                "total_mensajes": 0,
                "no_leidos": 0,
                "ultimo_mensaje_at": None,
                "ultimo_mensaje_preview": None,
            },
        }
    resultado = await pool.execute(
        """
        UPDATE chat_mensajes
           SET leido_panel_at = now()
         WHERE conversacion_id = $1::uuid
           AND direccion = 'ENTRANTE'
           AND leido_panel_at IS NULL
        """,
        conversacion_id,
    )
    marcados = int(resultado.split()[-1]) if resultado else 0
    return {
        "marcados": marcados,
        "resumen": await _resumen(pool, conversacion_id),
    }


@router.get("/chat/buscar")
async def buscar_mensajes(
    request: Request,
    q: str = Query(default="", min_length=2, max_length=160),
    cliente_id: str | None = Query(default=None),
    limite: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """Busqueda full-text para el bot: devuelve el fragmento con marcas << >>."""
    await exigir_modulo(request, "clientes_cartera")
    pool = _pool(request)
    parametros: list[Any] = [q]
    filtro_cliente = ""
    if cliente_id:
        parametros.append(_id_cliente(cliente_id))
        filtro_cliente = f" AND cv.cliente_id = ${len(parametros)}::uuid"
    filas = await pool.fetch(
        f"""
        SELECT m.id::text,
               m.conversacion_id::text,
               cv.cliente_id::text,
               c.nombre AS cliente_nombre,
               cv.canal,
               m.direccion,
               m.autor_tipo,
               m.cuerpo,
               m.created_at,
               ts_headline(
                   'spanish', m.cuerpo, consulta,
                   'StartSel=<<, StopSel=>>, MaxFragments=2, MaxWords=40'
               ) AS fragmento
          FROM chat_mensajes m
          JOIN chat_conversaciones cv ON cv.id = m.conversacion_id
          JOIN clients c ON c.id = cv.cliente_id,
               websearch_to_tsquery('spanish', $1) AS q(consulta)
         WHERE m.busqueda @@ consulta{filtro_cliente}
         ORDER BY m.created_at DESC
         LIMIT ${len(parametros) + 1}
        """,
        *parametros,
        limite,
    )
    return {"q": q, "total": len(filas), "resultados": [dict(f) for f in filas]}
