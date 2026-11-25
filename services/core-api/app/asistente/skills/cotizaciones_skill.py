"""Skill de Cotizaciones: preparar y ejecutar el envío por WhatsApp.

No genera el PDF ni calcula precios: delega en cotizaciones_envio.
Aplica la política de permisos antes de ejecutar.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping

from .contrato import (
    EJECUTADA,
    ERROR,
    ESPERANDO_CONFIRMACION,
    FALTAN_DATOS,
    NO_CONECTADA,
    NO_PERMITIDO,
    Autorizacion,
    ContextoSkill,
    Preparacion,
    ResultadoSkill,
)
from .politica import huella_texto, permisos_envio_cotizacion, precio_bloqueado

_LOG = logging.getLogger(__name__)


class CotizacionesSkill:
    """Skill que prepara y ejecuta el envío de una cotización por WhatsApp."""

    # ------------------------------------------------------------------ #
    # Preparar envío                                                       #
    # ------------------------------------------------------------------ #

    async def preparar_envio(self, ctx: ContextoSkill) -> Preparacion:
        """Resuelve cotización, permisos, teléfono y hora antes de mostrar el resumen."""
        p = ctx.puertos.cotizaciones
        cfg_port = ctx.puertos.config
        if p is None:
            return Preparacion(NO_CONECTADA, motivo="Módulo de cotizaciones no disponible.")

        params = ctx.parametros
        cotizacion_id: str | None = params.get("cotizacion_id") or ctx.cotizacion_dependencia

        # 1. Resolver cotización
        cotizacion: Mapping[str, Any] | None = None
        if cotizacion_id:
            cotizacion = await p.obtener(cotizacion_id)
        if cotizacion is None:
            # Buscar la más reciente del asunto si hay hilo
            if ctx.cotizaciones_hilo:
                cotizacion = await p.obtener(ctx.cotizaciones_hilo[-1])
                if cotizacion:
                    cotizacion_id = ctx.cotizaciones_hilo[-1]
        if cotizacion is None:
            return Preparacion(FALTAN_DATOS, vista="No encontré la cotización a enviar. ¿A cuál te refieres?")

        # 2. Permisos
        config: dict[str, Any] = {}
        if cfg_port:
            config = {
                "gato.secretaria_envia_cotizacion_aprobada": await cfg_port.valor(
                    "gato.secretaria_envia_cotizacion_aprobada", False
                ),
                "cotizaciones.quien_aprueba_precio": await cfg_port.valor(
                    "cotizaciones.quien_aprueba_precio", "SUPERADMIN"
                ),
            }

        if not permisos_envio_cotizacion(ctx.actor.rol, config):
            return Preparacion(
                NO_PERMITIDO,
                motivo="Tu perfil no tiene permiso para enviar cotizaciones.",
            )

        precio_estado = str(cotizacion.get("precio_estado") or "")
        bloqueado, motivo_precio = precio_bloqueado(
            precio_estado, ctx.sandbox, ctx.actor.rol, config
        )
        if bloqueado:
            return Preparacion(NO_PERMITIDO, motivo=motivo_precio)

        # 3. Teléfono destino
        telefono_destino: str | None = (
            params.get("destinatario_telefono")
            or params.get("telefono_destino")
        )
        destinatario_nombre: str | None = params.get("destinatario_nombre")

        if not telefono_destino:
            # Fallback: teléfono de la ficha del cliente de la cotización
            telefono_destino = str(cotizacion.get("cliente_telefono") or "") or None

        if not telefono_destino:
            return Preparacion(
                FALTAN_DATOS,
                vista="¿A qué número de WhatsApp envío la cotización?",
            )

        # 4. Hora de envío
        enviar_cuando_str: str | None = params.get("enviar_cuando")
        cuando: datetime | None = None
        if enviar_cuando_str:
            try:
                cuando = datetime.fromisoformat(enviar_cuando_str)
            except ValueError:
                # Intentar parsear con el módulo de recordatorios
                from .. import recordatorios as rec
                cuando = rec.parsear_cuando(enviar_cuando_str)

        # 5. Detectar envío programado previo
        envio_previo = await p.consultar_envio(str(cotizacion_id))

        # 6. Construir vista de confirmación
        numero_cotizacion = cotizacion.get("numero") or cotizacion.get("id") or cotizacion_id
        cliente_nombre = ctx.cliente_nombre or str(cotizacion.get("cliente_nombre") or "")
        lineas = [f"Cotización #{numero_cotizacion} para {cliente_nombre}"]
        lineas.append(f"Destino: {destinatario_nombre or 'encargado'} · {telefono_destino}")
        if cuando:
            from ... import tiempo
            local = cuando.astimezone(tiempo.ZONA)
            lineas.append(f"Envío programado: {local:%Y-%m-%d} a las {local:%H:%M}")
        else:
            lineas.append("Envío: inmediato")
        if precio_estado == "PROVISIONAL":
            lineas.append("⚠ El precio es provisional.")
        if envio_previo:
            lineas.append(f"(Reemplaza envío previo en estado {envio_previo.get('estado')})")
        lineas.append("\nResponde «Confirmado» para enviar.")
        vista = "\n".join(lineas)

        parametros_ejecutar = {
            "cotizacion_id": str(cotizacion_id),
            "telefono_destino": telefono_destino,
            "destinatario_nombre": destinatario_nombre,
            "enviar_cuando": enviar_cuando_str,
        }
        return Preparacion(
            ESPERANDO_CONFIRMACION,
            parametros=parametros_ejecutar,
            vista=vista,
        )

    # ------------------------------------------------------------------ #
    # Ejecutar envío                                                       #
    # ------------------------------------------------------------------ #

    async def ejecutar_envio(
        self,
        ctx: ContextoSkill,
        autorizacion: Autorizacion,
    ) -> ResultadoSkill:
        """Llama a cotizaciones_envio.enviar_cotizacion() si la huella es válida."""
        p = ctx.puertos.cotizaciones
        if p is None:
            return ResultadoSkill(ERROR, "Módulo de cotizaciones no disponible.", {})

        params = ctx.parametros
        huella_esperada = huella_texto(ctx.actor.actor_id, "enviar_cotizacion", params)
        if autorizacion.huella != huella_esperada:
            return ResultadoSkill(
                ERROR,
                "No puedo confirmar el envío: la confirmación no corresponde a lo mostrado. "
                "Dime de nuevo qué cotización envío y a quién.",
                {},
            )

        cotizacion_id: str | None = params.get("cotizacion_id")
        if not cotizacion_id:
            return ResultadoSkill(ERROR, "No hay cotización identificada.", {})

        telefono_destino: str | None = params.get("telefono_destino")
        destinatario_nombre: str | None = params.get("destinatario_nombre")
        enviar_cuando_str: str | None = params.get("enviar_cuando")

        cuando: datetime | None = None
        if enviar_cuando_str:
            try:
                cuando = datetime.fromisoformat(enviar_cuando_str)
            except ValueError:
                from .. import recordatorios as rec
                cuando = rec.parsear_cuando(enviar_cuando_str)

        try:
            resultado = await p.enviar(
                cotizacion_id,
                actor=ctx.actor,
                telefono_destino=telefono_destino,
                destinatario_nombre=destinatario_nombre,
                cuando=cuando,
                clave_idempotencia=autorizacion.huella,
            )
        except Exception as exc:
            _LOG.warning("Error en ejecutar_envio: %s", exc)
            return ResultadoSkill(ERROR, f"No pude enviar la cotización: {exc}", {})

        enviado = resultado.get("enviado", False)
        programado = resultado.get("programado", False)

        if programado and cuando:
            from ... import tiempo
            local = cuando.astimezone(tiempo.ZONA)
            nota = f"Listo. La cotización se enviará el {local:%Y-%m-%d} a las {local:%H:%M}."
        elif enviado:
            nota = "Listo. La cotización fue enviada por WhatsApp."
        else:
            # Sandbox: no finge envío
            nota = "Registrado. El envío está pendiente (modo sandbox)."

        return ResultadoSkill(EJECUTADA, nota, dict(resultado))
