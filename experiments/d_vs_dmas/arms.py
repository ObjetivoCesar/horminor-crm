"""Brazos del experimento: motor actual (v7), D y D+.

Los brazos no escriben en la base ni modifican el motor. El brazo v7 importa
el prompt y el compilador productivos en modo lectura para proyectar acciones
a tipos de orden comparables.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Sequence

import httpx

from . import prompts
from .contracts import (
    Hallazgo,
    OrdenPropuesta,
    RestriccionPropuesta,
    ResultadoConciliacion,
    SobreHechos,
    SobreOrdenes,
    SobreRestricciones,
    SobreUnico,
)
from .llm import RespuestaLLM, en_paralelo, llamar
from .reconcile import conciliar

RAIZ = Path(__file__).resolve().parents[2]
APP = RAIZ / "services" / "core-api"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))


def normalizar(texto: str) -> str:
    try:
        from app.voz import normalizar_con_mapa

        return normalizar_con_mapa(texto).texto
    except Exception:
        return texto


def _mensaje(texto: str, clientes: Sequence[str] = ()) -> str:
    conocidos = ", ".join(clientes) if clientes else "(sin lista)"
    return (
        f"HOY: {date.today().isoformat()} (America/Guayaquil)\n"
        f"CLIENTES CONOCIDOS: {conocidos}\n"
        f"DICTADO:\n{texto}"
    )


@dataclass
class ResultadoBrazo:
    brazo: str
    texto: str
    conciliacion: ResultadoConciliacion = field(
        default_factory=ResultadoConciliacion
    )
    llamadas: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def usage_total(self) -> dict[str, int]:
        entrada = salida = 0
        for llamada in self.llamadas:
            usage = llamada.get("usage") or {}
            entrada += int(usage.get("prompt_tokens") or 0)
            salida += int(usage.get("completion_tokens") or 0)
        return {"prompt_tokens": entrada, "completion_tokens": salida}

    @property
    def latencia_ms(self) -> int:
        if not self.llamadas:
            return 0
        return max(int(c.get("latency_ms") or 0) for c in self.llamadas)


def _registrar(resultado: ResultadoBrazo, nombre: str, r: RespuestaLLM) -> None:
    resultado.llamadas.append(
        {
            "analizador": nombre,
            "ok": bool(r.get("ok")),
            "latency_ms": int(r.get("latency_ms") or 0),
            "usage": r.get("usage") or {},
            "error": r.get("error"),
            "intentos": r.get("intentos"),
        }
    )


async def arm_d(
    cliente: httpx.AsyncClient, texto: str, *, clientes: Sequence[str] = ()
) -> ResultadoBrazo:
    normalizado = normalizar(texto)
    resultado = ResultadoBrazo(brazo="D", texto=normalizado)
    r = await llamar(
        cliente,
        system=prompts.D,
        user=_mensaje(normalizado, clientes),
        max_tokens=3500,
    )
    _registrar(resultado, "D", r)
    if not r.get("ok"):
        resultado.error = r.get("error")
        return resultado
    try:
        sobre = SobreUnico.model_validate(r["data"])
    except Exception as exc:  # contrato incumplido
        resultado.error = f"CONTRATO_D: {exc}"
        return resultado
    resultado.conciliacion = conciliar(
        normalizado,
        ordenes=sobre.ordenes,
        restricciones=[*sobre.restricciones, *sobre.rectificaciones],
        hechos=(),
    )
    resultado.extras["asuntos"] = [a.model_dump() for a in sobre.asuntos]
    return resultado


async def arm_dplus(
    cliente: httpx.AsyncClient,
    texto: str,
    *,
    clientes: Sequence[str] = (),
    con_arbitro: bool = False,
) -> ResultadoBrazo:
    normalizado = normalizar(texto)
    resultado = ResultadoBrazo(brazo="D+" if not con_arbitro else "D+ARB", texto=normalizado)
    mensaje = _mensaje(normalizado, clientes)

    r1, r2, r3 = await en_paralelo(
        cliente,
        [
            {"system": prompts.A1.replace("{claves}", ", ".join(prompts.CLAVES_HECHOS)), "user": mensaje, "max_tokens": 3000},
            {"system": prompts.A2, "user": mensaje, "max_tokens": 3000},
            {"system": prompts.A3, "user": mensaje, "max_tokens": 3000},
        ],
    )
    _registrar(resultado, "A1", r1)
    _registrar(resultado, "A2", r2)
    _registrar(resultado, "A3", r3)

    if not r1.get("ok") or not r2.get("ok"):
        resultado.error = f"A1={r1.get('error')} A2={r2.get('error')}"
        return resultado

    try:
        hechos = SobreHechos.model_validate(r1["data"]).hechos
        ordenes = SobreOrdenes.model_validate(r2["data"])
    except Exception as exc:
        resultado.error = f"CONTRATO: {exc}"
        return resultado

    restricciones: list[RestriccionPropuesta] = []
    if r3.get("ok"):
        try:
            sobre_r = SobreRestricciones.model_validate(r3["data"])
            restricciones = [*sobre_r.restricciones, *sobre_r.rectificaciones]
        except Exception as exc:
            resultado.error = f"CONTRATO_A3: {exc}"

    conciliacion = conciliar(
        normalizado,
        ordenes=ordenes.ordenes,
        restricciones=restricciones,
        hechos=hechos,
    )
    if not r3.get("ok"):
        # Sin A3 no se avanza en silencio: todo queda bloqueado hasta revisiÃ³n.
        for orden in conciliacion.ordenes:
            orden.estado = "BLOQUEADA"
            orden.motivo_estado = "restricciones no verificadas: A3 fallo"
        conciliacion.hallazgos.append(
            Hallazgo(
                codigo="A3_FALLIDO",
                detalle=r3.get("error") or "sin respuesta",
            )
        )
    resultado.conciliacion = conciliacion
    resultado.extras["asuntos"] = [a.model_dump() for a in ordenes.asuntos]
    resultado.extras["hechos"] = len(hechos)
    resultado.extras["a3_ok"] = bool(r3.get("ok"))

    if con_arbitro and conciliacion.conflictos:
        conflicto = conciliacion.conflictos[0]
        r4 = await llamar(
            cliente,
            system=prompts.ARB,
            user=(
                f"DICTADO:\n{normalizado}\n\n"
                f"CONFLICTO: {conflicto.model_dump_json()}\n"
            ),
            max_tokens=600,
        )
        _registrar(resultado, "ARB", r4)
        resultado.extras["arbitro"] = r4.get("data") if r4.get("ok") else None

    return resultado


# ---------------------------------------------------------------------------
# Brazo del motor actual (v7): prompt productivo, sin base de datos.
# ---------------------------------------------------------------------------
_MAPA_ACCION = {
    "crear_tarea_interna": "DELEGAR",
    "crear_tarea_recordatorio": "ENVIAR_MENSAJE",
    "crear_cotizacion_borrador": "COTIZAR",
    "crear_cliente": "REGISTRAR",
    "registrar_abono_cliente": "REGISTRAR",
    "registrar_traslado_caja_banco": "REGISTRAR",
    "enviar_cotizacion_whatsapp": "ENVIAR_MENSAJE",
    "solicitar_ubicacion_whatsapp": "ENVIAR_MENSAJE",
}


async def arm_v7(
    cliente: httpx.AsyncClient, texto: str, *, clientes: Sequence[str] = ()
) -> ResultadoBrazo:
    """Motor actual a nivel de interpretaciÃ³n: prompt v7 â†’ hechos â†’ compilar."""
    normalizado = normalizar(texto)
    resultado = ResultadoBrazo(brazo="V7", texto=normalizado)
    try:
        from app.cerebro import compilar
        from app.cerebro.extractor import (
            PROMPT,
            construir_hechos,
            validar_sobre,
            _mensaje as mensaje_productivo,
        )
        from app.cerebro.compilador import Contexto
        from app.voz import localizar_palabras, normalizar_con_mapa
    except Exception as exc:
        resultado.error = f"IMPORT: {exc}"
        return resultado

    mapa = normalizar_con_mapa(texto)
    palabras = localizar_palabras(texto, [])
    r = await llamar(
        cliente,
        system=PROMPT.format(claves=", ".join(CLAVES_PRODUCTIVAS())),
        user=mensaje_productivo(mapa.texto, palabras, date.today(), list(clientes), ()),
        max_tokens=3000,
    )
    _registrar(resultado, "V7", r)
    if not r.get("ok"):
        resultado.error = r.get("error")
        return resultado
    try:
        sobre = validar_sobre(r["data"])
        hechos, _notas = construir_hechos(
            sobre, texto_crudo=texto, mapa=mapa, palabras=palabras
        )
        borrador = compilar(
            hechos,
            Contexto(
                hoy=date.today(),
                sandbox=True,
                cliente=None,
                receta=None,
                texto=mapa.texto,
            ),
        )
    except Exception as exc:
        resultado.error = f"COMPILAR: {exc}"
        return resultado

    ordenes: list[OrdenPropuesta] = []
    for accion in borrador.acciones:
        tipo = _MAPA_ACCION.get(accion.nombre)
        if tipo is None:
            continue
        citas = [
            h.evidencia.cita
            for h in hechos
            if h.evidencia is not None
            and h.evidencia.cita
            and h.encargo == accion.encargo
        ][:3]
        ordenes.append(
            OrdenPropuesta(
                asunto=str(accion.encargo),
                tipo=tipo,
                responsable_ejecucion=accion.parametros.get("asignado_rol"),
                destinatario_comunicacion=accion.parametros.get("destinatario"),
                medio=(
                    "WHATSAPP"
                    if accion.nombre in ("crear_tarea_recordatorio", "enviar_cotizacion_whatsapp")
                    else "CRM"
                ),
                ejecutor="HUMANO",
                datos_requeridos=[],
                citas=citas,
                confianza=0.5,
            )
        )
    resultado.conciliacion = conciliar(
        mapa.texto, ordenes=ordenes, restricciones=(), hechos=()
    )
    resultado.extras["acciones"] = [a.nombre for a in borrador.acciones]
    resultado.extras["asuntos"] = [e.a_dict() for e in borrador.encargos]
    return resultado


def CLAVES_PRODUCTIVAS() -> tuple[str, ...]:
    from app.cerebro.extractor import CLAVES

    return CLAVES

