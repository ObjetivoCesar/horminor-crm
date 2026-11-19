"""Gato por audio y una sola instrucción con dos destinatarios.

Caso real (2026-11-19): «Dame preparando una entrega de 25 m3 … confírmame con
el chofer y con Julio». El extractor partió la coordinación en tres encargos y
el borrador terminó con siete preguntas. Aquí se fija el comportamiento:
un solo encargo, una tarea interna y como máximo tres preguntas.

No se llama al LLM: se construyen los hechos con su cita, como en
``test_v95_encargos.py``.
"""

from __future__ import annotations

from datetime import date

from app.cerebro import Contexto, Evidencia, HechoCitado, compilar
from app.cerebro.encargos import asignar, fusionar_coordinaciones, segmentar
from app.cerebro.internas import detectar_intencion_tarea

TEXTO = (
    "Dame preparando una entrega de 25 m3 de hormigón en la entrada de El Coca, "
    "en una hostelería llamada Jack Sparrow. Está todo pagado, va a recibir el "
    "maestro Pedro, confírmame con el chofer y con Julio."
)


def hecho(
    clave: str,
    valor,
    tipo: str = "TEXTO",
    *,
    cita: str,
    encargo: int = 1,
) -> HechoCitado:
    inicio = TEXTO.find(cita)
    if inicio < 0:
        raise AssertionError(f"la cita no está en el texto: {cita!r}")
    return HechoCitado(
        clave=clave,
        valor=valor,
        estado="EXTRAIDO",
        tipo=tipo,
        evidencia=Evidencia(
            cita=cita,
            sostiene=cita,
            crudo_inicio=inicio,
            crudo_fin=inicio + len(cita),
            start_ms=None,
            end_ms=None,
            confianza=0.82,
            hablante="SUPERADMIN",
        ),
        encargo=encargo,
    )


def caso() -> list[HechoCitado]:
    """Lo que devolvió el extractor: tres encargos, dos solo de coordinación."""
    return asignar(
        [
            hecho("cotizacion.volumen_m3", 25, "DECIMAL", cita="25 m3"),
            hecho("contacto.nombre", "Pedro", cita="el maestro Pedro"),
            hecho("contacto.rol", "maestro", cita="el maestro Pedro"),
            hecho(
                "tarea.destinatario",
                "chofer",
                cita="confírmame con el chofer",
                encargo=2,
            ),
            hecho(
                "tarea.mensaje",
                "confírmame con el chofer",
                cita="confírmame con el chofer",
                encargo=2,
            ),
            hecho("tarea.destinatario", "Julio", cita="y con Julio", encargo=3),
        ],
        segmentar(TEXTO),
    )


def contexto() -> Contexto:
    return Contexto(
        hoy=date(2026, 11, 19),
        sandbox=True,
        cliente=None,
        receta=None,
        rol_actor="SUPERADMIN",
        texto=TEXTO,
    )


def test_dos_destinatarios_de_una_frase_son_un_solo_encargo() -> None:
    unidos = fusionar_coordinaciones(caso())

    assert {hecho.encargo for hecho in unidos} == {1}
    destinos = [
        str(hecho.valor)
        for hecho in unidos
        if hecho.clave == "tarea.destinatario"
    ]
    assert destinos == ["chofer", "Julio"]


def test_la_coordinacion_se_registra_como_tarea_interna() -> None:
    borrador = compilar(fusionar_coordinaciones(caso()), contexto())

    assert len(borrador.encargos) == 1
    tarea = next(
        accion for accion in borrador.acciones if accion.nombre == "crear_tarea_interna"
    )
    assert "chofer" in tarea.parametros["asignado_a"]
    assert "Julio" in tarea.parametros["asignado_a"]
    assert "confírmame" in tarea.parametros["instruccion"]
    assert "Julio" in tarea.parametros["instruccion"]
    assert " y con Julio" in tarea.parametros["instruccion"]
    assert "y y" not in tarea.parametros["instruccion"]


def test_el_borrador_no_devuelve_siete_preguntas() -> None:
    borrador = compilar(fusionar_coordinaciones(caso()), contexto())

    assert len(borrador.preguntas) <= 3
    claves = {pregunta.clave for pregunta in borrador.preguntas}
    assert "cliente.nombre" in claves
    assert "cotizacion.obra_direccion" in claves
    assert "cotizacion.resistencia" in claves


def test_confirmame_es_una_instruccion_interna_no_un_envio() -> None:
    assert detectar_intencion_tarea("confírmame con el chofer y con Julio") == "DELEGAR"


def test_un_encargo_con_datos_propios_no_se_fusiona() -> None:
    hechos = caso() + [
        hecho(
            "cotizacion.obra_direccion",
            "en la entrada de El Coca",
            cita="en la entrada de El Coca",
            encargo=4,
        )
    ]
    unidos = fusionar_coordinaciones(hechos)

    assert {hecho.encargo for hecho in unidos} == {1, 2}
