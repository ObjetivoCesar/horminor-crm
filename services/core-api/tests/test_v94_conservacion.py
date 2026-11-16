"""Conservación de instrucciones: lo dictado no se pierde al compilar.

Caso de regresión real (2026-11-16): un audio espontáneo de Julio con anticipo,
pedido, contacto, una rectificación («la cotización, no la cotización, el
recordatorio del pago»), la condición de entregar contra pago, un plazo de dos
meses y un encargo al expediente. El compilador conservaba los datos pero
perdía el plazo, la condición y el expediente porque no cabían en la acción de
cotización (que no se pudo armar sin la dirección de obra).

Estas pruebas no llaman al LLM: parten de los hechos citados que el extractor
dejó en la base y verifican la matriz
dictado → hechos → resumen → acciones y condiciones.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.cerebro import (
    Condicion,
    Contexto,
    Evidencia,
    HechoCitado,
    Receta,
    compilar,
    mensaje_es_final,
)
from app.cerebro.extractor import _degradar_pago_no_declarado
from app.cerebro.router import validar_confirmacion_recordatorio

TEXTO = (
    "A ver, necesito registrar un anticipo de 17000 USD de la empresa eléctrica "
    "de El Coca, que nos acaban de contratar 250 m3 de hormigón de 240. Nos "
    "tenemos que poner en contacto con un ingeniero Julio Cartuche, con número "
    "de teléfono 0963444666. Hay que pasarle por WhatsApp la cotización, no la "
    "cotización, el recordatorio del pago que tiene que hacernos. Contra "
    "entrega de ese pago, nosotros podemos hacer la entrega ya del hormigón. "
    "Nos han dado un plazo de 2 meses para entregar todo el hormigón. según las "
    "especificaciones de la constructora. Entonces también tenemos que añadir "
    "ese expediente."
)


def hecho(
    clave: str,
    valor,
    tipo: str = "TEXTO",
    *,
    cita: str | None = None,
    estado: str = "EXTRAIDO",
) -> HechoCitado:
    texto = cita if cita is not None else str(valor)
    return HechoCitado(
        clave=clave,
        valor=valor,
        estado=estado,
        tipo=tipo,
        evidencia=Evidencia(
            cita=texto,
            sostiene=str(valor),
            crudo_inicio=0,
            crudo_fin=len(texto),
            start_ms=0,
            end_ms=1000,
            confianza=0.94,
            hablante="SUPERADMIN",
        ),
    )


def hechos_del_caso() -> list[HechoCitado]:
    """Los 13 hechos que el extractor guardó para el dictado del 2026-11-16."""
    return [
        hecho("pago.monto", 17000, "DECIMAL", cita="un anticipo de 17 mil dólares"),
        hecho(
            "cliente.nombre",
            "empresa eléctrica de El Coca",
            cita="de la empresa eléctrica de El Coca",
        ),
        hecho("cliente.ciudad", "El Coca", cita="del COCA,"),
        hecho("cotizacion.volumen_m3", 250, "DECIMAL", cita="250 metros cúbicos"),
        hecho("cotizacion.resistencia", 240, "ENTERO", cita="hormigón de 240."),
        hecho("contacto.nombre", "Julio Cartuche", cita="ingeniero Julio Cartuche,"),
        hecho("contacto.rol", "ingeniero", cita="un ingeniero Julio Cartuche"),
        hecho("contacto.telefono", "0963444666", "TELEFONO", cita="0963-444-666."),
        hecho(
            "tarea.destinatario",
            "Julio Cartuche",
            cita="Hay que pasarle por WhatsApp",
        ),
        hecho("tarea.telefono", "0963444666", "TELEFONO", cita="0963-444-666."),
        hecho(
            "tarea.mensaje",
            "recordatorio del pago que tiene que hacernos",
            cita="el recordatorio del pago que tiene que hacernos",
        ),
        hecho(
            "cotizacion.plazo_entrega",
            "dos meses",
            cita="un plazo de dos meses",
        ),
        hecho(
            "pago.recibido",
            False,
            "BOOLEANO",
            cita="el recordatorio del pago que tiene que hacernos",
            estado="INFERIDO",
        ),
    ]


def contexto() -> Contexto:
    return Contexto(
        hoy=date(2026, 11, 16),
        sandbox=True,
        cliente=None,
        receta=Receta(
            resistencia="FC-240",
            precio_m3=Decimal("120"),
            precio_estado="PROVISIONAL",
        ),
        rol_actor="SUPERADMIN",
        texto=TEXTO,
    )


def test_el_plazo_no_se_pierde_aunque_la_cotizacion_no_se_pueda_armar() -> None:
    borrador = compilar(hechos_del_caso(), contexto())

    # Sin dirección de obra no hay acción de cotización...
    assert not any(
        accion.nombre == "crear_cotizacion_borrador" for accion in borrador.acciones
    )
    # ...pero el plazo sigue visible como condición del encargo.
    plazo = next(c for c in borrador.condiciones if c.clave == "entrega.plazo")
    assert "dos meses" in plazo.texto
    assert plazo.estado == "POR_ACLARAR"
    assert plazo.cita == "un plazo de dos meses"


def test_la_entrega_contra_pago_se_conserva_sin_autorizar_despacho() -> None:
    borrador = compilar(hechos_del_caso(), contexto())

    condicion = next(
        c for c in borrador.condiciones if c.clave == "entrega.contra_pago"
    )
    assert condicion.estado == "VIGENTE"
    assert "condicionada a la recepción del pago" in condicion.texto
    assert "No autoriza despachar" in condicion.texto
    # Conservar la condición no crea ninguna acción de envío ni de despacho.
    assert not any(
        accion.nombre in ("enviar_cotizacion_whatsapp", "despachar")
        for accion in borrador.acciones
    )


def test_el_encargo_al_expediente_queda_como_tarea_interna() -> None:
    borrador = compilar(hechos_del_caso(), contexto())

    condicion = next(
        c for c in borrador.condiciones if c.clave == "expediente.completar"
    )
    assert condicion.estado == "POR_ACLARAR"
    assert "Falta verificar" in condicion.texto

    interna = next(
        a for a in borrador.acciones if a.nombre == "crear_tarea_interna"
    )
    assert interna.parametros["asignado_rol"] == "SECRETARIA"
    # La instrucción se copia de la cita; no se inventa un documento recibido.
    assert "expediente" in interna.parametros["instruccion"].lower()
    assert interna.parametros["ficha"]["nota"] == condicion.texto


def test_el_recordatorio_no_hereda_la_frase_dictada_como_mensaje_final() -> None:
    borrador = compilar(hechos_del_caso(), contexto())

    tarea = next(
        a for a in borrador.acciones if a.nombre == "crear_tarea_recordatorio"
    )
    assert tarea.parametros["instruccion"] == (
        "recordatorio del pago que tiene que hacernos"
    )
    assert tarea.parametros["mensaje"] is None
    assert tarea.parametros["mensaje_por_confirmar"] is True
    # Sin hora dictada, el envío inmediato está marcado como inferido.
    assert tarea.parametros["cuando"] == "ahora"
    assert tarea.parametros["programado_inferido"] is True


def test_el_resumen_conserva_plazo_condicion_y_expediente() -> None:
    from app.cerebro.revision import resumen_legible

    borrador = compilar(hechos_del_caso(), contexto())
    resumen = resumen_legible(
        borrador.hechos, texto=TEXTO, condiciones=borrador.condiciones
    )

    assert "250 m3 de 240" in resumen
    assert "plazo de dos meses" in resumen
    assert "condicionada a la recepción del pago" in resumen
    assert "expediente" in resumen
    # El anticipo no se declara recibido ni se declara perdido.
    assert "sin ingreso confirmado" in resumen
    assert "que ya entró" not in resumen


def test_matriz_de_conservacion_dictado_hechos_acciones() -> None:
    """Cada instrucción relevante aparece en algún lado del borrador."""
    borrador = compilar(hechos_del_caso(), contexto())
    claves_hechos = {h.clave for h in borrador.hechos}
    claves_condiciones = {c.clave for c in borrador.condiciones}
    nombres_acciones = {a.nombre for a in borrador.acciones}
    claves_preguntas = {p.clave for p in borrador.preguntas}

    matriz = {
        "anticipo 17000 USD": "pago.monto" in claves_hechos,
        "empresa eléctrica de El Coca": "cliente.nombre" in claves_hechos,
        "250 m3 FC-240": {
            "cotizacion.volumen_m3",
            "cotizacion.resistencia",
        }.issubset(claves_hechos),
        "contacto Julio Cartuche": "contacto.telefono" in claves_hechos,
        "recordatorio (no cotización)": "crear_tarea_recordatorio" in nombres_acciones,
        "entrega contra pago": "entrega.contra_pago" in claves_condiciones,
        "plazo de dos meses": "entrega.plazo" in claves_condiciones,
        "expediente de la constructora": (
            "expediente.completar" in claves_condiciones
            and "crear_tarea_interna" in nombres_acciones
        ),
        "dirección de obra (faltante)": "cotizacion.obra_direccion" in claves_preguntas,
        "texto del mensaje (faltante)": "tarea.mensaje" in claves_preguntas,
    }
    perdidas = [nombre for nombre, presente in matriz.items() if not presente]
    assert not perdidas, f"instrucciones perdidas: {perdidas}"


def test_condiciones_deterministicas_sin_hechos_del_llm() -> None:
    """Aunque el modelo no extraiga nada, el texto sostiene las condiciones."""
    borrador = compilar([], contexto())

    claves = {c.clave for c in borrador.condiciones}
    assert {"entrega.plazo", "entrega.contra_pago", "expediente.completar"} <= claves
    for condicion in borrador.condiciones:
        assert isinstance(condicion, Condicion)
        assert condicion.cita


def test_mensaje_directo_si_se_puede_enviar_tal_cual() -> None:
    assert mensaje_es_final(
        "dile que por favor nos envie el comprobante",
        "por favor nos envie el comprobante de la transferencia",
    )
    assert not mensaje_es_final(
        "hay que pasarle el recordatorio del pago que tiene que hacernos",
        "recordatorio del pago que tiene que hacernos",
    )


def test_pago_no_recibido_sin_negacion_explicita_queda_inferido() -> None:
    hechos = [
        hecho(
            "pago.recibido",
            False,
            "BOOLEANO",
            cita="el recordatorio del pago que tiene que hacernos",
        )
    ]

    notas = _degradar_pago_no_declarado(hechos, TEXTO)

    assert hechos[0].estado == "INFERIDO"
    assert notas and "sin ingreso confirmado" in notas[0]


def test_pago_no_recibido_declarado_se_respeta() -> None:
    hechos = [
        hecho("pago.recibido", False, "BOOLEANO", cita="todavia no nos ha pagado")
    ]

    notas = _degradar_pago_no_declarado(hechos, "todavia no nos ha pagado nada")

    assert hechos[0].estado == "EXTRAIDO"
    assert notas == []


def test_el_plazo_sobrevive_a_la_normalizacion_de_los_numeros() -> None:
    """«dos meses» se normaliza a «2 meses»; la cita cruda sigue sosteniéndolo."""
    from app.cerebro import validar_hecho

    plazo = HechoCitado(
        clave="cotizacion.plazo_entrega",
        valor="dos meses",
        estado="EXTRAIDO",
        tipo="TEXTO",
        evidencia=Evidencia(
            cita="un plazo de dos meses",
            sostiene="un plazo de 2 meses",
            crudo_inicio=0,
            crudo_fin=len("un plazo de dos meses"),
            start_ms=0,
            end_ms=1000,
            confianza=0.9,
            hablante="SUPERADMIN",
        ),
    )

    assert validar_hecho(plazo) == []


# ---------------------------------------------------------------------------
# Confirmación: sin texto autorizado ni momento, no se programa
# ---------------------------------------------------------------------------
def _parametros_recordatorio() -> dict:
    return {
        "destinatario": "0963444666",
        "mensaje": None,
        "instruccion": "recordatorio del pago que tiene que hacernos",
        "mensaje_por_confirmar": True,
        "cuando": "ahora",
        "programado_inferido": True,
        "adjuntar_factura": False,
    }


def test_confirmar_sin_mensaje_final_no_programa() -> None:
    with pytest.raises(HTTPException) as error:
        validar_confirmacion_recordatorio(
            _parametros_recordatorio(),
            mensaje_final="   ",
            enviar_ahora=True,
            actor_id="actor-1",
        )

    assert error.value.status_code == 422
    assert error.value.detail["code"] == "MENSAJE_POR_CONFIRMAR"


def test_confirmar_sin_aceptar_envio_inmediato_no_programa() -> None:
    with pytest.raises(HTTPException) as error:
        validar_confirmacion_recordatorio(
            _parametros_recordatorio(),
            mensaje_final="Ingeniero, le recuerdo el anticipo pendiente.",
            enviar_ahora=False,
            actor_id="actor-1",
        )

    assert error.value.status_code == 422
    assert error.value.detail["code"] == "CONFIRMAR_ENVIO_INMEDIATO"


def test_confirmar_con_mensaje_y_momento_autoriza() -> None:
    parametros = validar_confirmacion_recordatorio(
        _parametros_recordatorio(),
        mensaje_final="  Ingeniero,   le recuerdo el anticipo pendiente. ",
        enviar_ahora=True,
        actor_id="actor-1",
    )

    assert parametros["mensaje"] == "Ingeniero, le recuerdo el anticipo pendiente."
    assert parametros["mensaje_por_confirmar"] is False
    assert parametros["mensaje_autorizado_por"] == "actor-1"
    assert parametros["instruccion"] == (
        "recordatorio del pago que tiene que hacernos"
    )


def test_recordatorio_con_mensaje_y_hora_dictados_no_pide_nada() -> None:
    hechos = hechos_del_caso()
    hechos = [
        h
        for h in hechos
        if h.clave not in ("tarea.mensaje",)
    ]
    hechos.append(
        hecho(
            "tarea.mensaje",
            "por favor nos envie el comprobante de la transferencia",
            cita="dile que por favor nos envie el comprobante",
        )
    )
    hechos.append(hecho("tarea.cuando", "a las 18:00", cita="a las 18:00"))

    borrador = compilar(hechos, contexto())
    tarea = next(
        a for a in borrador.acciones if a.nombre == "crear_tarea_recordatorio"
    )

    assert tarea.parametros["mensaje_por_confirmar"] is False
    assert tarea.parametros["programado_inferido"] is False
    assert tarea.parametros["mensaje"].startswith("por favor nos envie")
