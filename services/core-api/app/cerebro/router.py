"""HTTP del Cerebro: interpretar texto/transcripción y consultar borradores."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime
from typing import Any, Literal, Mapping
from zoneinfo import ZoneInfo

import asyncpg
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..asistente import recordatorios
from ..asistente.bibliotecario import Bibliotecario
from ..asistente.orquestador import Actor
from ..db import setting
from ..m1_whatsapp.bunny import BunnyError, BunnyHttpStorageClient
from ..panel_acl import exigir_modulo
from ..services import media as media_svc
from ..voz import localizar_palabras, normalizar_con_mapa
from . import ejecutores
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
    conversacion_id: str | None = Field(default=None, max_length=80)
    # Dictados anteriores de la misma conversacion. El Cerebro los usa como
    # contexto para que «me acaba de dar el efectivo» se refiera al cliente y
    # monto que se acaban de dictar, no a una operacion nueva.
    contexto: str | None = Field(default=None, max_length=8000)


class ConfirmarIn(BaseModel):
    accion_orden: int = Field(ge=1)
    # Archivos (media_assets) que se mueven a la carpeta del cliente al confirmar.
    archivos: list[str] = Field(default_factory=list, max_length=50)
    # Texto que el humano autoriza para el recordatorio. Si la acción nace con
    # `mensaje_por_confirmar`, sin esto no se programa nada: la instrucción
    # dictada no es el mensaje que lee el destinatario.
    mensaje_final: str | None = Field(default=None, max_length=2000)
    # Confirmación explícita de envío inmediato cuando el dictado no dio hora.
    enviar_ahora: bool = False


class CorregirIn(BaseModel):
    clave: str = Field(min_length=3, max_length=80)
    valor: Any
    tipo: str | None = Field(default=None, max_length=12)
    # Si el dictado trae varios encargos y la clave se repite, hay que decir
    # cuál se corrige. Sin esto, una corrección podría tocar dos asuntos.
    encargo: int | None = Field(default=None, ge=1)


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
    conversacion_id = (body.conversacion_id or "").strip() or None
    texto = (body.texto or "").strip()
    palabras: list[dict[str, Any]] = []

    if conversacion_id:
        try:
            uuid.UUID(conversacion_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="conversacion_id invalido") from exc
        conv = await pool.fetchrow(
            "SELECT cerrada_en FROM gato_conversaciones WHERE id = $1::uuid",
            conversacion_id,
        )
        if conv is None:
            raise HTTPException(status_code=404, detail="conversacion no encontrada")
        if conv["cerrada_en"] is not None:
            raise HTTPException(
                status_code=409, detail="la conversacion esta cerrada"
            )

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

    # Memoria de la conversacion: los dictados previos se leen como contexto.
    # El texto que se guarda y se compila es el mismo que se interpreta.
    continuacion_desde: int | None = None
    if body.contexto and not transcripcion_id:
        contexto = body.contexto.strip()
        if contexto:
            texto = f"{contexto}\n\n{texto}"
            continuacion_desde = len(contexto) + 2

    inicio = time.perf_counter()
    try:
        resultado = await interpretar(
            pool,
            texto_crudo=texto,
            palabras_crudas=palabras,
            sandbox=bool(getattr(request.app.state.settings, "sandbox_mode", True)),
            continuacion_desde=continuacion_desde,
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
                    version_prompt, sobre_json, latencia_ms, costo_llm_usd,
                    conversacion_id
                ) VALUES (
                    $1::uuid, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, 0, $10::uuid
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
                conversacion_id,
            )
            guardado = await conn.fetchrow(
                """
                INSERT INTO cerebro_borradores (
                    extraccion_id, version, estado, acciones_propuestas_json,
                    preguntas_pendientes_json, condiciones_json, encargos_json,
                    creado_por, conversacion_id
                ) VALUES (
                    $1::uuid, 1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6::jsonb,
                    $7, $8::uuid
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
                json.dumps(
                    [condicion.a_dict() for condicion in borrador.condiciones],
                    ensure_ascii=False,
                ),
                json.dumps(
                    [encargo.a_dict() for encargo in borrador.encargos],
                    ensure_ascii=False,
                ),
                usuario,
                conversacion_id,
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
               b.preguntas_pendientes_json, b.condiciones_json, b.encargos_json,
               b.creado_por, b.creado_en,
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
    datos["condiciones"] = _jsonb(datos.pop("condiciones_json")) or []
    datos["encargos"] = _jsonb(datos.pop("encargos_json")) or []
    cancelados = await pool.fetch(
        """
        SELECT encargo, motivo, decidido_por, creado_en
          FROM cerebro_encargos_decisiones
         WHERE borrador_id = $1::uuid AND decision = 'CANCELADO'
         ORDER BY creado_en
        """,
        borrador_id,
    )
    datos["encargos_cancelados"] = [
        {
            "encargo": fila["encargo"],
            "motivo": fila["motivo"],
            "decidido_por": fila["decidido_por"],
            "creado_en": (
                fila["creado_en"].isoformat() if fila["creado_en"] else None
            ),
        }
        for fila in cancelados
    ]
    # Estado real de cada encargo: una confirmación parcial no puede leerse
    # como si todo el dictado se hubiera ejecutado.
    ejecutadas = await pool.fetch(
        """
        SELECT encargo, COUNT(DISTINCT orden_ejecucion) AS total
          FROM cerebro_ejecuciones
         WHERE borrador_id = $1::uuid AND estado = 'EXITOSO'
         GROUP BY encargo
        """,
        borrador_id,
    )
    hechas = {fila["encargo"]: int(fila["total"]) for fila in ejecutadas}
    cancelados_indices = {fila["encargo"] for fila in cancelados}
    for encargo in datos["encargos"]:
        indice = int(encargo.get("encargo") or 1)
        acciones = encargo.get("acciones") or []
        if indice in cancelados_indices:
            encargo["estado_actual"] = "CANCELADO"
        elif acciones and hechas.get(indice, 0) >= len(acciones):
            encargo["estado_actual"] = "EJECUTADO"
        elif hechas.get(indice, 0) > 0:
            encargo["estado_actual"] = "CONFIRMADO_PARCIAL"
        else:
            encargo["estado_actual"] = encargo.get("estado")
    datos["sobre"] = _jsonb(datos.pop("sobre_json")) or {}
    datos["creado_en"] = (
        datos["creado_en"].isoformat() if datos.get("creado_en") else None
    )
    return datos


# Acciones con ejecutor conectado. Las demas se proponen, pero todavia no se
# pueden ejecutar desde el Cerebro: el endpoint lo dice en vez de simularlo.
ACCIONES_CONECTADAS = (
    "crear_tarea_recordatorio",
    "crear_tarea_interna",
    "crear_cliente",
)


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
            candidatos_visibles = []
            try:
                base = await recompilar(
                    pool,
                    hechos=hechos,
                    intencion=sobre.intencion,
                    sandbox=sandbox,
                    hoy=hoy,
                    texto=normalizar_con_mapa(texto_dictado).texto,
                )
                candidatos_visibles = [
                    h for h in base["hechos"] if h.clave == clave
                ]
            except Exception:  # pragma: no cover - si no se puede, sigue el camino simple
                candidatos_visibles = [
                    h for h in hechos if h.clave == clave
                ]
            candidatos = candidatos_visibles or [
                h for h in hechos if h.clave == clave
            ]
            encargos_de_la_clave = sorted({h.encargo for h in candidatos})
            if body.encargo is None and len(encargos_de_la_clave) > 1:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "ENCARGO_AMBIGUO",
                        "message": (
                            f"«{clave}» aparece en los encargos "
                            + ", ".join(str(e) for e in encargos_de_la_clave)
                            + ". Indica cuál se corrige para no tocar dos asuntos."
                        ),
                        "encargos": encargos_de_la_clave,
                    },
                )
            encargo_objetivo = body.encargo or (
                candidatos[0].encargo if candidatos else 1
            )
            actual = next(
                (
                    h
                    for h in candidatos
                    if h.encargo == encargo_objetivo
                ),
                None,
            )
            tipo = body.tipo or (
                actual.tipo if actual is not None else TIPOS_CONOCIDOS.get(clave, "TEXTO")
            )
            try:
                corregidos = aplicar(
                    hechos,
                    {clave: body.valor},
                    tipos={clave: tipo},
                    hablante=str(perfil.get("rol_base") or "SUPERADMIN"),
                    encargo=encargo_objetivo,
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
                    acciones_propuestas_json, preguntas_pendientes_json,
                    condiciones_json, encargos_json, creado_por
                ) VALUES (
                    $1::uuid, $2::uuid, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb,
                    $8::jsonb, $9
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
                json.dumps(
                    [condicion.a_dict() for condicion in borrador.condiciones],
                    ensure_ascii=False,
                ),
                json.dumps(
                    [encargo.a_dict() for encargo in borrador.encargos],
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
            nuevo_hecho = next(
                h
                for h in corregidos
                if h.clave == clave and h.encargo == encargo_objetivo
            )
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
                    valor_anterior, valor_nuevo, cita, corregido_por, rol_base,
                    encargo
                ) VALUES (
                    $1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9, $10
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
                encargo_objetivo,
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
            "encargo": encargo_objetivo,
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


def validar_confirmacion_recordatorio(
    parametros: Mapping[str, Any],
    *,
    mensaje_final: str | None,
    enviar_ahora: bool,
    actor_id: str,
) -> dict[str, Any]:
    """Exige el texto autorizado y el momento antes de programar.

    Lo dictado describe el encargo; el mensaje que lee la persona y el momento
    del envío los autoriza un humano. Si falta cualquiera de los dos, no se
    programa nada: se devuelve el motivo.
    """
    mensaje = " ".join(str(mensaje_final or "").split())
    if parametros.get("mensaje_por_confirmar") and not mensaje:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "MENSAJE_POR_CONFIRMAR",
                "message": (
                    "Falta el texto exacto del recordatorio. Lo dictado fue "
                    f"«{parametros.get('instruccion')}», que describe el "
                    "encargo; escribe el mensaje que va a leer la persona "
                    "antes de programarlo."
                ),
            },
        )
    if parametros.get("programado_inferido") and not enviar_ahora:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "CONFIRMAR_ENVIO_INMEDIATO",
                "message": (
                    "El dictado no dijo cuándo enviarlo. Confirma que se "
                    "envía ahora o indica la hora antes de programarlo."
                ),
            },
        )
    if not mensaje:
        return dict(parametros)
    return {
        **parametros,
        "mensaje": mensaje,
        "mensaje_por_confirmar": False,
        "mensaje_autorizado_por": actor_id,
    }


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
               preguntas_pendientes_json,
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

    cancelado = await pool.fetchval(
        """
        SELECT 1 FROM cerebro_encargos_decisiones
         WHERE borrador_id = $1::uuid AND encargo = $2
           AND decision = 'CANCELADO'
         LIMIT 1
        """,
        borrador_id,
        int(accion.get("encargo") or 1),
    )
    if cancelado:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ENCARGO_CANCELADO",
                "message": (
                    f"El encargo {int(accion.get('encargo') or 1)} está cancelado: "
                    "no se ejecuta. Los demás encargos del dictado siguen vigentes."
                ),
            },
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
                "repetido": True,
            },
            "ejecutado_en": existente["ejecutado_en"].isoformat(),
        }

    parametros = accion.get("parametros") or {}
    if nombre == "crear_tarea_recordatorio":
        # El dictado propone; el humano autoriza el texto y el momento. Sin
        # eso, la tarea no se programa (no se envía nada por inferencia).
        parametros = validar_confirmacion_recordatorio(
            parametros,
            mensaje_final=body.mensaje_final,
            enviar_ahora=body.enviar_ahora,
            actor_id=actor_id,
        )
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
    elif nombre == "crear_cliente":
        resultado = await ejecutores.crear_cliente_desde_accion(
            pool,
            parametros=parametros,
            borrador_id=borrador_id,
            settings=getattr(request.app.state, "settings", None),
        )
        if resultado.estado == "OK" and body.archivos:
            carpeta = ((resultado.datos or {}).get("carpeta") or {}).get("carpeta")
            if carpeta:
                movidos = await ejecutores.mover_archivos_a_cliente(
                    pool,
                    getattr(request.app.state, "settings", None),
                    carpeta=str(carpeta),
                    media_ids=list(body.archivos),
                    confirmado=True,
                )
                resultado.datos["archivos"] = movidos
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
                    borrador_id, encargo, orden_ejecucion, intento_num,
                    accion_nombre, request_id_custodio,
                    parametros_ejecutados_json, estado, entidad_destino_tabla,
                    entidad_destino_id, error_mensaje
                ) VALUES (
                    $1::uuid, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10::uuid,
                    $11
                )
                RETURNING id::text AS id
                """,
                borrador_id,
                int(accion.get("encargo") or 1),
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
                    if nombre == "crear_tarea_interna"
                    else "clients"
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
        # Un borrador puede ejecutarse por partes: lo confirmado se programó y
        # lo que falta sigue visible. Nunca se presenta como «todo listo».
        "confirmado_parcial": estado_borrador == "REQUIERE_ACLARACION",
        "preguntas_pendientes": len(
            _jsonb(fila["preguntas_pendientes_json"]) or []
        ),
    }


class CancelarEncargoIn(BaseModel):
    motivo: str = Field(min_length=3, max_length=500)


@router.post("/borradores/{borrador_id}/encargos/{encargo}/cancelar")
async def cancelar_encargo(
    request: Request, borrador_id: str, encargo: int, body: CancelarEncargoIn
) -> dict[str, Any]:
    """Cancela un encargo sin tocar los demás asuntos del dictado.

    Si ese encargo ya produjo algo, se distingue: un recordatorio todavía
    PENDIENTE se cancela de verdad; uno ya ENVIADO no se puede cancelar; una
    tarea interna ya creada se cierra desde su propio flujo.
    """
    perfil = await exigir_modulo(request, "cerebro", mutacion=True)
    try:
        uuid.UUID(borrador_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="borrador_id invalido") from exc
    if encargo < 1:
        raise HTTPException(status_code=422, detail="encargo invalido")

    actor_id = str(perfil.get("id") or "").strip()
    if not actor_id:
        raise HTTPException(
            status_code=403,
            detail="Falta el usuario del panel para registrar la cancelación.",
        )
    rol = str(perfil.get("rol_base") or "").strip().upper()
    pool = _pool(request)

    fila = await pool.fetchrow(
        """
        SELECT estado, acciones_propuestas_json, encargos_json
          FROM cerebro_borradores
         WHERE id = $1::uuid
        """,
        borrador_id,
    )
    if fila is None:
        raise HTTPException(status_code=404, detail="borrador no encontrado")
    if fila["estado"] == "EJECUTADO":
        raise HTTPException(
            status_code=409,
            detail="el borrador ya está ejecutado; no hay nada que cancelar",
        )
    acciones = _jsonb(fila["acciones_propuestas_json"]) or []
    del_encargo = [a for a in acciones if int(a.get("encargo") or 1) == encargo]
    if not del_encargo and not any(
        int(e.get("encargo") or 1) == encargo
        for e in (_jsonb(fila["encargos_json"]) or [])
    ):
        raise HTTPException(
            status_code=404, detail=f"el borrador no tiene un encargo {encargo}"
        )

    ya = await pool.fetchval(
        """
        SELECT 1 FROM cerebro_encargos_decisiones
         WHERE borrador_id = $1::uuid AND encargo = $2 AND decision = 'CANCELADO'
        """,
        borrador_id,
        encargo,
    )
    if ya:
        return {
            "borrador_id": borrador_id,
            "encargo": encargo,
            "estado": "CANCELADO",
            "repetido": True,
            "nota": "Ese encargo ya estaba cancelado.",
        }

    ejecuciones = await pool.fetch(
        """
        SELECT id::text AS id, accion_nombre, entidad_destino_tabla,
               entidad_destino_id::text AS entidad_destino_id
          FROM cerebro_ejecuciones
         WHERE borrador_id = $1::uuid AND encargo = $2 AND estado = 'EXITOSO'
        """,
        borrador_id,
        encargo,
    )
    cancelados: list[str] = []
    for ejecucion in ejecuciones:
        tabla = ejecucion["entidad_destino_tabla"]
        destino = ejecucion["entidad_destino_id"]
        if tabla == "gato_recordatorios" and destino:
            estado_recordatorio = await pool.fetchval(
                "SELECT estado FROM gato_recordatorios WHERE id = $1::uuid",
                destino,
            )
            if estado_recordatorio == "ENVIADO":
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "ENCARGO_YA_ENVIADO",
                        "message": (
                            "Ese recordatorio ya se envió: no se puede cancelar. "
                            "Se puede registrar una corrección o una tarea de "
                            "seguimiento, pero el mensaje ya salió."
                        ),
                    },
                )
            if estado_recordatorio in ("PENDIENTE", "BORRADOR", "FALLIDO"):
                await recordatorios.cancelar(
                    Bibliotecario(pool), actor=_actor(perfil), recordatorio_id=destino
                )
                cancelados.append(destino)
        else:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ENCARGO_YA_EJECUTADO",
                    "message": (
                        f"El encargo {encargo} ya generó «{ejecucion['accion_nombre']}». "
                        "Eso se cierra o se revierte desde su propio módulo, no "
                        "cancelando el encargo."
                    ),
                },
            )

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO cerebro_encargos_decisiones (
                    borrador_id, encargo, decision, motivo, decidido_por, rol_base
                ) VALUES ($1::uuid, $2, 'CANCELADO', $3, $4, $5)
                """,
                borrador_id,
                encargo,
                body.motivo.strip(),
                str(perfil.get("nombre") or actor_id),
                rol,
            )

    return {
        "borrador_id": borrador_id,
        "encargo": encargo,
        "estado": "CANCELADO",
        "repetido": False,
        "recordatorios_cancelados": cancelados,
        "nota": (
            "Encargo cancelado. Los demás encargos del dictado siguen vigentes."
        ),
    }


