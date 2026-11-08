"""Tests del Modulo 1 - Central de Comunicaciones (WhatsApp).

Todo se prueba sin infraestructura: buffer en memoria, Juez deterministico,
Bunny simulado y repositorio en memoria. Los dobles implementan los mismos
contratos que las piezas reales, asi que el pipeline se ejercita completo.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.m1_whatsapp.bunny import (  # noqa: E402
    BunnyHttpStorageClient,
    BunnyNoConfigurado,
    MemoryBunnyStorageClient,
    NullBunnyStorageClient,
    construir_bunny,
    decodificar_base64,
    nombre_evidencia,
)
from app.m1_whatsapp.debounce import (  # noqa: E402
    DebounceAccumulator,
    MemoryBufferStore,
)
from app.m1_whatsapp.identity import (  # noqa: E402
    ClienteRegistrado,
    IdentityResolver,
    RegistroIdentidad,
)
from app.m1_whatsapp.judges import (  # noqa: E402
    ACCION_ESPERAR_CONFIRMACION,
    ACCION_EVIDENCIA_FALTANTE,
    ACCION_EVIDENCIA_VALIDA,
    ACCION_LEAD_CALIFICADO,
    ACCION_LEAD_NO_CALIFICADO,
    ACCION_RECEPCION_CONFORME,
    ACCION_RECLAMO,
    ACCION_DESPACHO_CONFIRMADO,
    ACCION_DESPACHO_NO_CONFIRMADO,
    COMPUERTA_CLIENTE,
    COMPUERTA_DESPACHO,
    COMPUERTA_EVIDENCIA,
    COMPUERTA_LEAD,
    DeterministicRuleMockJudge,
    ErrorJuez,
    GeminiFlashBooleanJudge,
    _parsear_veredicto,
    construir_juez,
)
from app.m1_whatsapp.models import (  # noqa: E402
    IncomingMessage,
    MediaAttachment,
    MessageBatch,
    Rol,
    extraer_referencia,
    normalizar_codigo_mixer,
    normalizar_telefono,
)
from app.m1_whatsapp.notifications import (  # noqa: E402
    RecordingNotifier,
    SentinelAlerter,
)
from app.m1_whatsapp.pipeline import WhatsAppPipeline  # noqa: E402
from app.m1_whatsapp.repositorio import (  # noqa: E402
    MemoriaRepositorio,
    ViajeObjetivo,
)
from app.m1_whatsapp.router import router as whatsapp_router  # noqa: E402
from app.m1_whatsapp.webhook import normalizar_evento  # noqa: E402
from app.m1_whatsapp.worker import DebounceWorker  # noqa: E402
from app.services.ordenes import _payload_base  # noqa: E402
from app.settings import Settings  # noqa: E402

CLAVE_M1 = "clave-m1-de-prueba"
BODEGA = "0991111111"
CHOFER = "0992222222"
CLIENTE = "0999999999"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _msg(
    telefono: str,
    texto: str,
    *,
    mensaje_id: str = "m-1",
    media: tuple[MediaAttachment, ...] = (),
    recibido_at: datetime | None = None,
) -> IncomingMessage:
    return IncomingMessage(
        mensaje_id=mensaje_id,
        telefono=telefono,
        texto=texto,
        recibido_at=recibido_at or datetime.now(timezone.utc),
        media=media,
    )


def _batch(
    telefono: str,
    texto: str,
    *,
    mensaje_id: str = "m-1",
    media: tuple[MediaAttachment, ...] = (),
) -> MessageBatch:
    return MessageBatch(
        telefono=normalizar_telefono(telefono),
        mensajes=(_msg(telefono, texto, mensaje_id=mensaje_id, media=media),),
    )


def _registro() -> RegistroIdentidad:
    return RegistroIdentidad(
        staff={
            normalizar_telefono(BODEGA): Rol.BODEGA_PLANTA,
            normalizar_telefono(CHOFER): Rol.CHOFER_MIXER,
        },
        clientes={
            normalizar_telefono(CLIENTE): ClienteRegistrado(
                cliente_id="cli-1",
                nombre="Constructora Prueba",
                estado="ACTIVO",
                telefono=CLIENTE,
            )
        },
    )


def _viaje(
    *,
    estado: str = "PROGRAMADO",
    orden: int = 101,
    viaje: int = 1,
) -> ViajeObjetivo:
    dispatch_id = str(uuid4())
    payload = _payload_base(
        dispatch_id=UUID(dispatch_id),
        viaje_numero=viaje,
        total_viajes=2,
        volumen=8,
        resistencia="FC-210",
        mixer_codigo="MIXER-01",
        chofer_nombre=None,
        receta_provisional=True,
    )
    payload["estado_actual"] = estado
    return ViajeObjetivo(
        dispatch_id=dispatch_id,
        order_id=str(uuid4()),
        orden_numero=orden,
        viaje_numero=viaje,
        total_viajes_orden=2,
        mixer_codigo="MIXER-01",
        cliente_id="cli-1",
        cliente_nombre="Constructora Prueba",
        cliente_telefono=CLIENTE,
        payload=payload,
    )


def _pipeline(
    repo: MemoriaRepositorio,
) -> tuple[WhatsAppPipeline, MemoryBunnyStorageClient, RecordingNotifier]:
    bunny = MemoryBunnyStorageClient()
    notifier = RecordingNotifier()
    pipe = WhatsAppPipeline(
        repo=repo,
        identidad=IdentityResolver(registro=_registro()),
        juez=DeterministicRuleMockJudge(),
        bunny=bunny,
        notifier=notifier,
        alerter=SentinelAlerter(
            webhook_url=None, master_key=None, repo=repo
        ),
    )
    return pipe, bunny, notifier


# ---------------------------------------------------------------------------
# Normalizacion (pura)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        ("+593 99 123 4567", "991234567"),
        ("0991234567", "991234567"),
        ("593991234567", "991234567"),
        ("00593991234567", "991234567"),
        ("", ""),
        (None, ""),
        ("12345", "12345"),
    ],
)
def test_normalizar_telefono(crudo: object, esperado: str) -> None:
    assert normalizar_telefono(crudo) == esperado


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        ("#M1", "MIXER-01"),
        ("mixer 12", "MIXER-12"),
        ("MIXER-01", "MIXER-01"),
        ("", ""),
    ],
)
def test_normalizar_codigo_mixer(crudo: str, esperado: str) -> None:
    assert normalizar_codigo_mixer(crudo) == esperado


def test_extraer_referencia_orden_viaje_mixer() -> None:
    referencia = extraer_referencia("Orden #104 viaje V2, mixer #M3")

    assert referencia.orden_numero == 104
    assert referencia.viaje_numero == 2
    assert referencia.mixer_codigo == "MIXER-03"


def test_extraer_referencia_vacia() -> None:
    assert extraer_referencia("ya salio el mixer").vacia is True


# ---------------------------------------------------------------------------
# Debounce de 14 segundos (inyectado a 0.1 s)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_debounce_agrupa_cuatro_mensajes_en_un_lote() -> None:
    acumulador = DebounceAccumulator(MemoryBufferStore(), ventana_segundos=0.1)
    t0 = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    fragmentos = ["ya", "llego", "el mixer", "todo bien"]

    for indice, fragmento in enumerate(fragmentos):
        await acumulador.agregar(
            _msg(CLIENTE, fragmento, mensaje_id=f"m{indice}"),
            ahora=t0 + timedelta(seconds=0.02 * indice),
        )

    # A los 0.05 s el remitente sigue escribiendo: no se procesa nada.
    assert await acumulador.listos(t0 + timedelta(seconds=0.05)) == []

    listos = await acumulador.listos(t0 + timedelta(seconds=0.3))

    assert len(listos) == 1
    assert len(listos[0].mensajes) == 4
    assert listos[0].texto == "ya llego el mixer todo bien"
    assert listos[0].telefono == normalizar_telefono(CLIENTE)
    # El lote se consume: no se procesa dos veces.
    assert await acumulador.listos(t0 + timedelta(seconds=1)) == []


@pytest.mark.asyncio
async def test_debounce_separa_remitentes_distintos() -> None:
    acumulador = DebounceAccumulator(MemoryBufferStore(), ventana_segundos=0.1)
    t0 = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)

    await acumulador.agregar(_msg(BODEGA, "salio"), ahora=t0)
    await acumulador.agregar(_msg(CHOFER, "llegue"), ahora=t0)

    listos = await acumulador.listos(t0 + timedelta(seconds=5))

    assert len(listos) == 2
    assert {lote.telefono for lote in listos} == {
        normalizar_telefono(BODEGA),
        normalizar_telefono(CHOFER),
    }


@pytest.mark.asyncio
async def test_debounce_tope_maximo_evita_espera_infinita() -> None:
    """Si el remitente no deja de escribir, el lote sale al cumplir el tope."""
    acumulador = DebounceAccumulator(
        MemoryBufferStore(), ventana_segundos=14, maximo_segundos=0.1
    )
    t0 = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)

    await acumulador.agregar(_msg(CLIENTE, "uno"), ahora=t0)
    await acumulador.agregar(
        _msg(CLIENTE, "dos"), ahora=t0 + timedelta(seconds=0.05)
    )

    listos = await acumulador.listos(t0 + timedelta(seconds=0.15))

    assert len(listos) == 1
    assert listos[0].texto == "uno dos"


# ---------------------------------------------------------------------------
# Identidad: telefono registrado manda; codigo es fallback
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("telefono", ["0991111111", "+593 99 111 1111"])
@pytest.mark.asyncio
async def test_identidad_por_telefono_registrado_staff(telefono: str) -> None:
    identidad = await IdentityResolver(registro=_registro()).resolver(
        telefono, "hola"
    )

    assert identidad.rol is Rol.BODEGA_PLANTA
    assert identidad.origen == "registro_staff"


@pytest.mark.asyncio
async def test_identidad_cliente_activo() -> None:
    identidad = await IdentityResolver(registro=_registro()).resolver(
        CLIENTE, "recibi"
    )

    assert identidad.rol is Rol.CLIENTE
    assert identidad.origen == "registro_cliente"
    assert identidad.cliente_id == "cli-1"
    assert identidad.nombre == "Constructora Prueba"


@pytest.mark.asyncio
async def test_identidad_prospecto_cae_en_gate_de_lead_sin_duplicar() -> None:
    registro = RegistroIdentidad(
        clientes={
            normalizar_telefono("0988888888"): ClienteRegistrado(
                cliente_id="cli-prospecto",
                nombre="Obra Nueva",
                estado="PROSPECTO",
            )
        }
    )

    identidad = await IdentityResolver(registro=registro).resolver(
        "0988888888", "necesito hormigon"
    )

    assert identidad.rol is Rol.LEAD_DESCONOCIDO
    assert identidad.cliente_id == "cli-prospecto"


@pytest.mark.asyncio
async def test_identidad_fallback_por_codigo_bodega() -> None:
    identidad = await IdentityResolver(registro=_registro()).resolver(
        "0977777777", "salida confirmada #BODEGA"
    )

    assert identidad.rol is Rol.BODEGA_PLANTA
    assert identidad.origen == "codigo_operador"


@pytest.mark.asyncio
async def test_identidad_fallback_mixer() -> None:
    identidad = await IdentityResolver(registro=_registro()).resolver(
        "0977777777", "#M1 llegue a la obra"
    )

    assert identidad.rol is Rol.CHOFER_MIXER
    assert identidad.mixer_codigo == "MIXER-01"
    assert identidad.origen == "codigo_operador"


@pytest.mark.asyncio
async def test_codigo_de_operador_gana_sobre_referencia_a_mixer() -> None:
    """El bodeguero reporta el mixer y se identifica con #BODEGA a la vez."""
    identidad = await IdentityResolver(registro=_registro()).resolver(
        "0977777777", "Ya salio el mixer #M1 hacia la obra #BODEGA"
    )

    assert identidad.rol is Rol.BODEGA_PLANTA
    assert identidad.origen == "codigo_operador"


