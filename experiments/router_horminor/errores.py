"""Registro append-only de correcciones y errores del router (experimento).

No toca la base de negocio. Guarda qué entendió el sistema, qué corrigió Julio
y con qué mensaje, para poder seguir el trazo de los informes de errores.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUTA = Path(__file__).resolve().parent / "evidencias" / "errores.jsonl"


def registrar(
    *,
    mensaje: str,
    cambios: list[dict[str, Any]],
    version_antes: int,
    version_despues: int,
    contexto: dict[str, Any] | None = None,
    tipo: str = "CORRECCION",
    origen: str = "LABORATORIO",
) -> dict[str, Any]:
    """Agrega una entrada. Nunca reescribe las anteriores."""
    RUTA.parent.mkdir(parents=True, exist_ok=True)
    entrada = {
        "id": uuid.uuid4().hex[:12],
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tipo": tipo,
        "origen": origen,
        "mensaje_julio": mensaje,
        "version_antes": version_antes,
        "version_despues": version_despues,
        "cambios": cambios,
        "contexto": contexto or {},
    }
    with RUTA.open("a", encoding="utf-8") as archivo:
        archivo.write(json.dumps(entrada, ensure_ascii=False) + "\n")
    return entrada


def listar(limite: int = 20) -> list[dict[str, Any]]:
    if not RUTA.exists():
        return []
    lineas = RUTA.read_text(encoding="utf-8").splitlines()
    salida = []
    for linea in lineas[-limite:]:
        linea = linea.strip()
        if not linea:
            continue
        try:
            salida.append(json.loads(linea))
        except json.JSONDecodeError:
            continue
    return list(reversed(salida))
