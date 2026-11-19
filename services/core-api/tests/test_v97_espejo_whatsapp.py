"""Tests del espejo bidireccional de WhatsApp (v9.7).

No tocan Evolution, Redis ni PostgreSQL: usan la identidad pura, la
normalizacion de mensajes y el repositorio en memoria. La regla que se
verifica es la del alcance: **sin numero autorizado no se persiste nada**.
"""

from __future__ import annotations

import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.whatsapp_espejo import (  # noqa: E402
    BusEventos,
    EspejoNoAutorizado,
    EspejoWhatsApp,
    MemoryRepositorioEspejo,
    NumeroEspejo,
    configuracion_evolution,
    desde_registro,
    resolver_jid,
    telefono_canonico,
)

PANEL = RAIZ_SERVICIO / "app" / "web" / "templates" / "panel.html"
MAIN = RAIZ_SERVICIO / "app" / "main.py"
CHAT = RAIZ_SERVICIO / "app" / "routers" / "chat_clientes.py"


def _migracion() -> Path:
    for base in (RAIZ_SERVICIO, *RAIZ_SERVICIO.parents):
        candidato = base / "db" / "migrations" / "093_whatsapp_espejo.sql"
        if candidato.is_file():
            return candidato
    raise FileNotFoundError("093_whatsapp_espejo.sql no encontrada")


MIGRACION = _migracion()


def registro(
    mensaje_id: str,
    jid: str,
    texto: str = "Hola",
    *,
    from_me: bool = False,
    alt: str | None = None,
    status: str = "DELIVERY_ACK",
    timestamp: int = 1_763_000_000,
) -> dict[str, Any]:
    clave: dict[str, Any] = {
        "id": mensaje_id,
        "remoteJid": jid,
        "fromMe": from_me,
        "messageTimestamp": timestamp,
    }
    if alt:
        clave["remoteJidAlt"] = alt
    return {
        "key": clave,
        "message": {"conversation": texto},
        "messageType": "conversation",
        "status": status,
        "pushName": "Contacto",
    }


class FakeEvolution:
    """Devuelve paginas prefabricadas por JID."""

    def __init__(self, paginas: dict[str, list[list[dict[str, Any]]]]) -> None:
        self.paginas = paginas
        self.llamadas: list[tuple[str, int]] = []

    async def buscar_mensajes(
        self, jid: str, *, page: int = 1, offset: int = 100
    ) -> dict[str, Any]:
        self.llamadas.append((jid, page))
        bloques = self.paginas.get(jid, [])
        if page > len(bloques):
            return {"records": [], "total": 0, "pages": len(bloques), "page": page}
        return {
            "records": bloques[page - 1],
            "total": sum(len(b) for b in bloques),
            "pages": len(bloques),
            "page": page,
        }


def build_espejo(
    *, telefono: str = "593991234567", cliente_id: str = "c1"
) -> tuple[EspejoWhatsApp, MemoryRepositorioEspejo]:
    repo = MemoryRepositorioEspejo()
    repo.clientes[cliente_id] = True
    repo.numeros[telefono] = NumeroEspejo(
        telefono=telefono, cliente_id=cliente_id, activo=True
    )
    return EspejoWhatsApp(repo), repo


# ---------------------------------------------------------------------------
# Identidad
# ---------------------------------------------------------------------------
def test_telefono_canonico_acepta_las_formas_ecuatorianas() -> None:
    assert telefono_canonico("0991234567") == "593991234567"
    assert telefono_canonico("991234567") == "593991234567"
    assert telefono_canonico("+593 99 123 4567") == "593991234567"
    assert telefono_canonico("00593991234567") == "593991234567"
    assert telefono_canonico("") is None
    assert telefono_canonico("123") is None


def test_resolver_pn_usa_el_telefono_real() -> None:
    identidad = resolver_jid("593991234567@s.whatsapp.net")
    assert identidad.origen == "PN"
    assert identidad.telefono == "593991234567"
    assert identidad.ambiguo is False


def test_resolver_lid_con_remote_jid_alt() -> None:
    identidad = resolver_jid(
        "153459886145727@lid", "593986962872@s.whatsapp.net"
    )
    assert identidad.origen == "ALT"
    assert identidad.telefono == "593986962872"
    assert identidad.jid_telefono == "593986962872@s.whatsapp.net"


def test_resolver_lid_por_alias_conocido() -> None:
    identidad = resolver_jid(
        "153459886145727@lid",
        alias={"153459886145727@lid": "593986962872"},
    )
    assert identidad.origen == "LID"
    assert identidad.telefono == "593986962872"


def test_resolver_lid_sin_alt_es_ambiguo_no_es_un_telefono() -> None:
    identidad = resolver_jid("153459886145727@lid")
    assert identidad.ambiguo is True
    assert identidad.telefono is None
    assert identidad.motivo == "LID_SIN_TELEFONO"


def test_resolver_grupo_y_canal_se_ignoran() -> None:
    assert resolver_jid("120363000000000000@g.us").ignorado is True
    assert resolver_jid("status@broadcast").ignorado is True


