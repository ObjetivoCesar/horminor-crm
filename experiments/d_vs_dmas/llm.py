"""Cliente LLM del experimento: mide latencia, tokens y errores.

No usa el cliente productivo. Lee DEEPSEEK_API_KEY del entorno o del .env.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
MODEL = os.getenv("EXPERIMENT_MODEL", "deepseek-chat")
TIMEOUT = float(os.getenv("EXPERIMENT_TIMEOUT", "60"))


def _cargar_env() -> None:
    if os.getenv("DEEPSEEK_API_KEY"):
        return
    env = Path(__file__).resolve().parents[2] / ".env"
    if not env.exists():
        return
    for linea in env.read_text(encoding="utf-8", errors="ignore").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        if clave.strip() == "DEEPSEEK_API_KEY" and valor.strip():
            os.environ["DEEPSEEK_API_KEY"] = valor.strip()
            return


class RespuestaLLM(dict):
    pass


async def llamar(
    cliente: httpx.AsyncClient,
    *,
    system: str,
    user: str,
    max_tokens: int = 2500,
) -> RespuestaLLM:
    _cargar_env()
    clave = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not clave:
        return RespuestaLLM(
            ok=False, data=None, usage={}, latency_ms=0, error="SIN_CLAVE", intentos=0
        )

    mensajes = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    inicio = time.perf_counter()
    ultimo = ""
    for intento in range(1, 3):
        try:
            respuesta = await cliente.post(
                f"{BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {clave}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MODEL,
                    "messages": mensajes,
                    "temperature": 0,
                    "max_tokens": max_tokens,
                    "response_format": {"type": "json_object"},
                },
            )
            if respuesta.status_code >= 400:
                raise RuntimeError(
                    f"HTTP_{respuesta.status_code}: {(respuesta.text or '')[:200]}"
                )
            cuerpo = respuesta.json()
            contenido = cuerpo["choices"][0]["message"]["content"]
            datos = json.loads(contenido)
            return RespuestaLLM(
                ok=True,
                data=datos,
                usage=cuerpo.get("usage") or {},
                latency_ms=int((time.perf_counter() - inicio) * 1000),
                error=None,
                intentos=intento,
            )
        except (ValueError, KeyError, TypeError, RuntimeError) as exc:
            ultimo = f"{type(exc).__name__}: {exc}"
            if intento == 1:
                mensajes.append(
                    {
                        "role": "user",
                        "content": (
                            "El JSON no cumple el contrato. Corrigelo y devuelve "
                            f"solo JSON valido. Error: {ultimo}"
                        ),
                    }
                )
    return RespuestaLLM(
        ok=False,
        data=None,
        usage={},
        latency_ms=int((time.perf_counter() - inicio) * 1000),
        error=ultimo,
        intentos=2,
    )


def nuevo_cliente(concurrencia: int = 6) -> httpx.AsyncClient:
    limites = httpx.Limits(
        max_connections=concurrencia, max_keepalive_connections=concurrencia
    )
    return httpx.AsyncClient(timeout=TIMEOUT, limits=limites)


async def en_paralelo(
    cliente: httpx.AsyncClient, tareas: list[dict[str, Any]]
) -> list[RespuestaLLM]:
    async def uno(tarea: dict[str, Any]) -> RespuestaLLM:
        return await llamar(
            cliente,
            system=tarea["system"],
            user=tarea["user"],
            max_tokens=tarea.get("max_tokens", 2500),
        )

    return list(await asyncio.gather(*(uno(t) for t in tareas)))