@pytest.mark.asyncio
async def test_identidad_desconocida_es_lead() -> None:
    identidad = await IdentityResolver(registro=_registro()).resolver(
        "0977777777", "buenas tardes"
    )

    assert identidad.rol is Rol.LEAD_DESCONOCIDO
    assert identidad.origen == "desconocido"


@pytest.mark.asyncio
async def test_telefono_registrado_gana_sobre_codigo() -> None:
    identidad = await IdentityResolver(registro=_registro()).resolver(
        CLIENTE, "#ADMIN confirmo"
    )

    assert identidad.rol is Rol.CLIENTE


# ---------------------------------------------------------------------------
# Juez Binario deterministico
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("texto", "cumple", "codigo"),
    [
        ("Ya salio el mixer #M1 hacia la obra", True, ACCION_DESPACHO_CONFIRMADO),
        ("Todavia no sale, falta cargar", False, ACCION_DESPACHO_NO_CONFIRMADO),
        ("Salida confirmada", True, ACCION_DESPACHO_CONFIRMADO),
    ],
)
async def test_juez_despacho(texto: str, cumple: bool, codigo: str) -> None:
    veredicto = await DeterministicRuleMockJudge().evaluar(
        compuerta=COMPUERTA_DESPACHO, texto=texto
    )

    assert veredicto.cumple is cumple
    assert veredicto.codigo_accion == codigo
    assert 0.0 <= veredicto.confianza <= 1.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("texto", "cumple", "codigo"),
    [
        ("Recibi el hormigon, todo bien", True, ACCION_RECEPCION_CONFORME),
        ("si", True, ACCION_RECEPCION_CONFORME),
        (
            "Hay mucha demora, el hormigon no ha llegado",
            False,
            ACCION_RECLAMO,
        ),
        ("El material llego en mal estado", False, ACCION_RECLAMO),
        ("lo estoy revisando", False, ACCION_ESPERAR_CONFIRMACION),
    ],
)
async def test_juez_cliente(texto: str, cumple: bool, codigo: str) -> None:
    veredicto = await DeterministicRuleMockJudge().evaluar(
        compuerta=COMPUERTA_CLIENTE, texto=texto
    )

    assert veredicto.cumple is cumple
    assert veredicto.codigo_accion == codigo