# ---------------------------------------------------------------------------
# Normalizacion
# ---------------------------------------------------------------------------
def test_desde_registro_distingue_entrante_y_saliente() -> None:
    entrante = desde_registro(registro("m1", "593991234567@s.whatsapp.net"))
    saliente = desde_registro(
        registro("m2", "593991234567@s.whatsapp.net", from_me=True, status="READ")
    )
    assert entrante is not None and entrante.direccion == "ENTRANTE"
    assert entrante.autor_tipo == "CLIENTE"
    assert saliente is not None and saliente.direccion == "SALIENTE"
    assert saliente.autor_tipo == "OPERADOR"
    assert saliente.estado_entrega == "LEIDO"


def test_historial_sin_status_usa_el_estado_real_conocido() -> None:
    """findMessages no trae status: no se inventa una confirmacion de entrega."""
    base = {
        "key": {"id": "h1", "remoteJid": "593991234567@s.whatsapp.net"},
        "message": {"conversation": "Hola"},
        "messageType": "conversation",
    }
    entrante = desde_registro(base)
    assert entrante is not None and entrante.estado_entrega == "ENTREGADO"

    saliente = desde_registro(
        {
            **base,
            "key": {**base["key"], "id": "h2", "fromMe": True},
        }
    )
    assert saliente is not None and saliente.estado_entrega == "ENVIADO"


def test_desde_registro_descarta_protocolo_y_conserva_multimedia() -> None:
    protocolo = registro("m3", "593991234567@s.whatsapp.net")
    protocolo["message"] = {"protocolMessage": {"type": "REVOKE"}}
    assert desde_registro(protocolo) is None

    foto = {
        "key": {"id": "m4", "remoteJid": "593991234567@s.whatsapp.net"},
        "message": {"imageMessage": {"mimetype": "image/jpeg", "caption": "Avance"}},
        "messageType": "imageMessage",
    }
    mensaje = desde_registro(foto)
    assert mensaje is not None
    assert mensaje.cuerpo == "Avance"
    assert mensaje.adjuntos[0]["tipo"] == "IMAGEN"
    assert mensaje.adjuntos[0]["pendiente_descarga"] is True


# ---------------------------------------------------------------------------
# Lista blanca
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sin_numero_autorizado_no_se_persiste_nada() -> None:
    repo = MemoryRepositorioEspejo()
    espejo = EspejoWhatsApp(repo)
    resultado = await espejo.ingerir(
        registro("m1", "593990000000@s.whatsapp.net")
    )
    assert resultado == "NO_AUTORIZADO"
    assert repo.mensajes == []
    assert repo.conversaciones == {}


@pytest.mark.asyncio
async def test_numero_autorizado_importa_y_no_duplica() -> None:
    espejo, repo = build_espejo()
    primero = await espejo.ingerir(
        registro("m1", "593991234567@s.whatsapp.net", "Buenos días")
    )
    segundo = await espejo.ingerir(
        registro("m1", "593991234567@s.whatsapp.net", "Buenos días")
    )
    assert primero == "IMPORTADO"
    assert segundo == "DUPLICADO"
    assert len(repo.mensajes) == 1
    assert repo.mensajes[0]["direccion"] == "ENTRANTE"
    assert repo.mensajes[0]["cuerpo"] == "Buenos días"


@pytest.mark.asyncio
async def test_otro_numero_no_entra_aunque_el_autorizado_exista() -> None:
    espejo, repo = build_espejo()
    resultado = await espejo.ingerir(
        registro("m2", "593987654321@s.whatsapp.net", "Soy otro contacto")
    )
    assert resultado == "NO_AUTORIZADO"
    assert len(repo.mensajes) == 0


@pytest.mark.asyncio
async def test_from_me_del_telefono_se_guarda_como_saliente() -> None:
    espejo, repo = build_espejo()
    resultado = await espejo.ingerir(
        registro(
            "m3",
            "593991234567@s.whatsapp.net",
            "Respuesta enviada desde el teléfono",
            from_me=True,
            status="DELIVERY_ACK",
        )
    )
    assert resultado == "IMPORTADO"
    assert repo.mensajes[0]["direccion"] == "SALIENTE"
    assert repo.mensajes[0]["from_me"] is True
    assert repo.mensajes[0]["estado_entrega"] == "ENTREGADO"


@pytest.mark.asyncio
async def test_duplicado_avanza_el_estado_de_entrega() -> None:
    espejo, repo = build_espejo()
    await espejo.ingerir(
        registro(
            "m3b",
            "593991234567@s.whatsapp.net",
            "Respuesta desde el teléfono",
            from_me=True,
            status="SERVER_ACK",
        )
    )
    assert repo.mensajes[0]["estado_entrega"] == "ENVIADO"
    repetido = await espejo.ingerir(
        registro(
            "m3b",
            "593991234567@s.whatsapp.net",
            "Respuesta desde el teléfono",
            from_me=True,
            status="READ",
        )
    )
    assert repetido == "DUPLICADO"
    assert len(repo.mensajes) == 1
    assert repo.mensajes[0]["estado_entrega"] == "LEIDO"


@pytest.mark.asyncio
async def test_registro_con_contexto_y_texto_no_se_descarta() -> None:
    """Evolution adjunta messageContextInfo a mensajes validos: no es ruido."""
    espejo, repo = build_espejo()
    bruto = registro("ctx1", "593991234567@s.whatsapp.net", "Mensaje real")
    bruto["message"]["messageContextInfo"] = {"deviceListMetadata": {}}
    resultado = await espejo.ingerir(bruto)
    assert resultado == "IMPORTADO"
    assert repo.mensajes[0]["cuerpo"] == "Mensaje real"


