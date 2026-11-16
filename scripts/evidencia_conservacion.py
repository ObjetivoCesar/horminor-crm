"""Evidencia de conservación de instrucciones (caso real del 2026-11-16).

Lee de la base el dictado espontáneo que Julio grabó en el laboratorio
—anticipo de USD 17.000, 250 m3 FC-240, ingeniero Julio Cartuche, la
rectificación «la cotización, no la cotización, el recordatorio del pago»,
la entrega contra pago, el plazo de dos meses y el encargo al expediente— y
vuelve a compilarlo sin llamar al LLM. Compara lo que se guardó entonces con
lo que el compilador produce ahora.

No escribe en la base.

    docker compose run --rm --no-deps core-api python scripts/evidencia_conservacion.py
"""

from __future__ import annotations

import asyncio
import json

import _path  # noqa: F401  (ajusta sys.path)

from fastapi import HTTPException

from app.cerebro.extractor import SobreIn, construir_hechos, recompilar
from app.cerebro.router import validar_confirmacion_recordatorio
from app.db import create_pool
from app.settings import get_settings
from app.voz import localizar_palabras, normalizar_con_mapa

MARCA = "empresa eléctrica"


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
            SELECT b.id::text AS borrador_id,
                   b.estado AS estado_guardado,
                   b.acciones_propuestas_json,
                   b.preguntas_pendientes_json,
                   b.condiciones_json,
                   b.creado_en,
                   e.id::text AS extraccion_id,
                   e.sobre_json,
                   e.texto_directo,
                   t.texto_crudo,
                   t.segmentos_json
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
            print("No hay dictado con esa marca en la base local.")
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

        _linea("1. LO QUE SE GUARDÓ ENTONCES")
        print(f"borrador {fila['borrador_id']} · {fila['creado_en']}")
        print(f"estado: {fila['estado_guardado']}")
        guardadas = fila["acciones_propuestas_json"] or []
        if isinstance(guardadas, str):
            guardadas = json.loads(guardadas)
        for accion in guardadas:
            print(f"  - {accion.get('accion_nombre')}: {accion.get('parametros')}")
        print(f"condiciones guardadas: {fila['condiciones_json']}")

        _linea("2. LO QUE DICE EL DICTADO (texto normalizado)")
        print(mapa.texto)

        _linea("3. HECHOS CONSERVADOS CON CITA")
        for hecho in hechos:
            cita = hecho.evidencia.cita if hecho.evidencia is not None else "—"
            print(f"  [{hecho.estado:10}] {hecho.clave:28} = {hecho.valor!r}")
            print(f"               cita: «{cita}»")

        _linea("4. RECOMPILADO CON EL COMPILADOR ACTUAL (sin LLM)")
        nuevo = await recompilar(
            pool,
            hechos=hechos,
            intencion=sobre.intencion,
            sandbox=True,
            texto=mapa.texto,
        )
        borrador = nuevo["borrador"]
        print(f"estado: {borrador.estado}")
        for accion in borrador.acciones:
            print(f"  {accion.orden}. {accion.nombre}")
            print(f"     {json.dumps(accion.a_dict()['parametros'], ensure_ascii=False)}")
        print("condiciones:")
        for condicion in borrador.condiciones:
            print(
                f"  - {condicion.clave} [{condicion.estado}] {condicion.texto}"
            )
            print(f"    cita: «{condicion.cita}»")
        print("preguntas:")
        for pregunta in borrador.preguntas:
            print(f"  - {pregunta.clave}: {pregunta.texto}")

        _linea("5. RESUMEN QUE LEERÍA JULIO")
        print(nuevo["resumen"])

        _linea("6. GUARDA DE CONFIRMACIÓN DEL RECORDATORIO")
        tarea = next(
            (a for a in borrador.acciones if a.nombre == "crear_tarea_recordatorio"),
            None,
        )
        if tarea is None:
            print("  no hay recordatorio en este dictado")
        else:
            for etiqueta, mensaje, ahora in (
                ("sin mensaje final", "", True),
                ("sin aceptar envío inmediato", "Ing. Cartuche, le recuerdo el anticipo.", False),
                ("con mensaje y envío aceptado", "Ing. Cartuche, le recuerdo el anticipo.", True),
            ):
                try:
                    resultado = validar_confirmacion_recordatorio(
                        tarea.parametros,
                        mensaje_final=mensaje,
                        enviar_ahora=ahora,
                        actor_id="evidencia",
                    )
                    print(f"  [{etiqueta}] AUTORIZADO → mensaje={resultado['mensaje']!r}")
                except HTTPException as error:
                    print(
                        f"  [{etiqueta}] RECHAZADO {error.status_code} "
                        f"{error.detail['code']}"
                    )

        _linea("7. MATRIZ DE CONSERVACIÓN")
        claves_hechos = {h.clave for h in hechos}
        claves_condiciones = {c.clave for c in borrador.condiciones}
        nombres = {a.nombre for a in borrador.acciones}
        preguntas_claves = {p.clave for p in borrador.preguntas}
        matriz = [
            ("anticipo USD 17.000", "pago.monto" in claves_hechos),
            ("empresa eléctrica de El Coca", "cliente.nombre" in claves_hechos),
            ("250 m3 FC-240", "cotizacion.volumen_m3" in claves_hechos),
            ("contacto Julio Cartuche 0963444666", "contacto.telefono" in claves_hechos),
            ("recordatorio y no cotización", "crear_tarea_recordatorio" in nombres),
            ("entrega contra pago", "entrega.contra_pago" in claves_condiciones),
            ("plazo de dos meses", "entrega.plazo" in claves_condiciones),
            (
                "expediente de la constructora",
                "expediente.completar" in claves_condiciones
                and "crear_tarea_interna" in nombres,
            ),
            ("dirección de obra pendiente", "cotizacion.obra_direccion" in preguntas_claves),
            ("texto del mensaje pendiente", "tarea.mensaje" in preguntas_claves),
        ]
        perdidas = [nombre for nombre, presente in matriz if not presente]
        for nombre, presente in matriz:
            print(f"  [{'OK' if presente else 'PERDIDO'}] {nombre}")
        print()
        if perdidas:
            print(f"CONSERVACION: FALLA → {perdidas}")
        else:
            print("CONSERVACION: OK — ninguna instrucción relevante se perdió")
        if notas:
            print("\nnotas del verificador:")
            for nota in notas:
                print(f"  - {nota}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
