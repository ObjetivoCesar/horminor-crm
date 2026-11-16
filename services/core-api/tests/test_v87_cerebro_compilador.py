"""Compilador del Cerebro: hechos citados → acciones con invariantes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.cerebro import (
    ClienteResuelto,
    Contexto,
    Evidencia,
    HechoCitado,
    Receta,
    acciones_permitidas,
    compilar,
    normalizar_resistencia,
    validar_hecho,
)


def hecho(
    clave: str,
    valor,
    tipo: str = "TEXTO",
    *,
    sostiene: str | None = None,
    cita: str | None = None,
    hablante: str = "SUPERADMIN",
    checksum: bool | None = None,
    estado: str = "EXTRAIDO",
) -> HechoCitado:
    texto = cita if cita is not None else str(valor)
    evidencia = Evidencia(
        cita=texto,
        sostiene=sostiene if sostiene is not None else str(valor),
        crudo_inicio=0,
        crudo_fin=len(texto),
        start_ms=0,
        end_ms=1000,
        confianza=0.95,
        hablante=hablante,
    )
    return HechoCitado(
        clave=clave,
        valor=valor,
        estado=estado,
        tipo=tipo,
        evidencia=evidencia,
        checksum_valido=checksum,
    )


def _receta() -> Receta:
    return Receta(
        resistencia="FC-210",
        precio_m3=Decimal("118"),
        precio_estado="PROVISIONAL",
    )


def _contexto(**extra) -> Contexto:
    base = {
        "hoy": date(2026, 11, 14),
        "sandbox": True,
        "cliente": None,
        "receta": _receta(),
        "rol_actor": "SUPERADMIN",
    }
    base.update(extra)
    return Contexto(**base)


def _hechos_caso_a(*, cedula: str = "1710034065", checksum: bool = True):
    return [
        hecho("cliente.nombre", "Jorge Bailon"),
        hecho("cliente.cedula", cedula, "CEDULA", checksum=checksum),
        hecho("cliente.telefono", "0965555555", "TELEFONO"),
        hecho("cliente.referencia", "a la vuelta del estadio"),
        hecho("cotizacion.volumen_m3", 25, "ENTERO", sostiene="25"),
        hecho("cotizacion.fecha_entrega", date(2026, 11, 21), "FECHA"),
        hecho("pago.monto", Decimal("1000"), "DECIMAL", sostiene="1000",
              cita="ya me acaba de dar 1000 dolares de abono en efectivo"),
        hecho("pago.forma", "EFECTIVO",
              cita="ya me acaba de dar 1000 dolares de abono en efectivo"),
        hecho("cotizacion.enviar", True, "BOOLEANO"),
    ]


# ---------------------------------------------------------------------------
# Caso A
# ---------------------------------------------------------------------------
def test_caso_a_propone_cuatro_acciones_en_orden() -> None:
    borrador = compilar(_hechos_caso_a(), _contexto())

    assert borrador.estado == "PENDIENTE_CONFIRMACION"
    assert [a.nombre for a in borrador.acciones] == [
        "crear_cliente",
        "crear_cotizacion_borrador",
        "registrar_abono_cliente",
        "enviar_cotizacion_whatsapp",
    ]
    assert borrador.acciones[1].depende_de == 1
    assert borrador.acciones[2].depende_de == 1
    assert borrador.acciones[3].depende_de == 2


def test_caso_a_usa_la_referencia_como_obra_y_la_receta_como_precio() -> None:
    borrador = compilar(_hechos_caso_a(), _contexto())
    cotizacion = borrador.acciones[1].parametros

    assert cotizacion["obra_direccion"] == "a la vuelta del estadio"
    assert cotizacion["resistencia"] == "FC-210"
    assert cotizacion["precio_m3"] == Decimal("118")
    assert cotizacion["precio_estado"] == "PROVISIONAL"
    assert cotizacion["volumen_m3"] == Decimal("25")


def test_caso_a_el_abono_exige_doble_confirmacion() -> None:
    borrador = compilar(_hechos_caso_a(), _contexto())
    abono = borrador.acciones[2]
    assert abono.requiere_doble_confirmacion is True
    assert abono.parametros["monto_usd"] == Decimal("1000")


def test_cedula_con_verificador_invalido_pregunta_y_bloquea() -> None:
    hechos = _hechos_caso_a(cedula="1102561531", checksum=False)
    borrador = compilar(hechos, _contexto())

    assert borrador.estado == "REQUIERE_ACLARACION"
    assert any(p.clave == "cliente.cedula" for p in borrador.preguntas)


def test_forma_de_pago_invalida_no_se_propaga_y_se_pregunta() -> None:
    """«de abono» no es un método de pago: el abono va a caja en efectivo o
    transferencia. Se pregunta en vez de inventar el método."""
    hechos = [h for h in _hechos_caso_a() if h.clave != "pago.forma"]
    hechos.append(hecho("pago.forma", "abono", cita="de abono"))
    borrador = compilar(hechos, _contexto())

    abono = next(a for a in borrador.acciones if a.nombre == "registrar_abono_cliente")
    assert abono.parametros["forma_pago"] == "POR_DEFINIR"
    assert borrador.estado == "REQUIERE_ACLARACION"
    assert borrador.preguntas[0].clave == "pago.forma"


def test_forma_de_pago_del_abono_no_es_condicion_de_la_cotizacion() -> None:
    hechos = [h for h in _hechos_caso_a() if h.clave != "pago.forma"]
    hechos.append(hecho("pago.forma", "TRANSFERENCIA"))
    borrador = compilar(hechos, _contexto())

    cotizacion = next(a for a in borrador.acciones if a.nombre == "crear_cotizacion_borrador")
    assert cotizacion.parametros["forma_pago"] == "POR_DEFINIR"


def test_precio_provisional_bloquea_envio_fuera_de_sandbox() -> None:
    borrador = compilar(_hechos_caso_a(), _contexto(sandbox=False))
    envio = next(a for a in borrador.acciones if a.nombre == "enviar_cotizacion_whatsapp")

    assert envio.bloqueada_por == "PRECIO_PROVISIONAL"
    assert any(p.clave == "cotizacion.precio_estado" for p in borrador.preguntas)


def test_precio_dictado_por_otro_rol_no_se_usa() -> None:
    hechos = _hechos_caso_a() + [
        hecho(
            "cotizacion.precio_m3",
            Decimal("90"),
            "DECIMAL",
            sostiene="90",
            hablante="SECRETARIA",
        )
    ]
    borrador = compilar(hechos, _contexto())
    cotizacion = borrador.acciones[1].parametros

    assert cotizacion["precio_m3"] == Decimal("118")
    assert any(p.clave == "cotizacion.precio_m3" for p in borrador.preguntas)


# ---------------------------------------------------------------------------
# Caso B
# ---------------------------------------------------------------------------
def _hechos_caso_b():
    return [
        hecho("pago.monto", Decimal("12000"), "DECIMAL", sostiene="12000",
              cita="ya me deposito 12000 dolares en efectivo"),
        hecho("pago.forma", "EFECTIVO",
              cita="ya me deposito 12000 dolares en efectivo"),
        hecho("traslado.cuenta_banco", "PICHINCHA"),
    ]


def test_caso_b_son_dos_acciones_y_el_traslado_depende_del_abono() -> None:
    contexto = _contexto(
        cliente=ClienteResuelto("cli-42", "Ing. Reyes", True)
    )
    borrador = compilar(_hechos_caso_b(), contexto)

    assert [a.nombre for a in borrador.acciones] == [
        "registrar_abono_cliente",
        "registrar_traslado_caja_banco",
    ]
    assert borrador.acciones[1].depende_de == 1
    assert all(a.requiere_doble_confirmacion for a in borrador.acciones)
    assert borrador.acciones[0].parametros["monto_usd"] == Decimal("12000")
    # Un audio de dinero no debe pedir volumen ni obra de una cotización.
    assert borrador.preguntas == ()
    assert borrador.estado == "PENDIENTE_CONFIRMACION"


def test_caso_b_saldo_insuficiente_marca_el_traslado() -> None:
    contexto = _contexto(
        cliente=ClienteResuelto("cli-42", "Ing. Reyes", True),
        saldo_caja=Decimal("5000"),
    )
    borrador = compilar(_hechos_caso_b(), contexto)
    traslado = borrador.acciones[1]

    assert traslado.bloqueada_por == "SALDO_CAJA_INSUFICIENTE"


# ---------------------------------------------------------------------------
# Caso C y datos faltantes
# ---------------------------------------------------------------------------
def test_caso_c_consulta_no_crea_acciones() -> None:
    borrador = compilar([], _contexto(), intencion="CONSULTA")

    assert borrador.estado == "SIN_ACCIONES"
    assert borrador.acciones == ()
    assert borrador.preguntas == ()


def test_faltan_obra_resistencia_y_precio_pregunta_sin_inventar() -> None:
    hechos = [hecho("cotizacion.volumen_m3", 12, "ENTERO", sostiene="12")]
    contexto = _contexto(
        cliente=ClienteResuelto("cli-1", "Cliente", True),
        receta=None,
    )
    borrador = compilar(hechos, contexto)

    assert borrador.estado == "REQUIERE_ACLARACION"
    assert borrador.acciones == ()
    claves = {p.clave for p in borrador.preguntas}
    assert {"cotizacion.obra_direccion", "cotizacion.resistencia", "cotizacion.precio_m3"} <= claves
    assert len(borrador.preguntas) <= 3


def test_sin_cliente_pregunta_para_quien() -> None:
    borrador = compilar([], _contexto())

    assert borrador.estado == "REQUIERE_ACLARACION"
    assert any(p.clave == "cliente.nombre" for p in borrador.preguntas)


# ---------------------------------------------------------------------------
# Validación de hechos
# ---------------------------------------------------------------------------
def test_hecho_con_valor_no_sostenido_se_rechaza() -> None:
    inventado = hecho(
        "cliente.cedula",
        "1102561532",
        "CEDULA",
        sostiene="1102561531",
        checksum=False,
    )
    errores = validar_hecho(inventado)
    assert errores
    assert "no esta sostenido" in errores[0]


def test_hecho_bien_sostenido_pasa() -> None:
    valido = hecho(
        "cliente.cedula",
        "1710034065",
        "CEDULA",
        sostiene="1710034065",
        checksum=True,
    )
    assert validar_hecho(valido) == []


def test_nombre_canonico_se_sostiene_por_la_mencion() -> None:
    """«inge Reyes» puede resolverse al nombre exacto del catálogo."""
    resuelto = hecho(
        "cliente.nombre",
        "Ing. Reyes (prueba Hito 1)",
        cita="del inge Reyes",
        sostiene="del inge Reyes",
    )
    assert validar_hecho(resuelto) == []


# ---------------------------------------------------------------------------
# Permisos
# ---------------------------------------------------------------------------
def test_permisos_por_rol_filtran_dinero() -> None:
    contexto = _contexto(
        cliente=ClienteResuelto("cli-42", "Ing. Reyes", True)
    )
    borrador = compilar(_hechos_caso_b(), contexto)

    assert acciones_permitidas(borrador, "BODEGA") == ()
    assert [a.nombre for a in acciones_permitidas(borrador, "CONTADORA")] == [
        "registrar_abono_cliente",
        "registrar_traslado_caja_banco",
    ]


# ---------------------------------------------------------------------------
# Caso Joaquín: teléfono dictado en grupos y hora sin fecha
# ---------------------------------------------------------------------------
def _hechos_joaquin() -> list[HechoCitado]:
    return [
        hecho("cliente.nombre", "Joaquín Olmedo"),
        hecho("cotizacion.obra_direccion", "Juan José Peña y Mercadillo"),
        hecho("cotizacion.volumen_m3", 10, "ENTERO", sostiene="10"),
        hecho(
            "cotizacion.hora_entrega",
            "06:00",
            "HORA",
            cita="a las 6 de la mañana",
            sostiene="6 de la mañana",
        ),
        hecho("pago.monto", Decimal("500"), "DECIMAL", sostiene="500"),
        hecho("pago.forma", "abono", cita="un abono de 500 USD"),
        hecho("cotizacion.enviar", True, "BOOLEANO", cita="enviarle el recibo"),
    ]


def test_hora_suelta_va_a_hora_tentativa_y_no_a_fecha() -> None:
    borrador = compilar(_hechos_joaquin(), _contexto())
    cotizacion = next(
        a for a in borrador.acciones if a.nombre == "crear_cotizacion_borrador"
    )

    assert cotizacion.parametros["hora_entrega_tentativa"] == "06:00"
    assert cotizacion.parametros["fecha_entrega_tentativa"] is None


def test_fecha_con_cita_de_solo_hora_se_ignora() -> None:
    hechos = _hechos_joaquin()
    hechos.append(
        hecho(
            "cotizacion.fecha_entrega",
            date(2026, 11, 15),
            "FECHA",
            cita="a las 6 de la mañana",
            sostiene="6 de la mañana",
        )
    )
    borrador = compilar(hechos, _contexto())
    cotizacion = next(
        a for a in borrador.acciones if a.nombre == "crear_cotizacion_borrador"
    )

    assert cotizacion.parametros["fecha_entrega_tentativa"] is None


def test_telefono_inferido_pide_confirmacion_y_bloquea() -> None:
    hechos = _hechos_joaquin()
    hechos.insert(
        1,
        hecho(
            "cliente.telefono",
            "0965555555",
            "TELEFONO",
            cita="0965 555 555",
            estado="INFERIDO",
        ),
    )
    borrador = compilar(hechos, _contexto())

    assert borrador.estado == "REQUIERE_ACLARACION"
    pregunta = next(p for p in borrador.preguntas if p.clave == "cliente.telefono")
    assert "0965555555" in pregunta.texto
    assert pregunta.opciones == ("Sí", "No")
    cliente_accion = next(
        a for a in borrador.acciones if a.nombre == "crear_cliente"
    )
    assert cliente_accion.parametros["telefono"] == "0965555555"


def test_telefono_extraido_no_pide_confirmacion() -> None:
    hechos = _hechos_joaquin()
    hechos.insert(
        1,
        hecho(
            "cliente.telefono",
            "0965555555",
            "TELEFONO",
            cita="0965 555 555",
            estado="EXTRAIDO",
        ),
    )
    borrador = compilar(hechos, _contexto())

    assert not any(p.clave == "cliente.telefono" for p in borrador.preguntas)


# ---------------------------------------------------------------------------
# Caso Juan Carlos Lima: recordatorio + transferencia que aun no llega
# ---------------------------------------------------------------------------
def _hechos_juan_carlos(*, recibido: bool = False):
    return [
        hecho("cliente.nombre", "Juan Carlos Lima"),
        hecho("contacto.rol", "maestro", cita="el maestro que va a ser el encargado"),
        hecho(
            "contacto.telefono",
            "0965555556",
            "TELEFONO",
            cita="es el 0965 555 556",
        ),
        hecho("cotizacion.obra_direccion", "avenida Eros del Cenepa"),
        hecho("cotizacion.volumen_m3", 23, "ENTERO", sostiene="23"),
        hecho("cotizacion.resistencia", "210", "ENTERO", sostiene="210"),
        hecho(
            "cotizacion.hora_entrega",
            "10:00",
            "HORA",
            cita="la fundicion va a comenzar a las 10 de la manana",
        ),
        hecho("pago.monto", Decimal("2700"), "DECIMAL", sostiene="2700"),
        hecho("pago.forma", "transferencia"),
        hecho(
            "pago.recibido",
            recibido,
            "BOOLEANO",
            cita="todavia no me envia el comprobante",
        ),
        hecho("pago.cuenta_destino", "Banco de Pichincha"),
        hecho(
            "tarea.telefono",
            "0965555557",
            "TELEFONO",
            cita="enviarle un recordatorio al 0965 555 557",
        ),
        hecho(
            "tarea.mensaje",
            "por favor nos envie el comprobante de la transferencia",
            cita="que por favor nos envie el comprobante de la transferencia",
        ),
    ]


def test_juan_carlos_propone_tarea_y_no_registra_dinero_sin_comprobante() -> None:
    borrador = compilar(_hechos_juan_carlos(), _contexto())

    nombres = [a.nombre for a in borrador.acciones]
    assert nombres == [
        "crear_cliente",
        "crear_cotizacion_borrador",
        "crear_tarea_recordatorio",
    ]
    assert "registrar_abono_cliente" not in nombres
    assert "registrar_traslado_caja_banco" not in nombres
    assert borrador.estado == "PENDIENTE_CONFIRMACION"
    assert borrador.preguntas == ()


def test_juan_carlos_el_telefono_del_maestro_no_es_el_del_cliente() -> None:
    borrador = compilar(_hechos_juan_carlos(), _contexto())

    cliente_accion = next(
        a for a in borrador.acciones if a.nombre == "crear_cliente"
    )
    assert cliente_accion.parametros["telefono"] is None


def test_juan_carlos_la_resistencia_210_resuelve_la_receta() -> None:
    borrador = compilar(_hechos_juan_carlos(), _contexto())

    cotizacion = next(
        a for a in borrador.acciones if a.nombre == "crear_cotizacion_borrador"
    ).parametros
    assert cotizacion["resistencia"] == "FC-210"
    assert cotizacion["precio_m3"] == Decimal("118")
    assert cotizacion["hora_entrega_tentativa"] == "10:00"
    assert cotizacion["fecha_entrega_tentativa"] is None


def test_juan_carlos_la_tarea_lleva_el_mensaje_dictado_y_el_destinatario() -> None:
    borrador = compilar(_hechos_juan_carlos(), _contexto())

    tarea = next(
        a for a in borrador.acciones if a.nombre == "crear_tarea_recordatorio"
    )
    assert tarea.parametros["destinatario"] == "0965555557"
    assert tarea.parametros["mensaje"] == (
        "por favor nos envie el comprobante de la transferencia"
    )
    # Sin hora dictada se propone "ahora", pero queda marcado como inferido.
    assert tarea.parametros["cuando"] == "ahora"
    assert tarea.parametros["programado_inferido"] is True
    assert tarea.parametros["adjuntar_factura"] is False
    assert tarea.rol_requerido == ("SUPERADMIN", "SECRETARIA")


def test_tarea_con_hora_dictada_no_se_marca_inferida() -> None:
    hechos = _hechos_juan_carlos()
    hechos.append(
        hecho("tarea.cuando", "manana a las 9", cita="manana a las 9")
    )
    borrador = compilar(hechos, _contexto())

    tarea = next(
        a for a in borrador.acciones if a.nombre == "crear_tarea_recordatorio"
    )
    assert tarea.parametros["cuando"] == "manana a las 9"
    assert tarea.parametros["programado_inferido"] is False


def test_tarea_sin_mensaje_pregunta_y_no_propone_accion() -> None:
    hechos = [hecho("tarea.telefono", "0965555557", "TELEFONO")]
    borrador = compilar(hechos, _contexto())

    assert not any(a.nombre == "crear_tarea_recordatorio" for a in borrador.acciones)
    assert any(p.clave == "tarea.mensaje" for p in borrador.preguntas)


def test_transferencia_del_cliente_no_se_convierte_en_traslado_de_caja() -> None:
    hechos = [
        hecho("pago.monto", Decimal("2700"), "DECIMAL", sostiene="2700",
              cita="ya nos transfirio los 2700"),
        hecho("pago.forma", "TRANSFERENCIA", cita="ya nos transfirio los 2700"),
        hecho("traslado.cuenta_banco", "Banco de Pichincha"),
    ]
    borrador = compilar(
        hechos, _contexto(cliente=ClienteResuelto("cli-1", "Juan Carlos", True))
    )

    assert [a.nombre for a in borrador.acciones] == ["registrar_abono_cliente"]


def test_normalizar_resistencia_completa_el_prefijo_del_catalogo() -> None:
    assert normalizar_resistencia("210") == "FC-210"
    assert normalizar_resistencia("FC-280") == "FC-280"
    assert normalizar_resistencia(None) is None


# ---------------------------------------------------------------------------
# Caso Díaz Sur: dos contactos, descuento y planta móvil
# ---------------------------------------------------------------------------
def _hechos_diaz_sur():
    return [
        hecho("cliente.nombre", "Díaz Sur", cita="un contrato con la empresa Díaz Sur"),
        hecho("cotizacion.volumen_m3", 380, "ENTERO", sostiene="380"),
        hecho("cotizacion.resistencia", "240", "ENTERO", sostiene="240"),
        hecho("cotizacion.descuento_pct", 13, "ENTERO", sostiene="13"),
        hecho("cotizacion.plazo_entrega", "en un mes", cita="entregados en un mes"),
        hecho(
            "cotizacion.dias_trabajo",
            "sábados y domingos",
            cita="se va a trabajar exclusivamente sábados y domingos",
        ),
        hecho(
            "operacion.planta_movil",
            True,
            "BOOLEANO",
            cita="hay que llevar la planta móvil",
        ),
        hecho(
            "contacto.nombre",
            "Julio Alvarado Meneses",
            cita="el ingeniero Julio Alvarado Meneses",
        ),
        hecho(
            "contacto.rol", "ingeniero", cita="el ingeniero Julio Alvarado Meneses"
        ),
        hecho(
            "contacto.telefono",
            "0965555556",
            "TELEFONO",
            cita="0963-444-444",
        ),
        hecho(
            "contacto.2.nombre",
            "Mauricio Santander",
            cita="el ingeniero Mauricio Santander",
        ),
        hecho(
            "contacto.2.rol", "ingeniero", cita="el ingeniero Mauricio Santander"
        ),
        hecho(
            "contacto.2.telefono",
            "0965555557",
            "TELEFONO",
            cita="0985 454545",
        ),
        hecho("pago.monto", Decimal("27000"), "DECIMAL", sostiene="27000"),
        hecho("pago.forma", "transferencia"),
        hecho(
            "pago.recibido",
            False,
            "BOOLEANO",
            cita="nos van a hacer una transferencia",
        ),
        hecho(
            "tarea.mensaje",
            "que nos haga la transferencia de este monto",
            cita="pidiéndole que nos haga la transferencia de este monto",
        ),
    ]


def _contexto_diaz_sur():
    return _contexto(
        receta=Receta(
            resistencia="FC-240",
            precio_m3=Decimal("122"),
            precio_estado="PROVISIONAL",
        )
    )


def test_diaz_sur_pregunta_a_cual_de_los_dos_contactos() -> None:
    borrador = compilar(_hechos_diaz_sur(), _contexto_diaz_sur())

    assert not any(
        a.nombre == "crear_tarea_recordatorio" for a in borrador.acciones
    )
    pregunta = next(
        p for p in borrador.preguntas if p.clave == "tarea.destinatario"
    )
    assert pregunta.opciones == ("Julio Alvarado Meneses", "Mauricio Santander")


def test_diaz_sur_con_destinatario_usa_el_telefono_del_contacto() -> None:
    hechos = _hechos_diaz_sur()
    hechos.append(hecho("tarea.destinatario", "Mauricio Santander"))
    borrador = compilar(hechos, _contexto_diaz_sur())

    tarea = next(
        a for a in borrador.acciones if a.nombre == "crear_tarea_recordatorio"
    )
    assert tarea.parametros["destinatario"] == "0965555557"


def test_diaz_sur_no_es_abono_ni_traslado_y_el_cliente_es_la_empresa() -> None:
    borrador = compilar(_hechos_diaz_sur(), _contexto_diaz_sur())

    nombres = [a.nombre for a in borrador.acciones]
    assert "registrar_abono_cliente" not in nombres
    assert "registrar_traslado_caja_banco" not in nombres
    cliente = next(a for a in borrador.acciones if a.nombre == "crear_cliente")
    assert cliente.parametros["nombre"] == "Díaz Sur"
    assert cliente.parametros["telefono"] is None


def test_diaz_sur_la_cotizacion_lleva_descuento_plazo_y_planta_movil() -> None:
    hechos = _hechos_diaz_sur()
    hechos.append(
        hecho("cotizacion.obra_direccion", "terreno de Díaz Sur, cerca de la planta")
    )
    borrador = compilar(hechos, _contexto_diaz_sur())

    cotizacion = next(
        a for a in borrador.acciones if a.nombre == "crear_cotizacion_borrador"
    ).parametros
    assert cotizacion["resistencia"] == "FC-240"
    assert cotizacion["precio_m3"] == Decimal("122")
    assert cotizacion["descuento_pct"] == Decimal("13")
    assert cotizacion["plazo_entrega"] == "en un mes"
    assert "Descuento acordado: 13%" in cotizacion["notas"]
    assert "Plazo de entrega: en un mes" in cotizacion["notas"]
    assert "Dias de trabajo: sábados y domingos" in cotizacion["notas"]
    assert "Llevar la planta movil al sitio" in cotizacion["notas"]


def test_la_resistencia_no_se_convierte_en_precio() -> None:
    hechos = [
        hecho("cliente.nombre", "Díaz Sur"),
        hecho("cotizacion.volumen_m3", 380, "ENTERO", sostiene="380"),
        hecho("cotizacion.resistencia", "240", "ENTERO", sostiene="240"),
        hecho("cotizacion.obra_direccion", "terreno propio"),
    ]
    borrador = compilar(hechos, _contexto_diaz_sur())

    cotizacion = next(
        a for a in borrador.acciones if a.nombre == "crear_cotizacion_borrador"
    ).parametros
    assert cotizacion["precio_m3"] == Decimal("122")
    assert not any(p.clave == "cotizacion.precio_m3" for p in borrador.preguntas)


# ---------------------------------------------------------------------------
# Recordatorio suelto: no exige cliente y toma la hora de la frase
# ---------------------------------------------------------------------------
def test_recordatorio_a_un_numero_no_pide_cliente() -> None:
    hechos = [
        hecho("tarea.telefono", "0965555555", "TELEFONO"),
        hecho("tarea.mensaje", "que nos envíe el comprobante"),
        hecho("tarea.cuando", "18:00"),
    ]
    borrador = compilar(hechos, _contexto(cliente=None))

    assert not any(p.clave == "cliente.nombre" for p in borrador.preguntas)
    assert [a.nombre for a in borrador.acciones] == ["crear_tarea_recordatorio"]
    assert borrador.estado == "PENDIENTE_CONFIRMACION"


def test_completar_cuando_de_tarea_toma_la_hora_de_la_frase() -> None:
    from app.cerebro.extractor import _completar_cuando_de_tarea

    hechos = [
        hecho(
            "tarea.telefono",
            "0965555555",
            "TELEFONO",
            cita="al 0965555555",
        ),
        hecho("tarea.mensaje", "que nos envíe el comprobante"),
    ]
    texto = (
        "Envíale un recordatorio al 0965555555 a las 18:00 "
        "que nos envíe el comprobante."
    )
    notas = _completar_cuando_de_tarea(hechos, texto)

    cuando = next(h for h in hechos if h.clave == "tarea.cuando")
    assert cuando.valor == "18:00"
    assert notas


def _hechos_dinero(cita: str, *, recibido: bool | None = None):
    hechos = [
        hecho("pago.monto", Decimal("27000"), "DECIMAL", cita=cita),
        hecho("pago.forma", "transferencia", cita=cita),
    ]
    if recibido is not None:
        hechos.append(hecho("pago.recibido", recibido, "BOOLEANO", cita=cita))
    return hechos


def test_dinero_sin_decir_si_entro_pregunta_y_no_registra_abono() -> None:
    """Un abono toca caja: si el audio no dice que el dinero entró, se pregunta."""
    hechos = _hechos_dinero("nos van a hacer una transferencia de 27000 USD")

    borrador = compilar(hechos, _contexto())

    assert "registrar_abono_cliente" not in [a.nombre for a in borrador.acciones]
    assert any(p.clave == "pago.recibido" for p in borrador.preguntas)
    assert borrador.estado == "REQUIERE_ACLARACION"


def test_dinero_dicho_en_pasado_se_registra_aunque_falte_el_booleano() -> None:
    hechos = _hechos_dinero("ya nos depositaron 27000 USD")

    borrador = compilar(hechos, _contexto())

    assert "registrar_abono_cliente" in [a.nombre for a in borrador.acciones]
    assert not any(p.clave == "pago.recibido" for p in borrador.preguntas)


def test_si_el_audio_dice_que_no_entro_no_se_pregunta_ni_se_registra() -> None:
    hechos = _hechos_dinero(
        "hay que pedirle que nos haga la transferencia", recibido=False
    )

    borrador = compilar(hechos, _contexto())

    assert "registrar_abono_cliente" not in [a.nombre for a in borrador.acciones]
    assert not any(p.clave == "pago.recibido" for p in borrador.preguntas)


def test_un_si_del_modelo_sin_frase_en_pasado_se_pregunta() -> None:
    """El modelo no puede afirmar por su cuenta que el dinero ya entró."""
    hechos = _hechos_dinero("acordamos 27000 USD", recibido=True)

    borrador = compilar(hechos, _contexto(texto="acordamos 27000 USD"))

    assert "registrar_abono_cliente" not in [a.nombre for a in borrador.acciones]
    assert any(p.clave == "pago.recibido" for p in borrador.preguntas)


def test_una_correccion_humana_del_si_se_respeta() -> None:
    hechos = _hechos_dinero("acordamos 27000 USD", recibido=True)
    hechos[-1] = hecho(
        "pago.recibido", True, "BOOLEANO", estado="CORREGIDO_POR_HUMANO"
    )

    borrador = compilar(hechos, _contexto(texto="acordamos 27000 USD"))

    assert "registrar_abono_cliente" in [a.nombre for a in borrador.acciones]
    assert not any(p.clave == "pago.recibido" for p in borrador.preguntas)


def test_la_frase_alrededor_de_la_cifra_distingue_futuro_de_pasado() -> None:
    """La cita de un monto numérico es solo la cifra: manda el texto."""
    hechos = _hechos_dinero("27000")

    futuro = compilar(
        hechos, _contexto(texto="nos van a hacer una transferencia de 27000 USD")
    )
    pasado = compilar(hechos, _contexto(texto="ya me deposito 27000 USD"))

    assert "registrar_abono_cliente" not in [a.nombre for a in futuro.acciones]
    assert any(p.clave == "pago.recibido" for p in futuro.preguntas)
    assert "registrar_abono_cliente" in [a.nombre for a in pasado.acciones]


def test_hora_de_recordatorio_acepta_hh_mm_y_forma_hablada() -> None:
    from app.cerebro.tiempo import hora_de_recordatorio

    assert hora_de_recordatorio("a las 18:00 pidiendo el comprobante") == "18:00"
    assert hora_de_recordatorio("a las 6 de la tarde") == "18:00"
    assert hora_de_recordatorio("que nos envíe el comprobante") is None
