"""Caso real: contrato Díaz Sur (audio de 122 s).

Compara V07 (producción, sin escribir en la base) con router-1.1 y prueba una
corrección de destinatario y el plan de confirmación.

    python -m experiments.router_horminor.caso_diaz_sur
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import date
from pathlib import Path

from experiments.d_vs_dmas.llm import nuevo_cliente

from .confirmacion import planificar, verificar_correspondencia
from .correccion import corregir
from .router import construir

BASE = Path(__file__).resolve().parent
EVIDENCIAS = BASE / "evidencias"
ORIGINAL = EVIDENCIAS / "caso_diaz_sur_original.json"
APP = BASE.parents[1] / "services" / "core-api"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

CORRECCION = "No, el recordatorio va para Mauricio, no para Julio Alvarado"


def reproducir_v07(texto: str, sobre_json: dict) -> dict:
    from app.cerebro import compilar
    from app.cerebro.compilador import Contexto, _MARCAS_REVOCACION, dictado_revocado
    from app.cerebro.extractor import construir_hechos, validar_sobre
    from app.cerebro.dinero import sin_tildes
    from app.voz import localizar_palabras, normalizar_con_mapa

    plano = sin_tildes(texto)
    marcas = [m for m in _MARCAS_REVOCACION if m in plano]
    mapa = normalizar_con_mapa(texto)
    palabras = localizar_palabras(texto, [])
    sobre = validar_sobre(sobre_json)
    hechos, notas = construir_hechos(
        sobre, texto_crudo=texto, mapa=mapa, palabras=palabras
    )
    borrador = compilar(
        hechos,
        Contexto(
            hoy=date.today(),
            sandbox=True,
            cliente=None,
            receta=None,
            texto=mapa.texto,
        ),
    )
    return {
        "revocado": dictado_revocado(texto),
        "marcas_encontradas": marcas,
        "hechos": len(hechos),
        "estado": borrador.estado,
        "acciones": [a.nombre for a in borrador.acciones],
        "preguntas": [p.clave for p in borrador.preguntas],
        "notas": notas,
    }


async def main() -> None:
    original = json.loads(ORIGINAL.read_text(encoding="utf-8-sig"))
    texto = original["texto_normalizado"]

    v07 = reproducir_v07(texto, original["sobre"])
    print("=== V07 (reproducción en memoria) ===")
    print(json.dumps(v07, ensure_ascii=False, indent=1))

    async with nuevo_cliente(concurrencia=6) as cliente:
        resultado = await construir(cliente, texto)
        borrador = resultado.borrador
        print("\n=== ROUTER ===")
        print(borrador.resumen)
        for encargo in borrador.encargos:
            print(
                f"\n{encargo.id}. {encargo.titulo}\n"
                f"   responsable: {encargo.responsable}"
                f"{' (sugerido)' if encargo.responsable_sugerido else ''}\n"
                f"   que hacer: {encargo.que_hacer}\n"
                f"   destinatario: {encargo.destinatario} · canal {encargo.canal}\n"
                f"   resultado: {encargo.resultado_esperado}\n"
                f"   por investigar: {encargo.por_investigar}\n"
                f"   condiciones: {encargo.condiciones}\n"
                f"   datos: {json.dumps(encargo.datos, ensure_ascii=False)}"
            )
        print("\npreguntas:", borrador.preguntas)
        print("notas:", borrador.notas)

        plan_antes = planificar(borrador)
        print("\nplan antes:", json.loads(plan_antes.model_dump_json()))

        nuevo, errores, meta = await corregir(cliente, borrador, CORRECCION)
        print("\n=== CORRECCIÓN ===")
        print("frase:", CORRECCION)
        print("errores:", errores, "via:", meta.get("via"))
        if nuevo:
            for antes, despues in zip(borrador.encargos, nuevo.encargos):
                if antes.model_dump() != despues.model_dump():
                    print(
                        f"cambió {antes.id}: destinatario "
                        f"{antes.destinatario} -> {despues.destinatario}"
                    )
            print("versión:", nuevo.version)
            plan = planificar(nuevo)
            problemas = verificar_correspondencia(nuevo, plan)
            print("\nplan después:", json.loads(plan.model_dump_json()))
            print("correspondencia:", problemas or "OK")
        else:
            plan = plan_antes
            problemas = ["sin corrección"]

    salida = EVIDENCIAS / "caso_diaz_sur_resultado.json"
    salida.write_text(
        json.dumps(
            {
                "texto": texto,
                "duracion_ms": original.get("duracion_ms"),
                "v07": v07,
                "router": json.loads(borrador.model_dump_json()),
                "correccion": {
                    "frase": CORRECCION,
                    "errores": errores,
                    "meta": meta,
                    "borrador": json.loads(nuevo.model_dump_json()) if nuevo else None,
                },
                "plan": json.loads(plan.model_dump_json()),
                "correspondencia": problemas,
                "llamadas": resultado.llamadas,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\nevidence: {salida}")


if __name__ == "__main__":
    asyncio.run(main())
