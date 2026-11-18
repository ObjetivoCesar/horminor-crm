"""Check local del espejo de WhatsApp (v9.7) contra PostgreSQL real.

Usa datos de ensayo y un cliente Evolution falso: no envia mensajes, no
llama a la red y limpia todo al terminar. Sirve como evidencia reproducible
de que la lista blanca se aplica en el backend.

Uso: python scripts/espejo_v97_check.py
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import _path  # noqa: F401  (ajusta sys.path)

from app.db import create_pool
from app.settings import get_settings
from app.whatsapp_espejo import (
    EspejoWhatsApp,
    PostgresRepositorioEspejo,
)

TELEFONO = "593990009997"
OTRO = "593990009998"
CLIENTE = "Espejo Check v97"


def registro(
    mensaje_id: str,
    jid: str,
    texto: str,
    *,
    from_me: bool = False,
    status: str = "DELIVERY_ACK",
) -> dict[str, Any]:
    return {
        "key": {
            "id": mensaje_id,
            "remoteJid": jid,
            "fromMe": from_me,
            "messageTimestamp": 1_763_000_000,
        },
        "message": {"conversation": texto},
        "messageType": "conversation",
        "status": status,
    }


class FakeEvolution:
    async def buscar_mensajes(
        self, jid: str, *, page: int = 1, offset: int = 100
    ) -> dict[str, Any]:
        if page == 1 and jid == f"{TELEFONO}@s.whatsapp.net":
            return {
                "records": [
                    registro("CHECK-HIST-1", jid, "Mensaje historico de ensayo")
                ],
                "total": 1,
                "pages": 1,
                "page": 1,
            }
        return {"records": [], "total": 0, "pages": 0, "page": page}


async def main() -> None:
    settings = get_settings()
    pool = await create_pool(settings.database_url)
    cliente_id = None
    try:
        cliente_id = await pool.fetchval(
            "INSERT INTO clients (nombre, estado) VALUES ($1, 'PROSPECTO') RETURNING id::text",
            CLIENTE,
        )
        repo = PostgresRepositorioEspejo(pool)
        await repo.upsert_numero(
            telefono=TELEFONO, cliente_id=cliente_id, etiqueta="check"
        )
        await repo.registrar_jid(f"{TELEFONO}@s.whatsapp.net", TELEFONO, "PN")

        espejo = EspejoWhatsApp(repo, settings=settings, evolution=FakeEvolution())

        entrada = await espejo.ingerir(
            registro("CHECK-IN-1", f"{TELEFONO}@s.whatsapp.net", "Hola desde el telefono")
        )
        ajeno = await espejo.ingerir(
            registro("CHECK-OUT-1", f"{OTRO}@s.whatsapp.net", "Contacto no autorizado")
        )
        salida = await espejo.ingerir(
            registro(
                "CHECK-FROMME-1",
                f"{TELEFONO}@s.whatsapp.net",
                "Respuesta desde WhatsApp",
                from_me=True,
                status="READ",
            )
        )
        repetido = await espejo.ingerir(
            registro("CHECK-IN-1", f"{TELEFONO}@s.whatsapp.net", "Hola desde el telefono")
        )

        sync = await espejo.sincronizar(cliente_id=cliente_id)
        sync_repetido = await espejo.sincronizar(cliente_id=cliente_id)

        filas = await pool.fetch(
            """
            SELECT direccion, autor_tipo, cuerpo, estado_entrega
              FROM chat_mensajes m
              JOIN chat_conversaciones cv ON cv.id = m.conversacion_id
             WHERE cv.cliente_id = $1::uuid
             ORDER BY m.created_at
            """,
            cliente_id,
        )
        conversaciones = await pool.fetchval(
            "SELECT count(*) FROM chat_conversaciones WHERE cliente_id = $1::uuid",
            cliente_id,
        )
        ajenos = await pool.fetchval(
            """
            SELECT count(*) FROM chat_mensajes m
              JOIN chat_conversaciones cv ON cv.id = m.conversacion_id
             WHERE cv.cliente_id = $1::uuid AND m.whatsapp_msg_id LIKE 'CHECK-OUT-%'
            """,
            cliente_id,
        )

        resultado = {
            "ingesta": {
                "autorizado": entrada,
                "ajeno": ajeno,
                "from_me": salida,
                "repetido": repetido,
            },
            "sync": {
                "importados": sync.importados,
                "paginas": sync.paginas,
                "repetido_importados": sync_repetido.importados,
            },
            "espejo": {
                "conversaciones": conversaciones,
                "mensajes": len(filas),
                "mensajes_ajenos": ajenos,
                "detalle": [dict(f) for f in filas],
            },
        }
        print(json.dumps(resultado, ensure_ascii=False, default=str, indent=2))

        assert entrada == "IMPORTADO"
        assert ajeno == "NO_AUTORIZADO"
        assert salida == "IMPORTADO"
        assert repetido == "DUPLICADO"
        assert sync.importados == 1
        assert sync_repetido.importados == 0
        assert conversaciones == 1
        assert len(filas) == 3
        assert ajenos == 0
    finally:
        if cliente_id:
            await pool.execute(
                "DELETE FROM whatsapp_espejo_numeros WHERE telefono_e164 = $1",
                TELEFONO,
            )
            await pool.execute(
                "DELETE FROM clients WHERE id = $1::uuid", cliente_id
            )
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