@pytest.mark.asyncio
async def test_juez_evidencia_exige_adjunto() -> None:
    juez = DeterministicRuleMockJudge()

    sin_media = await juez.evaluar(
        compuerta=COMPUERTA_EVIDENCIA, texto="llegue", contexto={"media": 0}
    )
    con_media = await juez.evaluar(
        compuerta=COMPUERTA_EVIDENCIA, texto="llegue", contexto={"media": 1}
    )

    assert sin_media.cumple is False
    assert sin_media.codigo_accion == ACCION_EVIDENCIA_FALTANTE
    assert con_media.cumple is True
    assert con_media.codigo_accion == ACCION_EVIDENCIA_VALIDA


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("texto", "cumple", "codigo"),
    [
        ("Necesito cotizacion de hormigon para 20 m3", True, ACCION_LEAD_CALIFICADO),
        ("Hola, buenas tardes", False, ACCION_LEAD_NO_CALIFICADO),
    ],
)
async def test_juez_lead(texto: str, cumple: bool, codigo: str) -> None:
    veredicto = await DeterministicRuleMockJudge().evaluar(
        compuerta=COMPUERTA_LEAD, texto=texto
    )

    assert veredicto.cumple is cumple
    assert veredicto.codigo_accion == codigo


def test_juez_datos_extraidos_lee_referencias() -> None:
    juez = DeterministicRuleMockJudge()
    datos = juez._datos_extraidos(
        "Orden #104 viaje V2 mixer #M1 FC-210", "orden #104 viaje v2 mixer #m1 fc-210"
    )

    assert datos["orden"] == 104
    assert datos["viaje"] == 2
    assert datos["mixer"] == "MIXER-01"
    assert datos["resistencia"] == "FC-210"