@pytest.mark.asyncio
async def test_lid_con_alt_autorizado_registra_el_alias() -> None:
    espejo, repo = build_espejo()
    resultado = await espejo.ingerir(
        registro(
            "m5",
            "153459886145727@lid",
            "Hola desde LID",
            alt="593991234567@s.whatsapp.net",
        )
    )
    assert resultado == "IMPORTADO"
    assert repo.jids["153459886145727@lid"] == "593991234567"
    assert repo.jids["593991234567@s.whatsapp.net"] == "593991234567"


@pytest.mark.asyncio
async def test_lid_ambiguo_no_se_importa_y_queda_pendiente() -> None:
    espejo, repo = build_espejo()
    resultado = await espejo.ingerir(
        registro("m6", "153459886145727@lid", "¿Quién soy?")
    )
    assert resultado == "AMBIGUO"
    assert repo.mensajes == []
    assert len(repo.pendientes) == 1
    assert repo.pendientes[0]["motivo"] == "LID_SIN_TELEFONO"
    # Nunca se guarda el contenido de un numero no resuelto.
    assert "¿Quién soy?" not in str(repo.pendientes[0])


@pytest.mark.asyncio
async def test_lid_sin_alt_aprende_el_telefono_del_historial() -> None:
    """WhatsApp omite remoteJidAlt: el par LID->telefono se aprende del historial."""

    class EvolutionConHistorial:
        def __init__(self) -> None:
            self.consultados: list[str] = []

        async def telefono_de_lid(self, lid: str) -> str | None:
            self.consultados.append(lid)
            return "593991234567"

    repo = MemoryRepositorioEspejo()
    repo.clientes["c1"] = True
    repo.numeros["593991234567"] = NumeroEspejo(
        telefono="593991234567", cliente_id="c1", activo=True
    )
    historial = EvolutionConHistorial()
    espejo = EspejoWhatsApp(repo, evolution=historial)

    resultado = await espejo.ingerir(
        registro("m-lid-sin-alt", "153459886145727@lid", "Hola desde LID")
    )

    assert resultado == "IMPORTADO"
    assert historial.consultados == ["153459886145727@lid"]
    assert repo.jids["153459886145727@lid"] == "593991234567"
    assert repo.jids["593991234567@s.whatsapp.net"] == "593991234567"
    assert repo.mensajes[0]["cuerpo"] == "Hola desde LID"
    # Se resuelve una sola vez: el alias queda registrado.
    assert repo.pendientes == []


@pytest.mark.asyncio
async def test_lid_sin_historial_sigue_ambiguo_y_no_se_reintenta() -> None:
    class EvolutionSinDatos:
        def __init__(self) -> None:
            self.consultados = 0

        async def telefono_de_lid(self, lid: str) -> str | None:
            self.consultados += 1
            return None

    repo = MemoryRepositorioEspejo()
    repo.clientes["c1"] = True
    repo.numeros["593991234567"] = NumeroEspejo(
        telefono="593991234567", cliente_id="c1", activo=True
    )
    historial = EvolutionSinDatos()
    espejo = EspejoWhatsApp(repo, evolution=historial)

    assert await espejo.ingerir(registro("m-a", "31387822325914@lid", "uno")) == "AMBIGUO"
    assert await espejo.ingerir(registro("m-b", "31387822325914@lid", "dos")) == "AMBIGUO"

    assert repo.mensajes == []
    assert len(repo.pendientes) == 2
    assert repo.pendientes[0]["motivo"] == "LID_SIN_TELEFONO"
    # El historial se consulta una vez por LID, no en cada mensaje.
    assert historial.consultados == 1


@pytest.mark.asyncio
async def test_grupo_no_se_importa() -> None:
    espejo, repo = build_espejo()
    resultado = await espejo.ingerir(
        registro("m7", "120363000000000000@g.us", "Mensaje de grupo")
    )
    assert resultado == "IGNORADO"
    assert repo.mensajes == []


