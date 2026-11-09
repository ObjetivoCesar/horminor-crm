"""HITO 3 - Test de Candado del Modulo 1 (WhatsApp) contra PostgreSQL real.

Simula tres celulares (bodega, chofer y cliente) sobre una orden real creada en
la base de datos, pasa los mensajes por la ventana de debounce y por las cuatro
compuertas, y verifica que:

1. El ``tracking_payload`` (contrato JSONB) refleje Bodega -> Chofer -> Cliente.
2. El trigger ``trg_dispatch_project`` proyecte el estado a las columnas planas.
3. El limite termico sea exactamente el reloj de fraguado configurado.
4. Un reclamo del cliente quede como incidencia y en ``error_logs``.
5. La receta oficial (confirmada) haya generado el consumo y quede marcada
   como ``receta_provisional=false`` en el contrato.

No usa Evolution, Gemini ni Bunny reales: usa el Juez deterministico, un
notificador en memoria y un Bunny en memoria. La base de datos si es la real.

Uso:
    python scripts/hito3_lock_test.py

Sale con codigo 1 si alguna verificacion falla.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import _path  # noqa: F401

import asyncpg

from app.db import create_pool, run_migrations
from app.m1_whatsapp.bunny import MemoryBunnyStorageClient
from app.m1_whatsapp.debounce import DebounceAccumulator, MemoryBufferStore
from app.m1_whatsapp.identity import IdentityResolver
from app.m1_whatsapp.judges import DeterministicRuleMockJudge
from app.m1_whatsapp.models import (
    IncomingMessage,
    MediaAttachment,
    normalizar_telefono,
)
from app.m1_whatsapp.notifications import RecordingNotifier, SentinelAlerter
from app.m1_whatsapp.pipeline import WhatsAppPipeline
from app.m1_whatsapp.repositorio import PostgresRepositorio
from app.m1_whatsapp.worker import DebounceWorker
from app.sandbox import SandboxBunnyStorageClient, SandboxNotifier
from app.services.ordenes import NuevaOrden, crear_orden
from app.settings import get_settings

TAG = "HITO3-LOCK"
CLIENTE = "Cliente Prueba Hito 3 (WhatsApp)"
# Numeros de prueba: no pertenecen a ninguna persona real ni chocan con las
# semillas de whatsapp.staff (migracion 060), para probar el fallback por codigo.
TEL_BODEGA = "0990000011"
TEL_CHOFER = "0990000012"
TEL_CLIENTE = "0990000013"
TEL_LEAD = "0990000014"

OK = "[OK]"
FALLA = "[FALLA]"


def _linea(titulo: str) -> None:
    print()
    print("=" * 70)
    print(titulo)
    print("=" * 70)


def _check(condicion: bool, mensaje: str) -> bool:
    print(f"  {OK if condicion else FALLA} {mensaje}")
    return condicion


def _msg(telefono: str, texto: str, *, mensaje_id: str, media: tuple = ()) -> IncomingMessage:
    return IncomingMessage(
        mensaje_id=mensaje_id,
        telefono=telefono,
        texto=texto,
        recibido_at=datetime.now(timezone.utc),
        media=media,
    )


async def _limpiar(pool: asyncpg.Pool) -> None:
    """Idempotencia: borra solo lo que el propio test genero."""
    await pool.execute(
        """
        DELETE FROM inventory_movements
         WHERE order_id IN (SELECT id FROM orders WHERE notas = $1)
        """,
        TAG,
    )
    await pool.execute(
        """
        DELETE FROM error_logs
         WHERE order_id IN (SELECT id FROM orders WHERE notas = $1)
        """,
        TAG,
    )
    await pool.execute("DELETE FROM orders WHERE notas = $1", TAG)
    await pool.execute("DELETE FROM clients WHERE notas = $1", TAG)


async def _cliente(pool: asyncpg.Pool) -> str:
    fila = await pool.fetchrow(
        """
        INSERT INTO clients (nombre, telefono_whatsapp, estado, provincia, notas)
        VALUES ($1, $2, 'ACTIVO', 'Sucumbios', $3)
        RETURNING id::text
        """,
        CLIENTE,
        TEL_CLIENTE,
        TAG,
    )
    return fila["id"]


async def _dispatches(pool: asyncpg.Pool, orden_id: str) -> list[dict]:
    filas = await pool.fetch(
        """
        SELECT id::text AS dispatch_id,
               viaje_numero,
               estado_actual,
               tracking_payload::text AS payload
          FROM mixer_dispatches
         WHERE order_id = $1::uuid
         ORDER BY viaje_numero
        """,
        orden_id,
    )
    return [
        {
            "dispatch_id": f["dispatch_id"],
            "viaje_numero": int(f["viaje_numero"]),
            "estado_actual": f["estado_actual"],
            "payload": json.loads(f["payload"]),
        }
        for f in filas
    ]


async def main() -> int:
    settings = get_settings()
    pool = await create_pool(settings.database_url)
    fallos = 0

    try:
        aplicadas = await run_migrations(pool, settings.migrations_dir)
        _linea("HITO 3 - MODULO 1 (WhatsApp) CONTRA POSTGRESQL REAL")
        print(f"  Migraciones aplicadas ahora: {aplicadas or 'ninguna (ya estaban)'}")

        # -----------------------------------------------------------------
        # 0. Modo SANDBOX conmutable (Directriz 2026-11-08).
        # -----------------------------------------------------------------
        _linea("0. MODO SANDBOX (sin credenciales externas)")
        repo_sandbox = PostgresRepositorio(pool)
        notifier_sandbox = SandboxNotifier(repo_sandbox)
        fallos += not _check(
            await notifier_sandbox.enviar_texto(
                "+593990000001", "HITO3-LOCK: prueba de outbox sandbox"
            ),
            "SandboxNotifier acepta el mensaje sin Evolution API",
        )
        outbox = await repo_sandbox.listar_outbox(5)
        fallos += not _check(
            any(
                item["canal"] == "WHATSAPP"
                and item["destino"] == "+593990000001"
                and item["estado"] == "ENCOLADO"
                for item in outbox
            ),
            "El mensaje quedo en sandbox_outbox como ENCOLADO",
        )
        bunny_sandbox = SandboxBunnyStorageClient()
        url_sandbox = await bunny_sandbox.subir(
            nombre_archivo="evidencias/MIXER-01/viaje-1.jpg",
            contenido=b"demo",
            mimetype="image/jpeg",
        )
        fallos += not _check(
            "/sandbox/" in url_sandbox and url_sandbox.startswith("https://"),
            f"Bunny sandbox devuelve URL deterministica ({url_sandbox})",
        )
        from app.m1_whatsapp.runtime import construir_runtime

        runtime_sandbox = await construir_runtime(pool, settings)
        estado_sandbox = runtime_sandbox.estado()
        fallos += not _check(
            estado_sandbox.get("modo") == "SANDBOX",
            f"/health informa modo={estado_sandbox.get('modo')}",
        )
        esperado_juez = (
            "GEMINI" if settings.gemini_api_key else "DETERMINISTIC_FALLBACK"
        )
        fallos += not _check(
            estado_sandbox.get("judge_mode") == esperado_juez,
            f"/health informa judge_mode={estado_sandbox.get('judge_mode')} "
            f"(esperado: {esperado_juez})",
        )
        await runtime_sandbox.cerrar()

        await _limpiar(pool)
        cliente_id = await _cliente(pool)

        orden = await crear_orden(
            pool,
            NuevaOrden(
                cliente_id=cliente_id,
                resistencia="FC-210",
                volumen_m3=Decimal("16"),
                planta_codigo="PLANTA-COCA",
                forma_pago="FIADO",
                notas=TAG,
                creada_por="hito3_lock_test",
            ),
        )
        print(
            f"  Orden #{orden.orden_numero}: 16 m3 FC-210 -> "
            f"{orden.total_viajes} viajes (receta oficial confirmada)"
        )

        repo = PostgresRepositorio(pool)
        acumulador = DebounceAccumulator(MemoryBufferStore(), ventana_segundos=0.1)
        bunny = MemoryBunnyStorageClient(cdn_host="cdn.candado.local")
        notifier = RecordingNotifier()
        pipeline = WhatsAppPipeline(
            repo=repo,
            identidad=IdentityResolver(pool=pool, ttl_segundos=0.0),
            juez=DeterministicRuleMockJudge(),
            bunny=bunny,
            notifier=notifier,
            alerter=SentinelAlerter(webhook_url=None, master_key=None, repo=repo),
        )
        worker = DebounceWorker(
            accumulator=acumulador,
            pipeline=pipeline,
            repo=repo,
            intervalo_segundos=0.01,
        )

        estado = await _dispatches(pool, orden.orden_id)
        fallos += not _check(len(estado) == 2, "La orden genero 2 viajes de 8 m3")
        fallos += not _check(
            all(d["payload"].get("receta_provisional") is False for d in estado),
            "Ambos viajes declaran receta_provisional=false (receta confirmada)",
        )
        viaje_1 = estado[0]["dispatch_id"]
        viaje_2 = estado[1]["dispatch_id"]

        # -----------------------------------------------------------------
        # Celular 1: BODEGA confirma la salida del viaje 1.
        # -----------------------------------------------------------------
        _linea("1. BODEGA -> Gate #1 (salida de planta)")
        ahora = datetime.now(timezone.utc)
        await acumulador.agregar(
            _msg(
                TEL_BODEGA,
                f"Ya salio el mixer #M1, orden #{orden.orden_numero}, viaje V1 #BODEGA",
                mensaje_id="H3-BODEGA-1",
            ),
            ahora=ahora - timedelta(seconds=10),
        )
        resultados = await worker.tick()
        bodega = resultados[0] if resultados else None
        fallos += not _check(len(resultados) == 1, "El debounce entrego 1 lote de bodega")
        fallos += not _check(
            bodega is not None and bodega.rol == "BODEGA_PLANTA",
            "Identidad por codigo #BODEGA (telefono no registrado)",
        )
        fallos += not _check(
            bodega is not None and bodega.estado_actual == "EN_RUTA",
            "Gate #1 dejo el viaje 1 en EN_RUTA",
        )

        fila = await pool.fetchrow(
            """
            SELECT estado_actual,
                   tracking_payload::text AS payload
              FROM mixer_dispatches WHERE id = $1::uuid
            """,
            viaje_1,
        )
        payload_1 = json.loads(fila["payload"])
        tiempos = payload_1["tiempos_forenses"]
        salida_crudo = tiempos.get("salida_planta")
        limite_crudo = tiempos.get("limite_termico_fraguado")
        delta_min = -1.0
        if salida_crudo and limite_crudo:
            salida = datetime.fromisoformat(salida_crudo)
            limite = datetime.fromisoformat(limite_crudo)
            delta_min = (limite - salida).total_seconds() / 60
        fallos += not _check(
            fila["estado_actual"] == "EN_RUTA",
            "Trigger: columna estado_actual = EN_RUTA (proyectada del JSONB)",
        )
        fallos += not _check(
            abs(delta_min - 150) < 0.1,
            f"Limite termico = salida + 150 min (calculado: {delta_min:.1f})",
        )
        fallos += not _check(
            (salida_crudo or "").endswith("-05:00"),
            "Sellos forenses con offset de America/Guayaquil (-05:00)",
        )
        fallos += not _check(
            payload_1["juez_binario_jeb"]["despacho_validado"] is True,
            "Juez Binario marco despacho_validado=true",
        )
        fallos += not _check(
            payload_1["receta_provisional"] is False,
            "La venta corrio con receta confirmada (receta_provisional=false)",
        )
        fallos += not _check(
            len(notifier.enviados) == 1
            and notifier.enviados[0]["telefono"] == TEL_CLIENTE,
            "Aviso de salida encolado al telefono del cliente",
        )

        # -----------------------------------------------------------------
        # Celular 2: CHOFER manda la evidencia.
        # -----------------------------------------------------------------
        _linea("2. CHOFER -> Gate #3 (evidencia a Bunny.net)")
        await acumulador.agregar(
            _msg(
                TEL_CHOFER,
                "#M1 llegue a la obra, adjunto guia de remision",
                mensaje_id="H3-CHOFER-1",
                media=(
                    MediaAttachment(
                        tipo="imagen",
                        mimetype="image/jpeg",
                        nombre="guia.jpg",
                        base64="aG9sYQ==",
                    ),
                ),
            ),
            ahora=datetime.now(timezone.utc) - timedelta(seconds=8),
        )
        resultados = await worker.tick()
        chofer = resultados[0] if resultados else None
        fallos += not _check(
            chofer is not None and chofer.rol == "CHOFER_MIXER",
            "Identidad por codigo #M1 (CHOFER_MIXER)",
        )
        fallos += not _check(
            chofer is not None
            and chofer.compuerta == "GATE_3_EVIDENCIA"
            and "EVIDENCIA_SUBIDA:1" in chofer.acciones,
            "Gate #3 subio 1 adjunto al storage",
        )

        fila = await pool.fetchrow(
            "SELECT tracking_payload::text AS payload FROM mixer_dispatches WHERE id = $1::uuid",
            viaje_1,
        )
        payload_1 = json.loads(fila["payload"])
        fallos += not _check(
            len(payload_1["evidencias_bunny_cdn"]) == 1,
            "URL de Bunny.net quedo en evidencias_bunny_cdn",
        )
        fallos += not _check(
            payload_1["tiempos_forenses"]["llegada_obra_chofer"] is not None,
            "Sello llegada_obra_chofer registrado",
        )

        # -----------------------------------------------------------------
        # Celular 3: CLIENTE escribe en 4 fragmentos (debounce) y confirma.
        # -----------------------------------------------------------------
        _linea("3. CLIENTE -> Gate #2 (debounce de 4 mensajes + sello)")
        base = datetime.now(timezone.utc) - timedelta(seconds=1)
        for indice, fragmento in enumerate(
            ["Recibi", "el hormigon", "conforme", "muchas gracias"]
        ):
            await acumulador.agregar(
                _msg(
                    TEL_CLIENTE,
                    fragmento,
                    mensaje_id=f"H3-CLIENTE-{indice}",
                ),
                ahora=base + timedelta(seconds=0.02 * indice),
            )
        resultados = await worker.tick()
        cliente = resultados[0] if resultados else None
        fallos += not _check(
            len(resultados) == 1,
            "Los 4 fragmentos salieron como UN solo lote (ventana de silencio)",
        )
        fallos += not _check(
            cliente is not None and cliente.rol == "CLIENTE",
            "Identidad por telefono registrado en clients",
        )
        fallos += not _check(
            cliente is not None and cliente.estado_actual == "CONFIRMADO_CLIENTE",
            "Gate #2 sello la recepcion del viaje 1",
        )

        fila = await pool.fetchrow(
            """
            SELECT estado_actual,
                   tracking_payload::text AS payload,
                   (tracking_payload #>> '{tiempos_forenses,confirmacion_whatsapp_cliente}') AS confirmacion
              FROM mixer_dispatches WHERE id = $1::uuid
            """,
            viaje_1,
        )
        payload_1 = json.loads(fila["payload"])
        fallos += not _check(
            fila["estado_actual"] == "CONFIRMADO_CLIENTE",
            "Trigger: columna estado_actual = CONFIRMADO_CLIENTE",
        )
        fallos += not _check(
            payload_1["mensaje_literal_cliente"]
            == "Recibi el hormigon conforme muchas gracias",
            "Mensaje literal del cliente quedo como evidencia forense",
        )
        fallos += not _check(
            fila["confirmacion"] is not None,
            "Sello confirmacion_whatsapp_cliente registrado",
        )

        vista = await pool.fetchrow(
            """
            SELECT salida_planta, limite_termico_fraguado,
                   confirmacion_whatsapp_cliente, despacho_validado,
                   recepcion_validada
              FROM v_dispatch_timeline WHERE id = $1::uuid
            """,
            viaje_1,
        )
        fallos += not _check(
            vista["salida_planta"] is not None
            and vista["limite_termico_fraguado"] is not None
            and vista["confirmacion_whatsapp_cliente"] is not None,
            "v_dispatch_timeline expone los tres sellos del viaje 1",
        )
        fallos += not _check(
            vista["despacho_validado"] is True and vista["recepcion_validada"] is True,
            "v_dispatch_timeline expone las dos validaciones del Juez",
        )

        # -----------------------------------------------------------------
        # Reclamo: el cliente reporta demora en el viaje 2.
        # -----------------------------------------------------------------
        _linea("4. RECLAMO -> alerta al Centinela")
        await acumulador.agregar(
            _msg(
                TEL_BODEGA,
                f"Ya salio el mixer #M1, orden #{orden.orden_numero}, viaje V2 #BODEGA",
                mensaje_id="H3-BODEGA-2",
            ),
            ahora=datetime.now(timezone.utc) - timedelta(seconds=6),
        )
        await worker.tick()
        await acumulador.agregar(
            _msg(
                TEL_CLIENTE,
                "Hay mucha demora, el hormigon del viaje 2 no ha llegado",
                mensaje_id="H3-RECLAMO-1",
            ),
            ahora=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        resultados = await worker.tick()
        reclamo = resultados[0] if resultados else None
        fallos += not _check(
            reclamo is not None and reclamo.estado_actual == "INCIDENCIA_RECLAMO",
            "El reclamo dejo el viaje 2 en INCIDENCIA_RECLAMO",
        )
        fallos += not _check(
            reclamo is not None
            and reclamo.alerta is not None
            and reclamo.alerta["estado"] == "NO_CONFIGURADO",
            "Sin AGENCY_CRM_WEBHOOK_URL la alerta degrada a NO_CONFIGURADO",
        )

        log = await pool.fetchrow(
            """
            SELECT nivel, origen, contexto::text AS contexto
              FROM error_logs
             WHERE dispatch_id = $1::uuid
               AND contexto ->> 'codigo' = 'INCIDENCIA_RECLAMO_CLIENTE'
             ORDER BY id DESC LIMIT 1
            """,
            viaje_2,
        )
        fallos += not _check(
            log is not None
            and log["nivel"] == "ERROR"
            and log["origen"] == "M1_WHATSAPP",
            "La incidencia quedo en error_logs (origen M1_WHATSAPP, nivel ERROR)",
        )

        # -----------------------------------------------------------------
        # Celular 4: LEAD desconocido -> Gate #4 (bot de atencion publico).
        # -----------------------------------------------------------------
        _linea("5. LEAD -> Gate #4 (respuesta con ADN y precios en vivo)")
        await acumulador.agregar(
            _msg(
                TEL_LEAD,
                "Buenas tardes, necesito cotizacion de hormigon para 20 m3",
                mensaje_id="H3-LEAD-1",
            ),
            ahora=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        resultados = await worker.tick()
        lead = resultados[0] if resultados else None
        fallos += not _check(
            lead is not None and lead.rol == "LEAD_DESCONOCIDO",
            "Numero desconocido entra como LEAD_DESCONOCIDO",
        )
        fallos += not _check(
            lead is not None and lead.compuerta == "GATE_4_LEAD",
            "Gate #4 califico el mensaje como solicitud de cotizacion",
        )
        respuesta = (lead.respuesta if lead else "") or ""
        marca_ok = "horminor" in respuesta.lower() or "orminorth" in respuesta.lower()
        fallos += not _check(
            marca_ok and "FC-210" in respuesta,
            "La respuesta usa empresa.bot_publico y las recetas de la base",
        )
        fallos += not _check(
            "$118.00" in respuesta and "Orellana" in respuesta,
            "La respuesta incluye precio FC-210 y cobertura de Orellana",
        )
        fallos += not _check(
            any(
                normalizar_telefono(envio["telefono"]) == normalizar_telefono(TEL_LEAD)
                and (
                    "horminor" in envio["texto"].lower()
                    or "orminorth" in envio["texto"].lower()
                )
                for envio in notifier.enviados
            ),
            "El bot respondio al telefono del lead por WhatsApp",
        )
        prospecto = await pool.fetchrow(
            "SELECT estado FROM clients WHERE telefono_whatsapp = $1",
            normalizar_telefono(TEL_LEAD),
        )
        fallos += not _check(
            prospecto is not None and prospecto["estado"] == "PROSPECTO",
            "El lead quedo registrado como PROSPECTO para Secretaria",
        )

        # -----------------------------------------------------------------
        # Verificacion final del trigger en los dos viajes.
        # -----------------------------------------------------------------
        _linea("6. CONTRATO JSONB vs COLUMNAS PLANAS")
        filas = await pool.fetch(
            """
            SELECT id::text AS dispatch_id,
                   estado_actual,
                   tracking_payload ->> 'estado_actual' AS estado_json
              FROM mixer_dispatches
             WHERE order_id = $1::uuid
             ORDER BY viaje_numero
            """,
            orden.orden_id,
        )
        for fila in filas:
            fallos += not _check(
                fila["estado_actual"] == fila["estado_json"],
                f"Viaje {fila['dispatch_id'][:8]}: columna = JSON ({fila['estado_json']})",
            )

        _linea("RESULTADO")
        if fallos == 0:
            print("  [CANDADO CERRADO EN SANDBOX] El Modulo 1 ejecuta las 4 compuertas,")
            print("  el contrato JSONB se proyecta sin errores y el modo SANDBOX encola")
            print("  la salida sin fingir un envio real.")
            print("  Las credenciales reales (Evolution, Bunny, Gemini) y los telefonos")
            print("  definitivos se cargan despues desde Superadmin; ya no bloquean.")
            return 0
        print(f"  [CANDADO BLOQUEADO] {fallos} verificacion(es) fallaron.")
        return 1
    finally:
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