# ---------------------------------------------------------------------------
# Contrato estricto del Juez
# ---------------------------------------------------------------------------
def test_parsear_veredicto_valido() -> None:
    veredicto = _parsear_veredicto(
        json.dumps(
            {
                "cumple": True,
                "codigo_accion": "REGISTRAR_SALIDA_PLANTA",
                "confianza": 1.7,
                "datos_extraidos": {"orden": 104},
            }
        ),
        "gemini_flash",
    )

    assert veredicto.cumple is True
    assert veredicto.confianza == 1.0
    assert veredicto.datos_extraidos == {"orden": 104}


@pytest.mark.parametrize(
    "crudo",
    [
        "no es json",
        "[]",
        '{"cumple": "si", "codigo_accion": "X", "confianza": 0.5, "datos_extraidos": {}}',
        '{"cumple": true, "codigo_accion": "", "confianza": 0.5, "datos_extraidos": {}}',
        '{"cumple": true, "codigo_accion": "X", "confianza": true, "datos_extraidos": {}}',
        '{"cumple": true, "codigo_accion": "X", "confianza": 0.5, "datos_extraidos": []}',
    ],
)
def test_parsear_veredicto_rechaza_salidas_fuera_de_contrato(crudo: str) -> None:
    with pytest.raises(ErrorJuez):
        _parsear_veredicto(crudo, "prueba")


# ---------------------------------------------------------------------------
# Gemini Flash: JSON forzado y fallback
# ---------------------------------------------------------------------------
def _respuesta_gemini(veredicto: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [
                {"content": {"parts": [{"text": json.dumps(veredicto)}]}}
            ]
        },
    )


@pytest.mark.asyncio
async def test_gemini_usa_salida_json_forzada() -> None:
    capturado: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["url"] = str(request.url)
        capturado["cuerpo"] = json.loads(request.content)
        return _respuesta_gemini(
            {
                "cumple": True,
                "codigo_accion": ACCION_DESPACHO_CONFIRMADO,
                "confianza": 0.97,
                "datos_extraidos": {"orden": 104},
            }
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as cliente:
        juez = GeminiFlashBooleanJudge(api_key="clave-falsa", http_client=cliente)
        veredicto = await juez.evaluar(
            compuerta=COMPUERTA_DESPACHO, texto="Ya salio el mixer"
        )

    assert veredicto.cumple is True
    assert veredicto.proveedor == "gemini_flash"
    assert capturado["url"].startswith(
        "https://generativelanguage.googleapis.com/v1beta/models/"
    )
    assert "gemini-2.5-flash:generateContent" in capturado["url"]
    assert capturado["cuerpo"]["generationConfig"]["responseMimeType"] == "application/json"
    assert capturado["cuerpo"]["generationConfig"]["temperature"] == 0


@pytest.mark.asyncio
async def test_gemini_sin_red_cae_al_deterministico() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as cliente:
        juez = GeminiFlashBooleanJudge(api_key="clave-falsa", http_client=cliente)
        veredicto = await juez.evaluar(
            compuerta=COMPUERTA_CLIENTE, texto="Recibi todo bien"
        )

    assert veredicto.cumple is True
    assert veredicto.codigo_accion == ACCION_RECEPCION_CONFORME
    assert veredicto.proveedor == "deterministico_fallback"
    assert veredicto.datos_extraidos["fallback"] == "ConnectError"


@pytest.mark.asyncio
async def test_gemini_con_salida_invalida_cae_al_deterministico() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": '{"cumple": "si"}'}]}}
                ]
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as cliente:
        juez = GeminiFlashBooleanJudge(api_key="clave-falsa", http_client=cliente)
        veredicto = await juez.evaluar(
            compuerta=COMPUERTA_CLIENTE, texto="Recibi todo bien"
        )

    assert veredicto.proveedor == "deterministico_fallback"
    assert veredicto.datos_extraidos["fallback"] == "ErrorJuez"


