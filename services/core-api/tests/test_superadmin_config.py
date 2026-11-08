"""Tests del Centro de Configuracion Superadmin y del Gate #4 dinamico.

Todo sin infraestructura: el store en memoria reproduce el contrato de
PostgreSQL y el bot lee la configuracion del repositorio en memoria. El punto
central es que **cambiar una seccion se refleja en la siguiente lectura o en
la siguiente respuesta**, sin reiniciar el proceso.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
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
from app.m1_whatsapp.notifications import (  # noqa: E402
    RecordingNotifier,
    SentinelAlerter,
)
from app.m1_whatsapp.pipeline import WhatsAppPipeline  # noqa: E402
from app.m1_whatsapp.repositorio import MemoriaRepositorio  # noqa: E402
from app.m1_whatsapp.bunny import MemoryBunnyStorageClient  # noqa: E402
from app.settings import Settings  # noqa: E402
from app.superadmin.router import router as superadmin_router  # noqa: E402
from app.superadmin.secciones import (  # noqa: E402
    SECCIONES,
    componer_respuesta_lead,
    normalizar_seccion,
)
from app.superadmin.store import MemoryConfigStore  # noqa: E402

CLAVE = "clave-prueba-superadmin"
LEAD = "0994000001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class _RuntimeRecarga:
    """Doble del Modulo 1: cuenta cuantas veces se recargo la config."""

    def __init__(self) -> None:
        self.recargas = 0
        self.ventana_segundos = 14.0

    async def recargar_config(self) -> dict[str, object]:
        self.recargas += 1
        return {"ventana_segundos": self.ventana_segundos}


def _app(store: MemoryConfigStore, runtime: object | None = None) -> FastAPI:
    app = FastAPI()
    app.state.settings = Settings(_env_file=None, agency_master_key=CLAVE)
    app.state.config_store = store
    app.state.whatsapp = runtime
    app.include_router(superadmin_router)
    return app


def _batch(telefono: str, texto: str, mensaje_id: str = "m-1") -> MessageBatch:
    return MessageBatch(
        telefono=telefono,
        mensajes=(
            IncomingMessage(
                mensaje_id=mensaje_id,
                telefono=telefono,
                texto=texto,
                recibido_at=datetime.now(timezone.utc),
            ),
        ),
    )


def _pipeline(
    repo: MemoriaRepositorio,
) -> tuple[WhatsAppPipeline, RecordingNotifier]:
    notifier = RecordingNotifier()
    pipe = WhatsAppPipeline(
        repo=repo,
        identidad=IdentityResolver(registro=RegistroIdentidad()),
        juez=DeterministicRuleMockJudge(),
        bunny=MemoryBunnyStorageClient(),
        notifier=notifier,
        alerter=SentinelAlerter(webhook_url=None, master_key=None, repo=repo),
    )
    return pipe, notifier


# ---------------------------------------------------------------------------
# Las 7 secciones
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_config_expone_las_siete_secciones() -> None:
    store = MemoryConfigStore()

    config = await store.leer_todo()

    assert set(config) == set(SECCIONES)
    assert len(SECCIONES) == 7
    assert config["empresa_bot_publico"]["company_name"] == "Orminorth Hormigones"
    assert config["flota_y_operacion"]["politica_ultimo_viaje"] == "PARCIAL"
    assert config["flota_y_operacion"]["reloj_termico"] == {
        "max_fraguado_minutes": 150,
        "alerta_temprana_min": 90,
        "alerta_critica_min": 120,
    }


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        ("formulas_y_precios", "formulas_y_precios"),
        ("FORMULAS", "formulas_y_precios"),
        ("whatsapp", "whatsapp_evolution_y_cdn"),
        ("empresa", "empresa_bot_publico"),
        ("flota", "flota_y_operacion"),
        ("directorio", "directorio_roles_whatsapp"),
        ("bodega", "bodega_y_umbrales"),
        ("finanzas", "finanzas_y_ases_gerenciales"),
    ],
)
def test_nombres_y_alias_de_seccion(crudo: str, esperado: str) -> None:
    assert normalizar_seccion(crudo) == esperado


def test_seccion_desconocida_falla_explicito() -> None:
    with pytest.raises(ValueError, match="no existe"):
        normalizar_seccion("ventas_magicas")


# ---------------------------------------------------------------------------
# Cambio en vivo (sin reiniciar)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cambiar_texto_del_bot_cambia_la_respuesta_en_vivo() -> None:
    store = MemoryConfigStore()
    recetas = await store.listar_recetas()

    antes = componer_respuesta_lead(
        await store.leer_seccion("empresa_bot_publico"), recetas
    )
    assert "Orminorth Hormigones" in antes

    await store.guardar_seccion(
        "empresa_bot_publico",
        {
            "company_name": "Hormigones del Oriente",
            "coverage_zones": ["Orellana", "Sucumbios"],
        },
    )
    despues = componer_respuesta_lead(
        await store.leer_seccion("empresa_bot_publico"),
        await store.listar_recetas(),
    )

    assert "Hormigones del Oriente" in despues
    assert "Orminorth Hormigones" not in despues
    assert "Sucumbios" in despues


@pytest.mark.asyncio
async def test_cambiar_precio_de_una_formula_se_ve_de_inmediato() -> None:
    store = MemoryConfigStore()

    await store.guardar_seccion(
        "formulas_y_precios",
        {"recetas": [{"resistencia": "FC-210", "precio_m3": 124.5}]},
    )
    recetas = await store.listar_recetas()
    fc210 = next(r for r in recetas if r["resistencia"] == "FC-210")

    assert fc210["precio_m3"] == 124.5
    respuesta = componer_respuesta_lead(
        await store.leer_seccion("empresa_bot_publico"), recetas
    )
    assert "$124.50" in respuesta


@pytest.mark.asyncio
async def test_politica_y_reloj_termico_respetan_el_formato_editado() -> None:
    store = MemoryConfigStore()

    flota = await store.guardar_seccion(
        "flota_y_operacion",
        {
            "politica_ultimo_viaje": "UNIFORME",
            "reloj_termico": {
                "max_fraguado_minutes": 180,
                "alerta_temprana_min": 120,
                "alerta_critica_min": 150,
            },
        },
    )

    assert flota["politica_ultimo_viaje"] == "UNIFORME"
    assert flota["reloj_termico"] == {
        "max_fraguado_minutes": 180,
        "alerta_temprana_min": 120,
        "alerta_critica_min": 150,
    }
    # Internamente se guarda "minutos antes", como lo leen el pipeline y el
    # Centinela: 180 - 120 = 60 y 180 - 150 = 30.
    assert store.settings["operacion.alerta_temprana_minutos_antes"] == 60.0
    assert store.settings["operacion.por_vencer_critico_minutos_antes"] == 30.0


# ---------------------------------------------------------------------------
# CRUD de recetas y flota
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_crud_recetas_completo() -> None:
    store = MemoryConfigStore()

    creada = await store.upsert_receta(
        {
            "resistencia": "FC-500",
            "cemento_sacos_m3": 14.0,
            "arena_m3_m3": 0.4,
            "ripio_m3_m3": 0.58,
            "agua_litros_m3": 165,
            "retardante_litros_m3": 2.5,
            "saco_kg": 50,
            "precio_m3": 190,
            "uso_comercial": "Pilotes especiales",
        }
    )
    assert creada["resistencia"] == "FC-500"
    assert len(await store.listar_recetas()) == 3

    await store.upsert_receta({"resistencia": "FC-500", "precio_m3": 195})
    actualizada = next(
        r for r in await store.listar_recetas() if r["resistencia"] == "FC-500"
    )
    assert actualizada["precio_m3"] == 195

    assert await store.eliminar_receta("FC-500") is True
    assert await store.eliminar_receta("FC-500") is False
    assert len(await store.listar_recetas()) == 2


@pytest.mark.asyncio
async def test_crud_flota_completo() -> None:
    store = MemoryConfigStore()

    creado = await store.upsert_mixer(
        {"codigo": "MIXER-09", "capacidad_m3": 6, "placa": "PBA-1234"}
    )
    assert creado["codigo"] == "MIXER-09"
    assert creado["placa"] == "PBA-1234"
    assert len(await store.listar_flota()) == 4

    await store.upsert_mixer({"codigo": "MIXER-09", "activo": False})
    desactivado = next(
        m for m in await store.listar_flota() if m["codigo"] == "MIXER-09"
    )
    assert desactivado["activo"] is False

    assert await store.eliminar_mixer("MIXER-09") is True
    assert await store.eliminar_mixer("MIXER-09") is False
    assert len(await store.listar_flota()) == 3


@pytest.mark.asyncio
async def test_mixer_sin_capacidad_es_rechazado() -> None:
    with pytest.raises(ValueError, match="capacidad_m3"):
        await MemoryConfigStore().upsert_mixer({"codigo": "MIXER-X"})


# ---------------------------------------------------------------------------
# Endpoints HTTP (abiertos, sin login en esta etapa)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_http_lee_y_escribe_sin_autenticacion() -> None:
    store = MemoryConfigStore()
    transporte = httpx.ASGITransport(app=_app(store))

    async with httpx.AsyncClient(
        transport=transporte, base_url="http://test"
    ) as cliente:
        completa = await cliente.get("/api/v1/superadmin/config")
        empresa = await cliente.get("/api/v1/superadmin/config/empresa")
        guardado = await cliente.put(
            "/api/v1/superadmin/config/empresa_bot_publico",
            json={"business_hours": "Lunes a sabado, 07:00 a 18:00"},
        )

    assert completa.status_code == 200
    assert set(completa.json()) == set(SECCIONES)
    assert empresa.json()["company_name"] == "Orminorth Hormigones"
    assert guardado.status_code == 200
    assert guardado.json()["business_hours"] == "Lunes a sabado, 07:00 a 18:00"
    # El cambio ya esta en memoria: la siguiente lectura lo devuelve.
    assert (
        await store.leer_seccion("empresa_bot_publico")
    )["business_hours"] == "Lunes a sabado, 07:00 a 18:00"


@pytest.mark.asyncio
async def test_http_crud_recetas_y_flota() -> None:
    store = MemoryConfigStore()
    transporte = httpx.ASGITransport(app=_app(store))

    async with httpx.AsyncClient(
        transport=transporte, base_url="http://test"
    ) as cliente:
        receta = await cliente.post(
            "/api/v1/superadmin/recetas",
            json={"resistencia": "FC-240", "precio_m3": 126, "confirmado": True},
        )
        listado = await cliente.get("/api/v1/superadmin/recetas")
        borrada = await cliente.delete("/api/v1/superadmin/recetas/FC-240")
        mixer = await cliente.post(
            "/api/v1/superadmin/flota",
            json={"codigo": "MIXER-07", "capacidad_m3": 7},
        )
        flota = await cliente.get("/api/v1/superadmin/flota")

    assert receta.status_code == 201
    assert receta.json()["resistencia"] == "FC-240"
    assert any(r["resistencia"] == "FC-240" for r in listado.json()["recetas"])
    assert borrada.json() == {"eliminada": True, "resistencia": "FC-240"}
    assert mixer.status_code == 201
    assert any(m["codigo"] == "MIXER-07" for m in flota.json()["mixers"])


@pytest.mark.asyncio
async def test_http_put_avisa_al_modulo_1_para_recargar() -> None:
    store = MemoryConfigStore()
    runtime = _RuntimeRecarga()
    transporte = httpx.ASGITransport(app=_app(store, runtime))

    async with httpx.AsyncClient(
        transport=transporte, base_url="http://test"
    ) as cliente:
        respuesta = await cliente.put(
            "/api/v1/superadmin/config/whatsapp",
            json={"debounce_seconds": 5},
        )

    assert respuesta.status_code == 200
    assert respuesta.json()["debounce_seconds"] == 5.0
    assert runtime.recargas == 1


@pytest.mark.asyncio
async def test_http_seccion_desconocida_responde_404() -> None:
    transporte = httpx.ASGITransport(app=_app(MemoryConfigStore()))

    async with httpx.AsyncClient(
        transport=transporte, base_url="http://test"
    ) as cliente:
        respuesta = await cliente.get("/api/v1/superadmin/config/no_existe")

    assert respuesta.status_code == 404


# ---------------------------------------------------------------------------
# Gate #4 lee la configuracion viva del repositorio
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_gate_4_responde_y_registra_el_lead() -> None:
    repo = MemoriaRepositorio(
        parametros={
            "empresa.bot_publico": {
                "company_name": "Orminorth Hormigones",
                "main_plant_address": "El Coca, Orellana",
                "coverage_zones": ["Orellana", "Sucumbios", "Via Auca"],
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
    pipe, notifier = _pipeline(repo)

    resultado = await pipe.procesar(
        _batch(LEAD, "Necesito cotizacion de hormigon para 20 m3")
    )

    assert resultado.compuerta == "GATE_4_LEAD"
    assert "PROSPECTO_CREADO" in resultado.acciones
    assert "RESPUESTA_BOT_ENVIADA" in resultado.acciones
    assert resultado.respuesta is not None
    assert "Orminorth Hormigones" in resultado.respuesta
    assert "FC-210: $118.00/m3" in resultado.respuesta
    assert "El Coca, Orellana" in resultado.respuesta
    assert len(repo.leads) == 1
    assert notifier.enviados[0]["texto"] == resultado.respuesta


@pytest.mark.asyncio
async def test_gate_4_cambia_la_respuesta_si_cambia_la_config() -> None:
    repo = MemoriaRepositorio()
    repo.parametros["empresa.bot_publico"] = {
        "company_name": "Orminorth Hormigones",
        "coverage_zones": ["Orellana"],
    }
    repo.recetas = [
        {"resistencia": "FC-180", "precio_m3": 108.0, "confirmado": True}
    ]
    pipe, _ = _pipeline(repo)

    primera = await pipe.procesar(
        _batch("0994000002", "Necesito cotizacion de hormigon")
    )
    assert "FC-180: $108.00/m3" in (primera.respuesta or "")

    # El Superadmin edita la seccion: sin reiniciar nada, el siguiente lead
    # recibe la configuracion nueva.
    repo.parametros["empresa.bot_publico"] = {
        "company_name": "Hormigones del Oriente",
        "coverage_zones": ["Orellana", "Loreto"],
    }
    repo.recetas = [
        {"resistencia": "FC-350", "precio_m3": 158.0, "confirmado": True}
    ]

    segunda = await pipe.procesar(
        _batch("0994000003", "Necesito cotizacion de hormigon")
    )

    assert "Hormigones del Oriente" in (segunda.respuesta or "")
    assert "FC-350: $158.00/m3" in (segunda.respuesta or "")
    assert "FC-180" not in (segunda.respuesta or "")


@pytest.mark.asyncio
async def test_gate_4_omite_datos_que_el_cliente_no_entrego() -> None:
    repo = MemoriaRepositorio(
        parametros={
            "empresa.bot_publico": {
                "company_name": "Orminorth Hormigones",
                "ruc": None,
                "business_hours": None,
                "bank_accounts": [],
            }
        }
    )
    pipe, _ = _pipeline(repo)

    resultado = await pipe.procesar(
        _batch("0994000004", "Necesito cotizacion de hormigon")
    )
    respuesta = resultado.respuesta or ""

    assert "RUC:" not in respuesta
    assert "Horario" not in respuesta
    assert "Transferencias" not in respuesta
