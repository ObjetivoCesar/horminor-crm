"""CLI del router: dictar → borrador → corregir → plan de confirmación.

No ejecuta tareas ni escribe en la base.

    python -m experiments.router_horminor.cli "Que secretaría revise el pago..."
    python -m experiments.router_horminor.cli "..." --corregir "no era para secretaría, era para el jefe de planta"
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from experiments.d_vs_dmas.llm import nuevo_cliente

from .confirmacion import planificar, verificar_correspondencia
from .correccion import corregir
from .router import construir

EVIDENCIAS = Path(__file__).resolve().parent / "evidencias"


def _imprimir(borrador) -> None:
    print("=" * 78)
    print(borrador.resumen)
    print("-" * 78)
    for encargo in borrador.encargos:
        print(f"\n{encargo.id}. {encargo.titulo}")
        print(f"   qué hacer: {encargo.que_hacer}")
        print(
            f"   responsable: {encargo.responsable}"
            + (" (sugerido)" if encargo.responsable_sugerido else "")
        )
        if encargo.destinatario:
            print(f"   destinatario: {encargo.destinatario} · canal {encargo.canal}")
        if encargo.resultado_esperado:
            print(f"   resultado esperado: {encargo.resultado_esperado}")
        if encargo.plazo:
            print(f"   plazo: {encargo.plazo}")
        if encargo.condiciones:
            print(f"   condiciones: {'; '.join(encargo.condiciones)}")
        if encargo.por_investigar:
            print(f"   por investigar: {'; '.join(encargo.por_investigar)}")
        if encargo.requiere_autorizacion:
            print(
                f"   requiere autorización: sí · autorizado: "
                f"{'sí' if encargo.autorizado else 'no'}"
            )
        if encargo.datos:
            print(f"   datos: {json.dumps(encargo.datos, ensure_ascii=False)}")
    if borrador.consultas:
        print(f"\nConsultas: {borrador.consultas}")
    if borrador.constancias:
        print(f"Constancias: {borrador.constancias}")
    if borrador.preguntas:
        print(f"\nPreguntas: {borrador.preguntas}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dictado")
    parser.add_argument("--corregir", default="")
    parser.add_argument("--confirmar", action="store_true")
    parser.add_argument("--autorizar", default="", help="ids separados por coma")
    args = parser.parse_args()

    EVIDENCIAS.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    salida = EVIDENCIAS / f"router_{marca}.json"
    registro: dict = {"dictado": args.dictado}

    async with nuevo_cliente(concurrencia=6) as cliente:
        resultado = await construir(cliente, args.dictado)
        if resultado.error:
            print(f"ERROR: {resultado.error}")
            return
        borrador = resultado.borrador
        _imprimir(borrador)
        registro["borrador"] = json.loads(borrador.model_dump_json())
        registro["llamadas"] = resultado.llamadas

        if args.corregir:
            print("\n" + "=" * 78)
            print(f"CORRECCIÓN: {args.corregir}")
            nuevo, errores, meta = await corregir(cliente, borrador, args.corregir)
            registro["correccion"] = {
                "frase": args.corregir,
                "errores": errores,
                "meta": meta,
            }
            if errores:
                print("No se pudo corregir:", errores)
            else:
                borrador = nuevo
                _imprimir(borrador)
                registro["borrador_corregido"] = json.loads(
                    borrador.model_dump_json()
                )

        if args.confirmar:
            autorizados = {
                x.strip() for x in args.autorizar.split(",") if x.strip()
            }
            plan = planificar(
                borrador,
                autorizaciones={x: True for x in autorizados},
            )
            problemas = verificar_correspondencia(borrador, plan)
            print("\n" + "=" * 78)
            print("PLAN DE CONFIRMACIÓN (no se ejecuta nada)")
            print(json.dumps(json.loads(plan.model_dump_json()), ensure_ascii=False, indent=1))
            print("\nCorrespondencia:", "OK" if not problemas else problemas)
            registro["plan"] = json.loads(plan.model_dump_json())
            registro["correspondencia"] = problemas

    salida.write_text(
        json.dumps(registro, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\nevidence: {salida}")


if __name__ == "__main__":
    asyncio.run(main())
