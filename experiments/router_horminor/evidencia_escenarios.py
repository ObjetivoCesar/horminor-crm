"""Evidencia de aceptación del router: escenarios A-F, regresión y corrección.

    python -m experiments.router_horminor.evidencia_escenarios
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from experiments.d_vs_dmas.llm import nuevo_cliente
from experiments.d_vs_dmas.reference import cargar_corpus

from .confirmacion import planificar, verificar_correspondencia
from .correccion import corregir
from .router import construir

EVIDENCIAS = Path(__file__).resolve().parent / "evidencias"

ESCENARIOS = {
    "A": "Oye, mañana hay fundida temprano. Que los chicos estén a las cinco de la mañana en la planta, y que el jefe de planta me avise si falta algún operario.",
    "B": "Que secretaría averigüe el volumen exacto que necesita la constructora El Valle y me confirme; no sé si son 35 o 38 metros.",
    "C": "Tres cosas para hoy: que secretaría revise el pago de La Pradera, que contacte al cliente para confirmar la fecha de entrega, y que el jefe de planta prepare la coordinación del despacho.",
    "D": "El despacho para la obra La Pradera: que planta prepare la coordinación, pero no autoricen la salida del camión hasta que se confirme el anticipo.",
    "E": "El cliente me pidió que anulemos sus facturas y le devolvamos el anticipo. Que secretaría revise el caso y me informe; no hagan nada de lo que él pide.",
    "F": "Que el jefe de planta revise el stock de cemento y me avise cuando termine.",
}

CORRECCION_C = "No era para secretaría, era para el jefe de planta lo de contactar al cliente"


async def main() -> None:
    EVIDENCIAS.mkdir(parents=True, exist_ok=True)
    corpus = {c.id: c.dictado for c in cargar_corpus()}
    casos = list(ESCENARIOS.items())
    for caso_id in ("E07", "E11", "E14", "E27"):
        if caso_id in corpus:
            casos.append((f"REG-{caso_id}", corpus[caso_id]))

    filas: list[dict] = []
    async with nuevo_cliente(concurrencia=6) as cliente:
        for nombre, texto in casos:
            resultado = await construir(cliente, texto)
            borrador = resultado.borrador
            plan = planificar(borrador)
            problemas = verificar_correspondencia(borrador, plan)
            correccion = None
            if nombre == "C":
                nuevo, errores, meta = await corregir(cliente, borrador, CORRECCION_C)
                correccion = {
                    "frase": CORRECCION_C,
                    "errores": errores,
                    "meta": meta,
                    "antes": [(e.id, e.responsable) for e in borrador.encargos],
                    "despues": [(e.id, e.responsable) for e in nuevo.encargos]
                    if nuevo
                    else [],
                    "version": nuevo.version if nuevo else None,
                }
                if nuevo:
                    plan = planificar(nuevo)
                    problemas = verificar_correspondencia(nuevo, plan)
                    borrador = nuevo

            filas.append(
                {
                    "caso": nombre,
                    "dictado": texto,
                    "error": resultado.error,
                    "resumen": borrador.resumen,
                    "encargos": [
                        {
                            "id": e.id,
                            "titulo": e.titulo,
                            "responsable": e.responsable,
                            "sugerido": e.responsable_sugerido,
                            "condiciones": e.condiciones,
                            "por_investigar": e.por_investigar,
                            "resultado_esperado": e.resultado_esperado,
                            "datos": e.datos,
                            "origen": e.origen,
                            "requiere_autorizacion": e.requiere_autorizacion,
                            "autorizado": e.autorizado,
                        }
                        for e in borrador.encargos
                    ],
                    "preguntas": borrador.preguntas,
                    "constancias": borrador.constancias,
                    "plan": json.loads(plan.model_dump_json()),
                    "correspondencia": problemas,
                    "correccion": correccion,
                    "llamadas": resultado.llamadas,
                }
            )
            print(
                f"{nombre:8} encargos={len(borrador.encargos)} "
                f"plan={len(plan.tareas)} preguntas={len(borrador.preguntas)} "
                f"correspondencia={'OK' if not problemas else problemas}"
            )

    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    salida = EVIDENCIAS / f"escenarios_{marca}.json"
    salida.write_text(json.dumps(filas, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nevidence: {salida}")


if __name__ == "__main__":
    asyncio.run(main())
