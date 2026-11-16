"""Correcciones humanas del Cerebro: editar lo entendido y recompilar."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.cerebro.extractor import _mensaje
from app.cerebro.hechos import Evidencia, HechoCitado, validar_hecho, validar_hechos
from app.cerebro.revision import (
    CorreccionInvalida,
    aplicar,
    corregir,
    normalizar_valor,
    resumen_legible,
)

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]


def _migracion() -> Path:
    """Funciona con el servicio suelto y dentro del contenedor (/app/db)."""
    for base in (RAIZ_SERVICIO, *RAIZ_SERVICIO.parents):
        candidato = base / "db" / "migrations" / "087_cerebro_correcciones.sql"
        if candidato.is_file():
            return candidato
    raise FileNotFoundError("087_cerebro_correcciones.sql no encontrada")


def hecho(
    clave: str,
    valor,
    tipo: str = "TEXTO",
    *,
    cita: str | None = None,
    sostiene: str | None = None,
) -> HechoCitado:
    texto = cita if cita is not None else str(valor)
    return HechoCitado(
        clave=clave,
        valor=valor,
        estado="EXTRAIDO",
        tipo=tipo,
        evidencia=Evidencia(
            cita=texto,
            sostiene=sostiene if sostiene is not None else str(valor),
            crudo_inicio=0,
            crudo_fin=len(texto),
            start_ms=0,
            end_ms=900,
            confianza=0.9,
            hablante="SUPERADMIN",
        ),
    )


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------
def test_normalizar_valor_respeta_el_tipo() -> None:
    assert normalizar_valor("BOOLEANO", "sí") is True
    assert normalizar_valor("BOOLEANO", "no") is False
    assert normalizar_valor("TELEFONO", "0963 444 444") == "0963444444"
    assert normalizar_valor("DECIMAL", "27.000") == Decimal("27000")
    assert normalizar_valor("DECIMAL", "27,000") == Decimal("27000")
    assert normalizar_valor("HORA", "6 de la tarde") == "18:00"
    assert normalizar_valor("FECHA", "2026-11-21") == date(2026, 11, 21)
    assert normalizar_valor("TEXTO", "  Dualsur  ") == "Dualsur"


def test_normalizar_valor_rechaza_lo_que_no_es() -> None:
    with pytest.raises(CorreccionInvalida):
        normalizar_valor("TELEFONO", "123")
    with pytest.raises(CorreccionInvalida):
        normalizar_valor("BOOLEANO", "tal vez")
    with pytest.raises(CorreccionInvalida):
        normalizar_valor("TEXTO", "   ")


# ---------------------------------------------------------------------------
# Corrección de un hecho
# ---------------------------------------------------------------------------
def test_corregir_conserva_la_cita_y_marca_el_estado() -> None:
    original = hecho("cliente.nombre", "empresa Díaz Sur", cita="la empresa Díaz Sur")

    corregido = corregir(original, "cliente.nombre", "Dualsur")

    assert corregido.valor == "Dualsur"
    assert corregido.estado == "CORREGIDO_POR_HUMANO"
    assert corregido.evidencia is not None
    assert corregido.evidencia.cita == "la empresa Díaz Sur"
    assert validar_hecho(corregido) == []


def test_un_dato_nuevo_no_finge_evidencia() -> None:
    corregido = corregir(None, "tarea.destinatario", "Mauricio Santander")

    assert corregido.evidencia is None
    assert corregido.estado == "CORREGIDO_POR_HUMANO"
    assert validar_hecho(corregido) == []
    # Sin el estado humano, un hecho sin cita es invalido.
    impostor = HechoCitado(clave="tarea.destinatario", valor="X", estado="EXTRAIDO")
    assert validar_hecho(impostor)


def test_aplicar_no_toca_los_demas_hechos() -> None:
    hechos = [
        hecho("cliente.nombre", "empresa Díaz Sur"),
        hecho("cotizacion.volumen_m3", 380, "DECIMAL"),
    ]

    salida = aplicar(hechos, {"cliente.nombre": "Dualsur"})

    assert [h.clave for h in salida] == ["cliente.nombre", "cotizacion.volumen_m3"]
    assert salida[0].valor == "Dualsur"
    assert salida[1].valor == 380
    assert validar_hechos(salida) == []


def test_aplicar_agrega_la_respuesta_a_una_pregunta() -> None:
    hechos = [hecho("cliente.nombre", "empresa Díaz Sur")]
    salida = aplicar(
        hechos,
        {"tarea.destinatario": "Mauricio Santander"},
        tipos={"tarea.destinatario": "TEXTO"},
    )

    assert [h.clave for h in salida] == ["cliente.nombre", "tarea.destinatario"]
    assert salida[1].estado == "CORREGIDO_POR_HUMANO"
    assert validar_hechos(salida) == []


# ---------------------------------------------------------------------------
# Lectura en voz alta
# ---------------------------------------------------------------------------
def test_resumen_dice_lo_que_entendio() -> None:
    hechos = [
        hecho("cliente.nombre", "Dualsur"),
        hecho("cotizacion.volumen_m3", 380, "DECIMAL"),
        hecho("cotizacion.resistencia", "240"),
        hecho("cotizacion.descuento_pct", 13, "ENTERO"),
        hecho("cotizacion.plazo_entrega", "en un mes"),
        hecho("contacto.nombre", "Mauricio Santander"),
        hecho("contacto.rol", "ingeniero"),
        hecho("contacto.telefono", "0985454545", "TELEFONO"),
        hecho("pago.monto", 27000, "DECIMAL"),
        hecho("pago.forma", "transferencia"),
        hecho("pago.recibido", False, "BOOLEANO"),
        hecho("tarea.mensaje", "que nos haga la transferencia"),
        hecho("tarea.cuando", "18:00"),
    ]

    resumen = resumen_legible(hechos)

    assert resumen.startswith("Entendí:")
    assert "Dualsur" in resumen
    assert "380 m3 de 240" in resumen
    assert "13% de descuento" in resumen
    assert "Mauricio Santander" in resumen
    assert "27000 USD" in resumen
    assert "todavía no entra" in resumen or "todavia no entra" in resumen
    assert "18:00" in resumen


def test_resumen_sin_hechos_lo_dice() -> None:
    assert "No entendí" in resumen_legible([])


def test_resumen_no_dice_que_el_dinero_entro_si_no_se_sabe() -> None:
    hechos = [
        hecho("pago.monto", 27000, "DECIMAL"),
        hecho("pago.forma", "transferencia"),
    ]

    resumen = resumen_legible(hechos)

    assert "sin confirmar si ya entró" in resumen
    assert "que ya entró" not in resumen
    assert "todavía no entra" not in resumen


def test_resumen_no_afirma_que_entro_sin_frase_en_pasado() -> None:
    hechos = [
        hecho("pago.monto", 27000, "DECIMAL"),
        hecho("pago.recibido", True, "BOOLEANO"),
    ]

    resumen = resumen_legible(hechos, texto="nos van a transferir 27000 USD")

    assert "sin confirmar si ya entró" in resumen


def test_resumen_dice_que_entro_cuando_el_audio_lo_dice_en_pasado() -> None:
    hechos = [
        hecho("pago.monto", 27000, "DECIMAL"),
        hecho("pago.recibido", True, "BOOLEANO"),
    ]

    resumen = resumen_legible(hechos, texto="ya me deposito 27000 USD")

    assert "que ya entró" in resumen


# ---------------------------------------------------------------------------
# Pista de vocabulario en el prompt
# ---------------------------------------------------------------------------
def test_el_prompt_lleva_las_correcciones_aprendidas() -> None:
    mensaje = _mensaje(
        "contrato con la empresa Díaz Sur",
        [],
        date(2026, 11, 15),
        (),
        [("Díaz Sur", "Dualsur")],
    )

    assert "CORRECCIONES CONOCIDAS" in mensaje
    assert "«Díaz Sur» → «Dualsur»" in mensaje


# ---------------------------------------------------------------------------
# Migración
# ---------------------------------------------------------------------------
def test_migracion_087_es_append_only() -> None:
    sql = _migracion().read_text(encoding="utf-8")

    assert "CREATE TABLE cerebro_correcciones" in sql
    assert "trg_cerebro_correcciones_immutable" in sql
    assert "CREATE OR REPLACE VIEW v_cerebro_vocabulario" in sql
    assert "SUPERADO_POR_CORRECCION" in sql
