"""Pruebas adversariales para porcentaje vs monto en USD y promoción de envío de cotización."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.cerebro.compilador import ClienteResuelto, Contexto, Receta, compilar
from app.cerebro.extractor import (
    _depurar_pago_porcentaje_y_negacion,
    _promover_envio_cotizacion_desde_tarea,
    construir_hechos,
)
from app.cerebro.hechos import Evidencia, HechoCitado
from app.cerebro.sobre import SobreIn
from app.voz import localizar_palabras, normalizar_con_mapa


def _hecho(clave: str, valor: object, *, tipo: str = "TEXTO", cita: str = "", encargo: int = 1) -> HechoCitado:
    return HechoCitado(
        clave=clave,
        valor=valor,
        estado="EXTRAIDO",
        tipo=tipo,
        evidencia=Evidencia(
            cita=cita or str(valor),
            sostiene=cita or str(valor),
            crudo_inicio=0,
            crudo_fin=len(cita or str(valor)),
            start_ms=None,
            end_ms=None,
            confianza=None,
            hablante="SUPERADMIN",
        ),
        encargo=encargo,
    )


def test_porcentaje_50_no_se_convierte_en_50_usd_y_pasa_a_anticipo_pct() -> None:
    texto = (
        "Corporación Favorita, 150 metros cúbicos de 210, con 10% de descuento, "
        "y el que tiene que depositar el 50%."
    )
    hechos = [
        _hecho("cliente.nombre", "Corporación Favorita", cita="Corporación Favorita"),
        _hecho("cotizacion.volumen_m3", 150, tipo="DECIMAL", cita="150 metros cúbicos"),
        _hecho("cotizacion.resistencia", 210, tipo="ENTERO", cita="210"),
        _hecho("cotizacion.descuento_pct", 10, tipo="ENTERO", cita="10% de descuento"),
        _hecho("pago.monto", 50, tipo="DECIMAL", cita="depositar el 50%"),
    ]
    notas = _depurar_pago_porcentaje_y_negacion(hechos, texto)

    assert not any(h.clave == "pago.monto" for h in hechos)
    anticipo = next(h for h in hechos if h.clave == "cotizacion.anticipo_pct")
    assert Decimal(str(anticipo.valor)) == Decimal("50")
    assert any("porcentaje de anticipo" in n for n in notas)


def test_negacion_explicita_de_50_dolares_retira_pago_monto_aunque_contexto_lo_traiga() -> None:
    texto = (
        "Corporación Favorita, 150 m3 de 210, 10% de descuento. "
        "no me han dado ningún 50 dólares nos van a dar el 50%"
    )
    hechos = [
        _hecho("cliente.nombre", "Corporación Favorita", cita="Corporación Favorita"),
        _hecho("cotizacion.volumen_m3", 150, tipo="DECIMAL", cita="150 m3"),
        _hecho("cotizacion.resistencia", 210, tipo="ENTERO", cita="210"),
        _hecho("pago.monto", 50, tipo="DECIMAL", cita="50"),
        _hecho("pago.recibido", False, tipo="BOOLEANO", cita="no me han dado"),
    ]
    notas = _depurar_pago_porcentaje_y_negacion(hechos, texto)

    assert not any(h.clave == "pago.monto" for h in hechos)
    assert any("niega los 50 USD" in n for n in notas)


def test_monto_real_en_dolares_y_porcentaje_coexisten_sin_romper_abono() -> None:
    texto = "Ya me dio 500 dólares y el resto 50% al entregar."
    hechos = [
        _hecho("pago.monto", 500, tipo="DECIMAL", cita="500 dólares"),
        _hecho("pago.recibido", True, tipo="BOOLEANO", cita="Ya me dio 500 dólares"),
        _hecho("pago.forma", "efectivo", cita="Ya me dio 500 dólares"),
    ]
    _depurar_pago_porcentaje_y_negacion(hechos, texto)

    monto = next(h for h in hechos if h.clave == "pago.monto")
    assert Decimal(str(monto.valor)) == Decimal("500")


def test_descuento_porcentaje_no_se_duplica_como_anticipo_si_llm_lo_confundio() -> None:
    texto = "150 m3 de 210 con el 10% de descuento."
    hechos = [
        _hecho("cotizacion.descuento_pct", 10, tipo="ENTERO", cita="10% de descuento"),
        _hecho("pago.monto", 10, tipo="DECIMAL", cita="10%"),
    ]
    _depurar_pago_porcentaje_y_negacion(hechos, texto)

    assert not any(h.clave == "pago.monto" for h in hechos)
    assert not any(h.clave == "cotizacion.anticipo_pct" for h in hechos)


def test_envio_monto_total_por_whatsapp_se_promueve_a_cotizacion_enviar() -> None:
    texto = (
        "Corporación Favorita, 150 m3 de 210, descuento 10%, en Juan José Peña y Mercadillo, "
        "enviar una notificación vía whatsapp al 0963410409 indicándole la totalidad del monto "
        "y que tiene que depositar el 50%."
    )
    hechos = [
        _hecho("cliente.nombre", "Corporación Favorita", cita="Corporación Favorita"),
        _hecho("cotizacion.volumen_m3", 150, tipo="DECIMAL", cita="150 m3"),
        _hecho("cotizacion.resistencia", 210, tipo="ENTERO", cita="210"),
        _hecho("cotizacion.descuento_pct", 10, tipo="ENTERO", cita="descuento 10%"),
        _hecho("cotizacion.obra_direccion", "Juan José Peña y Mercadillo", cita="Juan José Peña y Mercadillo"),
        _hecho("tarea.telefono", "0963410409", tipo="TELEFONO", cita="0963410409"),
        _hecho(
            "tarea.mensaje",
            "indicándole la totalidad del monto y que tiene que depositar el 50%",
            cita="indicándole la totalidad del monto",
        ),
        _hecho("pago.monto", 50, tipo="DECIMAL", cita="depositar el 50%"),
    ]
    _depurar_pago_porcentaje_y_negacion(hechos, texto)
    _promover_envio_cotizacion_desde_tarea(hechos, texto)

    assert not any(h.clave.startswith("tarea.") for h in hechos)
    assert not any(h.clave == "pago.monto" for h in hechos)
    assert any(h.clave == "cotizacion.enviar" and h.valor is True for h in hechos)
    assert any(h.clave == "cotizacion.enviar_destinatario" and h.valor == "0963410409" for h in hechos)


def test_cincuenta_por_ciento_en_palabras_no_se_vuelve_50_usd() -> None:
    texto = "Corporación Favorita, 150 m3 de 210, depositar el cincuenta por ciento."
    mapa = normalizar_con_mapa(texto)
    palabras = localizar_palabras(texto, [])
    sobre = SobreIn.model_validate(
        {
            "intencion": "MUTACION",
            "hechos": [
                {"clave": "cliente.nombre", "valor": "Corporación Favorita", "tipo": "TEXTO", "estado": "EXTRAIDO", "cita": "Corporación Favorita", "encargo": 1},
                {"clave": "cotizacion.volumen_m3", "valor": 150, "tipo": "DECIMAL", "estado": "EXTRAIDO", "cita": "150 m3", "encargo": 1},
                {"clave": "cotizacion.resistencia", "valor": 210, "tipo": "ENTERO", "estado": "EXTRAIDO", "cita": "210", "encargo": 1},
                {"clave": "pago.monto", "valor": 50, "tipo": "DECIMAL", "estado": "EXTRAIDO", "cita": "50", "encargo": 1},
            ],
        }
    )
    hechos, _ = construir_hechos(sobre, texto_crudo=texto, mapa=mapa, palabras=palabras)
    assert not any(h.clave == "pago.monto" for h in hechos)
    assert any(h.clave == "cotizacion.anticipo_pct" and Decimal(str(h.valor)) == Decimal("50") for h in hechos)


def test_dos_encargos_uno_con_50_usd_y_otro_con_50_por_ciento_no_se_contaminan() -> None:
    texto = (
        "Primero, Juan ya me dio 50 dólares de saldo. "
        "Segundo, Corporación Favorita quiere 150 m3 de 210 y va a depositar el 50%."
    )
    hechos = [
        _hecho("cliente.nombre", "Juan", cita="Juan", encargo=1),
        _hecho("pago.monto", 50, tipo="DECIMAL", cita="50 dólares", encargo=1),
        _hecho("pago.recibido", True, tipo="BOOLEANO", cita="ya me dio", encargo=1),
        _hecho("cliente.nombre", "Corporación Favorita", cita="Corporación Favorita", encargo=2),
        _hecho("cotizacion.volumen_m3", 150, tipo="DECIMAL", cita="150 m3", encargo=2),
        _hecho("cotizacion.resistencia", 210, tipo="ENTERO", cita="210", encargo=2),
        _hecho("pago.monto", 50, tipo="DECIMAL", cita="depositar el 50%", encargo=2),
    ]
    _depurar_pago_porcentaje_y_negacion(hechos, texto)
    montos = [h for h in hechos if h.clave == "pago.monto"]
    assert len(montos) == 1
    assert montos[0].encargo == 1
    assert any(h.clave == "cotizacion.anticipo_pct" and h.encargo == 2 for h in hechos)


def test_envio_con_bancos_conserva_bancos_y_no_deja_tarea_destinatario_huerfana() -> None:
    texto = (
        "Corporación Favorita, 150 m3 de 210. "
        "Envíale por WhatsApp al 0963410409 preguntando a qué cuenta quiere transferir, "
        "tenemos Banco de Pichincha, Guayaquil e Internacional."
    )
    hechos = [
        _hecho("cliente.nombre", "Corporación Favorita", cita="Corporación Favorita"),
        _hecho("cotizacion.volumen_m3", 150, tipo="DECIMAL", cita="150 m3"),
        _hecho("cotizacion.resistencia", 210, tipo="ENTERO", cita="210"),
        _hecho("tarea.destinatario", "cliente", cita="Envíale"),
        _hecho("tarea.telefono", "0963410409", tipo="TELEFONO", cita="0963410409"),
        _hecho(
            "tarea.mensaje",
            "preguntando a qué cuenta quiere transferir, tenemos Banco de Pichincha, Guayaquil e Internacional",
            cita="preguntando a qué cuenta quiere transferir, tenemos Banco de Pichincha, Guayaquil e Internacional",
        ),
    ]
    _promover_envio_cotizacion_desde_tarea(hechos, texto)
    assert not any(h.clave.startswith("tarea.") for h in hechos)
    nota = next(h for h in hechos if h.clave == "cotizacion.nota")
    assert "Pichincha" in str(nota.valor)
    assert "Guayaquil" in str(nota.valor)
    assert "Internacional" in str(nota.valor)


    borrador = compilar(
        hechos,
        Contexto(
            hoy=date(2026, 11, 24),
            sandbox=True,
            rol_actor="SUPERADMIN",
            texto=texto,
            cliente=ClienteResuelto(id="11111111-1111-1111-1111-111111111111", nombre="Corporación Favorita"),
            receta=Receta(resistencia="210", precio_m3=Decimal("110"), precio_estado="OFICIAL"),
        ),
        intencion="MUTACION",
    )
    nombres = [a.nombre for a in borrador.acciones]
    assert "crear_cotizacion_borrador" in nombres
    assert "enviar_cotizacion_whatsapp" in nombres
    assert "crear_tarea_recordatorio" not in nombres
    assert "registrar_abono_cliente" not in nombres
    envio = next(a for a in borrador.acciones if a.nombre == "enviar_cotizacion_whatsapp")
    assert envio.parametros["destinatario_telefono"] == "0963410409"
    cot = next(a for a in borrador.acciones if a.nombre == "crear_cotizacion_borrador")
    assert "50%" in str(cot.parametros.get("notas") or "")


def test_recordatorio_operativo_al_maestro_en_cotizacion_no_se_promueve_a_envio() -> None:
    texto = (
        "Cliente Juan Pérez, 80 m3 de 240 en la vía a Catamayo. "
        "Mándale un aviso al maestro al 0991112222 que limpie la vía antes de las 7."
    )
    hechos = [
        _hecho("cliente.nombre", "Juan Pérez", cita="Juan Pérez"),
        _hecho("cotizacion.volumen_m3", 80, tipo="DECIMAL", cita="80 m3"),
        _hecho("cotizacion.resistencia", 240, tipo="ENTERO", cita="240"),
        _hecho("cotizacion.obra_direccion", "vía a Catamayo", cita="vía a Catamayo"),
        _hecho("tarea.telefono", "0991112222", tipo="TELEFONO", cita="0991112222"),
        _hecho("tarea.mensaje", "limpie la vía antes de las 7", cita="limpie la vía antes de las 7"),
    ]
    _promover_envio_cotizacion_desde_tarea(hechos, texto)

    assert any(h.clave == "tarea.telefono" for h in hechos)
    assert any(h.clave == "tarea.mensaje" for h in hechos)
    assert not any(h.clave == "cotizacion.enviar" for h in hechos)


def test_construir_hechos_end_to_end_sobre_dictado_real_de_julio() -> None:
    texto = (
        "Corporación Favorita. 150 metros cúbicos de hormigón de 210, descuento del 10%, "
        "en Juan José Peña y Mercadillo. No me han dado ningún 50 dólares, nos van a dar el 50% "
        "por transferencia y envíale por WhatsApp al 0963410409 indicándole la totalidad del monto."
    )
    mapa = normalizar_con_mapa(texto)
    palabras = localizar_palabras(texto, [])
    sobre = SobreIn.model_validate(
        {
            "intencion": "MUTACION",
            "hechos": [
                {"clave": "cliente.nombre", "valor": "Corporación Favorita", "tipo": "TEXTO", "estado": "EXTRAIDO", "cita": "Corporación Favorita", "encargo": 1},
                {"clave": "cotizacion.volumen_m3", "valor": 150, "tipo": "DECIMAL", "estado": "EXTRAIDO", "cita": "150 metros cúbicos", "encargo": 1},
                {"clave": "cotizacion.resistencia", "valor": 210, "tipo": "ENTERO", "estado": "EXTRAIDO", "cita": "210", "encargo": 1},
                {"clave": "cotizacion.descuento_pct", "valor": 10, "tipo": "ENTERO", "estado": "EXTRAIDO", "cita": "descuento del 10%", "encargo": 1},
                {"clave": "cotizacion.obra_direccion", "valor": "Juan José Peña y Mercadillo", "tipo": "TEXTO", "estado": "EXTRAIDO", "cita": "Juan José Peña y Mercadillo", "encargo": 1},
                {"clave": "pago.monto", "valor": 50, "tipo": "DECIMAL", "estado": "EXTRAIDO", "cita": "50", "encargo": 1},
                {"clave": "pago.recibido", "valor": False, "tipo": "BOOLEANO", "estado": "EXTRAIDO", "cita": "No me han dado", "encargo": 1},
                {"clave": "tarea.telefono", "valor": "0963410409", "tipo": "TELEFONO", "estado": "EXTRAIDO", "cita": "0963410409", "encargo": 1},
                {"clave": "tarea.mensaje", "valor": "indicándole la totalidad del monto", "tipo": "TEXTO", "estado": "EXTRAIDO", "cita": "indicándole la totalidad del monto", "encargo": 1},
            ],
        }
    )
    hechos, _ = construir_hechos(sobre, texto_crudo=texto, mapa=mapa, palabras=palabras)

    assert not any(h.clave == "pago.monto" for h in hechos)
    assert not any(h.clave.startswith("tarea.") for h in hechos)
    assert any(h.clave == "cotizacion.enviar" and h.valor is True for h in hechos)
    assert any(h.clave == "cotizacion.enviar_destinatario" and h.valor == "0963410409" for h in hechos)


def test_cincuenta_por_ciento_en_palabras_no_se_vuelve_50_usd() -> None:
    texto = "Corporación Favorita, 150 m3 de 210, depositar el cincuenta por ciento."
    mapa = normalizar_con_mapa(texto)
    palabras = localizar_palabras(texto, [])
    sobre = SobreIn.model_validate(
        {
            "intencion": "MUTACION",
            "hechos": [
                {"clave": "cliente.nombre", "valor": "Corporación Favorita", "tipo": "TEXTO", "estado": "EXTRAIDO", "cita": "Corporación Favorita", "encargo": 1},
                {"clave": "cotizacion.volumen_m3", "valor": 150, "tipo": "DECIMAL", "estado": "EXTRAIDO", "cita": "150 m3", "encargo": 1},
                {"clave": "cotizacion.resistencia", "valor": 210, "tipo": "ENTERO", "estado": "EXTRAIDO", "cita": "210", "encargo": 1},
                {"clave": "pago.monto", "valor": 50, "tipo": "DECIMAL", "estado": "EXTRAIDO", "cita": "50", "encargo": 1},
            ],
        }
    )
    hechos, _ = construir_hechos(sobre, texto_crudo=texto, mapa=mapa, palabras=palabras)
    assert not any(h.clave == "pago.monto" for h in hechos)
    assert any(h.clave == "cotizacion.anticipo_pct" and Decimal(str(h.valor)) == Decimal("50") for h in hechos)


def test_dos_encargos_uno_con_50_usd_y_otro_con_50_por_ciento_no_se_contaminan() -> None:
    texto = (
        "Primero, Juan ya me dio 50 dólares de saldo. "
        "Segundo, Corporación Favorita quiere 150 m3 de 210 y va a depositar el 50%."
    )
    hechos = [
        _hecho("cliente.nombre", "Juan", cita="Juan", encargo=1),
        _hecho("pago.monto", 50, tipo="DECIMAL", cita="50 dólares", encargo=1),
        _hecho("pago.recibido", True, tipo="BOOLEANO", cita="ya me dio", encargo=1),
        _hecho("cliente.nombre", "Corporación Favorita", cita="Corporación Favorita", encargo=2),
        _hecho("cotizacion.volumen_m3", 150, tipo="DECIMAL", cita="150 m3", encargo=2),
        _hecho("cotizacion.resistencia", 210, tipo="ENTERO", cita="210", encargo=2),
        _hecho("pago.monto", 50, tipo="DECIMAL", cita="depositar el 50%", encargo=2),
    ]
    _depurar_pago_porcentaje_y_negacion(hechos, texto)
    montos = [h for h in hechos if h.clave == "pago.monto"]
    assert len(montos) == 1
    assert montos[0].encargo == 1
    assert any(h.clave == "cotizacion.anticipo_pct" and h.encargo == 2 for h in hechos)


def test_envio_con_bancos_conserva_bancos_y_no_deja_tarea_destinatario_huerfana() -> None:
    texto = (
        "Corporación Favorita, 150 m3 de 210. "
        "Envíale por WhatsApp al 0963410409 preguntando a qué cuenta quiere transferir, "
        "tenemos Banco de Pichincha, Guayaquil e Internacional."
    )
    hechos = [
        _hecho("cliente.nombre", "Corporación Favorita", cita="Corporación Favorita"),
        _hecho("cotizacion.volumen_m3", 150, tipo="DECIMAL", cita="150 m3"),
        _hecho("cotizacion.resistencia", 210, tipo="ENTERO", cita="210"),
        _hecho("tarea.destinatario", "cliente", cita="Envíale"),
        _hecho("tarea.telefono", "0963410409", tipo="TELEFONO", cita="0963410409"),
        _hecho(
            "tarea.mensaje",
            "preguntando a qué cuenta quiere transferir, tenemos Banco de Pichincha, Guayaquil e Internacional",
            cita="preguntando a qué cuenta quiere transferir, tenemos Banco de Pichincha, Guayaquil e Internacional",
        ),
    ]
    _promover_envio_cotizacion_desde_tarea(hechos, texto)
    assert not any(h.clave.startswith("tarea.") for h in hechos)
    nota = next(h for h in hechos if h.clave == "cotizacion.nota")
    assert "Pichincha" in str(nota.valor)
    assert "Guayaquil" in str(nota.valor)
    assert "Internacional" in str(nota.valor)

