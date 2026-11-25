"""Pruebas adversariales de la auditoria de conversaciones con Gato."""

from __future__ import annotations

from datetime import date

import pytest

from app.asistente import router as asistente_http
from app.cerebro.compilador import Contexto, compilar
from app.cerebro.hechos import Evidencia, HechoCitado


def _hecho(clave: str, valor, *, encargo: int = 1, cita: str = "x") -> HechoCitado:
    return HechoCitado(
        clave=clave,
        valor=valor,
        estado="EXTRAIDO",
        tipo="TEXTO",
        evidencia=Evidencia(
            cita=cita,
            sostiene=cita,
            crudo_inicio=0,
            crudo_fin=len(cita),
            start_ms=None,
            end_ms=None,
            confianza=None,
            hablante="SUPERADMIN",
        ),
        encargo=encargo,
    )


def test_ruido_o_saludo_no_arrastra_contexto_pendiente() -> None:
    previo = "35 m3 de 210 para escuela Miguel Rufrio"
    for msg in (
        "dictado: Hola, esta es una prueba de sonido.",
        "dictado: Gracias.",
        "dictado: ok",
    ):
        assert asistente_http._es_ruido_o_saludo(msg) is True
        assert (
            asistente_http._contexto_dictado(
                [], msg, texto_previo=previo, pendiente=True
            )
            is None
        )


def test_dictado_negocio_no_es_secuestrado_por_mixer() -> None:
    msg = (
        "dictado: A ver, me acaban de contratar 35 metros cubicos de hormigon 210 "
        "para una escuela 18 de noviembre y es para entregar este dia sabado "
        "crea al cliente, es nuevo cliente"
    )
    plano = asistente_http._plano(msg)
    es_dictado_negocio = asistente_http.cerebro_bridge.es_dictado(msg) and (
        "mixer" not in plano
        or any(k in plano for k in ("hormigon", "cliente", "cotizacion", "resistencia"))
    )
    assert es_dictado_negocio is True


def test_compilar_encargo_secundario_hereda_cliente_y_monto() -> None:
    hechos = [
        _hecho("cliente.nombre", "escuela Miguel Rufrio", encargo=1),
        _hecho("pago.monto", "1700", encargo=1),
        _hecho("pago.forma", "EFECTIVO", encargo=1),
        _hecho("pago.recibido", True, encargo=1),
        _hecho("traslado.cuenta_banco", "Banco Pichincha", encargo=2),
    ]
    borrador = compilar(
        hechos,
        Contexto(
            hoy=date(2026, 11, 24),
            sandbox=True,
            texto="escuela Miguel Rufrio 1700 efectivo. Llevo a la caja al banco",
        ),
    )
    claves_preguntas = {p.clave for p in borrador.preguntas}
    assert "cliente.nombre" not in claves_preguntas
    assert "traslado.monto" not in claves_preguntas

def test_reserva_conserva_pedido_y_solo_pide_hora() -> None:
    texto = "Contraté 24 m3 de hormigón 180 para Cliente Prueba en Obra Prueba el sábado. Reserva el mixer."
    hechos = [
        _hecho("cliente.nombre", "Cliente Prueba"),
        _hecho("cotizacion.volumen_m3", 24),
        _hecho("cotizacion.resistencia", "180"),
        _hecho("cotizacion.obra_direccion", "Obra Prueba"),
        _hecho("cotizacion.fecha_entrega", "2026-11-28", cita="el sábado"),
    ]
    from dataclasses import replace

    hechos[1] = replace(hechos[1], tipo="DECIMAL")
    hechos[4] = replace(hechos[4], tipo="FECHA")
    contexto = Contexto(hoy=date(2026, 11, 24), sandbox=True, texto=texto)
    pendiente = compilar(hechos, contexto)
    assert {p.clave for p in pendiente.preguntas} == {"cotizacion.hora_entrega"}
    hechos.append(replace(
        _hecho("cotizacion.hora_entrega", "10:00", cita="a las 10:00"), tipo="HORA"
    ))
    listo = compilar(hechos, contexto)
    assert not listo.preguntas
    assert [a.nombre for a in listo.acciones] == ["crear_cliente", "reservar_mixer"]
    reserva = listo.acciones[1]
    assert reserva.depende_de == listo.acciones[0].orden
    assert reserva.parametros["receta_codigo"] == "FC-180"
    assert reserva.parametros["fecha_entrega"] == date(2026, 11, 28)
    assert reserva.parametros["hora_inicio"] == "10:00"


@pytest.mark.asyncio
async def test_disponibilidad_indica_franja_con_capacidad(monkeypatch) -> None:
    from decimal import Decimal
    from app.agenda import service

    fecha = date(2026, 11, 28)

    class Base:
        async def fetchval(self, consulta):
            if "agenda.parametros" in consulta:
                return {"duracion_entrega_default_min": 60}
            return [{"codigo": "PRUEBA", "capacidad_m3": 8}]

    async def agenda_del_dia(self, desde, hasta):
        return [{
            "fecha_entrega": fecha.isoformat(), "hora_inicio": "10:00",
            "hora_fin_estimada": "11:00", "mixer_codigo": "PRUEBA",
            "estado": "RESERVA_CAMPO",
        }]

    monkeypatch.setattr(service.PostgresAgendaStore, "listar", agenda_del_dia)
    with pytest.raises(service.ReservaMixerInvalida, match="Hay cupo a las 11:00"):
        await service.plan_reserva_mixer(Base(), fecha=fecha, hora="10:00", volumen=Decimal("8"))
    with pytest.raises(service.ReservaMixerInvalida, match="Indica otra fecha"):
        await service.plan_reserva_mixer(Base(), fecha=fecha, hora="10:00", volumen=Decimal("9"))
    _, cargas = await service.plan_reserva_mixer(
        Base(), fecha=fecha, hora="11:00", volumen=Decimal("8")
    )
    assert [(unidad["codigo"], volumen) for unidad, volumen in cargas] == [("PRUEBA", Decimal("8"))]


def test_gato_consulta_resultado_y_pendientes_del_mismo_pedido() -> None:
    respuesta = asistente_http._estado_del_pedido({
        "ordenes_ejecutadas": [1],
        "acciones": [
            {"orden": 1, "accion_nombre": "crear_cliente", "parametros": {"nombre": "Cliente Prueba"}},
            {"orden": 2, "accion_nombre": "crear_tarea_recordatorio"},
        ],
        "preguntas": [{"texto": "¿Cuál es la dirección de obra?"}],
    })
    assert "Alta del cliente (Cliente Prueba): completado" in respuesta
    assert "Programación del recordatorio: pendiente" in respuesta
    assert "¿Cuál es la dirección de obra?" in respuesta
