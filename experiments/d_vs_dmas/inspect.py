"""Inspección cualitativa de casos concretos (D vs D+).

No forma parte del agregado: sirve para ver órdenes, estados y restricciones
detrás de un caso, sin tocar los prompts ni el evaluador congelado.

    python -m experiments.d_vs_dmas.inspect E07 E14 E27
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from .arms import arm_d, arm_dplus
from .llm import nuevo_cliente
from .reference import cargar_corpus

RUNS = Path(__file__).resolve().parent / "runs"


async def main() -> None:
    ids = [x for x in sys.argv[1:] if x.startswith("E")]
    if not ids:
        print("uso: python -m experiments.d_vs_dmas.inspect E07 E14")
        return
    corpus = {c.id: c for c in cargar_corpus()}
    salida = []
    async with nuevo_cliente(concurrencia=6) as cliente:
        for caso_id in ids:
            caso = corpus.get(caso_id)
            if caso is None:
                print(f"{caso_id}: no existe")
                continue
            print("=" * 76)
            print(f"{caso.id} — {caso.categoria}")
            print(caso.dictado)
            for nombre, fn in (("D", arm_d), ("D+", arm_dplus)):
                resultado = await fn(cliente, caso.dictado)
                print(f"\n  [{nombre}] error={resultado.error}")
                for orden in resultado.conciliacion.ordenes:
                    print(
                        f"   - {orden.tipo:14} {orden.estado:12} "
                        f"resp={orden.responsable_ejecucion} dest={orden.destinatario_comunicacion} "
                        f"medio={orden.medio} ambito={orden.ambito}"
                    )
                    if orden.restricciones:
                        print(f"       restricciones: {orden.restricciones}")
                    if orden.motivo_estado:
                        print(f"       motivo: {orden.motivo_estado}")
                    print(f"       citas: {orden.citas[:2]}")
                for conflicto in resultado.conciliacion.conflictos:
                    print(f"   ! conflicto {conflicto.codigo}: {conflicto.detalle}")
                salida.append(
                    {
                        "caso": caso.id,
                        "categoria": caso.categoria,
                        "dictado": caso.dictado,
                        "brazo": nombre,
                        "error": resultado.error,
                        "ordenes": [
                            o.model_dump() for o in resultado.conciliacion.ordenes
                        ],
                        "conflictos": [
                            c.model_dump() for c in resultado.conciliacion.conflictos
                        ],
                        "hallazgos": [
                            h.model_dump() for h in resultado.conciliacion.hallazgos
                        ],
                    }
                )
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = RUNS / f"inspect_{marca}.json"
    destino.write_text(
        json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\nresultado: {destino}")


if __name__ == "__main__":
    asyncio.run(main())
