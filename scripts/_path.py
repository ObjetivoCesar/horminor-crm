"""Permite que los scripts importen `app` tanto en Docker como en local."""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

for candidato in (RAIZ, RAIZ / "services" / "core-api"):
    if (candidato / "app").is_dir() and str(candidato) not in sys.path:
        sys.path.insert(0, str(candidato))