def test_construir_juez_sin_clave_usa_deterministico() -> None:
    juez = construir_juez(gemini_api_key="", model="gemini-2.5-flash", timeout=1.0)

    assert isinstance(juez, DeterministicRuleMockJudge)


def test_construir_juez_con_clave_usa_gemini() -> None:
    juez = construir_juez(
        gemini_api_key="clave-falsa", model="gemini-2.5-flash", timeout=1.0
    )

    assert isinstance(juez, GeminiFlashBooleanJudge)


# ---------------------------------------------------------------------------
# Bunny.net
# ---------------------------------------------------------------------------
def test_nombre_evidencia_estable() -> None:
    assert (
        nombre_evidencia(
            orden_numero=104,
            viaje_numero=2,
            mensaje_id="ABC-123!",
            extension="jpg",
        )
        == "ordenes/104/viaje_02_ABC-123.jpg"
    )


def test_decodificar_base64_acepta_data_uri() -> None:
    assert decodificar_base64("data:image/png;base64,aG9sYQ==") == b"hola"
    assert decodificar_base64(None) is None
    assert decodificar_base64("a") is None


def test_construir_bunny_sin_credenciales_es_no_configurado() -> None:
    settings = Settings(
        _env_file=None,
        bunny_cdn_host=None,
        bunny_storage_zone=None,
        bunny_storage_api_key=None,
    )

    assert isinstance(construir_bunny(settings), NullBunnyStorageClient)


@pytest.mark.asyncio
async def test_null_bunny_falla_explicito() -> None:
    with pytest.raises(BunnyNoConfigurado):
        await NullBunnyStorageClient().subir(nombre_archivo="x.jpg")


@pytest.mark.asyncio
async def test_bunny_http_sube_y_normaliza_host_cdn() -> None:
    capturado: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["url"] = str(request.url)
        capturado["clave"] = request.headers.get("AccessKey")
        return httpx.Response(201)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as cliente:
        bunny = BunnyHttpStorageClient(
            storage_zone="orminorth",
            api_key="clave-bunny",
            cdn_host="https://cdn.orminorth.example",
            http_client=cliente,
        )
        url = await bunny.subir(
            nombre_archivo="ordenes/104/foto.jpg",
            contenido=b"foto",
            mimetype="image/jpeg",
        )

    assert capturado["url"] == (
        "https://storage.bunnycdn.com/orminorth/ordenes/104/foto.jpg"
    )
    assert capturado["clave"] == "clave-bunny"
    assert url == "https://cdn.orminorth.example/ordenes/104/foto.jpg"


# ---------------------------------------------------------------------------
# Normalizacion del webhook de Evolution
# ---------------------------------------------------------------------------
def test_webhook_normaliza_mensaje_de_texto() -> None:
    payload = {
        "event": "messages.upsert",
        "data": [
            {
                "key": {
                    "remoteJid": "593991234567@s.whatsapp.net",
                    "fromMe": False,
                    "id": "ABC123",
                },
                "pushName": "Bodega",
                "message": {"conversation": "Ya salio el mixer"},
            }
        ],
    }

    mensajes = normalizar_evento(payload)

    assert len(mensajes) == 1
    assert mensajes[0].mensaje_id == "ABC123"
    assert mensajes[0].telefono == "593991234567"
    assert mensajes[0].telefono_normalizado == "991234567"
    assert mensajes[0].texto == "Ya salio el mixer"
    assert mensajes[0].nombre_contacto == "Bodega"


def test_webhook_ignora_eco_de_la_empresa() -> None:
    payload = {
        "event": "messages.upsert",
        "data": [
            {
                "key": {
                    "remoteJid": "593991234567@s.whatsapp.net",
                    "fromMe": True,
                    "id": "ECO",
                },
                "message": {"conversation": "mensaje enviado por el bot"},
            }
        ],
    }

    assert normalizar_evento(payload) == []


def test_webhook_de_grupo_usa_el_participante() -> None:
    payload = {
        "event": "messages.upsert",
        "data": [
            {
                "key": {
                    "remoteJid": "120363000000000000@g.us",
                    "participant": "593991234567@s.whatsapp.net",
                    "fromMe": False,
                    "id": "G1",
                },
                "message": {"conversation": "llego el mixer"},
            }
        ],
    }

    mensajes = normalizar_evento(payload)

    assert len(mensajes) == 1
    assert mensajes[0].es_grupo is True
    assert mensajes[0].telefono == "593991234567"


