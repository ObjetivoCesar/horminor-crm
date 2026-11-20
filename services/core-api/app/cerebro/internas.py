"""Tareas internas: la instrucción que se dicta a alguien del equipo.

Un audio puede decir «que revisen en secretaría cómo van los despachos». No hay
teléfono ni WhatsApp: hay una persona que debe hacer algo. El CRM deja el aviso,
y la tarea se cierra en tres pasos con hora cada uno:

1. **Notificada** — el sistema dejó el aviso en el panel (inicio del reloj).
2. **Resuelta** o **Justificada** — la persona la hizo, o explica por qué no.
3. **Registrada** — el cierre queda con metadatos (referencia, comprobante…).

Con eso se mide cuánto tardó de verdad, sin que nadie tenga que declararlo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

import asyncpg

from ..asistente.fichas import Resultado
from .dinero import sin_tildes

ESTADOS = ("NOTIFICADA", "RESUELTA", "JUSTIFICADA", "REGISTRADA")
ESTADOS_ABIERTOS = ("NOTIFICADA", "RESUELTA", "JUSTIFICADA")
RESOLUCIONES = ("RESUELTA", "JUSTIFICADA")
ROLES_INTERNOS = ("SECRETARIA", "BODEGA", "CONTADORA", "VENDEDOR", "SUPERADMIN")

# Transiciones permitidas. No se salta de NOTIFICADA a REGISTRADA: el registro
# es el cierre de algo que ya se resolvió o justificó.
TRANSICIONES: dict[str, tuple[str, ...]] = {
    "NOTIFICADA": ("RESUELTA", "JUSTIFICADA"),
    "RESUELTA": ("REGISTRADA",),
    "JUSTIFICADA": ("REGISTRADA",),
    "REGISTRADA": (),
}

# Cómo se nombra a cada área en un dictado. Solo alias fuertes: «planta» se dice
# en cualquier conversación de hormigón y no convierte una tarea en interna.
ALIAS_ROL: dict[str, tuple[str, ...]] = {
    "SECRETARIA": ("secretaria", "secretarias", "recepcion"),
    "BODEGA": ("bodega", "bodeguero", "bodeguera"),
    "CONTADORA": ("contadora", "contador", "contabilidad"),
    "VENDEDOR": ("vendedor", "vendedora", "ventas"),
}

# Verbos de encargo: «que revisen», «verifica», «que me confirme». Marcan una
# instrucción interna aunque no se nombre el área.
MARCAS_ENCARGO = (
    "que revisen",
    "que revise",
    "que verifiquen",
    "que verifique",
    "que confirmen",
    "que confirme",
    "que me confirmen",
    "que me confirme",
    "confirmame",
    "confirmenme",
    "confirma con",
    "confirmen con",
    "coordina con",
    "coordinen con",
    "llama a",
    "llamen a",
    "que se encarguen",
    "que se encargue",
    "que pregunten",
    "que pregunte",
    "que averiguen",
    "que averigue",
    "que coordinen",
    "que coordine",
    "que gestionen",
    "que gestione",
    "que despachen",
    "que despache",
    "que llamen",
    "que llame",
    "verifica",
    "revisa",
    "encargate",
    "averigua",
    "revise",
    "revisen",
    "verifique",
    "verifiquen",
    "confirme",
    "confirmen",
    "averigue",
    "averiguen",
    "coordine",
    "coordinen",
    "pregunte",
    "pregunten",
    "llame",
    "llamen",
    "gestione",
    "gestionen",
    "prepare",
    "preparen",
    "cotice",
    "coticen",
    "despache",
    "despachen",
)

# Verbos de envío: piden que un mensaje salga hacia alguien.
MARCAS_ENVIO = (
    "enviale",
    "que le envie",
    "que le envien",
    "mandale",
    "que le mande",
    "escribele",
    "avisale",
    "recordale",
    "recuerdale",
    "notificale",
    "whatsapp",
    "wsp",
    "mensaje a",
    "manda un mensaje",
    "envia un mensaje",
)

# Marcas de que el encargo es urgente. No incluye «ya» ni «ahora» sueltos:
# aparecen en cualquier frase («ya me pagó») y marcarían todo como urgente.
MARCAS_URGENTE = (
    "urgente",
    "inmediatamente",
    "de inmediato",
    "cuanto antes",
    "ya mismo",
    "lo antes posible",
    "sin falta",
)

# Política del sistema (no es un dato de negocio): cuánto se espera antes de
# marcar una tarea como vencida. Es configurable por tarea con `plazo_en`.
PLAZO_NORMAL_HORAS = 24
PLAZO_URGENTE_HORAS = 2


class TareaInternaInvalida(ValueError):
    """El dato no alcanza para crear o cerrar la tarea."""


class TareaNoEncontrada(LookupError):
    """No existe la tarea interna indicada."""


class TransicionInvalida(RuntimeError):
    """El estado actual no permite ese paso."""


@dataclass(frozen=True)
class Asignacion:
    """A quién le toca: un área y, si se dijo, una persona."""

    rol: str
    persona: str | None = None


# ---------------------------------------------------------------------------
# Lectura del dictado (determinística, sin LLM)
# ---------------------------------------------------------------------------
def detectar_rol_interno(texto: str | None) -> str | None:
    """Devuelve el área nombrada en el dictado, o None."""
    plano = f" {sin_tildes(texto or '')} "
    for rol, alias in ALIAS_ROL.items():
        if any(f" {nombre} " in plano for nombre in alias):
            return rol
    return None


def es_instruccion_interna(texto: str | None) -> bool:
    """True si el dictado encarga algo sin decir a qué teléfono mandarlo."""
    plano = sin_tildes(texto or "")
    return any(marca in plano for marca in MARCAS_ENCARGO)


def persona_dictada(nombre: str | None, rol: str | None = None) -> str | None:
    """El nombre propio, salvo que sea solo el nombre del área."""
    if not nombre:
        return None
    limpio = " ".join(nombre.split())
    plano = sin_tildes(limpio)
    if rol and plano in (" ".join(a.split()) for a in ALIAS_ROL.get(rol, ())):
        return None
    return limpio or None


def _encargo_a_area(texto: str, rol: str | None) -> bool:
    """«que secretaría revise» no es un envío aunque diga «avísale»."""
    if not rol:
        return False
    plano = f" {sin_tildes(texto or '')} "
    for alias in ALIAS_ROL.get(rol, ()):
        if f"que {alias} " in plano or f"que la {alias} " in plano:
            return True
    return False


def detectar_intencion_tarea(
    texto: str | None, *, tiene_telefono: bool = False
) -> str | None:
    """¿Julio quiere enviar un mensaje, o quiere que alguien haga algo?

    La intención manda: el teléfono es solo un límite de capacidad, no la
    decisión. Devuelve ENVIAR, DELEGAR o None (no se puede saber).
    """
    plano = sin_tildes(texto or "")
    rol = detectar_rol_interno(texto)
    if _encargo_a_area(plano, rol):
        return "DELEGAR"
    if any(marca in plano for marca in MARCAS_ENVIO):
        # «envíale un mensaje a secretaría» sin número es un aviso interno:
        # no hay a dónde enviarlo y el CRM sí puede dejarlo en el panel.
        if rol is not None and not tiene_telefono:
            return "DELEGAR"
        return "ENVIAR"
    if es_instruccion_interna(texto) or rol is not None:
        return "DELEGAR"
    return None


def detectar_prioridad(texto: str | None) -> str:
    plano = sin_tildes(texto or "")
    if any(marca in plano for marca in MARCAS_URGENTE):
        return "URGENTE"
    return "NORMAL"


def puede_transicionar(actual: str, nueva: str) -> bool:
    return nueva in TRANSICIONES.get(actual, ())


def minutos_entre(desde: datetime | None, hasta: datetime | None) -> int | None:
    if desde is None or hasta is None:
        return None
    return int(round((hasta - desde).total_seconds() / 60))


# ---------------------------------------------------------------------------
# Escritura
# ---------------------------------------------------------------------------
def _jsonb(valor: Any) -> str:
    return json.dumps(valor or {}, ensure_ascii=False, default=str)


async def _resolver_persona(
    conn: asyncpg.Connection, nombre: str | None
) -> str | None:
    """Si el nombre dictado coincide con un usuario del panel, se enlaza.

    Solo cuando hay una coincidencia exacta y única: dos personas con el mismo
    nombre no se adivinan.
    """
    if not nombre:
        return None
    filas = await conn.fetch(
        """
        SELECT id::text AS id
          FROM panel_users_acl
         WHERE lower(nombre) = lower($1)
           AND deleted_at IS NULL
         LIMIT 2
        """,
        nombre,
    )
    if len(filas) == 1:
        return str(filas[0]["id"])
    return None


async def _guardar_evento(
    conn: asyncpg.Connection,
    *,
    tarea_id: str,
    estado: str,
    actor_id: str | None,
    actor_nombre: str,
    rol_actor: str,
    nota: str | None,
    metadatos: Mapping[str, Any] | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO cerebro_tareas_internas_eventos (
            tarea_id, estado, actor_id, actor_nombre, rol_actor, nota, metadatos
        ) VALUES ($1::uuid, $2, $3::uuid, $4, $5, $6, $7::jsonb)
        """,
        tarea_id,
        estado,
        actor_id or None,
        actor_nombre,
        rol_actor,
        nota,
        _jsonb(metadatos),
    )


