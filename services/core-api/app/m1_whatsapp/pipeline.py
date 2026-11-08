"""Modulo 1 - Pipeline de las 4 compuertas binarias.

Entra un lote de mensajes ya agrupado por el debounce; sale un
``tracking_payload`` actualizado (o un prospecto creado). La matematica nunca
pasa por aqui: el Juez solo responde SI/NO y este pipeline ejecuta la accion
deterministica del PDR.

Flujo (PDR 3.2):

- Gate #1 Bodega  -> salida_planta + limite_termico_fraguado + aviso al cliente.
- Gate #2 Cliente -> sello forense de recepcion o incidencia + alerta al Centinela.
- Gate #3 Chofer  -> evidencia a Bunny.net + URL CDN en el JSON.
- Gate #4 Lead    -> prospecto en la bandeja de Secretaria.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .bunny import BunnyError, BunnyStorageClient, decodificar_base64, nombre_evidencia
from .identity import IdentityResolver
from .judges import (
    ACCION_RECLAMO,
    COMPUERTA_CLIENTE,
    COMPUERTA_DESPACHO,
    COMPUERTA_EVIDENCIA,
    COMPUERTA_LEAD,
    BooleanJudgeProvider,
    Veredicto,
)
from .models import MessageBatch, ReferenciaViaje, Rol, extraer_referencia
from .notifications import Notifier, SentinelAlerter
from .repositorio import RepositorioWhatsApp, ViajeObjetivo

log = logging.getLogger(__name__)

ZONA_POR_DEFECTO = "America/Guayaquil"
MINUTOS_FRAGUADO_POR_DEFECTO = 150

ESTADO_EN_RUTA = "EN_RUTA"
ESTADO_CONFIRMADO_CLIENTE = "CONFIRMADO_CLIENTE"
ESTADO_INCIDENCIA = "INCIDENCIA_RECLAMO"
ESTADO_EVIDENCIA_PENDIENTE = "EVIDENCIA_PENDIENTE"

PLANTILLA_SALIDA = (
    "Ormimorth: el mixer {mixer} del viaje {viaje}/{total} de la orden #{orden} "
    "salio de planta a las {hora}. Limite de fraguado: {limite}."
)


@dataclass
class ResultadoLote:
    """Lo que hizo el bot con un lote. Se devuelve para tests y para /flush."""

    telefono: str
    rol: str
    origen_identidad: str
    compuerta: str | None = None
    veredicto: dict[str, Any] | None = None
    dispatch_id: str | None = None
    estado_actual: str | None = None
    acciones: list[str] = field(default_factory=list)
    alerta: dict[str, Any] | None = None
    error: str | None = None

    def a_dict(self) -> dict[str, Any]:
        return {
            "telefono": self.telefono,
            "rol": self.rol,
            "origen_identidad": self.origen_identidad,
            "compuerta": self.compuerta,
            "veredicto": self.veredicto,
            "dispatch_id": self.dispatch_id,
            "estado_actual": self.estado_actual,
            "acciones": self.acciones,
            "alerta": self.alerta,
            "error": self.error,
        }


def _reloj_utc() -> datetime:
    return datetime.now(timezone.utc)


class WhatsAppPipeline:
    """Orquesta identidad + Juez + acciones sobre el contrato JSON."""

    def __init__(
        self,
        *,
        repo: RepositorioWhatsApp,
        identidad: IdentityResolver,
        juez: BooleanJudgeProvider,
        bunny: BunnyStorageClient,
        notifier: Notifier,
        alerter: SentinelAlerter,
        reloj: Any = None,
    ) -> None:
        self.repo = repo
        self.identidad = identidad
        self.juez = juez
        self.bunny = bunny
        self.notifier = notifier
        self.alerter = alerter
        self._reloj = reloj or _reloj_utc

    # -- helpers ----------------------------------------------------------
    async def _zona(self) -> ZoneInfo:
        nombre = await self.repo.parametro("core.zona_horaria", ZONA_POR_DEFECTO)
        for candidato in (str(nombre or "").strip(), ZONA_POR_DEFECTO):
            if not candidato:
                continue
            try:
                return ZoneInfo(candidato)
            except Exception:
                continue
        return timezone.utc  # type: ignore[return-value]

    @staticmethod
    def _iso(momento: datetime, zona: ZoneInfo) -> str:
        return momento.astimezone(zona).isoformat(timespec="seconds")

    @staticmethod
    def _hora(momento: datetime, zona: ZoneInfo) -> str:
        return momento.astimezone(zona).strftime("%H:%M")

    async def _minutos_fraguado(self) -> int:
        valor = await self.repo.parametro(
            "operacion.reloj_termico_minutos", MINUTOS_FRAGUADO_POR_DEFECTO
        )
        try:
            minutos = int(valor)
        except (TypeError, ValueError):
            minutos = MINUTOS_FRAGUADO_POR_DEFECTO
        return minutos if minutos > 0 else MINUTOS_FRAGUADO_POR_DEFECTO

    @staticmethod
    def _actualizar_json(payload: dict[str, Any], cambios: dict[str, Any]) -> None:
        """Fusiona cambios respetando el contrato (no borra claves existentes)."""
        for clave, valor in cambios.items():
            payload[clave] = valor

    # -- entrada ----------------------------------------------------------
    async def procesar(self, lote: MessageBatch) -> ResultadoLote:
        texto = lote.texto
        identidad = await self.identidad.resolver(lote.telefono, texto)
        resultado = ResultadoLote(
            telefono=lote.telefono,
            rol=identidad.rol.value,
            origen_identidad=identidad.origen,
        )

        if identidad.rol is Rol.LEAD_DESCONOCIDO:
            await self._gate_lead(lote, identidad.cliente_id, identidad.nombre, resultado)
        elif identidad.rol in (
            Rol.BODEGA_PLANTA,
            Rol.CAJA_SECRETARIA,
            Rol.SUPERADMIN,
        ):
            await self._gate_despacho(lote, resultado)
        elif identidad.rol is Rol.CHOFER_MIXER:
            await self._gate_evidencia(
                lote, identidad.mixer_codigo, resultado
            )
        else:
            await self._gate_cliente(
                lote, identidad.cliente_id, resultado
            )
        return resultado

    # -- Gate #1 ----------------------------------------------------------
    async def _gate_despacho(
        self, lote: MessageBatch, resultado: ResultadoLote
    ) -> None:
        referencia = extraer_referencia(lote.texto)
        viaje = await self.repo.buscar_viaje(
            referencia=referencia, estados=("PROGRAMADO",)
        )
        if viaje is None:
            resultado.error = "sin viaje PROGRAMADO para confirmar salida"
            return

        veredicto = await self.juez.evaluar(
            compuerta=COMPUERTA_DESPACHO,
            texto=lote.texto,
            contexto={"rol": resultado.rol, "referencia": referencia.__dict__},
        )
        resultado.compuerta = COMPUERTA_DESPACHO
        resultado.veredicto = veredicto.a_dict()
        resultado.dispatch_id = viaje.dispatch_id
        if not veredicto.cumple:
            resultado.estado_actual = viaje.estado_actual
            return

        ahora = self._reloj()
        zona = await self._zona()
        minutos = await self._minutos_fraguado()
        limite = ahora + timedelta(minutes=minutos)
        iso_salida = self._iso(ahora, zona)
        iso_limite = self._iso(limite, zona)

        def mutar(payload: dict[str, Any]) -> None:
            if referencia.mixer_codigo and not payload.get("mixer_codigo"):
                # Dato declarado por el bodeguero en el mensaje, no inventado.
                payload["mixer_codigo"] = referencia.mixer_codigo
            tiempos = payload.setdefault("tiempos_forenses", {})
            tiempos["salida_planta"] = iso_salida
            tiempos["limite_termico_fraguado"] = iso_limite
            payload.setdefault("juez_binario_jeb", {})["despacho_validado"] = True
            payload["estado_actual"] = ESTADO_EN_RUTA

        payload = await self.repo.actualizar_payload(viaje.dispatch_id, mutar)
        resultado.estado_actual = str(payload.get("estado_actual"))
        resultado.acciones.append("REGISTRAR_SALIDA_PLANTA")

        if viaje.cliente_telefono:
            enviado = await self.notifier.enviar_texto(
                viaje.cliente_telefono,
                PLANTILLA_SALIDA.format(
                    mixer=viaje.mixer_codigo or "mixer",
                    viaje=viaje.viaje_numero,
                    total=viaje.total_viajes_orden,
                    orden=viaje.orden_numero,
                    hora=self._hora(ahora, zona),
                    limite=self._hora(limite, zona),
                ),
            )
            resultado.acciones.append(
                "AVISO_CLIENTE_ENVIADO" if enviado else "AVISO_CLIENTE_NO_ENVIADO"
            )
        else:
            resultado.acciones.append("AVISO_CLIENTE_SIN_TELEFONO")

    # -- Gate #2 ----------------------------------------------------------
    async def _gate_cliente(
        self,
        lote: MessageBatch,
        cliente_id: str | None,
        resultado: ResultadoLote,
    ) -> None:
        referencia = extraer_referencia(lote.texto)
        viaje = await self.repo.buscar_viaje(
            referencia=referencia,
            cliente_id=cliente_id,
            estados=(ESTADO_EN_RUTA, "PROGRAMADO"),
        )
        if viaje is None:
            resultado.error = "sin viaje pendiente del cliente identificado"
            return

        veredicto = await self.juez.evaluar(
            compuerta=COMPUERTA_CLIENTE,
            texto=lote.texto,
            contexto={"orden": viaje.orden_numero, "viaje": viaje.viaje_numero},
        )
        resultado.compuerta = COMPUERTA_CLIENTE
        resultado.veredicto = veredicto.a_dict()
        resultado.dispatch_id = viaje.dispatch_id

        if veredicto.cumple:
            ahora = self._reloj()
            zona = await self._zona()
            iso = self._iso(ahora, zona)

            def mutar(payload: dict[str, Any]) -> None:
                payload.setdefault("tiempos_forenses", {})[
                    "confirmacion_whatsapp_cliente"
                ] = iso
                payload.setdefault("juez_binario_jeb", {})[
                    "recepcion_cliente_validada"
                ] = True
                payload["estado_actual"] = ESTADO_CONFIRMADO_CLIENTE
                payload["whatsapp_msg_id_forense"] = lote.ultimo_id
                payload["mensaje_literal_cliente"] = lote.texto

            payload = await self.repo.actualizar_payload(viaje.dispatch_id, mutar)
            resultado.estado_actual = str(payload.get("estado_actual"))
            resultado.acciones.append("SELLAR_RECEPCION_CLIENTE")
            return

        if veredicto.codigo_accion == ACCION_RECLAMO:
            def mutar_incidencia(payload: dict[str, Any]) -> None:
                payload.setdefault("juez_binario_jeb", {})["incidencia_detectada"] = True
                payload["estado_actual"] = ESTADO_INCIDENCIA
                payload["whatsapp_msg_id_forense"] = lote.ultimo_id
                payload["mensaje_literal_cliente"] = lote.texto

            payload = await self.repo.actualizar_payload(
                viaje.dispatch_id, mutar_incidencia
            )
            resultado.estado_actual = str(payload.get("estado_actual"))
            resultado.acciones.append("MARCAR_INCIDENCIA")

            alerta = await self.alerter.alertar(
                codigo="INCIDENCIA_RECLAMO_CLIENTE",
                mensaje=(
                    f"Cliente {viaje.cliente_nombre} reporto demora/reclamo en el "
                    f"viaje {viaje.viaje_numero}/{viaje.total_viajes_orden} de la "
                    f"orden #{viaje.orden_numero}"
                ),
                contexto={
                    "orden": viaje.orden_numero,
                    "viaje": viaje.viaje_numero,
                    "cliente": viaje.cliente_nombre,
                    "mensaje": lote.texto,
                    "veredicto": veredicto.a_dict(),
                },
                order_id=viaje.order_id,
                dispatch_id=viaje.dispatch_id,
            )
            resultado.alerta = alerta.a_dict()
            resultado.acciones.append(f"ALERTA_CENTINELA_{alerta.estado}")
            return

        resultado.estado_actual = viaje.estado_actual
        resultado.acciones.append("ESPERAR_CONFIRMACION")

    # -- Gate #3 ----------------------------------------------------------
    async def _gate_evidencia(
        self,
        lote: MessageBatch,
        mixer_codigo: str | None,
        resultado: ResultadoLote,
    ) -> None:
        referencia = extraer_referencia(lote.texto)
        if mixer_codigo and not referencia.mixer_codigo:
            referencia = ReferenciaViaje(
                orden_numero=referencia.orden_numero,
                viaje_numero=referencia.viaje_numero,
                mixer_codigo=mixer_codigo,
            )
        viaje = await self.repo.buscar_viaje(
            referencia=referencia, estados=(ESTADO_EN_RUTA, "PROGRAMADO")
        )
        if viaje is None:
            resultado.error = "sin viaje pendiente para asociar la evidencia"
            return

        veredicto = await self.juez.evaluar(
            compuerta=COMPUERTA_EVIDENCIA,
            texto=lote.texto,
            contexto={"media": len(lote.media), "orden": viaje.orden_numero},
        )
        resultado.compuerta = COMPUERTA_EVIDENCIA
        resultado.veredicto = veredicto.a_dict()
        resultado.dispatch_id = viaje.dispatch_id

        if not veredicto.cumple:
            resultado.estado_actual = viaje.estado_actual
            resultado.acciones.append("SOLICITAR_EVIDENCIA")
            return

        urls: list[str] = []
        for indice, adjunto in enumerate(lote.media, start=1):
            nombre = nombre_evidencia(
                orden_numero=viaje.orden_numero,
                viaje_numero=viaje.viaje_numero,
                mensaje_id=f"{lote.ultimo_id}_{indice}",
                extension=adjunto.extension(),
            )
            try:
                url = await self.bunny.subir(
                    nombre_archivo=nombre,
                    contenido=decodificar_base64(adjunto.base64),
                    url_origen=adjunto.url_origen,
                    mimetype=adjunto.mimetype,
                )
            except BunnyError as exc:
                await self._evidencia_fallida(viaje, lote, resultado, exc)
                return
            urls.append(url)

        if not urls:
            await self._evidencia_fallida(
                viaje, lote, resultado, BunnyError("sin adjuntos utilizables")
            )
            return

        ahora = self._reloj()
        zona = await self._zona()
        iso = self._iso(ahora, zona)

        def mutar(payload: dict[str, Any]) -> None:
            if referencia.mixer_codigo and not payload.get("mixer_codigo"):
                payload["mixer_codigo"] = referencia.mixer_codigo
            evidencias = payload.setdefault("evidencias_bunny_cdn", [])
            for url in urls:
                if url not in evidencias:
                    evidencias.append(url)
            tiempos = payload.setdefault("tiempos_forenses", {})
            if not tiempos.get("llegada_obra_chofer"):
                tiempos["llegada_obra_chofer"] = iso

        payload = await self.repo.actualizar_payload(viaje.dispatch_id, mutar)
        resultado.estado_actual = str(payload.get("estado_actual"))
        resultado.acciones.append(f"EVIDENCIA_SUBIDA:{len(urls)}")

    async def _evidencia_fallida(
        self,
        viaje: ViajeObjetivo,
        lote: MessageBatch,
        resultado: ResultadoLote,
        error: Exception,
    ) -> None:
        def mutar(payload: dict[str, Any]) -> None:
            payload.setdefault("juez_binario_jeb", {})["incidencia_detectada"] = True
            payload["estado_actual"] = ESTADO_EVIDENCIA_PENDIENTE

        payload = await self.repo.actualizar_payload(viaje.dispatch_id, mutar)
        resultado.estado_actual = str(payload.get("estado_actual"))
        resultado.acciones.append("EVIDENCIA_FALLIDA")
        alerta = await self.alerter.alertar(
            codigo="EVIDENCIA_BUNNY_FALLIDA",
            mensaje=(
                f"No se pudo subir la evidencia del viaje {viaje.viaje_numero} "
                f"de la orden #{viaje.orden_numero}: {error}"
            ),
            contexto={"error": str(error), "mensaje_whatsapp": lote.ultimo_id},
            order_id=viaje.order_id,
            dispatch_id=viaje.dispatch_id,
        )
        resultado.alerta = alerta.a_dict()

    # -- Gate #4 ----------------------------------------------------------
    async def _gate_lead(
        self,
        lote: MessageBatch,
        cliente_id: str | None,
        nombre: str | None,
        resultado: ResultadoLote,
    ) -> None:
        veredicto = await self.juez.evaluar(
            compuerta=COMPUERTA_LEAD, texto=lote.texto
        )
        resultado.compuerta = COMPUERTA_LEAD
        resultado.veredicto = veredicto.a_dict()
        if not veredicto.cumple:
            resultado.acciones.append("LEAD_NO_CALIFICADO")
            return
        lead = await self.repo.crear_lead(
            telefono=lote.telefono,
            nombre=nombre or lote.nombre_contacto,
            mensaje=lote.texto,
        )
        resultado.dispatch_id = None
        resultado.acciones.append("PROSPECTO_CREADO" if lead else "PROSPECTO_SIN_CAMBIOS")
        if cliente_id:
            resultado.acciones.append("CLIENTE_EXISTENTE_ACTUALIZADO")


__all__ = [
    "ESTADO_CONFIRMADO_CLIENTE",
    "ESTADO_EN_RUTA",
    "ESTADO_EVIDENCIA_PENDIENTE",
    "ESTADO_INCIDENCIA",
    "ResultadoLote",
    "Veredicto",
    "WhatsAppPipeline",
]
