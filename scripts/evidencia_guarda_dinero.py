"""Evidencia: la guarda del dinero no deja registrar un abono sin sustento.

No llama al LLM: parte de la extraccion real de Diaz Sur guardada en la base,
quita o cambia el hecho `pago.recibido` y vuelve a compilar con el mismo
compilador que usa el endpoint. Imprime estado, acciones, preguntas y resumen.
"""

import asyncio
import sys

import _path  # noqa: F401  (ajusta sys.path)

from app.db import create_pool
from app.settings import get_settings
from app.cerebro.extractor import recompilar
from app.cerebro.hechos import Evidencia, HechoCitado
from app.cerebro.revision import resumen_legible
from app.cerebro.router import _hechos_reconstruidos
from app.voz import normalizar_con_mapa


def sin_clave(hechos, clave):
    return [h for h in hechos if h.clave != clave]


def con_clave(hechos, clave, valor, estado="EXTRAIDO"):
    hechos = sin_clave(hechos, clave)
    hechos.append(
        HechoCitado(
            clave=clave,
            valor=valor,
            estado=estado,
            tipo="BOOLEANO",
            evidencia=Evidencia(
                cita="el anticipo",
                sostiene="el anticipo",
                crudo_inicio=0,
                crudo_fin=11,
                start_ms=0,
                end_ms=900,
                confianza=0.9,
                hablante="SUPERADMIN",
            ),
        )
    )
    return hechos


async def main(extraccion: str) -> None:
    settings = get_settings()
    pool = await create_pool(settings.database_url)
    try:
        async with pool.acquire() as conn:
            hechos, _notas, texto, sobre = await _hechos_reconstruidos(
                conn, extraccion
            )
        normalizado = normalizar_con_mapa(texto).texto
        base = sin_clave(hechos, "pago.recibido")

        casos = [
            ("1. Audio real, sin pago.recibido (el LLM no lo dijo)", base),
            ("2. El LLM afirma True sin frase en pasado", con_clave(base, "pago.recibido", True)),
            ("3. Persona corrige: si, ya entro", con_clave(base, "pago.recibido", True, "CORREGIDO_POR_HUMANO")),
            ("4. El audio dice que todavia no entro", con_clave(base, "pago.recibido", False)),
        ]

        for titulo, lista in casos:
            nuevo = await recompilar(
                pool,
                hechos=lista,
                intencion=sobre.intencion,
                sandbox=True,
                texto=normalizado,
            )
            borrador = nuevo["borrador"]
            print("=" * 72)
            print(titulo)
            print("-" * 72)
            print(f"estado: {borrador.estado}")
            print(
                "acciones: "
                + (", ".join(a.nombre for a in borrador.acciones) or "(ninguna)")
            )
            for accion in borrador.acciones:
                if accion.nombre == "registrar_abono_cliente":
                    print(f"  abono: {dict(accion.parametros)}")
            for pregunta in borrador.preguntas:
                print(f"  pregunta [{pregunta.clave}]: {pregunta.texto}")
            print(f"resumen: {resumen_legible(lista, texto=normalizado)}")
            print()
    finally:
        await pool.close()


asyncio.run(main(sys.argv[1]))
