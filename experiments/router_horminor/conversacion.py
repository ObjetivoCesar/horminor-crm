"""Respuestas conversacionales del router (experimento).

Clasifica lo que Julio responde y redacta la contestación del Cerebro.
No ejecuta tareas: solo devuelve el plan.
"""

from __future__ import annotations

import re
from typing import Any

from experiments.d_vs_dmas.contracts import plano

from .model import BorradorRouter, PlanConfirmacion


def es_confirmacion(frase: str) -> bool:
    t = plano(frase).strip()
    if any(
        marca in t
        for marca in ("no ", "pero", "cambia", "corrige", "cancela", "espera", "todavia")
    ):
        return False
    return bool(
        re.match(
            r"^(si|dale|ok|okay|correcto|confirmo|confirmado|de acuerdo|adelante|hazlo|perfecto)\b",
            t,
        )
    )


def resumen_cambios(cambios: list[dict[str, Any]]) -> str:
    partes = []
    for cambio in cambios:
        campo = str(cambio.get("campo") or "")
        antes = cambio.get("antes")
        despues = cambio.get("despues")
        if campo == "cliente.nombre":
            partes.append(f"el cliente ahora es {despues}")
        elif campo.endswith(".destinatario"):
            partes.append(f"el recordatorio va para {despues}")
        elif campo.endswith(".responsable"):
            partes.append(f"{campo.split('.')[0]} pasa a {despues}")
        elif campo == "confirmacion":
            continue
        elif antes in (None, ""):
            partes.append(f"{campo}: {despues}")
        else:
            partes.append(f"{campo}: «{antes}» → «{despues}»")
    return "; ".join(partes)


def respuesta_correccion(nuevo: BorradorRouter, meta: dict[str, Any]) -> str:
    cambios = meta.get("cambios") or []
    if not cambios:
        aclaracion = meta.get("aclaracion") or "no entendí qué corregir"
        return f"No cambié nada: {aclaracion}."
    hecho = "Hecho. Actualicé: " + resumen_cambios(cambios) + ". El resto queda igual."
    return hecho + "\n\n¿Confirmas el borrador actualizado?"


_ETIQUETAS = {
    "SECRETARIA": "Secretaría",
    "JEFE_PLANTA": "Jefe de planta",
    "JULIO": "Tú",
    "POR_DEFINIR": "Por asignar",
}


def respuesta_confirmacion(plan: PlanConfirmacion) -> str:
    lineas = ["Perfecto. Así quedarían las tareas:"]
    for tarea in plan.tareas:
        etiqueta = _ETIQUETAS.get(tarea.responsable, tarea.responsable)
        lineas.append(f"• {etiqueta}: {tarea.titulo}")
    for pendiente in plan.pendientes:
        lineas.append(f"• Pendiente: {pendiente}")
    if plan.comunicaciones:
        lineas.append("")
        lineas.append(
            "Las comunicaciones quedan preparadas; ninguna se envía sin tu autorización."
        )
    if plan.operaciones:
        lineas.append(
            "Las operaciones condicionadas no se ejecutan con esta confirmación."
        )
    lineas.append("")
    lineas.append("Todavía no se creó nada: este es el plan que se ejecutaría.")
    return "\n".join(lineas)
