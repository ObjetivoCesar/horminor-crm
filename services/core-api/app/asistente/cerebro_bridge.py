"""Puente controlado Gato -> Cerebro (2026-11-18).

Regla de la casa: Gato es la interfaz y el Cerebro la inteligencia interna.
Este puente NO duplica la logica del Cerebro: le entrega el texto al mismo
endpoint `/api/v1/cerebro/interpretar`, que ya valida modulo, interruptor y
permisos. Solo se activa cuando el mensaje lo pide de forma explicita
("cerebro, ..." / "dictado: ..."), para no secuestrar conversaciones normales.
"""

from __future__ import annotations

import re
from typing import Any

import httpx
from fastapi import HTTPException

BASE_URL = "http://127.0.0.1:8000"
TIMEOUT_SEGUNDOS = 120.0

_PREFIJO = re.compile(
    r"^\s*(?:cerebro|dictado|dicta)\s*[:,]\s*", re.IGNORECASE
)

_PALABRAS = ("cerebro", "dictado:", "dicta:", "cerebro:")


def es_dictado(texto: str) -> bool:
    """True solo si el mensaje pide explicitamente al Cerebro."""
    limpio = (texto or "").strip().lower()
    if not limpio:
        return False
    return any(
        limpio == palabra
        or limpio.startswith(palabra + " ")
        or limpio.startswith(palabra + ":")
        or limpio.startswith(palabra + ",")
        for palabra in _PALABRAS
    )


def texto_limpio(texto: str) -> str:
    """Quita el prefijo con el que se invoca al Cerebro."""
    return _PREFIJO.sub("", texto or "", count=1).strip()


def mensaje_de_resumen(datos: dict[str, Any]) -> str:
    """Arma la respuesta conversacional que ve Julio en Gato."""
    resumen = str(datos.get("resumen") or "").strip() or "Quedo a la espera de confirmacion."
    borrador_id = str(datos.get("borrador_id") or "").strip()
    preguntas = (datos.get("borrador") or {}).get("preguntas") or []
    partes = [resumen]
    if preguntas:
        textos = [
            str(p.get("texto") or p.get("clave") or "").strip()
            for p in preguntas
            if isinstance(p, dict)
        ]
        textos = [t for t in textos if t]
        if textos:
            partes.append("Antes de ejecutar necesito: " + "; ".join(textos) + ".")
    if borrador_id:
        partes.append(
            "Quedo como borrador; revisalo y confirmalo en /panel/cerebro."
        )
    return " ".join(partes)


async def interpretar(
    texto: str,
    *,
    usuario: str,
    rol: str,
    nombre: str,
) -> dict[str, Any]:
    """Entrega el dictado al Cerebro con la identidad de la sesion."""
    cuerpo = texto_limpio(texto)
    if not cuerpo:
        raise HTTPException(
            status_code=422, detail="el dictado llego vacio despues del prefijo"
        )
    headers = {
        "X-Panel-User": usuario,
        "X-Panel-Role": (rol or "").lower(),
        "X-Panel-Name": nombre,
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS) as cliente:
            respuesta = await cliente.post(
                f"{BASE_URL}/api/v1/cerebro/interpretar",
                json={"texto": cuerpo},
                headers=headers,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503, detail=f"no pude hablar con el Cerebro: {exc}"
        ) from exc
    if respuesta.status_code >= 400:
        detalle = respuesta.text[:300]
        raise HTTPException(status_code=respuesta.status_code, detail=detalle)
    datos = respuesta.json()
    if not isinstance(datos, dict):
        raise HTTPException(status_code=502, detail="respuesta inesperada del Cerebro")
    return datos