async def crear(
    pool: asyncpg.Pool,
    *,
    instruccion: str,
    asignado_rol: str = "SECRETARIA",
    asignado_a: str | None = None,
    creado_por: str,
    rol_actor: str,
    actor_id: str | None = None,
    clave_externa: str,
    extraccion_id: str | None = None,
    borrador_id: str | None = None,
    cita: str | None = None,
    hablante: str | None = None,
    metadatos: Mapping[str, Any] | None = None,
    ficha: Mapping[str, Any] | None = None,
    prioridad: str = "NORMAL",
    plazo_en: datetime | None = None,
) -> Resultado:
    """Deja el aviso en el panel. Idempotente por `clave_externa`.

    Nace NOTIFICADA (el sistema dejó el aviso). Vista y acuse son actos
    posteriores de una persona y se registran aparte.
    """
    texto = " ".join(str(instruccion or "").split())
    if len(texto) < 5:
        return Resultado(
            consulta_id="cerebro.tarea_interna",
            estado="FALTA_PARAMETRO",
            parametro_faltante="instruccion",
            nota="La instruccion esta vacia; no se inventa una tarea.",
        )
    rol = (asignado_rol or "SECRETARIA").strip().upper()
    if rol not in ROLES_INTERNOS:
        raise TareaInternaInvalida(f"rol interno desconocido: {asignado_rol}")
    persona = persona_dictada(asignado_a, rol)
    prioridad_final = (prioridad or "NORMAL").strip().upper()
    if prioridad_final not in ("NORMAL", "URGENTE"):
        raise TareaInternaInvalida(f"prioridad desconocida: {prioridad}")
    vence = plazo_en or (
        datetime.now(timezone.utc)
        + timedelta(
            hours=(
                PLAZO_URGENTE_HORAS
                if prioridad_final == "URGENTE"
                else PLAZO_NORMAL_HORAS
            )
        )
    )

    async with pool.acquire() as conn:
        async with conn.transaction():
            persona_id = await _resolver_persona(conn, persona)
            fila = await conn.fetchrow(
                """
                INSERT INTO cerebro_tareas_internas (
                    clave_externa, instruccion, asignado_rol, asignado_a,
                    asignado_a_id, extraccion_id, borrador_id, cita, hablante,
                    creado_por, metadatos, prioridad, plazo_en
                ) VALUES (
                    $1, $2, $3, $4, $5::uuid, $6::uuid, $7::uuid, $8, $9,
                    $10, $11::jsonb, $12, $13
                )
                ON CONFLICT (clave_externa) DO NOTHING
                RETURNING id::text AS id
                """,
                clave_externa,
                texto,
                rol,
                persona,
                persona_id,
                extraccion_id or None,
                borrador_id or None,
                cita,
                hablante,
                creado_por,
                _jsonb(
                    {
                        "canal": "PANEL",
                        "borrador_id": borrador_id,
                        "extraccion_id": extraccion_id,
                        "ficha": dict(ficha or {}),
                        **(metadatos or {}),
                    }
                ),
                prioridad_final,
                vence,
            )
            if fila is None:
                existente = await conn.fetchrow(
                    """
                    SELECT id::text AS id, estado
                      FROM cerebro_tareas_internas
                     WHERE clave_externa = $1
                    """,
                    clave_externa,
                )
                return Resultado(
                    consulta_id="cerebro.tarea_interna",
                    estado="OK",
                    datos={
                        "id": existente["id"],
                        "estado": existente["estado"],
                        "repetido": True,
                    },
                    nota=(
                        "Esa instruccion ya estaba registrada; no se duplico."
                    ),
                )

            tarea_id = str(fila["id"])
            await _guardar_evento(
                conn,
                tarea_id=tarea_id,
                estado="NOTIFICADA",
                actor_id=actor_id,
                actor_nombre=creado_por,
                rol_actor=rol_actor,
                nota="Aviso dejado en el panel al confirmar el borrador.",
                metadatos={"canal": "PANEL"},
            )

    return Resultado(
        consulta_id="cerebro.tarea_interna",
        estado="OK",
        datos={
            "id": tarea_id,
            "estado": "NOTIFICADA",
            "asignado_rol": rol,
            "asignado_a": persona,
            "repetido": False,
        },
        nota=(
            "Encargo confirmado. Se creó la tarea y quedó NOTIFICADA en el "
            f"panel para {persona or rol}: el trabajo todavía no está hecho. "
            "Se verá como vista y acusada cuando la reciban, y como resuelta "
            "cuando lo terminen."
        ),
    )