@pytest.mark.asyncio
async def test_retirar_el_numero_corta_la_ingesta_y_conserva_historial() -> None:
    espejo, repo = build_espejo()
    await espejo.ingerir(registro("m8", "593991234567@s.whatsapp.net", "Antes"))
    assert await repo.activar_numero("593991234567", False) is True
    resultado = await espejo.ingerir(
        registro("m9", "593991234567@s.whatsapp.net", "Después")
    )
    assert resultado == "NO_AUTORIZADO"
    assert len(repo.mensajes) == 1
    assert repo.mensajes[0]["cuerpo"] == "Antes"


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_webhook_procesa_upsert_y_update_de_estado() -> None:
    espejo, repo = build_espejo()
    payload = {
        "event": "MESSAGES_UPSERT",
        "data": [registro("m10", "593991234567@s.whatsapp.net", "Hola")],
    }
    resumen = await espejo.procesar_payload(payload)
    assert resumen["IMPORTADO"] == 1
    assert repo.mensajes[0]["estado_entrega"] == "ENTREGADO"

    update = {
        "event": "MESSAGES_UPDATE",
        "data": [
            {
                "key": {"id": "m10", "remoteJid": "593991234567@s.whatsapp.net"},
                "status": "READ",
            }
        ],
    }
    await espejo.procesar_payload(update)
    assert repo.mensajes[0]["estado_entrega"] == "LEIDO"

    # Un estado viejo no degrada uno nuevo.
    await espejo.procesar_payload(
        {
            "event": "MESSAGES_UPDATE",
            "data": [{"key": {"id": "m10"}, "status": "SERVER_ACK"}],
        }
    )
    assert repo.mensajes[0]["estado_entrega"] == "LEIDO"


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_backfill_pagina_e_es_idempotente() -> None:
    espejo, repo = build_espejo()
    evolution = FakeEvolution(
        {
            "593991234567@s.whatsapp.net": [
                [
                    registro("p1", "593991234567@s.whatsapp.net", "Página 1 - A"),
                    registro("p2", "593991234567@s.whatsapp.net", "Página 1 - B"),
                ],
                [registro("p3", "593991234567@s.whatsapp.net", "Página 2 - A")],
            ]
        }
    )
    espejo._evolution = evolution  # cliente inyectado
    primero = await espejo.sincronizar(cliente_id="c1")
    assert primero.importados == 3
    assert primero.paginas == 2
    assert len(repo.mensajes) == 3

    segundo = await espejo.sincronizar(cliente_id="c1")
    assert segundo.importados == 0
    assert len(repo.mensajes) == 3
    assert repo.numeros["593991234567"].mensajes_importados == 3


@pytest.mark.asyncio
async def test_backfill_rechaza_cliente_sin_numero_autorizado() -> None:
    repo = MemoryRepositorioEspejo()
    repo.clientes["c2"] = True
    espejo = EspejoWhatsApp(repo, evolution=FakeEvolution({}))
    with pytest.raises(EspejoNoAutorizado):
        await espejo.sincronizar(cliente_id="c2")


@pytest.mark.asyncio
async def test_backfill_no_copia_antes_del_alta_del_cliente() -> None:
    """Regla de Julio: solo cuenta desde que el contacto es cliente o lead."""
    viejo = 1_700_000_000  # 2023
    nuevo = 1_763_000_000  # dentro del corte
    espejo, repo = build_espejo()
    repo.numeros["593991234567"] = NumeroEspejo(
        telefono="593991234567",
        cliente_id="c1",
        activo=True,
        desde=datetime.fromtimestamp(1_750_000_000, tz=timezone.utc),
    )
    espejo._evolution = FakeEvolution(
        {
            "593991234567@s.whatsapp.net": [
                [
                    registro("nuevo-1", "593991234567@s.whatsapp.net", "Después del alta", timestamp=nuevo),
                    registro("viejo-1", "593991234567@s.whatsapp.net", "Antes del alta", timestamp=viejo),
                ]
            ]
        }
    )
    resultado = await espejo.sincronizar(cliente_id="c1")
    assert resultado.importados == 1
    assert resultado.omitidos == 1
    assert len(repo.mensajes) == 1
    assert repo.mensajes[0]["cuerpo"] == "Después del alta"


@pytest.mark.asyncio
async def test_sin_corte_el_backfill_importa_todo() -> None:
    espejo, repo = build_espejo()
    viejo = 1_700_000_000
    espejo._evolution = FakeEvolution(
        {
            "593991234567@s.whatsapp.net": [
                [registro("v-1", "593991234567@s.whatsapp.net", "Histórico", timestamp=viejo)]
            ]
        }
    )
    resultado = await espejo.sincronizar(cliente_id="c1")
    assert resultado.importados == 1
    assert resultado.omitidos == 0


def test_migracion_095_agrega_el_corte_de_historial() -> None:
    ruta = _migracion().with_name("095_espejo_corte_historial.sql")
    assert ruta.is_file(), "095_espejo_corte_historial.sql no encontrada"
    sql = ruta.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS desde timestamptz" in sql


def _registro_imagen(mensaje_id: str, jid: str) -> dict[str, Any]:
    return {
        "key": {"id": mensaje_id, "remoteJid": jid, "fromMe": False, "messageTimestamp": 1_763_000_000},
        "message": {
            "imageMessage": {
                "mimetype": "image/jpeg",
                "caption": "Foto de la obra",
                "fileLength": 12,
            }
        },
        "messageType": "imageMessage",
        "status": "DELIVERY_ACK",
        "pushName": "Contacto",
    }


