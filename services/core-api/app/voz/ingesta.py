"""Ingesta de audio: validar, guardar, transcribir y dejar constancia.

El audio se guarda en ``inbox_voz/`` porque ``media_assets`` exige
``cliente_id``: cuando el cliente se resuelve, se vincula con
``voz_ingesta_media_links``. Nada se escribe en negocio desde aquí.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import asyncpg

from ..db import setting
from ..m1_whatsapp.bunny import BunnyHttpStorageClient
from ..services import media as media_svc
from .normalizador_ec import normalizar_texto
from .stt import ResultadoSTT, construir_proveedor

CANALES = ("PANEL_WEB", "WHATSAPP_M1", "WHATSAPP_MINERIA")
_ESTADOS_VALIDOS = (
    "COMPLETADO",
    "FALLIDO",
    "DEGRADADO_SIN_CREDENCIAL",
)
_MOTIVO_SIN_TEXTO = "STT_SIN_TEXTO: el proveedor respondió sin texto"


def validar_audio(datos: bytes, nombre: str, mime: str | None, settings: Any):
    """Valida tipo y tamaño. Devuelve el archivo listo para guardar."""
    procesado = media_svc.procesar_audio(datos, nombre, mime)
    media_svc.validar_tamano("AUDIO", len(procesado.datos), settings)
    return procesado


async def _config_almacenamiento(pool: asyncpg.Pool, settings: Any) -> dict[str, Any]:
    cfg = {
        "storage_zone": getattr(settings, "bunny_storage_zone", None),
        "api_key": getattr(settings, "bunny_storage_api_key", None),
        "cdn_host": getattr(settings, "bunny_cdn_host", None),
        "sandbox": True,
    }
    try:
        datos = await setting(pool, "integraciones.bunny", {}) or {}
    except Exception:
        datos = {}
    if isinstance(datos, dict):
        for campo in ("storage_zone", "api_key", "cdn_host", "sandbox"):
            if datos.get(campo) not in (None, ""):
                cfg[campo] = datos[campo]
    cfg["sandbox"] = bool(cfg.get("sandbox", True))
    cfg["configurado"] = bool(
        cfg.get("storage_zone")
        and cfg.get("api_key")
        and cfg.get("cdn_host")
        and not cfg["sandbox"]
    )
    return cfg


async def guardar_audio(
    pool: asyncpg.Pool,
    settings: Any,
    procesado: media_svc.ArchivoProcesado,
    sha256: str,
) -> tuple[str, str]:
    """Guarda el binario y devuelve ``(backend, storage_path)``."""
    storage_path = (
        f"inbox_voz/{date.today().isoformat()}/{sha256[:16]}.{procesado.extension}"
    )
    cfg = await _config_almacenamiento(pool, settings)
    if cfg["configurado"]:
        cliente = BunnyHttpStorageClient(
            storage_zone=str(cfg["storage_zone"]),
            api_key=str(cfg["api_key"]),
            cdn_host=str(cfg["cdn_host"]),
            endpoint=getattr(settings, "bunny_storage_endpoint", None),
        )
        await cliente.subir(
            nombre_archivo=storage_path,
            contenido=procesado.datos,
            mimetype=procesado.mime,
        )
        return "BUNNY", storage_path
    media_svc.guardar_sandbox(settings.media_dir, storage_path, procesado.datos)
    return "SANDBOX", storage_path


def _estado(resultado: ResultadoSTT) -> str:
    if resultado.estado in _ESTADOS_VALIDOS:
        return resultado.estado
    return "FALLIDO"


def _duracion_ms(valor: Any) -> int | None:
    try:
        numero = int(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None
    return numero if numero and numero > 0 else None


async def ingestar_audio(
    pool: asyncpg.Pool,
    settings: Any,
    *,
    datos: bytes,
    nombre: str,
    mime: str | None,
    canal_origen: str,
    emisor_usuario: str | None = None,
    emisor_telefono: str | None = None,
    duracion_ms: int | None = None,
) -> dict[str, Any]:
    """Ingesta + intento de transcripción. Devuelve el estado real."""
    canal = (canal_origen or "").upper()
    if canal not in CANALES:
        raise ValueError(f"canal_origen invalido: {canal_origen}")

    procesado = validar_audio(datos, nombre, mime, settings)
    sha256 = media_svc.sha256(procesado.datos)

    existente = await pool.fetchrow(
        """
        SELECT i.id::text AS id, i.storage_backend, i.storage_path,
               (SELECT COALESCE(MAX(t.intento_num), 0)
                  FROM voz_trabajos_stt t WHERE t.ingesta_id = i.id) AS intento_max,
               (SELECT t.estado FROM voz_trabajos_stt t
                 WHERE t.ingesta_id = i.id ORDER BY t.intento_num DESC LIMIT 1)
                   AS ultimo_estado,
               (SELECT t.id::text FROM voz_trabajos_stt t
                 WHERE t.ingesta_id = i.id ORDER BY t.intento_num DESC LIMIT 1)
                   AS ultimo_trabajo,
               (SELECT tr.id::text FROM voz_transcripciones tr
                 WHERE tr.ingesta_id = i.id ORDER BY tr.creado_en DESC LIMIT 1)
                   AS transcripcion_id
          FROM voz_ingestas i
         WHERE i.audio_sha256 = $1 AND i.canal_origen = $2
         ORDER BY i.creado_en
         LIMIT 1
        """,
        sha256,
        canal,
    )

    if existente is not None and existente["ultimo_estado"] == "COMPLETADO":
        fila = await pool.fetchrow(
            """
            SELECT texto_normalizado, texto_crudo, duracion_ms
              FROM voz_transcripciones WHERE id = $1::uuid
            """,
            existente["transcripcion_id"],
        )
        return {
            "ingesta_id": existente["id"],
            "trabajo_id": existente["ultimo_trabajo"],
            "transcripcion_id": existente["transcripcion_id"],
            "estado": "COMPLETADO",
            "canal_origen": canal,
            "storage_backend": existente["storage_backend"],
            "storage_path": existente["storage_path"],
            "audio_sha256": sha256,
            "texto_crudo": (fila["texto_crudo"] if fila else None),
            "texto_normalizado": (fila["texto_normalizado"] if fila else None),
            "duracion_ms": (fila["duracion_ms"] if fila else None),
            "error": None,
            "reutilizada": True,
        }

    if existente is not None:
        # Mismo audio ya guardado: se reintenta la transcripción sin duplicar
        # el binario ni la ingesta.
        ingesta = {"id": existente["id"]}
        backend = existente["storage_backend"]
        storage_path = existente["storage_path"]
        intento = int(existente["intento_max"] or 0) + 1
        reutilizada = True
        async with pool.acquire() as conn:
            trabajo = await conn.fetchrow(
                """
                INSERT INTO voz_trabajos_stt (
                    ingesta_id, intento_num, estado, proveedor_stt, modelo_stt
                ) VALUES ($1::uuid, $2, 'PENDIENTE', 'por_resolver', 'por_resolver')
                RETURNING id::text AS id
                """,
                ingesta["id"],
                intento,
            )
    else:
        backend, storage_path = await guardar_audio(
            pool, settings, procesado, sha256
        )
        reutilizada = False
        async with pool.acquire() as conn:
            async with conn.transaction():
                ingesta = await conn.fetchrow(
                    """
                    INSERT INTO voz_ingestas (
                        audio_sha256, canal_origen, emisor_usuario, emisor_telefono,
                        storage_backend, storage_path, mime_original,
                        tamano_bytes, duracion_ms
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    RETURNING id::text AS id
                    """,
                    sha256,
                    canal,
                    emisor_usuario,
                    emisor_telefono,
                    backend,
                    storage_path,
                    procesado.mime,
                    len(procesado.datos),
                    _duracion_ms(duracion_ms),
                )
                trabajo = await conn.fetchrow(
                    """
                    INSERT INTO voz_trabajos_stt (
                        ingesta_id, intento_num, estado, proveedor_stt, modelo_stt
                    ) VALUES ($1::uuid, 1, 'PENDIENTE', 'por_resolver', 'por_resolver')
                    RETURNING id::text AS id
                    """,
                    ingesta["id"],
                )

    proveedor = await construir_proveedor(pool, settings)
    resultado = await proveedor.transcribir(procesado.datos, procesado.mime)
    estado = _estado(resultado)
    texto = (resultado.texto_crudo or "").strip()
    if estado == "COMPLETADO" and not texto:
        estado = "FALLIDO"
        resultado = ResultadoSTT(
            estado=estado,
            proveedor=resultado.proveedor,
            modelo=resultado.modelo,
            error=_MOTIVO_SIN_TEXTO,
        )

    transcripcion_id: str | None = None
    if estado == "COMPLETADO":
        normalizado = normalizar_texto(texto)
        async with pool.acquire() as conn:
            async with conn.transaction():
                fila = await conn.fetchrow(
                    """
                    INSERT INTO voz_transcripciones (
                        ingesta_id, trabajo_stt_id, idioma_detectado,
                        texto_crudo, texto_normalizado, segmentos_json,
                        confianza_global, duracion_ms
                    ) VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6::jsonb, $7, $8)
                    RETURNING id::text AS id
                    """,
                    ingesta["id"],
                    trabajo["id"],
                    resultado.idioma,
                    texto,
                    normalizado,
                    json.dumps(
                        {
                            "segmentos": resultado.segmentos,
                            "palabras": resultado.palabras,
                        },
                        ensure_ascii=False,
                    ),
                    resultado.confianza if resultado.confianza is not None else 0,
                    _duracion_ms(resultado.duracion_ms),
                )
                transcripcion_id = fila["id"]
                await conn.execute(
                    """
                    UPDATE voz_trabajos_stt
                       SET estado = 'COMPLETADO',
                           proveedor_stt = $2,
                           modelo_stt = $3,
                           costo_stt_usd = $4,
                           error_detalle = NULL,
                           actualizado_en = now()
                     WHERE id = $1::uuid
                    """,
                    trabajo["id"],
                    resultado.proveedor,
                    resultado.modelo,
                    resultado.costo_usd,
                )
    else:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE voz_trabajos_stt
                   SET estado = $2,
                       proveedor_stt = $3,
                       modelo_stt = $4,
                       error_detalle = $5,
                       actualizado_en = now()
                 WHERE id = $1::uuid
                """,
                trabajo["id"],
                estado,
                resultado.proveedor,
                resultado.modelo,
                resultado.error,
            )

    return {
        "ingesta_id": ingesta["id"],
        "trabajo_id": trabajo["id"],
        "transcripcion_id": transcripcion_id,
        "estado": estado,
        "canal_origen": canal,
        "storage_backend": backend,
        "storage_path": storage_path,
        "audio_sha256": sha256,
        "texto_crudo": texto or None,
        "texto_normalizado": normalizar_texto(texto) if texto else None,
        "duracion_ms": _duracion_ms(resultado.duracion_ms),
        "error": None if estado == "COMPLETADO" else (resultado.error or estado),
        "reutilizada": reutilizada,
    }


