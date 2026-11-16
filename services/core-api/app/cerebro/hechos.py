"""Hechos citados: el dato, su cita y la ventana de audio que lo sostiene.

Un hecho no es un valor suelto. Si no se puede señalar la frase y el instante,
no es un hecho: es una sospecha del modelo y no se compila.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ..voz import SecuenciaAlineada, TokenNormalizado
from .tiempo import hora_de_cita, hora_explicita, normalizar_hora

ESTADOS = (
    "EXTRAIDO",
    "INFERIDO",
    "TENTATIVO",
    "NO_DIJO",
    "INAUDIBLE_NO_ENTENDI",
    "BAJA_CONFIANZA_STT",
    "CORREGIDO_EN_AUDIO",
    "CORREGIDO_POR_HUMANO",
)
TIPOS = (
    "TEXTO",
    "ENTERO",
    "DECIMAL",
    "FECHA",
    "HORA",
    "TELEFONO",
    "CEDULA",
    "BOOLEANO",
)
HABLANTES = (
    "SUPERADMIN",
    "SECRETARIA",
    "VENDEDOR",
    "CONTADORA",
    "CHOFER",
    "CLIENTE",
    "TERCERO",
    "NO_DETERMINADO",
)
_ESTADOS_CON_VALOR = (
    "EXTRAIDO",
    "INFERIDO",
    "TENTATIVO",
    "BAJA_CONFIANZA_STT",
    "CORREGIDO_EN_AUDIO",
    "CORREGIDO_POR_HUMANO",
)


@dataclass(frozen=True)
class Evidencia:
    """Cita cruda y texto normalizado que sostienen el valor."""

    cita: str
    sostiene: str
    crudo_inicio: int
    crudo_fin: int
    start_ms: int | None
    end_ms: int | None
    confianza: float | None
    hablante: str


@dataclass(frozen=True)
class HechoCitado:
    clave: str
    valor: Any
    estado: str
    tipo: str = "TEXTO"
    evidencia: Evidencia | None = None
    checksum_valido: bool | None = None

    @property
    def utilizable(self) -> bool:
        """Un hecho tentativo no se usa para decidir: acompaña y se pregunta."""
        return (
            self.estado in _ESTADOS_CON_VALOR
            and self.estado != "TENTATIVO"
            and self.valor not in (None, "")
        )

    @property
    def es_tentativo(self) -> bool:
        return self.estado == "TENTATIVO"

    def a_dict(self) -> dict[str, Any]:
        evidencia = None
        if self.evidencia is not None:
            evidencia = {
                "cita": self.evidencia.cita,
                "sostiene": self.evidencia.sostiene,
                "crudo_inicio": self.evidencia.crudo_inicio,
                "crudo_fin": self.evidencia.crudo_fin,
                "start_ms": self.evidencia.start_ms,
                "end_ms": self.evidencia.end_ms,
                "confianza": self.evidencia.confianza,
                "hablante": self.evidencia.hablante,
            }
        valor = self.valor
        if isinstance(valor, Decimal):
            valor = str(valor)
        elif isinstance(valor, (date, datetime)):
            valor = valor.isoformat()
        return {
            "clave": self.clave,
            "valor": valor,
            "estado": self.estado,
            "tipo": self.tipo,
            "evidencia": evidencia,
            "checksum_valido": self.checksum_valido,
        }


def _sin_tildes(texto: str) -> str:
    normal = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in normal if unicodedata.category(c) != "Mn").lower()


def _digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def desde_secuencia(
    clave: str,
    secuencia: SecuenciaAlineada,
    texto_crudo: str,
    *,
    hablante: str,
    tipo: str | None = None,
    estado: str = "EXTRAIDO",
) -> HechoCitado:
    """Construye un hecho numérico desde una secuencia alineada."""
    if tipo is None:
        tipo = {"CEDULA": "CEDULA", "TELEFONO": "TELEFONO"}.get(
            secuencia.tipo, "ENTERO"
        )
    if tipo in ("CEDULA", "TELEFONO"):
        valor: Any = secuencia.digitos
    else:
        valor = int(secuencia.digitos)
    evidencia = Evidencia(
        cita=texto_crudo[secuencia.crudo_inicio : secuencia.crudo_fin],
        sostiene=secuencia.texto_origen,
        crudo_inicio=secuencia.crudo_inicio,
        crudo_fin=secuencia.crudo_fin,
        start_ms=secuencia.start_ms,
        end_ms=secuencia.end_ms,
        confianza=secuencia.confianza_minima,
        hablante=hablante,
    )
    return HechoCitado(
        clave=clave,
        valor=valor,
        estado=estado,
        tipo=tipo,
        evidencia=evidencia,
        checksum_valido=secuencia.checksum_valido,
    )


def desde_token(
    clave: str,
    token: TokenNormalizado,
    valor: Any,
    texto_crudo: str,
    *,
    hablante: str,
    tipo: str = "TEXTO",
    estado: str = "EXTRAIDO",
    start_ms: int | None = None,
    end_ms: int | None = None,
    confianza: float | None = None,
) -> HechoCitado:
    """Construye un hecho de texto desde un token con origen crudo."""
    evidencia = Evidencia(
        cita=texto_crudo[token.crudo_inicio : token.crudo_fin],
        sostiene=token.texto,
        crudo_inicio=token.crudo_inicio,
        crudo_fin=token.crudo_fin,
        start_ms=start_ms,
        end_ms=end_ms,
        confianza=confianza,
        hablante=hablante,
    )
    return HechoCitado(
        clave=clave,
        valor=valor,
        estado=estado,
        tipo=tipo,
        evidencia=evidencia,
    )


def no_dijo(clave: str, tipo: str = "TEXTO") -> HechoCitado:
    return HechoCitado(clave=clave, valor=None, estado="NO_DIJO", tipo=tipo)


def inaudible(clave: str, tipo: str = "TEXTO") -> HechoCitado:
    return HechoCitado(clave=clave, valor=None, estado="INAUDIBLE_NO_ENTENDI", tipo=tipo)


def validar_hecho(hecho: HechoCitado) -> list[str]:
    """Errores estructurales y de sostenibilidad del hecho."""
    errores: list[str] = []
    if not hecho.clave:
        errores.append("clave vacia")
    if hecho.estado not in ESTADOS:
        errores.append(f"estado invalido: {hecho.estado}")
    if hecho.tipo not in TIPOS:
        errores.append(f"tipo invalido: {hecho.tipo}")

    if hecho.estado not in _ESTADOS_CON_VALOR:
        if hecho.valor not in (None, ""):
            errores.append(f"{hecho.estado} no puede traer valor")
        return errores

    evidencia = hecho.evidencia
    if evidencia is None:
        if hecho.estado == "CORREGIDO_POR_HUMANO":
            # Un dato que Julio completa (p. ej. a quién enviar el recordatorio)
            # no viene del audio: no tiene cita, y fingir una sería inventar
            # evidencia. El estado lo declara.
            if hecho.valor in (None, ""):
                errores.append("correccion humana sin valor")
            return errores
        errores.append("un hecho con valor necesita evidencia")
        return errores
    if evidencia.crudo_fin <= evidencia.crudo_inicio:
        errores.append("span crudo invalido")
    if not evidencia.cita.strip():
        errores.append("cita vacia")
    if not evidencia.sostiene.strip():
        errores.append("texto de sosten vacio")
    if evidencia.confianza is not None and not 0 <= evidencia.confianza <= 1:
        errores.append("confianza fuera de rango")
    if evidencia.hablante not in HABLANTES:
        errores.append(f"hablante invalido: {evidencia.hablante}")

    # Una correccion humana es la autoridad: el dato se aparta de la cita a
    # proposito («Díaz Sur» transcrito, «Dualsur» dicho). Se validan estructura,
    # evidencia y tipo, pero no que el valor aparezca en el audio.
    if hecho.estado == "CORREGIDO_POR_HUMANO":
        return errores

    if hecho.tipo in ("CEDULA", "TELEFONO", "ENTERO", "DECIMAL"):
        esperado = _digitos(str(hecho.valor))
        sostenido = _digitos(evidencia.sostiene)
        if not esperado:
            errores.append("valor numerico vacio")
        elif esperado not in sostenido:
            errores.append(
                f"el valor {hecho.valor} no esta sostenido por la cita"
            )
    elif hecho.tipo == "HORA":
        esperado = normalizar_hora(hecho.valor)
        sostenida = hora_de_cita(evidencia.cita) or hora_explicita(evidencia.cita)
        if esperado is None:
            errores.append("hora invalida")
        elif sostenida != esperado:
            errores.append(f"la hora {hecho.valor} no esta sostenida por la cita")
    elif hecho.tipo == "TEXTO":
        # El nombre del cliente puede venir resuelto contra el catálogo
        # ("inge Reyes" -> "Ing. Reyes (prueba Hito 1)"); lo que debe existir
        # en el texto es la mención, no el nombre canónico.
        if hecho.clave == "cliente.nombre":
            return errores
        valor = _sin_tildes(str(hecho.valor)).strip()
        sosten = _sin_tildes(evidencia.sostiene).strip()
        if valor and valor not in sosten and sosten not in valor:
            errores.append("el texto no esta sostenido por la cita")
    return errores


def validar_hechos(hechos: list[HechoCitado]) -> list[str]:
    errores: list[str] = []
    for hecho in hechos:
        for error in validar_hecho(hecho):
            errores.append(f"{hecho.clave}: {error}")
    return errores


def decimal_utilizable(valor: Any) -> Decimal | None:
    """Convierte sin inventar: si no se puede, devuelve None."""
    if valor is None or valor == "":
        return None
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None