async def reprogramar(
    pool: asyncpg.Pool,
    tarea_id: str,
    *,
    plazo_en: datetime,
    actor_id: str | None = None,
    actor_nombre: str,
    rol_actor: str,
    nota: str | None = None,
) -> dict[str, Any]:
    """Mueve el plazo de una tarea interna que sigue abierta."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            fila = await conn.fetchrow(
                """
                SELECT id::text AS id, estado, plazo_en
                  FROM cerebro_tareas_internas
                 WHERE id = $1::uuid
                 FOR UPDATE
                """,
                tarea_id,
            )
            if fila is None:
                raise TareaInternaInvalida("tarea interna no encontrada")
            if str(fila["estado"]) not in ("NOTIFICADA",):
                raise TareaInternaInvalida(
                    "solo se mueve una tarea que todavía no se resolvió"
                )
            nueva = await conn.fetchrow(
                """
                UPDATE cerebro_tareas_internas
                   SET plazo_en = $2, actualizado_en = now(),
                       lock_version = lock_version + 1
                 WHERE id = $1::uuid
                RETURNING id::text AS id, instruccion, asignado_rol,
                          asignado_a, estado, prioridad, plazo_en,
                          notificada_en
                """,
                tarea_id,
                plazo_en,
            )
            await _guardar_evento(
                conn,
                tarea_id=tarea_id,
                estado="REPROGRAMADA",
                actor_id=actor_id,
                actor_nombre=actor_nombre,
                rol_actor=rol_actor,
                nota=nota or "Plazo movido desde Gato.",
                metadatos={
                    "antes": fila["plazo_en"].isoformat()
                    if fila["plazo_en"]
                    else None,
                    "despues": plazo_en.isoformat(),
                },
            )
    return dict(nueva)


async def resolver(
    pool: asyncpg.Pool,
    tarea_id: str,
    *,
    resolucion: str,
    nota: str,
    actor_id: str | None = None,
    actor_nombre: str,
    rol_actor: str,
    metadatos: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Marca la tarea como resuelta o justificada. La nota es obligatoria."""
    estado_nuevo = (resolucion or "").strip().upper()
    if estado_nuevo not in RESOLUCIONES:
        raise TareaInternaInvalida(
            "la resolucion debe ser RESUELTA o JUSTIFICADA"
        )
    limpia = " ".join(str(nota or "").split())
    if len(limpia) < 3:
        raise TareaInternaInvalida(
            "hace falta una nota: que se hizo o por que no se hizo"
        )

    async with pool.acquire() as conn:
        async with conn.transaction():
            fila = await conn.fetchrow(
                """
                SELECT id::text AS id, estado, notificada_en
                  FROM cerebro_tareas_internas
                 WHERE id = $1::uuid
                 FOR UPDATE
                """,
                tarea_id,
            )
            if fila is None:
                raise TareaNoEncontrada("tarea interna no encontrada")
            if not puede_transicionar(str(fila["estado"]), estado_nuevo):
                raise TransicionInvalida(
                    f"la tarea esta {fila['estado']}; no se puede pasar a "
                    f"{estado_nuevo}"
                )

            actualizada = await conn.fetchrow(
                """
                UPDATE cerebro_tareas_internas
                   SET estado = $2,
                       resuelta_en = now(),
                       resuelta_por = $3,
                       resolucion = $2,
                       resolucion_nota = $4,
                       acusada_en = COALESCE(acusada_en, now()),
                       acusada_por = COALESCE(acusada_por, $3),
                       metadatos = metadatos || $5::jsonb,
                       actualizado_en = now(),
                       lock_version = lock_version + 1
                 WHERE id = $1::uuid
                RETURNING id::text AS id, estado, notificada_en, resuelta_en
                """,
                tarea_id,
                estado_nuevo,
                actor_nombre,
                limpia,
                _jsonb(metadatos),
            )
            await _guardar_evento(
                conn,
                tarea_id=tarea_id,
                estado=estado_nuevo,
                actor_id=actor_id,
                actor_nombre=actor_nombre,
                rol_actor=rol_actor,
                nota=limpia,
                metadatos=metadatos,
            )

    return {
        "id": actualizada["id"],
        "estado": actualizada["estado"],
        "resuelta_en": actualizada["resuelta_en"].isoformat(),
        "minutos_hasta_resolucion": minutos_entre(
            actualizada["notificada_en"], actualizada["resuelta_en"]
        ),
    }