async def obtener_ingesta(pool: asyncpg.Pool, ingesta_id: str) -> dict[str, Any] | None:
    fila = await pool.fetchrow(
        """
        SELECT id::text AS id, audio_sha256, canal_origen, emisor_usuario,
               emisor_telefono, storage_backend, storage_path, mime_original,
               tamano_bytes, duracion_ms, creado_en
          FROM voz_ingestas WHERE id = $1::uuid
        """,
        ingesta_id,
    )
    if fila is None:
        return None
    trabajo = await pool.fetchrow(
        """
        SELECT id::text AS id, intento_num, estado, proveedor_stt, modelo_stt,
               error_detalle, costo_stt_usd, creado_en
          FROM voz_trabajos_stt
         WHERE ingesta_id = $1::uuid
         ORDER BY intento_num DESC
         LIMIT 1
        """,
        ingesta_id,
    )
    transcripcion = await pool.fetchrow(
        """
        SELECT id::text AS id, idioma_detectado, texto_crudo, texto_normalizado,
               segmentos_json, confianza_global, duracion_ms, creado_en
          FROM voz_transcripciones
         WHERE ingesta_id = $1::uuid
         ORDER BY creado_en DESC
         LIMIT 1
        """,
        ingesta_id,
    )
    datos = dict(fila)
    datos["creado_en"] = fila["creado_en"].isoformat() if fila["creado_en"] else None
    datos["trabajo"] = _fila_json(trabajo, ("costo_stt_usd",))
    datos["transcripcion"] = _fila_json(transcripcion, ("confianza_global",))
    return datos


def _fila_json(fila: Any, decimales: tuple[str, ...]) -> dict[str, Any] | None:
    if fila is None:
        return None
    datos = dict(fila)
    for campo in decimales:
        if datos.get(campo) is not None:
            datos[campo] = str(datos[campo])
    for campo in ("creado_en",):
        if datos.get(campo) is not None:
            datos[campo] = datos[campo].isoformat()
    if "segmentos_json" in datos and datos["segmentos_json"] is not None:
        valor = datos["segmentos_json"]
        if isinstance(valor, str):
            try:
                valor = json.loads(valor)
            except ValueError:
                valor = {}
        if isinstance(valor, dict):
            datos["segmentos"] = valor.get("segmentos") or []
            datos["palabras"] = valor.get("palabras") or []
        elif isinstance(valor, list):
            datos["segmentos"] = valor
            datos["palabras"] = []
        else:
            datos["segmentos"] = []
            datos["palabras"] = []
        datos.pop("segmentos_json", None)
    return datos