@pytest.mark.asyncio
async def test_multimedia_entrante_se_descarga_y_queda_en_el_hilo(tmp_path) -> None:
    """Imagen/audio/video: se baja de Evolution y queda como adjunto del mensaje."""

    class EvolutionConMedia:
        def __init__(self) -> None:
            self.pedidos: list[tuple[str, str, bool]] = []

        async def obtener_media_base64(self, mensaje_id: str, jid: str, from_me: bool):
            self.pedidos.append((mensaje_id, jid, from_me))
            return {
                "base64": base64.b64encode(b"contenido-de-prueba").decode(),
                "mimetype": "image/jpeg",
                "nombre": "obra.jpg",
            }

    repo = MemoryRepositorioEspejo()
    repo.clientes["c1"] = True
    repo.numeros["593991234567"] = NumeroEspejo(
        telefono="593991234567", cliente_id="c1", activo=True
    )
    medios = EvolutionConMedia()
    espejo = EspejoWhatsApp(
        repo,
        evolution=medios,
        settings=SimpleNamespace(media_dir=str(tmp_path), media_max_pixeles=50_000_000),
    )

    resultado = await espejo.ingerir(_registro_imagen("img-1", "593991234567@s.whatsapp.net"))

    assert resultado == "IMPORTADO"
    assert medios.pedidos == [("img-1", "593991234567@s.whatsapp.net", False)]
    assert len(repo.media) == 1
    assert repo.media[0]["tipo"] == "IMAGEN"
    assert repo.adjuntos_actualizados, "no se actualizaron los adjuntos del mensaje"
    adjuntos = repo.adjuntos_actualizados[0]["adjuntos"]
    assert adjuntos[0]["pendiente_descarga"] is False
    assert adjuntos[0]["media_id"]


@pytest.mark.asyncio
async def test_multimedia_va_a_bunny_con_el_prefijo_configurado(tmp_path, monkeypatch) -> None:
    """La 'carpeta' de Bunny es el prefijo de la ruta: se antepone al cliente."""

    class EvolutionConMedia:
        async def obtener_media_base64(self, mensaje_id: str, jid: str, from_me: bool):
            return {
                "base64": base64.b64encode(b"bytes-de-imagen").decode(),
                "mimetype": "image/jpeg",
                "nombre": "obra.jpg",
            }

    repo = MemoryRepositorioEspejo()
    repo.clientes["c1"] = True
    repo.numeros["593991234567"] = NumeroEspejo(
        telefono="593991234567", cliente_id="c1", activo=True
    )
    repo.bunny = {
        "storage_zone": "horminor-media",
        "api_key": "clave",
        "cdn_host": "horminor.b-cdn.net",
        "prefijo": "horminor",
        "sandbox": False,
    }
    espejo = EspejoWhatsApp(
        repo,
        evolution=EvolutionConMedia(),
        settings=SimpleNamespace(media_dir=str(tmp_path), media_max_pixeles=50_000_000),
    )
    subidas: dict[str, str] = {}

    async def falso_subir(cfg, storage_path, datos, mime):
        subidas["ruta"] = storage_path
        subidas["mime"] = mime
        return f"https://horminor.b-cdn.net/{storage_path}"

    monkeypatch.setattr(espejo, "_subir_a_bunny", falso_subir)

    assert await espejo.ingerir(_registro_imagen("img-bunny", "593991234567@s.whatsapp.net")) == "IMPORTADO"
    assert subidas["ruta"].startswith("horminor/clientes/")
    assert repo.media[0]["backend"] == "BUNNY"
    assert repo.media[0]["cdn_url"].startswith("https://horminor.b-cdn.net/")


@pytest.mark.asyncio
async def test_si_la_descarga_falla_el_mensaje_igual_se_guarda(tmp_path) -> None:
    class EvolutionSinMedia:
        async def obtener_media_base64(self, mensaje_id: str, jid: str, from_me: bool):
            raise RuntimeError("Evolution no respondio")

    repo = MemoryRepositorioEspejo()
    repo.clientes["c1"] = True
    repo.numeros["593991234567"] = NumeroEspejo(
        telefono="593991234567", cliente_id="c1", activo=True
    )
    espejo = EspejoWhatsApp(
        repo,
        evolution=EvolutionSinMedia(),
        settings=SimpleNamespace(media_dir=str(tmp_path), media_max_pixeles=50_000_000),
    )
    resultado = await espejo.ingerir(_registro_imagen("img-2", "593991234567@s.whatsapp.net"))
    assert resultado == "IMPORTADO"
    assert repo.mensajes, "el texto del mensaje no se pierde si la media falla"
    assert repo.media == []


# ---------------------------------------------------------------------------
# Contrato de despliegue
# ---------------------------------------------------------------------------
def test_migracion_define_lista_blanca_alias_y_pendientes() -> None:
    sql = MIGRACION.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS whatsapp_espejo_numeros" in sql
    assert "CREATE TABLE IF NOT EXISTS whatsapp_espejo_jids" in sql
    assert "CREATE TABLE IF NOT EXISTS whatsapp_espejo_pendientes" in sql
    assert "CREATE TABLE IF NOT EXISTS whatsapp_espejo_cursor" in sql
    assert "ON DELETE CASCADE" in sql
    assert "activo                 boolean NOT NULL DEFAULT true" in sql


def test_migracion_094_hace_monotono_el_preview_del_hilo() -> None:
    ruta = _migracion().with_name("094_chat_preview_monotono.sql")
    assert ruta.is_file(), "094_chat_preview_monotono.sql no encontrada"
    sql = ruta.read_text(encoding="utf-8")
    assert "CREATE OR REPLACE FUNCTION chat_marcar_ultimo_mensaje" in sql
    assert "NEW.created_at >= ultimo_mensaje_at" in sql
    assert "ultimo_mensaje_at IS NULL" in sql


def test_main_registra_el_espejo_y_su_router() -> None:
    fuente = MAIN.read_text(encoding="utf-8")
    assert "from .whatsapp_espejo import BusEventos, EspejoWhatsApp, PostgresRepositorioEspejo" in fuente
    assert "app.state.espejo = EspejoWhatsApp(" in fuente
    assert "app.include_router(espejo_router)" in fuente


