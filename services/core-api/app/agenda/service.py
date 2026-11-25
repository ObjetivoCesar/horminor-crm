"""Servicio unico de agenda de entregas y ocupacion de mixers (v6.2).

Todo el calendario del panel (Dashboard, Secretaria y Planta/Chofer) lee de
aqui y de ``dispatch_schedule``. Los horarios salen de
``system_settings['agenda.parametros']``.

Dos capas:

1. **Calculo puro** (``evaluar_disponibilidad``, ``validar_ventana``): recibe
   las filas ya leidas y devuelve disponibilidad, proxima hora y choques.
2. **Persistencia** (``PostgresAgendaStore``): crea, reagenda, edita y cancela
   filas de ``dispatch_schedule``.

Regla de choque: dos bloques del mismo mixer se solapan si
``inicio_a < fin_b`` y ``inicio_b < fin_a``. Un bloque sin mixer no bloquea
una maquina concreta.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Mapping, Sequence

import asyncpg

from .. import tiempo
from .seguimiento import notificar_secretaria

from .parametros import (
    DEFAULTS,
    dia_laborable,
    normalizar_parametros,
)

MINUTOS_DIA = 24 * 60
ESTADOS_INACTIVOS = ("CANCELADO", "REAGENDADO")


# ---------------------------------------------------------------------------
# Utilidades de hora
# ---------------------------------------------------------------------------
def a_minutos(valor: Any) -> int:
    """Convierte ``time``, ``HH:MM`` o ``HH:MM:SS`` a minutos del dia."""
    if isinstance(valor, time):
        return valor.hour * 60 + valor.minute
    texto = str(valor or "").strip()
    partes = texto.split(":")
    if len(partes) < 2:
        raise ValueError(f"hora invalida: {valor!r}")
    return int(partes[0]) * 60 + int(partes[1])


def a_hhmm(minutos: int) -> str:
    minutos = max(0, min(MINUTOS_DIA - 1, int(minutos)))
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def se_solapan(inicio_a: int, fin_a: int, inicio_b: int, fin_b: int) -> bool:
    return inicio_a < fin_b and inicio_b < fin_a


def _filas_activas(filas: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [
        fila
        for fila in filas
        if str(fila.get("estado") or "").upper() not in ESTADOS_INACTIVOS
        and fila.get("deleted_at") is None
    ]


def mixers_activos(flota: Any) -> list[dict[str, Any]]:
    """Normaliza ``flota.mixers`` (lista JSON) a mixers activos."""
    if isinstance(flota, str):
        try:
            flota = json.loads(flota)
        except ValueError:
            return []
    if not isinstance(flota, list):
        return []
    activos: list[dict[str, Any]] = []
    for item in flota:
        if not isinstance(item, Mapping) or not item.get("activo", True):
            continue
        codigo = str(item.get("codigo") or "").strip()
        if not codigo:
            continue
        activos.append(
            {
                "codigo": codigo,
                "capacidad_m3": item.get("capacidad_m3"),
                "chofer_asignado": item.get("chofer_asignado"),
            }
        )
    return activos


# ---------------------------------------------------------------------------
# Horario de planta
# ---------------------------------------------------------------------------
def validar_ventana(
    *,
    parametros: Mapping[str, Any] | None,
    fecha: date,
    hora: str,
    duracion_min: int,
) -> dict[str, Any] | None:
    """Devuelve un error de horario o ``None`` si la ventana es valida."""
    params = normalizar_parametros(parametros)
    if not dia_laborable(fecha, params):
        return {
            "code": "NON_WORKING_DAY",
            "message": f"{fecha.isoformat()} no es dia laborable de planta",
        }
    inicio = a_minutos(hora)
    fin = inicio + max(30, int(duracion_min or params["duracion_entrega_default_min"]))
    apertura = a_minutos(params["hora_apertura"])
    cierre = a_minutos(params["hora_cierre"])
    if inicio < apertura or fin > cierre:
        return {
            "code": "OUTSIDE_PLANT_HOURS",
            "message": (
                f"la entrega debe quedar entre {params['hora_apertura']} y "
                f"{params['hora_cierre']}"
            ),
            "hora_apertura": params["hora_apertura"],
            "hora_cierre": params["hora_cierre"],
        }
    return None


def _ocupacion_por_mixer(
    filas: Sequence[Mapping[str, Any]],
    fecha: date,
    inicio: int,
    fin: int,
    excluir_id: str | None = None,
) -> dict[str, int]:
    """Devuelve ``{mixer: minuto_hasta_el_que_esta_ocupado}``."""
    ocupados: dict[str, int] = {}
    for fila in _filas_activas(filas):
        if excluir_id and str(fila.get("id")) == str(excluir_id):
            continue
        if str(fila.get("fecha_entrega")) != fecha.isoformat():
            continue
        mixer = str(fila.get("mixer_codigo") or "").strip()
        if not mixer:
            continue
        f_inicio = a_minutos(fila.get("hora_inicio"))
        f_fin = a_minutos(fila.get("hora_fin_estimada"))
        if se_solapan(inicio, fin, f_inicio, f_fin):
            ocupados[mixer] = max(ocupados.get(mixer, 0), f_fin)
    return ocupados


def evaluar_disponibilidad(
    *,
    filas: Sequence[Mapping[str, Any]],
    mixers: Sequence[Mapping[str, Any]],
    fecha: date,
    hora: str,
    duracion_min: int | None = None,
    excluir_id: str | None = None,
    parametros: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Foto de disponibilidad para fecha/hora + proxima ventana libre."""
    params = normalizar_parametros(parametros)
    duracion = max(
        30, int(duracion_min or params["duracion_entrega_default_min"])
    )
    inicio = a_minutos(hora)
    apertura = a_minutos(params["hora_apertura"])
    cierre = a_minutos(params["hora_cierre"])
    paso = max(5, int(params["intervalo_slot_min"] or 30))

    detalle = [
        {
            "codigo": str(mixer["codigo"]),
            "estado": "LIBRE",
            "ocupado_hasta": None,
            "capacidad_m3": mixer.get("capacidad_m3"),
            "chofer_asignado": mixer.get("chofer_asignado"),
        }
        for mixer in mixers
    ]

    base = {
        "fecha": fecha.isoformat(),
        "hora": a_hhmm(inicio),
        "duracion_min": duracion,
        "mixers": detalle,
        "hora_apertura": params["hora_apertura"],
        "hora_cierre": params["hora_cierre"],
        "intervalo_slot_min": paso,
        "dia_laborable": dia_laborable(fecha, params),
    }

    if not base["dia_laborable"]:
        base.update(
            {
                "hay_disponible": False,
                "mixers_libres": [],
                "proxima_hora_disponible": None,
                "mixer_sugerido": None,
                "motivo": "DIA_NO_LABORABLE",
            }
        )
        return base

    if inicio < apertura or inicio + duracion > cierre:
        proxima = a_hhmm(apertura) if inicio < apertura else None
        base.update(
            {
                "hay_disponible": False,
                "mixers_libres": [],
                "proxima_hora_disponible": proxima,
                "mixer_sugerido": None,
                "motivo": "FUERA_DE_HORARIO",
            }
        )
        return base

    ocupados = _ocupacion_por_mixer(
        filas, fecha, inicio, min(cierre, inicio + duracion), excluir_id=excluir_id
    )
    for item in detalle:
        hasta = ocupados.get(item["codigo"])
        if hasta is not None:
            item["estado"] = "OCUPADO"
            item["ocupado_hasta"] = a_hhmm(hasta)

    libres = [item["codigo"] for item in detalle if item["estado"] == "LIBRE"]
    proxima = None
    sugerido = None
    if not libres and mixers:
        candidato = max(inicio, apertura)
        while candidato + duracion <= cierre:
            ocupados_candidato = _ocupacion_por_mixer(
                filas,
                fecha,
                candidato,
                candidato + duracion,
                excluir_id=excluir_id,
            )
            libres_candidato = [
                str(m["codigo"])
                for m in mixers
                if str(m["codigo"]) not in ocupados_candidato
            ]
            if libres_candidato:
                proxima = a_hhmm(candidato)
                sugerido = libres_candidato[0]
                break
            candidato += paso

    base.update(
        {
            "hay_disponible": bool(libres),
            "mixers_libres": libres,
            "proxima_hora_disponible": proxima,
            "mixer_sugerido": sugerido if proxima else (libres[0] if libres else None),
            "motivo": None,
        }
    )
    return base


