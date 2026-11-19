"""Pruebas de las manos de Miau en Bunny (listar, mover, borrar)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.cerebro import ejecutores  # noqa: E402
from app.cerebro.router import _ruta_permitida  # noqa: E402
from app.m1_whatsapp.bunny import BunnyError, BunnyHttpStorageClient  # noqa: E402


class RespuestaFalsa:
    def __init__(self, status: int, payload=None, content: bytes = b""):
        self.status_code = status
        self._payload = payload
        self.content = content

    def json(self):
        return self._payload


class HttpFalso:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas: list[tuple[str, str]] = []

    async def request(self, metodo, url, **kwargs):
        self.llamadas.append((metodo, url))
        return self.respuestas.pop(0)

    async def put(self, url, **kwargs):
        self.llamadas.append(("PUT", url))
        return self.respuestas.pop(0)

    async def get(self, url, **kwargs):
        self.llamadas.append(("GET", url))
        return self.respuestas.pop(0)


def _cliente(http) -> BunnyHttpStorageClient:
    return BunnyHttpStorageClient(
        storage_zone="horminor-media",
        api_key="clave",
        cdn_host="horminor.b-cdn.net",
        http_client=http,
    )


def test_ruta_permitida_solo_dentro_del_prefijo() -> None:
    assert _ruta_permitida("horminor", "horminor/clientes/paola/x.pdf")
    assert _ruta_permitida("horminor", "horminor")
    assert not _ruta_permitida("horminor", "otra-cosa/x.pdf")
    assert not _ruta_permitida("horminor", "horminor/../secreto")
    assert not _ruta_permitida("horminor", "/horminor/x.pdf")
    assert not _ruta_permitida("horminor", "")


def test_ruta_manifiesto_usa_la_carpeta_del_cliente() -> None:
    ruta = ejecutores.ruta_manifiesto("paola_b387d6a873d3", "horminor")
    assert ruta == "horminor/clientes/paola_b387d6a873d3/_momento_cero.json"


@pytest.mark.asyncio
async def test_listar_mapea_la_respuesta_de_bunny() -> None:
    http = HttpFalso(
        [
            RespuestaFalsa(
                200,
                [
                    {"ObjectName": "a.pdf", "IsDirectory": False, "Length": 10, "LastChanged": "2026-11-18"},
                    {"ObjectName": "fotos", "IsDirectory": True, "Length": 0, "LastChanged": "2026-11-18"},
                ],
            )
        ]
    )
    entradas = await _cliente(http).listar("horminor/clientes/paola")

    assert [e["nombre"] for e in entradas] == ["a.pdf", "fotos"]
    assert entradas[1]["es_directorio"] is True
    assert http.llamadas[0][0] == "GET"
    assert http.llamadas[0][1].endswith("/horminor/clientes/paola/")


@pytest.mark.asyncio
async def test_borrar_inexistente_devuelve_falso() -> None:
    http = HttpFalso([RespuestaFalsa(404)])
    assert await _cliente(http).borrar("horminor/clientes/paola/no-existe.pdf") is False


@pytest.mark.asyncio
async def test_ruta_con_traversal_se_rechaza_antes_de_red() -> None:
    cliente = _cliente(HttpFalso([]))
    with pytest.raises(BunnyError):
        await cliente.listar("horminor/../otra")


@pytest.mark.asyncio
async def test_mover_descarga_sube_y_borra() -> None:
    http = HttpFalso(
        [
            RespuestaFalsa(200, content=b"contenido"),  # GET origen
            RespuestaFalsa(201),                        # PUT destino
            RespuestaFalsa(200),                        # DELETE origen
        ]
    )
    url = await _cliente(http).mover(
        "horminor/clientes/paola/viejo.pdf",
        "horminor/clientes/paola/nuevo.pdf",
    )

    assert url == "https://horminor.b-cdn.net/horminor/clientes/paola/nuevo.pdf"
    assert [m for m, _ in http.llamadas] == ["GET", "PUT", "DELETE"]


def test_bucket_por_extension_sin_replicar_la_base() -> None:
    assert ejecutores.bucket_de("foto.webp") == "media"
    assert ejecutores.bucket_de("video.mp4") == "media"
    assert ejecutores.bucket_de("nota.ogg") == "media"
    assert ejecutores.bucket_de("audio.oga") == "media"
    assert ejecutores.bucket_de("contrato.pdf") == "documentos"
    assert ejecutores.bucket_de("planilla.xlsx") == "documentos"
    assert ejecutores.bucket_de("sin_extension") == "documentos"


def test_destino_dentro_de_la_carpeta_del_cliente() -> None:
    destino = ejecutores.destino_cliente("horminor", "paola_b387d6a873d3", "foto.jpg")
    assert destino["ruta"] == "horminor/clientes/paola_b387d6a873d3/media/foto.jpg"
    assert destino["bucket"] == "media"

    documento = ejecutores.destino_cliente("horminor", "paola_b387d6a873d3", "factura.pdf")
    assert documento["ruta"] == "horminor/clientes/paola_b387d6a873d3/documentos/factura.pdf"


def test_plan_ignora_rutas_peligrosas() -> None:
    plan = ejecutores.plan_mover_a_cliente(
        "horminor",
        "paola_b387d6a873d3",
        [
            "horminor/temporal/foto.jpg",
            "horminor/../secreto.pdf",
            "horminor/temporal/contrato.pdf",
        ],
    )
    assert [p["origen"] for p in plan] == [
        "horminor/temporal/foto.jpg",
        "horminor/temporal/contrato.pdf",
    ]
    assert [p["bucket"] for p in plan] == ["media", "documentos"]


def test_plan_alta_conserva_el_media_id_y_clasifica() -> None:
    filas = [
        {
            "id": "m1",
            "storage_path": "horminor/temporal/foto.jpg",
            "tipo": "IMAGEN",
            "nombre_original": "foto.jpg",
        },
        {
            "id": "m2",
            "storage_path": "horminor/temporal/contrato.pdf",
            "tipo": "DOCUMENTO",
            "nombre_original": "contrato.pdf",
        },
    ]
    plan = ejecutores.plan_alta("horminor", "cliente_x", filas)

    assert [p["media_id"] for p in plan] == ["m1", "m2"]
    assert [p["bucket"] for p in plan] == ["media", "documentos"]
    assert plan[0]["destino"] == "horminor/clientes/cliente_x/media/foto.jpg"
    assert plan[1]["destino"] == "horminor/clientes/cliente_x/documentos/contrato.pdf"
