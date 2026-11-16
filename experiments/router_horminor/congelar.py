"""Congela la versión del router con sus huellas.

    python -m experiments.router_horminor.congelar
"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
VERSION = "router-1.1"
ARCHIVOS = (
    "model.py",
    "prompts.py",
    "router.py",
    "correccion.py",
    "confirmacion.py",
    "cli.py",
    "lab.py",
    "tests_core.py",
    "evidencia_escenarios.py",
)


def main() -> None:
    contenido = {
        "router": VERSION,
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "archivos": {
            nombre: hashlib.sha256((BASE / nombre).read_bytes()).hexdigest()
            for nombre in ARCHIVOS
        },
    }
    (BASE / "VERSION.json").write_text(
        json.dumps(contenido, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(contenido, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
