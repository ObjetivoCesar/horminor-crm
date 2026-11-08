"""Modulo 1 - Juez Binario "Jeb" (compuertas SÍ / NO).

El PDR es explicito: no hay chatbot conversacional. Cada mensaje, ya agrupado
por el debounce, pasa por una compuerta que responde un objeto estricto::

    {"cumple": bool, "codigo_accion": str, "confianza": float,
     "datos_extraidos": dict}

Hay dos proveedores intercambiables:

- :class:`GeminiFlashBooleanJudge` -> Gemini Flash con ``responseMimeType``
  forzado a ``application/json``. Es el Juez de produccion.
- :class:`DeterministicRuleMockJudge` -> reglas de palabras clave. Es el Juez
  de tests y el *fallback* automatico si no hay API key, no hay internet o el
  modelo devuelve algo que no cumple el contrato.

La matematica del Modulo 2 nunca pasa por aqui: el Juez solo decide SÍ/NO.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from .models import extraer_referencia, normalizar_texto

log = logging.getLogger(__name__)

COMPUERTA_DESPACHO = "GATE_1_DESPACHO"
COMPUERTA_CLIENTE = "GATE_2_CLIENTE"
COMPUERTA_EVIDENCIA = "GATE_3_EVIDENCIA"
COMPUERTA_LEAD = "GATE_4_LEAD"

COMPUERTAS = (
    COMPUERTA_DESPACHO,
    COMPUERTA_CLIENTE,
    COMPUERTA_EVIDENCIA,
    COMPUERTA_LEAD,
)

ACCION_DESPACHO_CONFIRMADO = "REGISTRAR_SALIDA_PLANTA"
ACCION_DESPACHO_NO_CONFIRMADO = "SIN_ACCION"
ACCION_RECEPCION_CONFORME = "SELLAR_RECEPCION_CLIENTE"
ACCION_RECLAMO = "ALERTAR_CENTINELA_RECLAMO"
ACCION_ESPERAR_CONFIRMACION = "ESPERAR_CONFIRMACION"
ACCION_EVIDENCIA_VALIDA = "SUBIR_EVIDENCIA_BUNNY"
ACCION_EVIDENCIA_FALTANTE = "SOLICITAR_EVIDENCIA"
ACCION_LEAD_CALIFICADO = "CREAR_PROSPECTO"
ACCION_LEAD_NO_CALIFICADO = "IGNORAR"


class ErrorJuez(ValueError):
    """El proveedor devolvio algo que no cumple el contrato binario."""


@dataclass(frozen=True)
class Veredicto:
    """Salida estricta de una compuerta."""

    cumple: bool
    codigo_accion: str
    confianza: float
    datos_extraidos: dict[str, Any] = field(default_factory=dict)
    proveedor: str = "deterministico"

    def a_dict(self) -> dict[str, Any]:
        return {
            "cumple": bool(self.cumple),
            "codigo_accion": self.codigo_accion,
            "confianza": round(float(self.confianza), 4),
            "datos_extraidos": self.datos_extraidos,
            "proveedor": self.proveedor,
        }


class BooleanJudgeProvider(Protocol):
    """Contrato del Juez Binario. Cualquier proveedor debe respetarlo."""

    nombre: str

    async def evaluar(
        self,
        *,
        compuerta: str,
        texto: str,
        contexto: dict[str, Any] | None = None,
    ) -> Veredicto: ...


# ---------------------------------------------------------------------------
# Reglas deterministicas (fallback y tests)
# ---------------------------------------------------------------------------
_SALIDA = (
    r"\bsalio\b",
    r"\bsalida\b",
    r"\bsaliendo\b",
    r"\bya sali",
    r"\bdespach",
    r"\ben ruta\b",
    r"\bva en camino\b",
    r"\bcamino a obra\b",
    r"\bconfirmo (la )?salida\b",
)
_NEGACION_SALIDA = (
    "no salio",
    "no ha salido",
    "todavia no",
    "aun no",
    "sin salir",
    "no despach",
    "se demora",
    "no esta listo",
    "falta cargar",
    "esperando",
)
_CONFIRMA_CLIENTE = (
    "recibi",
    "recibido",
    "recepcion",
    "llego",
    "llegaron",
    "todo bien",
    "todo correcto",
    "conforme",
    "de acuerdo",
    "sin problema",
    "perfecto",
    "ok",
    "gracias",
)
_RECLAMO = (
    "demora",
    "demoro",
    "retras",
    "tarde",
    "tardanza",
    "queja",
    "reclamo",
    "no llego",
    "no ha llegado",
    "no habia llegado",
    "falt",
    "mal estado",
    "endurecid",
    "fraguado",
    "seco",
    "inconformidad",
    "pesimo",
    "no sirve",
    "quiero dejar constancia",
)
_LEAD = (
    "hormigon",
    "premezclado",
    "planta movil",
    "cotiza",
    "cotizacion",
    "presupuesto",
    "precio",
    "cuanto cuesta",
    "cuanto vale",
    "metros cubicos",
    "metro cubico",
    "m3",
    "cubos",
    "necesito concreto",
)
_RESPUESTA_SI = ("si", "sí", "claro", "correcto", "confirmo", "confirmado")


def _contiene(texto: str, agujas: tuple[str, ...]) -> bool:
    return any(aguja in texto for aguja in agujas)


def _contiene_regex(texto: str, patrones: tuple[str, ...]) -> bool:
    return any(re.search(patron, texto) for patron in patrones)


class DeterministicRuleMockJudge:
    """Juez de reglas: rapido, offline y sin costo.

    No pretende entender lenguaje natural; solo cubre las frases operativas
    que el PDR describe. Si el texto es ambiguo, responde ``cumple=False``:
    es preferible pedir confirmacion a sellar un viaje por error.
    """

    nombre = "deterministico"

    async def evaluar(
        self,
        *,
        compuerta: str,
        texto: str,
        contexto: dict[str, Any] | None = None,
    ) -> Veredicto:
        limpio = normalizar_texto(texto)
        datos = self._datos_extraidos(texto, limpio)
        ctx = contexto or {}

        if compuerta == COMPUERTA_DESPACHO:
            hay_salida = _contiene_regex(limpio, _SALIDA)
            hay_negacion = _contiene(limpio, _NEGACION_SALIDA)
            cumple = hay_salida and not hay_negacion
            return Veredicto(
                cumple=cumple,
                codigo_accion=(
                    ACCION_DESPACHO_CONFIRMADO
                    if cumple
                    else ACCION_DESPACHO_NO_CONFIRMADO
                ),
                confianza=0.9 if cumple else 0.6,
                datos_extraidos=datos,
                proveedor=self.nombre,
            )

        if compuerta == COMPUERTA_CLIENTE:
            if _contiene(limpio, _RECLAMO):
                return Veredicto(
                    cumple=False,
                    codigo_accion=ACCION_RECLAMO,
                    confianza=0.9,
                    datos_extraidos=datos,
                    proveedor=self.nombre,
                )
            if _contiene(limpio, _CONFIRMA_CLIENTE) or limpio.strip() in _RESPUESTA_SI:
                return Veredicto(
                    cumple=True,
                    codigo_accion=ACCION_RECEPCION_CONFORME,
                    confianza=0.85,
                    datos_extraidos=datos,
                    proveedor=self.nombre,
                )
            return Veredicto(
                cumple=False,
                codigo_accion=ACCION_ESPERAR_CONFIRMACION,
                confianza=0.5,
                datos_extraidos=datos,
                proveedor=self.nombre,
            )

        if compuerta == COMPUERTA_EVIDENCIA:
            adjuntos = int(ctx.get("media") or 0)
            cumple = adjuntos > 0
            return Veredicto(
                cumple=cumple,
                codigo_accion=(
                    ACCION_EVIDENCIA_VALIDA if cumple else ACCION_EVIDENCIA_FALTANTE
                ),
                confianza=0.95 if cumple else 0.7,
                datos_extraidos={**datos, "adjuntos": adjuntos},
                proveedor=self.nombre,
            )

        if compuerta == COMPUERTA_LEAD:
            cumple = _contiene(limpio, _LEAD)
            return Veredicto(
                cumple=cumple,
                codigo_accion=(
                    ACCION_LEAD_CALIFICADO if cumple else ACCION_LEAD_NO_CALIFICADO
                ),
                confianza=0.8 if cumple else 0.55,
                datos_extraidos=datos,
                proveedor=self.nombre,
            )

        raise ErrorJuez(f"Compuerta desconocida: {compuerta}")

    @staticmethod
    def _datos_extraidos(texto: str, limpio: str) -> dict[str, Any]:
        referencia = extraer_referencia(texto)
        datos: dict[str, Any] = {
            "orden": referencia.orden_numero,
            "viaje": referencia.viaje_numero,
            "mixer": referencia.mixer_codigo,
        }
        resistencia = re.search(r"\bFC[-\s]?(\d{3})\b", limpio, re.IGNORECASE)
        if resistencia:
            datos["resistencia"] = f"FC-{resistencia.group(1)}"
        return {k: v for k, v in datos.items() if v is not None}


# ---------------------------------------------------------------------------
# Gemini Flash (proveedor de produccion)
# ---------------------------------------------------------------------------
_INSTRUCCION_BASE = (
    "Eres un juez binario de operaciones de una concretera. No conversas ni "
    "explicas: clasificas un mensaje de WhatsApp contra UNA pregunta cerrada. "
    "Responde EXCLUSIVAMENTE un objeto JSON con las claves "
    '"cumple" (booleano), "codigo_accion" (texto), "confianza" (numero entre 0 y 1) '
    'y "datos_extraidos" (objeto). No agregues texto fuera del JSON.'
)

_PREGUNTAS = {
    COMPUERTA_DESPACHO: (
        "¿El bodeguero esta confirmando que un camion mixer acaba de salir de "
        "planta hacia la obra? Si el mensaje dice que aun no sale, que falta "
        "cargar o que hay demora, responde cumple=false."
    ),
    COMPUERTA_CLIENTE: (
        "¿El cliente confirma explicitamente que recibio el hormigon conforme y "
        "sin reclamos de retraso? Si reporta demora, queja, faltante o mal "
        "estado, responde cumple=false con codigo_accion=" + ACCION_RECLAMO
    ),
    COMPUERTA_EVIDENCIA: (
        "¿El archivo recibido es evidencia valida de obra, guia de remision o "
        "vaciado de hormigon enviada por el chofer?"
    ),
    COMPUERTA_LEAD: (
        "¿El remitente (un numero no registrado) esta solicitando cotizacion "
        "de hormigon premezclado o alquiler de planta movil?"
    ),
}


def _parsear_veredicto(crudo: str, proveedor: str) -> Veredicto:
    """Valida el contrato estricto. Cualquier desvio lanza ``ErrorJuez``."""
    try:
        datos = json.loads(crudo)
    except (TypeError, ValueError) as exc:
        raise ErrorJuez(f"salida no es JSON: {exc}") from exc
    if not isinstance(datos, dict):
        raise ErrorJuez("salida no es un objeto JSON")

    cumple = datos.get("cumple")
    if not isinstance(cumple, bool):
        raise ErrorJuez(f"'cumple' no es booleano: {cumple!r}")

    codigo = datos.get("codigo_accion")
    if not isinstance(codigo, str) or not codigo.strip():
        raise ErrorJuez(f"'codigo_accion' invalido: {codigo!r}")

    confianza = datos.get("confianza")
    if isinstance(confianza, bool) or not isinstance(confianza, (int, float)):
        raise ErrorJuez(f"'confianza' invalida: {confianza!r}")
    confianza = min(max(float(confianza), 0.0), 1.0)

    extra = datos.get("datos_extraidos")
    if not isinstance(extra, dict):
        raise ErrorJuez(f"'datos_extraidos' invalido: {extra!r}")

    return Veredicto(
        cumple=cumple,
        codigo_accion=codigo.strip(),
        confianza=confianza,
        datos_extraidos=extra,
        proveedor=proveedor,
    )


class GeminiFlashBooleanJudge:
    """Gemini Flash con salida JSON forzada y fallback deterministico."""

    nombre = "gemini_flash"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gemini-2.5-flash",
        timeout: float = 8.0,
        fallback: BooleanJudgeProvider | None = None,
        http_client: httpx.AsyncClient | None = None,
        endpoint: str = "https://generativelanguage.googleapis.com/v1beta",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._fallback = fallback or DeterministicRuleMockJudge()
        self._http = http_client
        self._endpoint = endpoint.rstrip("/")

    async def evaluar(
        self,
        *,
        compuerta: str,
        texto: str,
        contexto: dict[str, Any] | None = None,
    ) -> Veredicto:
        try:
            return await self._llamar(compuerta, texto, contexto or {})
        except Exception as exc:  # red, cuota, JSON invalido: nunca se cae el bot
            log.warning("Juez Gemini no disponible (%s); se usa el deterministico", exc)
            veredicto = await self._fallback.evaluar(
                compuerta=compuerta, texto=texto, contexto=contexto
            )
            return Veredicto(
                cumple=veredicto.cumple,
                codigo_accion=veredicto.codigo_accion,
                confianza=veredicto.confianza,
                datos_extraidos={
                    **veredicto.datos_extraidos,
                    "fallback": type(exc).__name__,
                },
                proveedor="deterministico_fallback",
            )

    async def _llamar(
        self, compuerta: str, texto: str, contexto: dict[str, Any]
    ) -> Veredicto:
        pregunta = _PREGUNTAS.get(compuerta)
        if pregunta is None:
            raise ErrorJuez(f"Compuerta desconocida: {compuerta}")

        prompt = (
            f"{_INSTRUCCION_BASE}\n\nPREGUNTA: {pregunta}\n\n"
            f"CONTEXTO: {json.dumps(contexto, ensure_ascii=False)}\n"
            f"MENSAJE: {texto or '(sin texto)'}"
        )
        cuerpo = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 300,
                "responseMimeType": "application/json",
            },
        }
        url = (
            f"{self._endpoint}/models/{self._model}:generateContent"
            f"?key={self._api_key}"
        )

        if self._http is not None:
            respuesta = await self._http.post(url, json=cuerpo, timeout=self._timeout)
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as cliente:
                respuesta = await cliente.post(url, json=cuerpo)
        respuesta.raise_for_status()

        datos = respuesta.json()
        try:
            crudo = datos["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ErrorJuez(f"respuesta sin texto: {datos!r}") from exc

        return _parsear_veredicto(crudo, self.nombre)


def construir_juez(
    *, gemini_api_key: str | None, model: str, timeout: float, http_client: Any = None
) -> BooleanJudgeProvider:
    """Devuelve Gemini si hay clave; si no, el Juez deterministico."""
    deterministico = DeterministicRuleMockJudge()
    if not (gemini_api_key or "").strip():
        return deterministico
    return GeminiFlashBooleanJudge(
        api_key=gemini_api_key.strip(),
        model=model,
        timeout=timeout,
        fallback=deterministico,
        http_client=http_client,
    )
