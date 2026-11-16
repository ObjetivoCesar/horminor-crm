"""Normalizador es-EC del componente de voz (sin red ni credenciales)."""

from __future__ import annotations

from app.voz import (
    cedula_valida,
    extraer_secuencias,
    normalizar_numero_hablado,
    normalizar_texto,
)


# ---------------------------------------------------------------------------
# Números hablados
# ---------------------------------------------------------------------------
def test_convierte_unidades_y_decenas() -> None:
    assert normalizar_texto("quiere veinticinco cubos") == "quiere 25 m3"
    assert normalizar_texto("treinta y dos metros cubicos") == "32 m3"


def test_convierte_miles_y_millones() -> None:
    assert normalizar_texto("doce mil de abono") == "12000 de abono"
    assert normalizar_texto("dos mil quinientos") == "2500"
    assert normalizar_texto("ciento veinte mil") == "120000"
    assert normalizar_texto("un millon doscientos mil") == "1200000"


def test_convierte_mil_dicho_con_digitos() -> None:
    """El STT mezcla cifras y palabras: «27 mil» es un monto, no dos números."""
    assert normalizar_texto("una transferencia de 27 mil dolares") == (
        "una transferencia de 27000 USD"
    )
    assert normalizar_texto("27 mil 500 dolares") == "27500 USD"


def test_no_convierte_el_articulo_suelto() -> None:
    assert normalizar_texto("un cliente llamado Jorge") == "un cliente llamado Jorge"
    assert normalizar_texto("una obra en el coca") == "una obra en El Coca"


def test_numero_hablado_exige_frase_numerica() -> None:
    assert normalizar_numero_hablado("veinticinco") == "25"
    assert normalizar_numero_hablado("doce mil") == "12000"
    assert normalizar_numero_hablado("hola") is None
    assert normalizar_numero_hablado("25") is None


# ---------------------------------------------------------------------------
# Unidades, moneda y ciudades
# ---------------------------------------------------------------------------
def test_unifica_unidades_de_volumen() -> None:
    assert normalizar_texto("quiere 25m3") == "quiere 25 m3"
    assert normalizar_texto("son 12 m³") == "son 12 m3"
    assert normalizar_texto("un metro cubico") == "un m3"


def test_deja_metros_solos_porque_pueden_ser_distancia() -> None:
    assert normalizar_texto("esta a 300 metros") == "esta a 300 metros"


def test_marca_moneda() -> None:
    assert normalizar_texto("me dio 1000 dolares") == "me dio 1000 USD"
    assert normalizar_texto("son 12000 USD") == "son 12000 USD"


def test_normaliza_ciudad_coloquial() -> None:
    assert normalizar_texto("es del coca") == "es de El Coca"
    assert normalizar_texto("vive en el coca") == "vive en El Coca"


def test_respeta_alias_configurables() -> None:
    alias = {"lago": "Lago Agrio"}
    assert normalizar_texto("es de lago", alias_ciudades=alias) == "es de Lago Agrio"


# ---------------------------------------------------------------------------
# Secuencias numéricas
# ---------------------------------------------------------------------------
def test_une_cedula_dictada_en_dos_tramos() -> None:
    (secuencia,) = extraer_secuencias("110256 que mas 1531")
    assert secuencia.digitos == "1102561531"
    assert secuencia.tipo == "CEDULA"
    # El ejemplo es inventado y no pasa el dígito verificador: se advierte,
    # no se corrige.
    assert secuencia.checksum_valido is False


def test_cedula_valida_no_se_altera() -> None:
    assert cedula_valida("1710034065") is True
    assert cedula_valida("1710034066") is False
    assert cedula_valida("1102561531") is False


def test_detecta_telefono_y_cantidad() -> None:
    (telefono,) = extraer_secuencias("el telefono es 0965555555")
    assert telefono.tipo == "TELEFONO"

    (cantidad,) = extraer_secuencias("quiere 25 m3")
    assert cantidad.digitos == "25"
    assert cantidad.tipo == "CANTIDAD"


def test_no_une_numeros_separados_por_coma_o_correccion() -> None:
    secuencias = extraer_secuencias("10, no mejor 15")
    assert [s.digitos for s in secuencias] == ["10", "15"]


def test_no_une_volumen_con_identificacion() -> None:
    secuencias = extraer_secuencias("25 m3 para el sabado")
    assert [s.digitos for s in secuencias] == ["25"]


def test_orden_y_posiciones() -> None:
    secuencias = extraer_secuencias("cedula 1710034065 y telefono 0965555555")
    assert [s.digitos for s in secuencias] == ["1710034065", "0965555555"]
    assert secuencias[0].inicio < secuencias[1].inicio
    assert secuencias[0].fin <= secuencias[1].inicio


def test_une_telefono_dictado_en_grupos() -> None:
    """«0965 555 555» es un solo número: el STT lo parte y hay que unirlo."""
    normalizado = normalizar_texto("Hay que enviarle al 0965 555 555")
    assert normalizado == "Hay que enviarle al 0965555555"
    (secuencia,) = extraer_secuencias(normalizado)
    assert secuencia.digitos == "0965555555"
    assert secuencia.tipo == "TELEFONO"


def test_une_telefono_dictado_con_guiones() -> None:
    """«0963-444-444» también es un solo número."""
    normalizado = normalizar_texto("el telefono es 0963-444-444")
    assert normalizado == "el telefono es 0963444444"
    (telefono,) = extraer_secuencias(normalizado)
    assert telefono.tipo == "TELEFONO"
    assert telefono.digitos == "0963444444"


def test_une_cedula_dictada_en_tres_grupos_sin_corregirla() -> None:
    normalizado = normalizar_texto("la cedula es 110256 153 1")
    (secuencia,) = extraer_secuencias(normalizado)
    assert secuencia.digitos == "1102561531"
    assert secuencia.tipo == "CEDULA"
    assert secuencia.checksum_valido is False


def test_no_une_cantidades_sueltas() -> None:
    normalizado = normalizar_texto("quiero 10 20 30 sacos")
    assert normalizado == "quiero 10 20 30 sacos"
    assert [s.digitos for s in extraer_secuencias(normalizado)] == [
        "10",
        "20",
        "30",
    ]


# ---------------------------------------------------------------------------
# Frase completa del Caso A
# ---------------------------------------------------------------------------
def test_frase_del_caso_a_conserva_datos_y_marca_lo_dudoso() -> None:
    crudo = (
        "Crea un cliente llamado Jorge Bailon con cedula 110256 que mas 1531, "
        "es del coca y quiere veinticinco cubos para el proximo sabado, "
        "el telefono es 0965555555 y ya me dio 1000 dolares de abono"
    )
    normalizado = normalizar_texto(crudo)
    assert "25 m3" in normalizado
    assert "1000 USD" in normalizado
    assert "El Coca" in normalizado

    secuencias = extraer_secuencias(normalizado)
    por_tipo = {s.tipo: s for s in secuencias}
    assert por_tipo["CEDULA"].digitos == "1102561531"
    assert por_tipo["CEDULA"].checksum_valido is False
    assert por_tipo["TELEFONO"].digitos == "0965555555"
