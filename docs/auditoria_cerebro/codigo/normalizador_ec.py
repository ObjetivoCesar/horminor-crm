"""Normalización determinística de español ecuatoriano **con mapa de alineación**.

El texto que llega del STT trae números en palabras, cédulas partidas en tramos
y unidades coloquiales. Normalizar cambia el texto, así que para poder citar la
evidencia hace falta algo más que la cadena final: cada pieza de la salida debe
saber de qué caracteres del texto crudo salió y, cuando hay palabras del STT,
qué palabras y qué milisegundos la sostienen.

Reglas duras:

* el normalizador no corrige dígitos: si el verificador de cédula no cuadra, se
  marca y el borrador pregunta;
* un número solo es «sostenido» si su secuencia se puede alinear con palabras
  del STT; si no, queda sin ventana y no se puede confirmar con un clic.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Vocabulario numérico
# ---------------------------------------------------------------------------

_UNIDADES: dict[str, int] = {
    "cero": 0,
    "uno": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "once": 11,
    "doce": 12,
    "trece": 13,
    "catorce": 14,
    "quince": 15,
    "dieciseis": 16,
    "diecisiete": 17,
    "dieciocho": 18,
    "diecinueve": 19,
    "veinte": 20,
    "veintiuno": 21,
    "veintiun": 21,
    "veintiuna": 21,
    "veintidos": 22,
    "veintitres": 23,
    "veinticuatro": 24,
    "veinticinco": 25,
    "veintiseis": 26,
    "veintisiete": 27,
    "veintiocho": 28,
    "veintinueve": 29,
    "treinta": 30,
    "cuarenta": 40,
    "cincuenta": 50,
    "sesenta": 60,
    "setenta": 70,
    "ochenta": 80,
    "noventa": 90,
    "cien": 100,
    "ciento": 100,
    "doscientos": 200,
    "doscientas": 200,
    "trescientos": 300,
    "trescientas": 300,
    "cuatrocientos": 400,
    "cuatrocientas": 400,
    "quinientos": 500,
    "quinientas": 500,
    "seiscientos": 600,
    "seiscientas": 600,
    "setecientos": 700,
    "setecientas": 700,
    "ochocientos": 800,
    "ochocientas": 800,
    "novecientos": 900,
    "novecientas": 900,
}

_MULTIPLOS: dict[str, int] = {
    "mil": 1_000,
    "millon": 1_000_000,
    "millones": 1_000_000,
}
_NUMEROS: dict[str, int] = {**_UNIDADES, **_MULTIPLOS}
_ARTICULOS_UNO = {"un", "una"}

_TOKEN = re.compile(r"[0-9]+|[^\W\d_]+|\s+|[^\w\s]", re.UNICODE)

# Volumen del negocio. "metros" a secas no se toca: puede ser distancia.
_M3_PEGADO = re.compile(r"(?i)(\d+)\s*(m3|m³)")
_M3 = re.compile(
    r"(?i)(?<![\w])(?:metros?\s+c[uú]bicos?|cubos?|m3|m³)(?![\w])"
)
_MONEDA = re.compile(
    r"(?i)(?<![\w])(\d[\d.,]*)\s*(?:d[oó]lares?|usd)(?![\w])"
)

# Tramos dictados con un conector explícito. Sin conector no se unen.
_TRAMO = re.compile(
    r"(?<!\d)(\d{3,})\s*(?:que\s+m[aá]s|guioncito|guion|gion)\s*(\d{2,})(?!\d)",
    re.IGNORECASE,
)
_NUMERO = re.compile(r"(?<![A-Za-z])\d[\d.,]*")

_ALIAS_CIUDADES_DEFECTO: dict[str, str] = {
    "en el coca": "en El Coca",
    "del coca": "de El Coca",
    "el coca": "El Coca",
}

_COEFICIENTES_CEDULA = (2, 1, 2, 1, 2, 1, 2, 1, 2)


# ---------------------------------------------------------------------------
# Piezas de la salida
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TokenNormalizado:
    """Pieza de la salida normalizada y su origen en el texto crudo."""

    texto: str
    inicio: int
    fin: int
    crudo_inicio: int
    crudo_fin: int
    tipo: str  # NUMERO | UNIDAD | MONEDA | ALIAS | TEXTO | ESPACIO | PUNTUACION


@dataclass(frozen=True)
class TextoNormalizado:
    texto: str
    tokens: tuple[TokenNormalizado, ...]


@dataclass(frozen=True)
class SecuenciaNumerica:
    """Número encontrado en el texto normalizado."""

    texto_origen: str
    digitos: str
    inicio: int
    fin: int
    tipo: str
    checksum_valido: bool | None = None


@dataclass(frozen=True)
class PalabraSTT:
    """Palabra del proveedor con su posición en el texto crudo y sus tiempos.

    ``inicio``/``fin`` son offsets de carácter en el texto crudo; ``start_ms`` y
    ``end_ms`` son los tiempos del audio.
    """

    texto: str
    inicio: int
    fin: int
    start_ms: int | None = None
    end_ms: int | None = None
    confianza: float | None = None


@dataclass(frozen=True)
class PalabraAlineada:
    token: TokenNormalizado
    palabras: tuple[int, ...]
    palabras_dato: tuple[int, ...]
    start_ms: int | None
    end_ms: int | None
    confianza_minima: float | None


@dataclass(frozen=True)
class SecuenciaAlineada:
    """Secuencia numérica con su cita cruda y su ventana de audio."""

    digitos: str
    tipo: str
    checksum_valido: bool | None
    texto_origen: str
    crudo_inicio: int
    crudo_fin: int
    palabras: tuple[int, ...]
    palabras_dato: tuple[int, ...]
    start_ms: int | None
    end_ms: int | None
    confianza_minima: float | None


@dataclass(frozen=True)
class _Seg:
    texto: str
    crudo_inicio: int
    crudo_fin: int
    tipo: str


# ---------------------------------------------------------------------------
# Ayudas de vocabulario
# ---------------------------------------------------------------------------
def _sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def _es_numero(token: str) -> bool:
    return _sin_tildes(token) in _NUMEROS


def _es_multiplo(token: str) -> bool:
    return _sin_tildes(token) in _MULTIPLOS


def _es_articulo(token: str) -> bool:
    return _sin_tildes(token) in _ARTICULOS_UNO


def _es_y(token: str) -> bool:
    return _sin_tildes(token) == "y"


def _es_conector(token: str) -> bool:
    """Conector de un tramo dictado, no parte del dato."""
    return _sin_tildes(token) in {"que", "mas", "guion", "guioncito", "gion", "y"}


def _valor(tokens: Sequence[str]) -> int:
    total = 0
    acumulado = 0
    for token in tokens:
        palabra = _sin_tildes(token)
        if _es_articulo(token):
            continue
        if palabra == "mil":
            total += (acumulado or 1) * _MULTIPLOS["mil"]
            acumulado = 0
        elif palabra in ("millon", "millones"):
            total += (acumulado or 1) * _MULTIPLOS[palabra]
            acumulado = 0
        else:
            acumulado += _NUMEROS[palabra]
    return total + acumulado


def _siguiente_no_espacio(tokens: Sequence[re.Match[str]], desde: int) -> int | None:
    for indice in range(desde, len(tokens)):
        if not tokens[indice].group(0).isspace():
            return indice
    return None


def _separador_identificador(segmento: "_Seg") -> bool:
    """Espacio o guion entre grupos de un mismo numero dictado."""
    if segmento.tipo == "ESPACIO":
        return True
    return segmento.tipo == "PUNTUACION" and segmento.texto in ("-", "–", "—")


# ---------------------------------------------------------------------------
# Segmentos con origen crudo
# ---------------------------------------------------------------------------
def _unir_multiplos(segmentos: list[_Seg]) -> list[_Seg]:
    """«27 mil» dicho con dígitos y palabra es 27000, no dos números.

    El transcriptor mezcla cifras y palabras («27 mil dólares», «1 millón»).
    Solo se multiplica cuando el número está seguido por un multiplicador
    suelto; una lista de cantidades («10 20 30») no se toca.
    """
    salida: list[_Seg] = []
    i = 0
    while i < len(segmentos):
        actual = segmentos[i]
        if actual.tipo == "NUMERO" and actual.texto.isdigit():
            valor = int(actual.texto)
            j = i
            k = i + 1
            while k < len(segmentos) and segmentos[k].tipo == "ESPACIO":
                k += 1
            if (
                k < len(segmentos)
                and segmentos[k].tipo == "MULTIPLO"
                and segmentos[k].texto.isdigit()
            ):
                valor *= int(segmentos[k].texto)
                j = k
                k += 1
                while k < len(segmentos) and segmentos[k].tipo == "ESPACIO":
                    k += 1
                # «27 mil 500»: el grupo de tres dígitos es la cola.
                if (
                    k < len(segmentos)
                    and segmentos[k].tipo == "NUMERO"
                    and segmentos[k].texto.isdigit()
                    and len(segmentos[k].texto) == 3
                ):
                    valor += int(segmentos[k].texto)
                    j = k
            if j > i:
                salida.append(
                    _Seg(
                        str(valor),
                        actual.crudo_inicio,
                        segmentos[j].crudo_fin,
                        "NUMERO",
                    )
                )
                i = j + 1
                continue
        salida.append(actual)
        i += 1
    return salida


def _unir_identificadores(segmentos: list[_Seg]) -> list[_Seg]:
    """Une grupos de dígitos dictados por separado («0965 555 555»).

    Solo se une cuando el número completo es un teléfono o una cédula: unir
    cantidades sueltas («10 20 30») inventaría una identificación que nadie
    dijo. Si la cédula unida no pasa el verificador, se conserva igual y queda
    marcada para preguntar; el normalizador no corrige dígitos.
    """
    salida: list[_Seg] = []
    i = 0
    while i < len(segmentos):
        actual = segmentos[i]
        if actual.tipo != "NUMERO" or not actual.texto.isdigit():
            salida.append(actual)
            i += 1
            continue

        grupos = [actual.texto]
        ultimo = i
        j = i
        while j + 1 < len(segmentos):
            k = j + 1
            while k < len(segmentos) and _separador_identificador(segmentos[k]):
                k += 1
            if k >= len(segmentos):
                break
            siguiente = segmentos[k]
            if siguiente.tipo != "NUMERO" or not siguiente.texto.isdigit():
                break
            grupos.append(siguiente.texto)
            j = k
            ultimo = k

        digitos = "".join(grupos)
        if len(grupos) > 1 and _clasificar(digitos) in ("TELEFONO", "CEDULA"):
            salida.append(
                _Seg(
                    digitos,
                    segmentos[i].crudo_inicio,
                    segmentos[ultimo].crudo_fin,
                    "NUMERO",
                )
            )
            i = ultimo + 1
            continue

        salida.append(actual)
        i += 1
    return salida


def _segmentos(texto: str) -> list[_Seg]:
    tokens = list(_TOKEN.finditer(texto))
    salida: list[_Seg] = []
    i = 0
    while i < len(tokens):
        actual = tokens[i]
        valor = actual.group(0)
        arranca = _es_numero(valor)
        if not arranca and _es_articulo(valor):
            siguiente = _siguiente_no_espacio(tokens, i + 1)
            arranca = siguiente is not None and _es_multiplo(
                tokens[siguiente].group(0)
            )
        if arranca:
            j = i
            corrida: list[str] = []
            ultimo = i
            while j < len(tokens):
                pieza = tokens[j].group(0)
                if _es_numero(pieza) or _es_articulo(pieza) or _es_multiplo(pieza):
                    corrida.append(pieza)
                    ultimo = j
                    j += 1
                    continue
                if pieza.isspace():
                    siguiente = _siguiente_no_espacio(tokens, j + 1)
                    if siguiente is not None and (
                        _es_numero(tokens[siguiente].group(0))
                        or _es_articulo(tokens[siguiente].group(0))
                        or _es_multiplo(tokens[siguiente].group(0))
                    ):
                        j = siguiente
                        continue
                    if siguiente is not None and _es_y(tokens[siguiente].group(0)):
                        despues = _siguiente_no_espacio(tokens, siguiente + 1)
                        if despues is not None and _es_numero(
                            tokens[despues].group(0)
                        ):
                            j = despues
                            continue
                    break
                if _es_y(pieza):
                    siguiente = _siguiente_no_espacio(tokens, j + 1)
                    if siguiente is not None and _es_numero(
                        tokens[siguiente].group(0)
                    ):
                        j = siguiente
                        continue
                    break
                break
            if any(_es_numero(t) or _es_multiplo(t) for t in corrida):
                tipo = (
                    "MULTIPLO"
                    if len(corrida) == 1 and _es_multiplo(corrida[0])
                    else "NUMERO"
                )
                salida.append(
                    _Seg(
                        str(_valor(corrida)),
                        actual.start(),
                        tokens[ultimo].end(),
                        tipo,
                    )
                )
                i = j
                continue
        if valor.isspace():
            tipo = "ESPACIO"
        elif valor.isdigit():
            tipo = "NUMERO"
        elif not any(c.isalnum() for c in valor):
            tipo = "PUNTUACION"
        else:
            tipo = "TEXTO"
        salida.append(_Seg(valor, actual.start(), actual.end(), tipo))
        i += 1
    return _unir_identificadores(_unir_multiplos(salida))


def _aplicar(
    segmentos: list[_Seg],
    patron: re.Pattern[str],
    reemplazo: Any,
    tipo: str,
) -> list[_Seg]:
    """Aplica un patrón solo si el match cae en bordes de segmento.

    Si el match empieza o termina dentro de un segmento no se transforma: es
    preferible no normalizar que inventar un origen.
    """
    texto = "".join(seg.texto for seg in segmentos)
    limites: list[tuple[int, int]] = []
    posicion = 0
    for seg in segmentos:
        limites.append((posicion, posicion + len(seg.texto)))
        posicion += len(seg.texto)

    rangos: list[tuple[re.Match[str], int, int]] = []
    for match in patron.finditer(texto):
        cubiertos = [
            indice
            for indice, (inicio, fin) in enumerate(limites)
            if inicio < match.end() and fin > match.start()
        ]
        if not cubiertos:
            continue
        primero, ultimo = cubiertos[0], cubiertos[-1]
        if match.start() != limites[primero][0] or match.end() != limites[ultimo][1]:
            continue
        rangos.append((match, primero, ultimo))

    if not rangos:
        return segmentos

    salida: list[_Seg] = []
    indice_rango = 0
    k = 0
    while k < len(segmentos):
        if indice_rango < len(rangos) and k == rangos[indice_rango][1]:
            match, primero, ultimo = rangos[indice_rango]
            salida.append(
                _Seg(
                    reemplazo(match),
                    segmentos[primero].crudo_inicio,
                    segmentos[ultimo].crudo_fin,
                    tipo,
                )
            )
            k = ultimo + 1
            indice_rango += 1
            continue
        salida.append(segmentos[k])
        k += 1
    return salida


def _aplicar_alias(segmentos: list[_Seg], alias: Mapping[str, str]) -> list[_Seg]:
    for clave in sorted(alias, key=len, reverse=True):
        patron = re.compile(r"(?i)(?<!\w)" + re.escape(clave) + r"(?!\w)")
        destino = alias[clave]
        segmentos = _aplicar(
            segmentos,
            patron,
            lambda _match, valor=destino: valor,
            "ALIAS",
        )
    return segmentos


# ---------------------------------------------------------------------------
# Normalización con mapa
# ---------------------------------------------------------------------------
def normalizar_con_mapa(
    texto: str,
    *,
    alias_ciudades: Mapping[str, str] | None = None,
) -> TextoNormalizado:
    """Normaliza y devuelve cada pieza con su origen en el texto crudo."""
    if not texto:
        return TextoNormalizado("", ())

    segmentos = _segmentos(texto)
    segmentos = _aplicar(
        segmentos,
        _TRAMO,
        lambda match: f"{match.group(1)}{match.group(2)}",
        "NUMERO",
    )
    segmentos = _aplicar(
        segmentos, _M3_PEGADO, lambda match: f"{match.group(1)} m3", "UNIDAD"
    )
    segmentos = _aplicar(segmentos, _M3, lambda _match: "m3", "UNIDAD")
    segmentos = _aplicar(
        segmentos, _MONEDA, lambda match: f"{match.group(1)} USD", "MONEDA"
    )
    segmentos = _aplicar_alias(
        segmentos,
        alias_ciudades if alias_ciudades is not None else _ALIAS_CIUDADES_DEFECTO,
    )

    salida = "".join(seg.texto for seg in segmentos)
    tokens: list[TokenNormalizado] = []
    posicion = 0
    for seg in segmentos:
        tokens.append(
            TokenNormalizado(
                texto=seg.texto,
                inicio=posicion,
                fin=posicion + len(seg.texto),
                crudo_inicio=seg.crudo_inicio,
                crudo_fin=seg.crudo_fin,
                tipo=seg.tipo,
            )
        )
        posicion += len(seg.texto)
    return TextoNormalizado(salida, tuple(tokens))


def normalizar_texto(
    texto: str,
    *,
    alias_ciudades: Mapping[str, str] | None = None,
) -> str:
    """Devuelve solo el texto normalizado (compatibilidad con la Fase 1)."""
    return normalizar_con_mapa(texto, alias_ciudades=alias_ciudades).texto


def normalizar_numero_hablado(texto: str) -> str | None:
    if not texto or not texto.strip():
        return None
    tokens = [t for t in _TOKEN.findall(texto) if not t.isspace()]
    if not tokens:
        return None
    if any(re.fullmatch(r"[0-9]+", t) for t in tokens):
        return None
    for token in tokens:
        if not (_es_numero(token) or _es_y(token)):
            return None
    if not any(_es_numero(t) or _es_multiplo(t) for t in tokens):
        return None
    return str(_valor(tokens))


def cedula_valida(digitos: str) -> bool:
    if len(digitos) != 10 or not digitos.isdigit():
        return False
    provincia = int(digitos[:2])
    if not 1 <= provincia <= 24:
        return False
    total = 0
    for digito, coeficiente in zip(digitos[:9], _COEFICIENTES_CEDULA):
        producto = int(digito) * coeficiente
        if producto > 9:
            producto -= 9
        total += producto
    verificador = (10 - total % 10) % 10
    return verificador == int(digitos[9])


def _clasificar(digitos: str) -> str:
    if len(digitos) == 10:
        if digitos.startswith("09"):
            return "TELEFONO"
        if 1 <= int(digitos[:2]) <= 24:
            return "CEDULA"
        return "DESCONOCIDO"
    if len(digitos) == 9 and digitos.startswith("9"):
        return "TELEFONO"
    if 1 <= len(digitos) <= 6:
        return "CANTIDAD"
    return "DESCONOCIDO"


def extraer_secuencias(texto: str) -> list[SecuenciaNumerica]:
    """Números del texto normalizado, con tramos dictados ya unidos."""
    if not texto:
        return []

    encontradas: list[SecuenciaNumerica] = []
    ocupados: list[tuple[int, int]] = []

    for coincidencia in _TRAMO.finditer(texto):
        digitos = coincidencia.group(1) + coincidencia.group(2)
        tipo = _clasificar(digitos)
        encontradas.append(
            SecuenciaNumerica(
                texto_origen=coincidencia.group(0),
                digitos=digitos,
                inicio=coincidencia.start(),
                fin=coincidencia.end(),
                tipo=tipo,
                checksum_valido=cedula_valida(digitos) if tipo == "CEDULA" else None,
            )
        )
        ocupados.append((coincidencia.start(), coincidencia.end()))

    for coincidencia in _NUMERO.finditer(texto):
        if any(
            coincidencia.start() < fin and inicio < coincidencia.end()
            for inicio, fin in ocupados
        ):
            continue
        digitos = re.sub(r"\D", "", coincidencia.group(0))
        if not digitos:
            continue
        tipo = _clasificar(digitos)
        encontradas.append(
            SecuenciaNumerica(
                texto_origen=coincidencia.group(0),
                digitos=digitos,
                inicio=coincidencia.start(),
                fin=coincidencia.end(),
                tipo=tipo,
                checksum_valido=cedula_valida(digitos) if tipo == "CEDULA" else None,
            )
        )

    encontradas.sort(key=lambda secuencia: secuencia.inicio)
    return encontradas


# ---------------------------------------------------------------------------
# Alineación con palabras del STT
# ---------------------------------------------------------------------------
def localizar_palabras(
    texto_crudo: str, palabras: Sequence[Any]
) -> tuple[PalabraSTT, ...]:
    """Convierte la salida del STT en palabras con offsets de carácter.

    Acepta ``PalabraSTT`` ya construidas o diccionarios con ``palabra``/``texto``
    y ``inicio_ms``/``start_ms``, ``fin_ms``/``end_ms``, ``confianza``.
    """
    salida: list[PalabraSTT] = []
    cursor = 0
    for item in palabras:
        if isinstance(item, PalabraSTT):
            salida.append(item)
            continue
        if not isinstance(item, Mapping):
            continue
        palabra = str(
            item.get("palabra") or item.get("texto") or item.get("word") or ""
        ).strip()
        if not palabra:
            continue
        indice = texto_crudo.find(palabra, cursor)
        if indice < 0:
            indice = texto_crudo.lower().find(palabra.lower(), cursor)
        if indice < 0:
            continue
        cursor = indice + len(palabra)
        salida.append(
            PalabraSTT(
                texto=palabra,
                inicio=indice,
                fin=indice + len(palabra),
                start_ms=_entero(item.get("inicio_ms", item.get("start_ms"))),
                end_ms=_entero(item.get("fin_ms", item.get("end_ms"))),
                confianza=_flotante(item.get("confianza", item.get("confidence"))),
            )
        )
    return tuple(salida)


def _entero(valor: Any) -> int | None:
    if valor is None:
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _flotante(valor: Any) -> float | None:
    if valor is None:
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _palabra_es_dato(palabra: PalabraSTT) -> bool:
    texto = palabra.texto.strip()
    return (
        any(caracter.isdigit() for caracter in texto)
        or _es_numero(texto)
        or _es_articulo(texto)
        or _es_multiplo(texto)
    )


def _ventana(
    palabras: Sequence[PalabraSTT], indices: Sequence[int]
) -> tuple[int | None, int | None, float | None]:
    inicios = [
        palabras[i].start_ms for i in indices if palabras[i].start_ms is not None
    ]
    fines = [palabras[i].end_ms for i in indices if palabras[i].end_ms is not None]
    confianzas = [
        palabras[i].confianza
        for i in indices
        if palabras[i].confianza is not None
    ]
    return (
        min(inicios) if inicios else None,
        max(fines) if fines else None,
        min(confianzas) if confianzas else None,
    )


def alinear_con_palabras(
    mapa: TextoNormalizado, palabras: Sequence[PalabraSTT]
) -> tuple[PalabraAlineada, ...]:
    """Ata cada token de la salida a las palabras del STT que lo sostienen."""
    salida: list[PalabraAlineada] = []
    for token in mapa.tokens:
        if token.tipo in ("ESPACIO", "PUNTUACION") or not token.texto.strip():
            salida.append(PalabraAlineada(token, (), (), None, None, None))
            continue
        indices = tuple(
            indice
            for indice, palabra in enumerate(palabras)
            if palabra.fin > token.crudo_inicio and palabra.inicio < token.crudo_fin
        )
        dato = tuple(
            indice
            for indice in indices
            if _palabra_es_dato(palabras[indice])
        )
        base = dato or indices
        inicio, fin, confianza = _ventana(palabras, base)
        salida.append(
            PalabraAlineada(token, indices, dato, inicio, fin, confianza)
        )
    return tuple(salida)


def alinear_secuencias(
    mapa: TextoNormalizado, palabras: Sequence[PalabraSTT]
) -> tuple[SecuenciaAlineada, ...]:
    """Alinea las secuencias numéricas (incluida la cédula unida) con el audio."""
    salida: list[SecuenciaAlineada] = []
    for secuencia in extraer_secuencias(mapa.texto):
        cubiertos = [
            token
            for token in mapa.tokens
            if token.tipo not in ("ESPACIO", "PUNTUACION")
            and token.inicio < secuencia.fin
            and token.fin > secuencia.inicio
        ]
        if not cubiertos:
            continue
        crudo_inicio = min(token.crudo_inicio for token in cubiertos)
        crudo_fin = max(token.crudo_fin for token in cubiertos)
        indices = tuple(
            indice
            for indice, palabra in enumerate(palabras)
            if palabra.fin > crudo_inicio and palabra.inicio < crudo_fin
        )
        dato = tuple(
            indice
            for indice in indices
            if _palabra_es_dato(palabras[indice]) and not _es_conector(palabras[indice].texto)
        )
        base = dato or indices
        inicio, fin, confianza = _ventana(palabras, base)
        salida.append(
            SecuenciaAlineada(
                digitos=secuencia.digitos,
                tipo=secuencia.tipo,
                checksum_valido=secuencia.checksum_valido,
                texto_origen=secuencia.texto_origen,
                crudo_inicio=crudo_inicio,
                crudo_fin=crudo_fin,
                palabras=indices,
                palabras_dato=dato,
                start_ms=inicio,
                end_ms=fin,
                confianza_minima=confianza,
            )
        )
    return tuple(salida)


def normalizar_alineado(
    texto_crudo: str,
    palabras: Sequence[Any],
    *,
    alias_ciudades: Mapping[str, str] | None = None,
) -> tuple[str, tuple[SecuenciaAlineada, ...]]:
    """Atajo: texto normalizado + secuencias numéricas con su ventana de audio."""
    mapa = normalizar_con_mapa(texto_crudo, alias_ciudades=alias_ciudades)
    localizadas = localizar_palabras(texto_crudo, palabras)
    return mapa.texto, alinear_secuencias(mapa, localizadas)