def test_webhook_del_modulo_1_llama_al_espejo() -> None:
    fuente = (RAIZ_SERVICIO / "app" / "m1_whatsapp" / "router.py").read_text(
        encoding="utf-8"
    )
    assert 'getattr(request.app.state, "espejo", None)' in fuente
    assert "await espejo.procesar_payload(payload)" in fuente


def test_panel_tiene_sincronizacion_y_refresco() -> None:
    html = PANEL.read_text(encoding="utf-8")
    assert 'id="chat-sync"' in html
    assert "async function chatSincronizar(" in html
    assert "/api/v1/whatsapp/espejo/clientes/" in html
    assert "function chatPollIniciar(" in html
    assert "chatPollIniciar();" in html
    assert "15" in html and "}, 15000);" in html


def test_el_envio_del_crm_usa_numero_autorizado_y_key_id() -> None:
    fuente = CHAT.read_text(encoding="utf-8")
    assert "await espejo.telefono_de_cliente(cliente_id)" in fuente
    assert "await espejo.enviar_texto(telefono, cuerpo)" in fuente
    assert 'metadata["evolution_msg_id"]' in fuente
    # El notificador del M1 sigue disponible como respaldo, sin encender el bot.
    assert 'getattr(runtime.notifier, "enviar_texto_detalle", None)' in fuente


@pytest.mark.asyncio
async def test_el_espejo_envia_con_su_propio_cliente() -> None:
    class FakeEnvio:
        def __init__(self) -> None:
            self.llamadas: list[tuple[str, str]] = []

        async def enviar_texto(self, telefono: str, texto: str) -> dict[str, object]:
            self.llamadas.append((telefono, texto))
            return {"ok": True, "message_id": "ABC123", "estado": "PENDIENTE"}

    repo = MemoryRepositorioEspejo()
    envio = FakeEnvio()
    espejo = EspejoWhatsApp(repo, evolution=envio)
    detalle = await espejo.enviar_texto("593991234567", "Hola")
    assert detalle["message_id"] == "ABC123"
    assert envio.llamadas == [("593991234567", "Hola")]


@pytest.mark.asyncio
async def test_el_espejo_envia_multimedia_con_el_tipo_correcto() -> None:
    class FakeEnvio:
        def __init__(self) -> None:
            self.llamadas: list[dict[str, object]] = []

        async def enviar_media(self, telefono: str, **kw: object) -> dict[str, object]:
            self.llamadas.append({"telefono": telefono, **kw})
            return {"ok": True, "message_id": "MIDIA", "estado": "PENDIENTE"}

    envio = FakeEnvio()
    espejo = EspejoWhatsApp(MemoryRepositorioEspejo(), evolution=envio)
    detalle = await espejo.enviar_media(
        "593991234567", tipo="IMAGEN", datos=b"x", mime="image/webp", nombre="a.webp"
    )
    assert detalle["message_id"] == "MIDIA"
    assert envio.llamadas[0]["mediatype"] == "image"
    assert envio.llamadas[0]["mimetype"] == "image/webp"


@pytest.mark.asyncio
async def test_evolution_envia_media_en_base64() -> None:
    """El cliente real arma el cuerpo de sendMedia con el binario en base64."""
    from app.whatsapp_espejo.evolution import EvolutionEspejo

    capturado: dict[str, object] = {}

    class Respuesta:
        status_code = 201

        def json(self) -> dict[str, object]:
            return {"key": {"id": "MEDIA1"}, "status": "PENDING"}

    class Http:
        async def post(self, url: str, json: dict[str, object], **kw: object) -> Respuesta:
            capturado["url"] = url
            capturado["body"] = json
            return Respuesta()

    cliente = EvolutionEspejo(
        base_url="http://evolution:8080",
        instancia="horminor",
        api_key="k",
        http_client=Http(),
    )
    detalle = await cliente.enviar_media(
        "593991234567",
        mediatype="image",
        mimetype="image/webp",
        nombre="foto.webp",
        datos=b"abc",
        caption="hola",
    )
    assert detalle["message_id"] == "MEDIA1"
    assert str(capturado["url"]).endswith("/message/sendMedia/horminor")
    cuerpo = capturado["body"]
    assert cuerpo["mediatype"] == "image"  # type: ignore[index]
    assert cuerpo["media"] == "YWJj"  # type: ignore[index]
    assert cuerpo["caption"] == "hola"  # type: ignore[index]


@pytest.mark.asyncio
async def test_sin_evolution_configurado_el_espejo_no_finge_envio() -> None:
    from app.whatsapp_espejo.evolution import EvolutionNoConfigurado

    espejo = EspejoWhatsApp(MemoryRepositorioEspejo())
    with pytest.raises(EvolutionNoConfigurado):
        await espejo.enviar_texto("593991234567", "Hola")


