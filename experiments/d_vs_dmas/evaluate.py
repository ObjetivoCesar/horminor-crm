"""Evaluador del experimento D vs D+.

No escribe en la base. Compara contra una referencia (por defecto la preliminar
NO HUMANA, marcada como no validada). La referencia definitiva debe ser humana.

    python -m experiments.d_vs_dmas.evaluate --brazo all --limite 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path

from .arms import arm_d, arm_dplus, arm_v7
from .contracts import TIPOS_ORDEN
from .llm import nuevo_cliente
from .reference import (
    ARCHIVO_CORPUS,
    ARCHIVO_REFERENCIA,
    cargar_corpus,
    cargar_referencia,
    comparar,
)

RUNS = Path(__file__).resolve().parent / "runs"


def _percentil(valores: list[int], p: float) -> int:
    if not valores:
        return 0
    ordenados = sorted(valores)
    pos = min(len(ordenados) - 1, max(0, round((p / 100) * (len(ordenados) - 1))))
    return ordenados[pos]


def _tipos(resultado) -> Counter:
    tipos: Counter = Counter()
    for orden in resultado.conciliacion.ordenes:
        if orden.estado == "RECHAZADA":
            continue
        tipos[orden.tipo] += 1
    return tipos


def _prohibidas_disparadas(prohibidas: list[str], tipos: Counter) -> list[str]:
    """Heurístico y provisional: no sustituye la revisión humana."""
    disparadas = []
    for frase in prohibidas:
        texto = frase.upper()
        for tipo in TIPOS_ORDEN:
            if tipo in texto and tipos.get(tipo):
                disparadas.append(f"{frase} -> {tipo}")
    return disparadas


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--brazo",
        default="all",
        choices=["all", "v7", "d", "dplus", "dplus_arb"],
    )
    parser.add_argument("--limite", type=int, default=0)
    parser.add_argument("--corpus", default=str(ARCHIVO_CORPUS))
    parser.add_argument("--referencia", default=str(ARCHIVO_REFERENCIA))
    parser.add_argument("--salida", default="")
    args = parser.parse_args()

    casos = cargar_corpus(Path(args.corpus))
    if args.limite:
        casos = casos[: args.limite]
    referencia = cargar_referencia(Path(args.referencia))

    brazos = ["v7", "d", "dplus"] if args.brazo == "all" else [args.brazo]
    if args.brazo == "all":
        brazos.append("dplus_arb")

    RUNS.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    filas: list[dict] = []

    async with nuevo_cliente(concurrencia=6) as cliente:
        for caso in casos:
            ref = referencia.get(caso.id)
            for brazo in brazos:
                if brazo == "v7":
                    resultado = await arm_v7(cliente, caso.dictado)
                elif brazo == "d":
                    resultado = await arm_d(cliente, caso.dictado)
                elif brazo == "dplus":
                    resultado = await arm_dplus(cliente, caso.dictado)
                else:
                    resultado = await arm_dplus(
                        cliente, caso.dictado, con_arbitro=True
                    )
                tipos = _tipos(resultado)
                metricas = (
                    comparar(ref.tipos, tipos)
                    if ref
                    else {
                        "coinciden": 0,
                        "omitidas": 0,
                        "inventadas": 0,
                        "duplicadas": 0,
                        "esperadas": 0,
                        "propuestas": sum(tipos.values()),
                    }
                )
                filas.append(
                    {
                        "caso": caso.id,
                        "categoria": caso.categoria,
                        "brazo": brazo,
                        "ok": resultado.error is None,
                        "error": resultado.error,
                        "tipos": dict(tipos),
                        "estados": dict(
                            Counter(o.estado for o in resultado.conciliacion.ordenes)
                        ),
                        "restricciones": sum(
                            len(o.restricciones)
                            for o in resultado.conciliacion.ordenes
                        ),
                        "conflictos": len(resultado.conciliacion.conflictos),
                        "hallazgos": len(resultado.conciliacion.hallazgos),
                        "metricas": metricas,
                        "prohibidas_disparadas": _prohibidas_disparadas(
                            ref.prohibidas if ref else [], tipos
                        ),
                        "latencia_ms": resultado.latencia_ms,
                        "usage": resultado.usage_total,
                        "requiere_revision_humana": any(
                            o.estado in ("BLOQUEADA", "POR_ACLARAR", "INCOMPLETA")
                            for o in resultado.conciliacion.ordenes
                        ),
                    }
                )
                print(
                    f"{caso.id} {brazo:8} ok={resultado.error is None} "
                    f"tipos={dict(tipos)} lat={resultado.latencia_ms}"
                )

    resumen: dict = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "referencia": str(args.referencia),
        "referencia_validada": False,
        "casos": len(casos),
        "brazos": {},
    }
    for brazo in brazos:
        del_brazo = [f for f in filas if f["brazo"] == brazo]
        latencias = [f["latencia_ms"] for f in del_brazo if f["latencia_ms"]]
        resumen["brazos"][brazo] = {
            "casos": len(del_brazo),
            "errores": sum(1 for f in del_brazo if not f["ok"]),
            "coinciden": sum(f["metricas"]["coinciden"] for f in del_brazo),
            "omitidas": sum(f["metricas"]["omitidas"] for f in del_brazo),
            "inventadas": sum(f["metricas"]["inventadas"] for f in del_brazo),
            "duplicadas": sum(f["metricas"]["duplicadas"] for f in del_brazo),
            "restricciones": sum(f["restricciones"] for f in del_brazo),
            "conflictos": sum(f["conflictos"] for f in del_brazo),
            "requieren_revision": sum(
                1 for f in del_brazo if f["requiere_revision_humana"]
            ),
            "prohibidas_disparadas": sum(
                len(f["prohibidas_disparadas"]) for f in del_brazo
            ),
            "latencia_p50_ms": _percentil(latencias, 50),
            "latencia_p95_ms": _percentil(latencias, 95),
            "latencia_media_ms": round(statistics.mean(latencias)) if latencias else 0,
            "tokens_in": sum(f["usage"]["prompt_tokens"] for f in del_brazo),
            "tokens_out": sum(f["usage"]["completion_tokens"] for f in del_brazo),
        }

    salida = Path(args.salida) if args.salida else RUNS / f"eval_{marca}.json"
    salida.write_text(
        json.dumps({"resumen": resumen, "filas": filas}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print()
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    print(f"\nresultado: {salida}")
    print(
        "\nAVISO: la referencia es preliminar y NO humana. Estos números prueban "
        "el arnés, no la calidad del sistema."
    )


if __name__ == "__main__":
    asyncio.run(main())