def test_webhook_normaliza_imagen_con_caption() -> None:
    payload = {
        "event": "messages.upsert",
        "data": [
            {
                "key": {
                    "remoteJid": "593991234567@s.whatsapp.net",
                    "fromMe": False,
                    "id": "IMG1",
                },
                "base64": "aG9sYQ==",
                "message": {
                    "imageMessage": {
                        "mimetype": "image/jpeg",
                        "caption": "guia de remision",
                    }
                },
            }
        ],
    }

    mensajes = normalizar_evento(payload)

    assert len(mensajes) == 1
    assert mensajes[0].texto == "guia de remision"
    assert len(mensajes[0].media) == 1
    assert mensajes[0].media[0].tipo == "imagen"
    assert mensajes[0].media[0].extension() == "jpg"
    assert mensajes[0].media[0].base64 == "aG9sYQ=="


def test_webhook_ignora_eventos_no_soportados() -> None:
    assert normalizar_evento({"event": "connection.update", "data": []}) == []


# ---------------------------------------------------------------------------
# Flujo completo: Bodega -> Chofer -> Cliente
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flujo_completo_bodega_chofer_cliente() -> None:
    repo = MemoriaRepositorio(viajes=[_viaje()])
    pipe, bunny, notifier = _pipeline(repo)
    payload = repo.viajes[0].payload

    # Gate #1: la bodega confirma la salida de planta.
    salida = await pipe.procesar(
        _batch(BODEGA, "Ya salio el mixer #M1 hacia la obra")
    )

    assert salida.rol == "BODEGA_PLANTA"
    assert salida.compuerta == COMPUERTA_DESPACHO
    assert salida.estado_actual == "EN_RUTA"
    assert payload["juez_binario_jeb"]["despacho_validado"] is True
    assert payload["tiempos_forenses"]["salida_planta"]
    assert payload["tiempos_forenses"]["limite_termico_fraguado"]
    # El ajuste ratificado viaja intacto en el contrato.
    assert payload["receta_provisional"] is True
    # Aviso al cliente por WhatsApp.
    assert len(notifier.enviados) == 1
    assert notifier.enviados[0]["telefono"] == CLIENTE
    assert "salio de planta" in notifier.enviados[0]["texto"]

    # Gate #3: el chofer manda la evidencia y se sube a Bunny.
    evidencia = await pipe.procesar(
        _batch(
            CHOFER,
            "Llegue a la obra",
            mensaje_id="FOTO-1",
            media=(
                MediaAttachment(
                    tipo="imagen",
                    mimetype="image/jpeg",
                    nombre="guia.jpg",
                    base64="aG9sYQ==",
                ),
            ),
        )
    )

    assert evidencia.rol == "CHOFER_MIXER"
    assert evidencia.compuerta == COMPUERTA_EVIDENCIA
    assert "EVIDENCIA_SUBIDA:1" in evidencia.acciones
    assert len(payload["evidencias_bunny_cdn"]) == 1
    assert payload["evidencias_bunny_cdn"][0].startswith("https://cdn.prueba.local/")
    assert payload["tiempos_forenses"]["llegada_obra_chofer"]
    assert bunny.subidas[0]["mimetype"] == "image/jpeg"
    assert bunny.subidas[0]["bytes"] == len(b"hola")

    # Gate #2: el cliente sella la recepcion.
    recepcion = await pipe.procesar(
        _batch(CLIENTE, "Recibi conforme, todo bien", mensaje_id="OK-1")
    )

    assert recepcion.rol == "CLIENTE"
    assert recepcion.compuerta == COMPUERTA_CLIENTE
    assert recepcion.estado_actual == "CONFIRMADO_CLIENTE"
    assert payload["juez_binario_jeb"]["recepcion_cliente_validada"] is True
    assert payload["juez_binario_jeb"]["incidencia_detectada"] is False
    assert payload["tiempos_forenses"]["confirmacion_whatsapp_cliente"]
    assert payload["whatsapp_msg_id_forense"] == "OK-1"
    assert payload["mensaje_literal_cliente"] == "Recibi conforme, todo bien"
    assert recepcion.alerta is None
    assert repo.leads == []


@pytest.mark.asyncio
async def test_salida_registra_mixer_declarado_si_el_viaje_no_tenia() -> None:
    """El bodeguero dice #M1 y el viaje aun no tenia mixer asignado."""
    base = _viaje()
    payload = dict(base.payload)
    payload["mixer_codigo"] = None
    sin_mixer = ViajeObjetivo(
        dispatch_id=base.dispatch_id,
        order_id=base.order_id,
        orden_numero=base.orden_numero,
        viaje_numero=base.viaje_numero,
        total_viajes_orden=base.total_viajes_orden,
        mixer_codigo=None,
        cliente_id=base.cliente_id,
        cliente_nombre=base.cliente_nombre,
        cliente_telefono=base.cliente_telefono,
        payload=payload,
    )
    repo = MemoriaRepositorio(viajes=[sin_mixer])
    pipe, _, _ = _pipeline(repo)

    resultado = await pipe.procesar(
        _batch(BODEGA, "Ya salio el mixer #M1 hacia la obra #BODEGA")
    )

    assert resultado.estado_actual == "EN_RUTA"
    assert payload["mixer_codigo"] == "MIXER-01"