def _actor(perfil: dict[str, Any]) -> Actor:
    return Actor(
        nombre=str(perfil.get("nombre") or perfil.get("rol_base") or "panel"),
        rol=str(perfil.get("rol_base") or "SECRETARIA"),
        actor_id=str(perfil.get("id") or ""),
        modo_envio="",
    )


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
        cifras_autorizadas=parametros.get("cifras_autorizadas") or (),
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


class BunnyOperacionIn(BaseModel):
    """Operacion sobre la carpeta del cliente en Bunny (M3).

    Sin `confirmado`, solo devuelve el plan y los enlaces: el "pasito".
    """

    accion: Literal["listar", "mover", "renombrar", "borrar", "mover_a_cliente"]
    ruta: str = Field(default="", max_length=600)
    destino: str | None = Field(default=None, max_length=600)
    cliente_id: str | None = Field(default=None, max_length=80)
    rutas: list[str] | None = Field(default=None, max_length=50)
    confirmado: bool = False


def _ruta_permitida(prefijo: str, ruta: str) -> bool:
    limpia = (ruta or "").strip()
    if not limpia or limpia.startswith("/") or ".." in limpia.split("/"):
        return False
    marca = (prefijo or "").strip("/")
    return not marca or limpia == marca or limpia.startswith(marca + "/")