async def marcar_vista(
    pool: asyncpg.Pool,
    tarea_id: str,
    *,
    actor_id: str | None,
    actor_nombre: str,
    rol_actor: str,
) -> dict[str, Any]:
    """Registra que una persona abrió el detalle. No es acuse de recibo."""
    ya_estaba = False
    async with pool.acquire() as conn:
        async with conn.transaction():
            fila = await conn.fetchrow(
                """
                SELECT id::text AS id, vista_en
                  FROM cerebro_tareas_internas
                 WHERE id = $1::uuid
                 FOR UPDATE
                """,
                tarea_id,
            )
            if fila is None:
                raise TareaNoEncontrada("tarea interna no encontrada")
            ya_estaba = fila["vista_en"] is not None
            if not ya_estaba:
                fila = await conn.fetchrow(
                    """
                    UPDATE cerebro_tareas_internas
                       SET vista_en = now(), vista_por = $2,
                           actualizado_en = now(), lock_version = lock_version + 1
                     WHERE id = $1::uuid
                    RETURNING id::text AS id, vista_en
                    """,
                    tarea_id,
                    actor_nombre,
                )
                await _guardar_evento(
                    conn,
                    tarea_id=tarea_id,
                    estado="VISTA",
                    actor_id=actor_id,
                    actor_nombre=actor_nombre,
                    rol_actor=rol_actor,
                    nota="Abrio el detalle de la tarea.",
                )
    return {
        "id": fila["id"],
        "vista_en": fila["vista_en"].isoformat(),
        "ya_estaba": ya_estaba,
    }


