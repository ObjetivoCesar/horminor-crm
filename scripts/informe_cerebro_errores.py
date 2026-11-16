"""Informe semanal de errores del Cerebro para Abelito.

Junta lo que el sistema entendió, lo que la persona corrigió y lo que se
ejecutó. No es un log: es el documento que Abelito lee para decidir qué
arreglar (STT, prompt, normalizador o compilador).

Uso:

    docker compose run --rm --no-deps core-api python scripts/informe_cerebro_errores.py
    docker compose run --rm --no-deps core-api python scripts/informe_cerebro_errores.py --dias 7
    docker compose run --rm --no-deps core-api python scripts/informe_cerebro_errores.py --salida /app/.agents/evidencias/informe.md

Solo lee. No corrige, no reejecuta y no manda nada.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import _path  # noqa: F401  (ajusta sys.path)

import asyncpg

from app.db import create_pool
from app.settings import get_settings

ZONA = ZoneInfo("America/Guayaquil")


def _jsonb(valor: Any) -> Any:
    if isinstance(valor, str):
        try:
            return json.loads(valor)
        except ValueError:
            return None
    return valor


def _fecha(valor: Any) -> str:
    if isinstance(valor, datetime):
        return valor.astimezone(ZONA).strftime("%Y-%m-%d %H:%M")
    return str(valor or "")


def _hechos(sobre: Mapping[str, Any]) -> list[str]:
    salida: list[str] = []
    for hecho in sobre.get("hechos") or []:
        if not isinstance(hecho, Mapping):
            continue
        estado = hecho.get("estado") or ""
        if estado in ("NO_DIJO", "INAUDIBLE_NO_ENTENDI"):
            continue
        salida.append(
            f"{hecho.get('clave')} = {hecho.get('valor')!r} [{estado}]"
        )
    return salida


def _acciones(borrador: Mapping[str, Any]) -> list[str]:
    salida: list[str] = []
    for accion in borrador.get("acciones") or []:
        if not isinstance(accion, Mapping):
            continue
        nombre = accion.get("accion_nombre") or accion.get("nombre")
        salida.append(f"{accion.get('orden')}. {nombre} :: {accion.get('parametros')}")
    return salida


async def _filas(pool: asyncpg.Pool, desde: datetime) -> Sequence[asyncpg.Record]:
    return await pool.fetch(
        """
        SELECT c.id::text AS correccion_id,
               c.clave, c.valor_anterior, c.valor_nuevo, c.cita,
               c.corregido_por, c.rol_base, c.creado_en,
               b.id::text AS borrador_id, b.version, b.estado,
               b.acciones_propuestas_json, b.preguntas_pendientes_json,
               e.sobre_json, e.texto_directo, e.version_prompt,
               t.texto_crudo
          FROM cerebro_correcciones c
          JOIN cerebro_borradores b ON b.id = c.borrador_id
          JOIN cerebro_extracciones e ON e.id = c.extraccion_id
          LEFT JOIN voz_transcripciones t ON t.id = e.transcripcion_id
         WHERE c.creado_en >= $1
         ORDER BY c.creado_en
        """,
        desde,
    )


async def _confirmadas(pool: asyncpg.Pool, desde: datetime) -> Sequence[asyncpg.Record]:
    return await pool.fetch(
        """
        SELECT x.borrador_id::text AS borrador_id, x.accion_nombre,
               x.estado, x.error_mensaje, x.ejecutado_en
          FROM cerebro_ejecuciones x
         WHERE x.ejecutado_en >= $1
         ORDER BY x.ejecutado_en
        """,
        desde,
    )


async def _tareas_internas(
    pool: asyncpg.Pool, desde: datetime
) -> Sequence[asyncpg.Record]:
    """Instrucciones al equipo del periodo, con su reloj.

    Si la base todavía no tiene la migración 088, el informe sigue saliendo.
    """
    try:
        return await pool.fetch(
            """
            SELECT id::text AS id, instruccion, asignado_rol, asignado_a,
                   estado, resolucion, resolucion_nota, notificada_en,
                   resuelta_en, registrada_en, minutos_hasta_resolucion,
                   minutos_hasta_registro, minutos_abierta
              FROM v_cerebro_tareas_internas
             WHERE notificada_en >= $1
             ORDER BY notificada_en
            """,
            desde,
        )
    except Exception:
        return []


async def _vocabulario(pool: asyncpg.Pool) -> Sequence[asyncpg.Record]:
    return await pool.fetch(
        """
        SELECT clave, valor_anterior, valor_nuevo, veces
          FROM v_cerebro_vocabulario
         ORDER BY veces DESC, ultima_vez DESC
         LIMIT 30
        """
    )


async def construir_informe(pool: asyncpg.Pool, dias: int) -> str:
    desde = datetime.now(ZONA) - timedelta(days=max(1, dias))
    correcciones = await _filas(pool, desde)
    ejecuciones = await _confirmadas(pool, desde)
    vocabulario = await _vocabulario(pool)
    tareas = await _tareas_internas(pool, desde)

    lineas: list[str] = []
    lineas.append("# Cerebro — informe de errores y correcciones")
    lineas.append("")
    lineas.append(f"**Periodo:** últimos {dias} días (desde {_fecha(desde)}).")
    lineas.append(f"**Generado:** {_fecha(datetime.now(ZONA))} (America/Guayaquil).")
    lineas.append("")
    lineas.append(
        "Cada bloque es un dictado donde una persona corrigió lo que el sistema "
        "entendió. Sirve para ver si el problema es el STT, el prompt, el "
        "normalizador o el compilador."
    )
    lineas.append("")

    if not correcciones:
        lineas.append("_Sin correcciones en el periodo._")
    for fila in correcciones:
        sobre = _jsonb(fila["sobre_json"]) or {}
        borrador = {
            "acciones": _jsonb(fila["acciones_propuestas_json"]) or [],
            "preguntas": _jsonb(fila["preguntas_pendientes_json"]) or [],
        }
        texto = str(fila["texto_crudo"] or fila["texto_directo"] or "").strip()
        lineas.append(f"## {_fecha(fila['creado_en'])} · {fila['clave']}")
        lineas.append("")
        lineas.append(f"- **Borrador:** {fila['borrador_id']} (v{fila['version']}, "
                      f"{fila['estado']})")
        lineas.append(f"- **Corrigió:** {fila['corregido_por']} ({fila['rol_base']})")
        lineas.append(f"- **Antes:** {fila['valor_anterior']!r}")
        lineas.append(f"- **Después:** {fila['valor_nuevo']!r}")
        if fila["cita"]:
            lineas.append(f"- **Cita del audio:** «{fila['cita']}»")
        lineas.append(f"- **Prompt:** {fila['version_prompt']}")
        lineas.append("")
        lineas.append("**Transcripción**")
        lineas.append("")
        lineas.append("> " + (texto.replace("\n", "\n> ") or "(sin texto)"))
        lineas.append("")
        lineas.append("**Hechos**")
        lineas.append("")
        for hecho in _hechos(sobre):
            lineas.append(f"- {hecho}")
        lineas.append("")
        lineas.append("**Acciones propuestas**")
        lineas.append("")
        for accion in _acciones(borrador):
            lineas.append(f"- {accion}")
        if not borrador["acciones"]:
            lineas.append("- (ninguna)")
        lineas.append("")

    lineas.append("## Tareas internas del periodo")
    lineas.append("")
    lineas.append(
        "Instrucciones a alguien del equipo (sin WhatsApp). El reloj corre desde "
        "que el sistema dejo el aviso."
    )
    lineas.append("")
    if not tareas:
        lineas.append("_Sin tareas internas en el periodo._")
    for fila in tareas:
        destino = fila["asignado_a"] or fila["asignado_rol"]
        lineas.append(f"### {_fecha(fila['notificada_en'])} · {destino}")
        lineas.append("")
        lineas.append(f"- **Instrucción:** «{fila['instruccion']}»")
        lineas.append(f"- **Estado:** {fila['estado']}")
        if fila["resolucion"]:
            lineas.append(f"- **Resolución:** {fila['resolucion']}")
        if fila["resolucion_nota"]:
            lineas.append(f"- **Nota:** {fila['resolucion_nota']}")
        if fila["minutos_hasta_resolucion"] is not None:
            lineas.append(
                f"- **Tardó en resolverse:** {fila['minutos_hasta_resolucion']} min"
            )
        if fila["minutos_hasta_registro"] is not None:
            lineas.append(
                f"- **Tardó en registrarse:** {fila['minutos_hasta_registro']} min"
            )
        if fila["minutos_abierta"] is not None:
            lineas.append(
                f"- **Abierta hace:** {fila['minutos_abierta']} min"
            )
        lineas.append("")

    lineas.append("## Confirmaciones y ejecuciones del periodo")
    lineas.append("")
    if not ejecuciones:
        lineas.append("_Sin ejecuciones._")
    for fila in ejecuciones:
        detalle = f" — {fila['error_mensaje']}" if fila["error_mensaje"] else ""
        lineas.append(
            f"- {_fecha(fila['ejecutado_en'])} · {fila['accion_nombre']} · "
            f"{fila['estado']} · borrador {fila['borrador_id']}{detalle}"
        )
    lineas.append("")

    lineas.append("## Vocabulario aprendido (pares que se repiten)")
    lineas.append("")
    if not vocabulario:
        lineas.append("_Sin pares repetidos todavía._")
    for fila in vocabulario:
        lineas.append(
            f"- {fila['clave']}: «{fila['valor_anterior']}» → "
            f"«{fila['valor_nuevo']}» ({fila['veces']} vez/veces)"
        )
    lineas.append("")
    lineas.append("## Qué revisar")
    lineas.append("")
    conteo = Counter(str(fila["clave"]) for fila in correcciones)
    if conteo:
        for clave, veces in conteo.most_common():
            lineas.append(f"- `{clave}`: {veces} corrección(es).")
    else:
        lineas.append("- Nada pendiente: no hubo correcciones.")
    lineas.append("")
    return "\n".join(lineas)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Informe semanal de errores del Cerebro.")
    parser.add_argument("--dias", type=int, default=7)
    parser.add_argument("--salida", default="")
    args = parser.parse_args()

    settings = get_settings()
    pool = await create_pool(settings.database_url)
    try:
        informe = await construir_informe(pool, args.dias)
    finally:
        await pool.close()

    if args.salida:
        with open(args.salida, "w", encoding="utf-8") as archivo:
            archivo.write(informe)
        print(f"Informe escrito en {args.salida}")
        return 0
    print(informe)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
