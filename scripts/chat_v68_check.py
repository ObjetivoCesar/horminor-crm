"""Verificacion del historial CHAT v6.8 (API + PostgreSQL).

Usa el primer cliente real, crea mensajes marcados con ``TAG``, comprueba
persistencia, idempotencia de WhatsApp, busqueda full-text y contador de no
leidos, y borra todo lo que creo en el bloque ``finally``.

Uso:
    docker compose run --rm --no-deps core-api python scripts/chat_v68_check.py

Sale con codigo 1 si una verificacion falla. No deja mensajes de prueba.
"""

from __future__ import annotations

import asyncio
import os
import sys

import _path  # noqa: F401

import asyncpg
import httpx

from app.settings import get_settings

TAG = "chatv68prueba"
# Dentro de `docker compose run` el API vive en el contenedor de servicio.
BASE = os.getenv("CHAT_CHECK_BASE", "http://orminorth-core-api:8000")
CANAL = "PANEL"

_fallos = 0


def check(condicion: bool, mensaje: str, detalle: str = "") -> None:
    global _fallos
    if condicion:
        print(f"  [OK] {mensaje}")
        return
    _fallos += 1
    print(f"  [FALLO] {mensaje}" + (f" :: {detalle}" if detalle else ""))


async def main() -> int:
    settings = get_settings()
    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=2)
    cliente_id: str | None = None
    conversacion_id: str | None = None
    conversacion_previa: str | None = None
    ids: list[str] = []
    try:
        async with httpx.AsyncClient(base_url=BASE, timeout=20) as http:
            respuesta = await http.get("/api/v1/secretaria/clientes")
            respuesta.raise_for_status()
            clientes = respuesta.json().get("clientes") or []
            if not clientes:
                print("  [FALLO] no hay clientes en la base")
                return 1
            cliente_id = clientes[0]["cliente_id"]
            print(f"Cliente de prueba: {clientes[0]['nombre']} ({cliente_id})")

            conversacion_previa = await pool.fetchval(
                "SELECT id::text FROM chat_conversaciones WHERE cliente_id = $1::uuid AND canal = $2",
                cliente_id,
                CANAL,
            )

            # 1. Abrir el hilo (GET crea la conversacion si no existe).
            r = await http.get(f"/api/v1/clients/{cliente_id}/chat", params={"canal": CANAL})
            check(r.status_code == 200, "GET chat responde 200", r.text[:200])
            cuerpo = r.json()
            conversacion_id = cuerpo["conversacion_id"]
            # Leer no crea el hilo: si no existe, viene None y lo crea el POST.
            check("conversacion_id" in cuerpo, "GET devuelve el campo conversacion_id")
            base_total = int(cuerpo["resumen"]["total_mensajes"])

            # 2. Mensaje saliente desde el panel.
            r = await http.post(
                f"/api/v1/clients/{cliente_id}/chat/mensajes",
                json={"cuerpo": f"Salida de verificacion {TAG}", "canal": CANAL},
            )
            check(r.status_code == 200, "POST saliente responde 200", r.text[:200])
            saliente = r.json()["mensaje"]
            conversacion_id = r.json()["conversacion_id"]
            check(bool(conversacion_id), "el POST crea el hilo")
            ids.append(saliente["id"])
            check(saliente["direccion"] == "SALIENTE", "el saliente queda como SALIENTE")
            check(saliente["autor_tipo"] == "OPERADOR", "el autor es OPERADOR del panel")

            # 3. Mensaje entrante (simula WhatsApp) con id de Evolution.
            r = await http.post(
                f"/api/v1/clients/{cliente_id}/chat/mensajes",
                json={
                    "cuerpo": f"Entrada de verificacion {TAG}",
                    "canal": CANAL,
                    "direccion": "ENTRANTE",
                    "autor_tipo": "CLIENTE",
                    "autor_nombre": "Verificacion chat",
                    "whatsapp_msg_id": f"wamid.{TAG}",
                },
            )
            check(r.status_code == 200, "POST entrante responde 200", r.text[:200])
            entrante = r.json()["mensaje"]
            ids.append(entrante["id"])
            check(r.json()["resumen"]["no_leidos"] == 1, "el entrante deja 1 no leido")

            # 4. Reintento del mismo whatsapp_msg_id: no duplica.
            r = await http.post(
                f"/api/v1/clients/{cliente_id}/chat/mensajes",
                json={
                    "cuerpo": f"Entrada de verificacion {TAG}",
                    "canal": CANAL,
                    "direccion": "ENTRANTE",
                    "autor_tipo": "CLIENTE",
                    "whatsapp_msg_id": f"wamid.{TAG}",
                },
            )
            check(r.status_code == 200, "el reintento responde 200", r.text[:200])
            check(r.json()["duplicado"] is True, "el reintento se marca duplicado")
            check(
                r.json()["resumen"]["total_mensajes"] == base_total + 2,
                "el duplicado no suma mensajes",
            )

            # 5. Historial persistido y en orden.
            r = await http.get(f"/api/v1/clients/{cliente_id}/chat", params={"canal": CANAL})
            mensajes = r.json()["mensajes"]
            check(
                [m["id"] for m in mensajes][-2:] == [saliente["id"], entrante["id"]],
                "el hilo devuelve los dos mensajes al final",
            )
            check(
                all(mensajes[i]["created_at"] <= mensajes[i + 1]["created_at"] for i in range(len(mensajes) - 1)),
                "el hilo viene en orden cronologico",
            )

            # 6. Busqueda full-text para el bot.
            r = await http.get("/api/v1/chat/buscar", params={"q": TAG, "cliente_id": cliente_id})
            check(r.status_code == 200, "GET /chat/buscar responde 200", r.text[:200])
            encontrados = r.json()["resultados"]
            check(len(encontrados) == 2, "la busqueda encuentra los 2 mensajes", str(len(encontrados)))
            check(
                all(TAG in (fila["fragmento"] or "") for fila in encontrados),
                "el fragmento resalta el termino buscado",
            )

            # 7. Marcar leido.
            r = await http.post(
                f"/api/v1/clients/{cliente_id}/chat/leido", params={"canal": CANAL}
            )
            check(r.status_code == 200, "POST leido responde 200", r.text[:200])
            check(r.json()["marcados"] >= 1, "marca al menos un entrante")
            check(r.json()["resumen"]["no_leidos"] == 0, "no quedan no leidos")

            # 8. El indice unico de WhatsApp esta activo.
            existe = await pool.fetchval(
                "SELECT count(*) FROM chat_mensajes WHERE whatsapp_msg_id = $1",
                f"wamid.{TAG}",
            )
            check(existe == 1, "whatsapp_msg_id unico en la base", str(existe))

        check(_fallos == 0, "sin fallos")
        return 0
    finally:
        if ids:
            await pool.execute("DELETE FROM chat_mensajes WHERE id = ANY($1::uuid[])", ids)
        if conversacion_id:
            if conversacion_previa is None:
                await pool.execute(
                    "DELETE FROM chat_conversaciones WHERE id = $1::uuid AND NOT EXISTS ("
                    "SELECT 1 FROM chat_mensajes WHERE conversacion_id = $1::uuid)",
                    conversacion_id,
                )
            if cliente_id:
                restantes = await pool.fetchval(
                    "SELECT count(*) FROM chat_mensajes m "
                    "JOIN chat_conversaciones cv ON cv.id = m.conversacion_id "
                    "WHERE cv.cliente_id = $1::uuid AND m.cuerpo LIKE $2",
                    cliente_id,
                    f"%{TAG}%",
                )
                print(f"Limpieza: mensajes de prueba restantes = {restantes}")
        total = await pool.fetchval("SELECT count(*) FROM chat_mensajes")
        print(f"Mensajes totales en chat_mensajes al terminar = {total}")
        await pool.close()


if __name__ == "__main__":
    resultado = asyncio.run(main())
    print("CHAT V6.8: OK" if resultado == 0 and _fallos == 0 else "CHAT V6.8: FALLO")
    sys.exit(0 if resultado == 0 and _fallos == 0 else 1)
