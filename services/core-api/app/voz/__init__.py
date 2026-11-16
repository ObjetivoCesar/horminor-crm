"""Componente de voz: ingesta, normalización y alineación con el audio."""

from .normalizador_ec import (
    PalabraAlineada,
    PalabraSTT,
    SecuenciaAlineada,
    SecuenciaNumerica,
    TextoNormalizado,
    TokenNormalizado,
    alinear_con_palabras,
    alinear_secuencias,
    cedula_valida,
    extraer_secuencias,
    localizar_palabras,
    normalizar_alineado,
    normalizar_con_mapa,
    normalizar_numero_hablado,
    normalizar_texto,
)

__all__ = [
    "PalabraAlineada",
    "PalabraSTT",
    "SecuenciaAlineada",
    "SecuenciaNumerica",
    "TextoNormalizado",
    "TokenNormalizado",
    "alinear_con_palabras",
    "alinear_secuencias",
    "cedula_valida",
    "extraer_secuencias",
    "localizar_palabras",
    "normalizar_alineado",
    "normalizar_con_mapa",
    "normalizar_numero_hablado",
    "normalizar_texto",
]
