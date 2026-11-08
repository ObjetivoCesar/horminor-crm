"""Tests del modo SANDBOX y del simulador de WhatsApp en pantalla.

Cubre los tres adaptadores que permiten operar sin credenciales externas:

- ``SandboxNotifier`` encola en ``sandbox_outbox`` (no finge un envio real).
- ``SandboxBunnyStorageClient`` devuelve URLs deterministas bajo ``/sandbox/``.
- El endpoint ``/simulador-whatsapp`` corre el pipeline completo y
  ``/sandbox/outbox`` devuelve lo encolado.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.m1_whatsapp.identity import IdentityResolver, RegistroIdentidad  # noqa: E402
from app.m1_whatsapp.judges import DeterministicRuleMockJudge  # noqa: E402
from app.m1_whatsapp.models import IncomingMessage, MessageBatch  # noqa: E402
from app.m1_whatsapp.notifications import SentinelAlerter  # noqa: E402
from app.m1_whatsapp.pipeline import WhatsAppPipeline  # noqa: E402
from app.m1_whatsapp.repositorio import MemoriaRepositorio  # noqa: E402
from app.sandbox import (  # noqa: E402
    SandboxBunnyStorageClient,
    SandboxNotifier,
    construir_notifier_sandbox,
)
from app.settings import Settings  # noqa: E402
from app.superadmin.router import router as superadmin_router  # noqa: E402
from app.superadmin.store import MemoryConfigStore  # noqa: E402

LEAD = "+593990000999"
CLAVE = "clave-prueba-sandbox"


class _RuntimeSandbox:
    """Doble minimo del runtime: pipeline real + outbox en memoria."""

    def __init__(self, repo: MemoriaRepositorio, pipeline: WhatsAppPipeline) -> None:
        self.repo = repo
        self.pipeline = pipeline

    def estado(self) -> dict[str, str]:
        return {"modo": "SANDBOX", "judge_mode": "DETERMINISTIC_FALLBACK"}


def _pipeline_sandbox(
    repo: MemoriaRepositorio,
) -> tuple[WhatsAppPipeline, SandboxNotifier, SandboxBunnyStorageClient]:
    notifier = SandboxNotifier(repo)
    bunny = SandboxBunnyStorageClient()
    pipe = WhatsAppPipeline(
        repo=repo,
        identidad=IdentityResolver(registro=RegistroIdentidad()),
        juez=DeterministicRuleMockJudge(),
        bunny=bunny,
        notifier=notifier,
        alerter=SentinelAlerter(webhook_url=None, master_key=None, repo=repo),
    )
    return pipe, notifier, bunny


def _app(
    repo: MemoriaRepositorio,
    store: MemoryConfigStore | None = None,
) -> FastAPI:
    pipe, _, _ = _pipeline_sandbox(repo)
    app = FastAPI()
    app.state.settings = Settings(_env_file=None, agency_master_key=CLAVE)
    app.state.config_store = store or MemoryConfigStore()
    app.state.whatsapp = _RuntimeSandbox(repo, pipe)
    app.include_router(superadmin_router)
    return app


# ---------------------------------------------------------------------------
# Adaptadores
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sandbox_notifier_encola_sin_evolution() -> None:
    repo = MemoriaRepositorio()
    notifier = SandboxNotifier(repo)

    assert await notifier.enviar_texto("+593990000001", "Hola desde sandbox") is True

    outbox = await repo.listar_outbox()
    assert len(outbox) == 1
    item = outbox[0]
    assert item["canal"] == "WHATSAPP"
    assert item["destino"] == "+593990000001"
    assert item["tipo"] == "TEXTO"
    assert item["contenido"] == "Hola desde sandbox"
    assert item["estado"] == "ENCOLADO"
    assert item["metadatos"]["modo"] == "SANDBOX"
    assert item["metadatos"]["proveedor"] == "evolution"


@pytest.mark.asyncio
async def test_sandbox_bunny_url_deterministica_y_sin_red() -> None:
    bunny = SandboxBunnyStorageClient(cdn_host="https://orminorth.b-cdn.net")

    primera = await bunny.subir(
        nombre_archivo="evidencias/MIXER-01/viaje-1.jpg",
        contenido=b"foto",
        mimetype="image/jpeg",
    )
    segunda = await bunny.subir(
        nombre_archivo="evidencias/MIXER-01/viaje-1.jpg",
        contenido=b"foto",
        mimetype="image/jpeg",
    )

    assert primera == segunda
    assert primera == (
        "https://orminorth.b-cdn.net/sandbox/evidencias/MIXER-01/viaje-1.jpg"
    )
    assert len(bunny.subidas) == 2
    assert bunny.subidas[0]["bytes"] == 4


@pytest.mark.asyncio
async def test_sandbox_bunny_sanea_nombres_y_acepta_host_sin_esquema() -> None:
    bunny = SandboxBunnyStorageClient(cdn_host="cdn.ejemplo.test/")

    url = await bunny.subir(nombre_archivo="evidencia con espacios y ñ.jpg")

    assert url.startswith("https://cdn.ejemplo.test/sandbox/")
    assert " " not in url
    assert "ñ" not in url


def test_construir_notifier_sandbox_devuelve_el_par_completo() -> None:
    notifier, bunny = construir_notifier_sandbox(
        MemoriaRepositorio(), cdn_host="https://cdn.origen.test"
    )
    assert isinstance(notifier, SandboxNotifier)
    assert isinstance(bunny, SandboxBunnyStorageClient)
    assert bunny.nombre == "sandbox"


# ---------------------------------------------------------------------------
# Endpoints del simulador
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_simulador_remitentes_incluye_lead_nuevo() -> None:
    transporte = httpx.ASGITransport(app=_app(MemoriaRepositorio()))
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as cliente:
        respuesta = await cliente.get("/api/v1/superadmin/simulador/remitentes")

    assert respuesta.status_code == 200
    remitentes = respuesta.json()["remitentes"]
    lead = next(r for r in remitentes if r["rol"] == "LEAD_DESCONOCIDO")
    assert lead["telefono"] == LEAD


@pytest.mark.asyncio
async def test_simulador_procesa_lead_y_deja_respuesta_en_outbox() -> None:
    repo = MemoriaRepositorio(
        parametros={
            "empresa.bot_publico": {
                "company_name": "ORMINORTH HORMIGONES Y PREFABRICADOS S.A.S.",
                "main_plant_address": "El Coca, Orellana",
                "coverage_zones": ["Orellana", "Sucumbios"],
                "mobile_plant_pitch": "Planta movil desde 1,000 m3",
                "extra_services": ["Bomba pluma"],
                "business_hours": None,
                "ruc": None,
                "bank_accounts": [],
            }
        },
        recetas=[
            {
                "resistencia": "FC-210",
                "precio_m3": 118.0,
                "uso_comercial": "Losas y columnas",
                "confirmado": True,
            }
        ],
    )
    transporte = httpx.ASGITransport(app=_app(repo))

    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as cliente:
        simulacion = await cliente.post(
            "/api/v1/superadmin/simulador-whatsapp",
            json={
                "telefono": LEAD,
                "texto": "Necesito cotizacion de hormigon para 20 m3",
            },
        )
        outbox = await cliente.get("/api/v1/superadmin/sandbox/outbox")

    assert simulacion.status_code == 200
    cuerpo = simulacion.json()
    assert cuerpo["compuerta"] == "GATE_4_LEAD"
    assert cuerpo["modo"] == "SANDBOX"
    assert cuerpo["judge_mode"] == "DETERMINISTIC_FALLBACK"
    assert "orminorth" in (cuerpo["respuesta"] or "").lower()
    assert len(repo.leads) == 1

    assert outbox.status_code == 200
    mensajes = outbox.json()["outbox"]
    assert len(mensajes) == 1
    assert mensajes[0]["destino"] == LEAD
    assert mensajes[0]["estado"] == "ENCOLADO"
    assert "FC-210" in mensajes[0]["contenido"]


@pytest.mark.asyncio
async def test_simulador_sin_runtime_responde_503() -> None:
    app = FastAPI()
    app.state.settings = Settings(_env_file=None, agency_master_key=CLAVE)
    app.state.config_store = MemoryConfigStore()
    app.state.whatsapp = None
    app.include_router(superadmin_router)
    transporte = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as cliente:
        respuesta = await cliente.post(
            "/api/v1/superadmin/simulador-whatsapp",
            json={"telefono": LEAD, "texto": "hola"},
        )

    assert respuesta.status_code == 503
