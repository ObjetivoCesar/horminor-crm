"""Proveedor DeepSeek con tool calling sobre los pilares (opcional).

Sin DEEPSEEK_API_KEY el orquestador usa el modo determinista. Con clave, este
módulo arma las tools desde `pilares.py` filtradas por rol y ejecuta de 1 a 3
pasos, igual que el modo determinista.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from . import pilares
from .persona import render_prompt

MODELO = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
TIMEOUT = float(os.getenv("DEEPSEEK_TIMEOUT", "20"))

PARAMS: dict[str, dict[str, Any]] = {
    "cliente_saldo": {
        "texto": {"type": "string", "description": "Nombre o RUC del cliente."}
    },
    "facturas_cliente": {
        "texto": {
            "type": "string",
            "description": "Nombre o RUC del cliente para listar sus facturas internas.",
        }
    },
    "cartera_total": {},
    "cierre_dia": {
        "desde": {"type": "string", "format": "date"},
        "hasta": {"type": "string", "format": "date"},
    },
    "banco_detalle": {
        "banco": {"type": "string", "enum": ["pichincha", "guayaquil", "internacional"]}
    },
    "stock_actual": {
        "material": {"type": "string", "enum": ["CEMENTO", "ARENA", "RIPIO", "RETARDANTE"]}
    },
    "agenda_obras": {
        "desde": {"type": "string", "format": "date"},
        "hasta": {"type": "string", "format": "date"},
    },
    "orden_estado": {"orden_numero": {"type": "integer", "minimum": 1}},
    "precios": {},
    "cliente_ficha": {"cliente_id": {"type": "string"}},
    "movimientos": {
        "desde": {"type": "string", "format": "date"},
        "hasta": {"type": "string", "format": "date"},
        "limite": {"type": "integer", "minimum": 1, "maximum": 500},
    },
    "banco_movimientos": {
        "banco": {"type": "string", "enum": ["pichincha", "guayaquil", "internacional"]},
        "limite": {"type": "integer", "minimum": 1, "maximum": 100},
    },
    "cuota_mercado": {
        "provincia": {"type": "string", "enum": ["TODAS", "ORELLANA", "SUCUMBIOS"]},
        "anio": {"type": "integer", "minimum": 2020, "maximum": 2100},
    },
    "stock_proyectado": {},
    "disponibilidad": {"fecha": {"type": "string", "format": "date"}},
    "viaje_estado": {"dispatch_id": {"type": "string"}},
    "balance": {},
    "resultados": {
        "desde": {"type": "string", "format": "date"},
        "hasta": {"type": "string", "format": "date"},
    },
    "empresa_info": {},
    "salud": {},
    "recordatorio_crear": {
        "destinatario": {
            "type": "string",
            "description": (
                "Nombre exacto del cliente en el CRM, o un número con código "
                "de país. Nunca inventes el número: si no está en el CRM, pídelo."
            ),
        },
        "mensaje": {
            "type": "string",
            "description": (
                "Texto exacto que se enviará por WhatsApp, tal como lo dictó el "
                "usuario. No agregues ni quites información."
            ),
        },
        "cuando": {
            "type": "string",
            "description": (
                "La hora tal como la dijo el usuario, sin convertirla a fecha "
                "absoluta: '18:40', 'en 5 minutos', 'ahora mismo', 'mañana a las 9'. "
                "El backend calcula la fecha en hora de Ecuador."
            ),
        },
        "adjuntar_factura": {
            "type": "boolean",
            "description": (
                "true si el usuario pide pasar, enviar o adjuntar la factura. "
                "Nunca preguntes por el contenido: solo marca la bandera."
            ),
        },
        "factura_de": {
            "type": "string",
            "description": (
                "Opcional: cliente al que pertenece la factura, si es distinto "
                "del destinatario (ej. 'Ing. Reyes')."
            ),
        },
    },
    "recordatorio_listar": {},
    "recordatorio_confirmar": {
        "recordatorio_id": {
            "type": "string",
            "description": "Opcional: id del borrador. Si se omite, usa el pendiente del hilo.",
        }
    },
    "recordatorio_descartar": {
        "recordatorio_id": {
            "type": "string",
            "description": "Opcional: id del borrador. Si se omite, usa el pendiente del hilo.",
        }
    },
    "recordatorio_cancelar": {
        "recordatorio_id": {"type": "string", "description": "id del recordatorio."}
    },
}

REQUERIDOS: dict[str, list[str]] = {
    "cliente_saldo": ["texto"],
    "facturas_cliente": ["texto"],
    "cartera_total": [],
    "cierre_dia": ["desde", "hasta"],
    "banco_detalle": ["banco"],
    "stock_actual": [],
    "agenda_obras": ["desde", "hasta"],
    "orden_estado": ["orden_numero"],
    "precios": [],
    "cliente_ficha": ["cliente_id"],
    "movimientos": ["desde", "hasta"],
    "banco_movimientos": ["banco"],
    "cuota_mercado": [],
    "stock_proyectado": [],
    "disponibilidad": ["fecha"],
    "viaje_estado": ["dispatch_id"],
    "balance": [],
    "resultados": ["desde", "hasta"],
    "empresa_info": [],
    "salud": [],
    "recordatorio_crear": ["destinatario", "mensaje", "cuando"],
    "recordatorio_listar": [],
    "recordatorio_confirmar": [],
    "recordatorio_descartar": [],
    "recordatorio_cancelar": ["recordatorio_id"],
}


def disponible() -> bool:
    return bool(os.getenv("DEEPSEEK_API_KEY")) and os.getenv("GATO_LLM", "1") == "1"


def _nombre(pilar: str, accion: str) -> str:
    return f"{pilar}__{accion}".replace("-", "_")


def herramientas_llm(actor_rol: str) -> tuple[list[dict[str, Any]], dict[str, tuple[str, str]]]:
    """Tools filtradas por rol + mapa nombre→(pilar, acción)."""
    tools: list[dict[str, Any]] = []
    mapa: dict[str, tuple[str, str]] = {}
    for pilar, datos in pilares.pilares_para(actor_rol).items():
        for accion, info in datos["acciones"].items():
            params = PARAMS.get(accion)
            if params is None:
                continue
            nombre = _nombre(pilar, accion)
            mapa[nombre] = (pilar, accion)
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": nombre,
                        "description": (
                            f"[{pilar}] {info['descripcion']}"
                        ),
                        "parameters": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": params,
                            "required": REQUERIDOS.get(accion, []),
                        },
                    },
                }
            )
    return tools, mapa


async def responder_llm(
    pregunta: str,
    actor: Any,
    biblio: Any,
    historial: list[dict[str, str]] | None = None,
) -> Any | None:
    """Devuelve una Respuesta o None si el proveedor falla."""
    if not disponible():
        return None

    from .orquestador import Respuesta, _ejecutar_accion
    from .guardas import CifraNoVerificada, verificar
    from .redactor import redactar

    tools, mapa = herramientas_llm(actor.rol)
    mensajes: list[dict[str, Any]] = [
        {"role": "system", "content": render_prompt(actor.nombre, actor.rol, actor.ahora)},
    ]
    for turno in historial or []:
        rol = turno.get("role")
        contenido = str(turno.get("content") or "").strip()
        if rol in ("user", "assistant") and contenido:
            mensajes.append({"role": rol, "content": contenido[:4000]})
    mensajes.append({"role": "user", "content": pregunta})
    resultados = []
    hubo_acl = False

    headers = {
        "Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as cliente:
        for _ in range(3):
            respuesta = await cliente.post(
                f"{BASE_URL}/chat/completions",
                headers=headers,
                json={
                    "model": MODELO,
                    "messages": mensajes,
                    "tools": tools,
                    "tool_choice": "auto",
                    "temperature": 0.1,
                },
            )
            respuesta.raise_for_status()
            datos = respuesta.json()
            mensaje = datos["choices"][0]["message"]
            mensajes.append(mensaje)

            llamadas = mensaje.get("tool_calls") or []
            if not llamadas:
                texto = (mensaje.get("content") or "").strip()
                if not texto:
                    return None
                fichas = [f for r in resultados for f in r.fichas]
                try:
                    verificar(texto, fichas)
                except CifraNoVerificada as exc:
                    return Respuesta(
                        "No pude verificar una cifra contra la base; no te la voy "
                        f"a mostrar sin fuente. Detalle: {exc}.",
                        "ERROR",
                        resultados,
                    )
                return Respuesta(
                    texto, "ACL" if hubo_acl else "OK", resultados
                )

            for llamada in llamadas:
                fn = llamada["function"]
                nombre = fn["name"]
                if nombre not in mapa:
                    mensajes.append(
                        {"role": "tool", "tool_call_id": llamada["id"],
                         "content": json.dumps({"error": "herramienta no permitida"})}
                    )
                    continue
                pilar, accion = mapa[nombre]
                if not pilares.permite(pilar, accion, actor.rol):
                    hubo_acl = True
                    mensajes.append(
                        {"role": "tool", "tool_call_id": llamada["id"],
                         "content": json.dumps({"estado": "ACL"})}
                    )
                    continue
                try:
                    params = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    params = {}
                rs = await _ejecutar_accion(pilar, accion, params, biblio, actor)
                resultados.extend(rs)
                mensajes.append(
                    {
                        "role": "tool",
                        "tool_call_id": llamada["id"],
                        "content": json.dumps(
                            {
                                "resultados": [
                                    {"estado": r.estado, "nota": r.nota,
                                     "datos": r.datos,
                                     "fichas": [f.a_dict() for f in r.fichas]}
                                    for r in rs
                                ]
                            },
                            ensure_ascii=False,
                            default=str,
                        ),
                    }
                )

    texto = redactar(resultados, actor.rol, actor.nombre)
    return Respuesta(
        texto or "No encontré datos para esa consulta.",
        "ACL" if hubo_acl else "OK",
        resultados,
    )
