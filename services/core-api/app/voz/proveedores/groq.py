"""Adaptador Groq (Whisper) con palabras y tiempos.

Groq expone un endpoint compatible con OpenAI. Con ``verbose_json`` y
``timestamp_granularities[]=word`` devuelve el texto, los segmentos y las
palabras con ``start``/``end``. No devuelve confianza por palabra: se usa
``exp(avg_logprob)`` del segmento que la contiene como **proxy**, no como
probabilidad calibrada.
"""

from __future__ import annotations

import io
import math
import os
from decimal import Decimal
from typing import Any

import httpx

from ..stt import ResultadoSTT

BASE_URL = os.getenv(
    "GROQ_BASE_URL", "https://api.groq.com/openai/v1"
).rstrip("/")
MODELO_POR_DEFECTO = os.getenv("GROQ_MODEL", "whisper-large-v3")
TIMEOUT = float(os.getenv("GROQ_TIMEOUT", "40"))

# Precio público por hora de audio (USD). Si cambia, se ajusta por entorno.
PRECIO_HORA = {
    "whisper-large-v3": Decimal("0.111"),
    "whisper-large-v3-turbo": Decimal("0.04"),
}


def _confianza(segmento: dict[str, Any]) -> float | None:
    logprob = segmento.get("avg_logprob")
    if logprob is None:
        return None
    try:
        valor = math.exp(float(logprob))
    except (OverflowError, TypeError, ValueError):
        return None
    return max(0.0, min(1.0, valor))


def parsear_respuesta(payload: dict[str, Any], modelo: str) -> ResultadoSTT:
    """Convierte la respuesta de Groq en el contrato del componente de voz."""
    texto = str(payload.get("text") or "").strip()
    segmentos_crudos = payload.get("segments") or []
    palabras_crudas = payload.get("words") or []

    segmentos: list[dict[str, Any]] = []
    for segmento in segmentos_crudos:
        inicio = segmento.get("start")
        fin = segmento.get("end")
        if inicio is None or fin is None:
            continue
        segmentos.append(
            {
                "start_ms": int(float(inicio) * 1000),
                "end_ms": int(float(fin) * 1000),
                "speaker": "NO_DETERMINADO",
                "text": str(segmento.get("text") or "").strip(),
                "confidence": _confianza(segmento),
            }
        )

    def confianza_en(momento: float) -> float | None:
        for segmento, crudo in zip(segmentos, segmentos_crudos):
            if segmento["start_ms"] / 1000 <= momento <= segmento["end_ms"] / 1000:
                return _confianza(crudo)
        return None

    palabras: list[dict[str, Any]] = []
    for palabra in palabras_crudas:
        inicio = palabra.get("start")
        fin = palabra.get("end")
        if inicio is None or fin is None:
            continue
        palabras.append(
            {
                "palabra": str(palabra.get("word") or "").strip(),
                "inicio_ms": int(float(inicio) * 1000),
                "fin_ms": int(float(fin) * 1000),
                "confianza": confianza_en(float(inicio)),
            }
        )

    duracion_ms = max((s["end_ms"] for s in segmentos), default=0)
    confianzas = [s["confidence"] for s in segmentos if s["confidence"] is not None]
    confianza_global = (
        sum(confianzas) / len(confianzas) if confianzas else None
    )

    precio = PRECIO_HORA.get(modelo, Decimal("0"))
    costo = (Decimal(duracion_ms) / Decimal(3_600_000)) * precio

    if not texto:
        return ResultadoSTT(
            estado="FALLIDO",
            proveedor="groq",
            modelo=modelo,
            error="STT_SIN_TEXTO: el proveedor no devolvió texto",
        )

    return ResultadoSTT(
        estado="COMPLETADO",
        proveedor="groq",
        modelo=modelo,
        texto_crudo=texto,
        segmentos=segmentos,
        palabras=palabras,
        confianza=confianza_global,
        idioma=str(payload.get("language") or "es"),
        duracion_ms=duracion_ms or None,
        costo_usd=costo,
    )


class GroqSTT:
    """Proveedor Groq/Whisper. No inventa texto si falla."""

    nombre = "groq"

    def __init__(
        self,
        api_key: str,
        *,
        modelo: str | None = None,
        timeout: float | None = None,
        http_client: Any = None,
    ) -> None:
        self.api_key = api_key
        self.modelo = modelo or MODELO_POR_DEFECTO
        self.timeout = timeout if timeout is not None else TIMEOUT
        self._http = http_client

    async def transcribir(
        self, datos: bytes, mime: str, *, idioma: str = "es-EC"
    ) -> ResultadoSTT:
        if not self.api_key:
            return ResultadoSTT(
                estado="DEGRADADO_SIN_CREDENCIAL",
                proveedor=self.nombre,
                modelo=self.modelo,
                error="GROQ_API_KEY no configurada",
            )

        archivos = {
            "file": ("audio.ogg", io.BytesIO(datos), mime or "audio/ogg")
        }
        campos = {
            "model": self.modelo,
            "language": "es",
            "response_format": "verbose_json",
            "timestamp_granularities[]": ["word", "segment"],
            "temperature": "0",
        }
        cabeceras = {"Authorization": f"Bearer {self.api_key}"}

        cliente = self._http
        propio = cliente is None
        if cliente is None:
            cliente = httpx.AsyncClient(timeout=self.timeout)
        try:
            respuesta = await cliente.post(
                f"{BASE_URL}/audio/transcriptions",
                headers=cabeceras,
                files=archivos,
                data=campos,
            )
        except Exception as exc:  # timeout, DNS, red
            return ResultadoSTT(
                estado="FALLIDO",
                proveedor=self.nombre,
                modelo=self.modelo,
                error=f"GROQ_RED: {type(exc).__name__}: {exc}",
            )
        finally:
            if propio:
                await cliente.aclose()

        if respuesta.status_code >= 400:
            detalle = (respuesta.text or "")[:300]
            return ResultadoSTT(
                estado="FALLIDO",
                proveedor=self.nombre,
                modelo=self.modelo,
                error=f"GROQ_HTTP_{respuesta.status_code}: {detalle}",
            )
        try:
            payload = respuesta.json()
        except ValueError:
            return ResultadoSTT(
                estado="FALLIDO",
                proveedor=self.nombre,
                modelo=self.modelo,
                error="GROQ_JSON_INVALIDO",
            )
        return parsear_respuesta(payload, self.modelo)
