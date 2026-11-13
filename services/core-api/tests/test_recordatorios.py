"""Tests de los recordatorios de Gato (sin base de datos real)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

import asyncio  # noqa: E402
from decimal import Decimal  # noqa: E402

from app.asistente import recordatorios  # noqa: E402
from app.asistente.despachador import DespachadorRecordatorios  # noqa: E402
from app.asistente.fichas import Resultado  # noqa: E402
from app.asistente.orquestador import Actor, planear  # noqa: E402
from app.asistente.redactor import redactar  # noqa: E402

ZONA = ZoneInfo("America/Guayaquil")
BASE = datetime(2026, 11, 12, 9, 0, tzinfo=ZONA)


def _utc(momento: datetime) -> datetime:
    return momento.astimezone(timezone.utc)


def test_parsea_hora_completa() -> None:
    cuando = recordatorios.parsear_cuando("a las 18:40", ahora=BASE)
    assert cuando is not None
    assert _utc(cuando).hour == 23  # 18:40 en Ecuador = 23:40 UTC
    assert _utc(cuando).minute == 40


def test_parsea_manana_con_hora() -> None:
    cuando = recordatorios.parsear_cuando("mañana a las 9", ahora=BASE)
    assert cuando is not None
    local = cuando.astimezone(ZONA)
    assert local.date() == BASE.date() + timedelta(days=1)
    assert (local.hour, local.minute) == (9, 0)


def test_parsea_en_minutos() -> None:
    cuando = recordatorios.parsear_cuando("en 30 minutos", ahora=BASE)
    assert cuando is not None
    assert cuando.astimezone(ZONA) == BASE + timedelta(minutes=30)


def test_parsea_iso_del_llm() -> None:
    cuando = recordatorios.parsear_cuando("2026-11-12T18:40:00", ahora=BASE)
    assert cuando is not None
    local = cuando.astimezone(ZONA)
    assert (local.hour, local.minute) == (18, 40)


def test_hora_pasada_sin_hoy_pasa_a_manana() -> None:
    tarde = datetime(2026, 11, 12, 20, 0, tzinfo=ZONA)
    cuando = recordatorios.parsear_cuando("a las 18:40", ahora=tarde)
    assert cuando is not None
    assert cuando.astimezone(ZONA).date() == tarde.date() + timedelta(days=1)


def test_sin_hora_no_inventa() -> None:
    assert recordatorios.parsear_cuando("recuérdale la cita", ahora=BASE) is None
    assert recordatorios.parsear_cuando("", ahora=BASE) is None


def test_de_la_manana_es_am_y_no_es_manana() -> None:
    temprano = datetime(2026, 11, 12, 5, 0, tzinfo=ZONA)
    cuando = recordatorios.parsear_cuando("a las 7 de la mañana", ahora=temprano)
    assert cuando is not None
    local = cuando.astimezone(ZONA)
    assert local.date() == temprano.date()  # hoy, no mañana
    assert (local.hour, local.minute) == (7, 0)


def test_de_la_tarde_es_pm() -> None:
    cuando = recordatorios.parsear_cuando("a las 6 de la tarde", ahora=BASE)
    assert cuando is not None
    assert cuando.astimezone(ZONA).hour == 18


def test_toma_la_ultima_hora_de_la_frase() -> None:
    frase = "la cita es a las 18:40 y recuérdame a las 17:00"
    cuando = recordatorios.parsear_cuando(frase, ahora=BASE)
    assert cuando is not None
    local = cuando.astimezone(ZONA)
    assert (local.hour, local.minute) == (17, 0)


def test_afirmaciones_y_negaciones() -> None:
    for texto in ("sí", "Si", "dale", "confirmo", "ok", "adelante"):
        assert recordatorios.es_afirmacion(texto), texto
    for texto in ("no", "No.", "cancela", "descarta", "mejor no"):
        assert recordatorios.es_negacion(texto), texto
    assert not recordatorios.es_afirmacion("sírvete un café")
    assert not recordatorios.es_negacion("no sé, pregúntale a Julio")


def test_ahora_mismo_es_ahora() -> None:
    cuando = recordatorios.parsear_cuando("ahora mismo", ahora=BASE)
    assert cuando is not None
    assert abs((cuando - BASE).total_seconds()) <= 60


def test_cifras_de_detecta_montos() -> None:
    valores = recordatorios.cifras_de(
        "Su saldo es USD 52.872,40 y la factura $43,424.00"
    )
    assert Decimal("52872.40") in valores
    assert Decimal("43424.00") in valores


def test_cifras_de_ignora_horas_y_numeros_de_orden() -> None:
    assert recordatorios.cifras_de("a las 18:40 la orden 55") == set()


def test_interpreta_factura_adjunta() -> None:
    info = recordatorios.interpretar(
        "notifícale al ing Reyes que pásale la factura a las 18:40", ahora=BASE
    )
    assert info["adjuntar_factura"] is True
    assert info["destinatario"] == "ing Reyes"


async def test_sin_usuario_no_agenda() -> None:
    resultado = await recordatorios.crear(
        None,
        actor=Actor(nombre="Ana", rol="SECRETARIA", actor_id="panel"),
        destinatario="ing Reyes",
        mensaje="hola",
        cuando="18:40",
    )
    assert resultado.estado == "FALTA_PARAMETRO"
    assert resultado.parametro_faltante == "usuario"


def test_interpreta_la_frase_de_julio() -> None:
    frase = (
        "Gato debes escribirle al ing Reyes a las 18:40 y recordarle que "
        "tiene una cita en las oficinas de Horminor"
    )
    info = recordatorios.interpretar(frase, ahora=BASE)
    assert info["destinatario"] == "ing Reyes"
    assert info["mensaje"] == "tiene una cita en las oficinas de Horminor"
    assert info["cuando"] is not None


def test_plan_detecta_recordatorio() -> None:
    plan = planear(
        "escríbele al ing Reyes a las 18:40 y recuérdale que tiene una cita "
        "en las oficinas de Horminor"
    )
    assert plan.faltante is None
    pilar, accion, params = plan.pasos[0]
    assert (pilar, accion) == ("recordatorios", "recordatorio_crear")
    assert params["destinatario"].lower().endswith("reyes")
    assert "cita" in params["mensaje"]


def test_plan_pide_la_hora_si_falta() -> None:
    plan = planear("escríbele al ing Reyes y recuérdale que tiene la cita")
    assert plan.faltante is not None
    assert "hora" in plan.faltante.lower()


def test_redactor_muestra_la_confirmacion() -> None:
    r = Resultado(
        "recordatorio_crear",
        "OK",
        datos={"id": "x"},
        nota="Recordatorio programado para 12/11/2026 18:40 (America/Guayaquil).",
    )
    texto = redactar([r], "SUPERADMIN", "Julio")
    assert "programado" in texto
    assert "18:40" in texto


async def test_bodega_no_puede_programar() -> None:
    resultado = await recordatorios.crear(
        None,
        actor=Actor(nombre="Bodega", rol="BODEGA", actor_id="bodega"),
        destinatario="ing Reyes",
        mensaje="hola",
        cuando="18:40",
    )
    assert resultado.estado == "ACL"


async def test_sin_mensaje_no_crea() -> None:
    resultado = await recordatorios.crear(
        None,
        actor=Actor(nombre="Ana", rol="SECRETARIA", actor_id="ana"),
        destinatario="ing Reyes",
        mensaje="   ",
        cuando="18:40",
    )
    assert resultado.estado == "FALTA_PARAMETRO"
    assert resultado.parametro_faltante == "mensaje"


class _Notifier:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.enviados: list[tuple[str, str]] = []

    async def enviar_texto(self, telefono: str, texto: str) -> bool:
        self.enviados.append((telefono, texto))
        return self.ok


class _Pool:
    def __init__(self, filas: list[dict], estado: str = "ENVIANDO") -> None:
        self.filas = filas
        self.estado = estado
        self.consultas: list[tuple[str, tuple]] = []

    async def fetch(self, sql: str, *args):
        self.consultas.append((sql, args))
        if "UPDATE gato_recordatorios r" in sql:
            return self.filas
        return []

    async def fetchval(self, sql: str, *args):
        self.consultas.append((sql, args))
        return self.estado

    async def execute(self, sql: str, *args):
        self.consultas.append((sql, args))
        return "UPDATE 1"


async def test_despachador_no_envia_lo_cancelado_entre_reclamo_y_envio() -> None:
    pool = _Pool(
        [{"id": "r1", "telefono": "0990000013", "mensaje": "x",
          "intentos": 1, "destinatario_nombre": None}],
        estado="CANCELADO",
    )
    notifier = _Notifier()
    despachador = DespachadorRecordatorios(
        pool=pool, proveedor_notifier=lambda: notifier, intervalo_segundos=1
    )
    assert await despachador.tick() == []
    assert notifier.enviados == []


async def test_despachador_envia_lo_vencido() -> None:
    pool = _Pool(
        [{"id": "r1", "telefono": "+593967491847", "mensaje": "cita 18:40",
          "intentos": 1, "destinatario_nombre": "Cristhopher"}]
    )
    notifier = _Notifier()
    despachador = DespachadorRecordatorios(
        pool=pool, proveedor_notifier=lambda: notifier, intervalo_segundos=1
    )
    procesados = await despachador.tick()
    assert [p["resultado"] for p in procesados] == ["ENVIADO"]
    assert notifier.enviados == [("593967491847", "cita 18:40")]
    assert any("SET estado = 'ENVIADO'" in sql for sql, _ in pool.consultas)


async def test_despachador_sin_canal_libera_la_fila() -> None:
    pool = _Pool(
        [{"id": "r1", "telefono": "+593967491847", "mensaje": "x",
          "intentos": 1, "destinatario_nombre": None}]
    )
    despachador = DespachadorRecordatorios(
        pool=pool, proveedor_notifier=lambda: None, intervalo_segundos=1
    )
    assert await despachador.tick() == []
    assert any("GREATEST(intentos - 1, 0)" in sql for sql, _ in pool.consultas)


async def test_despachador_marca_fallido_tras_tres_intentos() -> None:
    pool = _Pool(
        [{"id": "r1", "telefono": "+593967491847", "mensaje": "x",
          "intentos": 3, "destinatario_nombre": None}]
    )
    notifier = _Notifier(ok=False)
    despachador = DespachadorRecordatorios(
        pool=pool, proveedor_notifier=lambda: notifier, intervalo_segundos=1
    )
    procesados = await despachador.tick()
    assert [p["resultado"] for p in procesados] == ["FALLIDO"]
    assert any("SET estado = 'FALLIDO'" in sql for sql, _ in pool.consultas)
