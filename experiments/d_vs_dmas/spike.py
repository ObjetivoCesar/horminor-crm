"""Spike de paralelismo: tres lecturas simultÃ¡neas con el proveedor actual.

Mide latencia individual, latencia total en paralelo, tokens y errores.
No evalÃºa calidad. No escribe en la base.

    python -m experiments.d_vs_dmas.spike --repeticiones 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

from . import prompts
from .llm import en_paralelo, llamar, nuevo_cliente

DICTADO = (
    "Que secretarÃ­a revise si el despacho de maÃ±ana ya estÃ¡ listo y me confirme "
    "si falta algÃºn viaje. Si falta, que lo diga hoy."
)

RUNS = Path(__file__).resolve().parent / "runs"


def percentil(valores: list[int], p: float) -> int:
    if not valores:
        return 0
    ordenados = sorted(valores)
    pos = min(len(ordenados) - 1, max(0, round((p / 100) * (len(ordenados) - 1))))
    return ordenados[pos]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeticiones", type=int, default=5)
    parser.add_argument("--modelo", default="")
    args = parser.parse_args()

    RUNS.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    salida = RUNS / f"spike_{marca}.json"

    mensaje = f"HOY: 2026-11-16\nCLIENTES CONOCIDOS: (sin lista)\nDICTADO:\n{DICTADO}"
    tareas = [
        {"system": prompts.A1.replace("{claves}", ", ".join(prompts.CLAVES_HECHOS)), "user": mensaje, "max_tokens": 2000},
        {"system": prompts.A2, "user": mensaje, "max_tokens": 2000},
        {"system": prompts.A3, "user": mensaje, "max_tokens": 2000},
    ]

    registros: list[dict] = []
    latencias_paralelo: list[int] = []
    latencias_solas: list[int] = []

    async with nuevo_cliente(concurrencia=6) as cliente:
        for repeticion in range(1, args.repeticiones + 1):
            inicio = time.perf_counter()
            respuestas = await en_paralelo(cliente, tareas)
            total = int((time.perf_counter() - inicio) * 1000)
            latencias_paralelo.append(total)
            for nombre, r in zip(("A1", "A2", "A3"), respuestas):
                registros.append(
                    {
                        "repeticion": repeticion,
                        "modo": "paralelo",
                        "analizador": nombre,
                        "ok": r.get("ok"),
                        "latency_ms": r.get("latency_ms"),
                        "usage": r.get("usage"),
                        "error": r.get("error"),
                        "intentos": r.get("intentos"),
                    }
                )
            # Una llamada sola, para comparar con la latencia del paralelo.
            sola = await llamar(cliente, system=prompts.A2, user=mensaje, max_tokens=2000)
            latencias_solas.append(int(sola.get("latency_ms") or 0))
            registros.append(
                {
                    "repeticion": repeticion,
                    "modo": "sola",
                    "analizador": "A2",
                    "ok": sola.get("ok"),
                    "latency_ms": sola.get("latency_ms"),
                    "usage": sola.get("usage"),
                    "error": sola.get("error"),
                    "intentos": sola.get("intentos"),
                }
            )
            print(
                f"rep {repeticion}/{args.repeticiones}: paralelo={total} ms "
                f"sola={latencias_solas[-1]} ms "
                f"ok={sum(1 for r in respuestas if r.get('ok'))}/3"
            )

    def suma_usage(modo: str) -> dict:
        entrada = salida_tok = 0
        for r in registros:
            if r["modo"] != modo:
                continue
            usage = r.get("usage") or {}
            entrada += int(usage.get("prompt_tokens") or 0)
            salida_tok += int(usage.get("completion_tokens") or 0)
        return {"prompt_tokens": entrada, "completion_tokens": salida_tok}

    errores = [r for r in registros if not r["ok"]]
    resumen = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "modelo": args.modelo or "deepseek-chat",
        "dictado": DICTADO,
        "repeticiones": args.repeticiones,
        "paralelo": {
            "p50_ms": percentil(latencias_paralelo, 50),
            "p95_ms": percentil(latencias_paralelo, 95),
            "min_ms": min(latencias_paralelo) if latencias_paralelo else 0,
            "max_ms": max(latencias_paralelo) if latencias_paralelo else 0,
            "media_ms": round(statistics.mean(latencias_paralelo)) if latencias_paralelo else 0,
            "uso": suma_usage("paralelo"),
        },
        "sola": {
            "p50_ms": percentil(latencias_solas, 50),
            "p95_ms": percentil(latencias_solas, 95),
            "min_ms": min(latencias_solas) if latencias_solas else 0,
            "max_ms": max(latencias_solas) if latencias_solas else 0,
            "media_ms": round(statistics.mean(latencias_solas)) if latencias_solas else 0,
            "uso": suma_usage("sola"),
        },
        "errores": len(errores),
        "detalle_errores": errores[:10],
        "registros": registros,
    }
    salida.write_text(
        json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print()
    print(json.dumps({k: v for k, v in resumen.items() if k != "registros"}, ensure_ascii=False, indent=1))
    print(f"\nresultado: {salida}")


if __name__ == "__main__":
    asyncio.run(main())

