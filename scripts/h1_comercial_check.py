"""Verificacion real del nucleo comercial (H1) contra PostgreSQL.

Ejercita el modulo con datos ficticios y termina en ``ROLLBACK``: no queda
ningun lead ni cita de prueba. Comprueba las tres origenes (PANEL, WHATSAPP,
GATO), la separacion entre respuesta de la empresa y mensaje del lead, las
reglas de intencion, el choque de citas y la trazabilidad.

Uso:

    docker compose run --rm --no-deps core-api python scripts/h1_comercial_check.py
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import timedelta

import _path  # noqa: F401

import asyncpg

from app import tiempo
from app.comercial import citas as citas_svc
from app.comercial import leads as leads_svc
from app.comercial.whatsapp import ComercialWhatsApp
from app.settings import get_settings

DECLARACIONES: list[str] = []


class PoolDeUnaConexion:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    def acquire(self):
        conn = self._conn

        @asynccontextmanager
        async def _ctx():
            yield conn

        return _ctx()

    def __getattr__(self, nombre: str):
        return getattr(self._conn, nombre)


def exigir(condicion: bool, mensaje: str) -> None:
    if not condicion:
        raise AssertionError(mensaje)
    DECLARACIONES.append(mensaje)


async def eventos(conn: asyncpg.Connection, lead_id: str) -> list[dict]:
    filas = await conn.fetch(
        "SELECT tipo, detalle, actor FROM lead_eventos WHERE lead_id = $1::uuid "
        "ORDER BY id",
        lead_id,
    )
    return [dict(f) for f in filas]


async def main() -> int:
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    transaccion = conn.transaction()
    await transaccion.start()
    try:
        pool = PoolDeUnaConexion(conn)
        hoy = tiempo.hoy()

        # 1. Los tres origenes nacen contacto y llegan a LEAD con la misma regla.
        creados = {}
        for indice, origen in enumerate(("PANEL", "WHATSAPP", "GATO"), start=1):
            lead = await leads_svc.crear_o_reutilizar(
                pool,
                telefono_lead=f"59300000000{indice}",
                origen=origen,
                nombre=f"PRUEBA H1 {origen}",
            )
            exigir(lead["estado"] == "CONTACTO", f"{origen}: nace CONTACTO")
            exigir(lead["origen"] == origen, f"{origen}: conserva su origen")
            respuesta = await leads_svc.registrar_respuesta(
                pool, lead_id=lead["id"], texto="gracias por escribir"
            )
            exigir(respuesta["estado"] == "LEAD", f"{origen}: la respuesta crea el LEAD")
            tipos = [e["tipo"] for e in await eventos(conn, lead["id"])]
            exigir(tipos == ["CREADO", "RESPONDIDO"], f"{origen}: eventos CREADO y RESPONDIDO")
            creados[origen] = lead

        # 2. Respuesta de la empresa con una frase trampa no marca competencia.
        trampa = await leads_svc.registrar_respuesta(
            pool,
            lead_id=creados["PANEL"]["id"],
            texto="ya tengo listo su pedido",
        )
        exigir(trampa["estado"] == "LEAD", "la frase de la empresa no cae el lead")

        # 3. Mensaje del lead: rechazo explicito cae; volver revive.
        rechazo = await leads_svc.registrar_mensaje(
            pool,
            lead_id=creados["WHATSAPP"]["id"],
            texto="no me interesa, gracias",
        )
        exigir(rechazo["estado"] == "CAIDO", "el rechazo explicito marca CAIDO")
        exigir(rechazo["motivo_caida"] == "NO_INTERESADO", "la caida guarda el motivo")
        vuelve = await leads_svc.registrar_mensaje(
            pool,
            lead_id=creados["WHATSAPP"]["id"],
            texto="pensandolo mejor, me interesa",
        )
        exigir(vuelve["estado"] == "LEAD", "si vuelve a escribir revive a LEAD")
        exigir(vuelve["motivo_caida"] is None, "al revivir se limpia el motivo")
        tipos = [e["tipo"] for e in await eventos(conn, creados["WHATSAPP"]["id"])]
        exigir("INTENCION" in tipos and "REACTIVADO" in tipos, "la intencion y el revivir se auditan")

        # 4. Un telefono sigue siendo el mismo lead.
        repetido = await leads_svc.crear_o_reutilizar(
            pool, telefono_lead="593000000001", origen="PANEL"
        )
        exigir(repetido["creado"] is False, "el mismo telefono reutiliza el lead")
        tipos = [e["tipo"] for e in await eventos(conn, repetido["id"])]
        exigir("REINGRESO" in tipos, "el reingreso deja evento")

        # 5. Cita desde WhatsApp mediante el adaptador del canal.
        whatsapp = ComercialWhatsApp(pool)
        contacto = await whatsapp.entrante(
            telefono="593000000004",
            nombre="PRUEBA H1 CITA",
            texto="quiero agendar una visita manana a las 10:30",
        )
        await whatsapp.respuesta(lead_id=contacto["id"], texto="con gusto")
        cita_wa = await whatsapp.solicitar_cita(
            lead_id=contacto["id"], texto="quiero agendar una visita manana a las 10:30"
        )
        exigir(cita_wa is not None, "WhatsApp crea la cita SOLICITADA")
        exigir(cita_wa["estado"] == "SOLICITADA", "la cita nace SOLICITADA")
        exigir(cita_wa["origen"] == "WHATSAPP", "la cita conserva origen WHATSAPP")
        exigir(
            cita_wa["fecha"] == hoy + timedelta(days=1),
            "la fecha sale de app/tiempo (manana en Ecuador)",
        )

        # 6. Cita desde Gato y desde el panel (mismo modulo, otro origen).
        cita_gato = await citas_svc.crear(
            pool,
            tipo="REUNION",
            fecha=tiempo.hoy(),
            hora_inicio="15:00",
            origen="GATO",
            lead_id=creados["GATO"]["id"],
        )
        exigir(cita_gato["origen"] == "GATO", "Gato tambien pasa por el modulo")
        cita_panel = await citas_svc.crear(
            pool,
            tipo="MEDICION",
            fecha=tiempo.hoy(),
            hora_inicio="16:00",
            origen="PANEL",
            lead_id=creados["PANEL"]["id"],
        )
        exigir(cita_panel["origen"] == "PANEL", "el panel tambien pasa por el modulo")

        # 7. Dos citas del mismo lead a la misma hora se rechazan.
        try:
            await citas_svc.crear(
                pool,
                tipo="VISITA",
                fecha=tiempo.hoy(),
                hora_inicio="15:30",
                origen="PANEL",
                lead_id=creados["GATO"]["id"],
            )
        except ValueError as exc:
            exigir("se solapa" in str(exc), "el choque de citas se rechaza")
        else:
            raise AssertionError("el choque de citas no fue rechazado")

        # 8. La maquina de estados y el motivo de cancelacion quedan auditados.
        rechazada = False
        try:
            await citas_svc.cambiar_estado(
                pool, cita_id=cita_gato["id"], nuevo="REALIZADA"
            )
        except ValueError:
            rechazada = True
        exigir(rechazada, "no se realiza una cita sin confirmar")
        await citas_svc.cambiar_estado(
            pool,
            cita_id=cita_gato["id"],
            nuevo="CANCELADA",
            motivo="el cliente no asistio",
        )
        fila = await conn.fetchrow(
            "SELECT detalle FROM cita_eventos WHERE cita_id = $1::uuid "
            "ORDER BY id DESC LIMIT 1",
            cita_gato["id"],
        )
        exigir(
            "el cliente no asistio" in str(fila["detalle"]),
            "la cancelacion guarda el motivo en cita_eventos",
        )

        # 9. Nada quedo fuera de la transaccion.
        conteo = await conn.fetchrow(
            "SELECT (SELECT count(*) FROM leads) AS leads, "
            "(SELECT count(*) FROM citas) AS citas"
        )
        exigir(conteo["leads"] >= 4, "los leads del escenario existen dentro de la transaccion")

        print("[H1 COMERCIAL: OK]")
        for linea in DECLARACIONES:
            print(f"  - {linea}")
        return 0
    finally:
        await transaccion.rollback()
        await conn.close()


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as exc:
        print(f"[H1 COMERCIAL: FALLO] {exc}")
        sys.exit(1)