async def acusar(
    pool: asyncpg.Pool,
    tarea_id: str,
    *,
    actor_id: str | None,
    actor_nombre: str,
    rol_actor: str,
) -> dict[str, Any]:
    """La persona confirma que recibió el encargo. No significa que lo hizo."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            fila = await conn.fetchrow(
                """
                SELECT id::text AS id, estado, acusada_en
                  FROM cerebro_tareas_internas
                 WHERE id = $1::uuid
                 FOR UPDATE
                """,
                tarea_id,
            )
            if fila is None:
                raise TareaNoEncontrada("tarea interna no encontrada")
            if fila["acusada_en"] is None:
                if fila["estado"] == "REGISTRADA":
                    raise TransicionInvalida(
                        "la tarea ya esta registrada; no hace falta acusar recibo"
                    )
                fila = await conn.fetchrow(
                    """
                    UPDATE cerebro_tareas_internas
                       SET acusada_en = now(), acusada_por = $2,
                           actualizado_en = now(), lock_version = lock_version + 1
                     WHERE id = $1::uuid
                    RETURNING id::text AS id, acusada_en
                    """,
                    tarea_id,
                    actor_nombre,
                )
                await _guardar_evento(
                    conn,
                    tarea_id=tarea_id,
                    estado="ACUSADA",
                    actor_id=actor_id,
                    actor_nombre=actor_nombre,
                    rol_actor=rol_actor,
                    nota="Acuso recibo del encargo.",
                )
    return {
        "id": fila["id"],
        "acusada_en": fila["acusada_en"].isoformat(),
    }


async def escalar(
    pool: asyncpg.Pool,
    tarea_id: str,
    *,
    motivo: str,
    actor_id: str | None = None,
    actor_nombre: str,
    rol_actor: str,
) -> dict[str, Any]:
    """Marca una tarea vencida para que la vea un supervisor.

    No reasigna ni cierra: deja constancia y sube la prioridad.
    """
    limpio = " ".join(str(motivo or "").split())
    if len(limpio) < 3:
        raise TareaInternaInvalida("la escalada necesita un motivo")
    async with pool.acquire() as conn:
        async with conn.transaction():
            fila = await conn.fetchrow(
                """
                SELECT id::text AS id, estado, escalada_en
                  FROM cerebro_tareas_internas
                 WHERE id = $1::uuid
                 FOR UPDATE
                """,
                tarea_id,
            )
            if fila is None:
                raise TareaNoEncontrada("tarea interna no encontrada")
            if fila["estado"] == "REGISTRADA":
                raise TransicionInvalida(
                    "la tarea ya esta registrada; no se escala"
                )
            if fila["escalada_en"] is not None:
                return {
                    "id": fila["id"],
                    "escalada_en": fila["escalada_en"].isoformat(),
                    "repetido": True,
                }
            fila = await conn.fetchrow(
                """
                UPDATE cerebro_tareas_internas
                   SET escalada_en = now(), escalada_por = $2,
                       prioridad = 'URGENTE',
                       actualizado_en = now(), lock_version = lock_version + 1
                 WHERE id = $1::uuid
                RETURNING id::text AS id, escalada_en
                """,
                tarea_id,
                actor_nombre,
            )
            await _guardar_evento(
                conn,
                tarea_id=tarea_id,
                estado="ESCALADA",
                actor_id=actor_id,
                actor_nombre=actor_nombre,
                rol_actor=rol_actor,
                nota=limpio,
            )
    return {
        "id": fila["id"],
        "escalada_en": fila["escalada_en"].isoformat(),
        "repetido": False,
    }


async def retirar_vocabulario(
    pool: asyncpg.Pool,
    *,
    clave: str,
    valor_anterior: str,
    valor_nuevo: str,
    motivo: str,
    retirado_por: str,
    rol_base: str,
) -> dict[str, Any]:
    """Retira una asociación aprendida equivocada. La corrección no se borra."""
    limpio = " ".join(str(motivo or "").split())
    if len(limpio) < 3:
        raise TareaInternaInvalida("el retiro necesita un motivo")
    if not clave or not valor_anterior or not valor_nuevo:
        raise TareaInternaInvalida("faltan los datos del par a retirar")
    async with pool.acquire() as conn:
        fila = await conn.fetchrow(
            """
            INSERT INTO cerebro_vocabulario_retiros (
                clave, valor_anterior, valor_nuevo, motivo,
                retirado_por, rol_base
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id::text AS id, creado_en
            """,
            clave,
            valor_anterior,
            valor_nuevo,
            limpio,
            retirado_por,
            rol_base,
        )
    return {
        "id": fila["id"],
        "clave": clave,
        "valor_anterior": valor_anterior,
        "valor_nuevo": valor_nuevo,
        "retirado_en": fila["creado_en"].isoformat(),
    }


async def registrar(
    pool: asyncpg.Pool,
    tarea_id: str,
    *,
    nota: str | None = None,
    metadatos: Mapping[str, Any] | None = None,
    actor_id: str | None = None,
    actor_nombre: str,
    rol_actor: str,
) -> dict[str, Any]:
    """Cierra la tarea con metadatos. Sin metadatos no hay registro."""
    limpia = " ".join(str(nota or "").split())
    datos = {k: v for k, v in (metadatos or {}).items() if v not in (None, "")}
    if not limpia and not datos:
        raise TareaInternaInvalida(
            "el registro necesita metadatos: referencia, comprobante o nota"
        )

    async with pool.acquire() as conn:
        async with conn.transaction():
            fila = await conn.fetchrow(
                """
                SELECT id::text AS id, estado, notificada_en
                  FROM cerebro_tareas_internas
                 WHERE id = $1::uuid
                 FOR UPDATE
                """,
                tarea_id,
            )
            if fila is None:
                raise TareaNoEncontrada("tarea interna no encontrada")
            if not puede_transicionar(str(fila["estado"]), "REGISTRADA"):
                raise TransicionInvalida(
                    f"la tarea esta {fila['estado']}; primero hay que "
                    "resolverla o justificarla"
                )

            actualizada = await conn.fetchrow(
                """
                UPDATE cerebro_tareas_internas
                   SET estado = 'REGISTRADA',
                       registrada_en = now(),
                       registrada_por = $2,
                       metadatos = metadatos || $3::jsonb,
                       actualizado_en = now(),
                       lock_version = lock_version + 1
                 WHERE id = $1::uuid
                RETURNING id::text AS id, estado, notificada_en,
                          resuelta_en, registrada_en
                """,
                tarea_id,
                actor_nombre,
                _jsonb({**datos, **({"nota": limpia} if limpia else {})}),
            )
            await _guardar_evento(
                conn,
                tarea_id=tarea_id,
                estado="REGISTRADA",
                actor_id=actor_id,
                actor_nombre=actor_nombre,
                rol_actor=rol_actor,
                nota=limpia or None,
                metadatos=datos,
            )

    return {
        "id": actualizada["id"],
        "estado": actualizada["estado"],
        "registrada_en": actualizada["registrada_en"].isoformat(),
        "minutos_hasta_resolucion": minutos_entre(
            actualizada["notificada_en"], actualizada["resuelta_en"]
        ),
        "minutos_hasta_registro": minutos_entre(
            actualizada["notificada_en"], actualizada["registrada_en"]
        ),
    }


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------
def _fila_a_dict(fila: asyncpg.Record) -> dict[str, Any]:
    datos = dict(fila)
    for clave in (
        "notificada_en",
        "resuelta_en",
        "registrada_en",
        "plazo_en",
        "vista_en",
        "acusada_en",
        "escalada_en",
    ):
        if datos.get(clave) is not None:
            datos[clave] = datos[clave].isoformat()
    metadatos = datos.get("metadatos")
    if isinstance(metadatos, str):
        try:
            datos["metadatos"] = json.loads(metadatos)
        except ValueError:
            datos["metadatos"] = {}
    return datos


_CAMPOS_TAREA = """
        id::text AS id, instruccion, asignado_rol, asignado_a,
        estado, resolucion, resolucion_nota, prioridad, plazo_en,
        notificada_en, vista_en, acusada_en, escalada_en,
        resuelta_en, registrada_en, minutos_hasta_resolucion,
        minutos_hasta_registro, minutos_abierta, vencida, sin_acuse,
        requiere_escalamiento, metadatos
"""


async def listar(
    pool: asyncpg.Pool,
    *,
    estados: Sequence[str] = ESTADOS_ABIERTOS,
    limite: int = 50,
) -> list[dict[str, Any]]:
    filas = await pool.fetch(
        f"""
        SELECT {_CAMPOS_TAREA}
          FROM v_cerebro_tareas_internas
         WHERE estado = ANY($1::text[])
         ORDER BY
           CASE prioridad WHEN 'URGENTE' THEN 0 ELSE 1 END,
           COALESCE(plazo_en, notificada_en),
           notificada_en
         LIMIT $2
        """,
        list(estados),
        max(1, min(int(limite), 200)),
    )
    return [_fila_a_dict(fila) for fila in filas]


async def obtener(pool: asyncpg.Pool, tarea_id: str) -> dict[str, Any]:
    fila = await pool.fetchrow(
        f"""
        SELECT {_CAMPOS_TAREA}
          FROM v_cerebro_tareas_internas
         WHERE id = $1::uuid
        """,
        tarea_id,
    )
    if fila is None:
        raise TareaNoEncontrada("tarea interna no encontrada")
    return _fila_a_dict(fila)
