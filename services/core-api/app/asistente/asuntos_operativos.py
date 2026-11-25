"""Prepara datos explícitos de una visita o un recordatorio personal."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from .. import tiempo
from ..comercial import leads
from ..comercial.intencion import parse_cita
from ..voz.normalizador_ec import normalizar_texto
from . import recordatorios
from .razonador import Asunto, DatosTurno


async def preparar_visita(
    pool, texto: str, lectura: DatosTurno, anteriores: dict[str, Any] | None,
) -> Asunto:
    datos = dict(anteriores or {})
    if lectura.fecha:
        fecha = parse_cita(normalizar_texto(lectura.fecha))["fecha"]
        if fecha:
            datos["fecha"] = fecha.isoformat()
    if lectura.hora:
        hora = parse_cita(normalizar_texto(lectura.hora))["hora"]
        if hora:
            datos["hora"] = hora
    if lectura.contacto:
        if any(letra.isalpha() for letra in lectura.contacto):
            if datos.get("nombre") != lectura.contacto:
                datos.pop("telefono_lead", None)
                datos.pop("lead_id", None)
            datos["nombre"] = lectura.contacto
        elif not lectura.telefono:
            lectura = lectura.model_copy(update={"telefono": lectura.contacto})
    if lectura.telefono:
        try:
            datos["telefono_lead"] = leads.telefono(lectura.telefono)
            datos.pop("lead_id", None)
        except ValueError:
            datos.pop("lead_id", None)
    datos["tipo"] = "VISITA"
    datos["personal"] = bool(datos.get("personal") or lectura.personal)
    datos["motivo"] = datos.get("motivo") or texto
    preguntas = []
    if not datos.get("fecha"):
        preguntas.append("¿Qué día es la visita?")
    if not datos.get("hora"):
        preguntas.append("¿A qué hora es la visita?")
    if not datos["personal"] and not datos.get("lead_id"):
        nombre = datos.get("nombre")
        if nombre or datos.get("telefono_lead"):
            exactos = await pool.fetch(
                """
                SELECT id::text AS id, nombre
                  FROM leads
                 WHERE ($1::text IS NOT NULL AND telefono_e164 = $1)
                    OR ($1::text IS NULL AND $2::text IS NOT NULL AND lower(nombre) = lower($2))
                 LIMIT 2
                """,
                datos.get("telefono_lead"), nombre,
            )
            if len(exactos) == 1:
                datos["lead_id"] = str(exactos[0]["id"])
                datos["nombre"] = nombre or exactos[0].get("nombre")
            elif exactos:
                preguntas.append(f"Hay más de un contacto llamado {nombre}. ¿Cuál es su teléfono?")
        if not datos.get("nombre") and not datos.get("lead_id"):
            preguntas.append("¿A qué posible cliente quieres visitar?")
    datos.pop("falta_contacto", None)
    etiqueta = f"visita de {datos['nombre']}" if datos.get("nombre") else "visita"
    return Asunto(
        "visita", etiqueta, "ESPERANDO_ACLARACION" if preguntas else "ESPERANDO_CONFIRMACION",
        preguntas=tuple(preguntas), datos=datos,
    )


def preparar_recordatorio(lectura: DatosTurno, anteriores: dict[str, Any] | None) -> Asunto:
    datos = dict(anteriores or {})
    if lectura.mensaje:
        datos["mensaje"] = lectura.mensaje
    if lectura.fecha:
        fecha = parse_cita(normalizar_texto(lectura.fecha))["fecha"]
        if fecha:
            datos["fecha"] = fecha.isoformat()
    if lectura.hora:
        hora_dicha = normalizar_texto(lectura.hora)
        hora = parse_cita(hora_dicha)["hora"]
        if hora:
            datos["hora"] = hora
        elif instante := recordatorios.parsear_cuando(hora_dicha, tiempo.ahora()):
            datos.pop("hora", None)
            datos["cuando"] = instante.astimezone(tiempo.ZONA).isoformat()
    if "hora" in datos and "fecha" in datos:
        cuando = datetime.combine(date.fromisoformat(datos["fecha"]), time.fromisoformat(datos["hora"]), tiempo.ZONA)
        datos["cuando"] = cuando.isoformat()
    preguntas = []
    datos["falta_mensaje"] = not datos.get("mensaje")
    if datos["falta_mensaje"]:
        preguntas.append("¿Qué quieres que te recuerde?")
    if not datos.get("cuando"):
        preguntas.append(
            "¿A qué hora quieres el recordatorio?" if datos.get("fecha")
            else "¿Qué día y a qué hora quieres el recordatorio?"
        )
    etiqueta = f"recordatorio de {datos['mensaje'][:70]}" if datos.get("mensaje") else "recordatorio"
    return Asunto(
        "recordatorio", etiqueta, "ESPERANDO_ACLARACION" if preguntas else "ESPERANDO_CONFIRMACION",
        preguntas=tuple(preguntas), datos=datos,
    )
