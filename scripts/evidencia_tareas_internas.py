"""Evidencia del ciclo de una tarea interna: aviso, vista, acuse, cierre.

No usa el LLM: llama al mismo servicio que el Cerebro. Muestra que:

1. La tarea nace NOTIFICADA con prioridad y plazo.
2. Abrir el detalle (VISTA) no es acusar recibo (ACUSADA).
3. Acusar no cambia el estado de la tarea.
4. Resolver y registrar miden el tiempo real.
5. Una tarea vencida se puede escalar.
6. Crear dos veces la misma instruccion no duplica; resolver dos veces falla.
7. Retirar una asociacion aprendida la saca del vocabulario.

    docker compose run --rm --no-deps core-api python scripts/evidencia_tareas_internas.py

Escribe en la base local. Datos ficticios.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import _path  # noqa: F401  (ajusta sys.path)

from app.cerebro import internas
from app.db import create_pool
from app.settings import get_settings


def _linea(titulo: str) -> None:
    print("=" * 74)
    print(titulo)
    print("-" * 74)


async def main() -> None:
    settings = get_settings()
    pool = await create_pool(settings.database_url)
    sufijo = uuid.uuid4().hex[:8]
    try:
        _linea("1. Instruccion normal: nace NOTIFICADA con plazo")
        normal = await internas.crear(
            pool,
            instruccion=(
                "que revisen en secretaria como van los despachos de esta "
                "semana y confirmen que esta pendiente"
            ),
            asignado_rol="SECRETARIA",
            creado_por="Julio Villavicencio",
            rol_actor="SUPERADMIN",
            clave_externa=f"evidencia-{sufijo}-normal",
            ficha={
                "tipo": "REVISION",
                "accion": "Revisar lo indicado",
                "cliente": None,
                "monto_usd": None,
                "datos_faltantes": [],
                "resultado_esperado": "Informar que se reviso y que quedo pendiente.",
            },
            prioridad="NORMAL",
        )
        tarea_normal = normal.datos["id"]
        ficha_normal = await internas.obtener(pool, tarea_normal)
        print("estado:", ficha_normal["estado"])
        print("prioridad:", ficha_normal["prioridad"])
        print("plazo_en:", ficha_normal["plazo_en"])
        print("sin_acuse:", ficha_normal["sin_acuse"])
        print("ficha:", ficha_normal["metadatos"]["ficha"]["tipo"])

        _linea("2. Instruccion urgente: plazo mas corto")
        urgente = await internas.crear(
            pool,
            instruccion="verificar si ya entro la transferencia de 27.000 USD",
            asignado_rol="SECRETARIA",
            creado_por="Julio Villavicencio",
            rol_actor="SUPERADMIN",
            clave_externa=f"evidencia-{sufijo}-urgente",
            ficha={
                "tipo": "VERIFICACION",
                "accion": "Verificar el dato indicado",
                "cliente": "Dualsur",
                "monto_usd": "27000",
                "datos_faltantes": [],
                "resultado_esperado": "Informar si se confirmo o no, y con que referencia.",
            },
            prioridad="URGENTE",
        )
        tarea_urgente = urgente.datos["id"]
        ficha_urgente = await internas.obtener(pool, tarea_urgente)
        print("prioridad:", ficha_urgente["prioridad"])
        print("plazo_en:", ficha_urgente["plazo_en"])
        print("monto de referencia:", ficha_urgente["metadatos"]["ficha"]["monto_usd"])

        _linea("3. Vista y acuse son actos distintos")
        vista = await internas.marcar_vista(
            pool,
            tarea_urgente,
            actor_id=None,
            actor_nombre="Secretaria Ventanilla",
            rol_actor="SECRETARIA",
        )
        print("vista_en:", vista["vista_en"], "| ya_estaba:", vista["ya_estaba"])
        tras_vista = await internas.obtener(pool, tarea_urgente)
        print("estado tras ver el detalle:", tras_vista["estado"])
        print("acusada_en:", tras_vista["acusada_en"])
        acuse = await internas.acusar(
            pool,
            tarea_urgente,
            actor_id=None,
            actor_nombre="Secretaria Ventanilla",
            rol_actor="SECRETARIA",
        )
        print("acusada_en:", acuse["acusada_en"])
        tras_acuse = await internas.obtener(pool, tarea_urgente)
        print("estado tras acusar:", tras_acuse["estado"])
        print("sin_acuse:", tras_acuse["sin_acuse"])

        _linea("4. Resolver y registrar: el reloj real")
        resuelta = await internas.resolver(
            pool,
            tarea_urgente,
            resolucion="RESUELTA",
            nota="Se reviso el banco: la transferencia todavia no aparece.",
            actor_nombre="Secretaria Ventanilla",
            rol_actor="SECRETARIA",
        )
        print("estado:", resuelta["estado"])
        print("minutos_hasta_resolucion:", resuelta["minutos_hasta_resolucion"])
        registrada = await internas.registrar(
            pool,
            tarea_urgente,
            nota="Consulta bancaria archivada.",
            metadatos={"referencia": "transferencia-27000", "soporte": "extracto"},
            actor_nombre="Secretaria Ventanilla",
            rol_actor="SECRETARIA",
        )
        print("estado:", registrada["estado"])
        print("minutos_hasta_registro:", registrada["minutos_hasta_registro"])

        _linea("5. Vencida y escalada (plazo simulado en el pasado)")
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE cerebro_tareas_internas
                   SET plazo_en = now() - interval '10 minutes'
                 WHERE id = $1::uuid
                """,
                tarea_normal,
            )
        vencida = await internas.obtener(pool, tarea_normal)
        print("vencida:", vencida["vencida"])
        print("requiere_escalamiento:", vencida["requiere_escalamiento"])
        escalada = await internas.escalar(
            pool,
            tarea_normal,
            motivo="Nadie acuso recibo y el plazo vencio.",
            actor_id=None,
            actor_nombre="Julio Villavicencio",
            rol_actor="SUPERADMIN",
        )
        print("escalada_en:", escalada["escalada_en"])
        tras_escalar = await internas.obtener(pool, tarea_normal)
        print("prioridad:", tras_escalar["prioridad"])

        _linea("6. Idempotencia y doble resolucion")
        repetida = await internas.crear(
            pool,
            instruccion="verificar si ya entro la transferencia de 27.000 USD",
            asignado_rol="SECRETARIA",
            creado_por="Julio Villavicencio",
            rol_actor="SUPERADMIN",
            clave_externa=f"evidencia-{sufijo}-urgente",
            prioridad="URGENTE",
        )
        print("misma clave -> repetido:", repetida.datos.get("repetido"))
        print("misma tarea:", repetida.datos.get("id") == tarea_urgente)
        try:
            await internas.resolver(
                pool,
                tarea_urgente,
                resolucion="RESUELTA",
                nota="otra vez",
                actor_nombre="Secretaria Ventanilla",
                rol_actor="SECRETARIA",
            )
        except internas.TransicionInvalida as exc:
            print("segunda resolucion rechazada:", exc)

        _linea("7. Retiro de una asociacion aprendida (par de prueba)")
        retiro = await internas.retirar_vocabulario(
            pool,
            clave="cliente.nombre",
            valor_anterior="Prueba STT",
            valor_nuevo="Prueba Real",
            motivo="Eran dos empresas distintas.",
            retirado_por="Julio Villavicencio",
            rol_base="SUPERADMIN",
        )
        print("retiro registrado:", retiro["id"])
        async with pool.acquire() as conn:
            en_vista = await conn.fetchval(
                """
                SELECT count(*) FROM v_cerebro_vocabulario
                 WHERE clave = 'cliente.nombre'
                   AND valor_anterior = 'Prueba STT'
                   AND valor_nuevo = 'Prueba Real'
                """
            )
        print("el par retirado aparece en el vocabulario:", bool(en_vista))

        _linea("8. Linea de tiempo de la tarea urgente")
        async with pool.acquire() as conn:
            eventos = await conn.fetch(
                """
                SELECT estado, actor_nombre, nota, creado_en
                  FROM cerebro_tareas_internas_eventos
                 WHERE tarea_id = $1::uuid
                 ORDER BY creado_en
                """,
                tarea_urgente,
            )
        for evento in eventos:
            hora = evento["creado_en"].astimezone(timezone.utc).strftime("%H:%M:%S")
            print(
                f"{hora} UTC · {evento['estado']:<11} · {evento['actor_nombre']}"
                + (f" · {evento['nota']}" if evento["nota"] else "")
            )
        print("generado_en:", datetime.now(timezone.utc).isoformat())
        print("tarea de prueba:", tarea_urgente)
        print("plazo normal esperado:", timedelta(hours=internas.PLAZO_NORMAL_HORAS))
    finally:
        await pool.close()


asyncio.run(main())
