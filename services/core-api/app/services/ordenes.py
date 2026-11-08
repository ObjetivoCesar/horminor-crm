"""Servicio de creacion de ordenes: une Modulo 0 + Modulo 2.

Este servicio es el unico punto donde se decide como se reparte una
orden en viajes y como se descuenta el kardex teorico.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from ..db import setting
from ..m2_planta import (
    ErrorPlanta,
    Receta,
    calcular_consumo,
    dividir_en_viajes,
)
from ..m2_planta.kardex import registrar_consumo_teorico

FORMAS_PAGO = ("EFECTIVO", "TRANSFERENCIA", "ABONO", "FIADO")


class OrdenInvalidaError(ValueError):
    pass


@dataclass
class NuevaOrden:
    cliente_id: str
    resistencia: str
    volumen_m3: Decimal
    planta_codigo: str
    forma_pago: str
    precio_m3: Decimal | None = None
    creada_por: str | None = None
    notas: str | None = None
    politica_viajes: str | None = None
    # Ratificado 2026-11-08: una receta PROVISIONAL nunca bloquea una venta.
    permitir_receta_provisional: bool = True
    mixer_codigo: str | None = None
    chofer_nombre: str | None = None


@dataclass
class ResultadoOrden:
    orden_id: str
    orden_numero: int
    total_viajes: int
    viajes: list[dict[str, Any]] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    consumo_orden: dict[str, Any] | None = None


def _payload_base(
    *,
    dispatch_id: UUID,
    viaje_numero: int,
    total_viajes: int,
    volumen: Decimal,
    resistencia: str,
    mixer_codigo: str | None,
    chofer_nombre: str | None,
    receta_provisional: bool,
) -> dict[str, Any]:
    return {
        "dispatch_id": str(dispatch_id),
        "viaje_numero": viaje_numero,
        "total_viajes_orden": total_viajes,
        "mixer_codigo": mixer_codigo,
        "chofer_nombre": chofer_nombre,
        "volumen_m3": float(volumen),
        "resistencia": resistencia,
        # Ajuste ratificado 2026-11-08: el viaje declara en el contrato JSON
        # si su consumo se calculo con una receta sin validar por Julio.
        "receta_provisional": receta_provisional,
        "estado_actual": "PROGRAMADO",
        "juez_binario_jeb": {
            "despacho_validado": False,
            "recepcion_cliente_validada": False,
            "incidencia_detectada": False,
        },
        "tiempos_forenses": {
            "dosificado_planta": None,
            "salida_planta": None,
            "limite_termico_fraguado": None,
            "llegada_obra_chofer": None,
            "confirmacion_whatsapp_cliente": None,
        },
        "consumo_materiales": {
            "cemento_sacos_teorico": None,
            "cemento_sacos_real": None,
            "retardante_litros": None,
        },
        "evidencias_bunny_cdn": [],
        "mensaje_literal_cliente": None,
        "whatsapp_msg_id_forense": None,
    }


async def crear_orden(pool: asyncpg.Pool, datos: NuevaOrden) -> ResultadoOrden:
    if datos.forma_pago not in FORMAS_PAGO:
        raise OrdenInvalidaError(
            f"forma_pago '{datos.forma_pago}' no valida. Use: {', '.join(FORMAS_PAGO)}"
        )

    mixers = await setting(pool, "flota.mixers", []) or []
    politica = datos.politica_viajes or await setting(
        pool, "operacion.politica_redondeo_viajes", "ultimo_parcial"
    )

    mixer = None
    if datos.mixer_codigo:
        mixer = next(
            (m for m in mixers if m.get("codigo") == datos.mixer_codigo),
            None,
        )
        if mixer is None:
            raise OrdenInvalidaError(f"Mixer desconocido en flota.mixers: {datos.mixer_codigo}")
    else:
        capacidad_ref = max(
            (Decimal(str(m["capacidad_m3"])) for m in mixers if m.get("activo", True)),
            default=None,
        )
        if capacidad_ref is None:
            raise OrdenInvalidaError(
                "No hay mixers activos en system_settings.flota.mixers"
            )
        mixer = {"codigo": None, "capacidad_m3": capacidad_ref}

    capacidad = Decimal(str(mixer["capacidad_m3"]))
    plan = dividir_en_viajes(datos.volumen_m3, capacidad, politica)

    advertencias: list[str] = []
    if plan.excedente_m3 > 0:
        advertencias.append(
            f"La politica '{politica}' redondea el ultimo viaje: se entregan "
            f"{plan.excedente_m3} m3 de mas sobre el volumen pedido."
        )

    async with pool.acquire() as conn:
        async with conn.transaction():
            planta = await conn.fetchrow(
                "SELECT id, nombre FROM plants WHERE codigo = $1 AND activa",
                datos.planta_codigo,
            )
            if planta is None:
                raise OrdenInvalidaError(
                    f"Planta inexistente o inactiva: {datos.planta_codigo}"
                )

            receta_row = await conn.fetchrow(
                "SELECT * FROM concrete_recipes WHERE resistencia = $1",
                datos.resistencia,
            )
            if receta_row is None:
                raise OrdenInvalidaError(f"Resistencia no registrada: {datos.resistencia}")
            receta = Receta.from_row(dict(receta_row))

            orden = await conn.fetchrow(
                """
                INSERT INTO orders
                    (cliente_id, resistencia, volumen_m3, planta_id, forma_pago,
                     precio_m3, creada_por, notas)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id::text, numero, total
                """,
                datos.cliente_id,
                datos.resistencia,
                datos.volumen_m3,
                planta["id"],
                datos.forma_pago,
                datos.precio_m3,
                datos.creada_por,
                datos.notas,
            )

            consumo_orden = None
            try:
                consumo_orden = calcular_consumo(
                    receta,
                    datos.volumen_m3,
                    permitir_provisional=datos.permitir_receta_provisional,
                )
            except ErrorPlanta as exc:
                advertencias.append(f"Consumo de materiales no calculado: {exc}")

            viajes: list[dict[str, Any]] = []
            for numero, volumen_viaje in enumerate(plan.viajes, start=1):
                dispatch_id = uuid4()
                payload = _payload_base(
                    dispatch_id=dispatch_id,
                    viaje_numero=numero,
                    total_viajes=plan.total_viajes,
                    volumen=volumen_viaje,
                    resistencia=datos.resistencia,
                    mixer_codigo=mixer.get("codigo"),
                    chofer_nombre=datos.chofer_nombre,
                    receta_provisional=not receta.confirmado,
                )

                consumo_viaje = None
                try:
                    consumo_viaje = calcular_consumo(
                        receta,
                        volumen_viaje,
                        permitir_provisional=datos.permitir_receta_provisional,
                    )
                except ErrorPlanta:
                    consumo_viaje = None

                if consumo_viaje is not None:
                    payload["consumo_materiales"] = {
                        "cemento_sacos_teorico": float(consumo_viaje.cemento_sacos),
                        "cemento_sacos_real": None,
                        "retardante_litros": (
                            None
                            if consumo_viaje.retardante_litros is None
                            else float(consumo_viaje.retardante_litros)
                        ),
                        "arena_m3": (
                            None if consumo_viaje.arena_m3 is None else float(consumo_viaje.arena_m3)
                        ),
                        "ripio_m3": (
                            None if consumo_viaje.ripio_m3 is None else float(consumo_viaje.ripio_m3)
                        ),
                        "agua_litros": (
                            None
                            if consumo_viaje.agua_litros is None
                            else float(consumo_viaje.agua_litros)
                        ),
                        "provisional": consumo_viaje.provisional,
                        "campos_faltantes": list(consumo_viaje.campos_faltantes),
                    }

                await conn.execute(
                    """
                    INSERT INTO mixer_dispatches
                        (id, order_id, viaje_numero, total_viajes_orden,
                         volumen_m3, tracking_payload)
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                    """,
                    dispatch_id,
                    orden["id"],
                    numero,
                    plan.total_viajes,
                    volumen_viaje,
                    json.dumps(payload, ensure_ascii=False, default=str),
                )

                if consumo_viaje is not None:
                    await registrar_consumo_teorico(
                        conn,
                        order_id=orden["id"],
                        dispatch_id=str(dispatch_id),
                        consumo=consumo_viaje,
                        referencia="provisional" if consumo_viaje.provisional else "receta",
                    )

                viajes.append(
                    {
                        "dispatch_id": str(dispatch_id),
                        "viaje_numero": numero,
                        "volumen_m3": float(volumen_viaje),
                        "estado_actual": "PROGRAMADO",
                        "consumo_materiales": payload["consumo_materiales"],
                    }
                )

            await conn.execute(
                "UPDATE orders SET estado = 'CONFIRMADA' WHERE id = $1", orden["id"]
            )

    if not receta.confirmado:
        advertencias.append(
            f"La receta {receta.resistencia} esta PROVISIONAL (confirmado=false). "
            "La orden y el despacho siguen habilitados (politica ratificada 2026-11-08); "
            "los viajes quedan marcados con receta_provisional=true y el Centinela lo "
            "reporta como WARNING hasta que Julio valide la dosificacion."
        )

    return ResultadoOrden(
        orden_id=orden["id"],
        orden_numero=orden["numero"],
        total_viajes=plan.total_viajes,
        viajes=viajes,
        advertencias=advertencias,
        consumo_orden=None
        if consumo_orden is None
        else {
            "cemento_sacos": float(consumo_orden.cemento_sacos),
            "retardante_litros": (
                None
                if consumo_orden.retardante_litros is None
                else float(consumo_orden.retardante_litros)
            ),
            "campos_faltantes": list(consumo_orden.campos_faltantes),
            "provisional": consumo_orden.provisional,
        },
    )
