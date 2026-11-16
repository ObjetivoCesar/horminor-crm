"""Congela las versiones del experimento con sus huellas SHA-256.

No modifica nada. Escribe FREEZE.json una sola vez (o con --forzar).

    python -m experiments.d_vs_dmas.freeze
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

from .contracts import CONTRACT_VERSION
from .prompts import EXPERIMENT_VERSION, PROMPT_VERSIONS
from .reconcile import RECONCILE_VERSION

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[1]
CORPUS = REPO / "docs" / "HORMINOR_CORPUS_D_VS_DMAS_40"

ARCHIVOS_EXPERIMENTO = (
    "prompts.py",
    "contracts.py",
    "reconcile.py",
    "arms.py",
    "llm.py",
    "evaluate.py",
    "reference.py",
    "spike.py",
)


def _sha256(ruta: Path) -> str:
    digest = hashlib.sha256()
    digest.update(ruta.read_bytes())
    return digest.hexdigest()


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True
        ).strip()
    except Exception:
        return "desconocido"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forzar", action="store_true")
    args = parser.parse_args()

    destino = BASE / "FREEZE.json"
    if destino.exists() and not args.forzar:
        print(f"Ya congelado: {destino}. Usa --forzar solo si se reinicia el experimento.")
        print(destino.read_text(encoding="utf-8"))
        return

    contenido = {
        "experimento": EXPERIMENT_VERSION,
        "contratos": CONTRACT_VERSION,
        "conciliacion": RECONCILE_VERSION,
        "prompts": PROMPT_VERSIONS,
        "modelo": "deepseek-chat",
        "commit": _commit(),
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "archivos": {
            nombre: _sha256(BASE / nombre) for nombre in ARCHIVOS_EXPERIMENTO
        },
        "corpus": {
            ruta.name: _sha256(ruta)
            for ruta in sorted(CORPUS.glob("*"))
            if ruta.is_file()
        },
    }
    destino.write_text(
        json.dumps(contenido, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(contenido, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
