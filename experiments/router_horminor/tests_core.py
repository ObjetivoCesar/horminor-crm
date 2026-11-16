"""Pruebas determinísticas del router (sin LLM).

Cubren las reglas de negocio: no bloquear por datos que el responsable debe
investigar, separar preparar/notificar/ejecutar, corregir un solo encargo y
correspondencia exacta entre lo confirmado y el plan.

    python -m experiments.router_horminor.tests_core
"""

from __future__ import annotations

from .confirmacion import planificar, verificar_correspondencia
from .model import BorradorRouter, Encargo
from .router import ObservacionOut, TrabajoOut, conciliar

TEXTO = (
    "Que secretaría revise el pago de la obra La Pradera y me avise cuando "
    "esté confirmado. Que el jefe de planta prepare un plan tentativo, pero no "
    "despachen hasta que se confirme el anticipo."
)


def _trabajo() -> TrabajoOut:
    return TrabajoOut.model_validate(
        {
            "encargos": [
                {
                    "titulo": "Revisar pago de La Pradera",
                    "que_hacer": "revisar el pago y avisar a Julio",
                    "responsable": "SECRETARIA",
                    "responsable_sugerido": False,
                    "resultado_esperado": "avisar a Julio cuando esté confirmado",
                    "por_investigar": ["confirmación del anticipo"],
                    "citas": ["Que secretaría revise el pago de la obra La Pradera"],
                },
                {
                    "titulo": "Preparar plan de despacho",
                    "que_hacer": "preparar un plan tentativo de despacho",
                    "responsable": "JEFE_PLANTA",
                    "responsable_sugerido": False,
                    "requiere_autorizacion": True,
                    "citas": ["Que el jefe de planta prepare un plan tentativo"],
                },
            ],
            "informacion_sin_encargo": [],
            "consultas": [],
            "constancias": [],
            "decisiones_julio": [],
        }
    )


def _observaciones() -> list[ObservacionOut]:
    return [
        ObservacionOut(
            tipo="PROHIBICION",
            objeto="despacho",
            condiciona_operacion=True,
            texto="no despachen hasta que se confirme el anticipo",
            citas=["no despachen hasta que se confirme el anticipo"],
        )
    ]


def _caso(texto: str = TEXTO, con_observaciones: bool = True) -> BorradorRouter:
    return conciliar(
        texto,
        trabajo=_trabajo(),
        hechos=[],
        observaciones=_observaciones() if con_observaciones else [],
        revision_ok=True,
    )


