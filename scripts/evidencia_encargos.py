"""Evidencia de aceptación: tres encargos independientes en un dictado.

Lee de la base el dictado real de tres asuntos, rehace los hechos sin LLM y
muestra la matriz dictado → hechos → encargos → acciones y preguntas. Después
lee las decisiones registradas (corrección, cancelación, ejecución) del
borrador vivo.

No escribe en la base.

    docker compose run --rm --no-deps core-api python scripts/evidencia_encargos.py
"""

from __future__ import annotations

import asyncio
import json

import _path  # noqa: F401

from app.cerebro.extractor import SobreIn, construir_hechos, recompilar
from app.db import create_pool
from app.settings import get_settings
from app.voz import localizar_palabras, normalizar_con_mapa

MARCA = "tres cosas pendientes"


def _linea(titulo: str) -> None:
    print("=" * 74)
    print(titulo)
    print("-" * 74)


async def main() -> None:
    settings = get_settings()
    pool = await create_pool(settings.database_url)
    try:
        fila = await pool.fetchrow(
            """
            SELECT b.id::text AS borrador_id, b.version, b.estado,
                   b.encargos_json, e.sobre_json, e.texto_directo,
                   t.texto_crudo, t.segmentos_json
              FROM cerebro_borradores b
              JOIN cerebro_extracciones e ON e.id = b.extraccion_id
              LEFT JOIN voz_transcripciones t ON t.id = e.transcripcion_id
             WHERE COALESCE(e.texto_directo, t.texto_crudo) ILIKE '%' || $1 || '%'
             ORDER BY b.creado_en DESC
             LIMIT 1
            """,
            MARCA,
        )
        if fila is None:
            print("No hay dictado de tres encargos en la base local.")
            return

        texto = str(fila["texto_crudo"] or fila["texto_directo"] or "")
        datos = fila["segmentos_json"] or {}
        if isinstance(datos, str):
            datos = json.loads(datos)
        palabras_crudas = list(datos.get("palabras") or []) if isinstance(datos, dict) else []

        mapa = normalizar_con_mapa(texto)
        palabras = localizar_palabras(texto, palabras_crudas)
        sobre_json = fila["sobre_json"]
        if isinstance(sobre_json, str):
            sobre_json = json.loads(sobre_json)
        sobre = SobreIn.model_validate(sobre_json)
        hechos, notas = construir_hechos(
            sobre, texto_crudo=texto, mapa=mapa, palabras=palabras
        )

        _linea("1. DICTADO")
        print(mapa.texto)

        _linea("2. HECHOS Y SU ENCARGO")
        for hecho in hechos:
            cita = hecho.evidencia.cita if hecho.evidencia is not None else "—"
            print(
                f"  enc {hecho.encargo}  [{hecho.estado:10}] "
                f"{hecho.clave:26} = {hecho.valor!r}"
            )
            print(f"           cita: «{cita}»")

        _linea("3. RECOMPILADO (sin LLM)")
        nuevo = await recompilar(
            pool, hechos=hechos, intencion=sobre.intencion, sandbox=True,
            texto=mapa.texto,
        )
        borrador = nuevo["borrador"]
        print(f"estado global: {borrador.estado}")
        for encargo in borrador.encargos:
            print(f"\n  ENCARGO {encargo.encargo} · {encargo.estado}")
            print(f"    dictado: {encargo.texto}")
            print(f"    acciones: {list(encargo.acciones)}")
            print(f"    preguntas: {list(encargo.preguntas)}")
        print()
        for accion in borrador.acciones:
            print(f"  {accion.orden}. [encargo {accion.encargo}] {accion.nombre}")
            for clave in ("destinatario", "instruccion", "mensaje", "cuando"):
                if clave in accion.parametros:
                    print(f"       {clave}: {accion.parametros[clave]!r}")
        print("\nresumen:")
        print(nuevo["resumen"])

        _linea("4. DECISIONES REGISTRADAS EN LA BASE")
        decisiones = await pool.fetch(
            """
            SELECT encargo, decision, motivo, decidido_por, creado_en
              FROM cerebro_encargos_decisiones
             WHERE borrador_id = $1::uuid
             ORDER BY creado_en
            """,
            fila["borrador_id"],
        )
        if decisiones:
            for decision in decisiones:
                print(
                    f"  encargo {decision['encargo']}: {decision['decision']} · "
                    f"{decision['motivo']} · {decision['decidido_por']}"
                )
        else:
            print("  sin cancelaciones registradas")

        ejecuciones = await pool.fetch(
            """
            SELECT encargo, accion_nombre, estado, entidad_destino_tabla,
                   ejecutado_en
              FROM cerebro_ejecuciones
             WHERE borrador_id = $1::uuid
             ORDER BY ejecutado_en
            """,
            fila["borrador_id"],
        )
        for ejecucion in ejecuciones:
            print(
                f"  ejecución encargo {ejecucion['encargo']}: "
                f"{ejecucion['accion_nombre']} ({ejecucion['estado']}) -> "
                f"{ejecucion['entidad_destino_tabla']}"
            )

        _linea("5. MATRIZ DE ACEPTACIÓN")
        por_encargo = {a.encargo: a for a in borrador.acciones}
        checks = [
            ("encargo 1 separado (revisión de medidas)", 1 in por_encargo),
            ("encargo 2 separado (recordatorio externo)", 2 in por_encargo),
            ("encargo 3 separado (revisión de despachos)", 3 in por_encargo),
            (
                "el recordatorio no se contaminó con secretaría",
                por_encargo.get(2) is not None
                and por_encargo[2].nombre == "crear_tarea_recordatorio",
            ),
            (
                "el encargo 3 es interno y no menciona el comprobante",
                por_encargo.get(3) is not None
                and por_encargo[3].nombre == "crear_tarea_interna"
                and "comprobante"
                not in str(por_encargo[3].parametros.get("instruccion")),
            ),
        ]
        for nombre, ok in checks:
            print(f"  [{'OK' if ok else 'FALLA'}] {nombre}")
        if all(ok for _n, ok in checks):
            print("\nENCARGOS: OK — tres asuntos independientes, sin mezcla")
        else:
            print("\nENCARGOS: FALLA")
        if notas:
            print("\nnotas del verificador:")
            for nota in notas:
                print(f"  - {nota}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