@pytest.mark.asyncio
async def test_evolution_devuelve_el_estado_en_el_vocabulario_del_crm() -> None:
    """Evolution responde PENDING/SERVER_ACK; el CHECK del CRM no los admite."""
    from app.whatsapp_espejo.evolution import EvolutionEspejo

    class Respuesta:
        status_code = 201

        def json(self) -> dict[str, object]:
            return {"key": {"id": "3EB0ABC"}, "status": "PENDING"}

    class Http:
        async def post(self, *args: object, **kwargs: object) -> Respuesta:
            return Respuesta()

    cliente = EvolutionEspejo(
        base_url="http://evolution:8080",
        instancia="horminor",
        api_key="k",
        http_client=Http(),
    )
    detalle = await cliente.enviar_texto("593991234567", "Hola")
    assert detalle["estado"] == "PENDIENTE"
    assert detalle["message_id"] == "3EB0ABC"


def test_configuracion_evolution_ignora_filas_a_medias() -> None:
    settings = SimpleNamespace(
        evolution_url="http://evolution:8080",
        evolution_instance="horminor",
        evolution_api_key="clave-env",
    )
    completa = configuracion_evolution(
        settings,
        {"url": "http://otra:8080", "instancia": "x", "api_key": "otra"},
    )
    assert completa["url"] == "http://otra:8080"
    assert completa["instancia"] == "x"

    a_medias = configuracion_evolution(
        settings, {"url": None, "instancia": "orminorth-main", "api_key": None}
    )
    assert a_medias["url"] == "http://evolution:8080"
    assert a_medias["instancia"] == "horminor"
    assert a_medias["api_key"] == "clave-env"

# ---------------------------------------------------------------------------
# Aviso en vivo (SSE): el chat se entera sin esperar el sondeo de 15 s
# ---------------------------------------------------------------------------
def _dato_sse(trozo: str) -> dict[str, Any]:
    assert trozo.startswith("data: ")
    return json.loads(trozo[len("data: "):].strip())


@pytest.mark.asyncio
async def test_el_bus_entrega_el_aviso_y_limpia_al_suscriptor() -> None:
    bus = BusEventos()
    cola = bus.suscribir()
    assert bus.suscriptores == 1
    bus.publicar({"tipo": "mensaje", "cliente_id": "c1", "mensaje_id": "m1"})

    flujo = bus.transmitir(cola)
    assert _dato_sse(await flujo.__anext__()) == {"tipo": "listo"}
    evento = _dato_sse(await flujo.__anext__())
    assert evento["tipo"] == "mensaje"
    assert evento["cliente_id"] == "c1"

    await flujo.aclose()
    assert bus.suscriptores == 0


def test_el_bus_no_bloquea_si_un_panel_no_lee() -> None:
    bus = BusEventos(maxsize=1)
    bus.suscribir()  # nadie consume la cola
    for i in range(5):
        bus.publicar({"tipo": "mensaje", "mensaje_id": f"m{i}"})  # no debe lanzar


@pytest.mark.asyncio
async def test_importar_avisa_al_panel_en_vivo() -> None:
    bus = BusEventos()
    repo = MemoryRepositorioEspejo()
    repo.clientes["c1"] = True
    repo.numeros["593991234567"] = NumeroEspejo(
        telefono="593991234567", cliente_id="c1", activo=True
    )
    espejo = EspejoWhatsApp(repo, eventos=bus)
    cola = bus.suscribir()

    resultado = await espejo.ingerir(
        registro("m-vivo", "593991234567@s.whatsapp.net", "Hola en vivo")
    )

    assert resultado == "IMPORTADO"
    evento = cola.get_nowait()
    assert evento["tipo"] == "mensaje"
    assert evento["cliente_id"] == "c1"
    assert evento["mensaje_id"] == "m-vivo"
    assert evento["direccion"] == "ENTRANTE"
    assert evento["conversacion_id"] == repo.conversaciones[("c1", "WHATSAPP")]
    # El aviso viaja como JSON por SSE: una fecha cruda lo rompería.
    assert json.dumps(evento, ensure_ascii=False)


@pytest.mark.asyncio
async def test_un_mensaje_ignorado_no_avisa_al_panel() -> None:
    bus = BusEventos()
    repo = MemoryRepositorioEspejo()
    repo.clientes["c1"] = True
    repo.numeros["593991234567"] = NumeroEspejo(
        telefono="593991234567", cliente_id="c1", activo=True
    )
    espejo = EspejoWhatsApp(repo, eventos=bus)
    cola = bus.suscribir()

    await espejo.ingerir(registro("m-ajeno", "593000000000@s.whatsapp.net"))

    assert cola.empty()


@pytest.mark.asyncio
async def test_el_cambio_de_estado_tambien_avisa() -> None:
    bus = BusEventos()
    repo = MemoryRepositorioEspejo()
    repo.clientes["c1"] = True
    repo.numeros["593991234567"] = NumeroEspejo(
        telefono="593991234567", cliente_id="c1", activo=True
    )
    espejo = EspejoWhatsApp(repo, eventos=bus)
    telefono = "593991234567@s.whatsapp.net"
    await espejo.ingerir(
        registro("m-estado", telefono, "Saludos", from_me=True, status="SERVER_ACK")
    )
    cola = bus.suscribir()

    await espejo.ingerir(
        registro("m-estado", telefono, "Saludos", from_me=True, status="READ")
    )

    evento = cola.get_nowait()
    assert evento["tipo"] == "estado"
    assert evento["mensaje_id"] == "m-estado"
    assert evento["estado_entrega"] == "LEIDO"


