"""Skill de Agenda: consulta de disponibilidad y recordatorios personales.

Separa la PREPARACIÓN (qué se mostrará) de la EJECUCIÓN (qué se escribe).
No toca base de datos directamente: usa los puertos del contrato.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping

from .. import recordatorios as rec_svc
from ..razonador import DatosTurno
from .contrato import (
    DECIDIR_CHOQUE,
    EJECUTADA,
    ERROR,
    ESPERANDO_CONFIRMACION,
    FALTAN_DATOS,
    LISTA,
    NO_CONECTADA,
    Autorizacion,
    Choque,
    ContextoSkill,
    Preparacion,
    ResultadoSkill,
)
from .politica import huella_texto

_LOG = logging.getLogger(__name__)

# Margen para considerar un choque DURO (en minutos).
_DURO_MIN = 30


def _fmt_momento(dt: datetime) -> str:
    from ... import tiempo
    local = dt.astimezone(tiempo.ZONA)
    return f"{local:%Y-%m-%d} a las {local:%H:%M}"


def _choques_a_vista(choques: list[Choque]) -> str:
    lineas = ["Hay choques en la agenda:"]
    for c in choques:
        lineas.append(
            f"  · [{c.severidad}] {c.etiqueta} a las {c.inicio}"
            + (f"–{c.fin}" if c.fin else "")
        )
    return "\n".join(lineas)


class AgendaSkill:
    """Skills de agenda para Gato: consulta y recordatorios personales."""

    # ------------------------------------------------------------------ #
    # Consulta de disponibilidad                                           #
    # ------------------------------------------------------------------ #

    async def preparar_consulta(self, ctx: ContextoSkill) -> Preparacion:
        """Lee la agenda del actor para hoy o para la fecha pedida."""
        from ... import tiempo

        p = ctx.puertos.personal
        if p is None:
            return Preparacion(NO_CONECTADA, motivo="Agenda no disponible.")

        params = ctx.parametros
        fecha_str: str | None = params.get("fecha")
        try:
            dia = datetime.fromisoformat(fecha_str).date() if fecha_str else tiempo.hoy()
        except ValueError:
            dia = tiempo.hoy()

        try:
            eventos = await p.eventos(ctx.actor.actor_id, dia)
        except Exception as exc:
            _LOG.warning("Error leyendo agenda: %s", exc)
            return Preparacion(ERROR, motivo="No pude leer la agenda en este momento.")

        if not eventos:
            return Preparacion(LISTA, vista=f"No tienes compromisos el {dia}.")

        lineas = [f"Agenda del {dia}:"]
        for ev in eventos[:20]:
            hora = str(ev.get("hora_inicio") or ev.get("hora") or "")
            etiqueta = str(ev.get("etiqueta") or ev.get("descripcion") or "Sin descripción")
            estado = str(ev.get("estado") or "")
            lineas.append(f"  · {hora} {etiqueta}" + (f" [{estado}]" if estado else ""))
        return Preparacion(LISTA, vista="\n".join(lineas))

    # ------------------------------------------------------------------ #
    # Recordatorio personal                                                #
    # ------------------------------------------------------------------ #

    def preparar_recordatorio(
        self,
        datos: DatosTurno,
        datos_previos: Mapping[str, Any],
    ) -> "PrepRecordatorio":
        """Valida y prepara el recordatorio. No escribe nada."""
        from ... import tiempo
        from .. import asuntos_operativos

        registro = asuntos_operativos.preparar_recordatorio(datos, dict(datos_previos))
        registro.datos["personal"] = True
        registro.datos.pop("telefono", None)

        # Si faltan datos, el Asunto ya tiene preguntas pendientes
        if registro.preguntas:
            return _PrepRecordatorio(registro, cuando=None)

        cuando_str: str | None = registro.datos.get("cuando")
        if not cuando_str:
            return _PrepRecordatorio(registro, cuando=None)

        try:
            cuando = datetime.fromisoformat(cuando_str)
        except ValueError:
            registro.preguntas = ("No entendí la hora. ¿Cuándo quieres el recordatorio?",)
            return _PrepRecordatorio(registro, cuando=None)

        if cuando <= tiempo.ahora():
            registro = registro.__class__.__new__(registro.__class__)
            object.__setattr__(registro, "tipo", "recordatorio")
            object.__setattr__(registro, "estado", "ESPERANDO_ACLARACION")
            object.__setattr__(registro, "preguntas", ("Esa hora ya pasó. ¿A qué hora quieres el recordatorio?",))
            object.__setattr__(registro, "datos", {k: v for k, v in dict(datos_previos).items() if k not in {"hora", "cuando"}})
            object.__setattr__(registro, "etiqueta", str(datos_previos.get("etiqueta") or "recordatorio"))
            object.__setattr__(registro, "borrador_id", None)
            object.__setattr__(registro, "actualizado_en", "")
            return _PrepRecordatorio(registro, cuando=None)

        return _PrepRecordatorio(registro, cuando=cuando)

    async def ejecutar_recordatorio(
        self,
        ctx: ContextoSkill,
        autorizacion: Autorizacion,
        cuando: datetime,
    ) -> ResultadoSkill:
        """Escribe el recordatorio si la huella coincide."""
        p = ctx.puertos.personal
        if p is None:
            return ResultadoSkill(ERROR, "Agenda no disponible.", {})

        params = ctx.parametros
        huella_esperada = huella_texto(ctx.actor.actor_id, "recordatorio", params)
        if autorizacion.huella != huella_esperada:
            return ResultadoSkill(ERROR, "Confirmación no reconocida. Muéstrame el recordatorio de nuevo.", {})

        try:
            resultado = await p.agendar_recordatorio(
                actor=ctx.actor,
                asunto_id=ctx.asunto_id,
                mensaje=str(params.get("mensaje") or ""),
                cuando=cuando,
            )
            return ResultadoSkill(
                EJECUTADA,
                f"Listo. Te recuerdo el {_fmt_momento(cuando)}.",
                dict(resultado),
            )
        except Exception as exc:
            _LOG.warning("Error agendando recordatorio: %s", exc)
            return ResultadoSkill(ERROR, f"No pude agendar el recordatorio: {exc}", {})

    # ------------------------------------------------------------------ #
    # Verificar cupo (consulta sin modificación)                           #
    # ------------------------------------------------------------------ #

    async def verificar_cupo(self, ctx: ContextoSkill) -> Preparacion:
        """Consulta slots disponibles en la fecha/hora pedida.

        No modifica ningún registro. Responde «sí hay cupo» o «no hay cupo».
        """
        m = ctx.puertos.mixer
        if m is None:
            return Preparacion(NO_CONECTADA, motivo="Mixer no disponible.")

        params = ctx.parametros
        fecha_str: str | None = params.get("fecha")
        hora_str: str | None = params.get("hora")
        volumen = params.get("volumen")

        if not fecha_str or not hora_str:
            return Preparacion(
                FALTAN_DATOS,
                vista="¿Qué fecha y hora necesitas verificar?",
            )

        try:
            from datetime import date as _date
            fecha = datetime.fromisoformat(fecha_str).date() if "T" in fecha_str else _date.fromisoformat(fecha_str)
        except ValueError:
            return Preparacion(FALTAN_DATOS, vista="No entendí la fecha. Dímela en formato AAAA-MM-DD.")

        try:
            resultado = await m.verificar(
                fecha=fecha,
                hora=hora_str,
                volumen=volumen,
                unidades=None,
            )
        except Exception as exc:
            _LOG.warning("Error verificando cupo mixer: %s", exc)
            return Preparacion(ERROR, motivo=f"No pude consultar la disponibilidad: {exc}")

        disponible = resultado.get("disponible", False)
        if disponible:
            return Preparacion(LISTA, vista=f"Sí hay cupo el {fecha} a las {hora_str}.")
        razon = resultado.get("motivo") or "No hay cupo en ese horario."
        return Preparacion(LISTA, vista=razon)


# Clase auxiliar (not exported from __init__) para devolver el Asunto preparado
# sin introducir una dependencia circular con asuntos_operativos.
class _PrepRecordatorio:
    __slots__ = ("registro", "cuando")

    def __init__(self, registro: Any, cuando: datetime | None) -> None:
        self.registro = registro
        self.cuando = cuando
