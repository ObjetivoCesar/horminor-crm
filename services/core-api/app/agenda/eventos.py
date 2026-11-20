"""Agenda visual: una sola lectura para las pestañas del panel.

El calendario no ejecuta nada. WhatsApp, recordatorios y despachos los corre el
backend; aqui solo se reunen cuatro fuentes reales en un formato comun:

- ``mixers``       -> ``dispatch_schedule``
- ``recordatorios``-> ``gato_recordatorios``
- ``julio``        -> ``citas``
- ``equipo``       -> ``cerebro_tareas_internas`` (por plazo, o por aviso)

Reglas:
- La zona de la agenda es ``America/Guayaquil``. Las columnas timestamptz se
  convierten en SQL; no se hace aritmetica de fechas en el navegador.
- Nada se inventa: si una fila no trae titulo o detalle, queda vacio.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

import asyncpg

from .service import PostgresAgendaStore

ZONA = "America/Guayaquil"

TIPOS: tuple[str, ...] = ("mixers", "recordatorios", "julio", "equipo")

# Que modulo del panel habilita cada pestaña. Basta uno de ellos.
MODULOS_POR_TIPO: dict[str, tuple[str, ...]] = {
    "mixers": ("agenda_despachos", "secretaria_ventanilla"),
    "recordatorios": ("cerebro", "secretaria_ventanilla"),
    "julio": ("clientes_cartera", "cotizaciones"),
    "equipo": ("cerebro", "secretaria_ventanilla"),
}


def _texto(valor: Any) -> str | None:
    if valor is None:
        return None
    texto = " ".join(str(valor).split())
    return texto or None


def _hora(valor: Any) -> str | None:
    if valor is None:
        return None
    return str(valor)[:5]


def _evento(
    *,
    identificador: Any,
    tipo: str,
    fecha: Any,
    hora: Any,
    titulo: str | None,
    detalle: str | None,
    estado: str | None,
    cliente: str | None = None,
    referencia: str | None = None,
    color: str | None = None,
) -> dict[str, Any]:
    return {
        "id": str(identificador),
        "tipo": tipo,
        "fecha": str(fecha)[:10],
        "hora": _hora(hora),
        "titulo": _texto(titulo) or "Sin titulo",
        "detalle": _texto(detalle),
        "estado": (str(estado or "").strip().upper() or None),
        "cliente": _texto(cliente),
        "referencia": _texto(referencia),
        "color": color,
        "zona": ZONA,
    }


async def _mixers(
    pool: asyncpg.Pool, desde: date, hasta: date
) -> list[dict[str, Any]]:
    filas = await PostgresAgendaStore(pool).listar(desde, hasta)
    eventos: list[dict[str, Any]] = []
    for fila in filas:
        piezas = [
            f"{fila['volumen_m3']:g} m3" if fila.get("volumen_m3") else None,
            fila.get("receta_codigo"),
            fila.get("direccion_obra"),
        ]
        detalle = " · ".join(str(p) for p in piezas if p) or None
        eventos.append(
            _evento(
                identificador=fila["id"],
                tipo="mixers",
                fecha=fila["fecha_entrega"],
                hora=fila.get("hora_inicio"),
                titulo=f"{fila.get('mixer_codigo') or 'Mixer'} · {fila.get('cliente') or 'Sin cliente'}",
                detalle=detalle,
                estado=fila.get("estado"),
                cliente=fila.get("cliente"),
                referencia=fila.get("order_numero"),
            )
        )
    return eventos


async def _recordatorios(
    pool: asyncpg.Pool, desde: date, hasta: date
) -> list[dict[str, Any]]:
    filas = await pool.fetch(
        """
        SELECT r.id, r.destinatario_nombre, r.telefono, r.mensaje, r.estado,
               r.origen_destino, c.nombre AS cliente,
               (r.programado_at AT TIME ZONE $3)::date AS fecha,
               to_char(r.programado_at AT TIME ZONE $3, 'HH24:MI') AS hora
          FROM gato_recordatorios r
          LEFT JOIN clients c ON c.id = r.cliente_id
         WHERE (r.programado_at AT TIME ZONE $3)::date BETWEEN $1 AND $2
         ORDER BY r.programado_at, r.destinatario_nombre
        """,
        desde,
        hasta,
        ZONA,
    )
    return [
        _evento(
            identificador=fila["id"],
            tipo="recordatorios",
            fecha=fila["fecha"],
            hora=fila["hora"],
            titulo=f"Recordatorio a {fila['destinatario_nombre'] or fila['telefono']}",
            detalle=fila["mensaje"],
            estado=fila["estado"],
            cliente=fila["cliente"],
            referencia=fila["telefono"],
        )
        for fila in filas
    ]


async def _julio(
    pool: asyncpg.Pool, desde: date, hasta: date
) -> list[dict[str, Any]]:
    filas = await pool.fetch(
        """
        SELECT c.id, c.tipo, c.fecha, to_char(c.hora_inicio, 'HH24:MI') AS hora,
               c.duracion_min, c.estado, c.notas, c.solicitada_por,
               COALESCE(cl.nombre, l.nombre, l.telefono_e164) AS contacto
          FROM citas c
          LEFT JOIN clients cl ON cl.id = c.cliente_id
          LEFT JOIN leads l ON l.id = c.lead_id
         WHERE c.fecha BETWEEN $1 AND $2
           AND c.estado <> 'CANCELADA'
         ORDER BY c.fecha, c.hora_inicio
        """,
        desde,
        hasta,
    )
    return [
        _evento(
            identificador=fila["id"],
            tipo="julio",
            fecha=fila["fecha"],
            hora=fila["hora"],
            titulo=f"{str(fila['tipo']).title()} · {fila['contacto'] or 'Agenda de Julio'}",
            detalle=fila["notas"] or (
                f"Solicitada por {fila['solicitada_por']}"
                if fila["solicitada_por"]
                else None
            ) if str(fila["estado"]).upper() != "REAGENDADA" else "Cita reprogramada.",
            estado=fila["estado"],
            cliente=fila["contacto"],
            referencia=f"{fila['duracion_min']} min",
        )
        for fila in filas
    ]


async def _equipo(
    pool: asyncpg.Pool, desde: date, hasta: date
) -> list[dict[str, Any]]:
    filas = await pool.fetch(
        """
        SELECT id, instruccion, asignado_rol, asignado_a, estado, prioridad,
               (COALESCE(plazo_en, notificada_en) AT TIME ZONE $3)::date AS fecha,
               to_char(COALESCE(plazo_en, notificada_en) AT TIME ZONE $3, 'HH24:MI') AS hora
          FROM v_cerebro_tareas_internas
         WHERE (COALESCE(plazo_en, notificada_en) AT TIME ZONE $3)::date
               BETWEEN $1 AND $2
         ORDER BY COALESCE(plazo_en, notificada_en)
        """,
        desde,
        hasta,
        ZONA,
    )
    return [
        _evento(
            identificador=fila["id"],
            tipo="equipo",
            fecha=fila["fecha"],
            hora=fila["hora"],
            titulo=fila["instruccion"],
            detalle=" · ".join(
                str(p)
                for p in (
                    fila["asignado_a"] or fila["asignado_rol"],
                    f"Prioridad {str(fila['prioridad']).lower()}"
                    if fila["prioridad"] == "URGENTE"
                    else None,
                )
                if p
            )
            or None,
            estado=fila["estado"],
            referencia=fila["asignado_rol"],
        )
        for fila in filas
    ]


_FUENTES = {
    "mixers": _mixers,
    "recordatorios": _recordatorios,
    "julio": _julio,
    "equipo": _equipo,
}


async def listar(
    pool: asyncpg.Pool,
    *,
    desde: date,
    hasta: date,
    tipos: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Eventos de los tipos pedidos, ordenados por fecha y hora."""
    eventos: list[dict[str, Any]] = []
    for tipo in tipos:
        fuente = _FUENTES.get(tipo)
        if fuente is None:
            continue
        eventos.extend(await fuente(pool, desde, hasta))
    eventos.sort(key=lambda e: (e["fecha"], e["hora"] or "99:99", e["titulo"]))
    return eventos


def conteo(eventos: list[dict[str, Any]]) -> dict[str, int]:
    totales = {tipo: 0 for tipo in TIPOS}
    for evento in eventos:
        totales[evento["tipo"]] = totales.get(evento["tipo"], 0) + 1
    return totales
