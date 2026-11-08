"""Modulo 2 - Dosificador determinista de planta.

Regla de oro: aqui NO hay IA. Solo aritmetica con Decimal.
Toda la informacion de negocio (recetas) llega desde la base de datos.

Si una receta no esta confirmada por el cliente, el motor se niega a
calcular (RecetaNoConfirmadaError) salvo que el llamador pida
explicitamente `permitir_provisional=True` (solo scripts de diagnostico).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping, Sequence

Q3 = Decimal("0.001")
Q2 = Decimal("0.01")

CAMPOS_RECETA = (
    "cemento_sacos_m3",
    "arena_m3_m3",
    "ripio_m3_m3",
    "agua_litros_m3",
    "retardante_litros_m3",
)

POLITICAS_VIAJE = ("ultimo_parcial", "ultimo_completo", "distribucion_uniforme")


class ErrorPlanta(ValueError):
    """Error de negocio del motor de planta."""


class RecetaNoConfirmadaError(ErrorPlanta):
    def __init__(self, resistencia: str, fuente: str | None = None) -> None:
        detalle = f" La fuente registrada es: {fuente}" if fuente else ""
        super().__init__(
            f"La receta {resistencia} no esta confirmada por el cliente; "
            f"el motor no calcula con datos provisionales.{detalle}"
        )


class RecetaIncompletaError(ErrorPlanta):
    def __init__(self, resistencia: str, faltantes: Sequence[str]) -> None:
        super().__init__(
            f"La receta {resistencia} no tiene los campos: {', '.join(faltantes)}"
        )
        self.faltantes = tuple(faltantes)


class VolumenInvalidoError(ErrorPlanta):
    pass


class PoliticaViajeInvalidaError(ErrorPlanta):
    pass


@dataclass(frozen=True)
class Receta:
    resistencia: str
    cemento_sacos_m3: Decimal | None
    arena_m3_m3: Decimal | None
    ripio_m3_m3: Decimal | None
    agua_litros_m3: Decimal | None
    retardante_litros_m3: Decimal | None
    saco_kg: Decimal | None
    confirmado: bool
    fuente: str | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Receta":
        def d(key: str) -> Decimal | None:
            value = row.get(key)
            return None if value is None else Decimal(str(value))

        return cls(
            resistencia=row["resistencia"],
            cemento_sacos_m3=d("cemento_sacos_m3"),
            arena_m3_m3=d("arena_m3_m3"),
            ripio_m3_m3=d("ripio_m3_m3"),
            agua_litros_m3=d("agua_litros_m3"),
            retardante_litros_m3=d("retardante_litros_m3"),
            saco_kg=d("saco_kg"),
            confirmado=bool(row["confirmado"]),
            fuente=row.get("fuente"),
        )

    def faltantes(self) -> list[str]:
        return [campo for campo in CAMPOS_RECETA if getattr(self, campo) is None]


@dataclass(frozen=True)
class Consumo:
    resistencia: str
    volumen_m3: Decimal
    cemento_sacos: Decimal
    arena_m3: Decimal | None
    ripio_m3: Decimal | None
    agua_litros: Decimal | None
    retardante_litros: Decimal | None
    campos_faltantes: tuple[str, ...]
    provisional: bool

    def a_payload(self) -> dict[str, Any]:
        """Formato del contrato tracking_payload.consumo_materiales."""

        def num(value: Decimal | None) -> float | None:
            return None if value is None else float(value)

        return {
            "cemento_sacos_teorico": num(self.cemento_sacos),
            "cemento_sacos_real": None,
            "retardante_litros": num(self.retardante_litros),
            "arena_m3": num(self.arena_m3),
            "ripio_m3": num(self.ripio_m3),
            "agua_litros": num(self.agua_litros),
            "provisional": self.provisional,
            "campos_faltantes": list(self.campos_faltantes),
        }


@dataclass(frozen=True)
class PlanViajes:
    volumen_total_m3: Decimal
    capacidad_m3: Decimal
    politica: str
    viajes: tuple[Decimal, ...]
    excedente_m3: Decimal

    @property
    def total_viajes(self) -> int:
        return len(self.viajes)


def _q3(value: Decimal) -> Decimal:
    return value.quantize(Q3, rounding=ROUND_HALF_UP)


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def calcular_consumo(
    receta: Receta,
    volumen_m3: Decimal | float | str,
    *,
    permitir_provisional: bool = False,
) -> Consumo:
    """Multiplica la receta por el volumen. Cero IA, cero redondeos ocultos."""
    volumen = _decimal(volumen_m3)
    if volumen <= 0:
        raise VolumenInvalidoError("El volumen debe ser mayor que 0 m3")

    if not receta.confirmado and not permitir_provisional:
        raise RecetaNoConfirmadaError(receta.resistencia, receta.fuente)

    if receta.cemento_sacos_m3 is None:
        raise RecetaIncompletaError(receta.resistencia, receta.faltantes())

    def mul(base: Decimal | None) -> Decimal | None:
        return None if base is None else _q3(base * volumen)

    return Consumo(
        resistencia=receta.resistencia,
        volumen_m3=volumen,
        cemento_sacos=mul(receta.cemento_sacos_m3) or Decimal("0"),
        arena_m3=mul(receta.arena_m3_m3),
        ripio_m3=mul(receta.ripio_m3_m3),
        agua_litros=mul(receta.agua_litros_m3),
        retardante_litros=mul(receta.retardante_litros_m3),
        campos_faltantes=tuple(receta.faltantes()),
        provisional=not receta.confirmado,
    )


def dividir_en_viajes(
    volumen_m3: Decimal | float | str,
    capacidad_m3: Decimal | float | str,
    politica: str = "ultimo_parcial",
) -> PlanViajes:
    """Divide una orden en viajes de mixer.

    Politicas:
    - ultimo_parcial: viajes llenos + un ultimo viaje con el resto (default).
    - ultimo_completo: el ultimo viaje se redondea a la capacidad del mixer
      y el volumen sobrante se reporta en `excedente_m3`.
    - distribucion_uniforme: reparte el volumen en N viajes iguales.
    """
    volumen = _decimal(volumen_m3)
    capacidad = _decimal(capacidad_m3)
    if volumen <= 0:
        raise VolumenInvalidoError("El volumen debe ser mayor que 0 m3")
    if capacidad <= 0:
        raise VolumenInvalidoError("La capacidad del mixer debe ser mayor que 0 m3")
    if politica not in POLITICAS_VIAJE:
        raise PoliticaViajeInvalidaError(
            f"Politica '{politica}' no valida. Use una de: {', '.join(POLITICAS_VIAJE)}"
        )

    llenos = int(volumen // capacidad)
    resto = _q3(volumen - (capacidad * llenos))
    excedente = Decimal("0")

    if resto == 0:
        return PlanViajes(volumen, capacidad, politica, tuple([capacidad] * llenos), excedente)

    if politica == "ultimo_parcial":
        viajes = tuple([capacidad] * llenos + [resto])
    elif politica == "ultimo_completo":
        excedente = _q3(capacidad - resto)
        viajes = tuple([capacidad] * (llenos + 1))
    else:  # distribucion_uniforme
        n = llenos + 1
        cuota = _q3(volumen / n)
        viajes = tuple([cuota] * n)
        # ajuste de centesimas para que la suma sea exacta
        diferencia = _q3(volumen - cuota * n)
        if diferencia != 0:
            viajes = tuple(list(viajes[:-1]) + [_q3(cuota + diferencia)])

    return PlanViajes(volumen, capacidad, politica, viajes, excedente)


def limite_termico(salida_planta: datetime, minutos_fraguado: int) -> datetime:
    """PDR 3.2: el reloj de 150 min arranca al salir de planta."""
    if minutos_fraguado <= 0:
        raise ErrorPlanta("Los minutos de fraguado deben ser positivos")
    return salida_planta + timedelta(minutes=minutos_fraguado)


def estado_termico(
    ahora: datetime,
    limite: datetime,
    *,
    umbral_por_vencer_minutos: int = 30,
) -> str:
    """Devuelve OK | POR_VENCER | VENCIDO."""
    restante = (limite - ahora).total_seconds() / 60
    if restante <= 0:
        return "VENCIDO"
    if restante <= umbral_por_vencer_minutos:
        return "POR_VENCER"
    return "OK"


def seleccionar_mixer(mixers: Sequence[Mapping[str, Any]], volumen: Decimal) -> Mapping[str, Any] | None:
    """Elige el mixer activo mas pequeno que alcance el volumen (o el mayor si ninguno)."""
    activos = [m for m in mixers if m.get("activo", True)]
    if not activos:
        return None
    capaces = [m for m in activos if _decimal(m["capacidad_m3"]) >= volumen]
    if capaces:
        return min(capaces, key=lambda m: _decimal(m["capacidad_m3"]))
    return max(activos, key=lambda m: _decimal(m["capacidad_m3"]))