def main() -> None:
    resultados: list[tuple[str, bool, str]] = []

    # 1. Datos por investigar no bloquean la tarea
    b = _caso()
    tarea = b.encargos[0]
    plan = planificar(b)
    ok = (
        tarea.por_investigar == ["confirmación del anticipo"]
        and any(t.encargo_id == tarea.id for t in plan.tareas)
    )
    resultados.append(("dato por investigar no bloquea", ok, tarea.resumen()))

    # 2. Restricción de despacho no bloquea la planificación
    planta = b.encargos[1]
    ok = (
        planta.responsable == "JEFE_PLANTA"
        and bool(planta.condiciones)
        and planta.requiere_autorizacion
        and not planta.autorizado
        and any(t.encargo_id == planta.id for t in plan.tareas)
    )
    resultados.append(("planificación no se bloquea por el despacho", ok, planta.resumen()))

    # 3. Preparar no es enviar
    b_wa = BorradorRouter(
        resumen="",
        encargos=[
            Encargo(
                id="E1",
                titulo="Preparar WhatsApp a la ingeniera Paula",
                que_hacer="redactar el mensaje del comprobante",
                responsable="SECRETARIA",
                canal="WHATSAPP",
                ambito="EXTERNO",
                destinatario="ingeniera Paula",
                preparar_comunicacion=True,
                requiere_autorizacion=True,
                autorizado=False,
            )
        ],
    )
    plan_wa = planificar(b_wa)
    comunicacion = next(
        (c for c in plan_wa.comunicaciones if c.encargo_id == "E1"), None
    )
    ok = comunicacion is not None and comunicacion.accion == "PREPARAR"
    resultados.append(
        (
            "sin autorización solo se prepara",
            ok,
            str(comunicacion),
        )
    )

    # 3b. Con autorización explícita sí se envía
    b_wa.encargos[0].autorizado = True
    comunicacion = next(
        (c for c in planificar(b_wa).comunicaciones if c.encargo_id == "E1"), None
    )
    resultados.append(
        (
            "con autorización se envía",
            comunicacion is not None and comunicacion.accion == "PREPARAR_Y_ENVIAR",
            str(comunicacion),
        )
    )

    # 4. Resultado esperado no crea segunda tarea
    ok = (
        b.encargos[0].resultado_esperado is not None
        and len(b.encargos) == 2
        and len(plan.tareas) == 2
    )
    resultados.append(("avisar es resultado, no tarea aparte", ok, str(len(plan.tareas))))

    # 5. Correspondencia exacta
    problemas = verificar_correspondencia(b, plan)
    resultados.append(("correspondencia confirmado-plan", not problemas, str(problemas)))

    # 6. Confirmar solo uno
    solo = planificar(b, confirmados=["E1"])
    ok = [t.encargo_id for t in solo.tareas] == ["E1"] and not verificar_correspondencia(
        b, solo, confirmados=["E1"]
    )
    resultados.append(("confirmación parcial", ok, str([t.encargo_id for t in solo.tareas])))

    # 7. Responsable por definir no crea tarea
    b2 = b.model_copy(deep=True)
    b2.encargos[0].responsable = "POR_DEFINIR"
    b2.encargos[0].estado = "POR_DEFINIR"
    plan2 = planificar(b2)
    ok = any("E1" in p for p in plan2.pendientes) and not any(
        t.encargo_id == "E1" for t in plan2.tareas
    )
    resultados.append(("sin responsable no se crea tarea", ok, str(plan2.pendientes)))

    # 8. Clave idempotente estable
    p1 = planificar(b).tareas[0].clave_idempotencia
    p2 = planificar(b).tareas[0].clave_idempotencia
    resultados.append(("clave idempotente estable", p1 == p2, p1))

    # 9. Cita de cliente: no se ejecuta, se revisa
    b3 = conciliar(
        "El cliente pidió anular las facturas. Que secretaría lo revise.",
        trabajo=TrabajoOut.model_validate(
            {
                "encargos": [
                    {
                        "titulo": "Revisar solicitud del cliente",
                        "que_hacer": "revisar lo que pidió el cliente",
                        "responsable": "SECRETARIA",
                        "origen": "CITA_CLIENTE",
                        "citas": ["Que secretaría lo revise"],
                    }
                ]
            }
        ),
        hechos=[],
        observaciones=[],
        revision_ok=True,
    )
    ok = b3.encargos[0].origen == "CITA_CLIENTE" and not any(
        "anular" in t.titulo.lower() for t in planificar(b3).tareas
    )
    resultados.append(("cita de cliente no se ejecuta", ok, b3.encargos[0].origen))

    # 10. Sin C no se autoriza envío
    b4 = conciliar(
        TEXTO,
        trabajo=_trabajo(),
        hechos=[],
        observaciones=[],
        revision_ok=False,
    )
    ok = all(not e.autorizado for e in b4.encargos if e.canal == "WHATSAPP")
    resultados.append(("sin revisión no hay autorización", ok, "ok"))

    # 11. Corrección natural: cambia solo el encargo indicado
    b5 = _caso()
    texto_correccion = (
        "No era para secretaría, era para el jefe de planta lo de revisar el pago"
    )
    from .correccion import _aplicar, CambioIn

    objetivo = "E1"
    nuevo, errores = _aplicar(
        b5,
        cambios=[CambioIn(encargo=objetivo, campo="responsable", valor="JEFE_PLANTA")],
        cancelar=[],
        explicacion="prueba",
    )
    ok = (
        not errores
        and nuevo is not None
        and nuevo.version == b5.version + 1
        and next(e for e in nuevo.encargos if e.id == "E1").responsable
        == "JEFE_PLANTA"
        and next(e for e in nuevo.encargos if e.id == "E2").model_dump()
        == next(e for e in b5.encargos if e.id == "E2").model_dump()
    )
    resultados.append(("corrección de un encargo no toca los demás", ok, f"v{nuevo.version if nuevo else '?'}"))

    # 12. Cancelar uno no afecta al resto
    nuevo2, errores2 = _aplicar(
        b5,
        cambios=[],
        cancelar=["E2"],
        explicacion="prueba",
    )
    ok = (
        not errores2
        and nuevo2 is not None
        and [e.id for e in nuevo2.encargos] == ["E1"]
        and nuevo2.encargos[0].model_dump()
        == next(e for e in b5.encargos if e.id == "E1").model_dump()
    )
    resultados.append(("cancelar un encargo", ok, str([e.id for e in nuevo2.encargos]) if nuevo2 else "error"))

    # 13. Monto «27 1000» no es 271.000
    from .router import _reparar_monto

    ok = _reparar_monto(271000, "una transferencia de 27 1000 USD") == 27000
    resultados.append(("monto 27 1000 -> 27.000", ok, "27000"))

    # 14. «Hay que enviarle» no autoriza; «envíalo» sí
    base_wa = {
        "titulo": "Preparar mensaje",
        "que_hacer": "preparar un mensaje al cliente",
        "responsable": "SECRETARIA",
        "canal": "WHATSAPP",
        "preparar_comunicacion": True,
        "citas": ["hay que enviarle un mensaje al cliente"],
    }
    b_sin = conciliar(
        "hay que enviarle un mensaje al cliente",
        trabajo=TrabajoOut.model_validate({"encargos": [base_wa]}),
        hechos=[],
        observaciones=[
            ObservacionOut(
                tipo="AUTORIZACION",
                autoriza_ejecucion=True,
                texto="hay que enviarle un mensaje",
                citas=["hay que enviarle un mensaje al cliente"],
            )
        ],
        revision_ok=True,
    )
    ok1 = b_sin.encargos and not b_sin.encargos[0].autorizado
    b_con = conciliar(
        "envíalo ahora al cliente",
        trabajo=TrabajoOut.model_validate(
            {"encargos": [{**base_wa, "citas": ["envíalo ahora al cliente"]}]}
        ),
        hechos=[],
        observaciones=[
            ObservacionOut(
                tipo="AUTORIZACION",
                autoriza_ejecucion=True,
                texto="envíalo ahora",
                citas=["envíalo ahora al cliente"],
            )
        ],
        revision_ok=True,
    )
    ok2 = bool(b_con.encargos) and b_con.encargos[0].autorizado
    resultados.append(("autorización explícita vs mención", ok1 and ok2, f"{ok1} {ok2}"))

    # 15. Un pago anunciado no crea tarea de verificarlo
    b_pago = conciliar(
        "Nos van a transferir 27 mil dólares para la firma.",
        trabajo=TrabajoOut.model_validate(
            {
                "encargos": [
                    {
                        "titulo": "Verificar transferencia de 27 mil",
                        "que_hacer": "verificar la transferencia",
                        "responsable": "SECRETARIA",
                        "citas": ["Nos van a transferir 27 mil dólares"],
                    }
                ]
            }
        ),
        hechos=[],
        observaciones=[],
        revision_ok=True,
    )
    resultados.append(
        (
            "pago anunciado no es tarea de verificación",
            len(b_pago.encargos) == 0,
            str(len(b_pago.encargos)),
        )
    )

    # 16. Una condición sin marca real no ensucia la tarea
    b_cond = conciliar(
        "hay que llevar la planta móvil y despachar desde ahí",
        trabajo=TrabajoOut.model_validate(
            {
                "encargos": [
                    {
                        "titulo": "Evaluar planta móvil",
                        "que_hacer": "evaluar llevar la planta móvil",
                        "responsable": "JEFE_PLANTA",
                        "citas": ["hay que llevar la planta móvil"],
                    }
                ]
            }
        ),
        hechos=[],
        observaciones=[
            ObservacionOut(
                tipo="CONDICION",
                condiciona_operacion=True,
                objeto="planta móvil",
                texto="hay que llevar la planta móvil y despachar desde ahí",
                citas=["hay que llevar la planta móvil"],
            )
        ],
        revision_ok=True,
    )
    ok = bool(b_cond.encargos) and not b_cond.encargos[0].condiciones
    resultados.append(("condición falsa no se adjunta", ok, str(b_cond.encargos[0].condiciones if b_cond.encargos else None)))

    print()
    for nombre, ok, detalle in resultados:
        print(f"[{'OK' if ok else 'FALLA'}] {nombre} — {detalle}")
    aprobadas = sum(1 for _, ok, _ in resultados if ok)
    print(f"\n{aprobadas}/{len(resultados)} pruebas del router")
    if aprobadas != len(resultados):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
