"""Tres encargos en un dictado: separación, corrección y no mezcla.

Caso de aceptación del laboratorio (2026-11-16): un audio con tres asuntos
independientes (revisar medidas de una cotización, recordatorio a un ingeniero
externo y revisión de despachos). El motor anterior los colapsaba en uno.

Estas pruebas no llaman al LLM: fijan los hechos con su cita y comprueban que
la segmentación y el compilador mantienen cada asunto separado.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from app.cerebro import Contexto, Evidencia, HechoCitado, Receta, compilar
from app.cerebro.encargos import asignar, segmentar
from app.cerebro.revision import aplicar

TEXTO = (
    "A ver, tengo tres cosas pendientes. "
    "Primero, que secretaría revise las medidas para la cotización de la obra "
    "del colegio Central. Creo que son 30 metros cúbicos de hormigón de 240. "
    "Segundo, hay que enviarle mañana un recordatorio al ingeniero Mauricio "
    "para que nos mande el comprobante de pago. "
    "Y tercero, que secretaría revise los despachos que tenemos pendientes "
    "para esta semana y me informe cuáles todavía no tienen fecha confirmada."
)


def hecho(
    clave: str,
    valor,
    tipo: str = "TEXTO",
    *,
    cita: str,
    estado: str = "EXTRAIDO",
) -> HechoCitado:
    inicio = TEXTO.find(cita)
    if inicio < 0:
        raise AssertionError(f"la cita no está en el texto: {cita!r}")
    return HechoCitado(
        clave=clave,
        valor=valor,
        estado=estado,
        tipo=tipo,
        evidencia=Evidencia(
            cita=cita,
            sostiene=cita,
            crudo_inicio=inicio,
            crudo_fin=inicio + len(cita),
            start_ms=None,
            end_ms=None,
            confianza=0.9,
            hablante="SUPERADMIN",
        ),
    )


def hechos_del_caso() -> list[HechoCitado]:
    return asignar(
        [
            hecho(
                "cotizacion.volumen_m3",
                30,
                "DECIMAL",
                cita="Creo que son 30 metros cúbicos",
                estado="TENTATIVO",
            ),
            hecho(
                "cotizacion.resistencia",
                240,
                "ENTERO",
                cita="hormigón de 240",
            ),
            hecho(
                "tarea.destinatario",
                "secretaría",
                cita="que secretaría revise las medidas",
            ),
            hecho(
                "tarea.destinatario",
                "ingeniero Mauricio",
                cita="un recordatorio al ingeniero Mauricio",
            ),
            hecho(
                "tarea.mensaje",
                "para que nos mande el comprobante de pago",
                cita="para que nos mande el comprobante de pago",
            ),
            hecho(
                "tarea.cuando",
                "2026-11-17",
                cita="hay que enviarle mañana",
            ),
            hecho(
                "tarea.destinatario",
                "secretaría",
                cita="que secretaría revise los despachos",
            ),
        ],
        segmentar(TEXTO),
    )


def contexto(texto: str = TEXTO) -> Contexto:
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
        texto=texto,
    )


def test_segmentar_tres_ordinales_ignora_el_preambulo() -> None:
    segmentos = segmentar(TEXTO)

    assert len(segmentos) == 3
    assert segmentos[0].texto.startswith("Primero")
    assert segmentos[1].texto.startswith("Segundo")
    assert segmentos[2].texto.startswith("Y tercero")
    assert "tengo tres cosas" not in " ".join(s.texto for s in segmentos)


def test_un_solo_dictado_sigue_siendo_un_encargo() -> None:
    segmentos = segmentar("Necesito cotizar 12 m3 de FC-210 para la obra.")

    assert len(segmentos) == 1
    assert segmentos[0].indice == 1


def test_tres_acciones_independientes_y_sin_mezclar_texto() -> None:
    borrador = compilar(hechos_del_caso(), contexto())

    assert [e.encargo for e in borrador.encargos] == [1, 2, 3]
    assert len(borrador.acciones) == 3

    por_encargo = {a.encargo: a for a in borrador.acciones}

    # Encargo 1: encargo al equipo para revisar medidas. No es un envío.
    assert por_encargo[1].nombre == "crear_tarea_interna"
    assert "medidas" in por_encargo[1].parametros["instruccion"]
    assert por_encargo[1].parametros["instruccion"] != por_encargo[3].parametros[
        "instruccion"
    ]

    # Encargo 2: recordatorio externo al ingeniero, no a secretaría.
    assert por_encargo[2].nombre == "crear_tarea_recordatorio"
    assert por_encargo[2].parametros["destinatario"] == "ingeniero Mauricio"
    assert por_encargo[2].parametros["cuando"] == "2026-11-17"
    assert "comprobante" in por_encargo[2].parametros["instruccion"]

    # Encargo 3: revisión de despachos, sin el mensaje del ingeniero.
    assert por_encargo[3].nombre == "crear_tarea_interna"
    assert "despachos" in por_encargo[3].parametros["instruccion"]
    assert "comprobante" not in por_encargo[3].parametros["instruccion"]
    assert "Mauricio" not in por_encargo[3].parametros["instruccion"]


def test_el_pedido_de_secretaria_no_convierte_el_recordatorio_en_interno() -> None:
    """«secretaría» del encargo 1 no debe teñir el recordatorio del encargo 2."""
    borrador = compilar(hechos_del_caso(), contexto())

    recordatorio = next(
        a for a in borrador.acciones if a.nombre == "crear_tarea_recordatorio"
    )
    assert recordatorio.encargo == 2


def test_las_preguntas_quedan_en_su_encargo() -> None:
    borrador = compilar(hechos_del_caso(), contexto())

    claves_por_encargo: dict[int, set[str]] = {}
    for pregunta in borrador.preguntas:
        claves_por_encargo.setdefault(pregunta.encargo, set()).add(pregunta.clave)

    assert "cotizacion.obra_direccion" in claves_por_encargo[1]
    assert "tarea.telefono" in claves_por_encargo[2]
    assert "tarea.mensaje" not in claves_por_encargo.get(3, set())


def test_corregir_un_encargo_no_toca_los_demas() -> None:
    hechos = hechos_del_caso()
    corregidos = aplicar(
        hechos,
        {"cotizacion.volumen_m3": "35"},
        tipos={"cotizacion.volumen_m3": "DECIMAL"},
        encargo=1,
    )

    volumen = next(h for h in corregidos if h.clave == "cotizacion.volumen_m3")
    assert str(volumen.valor) == "35"
    assert volumen.encargo == 1
    assert volumen.estado == "CORREGIDO_POR_HUMANO"

    otros = [
        h for h in corregidos if h.encargo in (2, 3)
    ]
    originales = [h for h in hechos if h.encargo in (2, 3)]
    assert otros == originales


def test_la_misma_clave_en_dos_encargos_se_corrige_por_encargo() -> None:
    hechos = hechos_del_caso()
    hechos.append(
        replace(
            hecho(
                "tarea.mensaje",
                "revise los despachos pendientes",
                cita="que secretaría revise los despachos",
            ),
            encargo=3,
        )
    )

    corregidos = aplicar(
        hechos,
        {"tarea.mensaje": "otro texto"},
        encargo=3,
    )

    mensajes = [h for h in corregidos if h.clave == "tarea.mensaje"]
    assert len(mensajes) == 2
    assert str(next(h for h in mensajes if h.encargo == 2).valor) == (
        "para que nos mande el comprobante de pago"
    )
    assert str(next(h for h in mensajes if h.encargo == 3).valor) == "otro texto"


def test_el_resumen_dice_que_encargo_es_cada_uno() -> None:
    from app.cerebro.revision import resumen_legible

    borrador = compilar(hechos_del_caso(), contexto())
    textos = {s.indice: s.texto for s in segmentar(TEXTO)}
    resumen = resumen_legible(
        borrador.hechos,
        texto=TEXTO,
        condiciones=borrador.condiciones,
        textos_por_encargo=textos,
    )

    assert "Encargo 1:" in resumen
    assert "Encargo 2:" in resumen
    assert "Encargo 3:" in resumen
    # La tarea interna del 3 se lee como interna, no como recordatorio.
    tramo_3 = resumen.split("Encargo 3:")[1]
    assert "tarea interna" in tramo_3
    assert "recordatorio" not in tramo_3


def test_un_encargo_sin_hechos_pero_con_rol_se_conserva() -> None:
    """Si el modelo no extrajo nada del tramo, el encargo no desaparece."""
    solo_primero = [
        h
        for h in hechos_del_caso()
        if h.evidencia is not None
        and h.evidencia.crudo_inicio < TEXTO.find("Segundo,")
    ]
    assert solo_primero

    borrador = compilar(solo_primero, contexto())

    tercero = next((e for e in borrador.encargos if e.encargo == 3), None)
    assert tercero is not None
    instruccion = next(
        a.parametros["instruccion"]
        for a in borrador.acciones
        if a.encargo == 3
    )
    assert "despachos" in instruccion
    assert "comprobante" not in instruccion