class PaqueteAltaIn(BaseModel):
    borrador_id: str = Field(min_length=1, max_length=80)
    media_ids: list[str] = Field(default_factory=list, max_length=50)


@router.get("/alta/media")
async def alta_media(request: Request, limite: int = 20) -> dict[str, Any]:
    """Media reciente para armar el paquete de alta (solo lectura)."""
    await exigir_modulo(request, "cerebro", mutacion=True)
    pool = _pool(request)
    tope = max(1, min(int(limite), 50))
    filas = await pool.fetch(
        """
        SELECT m.id::text AS id, m.tipo, m.nombre_original, m.storage_path,
               m.created_at, c.id::text AS cliente_id, c.nombre AS cliente
          FROM media_assets m
          LEFT JOIN clients c ON c.id = m.cliente_id
         ORDER BY m.created_at DESC
         LIMIT $1
        """,
        tope,
    )
    return {"media": [dict(fila) for fila in filas]}


@router.post("/alta/paquete")
async def paquete_alta(request: Request, body: PaqueteAltaIn) -> dict[str, Any]:
    """Vista previa del alta: cliente + archivos y su destino (sin escribir)."""
    await exigir_modulo(request, "cerebro", mutacion=True)
    pool = _pool(request)
    try:
        uuid.UUID(body.borrador_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="borrador_id invalido") from exc
    fila = await pool.fetchrow(
        "SELECT acciones_propuestas_json FROM cerebro_borradores WHERE id = $1::uuid",
        body.borrador_id,
    )
    if fila is None:
        raise HTTPException(status_code=404, detail="borrador no encontrado")
    acciones = _jsonb(fila["acciones_propuestas_json"]) or []
    accion = next(
        (a for a in acciones if a.get("accion_nombre") == "crear_cliente"), None
    )
    if accion is None:
        raise HTTPException(
            status_code=409, detail="el borrador no tiene un alta de cliente"
        )
    datos = ejecutores.datos_cliente(
        accion.get("parametros") or {}, body.borrador_id
    )
    cfg = await ejecutores.config_bunny(
        pool, getattr(request.app.state, "settings", None)
    )
    prefijo = str((cfg or {}).get("prefijo") or "")
    carpeta = media_svc.carpeta_cliente(
        datos["nombre"], datos["cedula"], None, f"nuevo_{body.borrador_id[:8]}"
    )
    filas = await ejecutores.archivos_de_media(pool, body.media_ids)
    plan = ejecutores.plan_alta(prefijo, carpeta, filas)
    cdn = str((cfg or {}).get("cdn_host") or "").strip().strip("/")
    if cdn:
        for paso in plan:
            paso["url_destino"] = f"https://{cdn}/{paso['destino']}"
    return {
        "cliente": datos,
        "carpeta": carpeta,
        "archivos": plan,
        "aviso": None if cfg else "Bunny no esta configurado; el plan es informativo.",
    }


