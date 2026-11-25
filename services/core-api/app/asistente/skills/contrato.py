"""Contrato común de las skills de Gato: tipos y puertos.

Una skill PREPARA (qué falta, qué choca, qué se le muestra a quien autoriza)
y EJECUTA (llama al servicio real que ya existe). No decide la intención
(razonador) ni inventa datos (extractor).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Mapping, Protocol, Sequence

from ...cerebro.compilador import Pregunta

LISTA = "LISTA"
FALTAN_DATOS = "FALTAN_DATOS"
DECIDIR_CHOQUE = "DECIDIR_CHOQUE"
NO_PERMITIDO = "NO_PERMITIDO"
NO_CONECTADA = "NO_CONECTADA"
EJECUTADA = "EJECUTADA"
ERROR = "ERROR"
ESPERANDO_CONFIRMACION = "ESPERANDO_CONFIRMACION"


class ActorLike(Protocol):
    nombre: str
    rol: str
    actor_id: str


@dataclass(frozen=True)
class Choque:
    severidad: str  # DURO | AVISO
    tipo: str  # visita | recordatorio | mixer
    etiqueta: str
    inicio: str  # HH:MM
    fin: str | None = None


@dataclass(frozen=True)
class Preparacion:
    estado: str
    parametros: Mapping[str, Any] = field(default_factory=dict)
    preguntas: tuple[Pregunta, ...] = ()
    choques: tuple[Choque, ...] = ()
    vista: str = ""
    motivo: str | None = None


@dataclass(frozen=True)
class Autorizacion:
    actor_id: str
    rol: str
    huella: str
    mensaje_final: str | None = None
    enviar_ahora: bool = False
    cuando: str | None = None


@dataclass(frozen=True)
class ResultadoSkill:
    estado: str
    nota: str
    datos: Mapping[str, Any] = field(default_factory=dict)


class ConfigPort(Protocol):
    async def valor(self, clave: str, defecto: Any = None) -> Any: ...


class CerebroPort(Protocol):
    async def confirmar(
        self,
        borrador_id: str,
        orden: int,
        *,
        actor: ActorLike,
        mensaje_final: str | None = None,
        enviar_ahora: bool = False,
        cuando: str | None = None,
    ) -> Mapping[str, Any]: ...


class PersonalPort(Protocol):
    async def eventos(self, actor_id: str, dia: date) -> Sequence[Mapping[str, Any]]: ...
    async def agendar_recordatorio(
        self, *, actor: ActorLike, asunto_id: str, mensaje: str, cuando: datetime
    ) -> Mapping[str, Any]: ...
    async def agendar_visita(
        self, *, actor: ActorLike, asunto_id: str, texto: str, datos: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...


class MixerPort(Protocol):
    async def verificar(
        self, *, fecha: date, hora: str, volumen: Any, unidades: int | None
    ) -> Mapping[str, Any]: ...
    async def mover(
        self,
        *,
        reserva_id: str | None,
        fecha: date,
        hora: str,
        motivo: str,
        actor: ActorLike,
    ) -> Mapping[str, Any]: ...


class CotizacionesPort(Protocol):
    async def obtener(self, cotizacion_id: str) -> Mapping[str, Any] | None: ...
    async def abiertas(
        self, *, ids: Sequence[str] | None = None, cliente_id: str | None = None
    ) -> Sequence[Mapping[str, Any]]: ...
    async def enviar(
        self,
        cotizacion_id: str,
        *,
        actor: ActorLike,
        telefono_destino: str | None = None,
        destinatario_nombre: str | None = None,
        cuando: datetime | None = None,
        clave_idempotencia: str | None = None,
    ) -> Mapping[str, Any]: ...
    async def consultar_envio(self, cotizacion_id: str) -> Mapping[str, Any] | None: ...


class AvisosDineroPort(Protocol):
    """Para dinero, Gato solo crea o actualiza un aviso para Secretaría."""

    async def abierto(
        self, *, cliente_id: str | None, borrador_id: str | None
    ) -> Mapping[str, Any] | None: ...
    async def registrar_aviso(
        self,
        *,
        cliente_id: str | None,
        cliente_nombre: str | None,
        monto_usd: Any,
        forma_pago: str | None,
        referencia: str | None,
        cita: str | None,
        hablante: str,
        actor: ActorLike,
        clave: str,
        borrador_id: str | None = None,
        extraccion_id: str | None = None,
    ) -> Mapping[str, Any]: ...


@dataclass
class Puertos:
    config: ConfigPort
    cerebro: CerebroPort | None = None
    personal: PersonalPort | None = None
    mixer: MixerPort | None = None
    cotizaciones: CotizacionesPort | None = None
    avisos_dinero: AvisosDineroPort | None = None


@dataclass
class ContextoSkill:
    actor: ActorLike
    asunto_id: str
    puertos: Puertos
    accion: Mapping[str, Any] = field(default_factory=dict)
    borrador_id: str | None = None
    ejecutadas: frozenset[int] = frozenset()
    datos: Mapping[str, Any] = field(default_factory=dict)
    cliente_nombre: str | None = None
    cotizaciones_hilo: tuple[str, ...] = ()
    cotizacion_dependencia: str | None = None
    ahora: datetime | None = None
    sandbox: bool = True
    limite_vista: int = 8000

    @property
    def parametros(self) -> dict[str, Any]:
        if self.accion:
            return dict(self.accion.get("parametros") or {})
        return dict(self.datos)