@pytest.mark.asyncio
async def test_la_sincronizacion_avisa_una_sola_vez() -> None:
    bus = BusEventos()
    repo = MemoryRepositorioEspejo()
    repo.clientes["c1"] = True
    repo.numeros["593991234567"] = NumeroEspejo(
        telefono="593991234567", cliente_id="c1", activo=True
    )
    paginas = {
        "593991234567@s.whatsapp.net": [
            [registro("s1", "593991234567@s.whatsapp.net", "Uno")],
            [],
        ]
    }
    espejo = EspejoWhatsApp(repo, evolution=FakeEvolution(paginas), eventos=bus)
    cola = bus.suscribir()

    resultado = await espejo.sincronizar(cliente_id="c1")

    eventos = []
    while not cola.empty():
        eventos.append(cola.get_nowait())
    assert resultado.importados == 1
    assert [e["tipo"] for e in eventos] == ["mensaje", "sincronizado"]
    assert eventos[-1]["cliente_id"] == "c1"


def test_el_router_expone_el_aviso_en_vivo() -> None:
    fuente = (RAIZ_SERVICIO / "app" / "whatsapp_espejo" / "router.py").read_text(
        encoding="utf-8"
    )
    assert '@router.get("/eventos")' in fuente
    assert "StreamingResponse" in fuente
    assert "text/event-stream" in fuente
    assert 'exigir_modulo(request, "clientes_cartera", usuario=usuario)' in fuente


def test_main_crea_el_bus_y_lo_conecta_al_espejo() -> None:
    fuente = MAIN.read_text(encoding="utf-8")
    assert "BusEventos, EspejoWhatsApp, PostgresRepositorioEspejo" in fuente
    assert "app.state.eventos_espejo = BusEventos()" in fuente
    assert "eventos=app.state.eventos_espejo" in fuente


def test_el_panel_escucha_el_aviso_en_vivo() -> None:
    html = PANEL.read_text(encoding="utf-8")
    assert "chatEventosConectar();" in html
    assert "new EventSource(" in html
    assert "/api/v1/whatsapp/espejo/eventos" in html
    assert "function chatEventosRecibir(" in html
    # Sigue existiendo el sondeo como respaldo si el SSE se cae.
    assert "function chatPollIniciar(" in html


def test_nota_de_video_ptv_se_mapea_como_video() -> None:
    """La nota de video de WhatsApp llega como ptvMessage, no videoMessage."""
    registro = {
        "key": {
            "id": "ptv-1",
            "remoteJid": "593991234567@s.whatsapp.net",
            "fromMe": False,
            "messageTimestamp": 1_763_000_000,
        },
        "message": {"ptvMessage": {"mimetype": "video/mp4", "fileLength": 2048}},
        "messageType": "ptvMessage",
        "status": "DELIVERY_ACK",
        "pushName": "Contacto",
    }

    mensaje = desde_registro(registro)

    assert mensaje is not None, "la nota de video no puede descartarse"
    assert mensaje.cuerpo == "[nota de video]"
    assert mensaje.adjuntos[0]["tipo"] == "VIDEO"
    assert mensaje.adjuntos[0]["whatsapp_media"] == "ptvMessage"


@pytest.mark.asyncio
async def test_video_entrante_se_recomprime_antes_de_subir(tmp_path, monkeypatch) -> None:
    """El video que llega por WhatsApp pasa por ffmpeg igual que el del panel."""

    class EvolutionConVideo:
        async def obtener_media_base64(self, mensaje_id: str, jid: str, from_me: bool):
            return {
                "base64": base64.b64encode(b"video-original").decode(),
                "mimetype": "video/mp4",
                "nombre": "nota.mp4",
            }

    repo = MemoryRepositorioEspejo()
    repo.clientes["c1"] = True
    repo.numeros["593991234567"] = NumeroEspejo(
        telefono="593991234567", cliente_id="c1", activo=True
    )
    espejo = EspejoWhatsApp(
        repo,
        evolution=EvolutionConVideo(),
        settings=SimpleNamespace(media_dir=str(tmp_path), media_max_pixeles=50_000_000),
    )

    from app.services import media as media_svc

    recibido: dict[str, bytes] = {}

    async def falso_procesar_video(ruta, settings, *, max_lado=None):
        recibido["entrada"] = ruta.read_bytes()
        return media_svc.ArchivoProcesado(
            datos=b"video-comprimido",
            tipo="VIDEO",
            mime="video/mp4",
            extension="mp4",
        )

    monkeypatch.setattr(media_svc, "procesar_video", falso_procesar_video)

    registro = {
        "key": {
            "id": "vid-1",
            "remoteJid": "593991234567@s.whatsapp.net",
            "fromMe": False,
            "messageTimestamp": 1_763_000_000,
        },
        "message": {"videoMessage": {"mimetype": "video/mp4", "fileLength": 14}},
        "messageType": "videoMessage",
        "status": "DELIVERY_ACK",
    }

    assert await espejo.ingerir(registro) == "IMPORTADO"
    assert recibido["entrada"] == b"video-original"
    assert repo.media[0]["bytes"] == len(b"video-comprimido")
    assert repo.media[0]["mime_final"] == "video/mp4"
    assert repo.adjuntos_actualizados[0]["adjuntos"][0]["pendiente_descarga"] is False