@router.post("/bunny/operacion")
async def bunny_operacion(request: Request, body: BunnyOperacionIn) -> dict[str, Any]:
    """Manos de Miau en Bunny: listar, mover, renombrar y borrar con vista previa."""
    perfil = await exigir_modulo(request, "cerebro", mutacion=True)
    rol = str(perfil.get("rol_base") or "")
    if rol not in ("SUPERADMIN", "SECRETARIA"):
        raise HTTPException(
            status_code=403, detail="tu perfil no puede operar archivos de Bunny"
        )
    pool = _pool(request)
    cfg = await ejecutores.config_bunny(
        pool, getattr(request.app.state, "settings", None)
    )
    if cfg is None:
        raise HTTPException(status_code=503, detail="Bunny no esta configurado")
    prefijo = str(cfg.get("prefijo") or "")
    if body.accion != "mover_a_cliente" and not _ruta_permitida(prefijo, body.ruta):
        raise HTTPException(
            status_code=422,
            detail=f"la ruta debe estar dentro de {prefijo or 'la zona'}",
        )
    if body.destino is not None and not _ruta_permitida(prefijo, body.destino):
        raise HTTPException(
            status_code=422, detail="la ruta de destino no es valida"
        )

    cliente = BunnyHttpStorageClient(
        storage_zone=str(cfg["storage_zone"]),
        api_key=str(cfg["api_key"]),
        cdn_host=str(cfg["cdn_host"]),
        endpoint=str(cfg.get("endpoint") or "https://storage.bunnycdn.com"),
    )
    cdn = str(cfg["cdn_host"]).strip().strip("/")
    url = lambda ruta: f"https://{cdn}/{ruta.lstrip('/')}"  # noqa: E731

    try:
        if body.accion == "mover_a_cliente":
            if not body.cliente_id or not body.rutas:
                raise HTTPException(
                    status_code=422,
                    detail="indica cliente_id y al menos una ruta",
                )
            fila = await pool.fetchrow(
                """
                SELECT id::text AS id, nombre, cedula, ruc
                  FROM clients WHERE id = $1
                """,
                body.cliente_id,
            )
            if fila is None:
                raise HTTPException(status_code=404, detail="cliente no encontrado")
            carpeta = media_svc.carpeta_cliente(
                str(fila["nombre"] or ""),
                fila["cedula"],
                fila["ruc"],
                str(fila["id"]),
            )
            plan = ejecutores.plan_mover_a_cliente(prefijo, carpeta, body.rutas)
            for paso in plan:
                if not _ruta_permitida(prefijo, paso["origen"]) or not _ruta_permitida(
                    prefijo, paso["destino"]
                ):
                    raise HTTPException(
                        status_code=422,
                        detail=f"ruta fuera de la zona: {paso['origen']}",
                    )
            if not plan:
                raise HTTPException(status_code=422, detail="no hay rutas validas")
            if not body.confirmado:
                return {
                    "accion": "mover_a_cliente",
                    "dry_run": True,
                    "carpeta": carpeta,
                    "plan": [
                        {
                            **paso,
                            "url_origen": url(paso["origen"]),
                            "url_destino": url(paso["destino"]),
                        }
                        for paso in plan
                    ],
                    "nota": "nada se movio; confirma con confirmado=true",
                }
            resultados = []
            for paso in plan:
                try:
                    nueva = await cliente.mover(paso["origen"], paso["destino"])
                    # El enlace del chat vive en media_assets: se mueve con el archivo.
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
            return {
                "accion": "mover_a_cliente",
                "dry_run": False,
                "carpeta": carpeta,
                "resultados": resultados,
            }

        if body.accion == "listar":
            entradas = await cliente.listar(body.ruta)
            return {
                "accion": "listar",
                "ruta": body.ruta,
                "entradas": entradas,
                "url_carpeta": url(body.ruta) + "/",
                "dry_run": False,
            }

        if body.accion in ("mover", "renombrar"):
            if not body.destino:
                raise HTTPException(
                    status_code=422, detail="falta la ruta de destino"
                )
            plan = {
                "origen": body.ruta,
                "destino": body.destino,
                "url_origen": url(body.ruta),
                "url_destino": url(body.destino),
            }
            if not body.confirmado:
                return {
                    "accion": body.accion,
                    "dry_run": True,
                    "plan": plan,
                    "nota": "nada se movio; confirma con confirmado=true",
                }
            nueva = await cliente.mover(body.ruta, body.destino)
            return {
                "accion": body.accion,
                "dry_run": False,
                "ejecutado": True,
                "url": nueva,
                "plan": plan,
            }

        # borrar
        plan = {"ruta": body.ruta, "url": url(body.ruta)}
        if not body.confirmado:
            return {
                "accion": "borrar",
                "dry_run": True,
                "plan": plan,
                "nota": "nada se borro; confirma con confirmado=true",
            }
        hecho = await cliente.borrar(body.ruta)
        return {
            "accion": "borrar",
            "dry_run": False,
            "ejecutado": hecho,
            "existia": hecho,
            "plan": plan,
        }
    except BunnyError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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

