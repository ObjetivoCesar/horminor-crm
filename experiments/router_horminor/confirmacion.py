"""Confirmación: convierte encargos confirmados en un PLAN, no en ejecución.

Regla: ninguna acción real supera la autorización recibida.
"""

from __future__ import annotations

import hashlib

from .model import (
    BorradorRouter,
    Encargo,
    PlanComunicacion,
    PlanConfirmacion,
    PlanOperacion,
    PlanTarea,
)


def _clave(version: int, encargo: Encargo) -> str:
    base = f"{version}:{encargo.id}:{encargo.titulo}:{encargo.responsable}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


def planificar(
    borrador: BorradorRouter,
    *,
    confirmados: list[str] | None = None,
    autorizaciones: dict[str, bool] | None = None,
) -> PlanConfirmacion:
    """Plan de lo que se crearía al confirmar. No ejecuta nada."""
    autorizaciones = autorizaciones or {}
    ids = confirmados if confirmados is not None else [e.id for e in borrador.encargos]
    seleccion = [e for e in borrador.encargos if e.id in ids]
    plan = PlanConfirmacion(confirmados=[e.id for e in seleccion])

    for encargo in seleccion:
        if encargo.responsable == "POR_DEFINIR":
            plan.pendientes.append(
                f"{encargo.id}: falta asignar responsable (secretaría o jefe de planta)"
            )
            continue

        autorizado = bool(autorizaciones.get(encargo.id, encargo.autorizado))
        plan.tareas.append(
            PlanTarea(
                encargo_id=encargo.id,
                titulo=encargo.titulo,
                responsable=encargo.responsable,
                notificar=True,
                resultado_esperado=encargo.resultado_esperado,
                plazo=encargo.plazo,
                clave_idempotencia=_clave(borrador.version, encargo),
                condiciones=list(encargo.condiciones),
                datos_por_investigar=list(encargo.por_investigar),
            )
        )

        if encargo.canal == "WHATSAPP" or encargo.preparar_comunicacion:
            plan.comunicaciones.append(
                PlanComunicacion(
                    encargo_id=encargo.id,
                    destinatario=encargo.destinatario,
                    accion="PREPARAR_Y_ENVIAR" if autorizado else "PREPARAR",
                    motivo=(
                        "autorizado por Julio"
                        if autorizado
                        else "solo preparar: falta autorización explícita de envío"
                    ),
                )
            )

        if encargo.requiere_autorizacion and not autorizado:
            plan.operaciones.append(
                PlanOperacion(
                    encargo_id=encargo.id,
                    operacion="OPERACION_CONDICIONADA",
                    autorizada=False,
                    motivo="el dictado la condiciona; no se ejecuta con esta confirmación",
                )
            )

        if encargo.condiciones:
            plan.advertencias.append(
                f"{encargo.id}: {'; '.join(encargo.condiciones)}"
            )

    return plan


def verificar_correspondencia(
    borrador: BorradorRouter,
    plan: PlanConfirmacion,
    *,
    confirmados: list[str] | None = None,
) -> list[str]:
    """Comprueba que el plan no agrega ni omite encargos confirmados."""
    ids = set(confirmados if confirmados is not None else [e.id for e in borrador.encargos])
    problemas: list[str] = []

    creados = [t.encargo_id for t in plan.tareas]
    pendientes = {p.split(":", 1)[0] for p in plan.pendientes}
    cubiertos = set(creados) | pendientes

    if len(creados) != len(set(creados)):
        problemas.append("Hay tareas duplicadas en el plan")
    if cubiertos != ids:
        faltan = ids - cubiertos
        sobran = cubiertos - ids
        if faltan:
            problemas.append(f"Encargos confirmados sin plan: {sorted(faltan)}")
        if sobran:
            problemas.append(f"Encargos en el plan no confirmados: {sorted(sobran)}")

    for tarea in plan.tareas:
        if tarea.responsable == "POR_DEFINIR":
            problemas.append(f"{tarea.encargo_id}: tarea sin responsable")

    for comunicacion in plan.comunicaciones:
        if comunicacion.accion == "PREPARAR_Y_ENVIAR":
            encargo = next(
                (e for e in borrador.encargos if e.id == comunicacion.encargo_id),
                None,
            )
            if encargo is None or not (encargo.autorizado):
                problemas.append(
                    f"{comunicacion.encargo_id}: envío sin autorización registrada"
                )

    for operacion in plan.operaciones:
        if operacion.autorizada:
            problemas.append(
                f"{operacion.encargo_id}: operación autorizada sin regla explícita"
            )

    return problemas
