"""HTTP de la agenda visual: solo lectura, sin ejecutar envios."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from .. import tiempo
from ..asistente import recordatorios
from ..asistente.bibliotecario import Bibliotecario
from ..asistente.orquestador import Actor
from ..comercial import citas
from ..panel_acl import exigir_modulos
from . import eventos as eventos_svc

router = APIRouter(prefix="/api/v1/agenda", tags=["agenda"])

_MODULOS = tuple(
    sorted({modulo for modulos in eventos_svc.MODULOS_POR_TIPO.values() for modulo in modulos})
)
_RANGO_MAXIMO_DIAS = 400
_ESTADOS_PROXIMOS = {
    "mixers": {"RESERVA_CAMPO", "PROGRAMADO", "EN_PLANTA", "EN_RUTA"},
    "recordatorios": {"AGENDADO", "PENDIENTE"},
    "julio": {"SOLICITADA", "CONFIRMADA", "REAGENDADA"},
    "equipo": {"NOTIFICADA"},
}


def _pool(request: Request) -> asyncpg.Pool:
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="base de datos no disponible")
    return pool


def _tipos_permitidos(perfil: dict[str, Any]) -> list[str]:
    permitidos = perfil.get("modulos_permitidos") or {}
    return [
        tipo
        for tipo in eventos_svc.TIPOS
        if any(permitidos.get(modulo) for modulo in eventos_svc.MODULOS_POR_TIPO[tipo])
    ]


def _limite_visitas(perfil: dict[str, Any]) -> dict[str, bool]:
    permisos = perfil.get("modulos_permitidos") or {}
    if permisos.get("secretaria_ventanilla") and not (
        permisos.get("clientes_cartera") or permisos.get("cotizaciones")
    ):
        return {"solo_visitas_gato": True}
    return {}


@router.get("/proximo")
async def proximo_evento(request: Request) -> dict[str, Any]:
    """Primer compromiso vigente de hoy que el perfil puede consultar."""
    perfil = await exigir_modulos(request, _MODULOS)
    ahora = tiempo.ahora()
    hoy = ahora.date()
    hora = ahora.strftime("%H:%M")
    eventos = await eventos_svc.listar(
        _pool(request), desde=hoy, hasta=hoy, tipos=tuple(_tipos_permitidos(perfil)),
        **_limite_visitas(perfil),
    )
    proximo = next(
        (
            evento for evento in eventos
            if (evento["hora"] or "") > hora
            and evento["estado"] in _ESTADOS_PROXIMOS[evento["tipo"]]
        ),
        None,
    )
    return {"hoy": hoy.isoformat(), "evento": proximo}


@router.get("/eventos")
async def listar_eventos(
    request: Request,
    tipo: str | None = Query(default=None),
    desde: date | None = Query(default=None),
    hasta: date | None = Query(default=None),
) -> dict[str, Any]:
    """Eventos de la agenda entre dos fechas (por defecto, el mes en curso).

    ``tipo`` es opcional: sin el se devuelven todas las pestañas que el perfil
    puede ver, y el panel reparte por pestaña. El calendario no modifica nada.
    """
    perfil = await exigir_modulos(request, _MODULOS)
    permitidos = _tipos_permitidos(perfil)

    if tipo is not None:
        limpio = tipo.strip().lower()
        if limpio not in eventos_svc.TIPOS:
            raise HTTPException(
                status_code=422,
                detail=f"tipo de agenda invalido: {tipo}",
            )
        if limpio not in permitidos:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "MODULE_NOT_ALLOWED",
                    "message": "el perfil no tiene permiso sobre esta agenda",
                    "modulos": list(eventos_svc.MODULOS_POR_TIPO[limpio]),
                },
            )
        tipos = (limpio,)
    else:
        tipos = tuple(permitidos)

    fin = hasta or tiempo.hoy()
    inicio = desde or fin.replace(day=1)
    if inicio > fin:
        raise HTTPException(status_code=422, detail="desde no puede ser mayor que hasta")
    if (fin - inicio) > timedelta(days=_RANGO_MAXIMO_DIAS):
        raise HTTPException(
            status_code=422,
            detail=f"el rango no puede superar {_RANGO_MAXIMO_DIAS} dias",
        )

    eventos = await eventos_svc.listar(
        _pool(request), desde=inicio, hasta=fin, tipos=tipos, **_limite_visitas(perfil)
    )
    return {
        "zona": eventos_svc.ZONA,
        "hoy": tiempo.hoy().isoformat(),
        "desde": inicio.isoformat(),
        "hasta": fin.isoformat(),
        "tipos": list(tipos),
        "conteo": eventos_svc.conteo(eventos),
        "total": len(eventos),
        "eventos": eventos,
    }


class HorarioAgendaIn(BaseModel):
    fecha: date
    hora: time


@router.patch("/eventos/{tipo}/{evento_id}/horario")
async def corregir_horario(
    request: Request, tipo: str, evento_id: UUID, body: HorarioAgendaIn,
) -> dict[str, Any]:
    """Edita un compromiso que Gato ya agendó con autorización."""
    if tipo not in ("julio", "recordatorios"):
        raise HTTPException(status_code=404, detail="Este evento usa la edición de Mixers.")
    perfil = await exigir_modulos(request, eventos_svc.MODULOS_POR_TIPO[tipo], mutacion=True)
    rol = str(perfil.get("rol_base") or "")
    if rol not in ("SUPERADMIN", "SECRETARIA"):
        raise HTTPException(status_code=403, detail="La corrección corresponde a Julio o Secretaría.")
    if body.hora.tzinfo is not None or body.hora.second or body.hora.microsecond:
        raise HTTPException(status_code=422, detail="Indica una hora local en formato HH:MM.")
    instante = datetime.combine(body.fecha, body.hora, tiempo.ZONA)
    if instante <= tiempo.ahora():
        raise HTTPException(status_code=422, detail="Indica una fecha y hora futuras.")
    pool = _pool(request)
    identificador = str(evento_id)
    if tipo == "julio":
        if not await pool.fetchval(
            "SELECT 1 FROM citas WHERE id = $1::uuid AND clave_gato IS NOT NULL", identificador
        ):
            raise HTTPException(status_code=404, detail="Visita de Gato no encontrada.")
        try:
            return await citas.reagendar(
                pool, cita_id=identificador, fecha=body.fecha, hora_inicio=body.hora.strftime("%H:%M"),
                actor=str(perfil.get("nombre") or rol), motivo="Corrección desde Agenda",
                mantener_confirmada=True,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not await pool.fetchval(
        "SELECT 1 FROM gato_recordatorios WHERE id = $1::uuid AND origen_destino = 'PANEL'", identificador
    ):
        raise HTTPException(status_code=404, detail="Recordatorio interno no encontrado.")
    resultado = await recordatorios.actualizar(
        Bibliotecario(pool), recordatorio_id=identificador, cuando=instante.isoformat(),
        actor=Actor(nombre=str(perfil.get("nombre") or rol), rol=rol, actor_id=str(perfil.get("id") or "")),
    )
    if not resultado.ok:
        raise HTTPException(status_code=409, detail=resultado.nota)
    return resultado.datos