@pytest.mark.asyncio
async def test_reclamo_de_cliente_alerta_al_centinela() -> None:
    repo = MemoriaRepositorio(viajes=[_viaje()])
    pipe, _, _ = _pipeline(repo)
    payload = repo.viajes[0].payload

    await pipe.procesar(_batch(BODEGA, "Ya salio el mixer #M1"))
    reclamo = await pipe.procesar(
        _batch(CLIENTE, "Hay mucha demora, el hormigon no ha llegado")
    )

    assert reclamo.estado_actual == "INCIDENCIA_RECLAMO"
    assert payload["juez_binario_jeb"]["incidencia_detectada"] is True
    assert payload["juez_binario_jeb"]["recepcion_cliente_validada"] is False
    assert reclamo.alerta is not None
    # Sin AGENCY_CRM_WEBHOOK_URL: degrada a NO_CONFIGURADO, no finge el envio.
    assert reclamo.alerta["estado"] == "NO_CONFIGURADO"
    assert any(
        log["nivel"] == "ERROR"
        and log["contexto"].get("codigo") == "INCIDENCIA_RECLAMO_CLIENTE"
        for log in repo.logs
    )


@pytest.mark.asyncio
async def test_lead_desconocido_crea_prospecto() -> None:
    repo = MemoriaRepositorio()
    pipe, _, _ = _pipeline(repo)

    resultado = await pipe.procesar(
        _batch("0977777777", "Necesito cotizacion de hormigon para 20 m3")
    )

    assert resultado.compuerta == COMPUERTA_LEAD
    assert "PROSPECTO_CREADO" in resultado.acciones
    assert len(repo.leads) == 1
    assert repo.leads[0]["estado"] == "PROSPECTO"

    # Un segundo mensaje del mismo numero no duplica la ficha.
    await pipe.procesar(
        _batch("0977777777", "Sigo interesado, cuanto cuesta el m3")
    )
    assert len(repo.leads) == 1


@pytest.mark.asyncio
async def test_evidencia_sin_bunny_registra_incidencia() -> None:
    repo = MemoriaRepositorio(viajes=[_viaje(estado="EN_RUTA")])
    bunny = NullBunnyStorageClient()
    notifier = RecordingNotifier()
    pipe = WhatsAppPipeline(
        repo=repo,
        identidad=IdentityResolver(registro=_registro()),
        juez=DeterministicRuleMockJudge(),
        bunny=bunny,
        notifier=notifier,
        alerter=SentinelAlerter(webhook_url=None, master_key=None, repo=repo),
    )

    resultado = await pipe.procesar(
        _batch(
            CHOFER,
            "Llegue",
            media=(MediaAttachment(tipo="imagen", base64="aG9sYQ=="),),
        )
    )

    assert resultado.estado_actual == "EVIDENCIA_PENDIENTE"
    assert "EVIDENCIA_FALLIDA" in resultado.acciones
    assert resultado.alerta is not None
    assert resultado.alerta["codigo"] == "EVIDENCIA_BUNNY_FALLIDA"


# ---------------------------------------------------------------------------
# Alerta al CRM de la agencia
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_alerter_envia_webhook_con_clave_maestra() -> None:
    repo = MemoriaRepositorio()
    capturado: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["url"] = str(request.url)
        capturado["clave"] = request.headers.get("X-Agency-Master-Key")
        capturado["cuerpo"] = json.loads(request.content)
        return httpx.Response(202, json={"recibido": True})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as cliente:
        alerter = SentinelAlerter(
            webhook_url="https://crm.agencia.example/hook",
            master_key="clave-agencia",
            repo=repo,
            http_client=cliente,
        )
        resultado = await alerter.alertar(
            codigo="PRUEBA",
            mensaje="alerta de prueba",
            contexto={"viaje": 1},
            order_id=str(uuid4()),
        )

    assert resultado.estado == "ENVIADO"
    assert resultado.http_status == 202
    assert capturado["clave"] == "clave-agencia"
    assert capturado["cuerpo"]["evento"] == "PRUEBA"
    assert capturado["cuerpo"]["datos"] == {"viaje": 1}
    assert repo.logs[-1]["nivel"] == "ERROR"
    assert repo.logs[-1]["contexto"]["codigo"] == "PRUEBA"


@pytest.mark.asyncio
async def test_alerter_sin_clave_maestra_no_finge_envio() -> None:
    repo = MemoriaRepositorio()
    alerter = SentinelAlerter(
        webhook_url="https://crm.agencia.example/hook",
        master_key="change-me",
        repo=repo,
    )

    resultado = await alerter.alertar(codigo="X", mensaje="y")

    assert resultado.estado == "NO_CONFIGURADO"
    assert resultado.http_status is None
    assert repo.logs[-1]["nivel"] == "ERROR"