def conflicto_mixer(
    *,
    filas: Sequence[Mapping[str, Any]],
    mixer_codigo: str | None,
    fecha: date,
    hora: str,
    duracion_min: int | None,
    excluir_id: str | None = None,
    parametros: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Devuelve el bloque que choca con el mixer pedido, o ``None``."""
    params = normalizar_parametros(parametros)
    mixer = str(mixer_codigo or "").strip()
    if not mixer:
        return None
    inicio = a_minutos(hora)
    fin = inicio + max(
        30, int(duracion_min or params["duracion_entrega_default_min"])
    )
    for fila in _filas_activas(filas):
        if excluir_id and str(fila.get("id")) == str(excluir_id):
            continue
        if str(fila.get("fecha_entrega")) != fecha.isoformat():
            continue
        if str(fila.get("mixer_codigo") or "").strip() != mixer:
            continue
        f_inicio = a_minutos(fila.get("hora_inicio"))
        f_fin = a_minutos(fila.get("hora_fin_estimada"))
        if se_solapan(inicio, fin, f_inicio, f_fin):
            return {
                "id": str(fila.get("id")),
                "cliente": fila.get("cliente"),
                "hora_inicio": a_hhmm(f_inicio),
                "hora_fin": a_hhmm(f_fin),
                "estado": fila.get("estado"),
            }
    return None


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------
def _fecha_sql(valor: Any) -> date:
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    return date.fromisoformat(str(valor)[:10])


def _hora_sql(valor: Any) -> time:
    if isinstance(valor, time):
        return valor
    texto = str(valor)
    if len(texto) == 5:
        texto += ":00"
    return time.fromisoformat(texto)


_CAMPOS_EDITABLES = {
    "order_id",
    "cliente_id",
    "planta_id",
    "mixer_codigo",
    "chofer_nombre",
    "receta_codigo",
    "volumen_m3",
    "fecha_entrega",
    "hora_inicio",
    "duracion_estimada_min",
    "direccion_obra",
    "contacto_obra_telefono",
    "estado",
    "motivo_reagendamiento",
    "reagendado_de_id",
    "notificar_whatsapp",
    "notas",
}


def _texto_hora(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, time):
        return valor.strftime("%H:%M")
    return str(valor)[:5]


def _agenda_dict(fila: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(fila["id"]),
        "order_id": str(fila["order_id"]) if fila.get("order_id") else None,
        "order_numero": fila.get("order_numero"),
        "cliente_id": str(fila["cliente_id"]),
        "cliente": fila.get("cliente"),
        "planta_id": str(fila["planta_id"]) if fila.get("planta_id") else None,
        "planta": fila.get("planta"),
        "mixer_codigo": fila.get("mixer_codigo"),
        "chofer_nombre": fila.get("chofer_nombre"),
        "receta_codigo": fila.get("receta_codigo"),
        "volumen_m3": (
            float(fila["volumen_m3"]) if fila.get("volumen_m3") is not None else None
        ),
        "fecha_entrega": str(fila.get("fecha_entrega")),
        "hora_inicio": _texto_hora(fila.get("hora_inicio")),
        "hora_fin_estimada": _texto_hora(fila.get("hora_fin_estimada")),
        "duracion_estimada_min": fila.get("duracion_estimada_min"),
        "direccion_obra": fila.get("direccion_obra"),
        "contacto_obra_telefono": fila.get("contacto_obra_telefono"),
        "estado": fila.get("estado"),
        "motivo_reagendamiento": fila.get("motivo_reagendamiento"),
        "creado_por_rol": fila.get("creado_por_rol"),
        "notificar_whatsapp": fila.get("notificar_whatsapp"),
        "notas": fila.get("notas"),
        "created_at": str(fila.get("created_at")) if fila.get("created_at") else None,
    }


_SELECT = """
    SELECT d.id, d.order_id, o.numero AS order_numero, d.cliente_id,
           c.nombre AS cliente, d.planta_id, p.nombre AS planta,
           d.mixer_codigo, d.chofer_nombre, d.receta_codigo, d.volumen_m3,
           d.fecha_entrega, d.hora_inicio, d.hora_fin_estimada,
           d.duracion_estimada_min, d.direccion_obra,
           d.contacto_obra_telefono, d.estado, d.motivo_reagendamiento,
           d.creado_por_rol, d.notificar_whatsapp, d.notas, d.created_at,
           d.deleted_at
      FROM dispatch_schedule d
      JOIN clients c ON c.id = d.cliente_id
      LEFT JOIN orders o ON o.id = d.order_id
      LEFT JOIN plants p ON p.id = d.planta_id
"""


class ReservaMixerInvalida(ValueError):
    """La franja o las unidades no cubren la entrega solicitada."""


def planificar_cargas(disponibilidad, volumen, unidades=None):
    """Distribuye el volumen entre unidades libres de capacidad conocida."""
    paso = Decimal("0.01")
    if not volumen.is_finite() or volumen <= 0 or volumen != volumen.quantize(paso):
        raise ReservaMixerInvalida("Indica un volumen mayor que cero con hasta dos decimales.")
    candidatas = [
        (item, Decimal(str(item["capacidad_m3"])))
        for item in disponibilidad["mixers"]
        if item["estado"] == "LIBRE" and item.get("capacidad_m3")
    ]
    candidatas.sort(key=lambda pareja: (-pareja[1], pareja[0]["codigo"]))
    cargas = []
    choferes = set()
    for item, capacidad in candidatas:
        chofer = str(item.get("chofer_asignado") or "").strip().casefold()
        if capacidad <= 0 or (chofer and chofer in choferes):
            continue
        if unidades is not None and len(cargas) == unidades:
            break
        restante = unidades - len(cargas) - 1 if unidades is not None else 0
        carga = min(capacidad, volumen - restante * paso)
        if carga <= 0:
            break
        cargas.append((item, carga))
        if chofer:
            choferes.add(chofer)
        volumen -= carga
        if volumen == 0:
            break
    return cargas if volumen == 0 and (unidades is None or len(cargas) == unidades) else []


async def plan_reserva_mixer(db, *, fecha, hora, volumen, unidades=None):
    parametros = normalizar_parametros(await db.fetchval(
        "SELECT value FROM system_settings WHERE key = 'agenda.parametros'"
    ))
    flota = mixers_activos(await db.fetchval(
        "SELECT value FROM system_settings WHERE key = 'flota.mixers'"
    ))
    filas = await PostgresAgendaStore(db).listar(fecha, fecha)
    duracion = parametros["duracion_entrega_default_min"]
    def cargas_a(hora_inicio):
        disponibilidad = evaluar_disponibilidad(
            filas=filas, mixers=flota, fecha=fecha, hora=hora_inicio,
            duracion_min=duracion, parametros=parametros,
        )
        if not disponibilidad["hay_disponible"]:
            return []
        inicio = a_minutos(hora_inicio)
        ocupados = {
            str(fila.get("chofer_nombre") or "").strip().casefold()
            for fila in _filas_activas(filas)
            if se_solapan(
                inicio, inicio + duracion,
                a_minutos(fila.get("hora_inicio")), a_minutos(fila.get("hora_fin_estimada")),
            )
        } - {""}
        for item in disponibilidad["mixers"]:
            if str(item.get("chofer_asignado") or "").strip().casefold() in ocupados:
                item["estado"] = "OCUPADO"
        return planificar_cargas(disponibilidad, volumen, unidades)

    cargas = cargas_a(hora)
    if cargas:
        return duracion, cargas

    paso = parametros["intervalo_slot_min"]
    inicio = max(a_minutos(hora) + paso, a_minutos(parametros["hora_apertura"]))
    cierre = a_minutos(parametros["hora_cierre"]) - duracion
    alternativa = next(
        (a_hhmm(minuto) for minuto in range(inicio, cierre + 1, paso)
         if cargas_a(a_hhmm(minuto))),
        None,
    )
    mensaje = f"No hay capacidad de mixers verificada el {fecha.isoformat()} a las {hora}."
    if alternativa:
        mensaje += f" Hay cupo a las {alternativa}. ¿Quieres usar esa hora?"
    else:
        mensaje += " Indica otra fecha u hora, o revisa la flota y sus capacidades en Agenda."
    raise ReservaMixerInvalida(mensaje)


@asynccontextmanager
async def transaccion_agenda(pool):
    """Serializa la comprobación de cruces con la escritura de la agenda."""
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("LOCK TABLE dispatch_schedule IN SHARE ROW EXCLUSIVE MODE")
        yield conn


async def reservar_mixers(pool, datos, *, clave=None, unidades=None, avisar_secretaria=False):
    """Comprueba el cupo y guarda todas las cargas en una transacción."""
    fecha = _fecha_sql(datos["fecha_entrega"])
    hora = datos["hora_inicio"]
    async with transaccion_agenda(pool) as conn:
        store = PostgresAgendaStore(conn)
        if clave:
            anteriores = await conn.fetch(
                "SELECT id::text FROM dispatch_schedule WHERE notas = $1 ORDER BY id",
                clave,
            )
            if anteriores:
                filas = [await store.obtener(fila["id"]) for fila in anteriores]
                if any(fila is None or fila["estado"] in ("CANCELADO", "REAGENDADO") for fila in filas):
                    raise ReservaMixerInvalida("La reserva original fue cambiada en Agenda.")
                return filas
        if datetime.combine(fecha, _hora_sql(hora), tzinfo=tiempo.ahora().tzinfo) <= tiempo.ahora():
            raise ReservaMixerInvalida("Indica una fecha y hora futuras para la entrega.")
        duracion, cargas = await plan_reserva_mixer(
            conn, fecha=fecha, hora=hora,
            volumen=Decimal(str(datos["volumen_m3"])), unidades=unidades,
        )
        filas = [
            await store.crear({
                **datos,
                "mixer_codigo": mixer["codigo"],
                "chofer_nombre": mixer.get("chofer_asignado"),
                "volumen_m3": volumen,
                "duracion_estimada_min": duracion,
                "estado": "RESERVA_CAMPO",
                "notas": clave or datos.get("notas"),
            })
            for mixer, volumen in cargas
        ]
        if avisar_secretaria:
            await notificar_secretaria(
                conn, tipo="mixers", entidad_id=filas[0]["id"],
                fecha=fecha.isoformat(), hora=hora,
                actor_id=datos.get("creado_por_id"), actor=str(datos.get("creado_por_nombre") or "Gato"),
                rol=str(datos.get("creado_por_rol") or "SUPERADMIN"),
                referencia=filas[0].get("cliente"),
            )
        return filas


class PostgresAgendaStore:
    def __init__(self, pool: asyncpg.Pool | asyncpg.Connection) -> None:
        self._pool = pool

    async def listar(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            _SELECT
            + """
             WHERE d.deleted_at IS NULL
               AND d.fecha_entrega BETWEEN $1 AND $2
             ORDER BY d.fecha_entrega, d.hora_inicio, d.mixer_codigo
            """,
            desde,
            hasta,
        )
        return [_agenda_dict(f) for f in filas]

    async def obtener(self, agenda_id: str) -> dict[str, Any] | None:
        fila = await self._pool.fetchrow(
            _SELECT + " WHERE d.id = $1 AND d.deleted_at IS NULL", agenda_id
        )
        return _agenda_dict(fila) if fila else None

    async def crear(self, datos: Mapping[str, Any]) -> dict[str, Any]:
        fila = await self._pool.fetchrow(
            """
            INSERT INTO dispatch_schedule
                (order_id, cliente_id, planta_id, mixer_codigo, chofer_nombre,
                 receta_codigo, volumen_m3, fecha_entrega, hora_inicio,
                 duracion_estimada_min, direccion_obra, contacto_obra_telefono,
                 estado, motivo_reagendamiento, reagendado_de_id,
                 creado_por_rol, creado_por_id, notificar_whatsapp, notas)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                    $13, $14, $15, $16, $17, $18, $19)
            RETURNING id
            """,
            datos.get("order_id"),
            datos["cliente_id"],
            datos.get("planta_id"),
            datos.get("mixer_codigo"),
            datos.get("chofer_nombre"),
            datos.get("receta_codigo"),
            datos["volumen_m3"],
            _fecha_sql(datos["fecha_entrega"]),
            _hora_sql(datos["hora_inicio"]),
            datos.get("duracion_estimada_min", DEFAULTS["duracion_entrega_default_min"]),
            datos["direccion_obra"],
            datos.get("contacto_obra_telefono"),
            datos.get("estado", "PROGRAMADO"),
            datos.get("motivo_reagendamiento"),
            datos.get("reagendado_de_id"),
            datos.get("creado_por_rol", "SECRETARIA"),
            datos.get("creado_por_id", "panel"),
            bool(datos.get("notificar_whatsapp", True)),
            datos.get("notas"),
        )
        return await self.obtener(str(fila["id"]))

    async def actualizar(
        self, agenda_id: str, cambios: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        campos = {k: v for k, v in cambios.items() if k in _CAMPOS_EDITABLES}
        if "fecha_entrega" in campos:
            campos["fecha_entrega"] = _fecha_sql(campos["fecha_entrega"])
        if "hora_inicio" in campos:
            campos["hora_inicio"] = _hora_sql(campos["hora_inicio"])
        if not campos:
            return await self.obtener(agenda_id)
        asignaciones = ", ".join(
            f"{campo} = ${indice}" for indice, campo in enumerate(campos, start=2)
        )
        valores = list(campos.values())
        fila = await self._pool.fetchrow(
            f"""
            UPDATE dispatch_schedule
               SET {asignaciones}, updated_at = now()
             WHERE id = $1 AND deleted_at IS NULL
            RETURNING id
            """,
            agenda_id,
            *valores,
        )
        return await self.obtener(str(fila["id"])) if fila else None

    async def cancelar(self, agenda_id: str) -> bool:
        fila = await self._pool.fetchrow(
            """
            UPDATE dispatch_schedule
               SET estado = 'CANCELADO', deleted_at = now(), updated_at = now()
             WHERE id = $1 AND deleted_at IS NULL
            RETURNING id
            """,
            agenda_id,
        )
        return fila is not None
