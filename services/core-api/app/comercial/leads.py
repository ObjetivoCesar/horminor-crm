"""Modulo comercial: leads y citas. Independiente del canal.

Reglas:
- El origen (WHATSAPP, GATO, PANEL) no cambia las reglas.
- La fecha de negocio sale de ``app.tiempo`` (America/Guayaquil).
- Nada se inventa: los plazos sin definir quedan NULL.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import asyncpg

from .. import tiempo


def normalizar(texto: str | None) -> str:
    """Minusculas, sin tildes y con espacios simples (para patrones)."""
    crudo = str(texto or "").strip().lower()
    sin = "".join(
        c for c in unicodedata.normalize("NFD", crudo)
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sin)


def telefono(valor: str | None) -> str:
    digitos = re.sub(r"\D", "", str(valor or ""))
    if not digitos:
        raise ValueError("el lead necesita un telefono valido")
    return digitos


def coincide(texto: str | None, patrones: list[str] | None) -> bool:
    """True si alguna frase aparece como palabra/frase completa."""
    limpio = normalizar(texto)
    if not limpio:
        return False
    for patron in patrones or []:
        frase = normalizar(patron)
        if frase and frase in limpio:
            return True
    return False


async def reglas_activas(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    filas = await pool.fetch(
        """
        SELECT clave, intencion, patrones, estado_destino, motivo,
               gracia_dias, intentos
          FROM lead_reglas_caida
         WHERE activo
         ORDER BY clave
        """
    )
    return [dict(fila) for fila in filas]


def elegir_regla(texto: str, reglas: list[dict[str, Any]]) -> dict[str, Any] | None:
    for regla in reglas:
        patrones = regla.get("patrones") or []
        if isinstance(patrones, str):
            import json

            patrones = json.loads(patrones)
        if coincide(texto, patrones):
            return regla
    return None


async def evento(
    pool: asyncpg.Pool, lead_id: str, tipo: str, detalle: dict[str, Any], actor: str | None = None
) -> None:
    await pool.execute(
        """
        INSERT INTO lead_eventos (lead_id, tipo, detalle, actor)
        VALUES ($1::uuid, $2, $3::jsonb, $4)
        """,
        lead_id,
        tipo,
        __import__("json").dumps(detalle, ensure_ascii=False),
        actor,
    )


ESTADOS = (
    "CONTACTO",
    "LEAD",
    "CALIFICADO",
    "EN_ESPERA",
    "HANDOFF",
    "CAIDO",
    "CONVERTIDO",
)

# Un lead que vuelve a escribir o al que la empresa responde deja de estar caido.
_REVIVIBLES = ("CAIDO", "EN_ESPERA")


def estado_tras_intencion(
    estado_actual: str, regla: dict[str, Any] | None
) -> tuple[str, str | None, int | None]:
    """Estado, motivo y dias de gracia que produce un mensaje del lead.

    La regla de caida manda. Sin regla, un lead caido o en espera revive a
    LEAD; un CONTACTO sigue siendo CONTACTO (todavia no hubo respuesta de la
    empresa).
    """
    if regla is not None:
        return (
            str(regla["estado_destino"]),
            regla.get("motivo"),
            regla.get("gracia_dias"),
        )
    if estado_actual in _REVIVIBLES:
        return "LEAD", None, None
    return estado_actual, None, None


async def crear_o_reutilizar(
    pool: asyncpg.Pool,
    *,
    telefono_lead: str,
    origen: str = "WHATSAPP",
    nombre: str | None = None,
) -> dict[str, Any]:
    tel = telefono(telefono_lead)
    fila = await pool.fetchrow(
        """
        SELECT id::text AS id, telefono_e164, nombre, origen, estado,
               motivo_caida, recontactar_at, intentos_recontacto,
               created_at, updated_at
          FROM leads WHERE telefono_e164 = $1
        """,
        tel,
    )
    if fila is not None:
        datos = dict(fila)
        actualizado = await pool.fetchrow(
            """
            UPDATE leads
               SET nombre              = COALESCE(nombre, $2),
                   ultimo_contacto_at  = now(),
                   updated_at          = now()
             WHERE id = $1::uuid
            RETURNING id::text AS id, telefono_e164, nombre, origen, estado,
                      motivo_caida, recontactar_at, intentos_recontacto,
                      created_at, updated_at
            """,
            datos["id"],
            nombre,
        )
        datos = dict(actualizado or datos)
        await evento(
            pool,
            datos["id"],
            "REINGRESO",
            {"origen": origen, "estado": datos.get("estado")},
        )
        return {**datos, "creado": False}
    fila = await pool.fetchrow(
        """
        INSERT INTO leads (telefono_e164, nombre, origen, estado, ultimo_contacto_at)
        VALUES ($1, $2, $3, 'CONTACTO', now())
        RETURNING id::text AS id, telefono_e164, nombre, origen, estado,
                  motivo_caida, recontactar_at, intentos_recontacto,
                  created_at, updated_at
        """,
        tel,
        nombre,
        origen,
    )
    datos = dict(fila)
    await evento(pool, datos["id"], "CREADO", {"origen": origen})
    return {**datos, "creado": True}


async def registrar_respuesta(
    pool: asyncpg.Pool,
    *,
    lead_id: str,
    texto: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    """Marca que **la empresa** respondio: nace el LEAD.

    El texto que responde la empresa no se interpreta como intencion del lead:
    una frase como «ya tengo listo su pedido» no puede marcar COMPETENCIA.
    La intencion del lead se registra con ``registrar_mensaje``.
    """
    fila = await pool.fetchrow(
        "SELECT id::text AS id, estado FROM leads WHERE id = $1::uuid", lead_id
    )
    if fila is None:
        raise LookupError("lead no encontrado")
    estado = str(fila["estado"])
    if estado == "CONTACTO":
        estado = "LEAD"
    elif estado in _REVIVIBLES:
        estado = "LEAD"
    actualizado = await pool.fetchrow(
        """
        UPDATE leads
           SET estado = $2,
               motivo_caida = CASE WHEN $2 = 'LEAD' THEN NULL ELSE motivo_caida END,
               recontactar_at = CASE WHEN $2 = 'LEAD' THEN NULL ELSE recontactar_at END,
               ultimo_contacto_at = now(),
               updated_at = now()
         WHERE id = $1::uuid
        RETURNING id::text AS id, estado, motivo_caida, recontactar_at
        """,
        lead_id,
        estado,
    )
    await evento(
        pool,
        lead_id,
        "RESPONDIDO",
        {"texto": texto},
        actor,
    )
    return dict(actualizado)


async def registrar_mensaje(
    pool: asyncpg.Pool,
    *,
    lead_id: str,
    texto: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    """Registra un mensaje **del lead** y aplica las reglas de intencion."""
    fila = await pool.fetchrow(
        "SELECT id::text AS id, estado FROM leads WHERE id = $1::uuid", lead_id
    )
    if fila is None:
        raise LookupError("lead no encontrado")
    anterior = str(fila["estado"])
    regla = elegir_regla(texto or "", await reglas_activas(pool))
    estado, motivo, gracia = estado_tras_intencion(anterior, regla)
    recontactar = None
    if gracia is not None:
        from datetime import timedelta

        recontactar = tiempo.ahora() + timedelta(days=int(gracia))
    actualizado = await pool.fetchrow(
        """
        UPDATE leads
           SET estado = $2,
               motivo_caida = $3,
               recontactar_at = $4,
               ultimo_contacto_at = now(),
               updated_at = now()
         WHERE id = $1::uuid
        RETURNING id::text AS id, estado, motivo_caida, recontactar_at
        """,
        lead_id,
        estado,
        motivo,
        recontactar,
    )
    if regla is not None:
        tipo = "INTENCION"
    elif anterior in _REVIVIBLES:
        tipo = "REACTIVADO"
    else:
        tipo = "MENSAJE_ENTRANTE"
    await evento(
        pool,
        lead_id,
        tipo,
        {
            "regla": (regla or {}).get("clave"),
            "texto": texto,
            "estado_anterior": anterior,
            "recontacto_configurado": recontactar is not None,
        },
        actor,
    )
    return dict(actualizado)


async def cambiar_estado(
    pool: asyncpg.Pool,
    *,
    lead_id: str,
    estado: str,
    motivo: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    """Cambio manual de estado: una persona puede revertir lo que propuso el sistema."""
    if estado not in ESTADOS:
        raise ValueError(f"estado invalido: {estado}")
    fila = await pool.fetchrow(
        "SELECT id::text AS id, estado FROM leads WHERE id = $1::uuid", lead_id
    )
    if fila is None:
        raise LookupError("lead no encontrado")
    actualizado = await pool.fetchrow(
        """
        UPDATE leads SET estado = $2, motivo_caida = $3, updated_at = now()
         WHERE id = $1::uuid
        RETURNING id::text AS id, estado, motivo_caida
        """,
        lead_id,
        estado,
        motivo,
    )
    await evento(
        pool,
        lead_id,
        "ESTADO_CAMBIADO",
        {"estado_anterior": str(fila["estado"]), "estado": estado, "motivo": motivo},
        actor,
    )
    return dict(actualizado)


async def buscar(pool: asyncpg.Pool, texto: str) -> dict[str, Any] | None:
    """Busca un lead por nombre o telefono. No inventa: si hay duda, None."""
    objetivo = normalizar(texto)
    if not objetivo:
        return None
    filas = await pool.fetch(
        """
        SELECT id::text AS id, telefono_e164, nombre, estado, origen
          FROM leads
         ORDER BY COALESCE(ultimo_contacto_at, created_at) DESC
        """
    )
    for fila in filas:
        nombre = normalizar(fila["nombre"])
        if nombre and (nombre in objetivo or objetivo in nombre):
            return dict(fila)
    digitos = re.sub(r"\D", "", texto)
    if len(digitos) >= 7:
        for fila in filas:
            if digitos in str(fila["telefono_e164"]):
                return dict(fila)
    return None


async def listar(pool: asyncpg.Pool, estado: str | None = None) -> list[dict[str, Any]]:
    if estado:
        filas = await pool.fetch(
            """
            SELECT id::text AS id, telefono_e164, nombre, origen, estado,
                   motivo_caida, recontactar_at, ultimo_contacto_at
              FROM leads WHERE estado = $1
             ORDER BY COALESCE(ultimo_contacto_at, created_at) DESC
            """,
            estado,
        )
    else:
        filas = await pool.fetch(
            """
            SELECT id::text AS id, telefono_e164, nombre, origen, estado,
                   motivo_caida, recontactar_at, ultimo_contacto_at
              FROM leads
             ORDER BY COALESCE(ultimo_contacto_at, created_at) DESC
            """
        )
    return [dict(fila) for fila in filas]
