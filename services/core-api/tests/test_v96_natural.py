"""Dictado espontáneo: separación sin ordinales y duda acotada al dato.

Casos del 2026-11-16 sobre lenguaje natural:
- tres encargos sin «primero/segundo/tercero»;
- «creo que eran treinta metros de hormigón de 240»: la duda es del volumen,
  no de la resistencia;
- la duda puede caer sobre el cliente, la fecha o una condición;
- si el dictado trae varias instrucciones y el extractor no las separa, se
  pregunta antes de proponer.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from app.cerebro import Contexto, Evidencia, HechoCitado, Receta, compilar
from app.cerebro.encargos import asignar
from app.cerebro.extractor import _ajustar_incertidumbre

TEXTO = (
    "A ver, que secretaría revise los despachos de mañana porque me parece "
    "que falta uno. Ah, también hay que llamar al ingeniero Mauricio por lo "
    "del pago. Y el colegio Central, creo que eran treinta metros de hormigón "
    "de 240, que me confirmen las medidas."
)


def hecho(
    clave: str,
    valor,
    tipo: str = "TEXTO",
    *,
    cita: str,
    estado: str = "EXTRAIDO",
    encargo: int = 1,
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
        encargo=encargo,
    )


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


def hechos_naturales() -> list[HechoCitado]:
    return [
        hecho(
            "tarea.destinatario",
            "secretaría",
            cita="que secretaría revise los despachos",
            encargo=1,
        ),
        hecho(
            "tarea.mensaje",
            "revise los despachos de mañana porque me parece que falta uno",
            cita="revise los despachos de mañana",
            encargo=1,
        ),
        hecho(
            "tarea.destinatario",
            "ingeniero Mauricio",
            cita="llamar al ingeniero Mauricio",
            encargo=2,
        ),
        hecho(
            "tarea.mensaje",
            "por lo del pago",
            cita="por lo del pago",
            encargo=2,
        ),
        hecho("cliente.nombre", "colegio Central", cita="el colegio Central", encargo=3),
        hecho(
            "cotizacion.volumen_m3",
            30,
            "DECIMAL",
            cita="treinta metros de hormigón",
            encargo=3,
        ),
        hecho(
            "cotizacion.resistencia",
            240,
            "ENTERO",
            cita="hormigón de 240",
            encargo=3,
        ),
        hecho(
            "tarea.mensaje",
            "que me confirmen las medidas",
            cita="que me confirmen las medidas",
            encargo=3,
        ),
    ]


# ---------------------------------------------------------------------------
# Separación
# ---------------------------------------------------------------------------
def test_tres_encargos_sin_ordinales_no_se_mezclan() -> None:
    borrador = compilar(hechos_naturales(), contexto())

    assert [e.encargo for e in borrador.encargos] == [1, 2, 3]
    por_encargo = {a.encargo: a for a in borrador.acciones}
    assert por_encargo[1].nombre == "crear_tarea_interna"
    assert por_encargo[2].nombre == "crear_tarea_recordatorio"
    assert por_encargo[2].parametros["destinatario"] == "ingeniero Mauricio"
    assert por_encargo[2].parametros["mensaje_por_confirmar"] is True
    assert "comprobante" not in str(por_encargo[1].parametros["instruccion"])
    assert "despachos" not in str(por_encargo[3].parametros["instruccion"])


def test_el_recordatorio_no_inventa_telefono_ni_fecha() -> None:
    borrador = compilar(hechos_naturales(), contexto())

    recordatorio = next(
        a for a in borrador.acciones if a.nombre == "crear_tarea_recordatorio"
    )
    assert recordatorio.parametros["destinatario"] == "ingeniero Mauricio"
    assert "cuando" not in recordatorio.parametros or recordatorio.parametros.get(
        "cuando"
    ) in (None, "ahora")
    claves = {p.clave for p in borrador.preguntas if p.encargo == 2}
    assert "tarea.telefono" in claves


def test_asignar_respeta_la_separacion_del_extractor_y_renumera() -> None:
    hechos = [
        hecho("tarea.mensaje", "uno", cita="revise los despachos", encargo=1),
        hecho("tarea.mensaje", "dos", cita="por lo del pago", encargo=3),
    ]

    asignados = asignar(hechos, ())

    assert [h.encargo for h in asignados] == [1, 2]


def test_si_el_extractor_no_separa_y_hay_dos_instrucciones_se_pregunta() -> None:
    hechos = [
        hecho("tarea.mensaje", "revise los despachos", cita="revise los despachos"),
        hecho("tarea.mensaje", "por lo del pago", cita="por lo del pago"),
    ]

    borrador = compilar(hechos, contexto())

    assert borrador.estado == "REQUIERE_ACLARACION"
    assert any(p.clave == "encargo.division" for p in borrador.preguntas)


def test_con_un_solo_mensaje_no_se_pregunta_por_la_division() -> None:
    hechos = [
        hecho("tarea.mensaje", "revise los despachos", cita="revise los despachos"),
    ]

    borrador = compilar(hechos, contexto())

    assert not any(p.clave == "encargo.division" for p in borrador.preguntas)


# ---------------------------------------------------------------------------
# Incertidumbre acotada al dato
# ---------------------------------------------------------------------------
def test_la_duda_es_del_volumen_y_no_de_la_resistencia() -> None:
    hechos = [
        hecho(
            "cotizacion.volumen_m3",
            30,
            "DECIMAL",
            cita="treinta metros de hormigón",
            estado="TENTATIVO",
        ),
        hecho(
            "cotizacion.resistencia",
            240,
            "ENTERO",
            cita="hormigón de 240",
            estado="TENTATIVO",
        ),
    ]

    notas = _ajustar_incertidumbre(hechos, TEXTO)

    volumen = next(h for h in hechos if h.clave == "cotizacion.volumen_m3")
    resistencia = next(h for h in hechos if h.clave == "cotizacion.resistencia")
    assert volumen.estado == "TENTATIVO"
    assert resistencia.estado == "EXTRAIDO"
    assert any("resistencia" in nota for nota in notas)


def test_la_duda_que_el_modelo_no_marco_se_marca() -> None:
    hechos = [
        hecho("cotizacion.volumen_m3", 30, "DECIMAL", cita="treinta metros de hormigón"),
        hecho("cotizacion.resistencia", 240, "ENTERO", cita="hormigón de 240"),
    ]

    _ajustar_incertidumbre(hechos, TEXTO)

    assert next(
        h for h in hechos if h.clave == "cotizacion.volumen_m3"
    ).estado == "TENTATIVO"
    assert next(
        h for h in hechos if h.clave == "cotizacion.resistencia"
    ).estado == "EXTRAIDO"


def test_la_duda_sobre_el_cliente_solo_marca_al_cliente() -> None:
    texto = "Creo que el cliente es la constructora Andes, con 40 metros cúbicos."
    hechos = [
        HechoCitado(
            clave="cliente.nombre",
            valor="constructora Andes",
            estado="TENTATIVO",
            tipo="TEXTO",
            evidencia=Evidencia(
                cita="la constructora Andes",
                sostiene="la constructora Andes",
                crudo_inicio=texto.find("la constructora"),
                crudo_fin=texto.find("la constructora") + len("la constructora Andes"),
                start_ms=None,
                end_ms=None,
                confianza=0.9,
                hablante="SUPERADMIN",
            ),
        ),
        HechoCitado(
            clave="cotizacion.volumen_m3",
            valor=40,
            estado="TENTATIVO",
            tipo="DECIMAL",
            evidencia=Evidencia(
                cita="40 metros cúbicos",
                sostiene="40 metros cúbicos",
                crudo_inicio=texto.find("40 metros"),
                crudo_fin=texto.find("40 metros") + len("40 metros cúbicos"),
                start_ms=None,
                end_ms=None,
                confianza=0.9,
                hablante="SUPERADMIN",
            ),
        ),
    ]

    _ajustar_incertidumbre(hechos, texto)

    assert next(h for h in hechos if h.clave == "cliente.nombre").estado == "TENTATIVO"
    assert next(
        h for h in hechos if h.clave == "cotizacion.volumen_m3"
    ).estado == "EXTRAIDO"


def test_la_duda_sobre_la_fecha_solo_marca_la_fecha() -> None:
    from datetime import date as fecha

    texto = "La entrega es el 21 de noviembre, creo, de 30 metros cúbicos."
    inicio_fecha = texto.find("21 de noviembre")
    inicio_volumen = texto.find("30 metros")
    hechos = [
        HechoCitado(
            clave="cotizacion.fecha_entrega",
            valor=fecha(2026, 11, 21),
            estado="TENTATIVO",
            tipo="FECHA",
            evidencia=Evidencia(
                cita="21 de noviembre",
                sostiene="21 de noviembre",
                crudo_inicio=inicio_fecha,
                crudo_fin=inicio_fecha + len("21 de noviembre"),
                start_ms=None,
                end_ms=None,
                confianza=0.9,
                hablante="SUPERADMIN",
            ),
        ),
        HechoCitado(
            clave="cotizacion.volumen_m3",
            valor=30,
            estado="TENTATIVO",
            tipo="DECIMAL",
            evidencia=Evidencia(
                cita="30 metros cúbicos",
                sostiene="30 metros cúbicos",
                crudo_inicio=inicio_volumen,
                crudo_fin=inicio_volumen + len("30 metros cúbicos"),
                start_ms=None,
                end_ms=None,
                confianza=0.9,
                hablante="SUPERADMIN",
            ),
        ),
    ]

    _ajustar_incertidumbre(hechos, texto)

    assert next(
        h for h in hechos if h.clave == "cotizacion.fecha_entrega"
    ).estado == "TENTATIVO"
    assert next(
        h for h in hechos if h.clave == "cotizacion.volumen_m3"
    ).estado == "EXTRAIDO"


def test_sin_marcas_de_duda_no_se_toca_lo_que_dijo_el_modelo() -> None:
    hechos = [
        hecho(
            "cotizacion.volumen_m3",
            30,
            "DECIMAL",
            cita="treinta metros de hormigón",
            estado="TENTATIVO",
        )
    ]

    notas = _ajustar_incertidumbre(hechos, "Treinta metros de hormigón para el colegio.")

    assert hechos[0].estado == "TENTATIVO"
    assert notas == []