# ---------------------------------------------------------------------------
# Worker de la ventana
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_worker_procesa_el_lote_vencido() -> None:
    repo = MemoriaRepositorio(viajes=[_viaje()])
    pipe, _, _ = _pipeline(repo)
    acumulador = DebounceAccumulator(MemoryBufferStore(), ventana_segundos=0.1)
    worker = DebounceWorker(
        accumulator=acumulador, pipeline=pipe, repo=repo, intervalo_segundos=0.01
    )
    pasado = datetime.now(timezone.utc) - timedelta(seconds=2)

    await acumulador.agregar(
        _msg(BODEGA, "Ya salio el mixer #M1", mensaje_id="W1"), ahora=pasado
    )

    resultados = await worker.tick()

    assert len(resultados) == 1
    assert resultados[0].estado_actual == "EN_RUTA"
    assert repo.viajes[0].payload["estado_actual"] == "EN_RUTA"


# ---------------------------------------------------------------------------
# Endpoints HTTP del Modulo 1
# ---------------------------------------------------------------------------
class _WorkerFalso:
    def __init__(self) -> None:
        self.llamadas = 0

    async def tick(self) -> list[object]:
        self.llamadas += 1
        return []


class _RuntimeFalso:
    def __init__(self) -> None:
        self.accumulator = DebounceAccumulator(
            MemoryBufferStore(), ventana_segundos=14.0
        )
        self.worker = _WorkerFalso()
        self.ventana_segundos = 14.0

    def estado(self) -> dict[str, object]:
        return {
            "store": "memoria",
            "ventana_segundos": 14.0,
            "juez": "deterministico",
            "bunny": "no_configurado",
            "notifier": "no_configurado",
            "webhook_centinela": "NO_CONFIGURADO",
        }


def _app_m1(clave: str = CLAVE_M1) -> FastAPI:
    app = FastAPI()
    app.state.settings = Settings(_env_file=None, agency_master_key=clave)
    app.state.whatsapp = _RuntimeFalso()
    app.include_router(whatsapp_router)
    return app


def _payload_evolution() -> dict:
    return {
        "event": "messages.upsert",
        "data": [
            {
                "key": {
                    "remoteJid": "593991234567@s.whatsapp.net",
                    "fromMe": False,
                    "id": "H1",
                },
                "message": {"conversation": "Ya salio el mixer"},
            }
        ],
    }


@pytest.mark.asyncio
async def test_endpoint_webhook_encola_mensajes() -> None:
    app = _app_m1()
    transporte = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transporte, base_url="http://test"
    ) as cliente:
        respuesta = await cliente.post("/api/v1/whatsapp/webhook", json=_payload_evolution())

    assert respuesta.status_code == 200
    assert respuesta.json() == {"recibidos": 1, "ventana_segundos": 14.0}
    assert len(app.state.whatsapp.accumulator.store._buffers) == 1


@pytest.mark.asyncio
async def test_endpoint_simulate_exige_clave_maestra() -> None:
    app = _app_m1()
    transporte = httpx.ASGITransport(app=app)
    cuerpo = {"telefono": "0999999999", "texto": "recibi todo bien"}

    async with httpx.AsyncClient(
        transport=transporte, base_url="http://test"
    ) as cliente:
        sin_clave = await cliente.post("/api/v1/whatsapp/simulate", json=cuerpo)
        con_clave = await cliente.post(
            "/api/v1/whatsapp/simulate",
            json=cuerpo,
            headers={"X-Agency-Master-Key": CLAVE_M1},
        )

    assert sin_clave.status_code == 401
    assert con_clave.status_code == 200
    assert con_clave.json()["telefono"] == "999999999"


@pytest.mark.asyncio
async def test_endpoint_flush_fuerza_el_tick() -> None:
    app = _app_m1()
    transporte = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transporte, base_url="http://test"
    ) as cliente:
        respuesta = await cliente.post(
            "/api/v1/whatsapp/flush",
            headers={"X-Agency-Master-Key": CLAVE_M1},
        )

    assert respuesta.status_code == 200
    assert respuesta.json() == {"lotes": 0, "resultados": []}
    assert app.state.whatsapp.worker.llamadas == 1


@pytest.mark.asyncio
async def test_endpoint_health_no_expone_secretos() -> None:
    app = _app_m1()
    transporte = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transporte, base_url="http://test"
    ) as cliente:
        respuesta = await cliente.get("/api/v1/whatsapp/health")

    cuerpo = respuesta.json()
    assert respuesta.status_code == 200
    assert cuerpo["modulo"] == "M1_WHATSAPP"
    assert cuerpo["estado"] == "NO_CONFIGURADO"
    assert cuerpo["ventana_segundos"] == 14.0
    assert "clave" not in json.dumps(cuerpo).lower()


@pytest.mark.asyncio
async def test_endpoint_sin_runtime_responde_503() -> None:
    app = FastAPI()
    app.state.settings = Settings(_env_file=None, agency_master_key=CLAVE_M1)
    app.state.whatsapp = None
    app.include_router(whatsapp_router)
    transporte = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transporte, base_url="http://test"
    ) as cliente:
        respuesta = await cliente.get("/api/v1/whatsapp/health")

    assert respuesta.status_code == 503
    assert "no inicializado" in respuesta.json()["detail"]
