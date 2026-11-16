"""Alineación entre texto normalizado, texto crudo y palabras del STT."""

from __future__ import annotations

from app.voz import (
    PalabraSTT,
    alinear_secuencias,
    localizar_palabras,
    normalizar_alineado,
    normalizar_con_mapa,
    normalizar_texto,
)


def _span(crudo: str, token) -> str:
    return crudo[token.crudo_inicio : token.crudo_fin]


# ---------------------------------------------------------------------------
# Mapa de tokens
# ---------------------------------------------------------------------------
def test_numero_hablado_apunta_a_su_palabra() -> None:
    crudo = "quiere veinticinco cubos"
    mapa = normalizar_con_mapa(crudo)

    assert mapa.texto == "quiere 25 m3"
    token = next(t for t in mapa.tokens if t.texto == "25")
    assert _span(crudo, token) == "veinticinco"
    assert token.tipo == "NUMERO"

    unidad = next(t for t in mapa.tokens if t.texto == "m3")
    assert _span(crudo, unidad) == "cubos"
    assert unidad.tipo == "UNIDAD"


def test_m3_pegado_es_un_solo_token() -> None:
    crudo = "quiere 25m3"
    mapa = normalizar_con_mapa(crudo)

    assert mapa.texto == "quiere 25 m3"
    unidad = next(t for t in mapa.tokens if t.tipo == "UNIDAD")
    assert _span(crudo, unidad) == "25m3"
    assert mapa.texto[unidad.inicio : unidad.fin] == "25 m3"


def test_moneda_conserva_el_origen_completo() -> None:
    crudo = "me dio 1000 dolares"
    mapa = normalizar_con_mapa(crudo)

    assert mapa.texto == "me dio 1000 USD"
    moneda = next(t for t in mapa.tokens if t.tipo == "MONEDA")
    assert _span(crudo, moneda) == "1000 dolares"


def test_alias_cubre_articulo_y_preposicion() -> None:
    crudo = "es del coca"
    mapa = normalizar_con_mapa(crudo)

    assert mapa.texto == "es de El Coca"
    alias = next(t for t in mapa.tokens if t.tipo == "ALIAS")
    assert _span(crudo, alias) == "del coca"


def test_normalizar_texto_sigue_siendo_el_mismo_texto() -> None:
    for crudo in (
        "quiere veinticinco cubos",
        "me dio 1000 dolares",
        "es del coca",
        "110256 que mas 1531",
    ):
        assert normalizar_texto(crudo) == normalizar_con_mapa(crudo).texto


# ---------------------------------------------------------------------------
# Alineación con palabras del STT
# ---------------------------------------------------------------------------
def _palabras_cedula() -> list[PalabraSTT]:
    crudo = "110256 que mas 1531"
    return [
        PalabraSTT("110256", crudo.index("110256"), 6, 0, 900, 0.99),
        PalabraSTT("que", 7, 10, 900, 1100, 0.40),
        PalabraSTT("mas", 11, 14, 1100, 1300, 0.50),
        PalabraSTT("1531", 15, 19, 1300, 1900, 0.98),
    ]


def test_cedula_unida_apunta_a_los_dos_tramos_y_omite_conectores() -> None:
    crudo = "110256 que mas 1531"
    mapa = normalizar_con_mapa(crudo)
    (secuencia,) = alinear_secuencias(mapa, _palabras_cedula())

    assert secuencia.digitos == "1102561531"
    assert secuencia.tipo == "CEDULA"
    assert secuencia.checksum_valido is False
    assert secuencia.crudo_inicio == 0
    assert secuencia.crudo_fin == len(crudo)
    assert secuencia.palabras == (0, 1, 2, 3)
    assert secuencia.palabras_dato == (0, 3)
    assert secuencia.confianza_minima == 0.98
    assert (secuencia.start_ms, secuencia.end_ms) == (0, 1900)


def test_la_confianza_minima_no_la_baja_el_conector() -> None:
    crudo = "110256 que mas 1531"
    mapa = normalizar_con_mapa(crudo)
    (secuencia,) = alinear_secuencias(mapa, _palabras_cedula())

    # 0.40 es la confianza de "que"; el dato no debe heredarla.
    assert secuencia.confianza_minima == 0.98


def test_secuencia_sin_palabras_queda_sin_ventana() -> None:
    mapa = normalizar_con_mapa("quiere 25 m3")
    (secuencia,) = alinear_secuencias(mapa, [])
    assert secuencia.start_ms is None
    assert secuencia.end_ms is None
    assert secuencia.confianza_minima is None


def test_localizar_palabras_respeta_el_orden() -> None:
    crudo = "hola mundo"
    palabras = localizar_palabras(
        crudo,
        [
            {"palabra": "hola", "inicio_ms": 0, "fin_ms": 500, "confianza": 0.9},
            {"palabra": "mundo", "inicio_ms": 500, "fin_ms": 900, "confianza": 0.8},
        ],
    )
    assert [(p.inicio, p.fin) for p in palabras] == [(0, 4), (5, 10)]
    assert [p.start_ms for p in palabras] == [0, 500]


def test_normalizar_alineado_frase_del_caso_a() -> None:
    crudo = "cedula 110256 que mas 1531 y telefono 0965555555"
    palabras = localizar_palabras(
        crudo,
        [
            {"palabra": "cedula", "inicio_ms": 0, "fin_ms": 300, "confianza": 0.9},
            {"palabra": "110256", "inicio_ms": 300, "fin_ms": 800, "confianza": 0.97},
            {"palabra": "que", "inicio_ms": 800, "fin_ms": 900, "confianza": 0.4},
            {"palabra": "mas", "inicio_ms": 900, "fin_ms": 1000, "confianza": 0.4},
            {"palabra": "1531", "inicio_ms": 1000, "fin_ms": 1400, "confianza": 0.96},
            {"palabra": "y", "inicio_ms": 1400, "fin_ms": 1450, "confianza": 0.5},
            {"palabra": "telefono", "inicio_ms": 1450, "fin_ms": 1800, "confianza": 0.9},
            {"palabra": "0965555555", "inicio_ms": 1800, "fin_ms": 3000, "confianza": 0.99},
        ],
    )
    texto, secuencias = normalizar_alineado(crudo, palabras)

    por_tipo = {s.tipo: s for s in secuencias}
    assert por_tipo["CEDULA"].digitos == "1102561531"
    assert por_tipo["CEDULA"].confianza_minima == 0.96
    assert por_tipo["TELEFONO"].digitos == "0965555555"
    assert por_tipo["TELEFONO"].start_ms == 1800
    assert "1102561531" in texto
