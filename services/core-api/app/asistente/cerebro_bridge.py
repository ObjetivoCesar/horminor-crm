"""Puente controlado Gato -> Cerebro (2026-11-18).

Regla de la casa: Gato es la interfaz y el Cerebro la inteligencia interna.
Este puente NO duplica la logica del Cerebro: le entrega el texto al mismo
endpoint `/api/v1/cerebro/interpretar`, que ya valida modulo, interruptor y
permisos. Solo se activa cuando el mensaje lo pide de forma explicita
("cerebro, ..." / "dictado: ..."), para no secuestrar conversaciones normales.
"""

from __future__ import annotations

import re
import uuid
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
    """Arma la respuesta conversacional que ve Julio en Gato.

    Se devuelve markdown sencillo (negritas, vinetas y saltos) porque el chat
    lo pinta con ``gatoMarkdown``. Un resumen de varios encargos sin saltos se
    vuelve un muro de texto.
    """
    resumen = str(datos.get("resumen") or "").strip() or "Quedo a la espera de confirmacion."
    borrador_id = str(datos.get("borrador_id") or "").strip()
    preguntas = (datos.get("borrador") or {}).get("preguntas") or []

    lineas: list[str] = []
    bloques = [
        bloque.strip()
        for bloque in re.split(r"(?=Encargo\s+\d+:\s*)", resumen)
        if bloque.strip()
    ]
    lineas.append("**Lo que entendí**")
    if len(bloques) > 1:
        for bloque in bloques:
            encabezado = re.match(r"Encargo\s+(\d+):\s*(.*)", bloque, re.S)
            if encabezado:
                detalle = encabezado.group(2).strip()
                if detalle.lower().startswith("entendí:"):
                    detalle = detalle[len("entendí:") :].strip()
                lineas.append(
                    f"- **Encargo {encabezado.group(1)}:** {detalle}"
                )
            else:
                lineas.append(f"- {bloque}")
    else:
        detalle = bloques[0] if bloques else resumen
        if detalle.lower().startswith("entendí:"):
            detalle = detalle[len("entendí:") :].strip()
        lineas.append(detalle)

    if preguntas:
        textos = [
            str(pregunta.get("texto") or pregunta.get("clave") or "").strip()
            for pregunta in preguntas
            if isinstance(pregunta, dict)
        ]
        textos = [texto for texto in textos if texto]
        if textos:
            lineas.append("")
            lineas.append("**Antes de ejecutar necesito:**")
            lineas.extend(f"- {texto}" for texto in textos)

    if borrador_id:
        lineas.append("")
        lineas.append(f"**Borrador:** `{borrador_id}`")
        lineas.append("Revísalo y confírmalo en `/panel/cerebro`.")
    return "\n".join(lineas)


async def interpretar(
    texto: str,
    *,
    usuario: str,
    rol: str,
    nombre: str,
    contexto: str | None = None,
    conversacion_id: str | None = None,
) -> dict[str, Any]:
    """Entrega el dictado al Cerebro con la identidad y el hilo de la sesion."""
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
        uuid.UUID(str(usuario))
    except (ValueError, AttributeError):
        # La opción «Julio (base Superadmin)» puede llegar solo con el rol.
        # Se usa el perfil base; para cualquier otro rol se exige un perfil
        # real para no escalar permisos.
        if (rol or "").upper() != "SUPERADMIN":
            raise HTTPException(
                status_code=403,
                detail=(
                    "Selecciona un perfil real en «Viendo como» para dictar al "
                    "Cerebro."
                ),
            )
        headers.pop("X-Panel-User", None)
    cuerpo_json: dict[str, Any] = {"texto": cuerpo}
    if contexto and contexto.strip():
        cuerpo_json["contexto"] = contexto.strip()[:8000]
    if conversacion_id:
        cuerpo_json["conversacion_id"] = conversacion_id
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS) as cliente:
            respuesta = await cliente.post(
                f"{BASE_URL}/api/v1/cerebro/interpretar",
                json=cuerpo_json,
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
