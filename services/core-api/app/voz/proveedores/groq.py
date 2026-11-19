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


def _limpiar_clave(valor: Any) -> str:
    """Quita el espacio que suele quedar despues del ``=`` en el .env."""
    return str(valor or "").strip().strip('"').strip("'").strip()


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
        self.api_key = _limpiar_clave(api_key)
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


# Errores donde tiene sentido probar la siguiente clave: credencial invalida,
# limite de uso o red caida. Un 400/413/415 es del audio y se repite igual.
_REINTENTABLES = ("GROQ_HTTP_401", "GROQ_HTTP_403", "GROQ_HTTP_429", "GROQ_RED")


class GroqCascada:
    """Prueba varias claves de Groq en orden hasta que una responda.

    Existe porque el operador puede dejar una clave principal y una de respaldo
    (``GROQ_API_KEY`` y ``GROQ_API_KEY2``). Solo se pasa a la siguiente cuando
    el fallo es de credencial, cuota o red; si el audio es invalido se devuelve
    el error sin gastar las demas claves.
    """

    nombre = "groq"

    def __init__(
        self,
        api_keys: list[str],
        *,
        modelo: str | None = None,
        timeout: float | None = None,
        http_client: Any = None,
    ) -> None:
        claves = [c for c in (_limpiar_clave(k) for k in api_keys) if c]
        # Sin duplicados, conservando el orden de prioridad.
        vistas: set[str] = set()
        self.api_keys = [c for c in claves if not (c in vistas or vistas.add(c))]
        self.modelo = modelo or MODELO_POR_DEFECTO
        self.timeout = timeout
        self._http = http_client

    def __repr__(self) -> str:  # sin exponer las claves
        return f"GroqCascada(claves={len(self.api_keys)}, modelo={self.modelo!r})"

    async def transcribir(
        self, datos: bytes, mime: str, *, idioma: str = "es-EC"
    ) -> ResultadoSTT:
        if not self.api_keys:
            return ResultadoSTT(
                estado="DEGRADADO_SIN_CREDENCIAL",
                proveedor=self.nombre,
                modelo=self.modelo,
                error="GROQ_API_KEY no configurada",
            )
        errores: list[str] = []
        for indice, clave in enumerate(self.api_keys, start=1):
            proveedor = GroqSTT(
                api_key=clave,
                modelo=self.modelo,
                timeout=self.timeout,
                http_client=self._http,
            )
            resultado = await proveedor.transcribir(datos, mime, idioma=idioma)
            if resultado.estado == "COMPLETADO":
                return resultado
            error = resultado.error or ""
            if not any(marca in error for marca in _REINTENTABLES):
                return resultado
            errores.append(f"clave {indice}: {error}")
            if indice < len(self.api_keys):
                continue
        return ResultadoSTT(
            estado="FALLIDO",
            proveedor=self.nombre,
            modelo=self.modelo,
            error="GROQ_TODAS_LAS_CLAVES_FALLARON: " + " | ".join(errores),
        )
