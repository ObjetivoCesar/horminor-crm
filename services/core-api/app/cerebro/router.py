"""HTTP del Cerebro: interpretar texto/transcripción y consultar borradores."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

import asyncpg
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..asistente import recordatorios
from ..asistente.bibliotecario import Bibliotecario
from ..asistente.orquestador import Actor
from ..db import setting
from ..panel_acl import exigir_modulo
from ..voz import localizar_palabras, normalizar_con_mapa
from .extractor import (
    CLAVES,
    MODELO,
    VERSION_PROMPT,
    ExtractorNoDisponible,
    construir_hechos,
    interpretar,
    recompilar,
)
from .hechos import HechoCitado, validar_hechos
from .internas import (
    ESTADOS as ESTADOS_TAREA,
    ESTADOS_ABIERTOS as ESTADOS_TAREA_ABIERTOS,
    TareaInternaInvalida,
    TareaNoEncontrada,
    TransicionInvalida,
    acusar as acusar_tarea_interna,
    crear as crear_tarea_interna,
    escalar as escalar_tarea_interna,
    listar as listar_tareas_internas,
    marcar_vista,
    registrar as registrar_tarea_interna,
    resolver as resolver_tarea_interna,
    retirar_vocabulario,
)
from .revision import CorreccionInvalida, TIPOS_CONOCIDOS, aplicar
from .sobre import SobreIn

router = APIRouter(prefix="/api/v1/cerebro", tags=["cerebro"])


class InterpretarIn(BaseModel):
    texto: str | None = Field(default=None, max_length=8000)
    transcripcion_id: str | None = None


class ConfirmarIn(BaseModel):
    accion_orden: int = Field(ge=1)


class CorregirIn(BaseModel):
    clave: str = Field(min_length=3, max_length=80)
    valor: Any
    tipo: str | None = Field(default=None, max_length=12)


class ResolverTareaIn(BaseModel):
    resolucion: Literal["RESUELTA", "JUSTIFICADA"]
    nota: str = Field(min_length=3, max_length=2000)
    metadatos: dict[str, Any] = Field(default_factory=dict)


class RegistrarTareaIn(BaseModel):
    nota: str | None = Field(default=None, max_length=2000)
    metadatos: dict[str, Any] = Field(default_factory=dict)


class EscalarTareaIn(BaseModel):
    motivo: str = Field(min_length=3, max_length=500)


class RetirarVocabularioIn(BaseModel):
    clave: str = Field(min_length=3, max_length=80)
    valor_anterior: str = Field(min_length=1, max_length=300)
    valor_nuevo: str = Field(min_length=1, max_length=300)
    motivo: str = Field(min_length=3, max_length=500)


def _pool(request: Request) -> asyncpg.Pool:
    pool = getattr(request.app.state, "pool", None)
    if not isinstance(pool, asyncpg.Pool):
        raise HTTPException(status_code=503, detail="base de datos no disponible")
    return pool


def _jsonb(valor: Any) -> Any:
    if isinstance(valor, str):
        try:
            return json.loads(valor)
        except ValueError:
            return None
    return valor


async def _habilitado(pool: asyncpg.Pool, clave: str) -> bool:
    return bool(await setting(pool, clave, False))


@router.post("/interpretar")
async def interpretar_http(request: Request, body: InterpretarIn) -> dict[str, Any]:
    perfil = await exigir_modulo(request, "cerebro", mutacion=True)
    pool = _pool(request)
    if not await _habilitado(pool, "cerebro.enabled"):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CEREBRO_DESHABILITADO",
                "message": "cerebro.enabled esta apagado; activelo para probar",
            },
        )

    transcripcion_id = (body.transcripcion_id or "").strip() or None
    texto = (body.texto or "").strip()
    palabras: list[dict[str, Any]] = []

    if transcripcion_id:
        try:
            uuid.UUID(transcripcion_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="transcripcion_id invalido") from exc
        fila = await pool.fetchrow(
            """
            SELECT t.texto_crudo, t.segmentos_json
              FROM voz_transcripciones t
             WHERE t.id = $1::uuid
            """,
            transcripcion_id,
        )
        if fila is None:
            raise HTTPException(status_code=404, detail="transcripcion no encontrada")
        texto = str(fila["texto_crudo"] or "").strip()
        datos = _jsonb(fila["segmentos_json"]) or {}
        if isinstance(datos, dict):
            palabras = list(datos.get("palabras") or [])
    elif not texto:
        raise HTTPException(status_code=422, detail="envia texto o transcripcion_id")

    inicio = time.perf_counter()
    try:
        resultado = await interpretar(
            pool,
            texto_crudo=texto,
            palabras_crudas=palabras,
            sandbox=bool(getattr(request.app.state.settings, "sandbox_mode", True)),
        )
    except ExtractorNoDisponible as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    latencia_ms = int((time.perf_counter() - inicio) * 1000)

    sobre = resultado["sobre"]
    borrador = resultado["borrador"]
    hechos = resultado["hechos"]

    usuario = str(perfil.get("nombre") or "desconocido")
    rol = str(perfil.get("rol_base") or "SECRETARIA")

    async with pool.acquire() as conn:
        async with conn.transaction():
            extraccion = await conn.fetchrow(
                """
                INSERT INTO cerebro_extracciones (
                    transcripcion_id, texto_directo, idempotency_key,
                    usuario_solicitante, rol_base_solicitante, modelo_llm,
                    version_prompt, sobre_json, latencia_ms, costo_llm_usd
                ) VALUES (
                    $1::uuid, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, 0
                )
                RETURNING id::text AS id
                """,
                transcripcion_id,
                None if transcripcion_id else texto,
                f"{uuid.uuid4().hex}",
                usuario,
                rol,
                MODELO,
                VERSION_PROMPT,
                json.dumps(sobre.model_dump(), ensure_ascii=False),
                latencia_ms,
            )
            guardado = await conn.fetchrow(
                """
                INSERT INTO cerebro_borradores (
                    extraccion_id, version, estado, acciones_propuestas_json,
                    preguntas_pendientes_json, creado_por
                ) VALUES (
                    $1::uuid, 1, $2, $3::jsonb, $4::jsonb, $5
                )
                RETURNING id::text AS id
                """,
                extraccion["id"],
                borrador.estado,
                json.dumps(
                    [accion.a_dict() for accion in borrador.acciones],
                    ensure_ascii=False,
                ),
                json.dumps(
                    [
                        {"clave": p.clave, "texto": p.texto, "opciones": list(p.opciones)}
                        for p in borrador.preguntas
                    ],
                    ensure_ascii=False,
                ),
                usuario,
            )

    return {
        "extraccion_id": extraccion["id"],
        "borrador_id": guardado["id"],
        "estado": borrador.estado,
        "intencion": borrador.intencion,
        "sobre": sobre.model_dump(),
        "borrador": borrador.a_dict(),
        "hechos": [hecho.a_dict() for hecho in hechos],
        "notas": resultado["notas"],
        "resumen": resultado["resumen"],
        "texto_normalizado": resultado["texto_normalizado"],
        "latencia_ms": latencia_ms,
    }


@router.get("/borradores/{borrador_id}")
async def obtener_borrador(request: Request, borrador_id: str) -> dict[str, Any]:
    await exigir_modulo(request, "cerebro")
    try:
        uuid.UUID(borrador_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="borrador_id invalido") from exc
    pool = _pool(request)
    fila = await pool.fetchrow(
        """
        SELECT b.id::text AS id, b.estado, b.version, b.acciones_propuestas_json,
               b.preguntas_pendientes_json, b.creado_por, b.creado_en,
               e.sobre_json, e.modelo_llm, e.version_prompt, e.latencia_ms
          FROM cerebro_borradores b
          JOIN cerebro_extracciones e ON e.id = b.extraccion_id
         WHERE b.id = $1::uuid
        """,
        borrador_id,
    )
    if fila is None:
        raise HTTPException(status_code=404, detail="borrador no encontrado")
    datos = dict(fila)
    datos["acciones"] = _jsonb(datos.pop("acciones_propuestas_json")) or []
    datos["preguntas"] = _jsonb(datos.pop("preguntas_pendientes_json")) or []
    datos["sobre"] = _jsonb(datos.pop("sobre_json")) or {}
    datos["creado_en"] = (
        datos["creado_en"].isoformat() if datos.get("creado_en") else None
    )
    return datos


# Acciones con ejecutor conectado. Las demas se proponen, pero todavia no se
# pueden ejecutar desde el Cerebro: el endpoint lo dice en vez de simularlo.
ACCIONES_CONECTADAS = ("crear_tarea_recordatorio", "crear_tarea_interna")


async def _hechos_reconstruidos(
    conn: asyncpg.Connection, extraccion_id: str
) -> tuple[list[HechoCitado], list[str], str, SobreIn]:
    """Rehace los hechos citados de una extracción sin llamar al LLM.

    El sobre quedó guardado, y el texto (directo o transcrito) también. Con
    ambos se repite la verificación contra la cita, así una corrección parte
    de los mismos hechos que leyó Julio, no de una nueva interpretación.
    """
    fila = await conn.fetchrow(
        """
        SELECT e.sobre_json, e.texto_directo, t.texto_crudo, t.segmentos_json
          FROM cerebro_extracciones e
          LEFT JOIN voz_transcripciones t ON t.id = e.transcripcion_id
         WHERE e.id = $1::uuid
        """,
        extraccion_id,
    )
    if fila is None:
        raise HTTPException(status_code=404, detail="extraccion no encontrada")
    texto = str(fila["texto_crudo"] or fila["texto_directo"] or "")
    if not texto.strip():
        raise HTTPException(
            status_code=409, detail="esta extraccion no tiene texto para recompilar"
        )
    datos = _jsonb(fila["segmentos_json"]) or {}
    palabras_crudas = list(datos.get("palabras") or []) if isinstance(datos, dict) else []
    sobre = SobreIn.model_validate(_jsonb(fila["sobre_json"]) or {})
    mapa = normalizar_con_mapa(texto)
    palabras = localizar_palabras(texto, palabras_crudas)
    hechos, notas = construir_hechos(
        sobre, texto_crudo=texto, mapa=mapa, palabras=palabras
    )
    return hechos, notas, texto, sobre


@router.post("/borradores/{borrador_id}/corregir")
async def corregir_borrador(
    request: Request, borrador_id: str, body: CorregirIn
) -> dict[str, Any]:
    """Corrige un hecho entendido y recompila. No reescribe el borrador viejo.

    Es la pelota que vuelve a Julio o a la secretaría: el sistema lee lo que
    entendió, la persona lo corrige, y el borrador se rehace con el dato
    correcto. La corrección queda como fila nueva (memoria y vocabulario).
    """
    perfil = await exigir_modulo(request, "cerebro", mutacion=True)
    try:
        uuid.UUID(borrador_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="borrador_id invalido") from exc
    clave = body.clave.strip()
    if clave not in CLAVES:
        raise HTTPException(status_code=422, detail=f"clave no permitida: {clave}")

    pool = _pool(request)
    usuario = str(perfil.get("nombre") or "desconocido")
    rol = str(perfil.get("rol_base") or "SECRETARIA")
    hoy = datetime.now(ZoneInfo("America/Guayaquil")).date()
    sandbox = bool(getattr(request.app.state.settings, "sandbox_mode", True))

    async with pool.acquire() as conn:
        async with conn.transaction():
            padre = await conn.fetchrow(
                """
                SELECT id::text AS id, extraccion_id::text AS extraccion_id,
                       version, estado, borrador_padre_id::text AS padre
                  FROM cerebro_borradores
                 WHERE id = $1::uuid
                 FOR UPDATE
                """,
                borrador_id,
            )
            if padre is None:
                raise HTTPException(status_code=404, detail="borrador no encontrado")
            if padre["estado"] in ("EJECUTADO", "CONFIRMADO", "RECHAZADO"):
                raise HTTPException(
                    status_code=409,
                    detail=f"el borrador esta {padre['estado']}; no se corrige",
                )

            hechos, notas, texto_dictado, sobre = await _hechos_reconstruidos(
                conn, padre["extraccion_id"]
            )
            # Las correcciones anteriores de esta cadena se reaplican en orden:
            # corregir el destinatario no puede borrar el nombre ya corregido.
            ancestros = await conn.fetch(
                """
                WITH RECURSIVE cadena AS (
                    SELECT id, borrador_padre_id
                      FROM cerebro_borradores
                     WHERE id = $1::uuid
                    UNION ALL
                    SELECT b.id, b.borrador_padre_id
                      FROM cerebro_borradores b
                      JOIN cadena c ON b.id = c.borrador_padre_id
                )
                SELECT id::text AS id FROM cadena
                """,
                padre["id"],
            )
            previas = await conn.fetch(
                """
                SELECT clave, valor_nuevo
                  FROM cerebro_correcciones
                 WHERE borrador_id = ANY($1::uuid[])
                 ORDER BY creado_en
                """,
                [fila["id"] for fila in ancestros],
            )
            for previa in previas:
                hechos = aplicar(
                    hechos,
                    {str(previa["clave"]): previa["valor_nuevo"]},
                    tipos=TIPOS_CONOCIDOS,
                )
            actual = next((h for h in hechos if h.clave == clave), None)
            tipo = body.tipo or (
                actual.tipo if actual is not None else TIPOS_CONOCIDOS.get(clave, "TEXTO")
            )
            try:
                corregidos = aplicar(
                    hechos,
                    {clave: body.valor},
                    tipos={clave: tipo},
                    hablante=str(perfil.get("rol_base") or "SUPERADMIN"),
                )
            except CorreccionInvalida as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

            errores = validar_hechos(corregidos)
            if errores:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "HECHO_INVALIDO", "errores": errores},
                )

            nuevo = await recompilar(
                pool,
                hechos=corregidos,
                intencion=sobre.intencion,
                sandbox=sandbox,
                hoy=hoy,
                texto=normalizar_con_mapa(texto_dictado).texto,
            )
            borrador = nuevo["borrador"]
            guardado = await conn.fetchrow(
                """
                INSERT INTO cerebro_borradores (
                    extraccion_id, borrador_padre_id, version, estado,
                    acciones_propuestas_json, preguntas_pendientes_json, creado_por
                ) VALUES (
                    $1::uuid, $2::uuid, $3, $4, $5::jsonb, $6::jsonb, $7
                )
                RETURNING id::text AS id
                """,
                padre["extraccion_id"],
                padre["id"],
                int(padre["version"]) + 1,
                borrador.estado,
                json.dumps(
                    [accion.a_dict() for accion in borrador.acciones],
                    ensure_ascii=False,
                ),
                json.dumps(
                    [
                        {"clave": p.clave, "texto": p.texto, "opciones": list(p.opciones)}
                        for p in borrador.preguntas
                    ],
                    ensure_ascii=False,
                ),
                usuario,
            )
            await conn.execute(
                """
                UPDATE cerebro_borradores
                   SET estado = 'SUPERADO_POR_CORRECCION',
                       lock_version = lock_version + 1
                 WHERE id = $1::uuid
                """,
                padre["id"],
            )
            nuevo_hecho = next(h for h in corregidos if h.clave == clave)
            valor_anterior = None if actual is None or actual.valor is None else str(
                actual.valor
            )
            valor_nuevo = str(nuevo_hecho.valor)
            if valor_anterior == valor_nuevo:
                raise HTTPException(
                    status_code=409, detail="el valor es igual al que ya estaba"
                )
            await conn.execute(
                """
                INSERT INTO cerebro_correcciones (
                    borrador_id, borrador_nuevo_id, extraccion_id, clave,
                    valor_anterior, valor_nuevo, cita, corregido_por, rol_base
                ) VALUES (
                    $1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9
                )
                """,
                padre["id"],
                guardado["id"],
                padre["extraccion_id"],
                clave,
                valor_anterior,
                valor_nuevo,
                actual.evidencia.cita if actual is not None and actual.evidencia else None,
                usuario,
                rol,
            )

    return {
        "extraccion_id": padre["extraccion_id"],
        "borrador_id": guardado["id"],
        "borrador_padre_id": padre["id"],
        "version": int(padre["version"]) + 1,
        "estado": borrador.estado,
        "intencion": borrador.intencion,
        "borrador": borrador.a_dict(),
        "hechos": [hecho.a_dict() for hecho in corregidos],
        "notas": notas + nuevo["notas"],
        "resumen": nuevo["resumen"],
        "texto_normalizado": normalizar_con_mapa(texto_dictado).texto,
        "correccion": {
            "clave": clave,
            "valor_anterior": valor_anterior,
            "valor_nuevo": valor_nuevo,
            "tipo": tipo,
        },
    }


@router.get("/tareas/pendientes")
async def tareas_pendientes(request: Request) -> dict[str, Any]:
    """Recordatorios ya ratificados que todavia no se enviaron.

    El panel los usa para el popout de tareas al entrar y para la campanita.
    """
    await exigir_modulo(request, "cerebro")
    pool = _pool(request)
    internas = await listar_tareas_internas(pool, limite=20)
    filas = await pool.fetch(
        """
        SELECT id::text AS id, destinatario_nombre, telefono, mensaje,
               programado_at, zona, estado, origen_destino
          FROM gato_recordatorios
         WHERE estado IN ('PENDIENTE', 'ENVIANDO')
         ORDER BY programado_at
         LIMIT 20
        """
    )
    tareas: list[dict[str, Any]] = []
    for fila in filas:
        try:
            zona = ZoneInfo(str(fila["zona"] or "America/Guayaquil"))
        except Exception:  # zona invalida guardada: se muestra en UTC
            zona = ZoneInfo("UTC")
        programado = fila["programado_at"].astimezone(zona)
        telefono = str(fila["telefono"] or "")
        legible = telefono
        if telefono.startswith("593") and len(telefono) == 12:
            legible = "0" + telefono[3:]
        tareas.append(
            {
                "id": fila["id"],
                "destinatario": fila["destinatario_nombre"] or legible,
                "telefono": telefono,
                "mensaje": fila["mensaje"],
                "programado_at": fila["programado_at"].isoformat(),
                "programado_local": programado.strftime("%d/%m/%Y %H:%M"),
                "zona": str(fila["zona"]),
                "estado": fila["estado"],
                "origen_destino": fila["origen_destino"],
            }
        )
    return {"tareas": tareas, "internas": internas, "total": len(tareas)}


@router.post("/borradores/{borrador_id}/confirmar")
async def confirmar_accion(
    request: Request, borrador_id: str, body: ConfirmarIn
) -> dict[str, Any]:
    """Ejecuta una accion que un humano acaba de confirmar en pantalla.

    Solo se conecta lo que ya existe y tiene sus propias reglas. La
    confirmacion de esta pantalla ES la ratificacion: la tarea nace PENDIENTE
    y el despachador de Gato la envia a su hora.
    """
    perfil = await exigir_modulo(request, "cerebro", mutacion=True)
    try:
        uuid.UUID(borrador_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="borrador_id invalido") from exc

    actor_id = str(perfil.get("id") or "").strip()
    if not actor_id:
        raise HTTPException(
            status_code=403,
            detail=(
                "Falta el usuario del panel: elige tu perfil antes de confirmar. "
                "Sin un humano identificado no se agenda nada."
            ),
        )
    rol = str(perfil.get("rol_base") or "").strip().upper()

    pool = _pool(request)
    fila = await pool.fetchrow(
        """
        SELECT id::text AS id, estado, acciones_propuestas_json,
               extraccion_id::text AS extraccion_id
          FROM cerebro_borradores
         WHERE id = $1::uuid
        """,
        borrador_id,
    )
    if fila is None:
        raise HTTPException(status_code=404, detail="borrador no encontrado")
    if fila["estado"] not in ("PENDIENTE_CONFIRMACION", "REQUIERE_ACLARACION"):
        raise HTTPException(
            status_code=409,
            detail=f"el borrador esta en {fila['estado']}; no se puede confirmar",
        )

    acciones = _jsonb(fila["acciones_propuestas_json"]) or []
    accion = next(
        (a for a in acciones if int(a.get("orden", 0)) == body.accion_orden), None
    )
    if accion is None:
        raise HTTPException(
            status_code=404,
            detail=f"el borrador no tiene una accion en el paso {body.accion_orden}",
        )
    nombre = str(accion.get("accion_nombre") or "")
    if rol not in (accion.get("rol_requerido") or []):
        raise HTTPException(
            status_code=403,
            detail=(
                f"tu perfil ({rol}) no puede ejecutar {nombre}; "
                f"requiere {' / '.join(accion.get('rol_requerido') or [])}"
            ),
        )
    if accion.get("bloqueada_por"):
        raise HTTPException(
            status_code=409,
            detail=f"la accion esta bloqueada por {accion['bloqueada_por']}",
        )
    if nombre not in ACCIONES_CONECTADAS:
        raise HTTPException(
            status_code=501,
            detail=(
                f"{nombre} todavia no tiene ejecutor conectado; el borrador "
                "queda pendiente y no se escribio nada."
            ),
        )

    dependencia = accion.get("depende_de_orden")
    if dependencia:
        previa = await pool.fetchval(
            """
            SELECT 1 FROM cerebro_ejecuciones
             WHERE borrador_id = $1::uuid AND orden_ejecucion = $2
               AND estado = 'EXITOSO'
             LIMIT 1
            """,
            borrador_id,
            int(dependencia),
        )
        if not previa:
            raise HTTPException(
                status_code=409,
                detail=f"primero hay que ejecutar el paso {dependencia}",
            )

    existente = await pool.fetchrow(
        """
        SELECT id::text AS id, parametros_ejecutados_json,
               entidad_destino_id::text AS entidad_destino_id, ejecutado_en
          FROM cerebro_ejecuciones
         WHERE borrador_id = $1::uuid AND orden_ejecucion = $2
           AND estado = 'EXITOSO'
         ORDER BY intento_num DESC
         LIMIT 1
        """,
        borrador_id,
        body.accion_orden,
    )
    if existente is not None:
        return {
            "borrador_id": borrador_id,
            "accion_orden": body.accion_orden,
            "accion_nombre": nombre,
            "repetido": True,
            "ejecucion_id": existente["id"],
            "estado": "OK",
            "nota": "Esa accion ya se habia ejecutado; no se creo otra.",
            "datos": {
                "id": existente["entidad_destino_id"],
                "estado": "PENDIENTE",
            },
            "ejecutado_en": existente["ejecutado_en"].isoformat(),
        }

    parametros = accion.get("parametros") or {}
    if nombre == "crear_tarea_recordatorio":
        resultado = await _ejecutar_tarea(
            request,
            pool,
            borrador_id=borrador_id,
            orden=body.accion_orden,
            parametros=parametros,
            actor_id=actor_id,
            rol=rol,
            nombre_actor=str(perfil.get("nombre") or ""),
        )
    elif nombre == "crear_tarea_interna":
        resultado = await _ejecutar_tarea_interna(
            pool,
            borrador_id=borrador_id,
            extraccion_id=fila["extraccion_id"],
            orden=body.accion_orden,
            parametros=parametros,
            actor_id=actor_id,
            rol=rol,
            nombre_actor=str(perfil.get("nombre") or ""),
        )
    else:  # pragma: no cover - guardado por ACCIONES_CONECTADAS
        raise HTTPException(status_code=501, detail="accion sin ejecutor")

    async with pool.acquire() as conn:
        async with conn.transaction():
            intento = await conn.fetchval(
                """
                SELECT COALESCE(MAX(intento_num), 0) + 1
                  FROM cerebro_ejecuciones
                 WHERE borrador_id = $1::uuid AND orden_ejecucion = $2
                """,
                borrador_id,
                body.accion_orden,
            )
            ejecucion = await conn.fetchrow(
                """
                INSERT INTO cerebro_ejecuciones (
                    borrador_id, orden_ejecucion, intento_num, accion_nombre,
                    request_id_custodio, parametros_ejecutados_json, estado,
                    entidad_destino_tabla, entidad_destino_id, error_mensaje
                ) VALUES (
                    $1::uuid, $2, $3, $4, $5, $6::jsonb, $7, $8, $9::uuid, $10
                )
                RETURNING id::text AS id
                """,
                borrador_id,
                body.accion_orden,
                int(intento or 1),
                nombre,
                f"cerebro:{borrador_id}:{body.accion_orden}:{int(intento or 1)}",
                json.dumps(parametros, ensure_ascii=False),
                "EXITOSO" if resultado.estado == "OK" else "FALLIDO",
                (
                    "gato_recordatorios"
                    if nombre == "crear_tarea_recordatorio"
                    else "cerebro_tareas_internas"
                )
                if resultado.estado == "OK"
                else None,
                (resultado.datos or {}).get("id"),
                None if resultado.estado == "OK" else (resultado.nota or "")[:2000],
            )

            estado_borrador = fila["estado"]
            if resultado.estado == "OK":
                exitosas = await conn.fetchval(
                    """
                    SELECT COUNT(DISTINCT orden_ejecucion)
                      FROM cerebro_ejecuciones
                     WHERE borrador_id = $1::uuid AND estado = 'EXITOSO'
                    """,
                    borrador_id,
                )
                if int(exitosas or 0) >= len(acciones):
                    estado_borrador = "EJECUTADO"
                await conn.execute(
                    """
                    UPDATE cerebro_borradores
                       SET confirmado_por = COALESCE(confirmado_por, $2),
                           confirmado_en = COALESCE(confirmado_en, now()),
                           lock_version = lock_version + 1,
                           estado = $3
                     WHERE id = $1::uuid
                    """,
                    borrador_id,
                    actor_id,
                    estado_borrador,
                )

    if resultado.estado != "OK":
        raise HTTPException(
            status_code=422,
            detail={
                "code": resultado.estado,
                "message": resultado.nota or "no se pudo ejecutar la accion",
                "ejecucion_id": ejecucion["id"],
            },
        )

    return {
        "borrador_id": borrador_id,
        "accion_orden": body.accion_orden,
        "accion_nombre": nombre,
        "repetido": False,
        "ejecucion_id": ejecucion["id"],
        "estado": resultado.estado,
        "nota": resultado.nota,
        "datos": resultado.datos,
        "estado_borrador": estado_borrador,
    }


async def _ejecutar_tarea(
    request: Request,
    pool: asyncpg.Pool,
    *,
    borrador_id: str,
    orden: int,
    parametros: dict[str, Any],
    actor_id: str,
    rol: str,
    nombre_actor: str,
):
    """Crea el recordatorio con la ratificacion que ya dio el humano."""
    sandbox = bool(getattr(request.app.state.settings, "sandbox_mode", True))
    actor = Actor(
        nombre=nombre_actor or rol,
        rol=rol,
        actor_id=actor_id,
        modo_envio="SANDBOX" if sandbox else "",
    )
    clave = hashlib.sha256(
        f"cerebro:{borrador_id}:{orden}".encode("utf-8")
    ).hexdigest()
    return await recordatorios.crear(
        Bibliotecario(pool),
        actor=actor,
        destinatario=str(parametros.get("destinatario") or ""),
        mensaje=str(parametros.get("mensaje") or ""),
        cuando=str(parametros.get("cuando") or "ahora"),
        adjuntar_factura=bool(parametros.get("adjuntar_factura")),
        confirmado_por=actor_id,
        clave_externa=clave,
    )


async def _ejecutar_tarea_interna(
    pool: asyncpg.Pool,
    *,
    borrador_id: str,
    extraccion_id: str | None,
    orden: int,
    parametros: dict[str, Any],
    actor_id: str,
    rol: str,
    nombre_actor: str,
):
    """Deja la instrucción en el panel: nace NOTIFICADA y el reloj corre."""
    clave = hashlib.sha256(
        f"cerebro:{borrador_id}:{orden}".encode("utf-8")
    ).hexdigest()
    return await crear_tarea_interna(
        pool,
        instruccion=str(parametros.get("instruccion") or ""),
        asignado_rol=str(parametros.get("asignado_rol") or "SECRETARIA"),
        asignado_a=parametros.get("asignado_a"),
        creado_por=nombre_actor or rol,
        rol_actor=rol,
        actor_id=actor_id or None,
        clave_externa=clave,
        extraccion_id=extraccion_id,
        borrador_id=borrador_id,
        ficha=parametros.get("ficha") or {},
        prioridad=str(parametros.get("prioridad") or "NORMAL"),
        metadatos={"cuando": parametros.get("cuando")},
    )


# ---------------------------------------------------------------------------
# Tareas internas: el seguimiento que vive en el CRM (no en WhatsApp)
# ---------------------------------------------------------------------------
@router.get("/tareas-internas")
async def tareas_internas(
    request: Request, estado: str | None = None, limite: int = 50
) -> dict[str, Any]:
    """Lista las tareas internas con sus relojes ya calculados."""
    await exigir_modulo(request, "cerebro")
    pool = _pool(request)
    if estado:
        estados = tuple(
            parte.strip().upper() for parte in estado.split(",") if parte.strip()
        )
        desconocidos = [e for e in estados if e not in ESTADOS_TAREA]
        if desconocidos:
            raise HTTPException(
                status_code=422,
                detail=f"estado invalido: {', '.join(desconocidos)}",
            )
    else:
        estados = ESTADOS_TAREA_ABIERTOS
    tareas = await listar_tareas_internas(pool, estados=estados, limite=limite)
    return {"tareas": tareas, "total": len(tareas)}


@router.post("/tareas-internas/{tarea_id}/resolver")
async def resolver_tarea(
    request: Request, tarea_id: str, body: ResolverTareaIn
) -> dict[str, Any]:
    """Resuelta (se hizo) o justificada (no hacía falta), con su nota."""
    perfil = await exigir_modulo(request, "cerebro", mutacion=True)
    try:
        uuid.UUID(tarea_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="tarea_id invalido") from exc
    pool = _pool(request)
    try:
        return await resolver_tarea_interna(
            pool,
            tarea_id,
            resolucion=body.resolucion,
            nota=body.nota,
            actor_id=str(perfil.get("id") or "") or None,
            actor_nombre=str(perfil.get("nombre") or "desconocido"),
            rol_actor=str(perfil.get("rol_base") or "SECRETARIA"),
            metadatos=body.metadatos,
        )
    except TareaNoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TransicionInvalida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TareaInternaInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/tareas-internas/{tarea_id}/registrar")
async def registrar_tarea(
    request: Request, tarea_id: str, body: RegistrarTareaIn
) -> dict[str, Any]:
    """Cierra con metadatos: sin metadatos no se registra."""
    perfil = await exigir_modulo(request, "cerebro", mutacion=True)
    try:
        uuid.UUID(tarea_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="tarea_id invalido") from exc
    pool = _pool(request)
    try:
        return await registrar_tarea_interna(
            pool,
            tarea_id,
            nota=body.nota,
            metadatos=body.metadatos,
            actor_id=str(perfil.get("id") or "") or None,
            actor_nombre=str(perfil.get("nombre") or "desconocido"),
            rol_actor=str(perfil.get("rol_base") or "SECRETARIA"),
        )
    except TareaNoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TransicionInvalida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TareaInternaInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/tareas-internas/{tarea_id}/vista")
async def ver_tarea(request: Request, tarea_id: str) -> dict[str, Any]:
    """Registra que la persona abrió el detalle. No es acuse de recibo."""
    perfil = await exigir_modulo(request, "cerebro")
    try:
        uuid.UUID(tarea_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="tarea_id invalido") from exc
    try:
        return await marcar_vista(
            _pool(request),
            tarea_id,
            actor_id=str(perfil.get("id") or "") or None,
            actor_nombre=str(perfil.get("nombre") or "desconocido"),
            rol_actor=str(perfil.get("rol_base") or "SECRETARIA"),
        )
    except TareaNoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tareas-internas/{tarea_id}/acusar")
async def acusar_tarea(request: Request, tarea_id: str) -> dict[str, Any]:
    """Confirma que recibió el encargo. No significa que lo hizo."""
    perfil = await exigir_modulo(request, "cerebro", mutacion=True)
    try:
        uuid.UUID(tarea_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="tarea_id invalido") from exc
    try:
        return await acusar_tarea_interna(
            _pool(request),
            tarea_id,
            actor_id=str(perfil.get("id") or "") or None,
            actor_nombre=str(perfil.get("nombre") or "desconocido"),
            rol_actor=str(perfil.get("rol_base") or "SECRETARIA"),
        )
    except TareaNoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TransicionInvalida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/tareas-internas/{tarea_id}/escalar")
async def escalar_tarea(
    request: Request, tarea_id: str, body: EscalarTareaIn
) -> dict[str, Any]:
    """Marca una tarea vencida para un supervisor y sube la prioridad."""
    perfil = await exigir_modulo(request, "cerebro", mutacion=True)
    if str(perfil.get("rol_base") or "").upper() != "SUPERADMIN":
        raise HTTPException(
            status_code=403, detail="solo un superadmin puede escalar una tarea"
        )
    try:
        uuid.UUID(tarea_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="tarea_id invalido") from exc
    try:
        return await escalar_tarea_interna(
            _pool(request),
            tarea_id,
            motivo=body.motivo,
            actor_id=str(perfil.get("id") or "") or None,
            actor_nombre=str(perfil.get("nombre") or "desconocido"),
            rol_actor="SUPERADMIN",
        )
    except TareaNoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TransicionInvalida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TareaInternaInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/vocabulario/retirar")
async def retirar_aprendizaje(
    request: Request, body: RetirarVocabularioIn
) -> dict[str, Any]:
    """Retira una asociación aprendida equivocada, con su motivo."""
    perfil = await exigir_modulo(request, "cerebro", mutacion=True)
    try:
        return await retirar_vocabulario(
            _pool(request),
            clave=body.clave,
            valor_anterior=body.valor_anterior,
            valor_nuevo=body.valor_nuevo,
            motivo=body.motivo,
            retirado_por=str(perfil.get("nombre") or "desconocido"),
            rol_base=str(perfil.get("rol_base") or "SECRETARIA"),
        )
    except TareaInternaInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

