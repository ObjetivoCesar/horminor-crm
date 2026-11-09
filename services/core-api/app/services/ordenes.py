"""Servicio de creacion de ordenes: une Modulo 0 + Modulo 2.

Este servicio es el unico punto donde se decide como se reparte una
orden en viajes y como se descuenta el kardex teorico.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
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
ABONO_METODOS = ("EFECTIVO", "TRANSFERENCIA")

# Directriz 2026-11-08: el cupo de fiado NO bloquea la venta. Si se excede,
# la orden se registra igual y queda marcada para el Centinela y Julio.
_CUPO_POR_DEFECTO = Decimal("1500.00")
_CENTAVO = Decimal("0.01")


def _decimal(valor: Any, por_defecto: Decimal | None = None) -> Decimal | None:
    if valor is None or valor == "":
        return por_defecto
    try:
        return Decimal(str(valor))
    except (TypeError, ValueError):
        return por_defecto


def _redondear(valor: Decimal) -> Decimal:
    """Mismo redondeo que PostgreSQL ``round(numeric, 2)`` para positivos."""
    return valor.quantize(_CENTAVO, rounding=ROUND_HALF_UP)


class OrdenInvalidaError(ValueError):
    pass


def calcular_iva(
    total_neto: Decimal | None,
    iva_pct: Decimal | None,
    *,
    aplica_iva: bool,
) -> tuple[Decimal, Decimal | None]:
    """Devuelve ``(iva_monto, total_con_iva)`` sin inventar precios.

    Si la orden no tiene precio (``total_neto is None``), el IVA queda en 0 y
    ``total_con_iva`` en ``None``: la orden se registra igual y se valorara
    cuando exista precio.
    """
    if not aplica_iva or total_neto is None:
        iva_monto = Decimal("0")
    else:
        pct = iva_pct if iva_pct is not None else Decimal("0")
        iva_monto = _redondear(total_neto * pct / Decimal("100"))
    total_con_iva = None if total_neto is None else total_neto + iva_monto
    return iva_monto, total_con_iva


def validar_abono_inicial(
    *,
    forma_pago: str,
    monto: Decimal | None,
    metodo: str | None,
    total_con_iva: Decimal | None,
) -> tuple[Decimal | None, str | None]:
    """Valida el abono inicial de una venta ``ABONO``.

    Devuelve ``(monto, metodo)`` para el ``COBRO`` o ``(None, None)`` cuando la
    forma de pago no genera cobro inicial (``FIADO``). ``EFECTIVO`` y
    ``TRANSFERENCIA`` cobran el total bruto y no admiten abono inicial.
    """
    if forma_pago == "ABONO":
        if monto is None or monto <= 0:
            raise OrdenInvalidaError("ABONO requiere abono_inicial_monto > 0")
        metodo_normalizado = str(metodo or "").upper()
        if metodo_normalizado not in ABONO_METODOS:
            raise OrdenInvalidaError(
                "abono_inicial_metodo debe ser EFECTIVO o TRANSFERENCIA"
            )
        if total_con_iva is None:
            raise OrdenInvalidaError(
                "No se puede registrar un abono inicial sin precio de venta "
                "(total_con_iva NULL)"
            )
        monto_redondeado = _redondear(monto)
        if monto_redondeado > total_con_iva:
            raise OrdenInvalidaError(
                f"El abono inicial ${monto_redondeado:,.2f} supera el total "
                f"con IVA ${total_con_iva:,.2f}"
            )
        return monto_redondeado, metodo_normalizado

    if monto is not None or metodo is not None:
        raise OrdenInvalidaError(
            "abono_inicial_monto y abono_inicial_metodo solo aplican a "
            "forma_pago ABONO"
        )
    return None, None


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
    # v4.3: IVA y abono inicial. ``None`` en ``aplica_iva`` usa
    # ``finanzas.iva_default_aplica`` (hoy true).
    aplica_iva: bool | None = None
    abono_inicial_monto: Decimal | None = None
    abono_inicial_metodo: str | None = None


@dataclass
class ResultadoOrden:
    orden_id: str
    orden_numero: int
    total_viajes: int
    viajes: list[dict[str, Any]] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    consumo_orden: dict[str, Any] | None = None
    excede_cupo_credito: bool = False
    cupo_credito_usd: Decimal | None = None
    saldo_cliente_usd: Decimal | None = None
    total: Decimal | None = None
    iva_pct: Decimal = Decimal("0")
    iva_monto: Decimal = Decimal("0")
    total_con_iva: Decimal | None = None
    cobro_inicial_id: str | None = None
    cobro_inicial_monto: Decimal | None = None


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
    forma_pago = str(datos.forma_pago).upper()
    if forma_pago not in FORMAS_PAGO:
        raise OrdenInvalidaError(
            f"forma_pago '{datos.forma_pago}' no valida. Use: {', '.join(FORMAS_PAGO)}"
        )
    if forma_pago != "ABONO" and (
        datos.abono_inicial_monto is not None
        or datos.abono_inicial_metodo is not None
    ):
        raise OrdenInvalidaError(
            "abono_inicial_monto y abono_inicial_metodo solo aplican a "
            "forma_pago ABONO"
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

    # Config de cupo e IVA se leen antes de abrir la conexion (evita pedir dos
    # conexiones al pool dentro de la misma transaccion).
    cupo_cfg = await setting(pool, "finanzas.tope_credito_auto", {}) or {}
    if not isinstance(cupo_cfg, dict):
        cupo_cfg = {}
    iva_default = await setting(pool, "finanzas.iva_default_aplica", True)
    aplica_iva = datos.aplica_iva if datos.aplica_iva is not None else bool(iva_default)

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

            # Precio de la orden: si no viene explicito se usa el de la receta.
            # Si la receta tampoco tiene precio, queda NULL (nunca se inventa):
            # la orden se registra igual y el total queda pendiente de valorar.
            precio_ref = _decimal(
                datos.precio_m3, _decimal(receta_row["precio_m3"])
            )

            total_neto = (
                None
                if precio_ref is None
                else _redondear(precio_ref * datos.volumen_m3)
            )
            iva_pct = Decimal("0")
            if aplica_iva:
                iva_pct = _decimal(receta_row["iva_pct"], Decimal("0")) or Decimal("0")
                iva_pct = _redondear(iva_pct)
            iva_monto, total_con_iva = calcular_iva(
                total_neto,
                iva_pct,
                aplica_iva=aplica_iva,
            )

            # Regla de contado/abono (decision 2026-11-09): el abono inicial se
            # cobra en la misma transaccion. FIADO no genera COBRO.
            abono_monto, abono_metodo = validar_abono_inicial(
                forma_pago=forma_pago,
                monto=_decimal(datos.abono_inicial_monto),
                metodo=datos.abono_inicial_metodo,
                total_con_iva=total_con_iva,
            )

            # Cupo de credito (Directriz 2026-11-08): se marca la orden, nunca
            # se bloquea la venta. El aviso al Centinela va en advertencias.
            # Se evalua sobre el total bruto, igual que v_cliente_saldo.
            excede_cupo = False
            cupo_usd: Decimal | None = None
            saldo_usd: Decimal | None = None
            if forma_pago == "FIADO":
                if cupo_cfg.get("enabled", True):
                    cliente_row = await conn.fetchrow(
                        """
                        SELECT c.credit_limit_usd,
                               COALESCE(s.saldo_pendiente, 0) AS saldo_pendiente
                          FROM clients c
                          LEFT JOIN v_cliente_saldo s ON s.id = c.id
                         WHERE c.id = $1
                        """,
                        datos.cliente_id,
                    )
                    if cliente_row is not None:
                        cupo_usd = _decimal(
                            cliente_row["credit_limit_usd"],
                            _decimal(
                                cupo_cfg.get("default_credit_limit_usd"),
                                _CUPO_POR_DEFECTO,
                            ),
                        )
                        saldo_usd = _decimal(cliente_row["saldo_pendiente"], Decimal("0"))
                    total_orden = (
                        Decimal("0") if total_con_iva is None else total_con_iva
                    )
                    if (
                        cupo_usd is not None
                        and saldo_usd is not None
                        and saldo_usd + total_orden > cupo_usd
                    ):
                        excede_cupo = True
                        advertencias.append(
                            "ALERTA DE CREDITO: la orden supera el cupo de fiado "
                            f"del cliente (saldo ${saldo_usd:,.2f} + orden "
                            f"${total_orden:,.2f} > cupo ${cupo_usd:,.2f}). "
                            "La venta se registra; el Centinela y Julio reciben el aviso."
                        )

            orden = await conn.fetchrow(
                """
                INSERT INTO orders
                    (cliente_id, resistencia, volumen_m3, planta_id, forma_pago,
                     precio_m3, creada_por, notas, excede_cupo_credito,
                     aplica_iva, iva_pct, iva_monto, total_con_iva)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                RETURNING id::text, numero, total, iva_pct, iva_monto,
                          total_con_iva
                """,
                datos.cliente_id,
                datos.resistencia,
                datos.volumen_m3,
                planta["id"],
                forma_pago,
                precio_ref,
                datos.creada_por,
                datos.notas,
                excede_cupo,
                aplica_iva,
                iva_pct,
                iva_monto,
                total_con_iva,
            )

            # COBRO inicial dentro de la misma transaccion: si algo falla, la
            # orden y el pago se revierten juntos. FIADO no entra aqui.
            cobro_inicial_id: str | None = None
            cobro_inicial_monto: Decimal | None = None
            if forma_pago in ("EFECTIVO", "TRANSFERENCIA"):
                cobro_inicial_monto = total_con_iva
                cobro_metodo = forma_pago
            else:
                cobro_inicial_monto = abono_monto
                cobro_metodo = abono_metodo

            if cobro_inicial_monto is None or cobro_inicial_monto <= 0:
                if forma_pago != "FIADO":
                    advertencias.append(
                        "La orden no tiene monto cobrable (precio nulo o cero): "
                        "no se registro COBRO automatico."
                    )
            else:
                bolsa = (
                    "CAJA_DIARIA"
                    if cobro_metodo == "EFECTIVO"
                    else "BANCO_GERENCIA"
                )
                cuenta_slug = (
                    "caja_diaria_secretaria"
                    if cobro_metodo == "EFECTIVO"
                    else "bancos_gerencia"
                )
                etiqueta = "Abono" if forma_pago == "ABONO" else "Cobro"
                pago = await conn.fetchrow(
                    """
                    INSERT INTO payments
                        (order_id, cliente_id, fecha, tipo_movimiento, metodo,
                         monto, referencia, account_id, bolsa, es_anticipo)
                    VALUES ($1, $2, CURRENT_DATE, 'COBRO', $3, $4, $5,
                            (SELECT id FROM accounting_accounts WHERE slug = $6),
                            $7, false)
                    RETURNING id::text, monto
                    """,
                    orden["id"],
                    datos.cliente_id,
                    cobro_metodo,
                    cobro_inicial_monto,
                    f"{etiqueta} inicial orden #{orden['numero']}",
                    cuenta_slug,
                    bolsa,
                )
                cobro_inicial_id = pago["id"]
                cobro_inicial_monto = pago["monto"]

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
        excede_cupo_credito=excede_cupo,
        cupo_credito_usd=cupo_usd,
        saldo_cliente_usd=saldo_usd,
        total=orden["total"],
        iva_pct=orden["iva_pct"],
        iva_monto=orden["iva_monto"],
        total_con_iva=orden["total_con_iva"],
        cobro_inicial_id=cobro_inicial_id,
        cobro_inicial_monto=cobro_inicial_monto,
    )
