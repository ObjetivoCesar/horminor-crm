"""Modulo 3 - Servicio de Secretaria y Caja.

Dos cosas separadas, a proposito:

1. **Calculo puro** (``calcular_resumen_caja``): recibe las ordenes y los
   movimientos del dia y devuelve los totales del cierre. No toca base de
   datos, por eso se prueba sin infraestructura.
2. **Persistencia** (``PostgresSecretariaStore`` / ``MemorySecretariaStore``):
   el mismo contrato para la UI real y para los tests.

La regla de credito de la Directriz 2026-11-08 vive en
``services/ordenes.py``: la orden se registra igual y queda marcada con
``excede_cupo_credito``.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping, Protocol, Sequence

import asyncpg

# ---------------------------------------------------------------------------
# Calculo puro del cierre de caja
# ---------------------------------------------------------------------------
FORMAS_VENTA = ("EFECTIVO", "TRANSFERENCIA", "ABONO", "FIADO")


def _d(valor: Any) -> Decimal:
    if valor is None or valor == "":
        return Decimal("0")
    try:
        return Decimal(str(valor))
    except (TypeError, ValueError):
        return Decimal("0")


def calcular_resumen_caja(
    *,
    fecha: date,
    ordenes: Sequence[Mapping[str, Any]],
    movimientos: Sequence[Mapping[str, Any]],
    efectivo_contado: Decimal | None = None,
) -> dict[str, Any]:
    """Totales del dia a partir de ordenes y ``payments``.

    - ``ventas_*``: ordenes creadas ese dia por forma de pago.
    - ``cobros_*``: movimientos ``COBRO`` registrados ese dia.
    - ``caja_chica``: movimientos ``GASTO_CAJA_CHICA``.
    - ``efectivo_esperado`` = cobros en efectivo - caja chica.
    """
    ventas = {forma: Decimal("0") for forma in FORMAS_VENTA}
    for orden in ordenes:
        forma = str(orden.get("forma_pago") or "").upper()
        if forma in ventas:
            ventas[forma] += _d(orden.get("total"))

    cobros = {"EFECTIVO": Decimal("0"), "TRANSFERENCIA": Decimal("0"), "FIADO": Decimal("0")}
    caja_chica = Decimal("0")
    detalle: list[dict[str, Any]] = []
    for mov in movimientos:
        tipo = str(mov.get("tipo_movimiento") or "").upper()
        metodo = str(mov.get("metodo") or "").upper()
        monto = _d(mov.get("monto"))
        if tipo == "GASTO_CAJA_CHICA":
            caja_chica += monto
        elif tipo == "COBRO" and metodo in cobros:
            cobros[metodo] += monto
        else:
            continue
        detalle.append(
            {
                "id": str(mov.get("id") or ""),
                "hora": str(mov.get("created_at") or ""),
                "tipo": tipo,
                "metodo": metodo,
                "monto": float(monto),
                "referencia": mov.get("referencia"),
            }
        )

    esperado = cobros["EFECTIVO"] - caja_chica
    diferencia = None if efectivo_contado is None else (_d(efectivo_contado) - esperado)

    return {
        "fecha": fecha.isoformat(),
        "ventas": {
            "efectivo": float(ventas["EFECTIVO"]),
            "transferencia": float(ventas["TRANSFERENCIA"]),
            "abono": float(ventas["ABONO"]),
            "fiado": float(ventas["FIADO"]),
            "total": float(sum(ventas.values())),
        },
        "cobros": {
            "efectivo": float(cobros["EFECTIVO"]),
            "transferencia": float(cobros["TRANSFERENCIA"]),
            "fiado": float(cobros["FIADO"]),
            "total": float(sum(cobros.values())),
        },
        "caja_chica": float(caja_chica),
        "efectivo_sistema": float(esperado),
        "efectivo_contado": None if efectivo_contado is None else float(_d(efectivo_contado)),
        "diferencia": None if diferencia is None else float(diferencia),
        "detalle": detalle,
        "generado_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Contrato de persistencia
# ---------------------------------------------------------------------------
class SecretariaStore(Protocol):
    async def listar_clientes(self, busqueda: str | None = None) -> list[dict[str, Any]]: ...

    async def obtener_carpeta(self, cliente_id: str) -> dict[str, Any] | None: ...

    async def listar_ordenes(
        self, cliente_id: str | None = None, limite: int = 50
    ) -> list[dict[str, Any]]: ...

    async def resumen_cierre(
        self, fecha: date, efectivo_contado: Decimal | None = None
    ) -> dict[str, Any]: ...

    async def cerrar_caja(
        self,
        *,
        fecha: date,
        efectivo_contado: Decimal | None,
        cerrado_por: str | None = None,
        observaciones: str | None = None,
    ) -> dict[str, Any]: ...

    async def listar_cierres(self, limite: int = 30) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------
class PostgresSecretariaStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def listar_clientes(self, busqueda: str | None = None) -> list[dict[str, Any]]:
        patron = f"%{(busqueda or '').strip()}%"
        filas = await self._pool.fetch(
            """
            SELECT c.id::text, c.nombre, c.constructora, c.ruc,
                   c.telefono_whatsapp, c.estado, c.credit_limit_usd,
                   COALESCE(s.total_m3, 0)         AS total_m3,
                   COALESCE(s.total_facturado, 0)  AS total_facturado,
                   COALESCE(s.saldo_pendiente, 0)  AS saldo_pendiente
              FROM clients c
              LEFT JOIN v_cliente_saldo s ON s.id = c.id
             WHERE ($1 = '%%' OR c.nombre ILIKE $1 OR COALESCE(c.constructora,'') ILIKE $1)
             ORDER BY c.nombre
             LIMIT 200
            """,
            patron,
        )
        return [
            {
                "cliente_id": fila["id"],
                "nombre": fila["nombre"],
                "constructora": fila["constructora"],
                "ruc": fila["ruc"],
                "telefono": fila["telefono_whatsapp"],
                "estado": fila["estado"],
                "credit_limit_usd": _f(fila["credit_limit_usd"]),
                "total_m3": _f(fila["total_m3"]),
                "total_facturado": _f(fila["total_facturado"]),
                "saldo_pendiente": _f(fila["saldo_pendiente"]),
            }
            for fila in filas
        ]

    async def obtener_carpeta(self, cliente_id: str) -> dict[str, Any] | None:
        cliente = await self._pool.fetchrow(
            """
            SELECT c.id::text, c.nombre, c.constructora, c.ruc,
                   c.telefono_whatsapp, c.estado, c.notas, c.credit_limit_usd,
                   COALESCE(s.total_m3, 0)        AS total_m3,
                   COALESCE(s.total_facturado, 0) AS total_facturado,
                   COALESCE(s.total_cobrado, 0)   AS total_cobrado,
                   COALESCE(s.total_fiado, 0)     AS total_fiado,
                   COALESCE(s.saldo_pendiente, 0) AS saldo_pendiente
              FROM clients c
              LEFT JOIN v_cliente_saldo s ON s.id = c.id
             WHERE c.id = $1
            """,
            cliente_id,
        )
        if cliente is None:
            return None

        ordenes = await self.listar_ordenes(cliente_id=cliente_id, limite=30)
        viajes = await self._pool.fetch(
            """
            SELECT id::text, order_id::text, orden_numero, resistencia, planta,
                   viaje_numero, total_viajes_orden, mixer_codigo, chofer_nombre,
                   volumen_m3, estado_actual, despacho_validado,
                   recepcion_validada, incidencia_detectada,
                   dosificado_planta, salida_planta, limite_termico_fraguado,
                   llegada_obra_chofer, confirmacion_whatsapp_cliente,
                   cemento_sacos_teorico, cemento_sacos_real, retardante_litros,
                   tracking_payload
              FROM v_dispatch_timeline
             WHERE order_id IN (
                 SELECT id FROM orders WHERE cliente_id = $1
             )
             ORDER BY order_id DESC, viaje_numero
             LIMIT 60
            """,
            cliente_id,
        )
        evidencias: list[dict[str, Any]] = []
        timeline: list[dict[str, Any]] = []
        for fila in viajes:
            payload = _json_objeto(fila["tracking_payload"])
            for url in payload.get("evidencias_bunny_cdn") or []:
                evidencias.append(
                    {
                        "url": url,
                        "dispatch_id": fila["id"],
                        "orden_numero": fila["orden_numero"],
                        "viaje_numero": fila["viaje_numero"],
                        "vehiculo": fila["mixer_codigo"],
                    }
                )
            for clave, etiqueta in (
                ("salida_planta", "Salida de planta"),
                ("llegada_obra_chofer", "Llegada a obra"),
                ("confirmacion_whatsapp_cliente", "Confirmacion del cliente"),
            ):
                valor = fila[clave]
                if valor:
                    timeline.append(
                        {
                            "fecha": valor.isoformat(),
                            "tipo": etiqueta,
                            "detalle": (
                                f"Orden #{fila['orden_numero']} - viaje "
                                f"{fila['viaje_numero']}/{fila['total_viajes_orden']}"
                            ),
                        }
                    )

        return {
            "cliente": {
                "cliente_id": cliente["id"],
                "nombre": cliente["nombre"],
                "constructora": cliente["constructora"],
                "ruc": cliente["ruc"],
                "telefono": cliente["telefono_whatsapp"],
                "estado": cliente["estado"],
                "notas": cliente["notas"],
                "credit_limit_usd": _f(cliente["credit_limit_usd"]),
            },
            "saldo": {
                "total_m3": _f(cliente["total_m3"]),
                "total_facturado": _f(cliente["total_facturado"]),
                "total_cobrado": _f(cliente["total_cobrado"]),
                "total_fiado": _f(cliente["total_fiado"]),
                "saldo_pendiente": _f(cliente["saldo_pendiente"]),
            },
            "ordenes": ordenes,
            "viajes": [
                {
                    "dispatch_id": fila["id"],
                    "orden_numero": fila["orden_numero"],
                    "resistencia": fila["resistencia"],
                    "planta": fila["planta"],
                    "viaje_numero": fila["viaje_numero"],
                    "total_viajes": fila["total_viajes_orden"],
                    "mixer_codigo": fila["mixer_codigo"],
                    "chofer_nombre": fila["chofer_nombre"],
                    "volumen_m3": _f(fila["volumen_m3"]),
                    "estado_actual": fila["estado_actual"],
                    "juez": {
                        "despacho_validado": bool(fila["despacho_validado"]),
                        "recepcion_validada": bool(fila["recepcion_validada"]),
                        "incidencia_detectada": bool(fila["incidencia_detectada"]),
                    },
                    "salida_planta": _iso(fila["salida_planta"]),
                    "limite_termico_fraguado": _iso(fila["limite_termico_fraguado"]),
                }
                for fila in viajes
            ],
            "evidencias": evidencias,
            "timeline": sorted(timeline, key=lambda item: item["fecha"], reverse=True),
        }

    async def listar_ordenes(
        self, cliente_id: str | None = None, limite: int = 50
    ) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT o.id::text, o.numero, o.cliente_id::text, c.nombre AS cliente,
                   o.resistencia, o.volumen_m3, p.nombre AS planta,
                   o.forma_pago, o.precio_m3, o.total, o.estado,
                   o.excede_cupo_credito, o.creada_por, o.created_at
              FROM orders o
              JOIN clients c ON c.id = o.cliente_id
              JOIN plants  p ON p.id = o.planta_id
             WHERE ($1::uuid IS NULL OR o.cliente_id = $1::uuid)
             ORDER BY o.created_at DESC, o.numero DESC
             LIMIT $2
            """,
            cliente_id,
            max(1, min(int(limite), 200)),
        )
        return [_orden_dict(fila) for fila in filas]

    async def _movimientos(self, fecha: date) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT id::text, order_id::text, cliente_id::text, fecha,
                   tipo_movimiento, metodo, monto, referencia, created_at
              FROM payments
             WHERE fecha = $1
             ORDER BY created_at
            """,
            fecha,
        )
        return [dict(fila) for fila in filas]

    async def _ordenes_del_dia(self, fecha: date) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT o.id::text, o.numero, o.cliente_id::text, c.nombre AS cliente,
                   o.resistencia, o.volumen_m3, p.nombre AS planta,
                   o.forma_pago, o.precio_m3, o.total, o.estado,
                   o.excede_cupo_credito, o.creada_por, o.created_at
              FROM orders o
              JOIN clients c ON c.id = o.cliente_id
              JOIN plants  p ON p.id = o.planta_id
             WHERE o.created_at::date = $1
               AND o.estado <> 'ANULADA'
             ORDER BY o.created_at
            """,
            fecha,
        )
        return [_orden_dict(fila) for fila in filas]

    async def resumen_cierre(
        self, fecha: date, efectivo_contado: Decimal | None = None
    ) -> dict[str, Any]:
        resumen = calcular_resumen_caja(
            fecha=fecha,
            ordenes=await self._ordenes_del_dia(fecha),
            movimientos=await self._movimientos(fecha),
            efectivo_contado=efectivo_contado,
        )
        cierre = await self._pool.fetchrow(
            """
            SELECT fecha, estado, efectivo_sistema, efectivo_contado,
                   transferencias, fiado_otorgado, caja_chica, diferencia,
                   snapshot, cerrado_por, cerrado_at
              FROM cash_closures
             WHERE fecha = $1
            """,
            fecha,
        )
        resumen["cierre"] = _cierre_dict(cierre) if cierre is not None else None
        resumen["cerrado"] = cierre is not None and cierre["estado"] == "CERRADO"
        return resumen

    async def cerrar_caja(
        self,
        *,
        fecha: date,
        efectivo_contado: Decimal | None,
        cerrado_por: str | None = None,
        observaciones: str | None = None,
    ) -> dict[str, Any]:
        resumen = await self.resumen_cierre(
            fecha, efectivo_contado=efectivo_contado
        )
        snapshot = {k: v for k, v in resumen.items() if k not in {"cierre", "cerrado"}}
        if observaciones:
            snapshot["observaciones"] = observaciones
        fila = await self._pool.fetchrow(
            """
            INSERT INTO cash_closures
                (fecha, estado, efectivo_sistema, efectivo_contado,
                 transferencias, fiado_otorgado, caja_chica, diferencia,
                 snapshot, cerrado_por, cerrado_at)
            VALUES ($1, 'CERRADO', $2, $3, $4, $5, $6, $7, $8::jsonb, $9, now())
            ON CONFLICT (fecha) DO UPDATE
               SET estado = 'REABIERTO',
                   efectivo_sistema = EXCLUDED.efectivo_sistema,
                   efectivo_contado = EXCLUDED.efectivo_contado,
                   transferencias = EXCLUDED.transferencias,
                   fiado_otorgado = EXCLUDED.fiado_otorgado,
                   caja_chica = EXCLUDED.caja_chica,
                   diferencia = EXCLUDED.diferencia,
                   snapshot = EXCLUDED.snapshot,
                   cerrado_por = EXCLUDED.cerrado_por,
                   cerrado_at = now()
            RETURNING fecha, estado, efectivo_sistema, efectivo_contado,
                      transferencias, fiado_otorgado, caja_chica, diferencia,
                      snapshot, cerrado_por, cerrado_at
            """,
            fecha,
            Decimal(str(resumen["efectivo_sistema"])),
            None if efectivo_contado is None else Decimal(str(efectivo_contado)),
            Decimal(str(resumen["cobros"]["transferencia"])),
            Decimal(str(resumen["ventas"]["fiado"])),
            Decimal(str(resumen["caja_chica"])),
            None if resumen["diferencia"] is None else Decimal(str(resumen["diferencia"])),
            _json(snapshot),
            cerrado_por,
        )
        return _cierre_dict(fila)

    async def listar_cierres(self, limite: int = 30) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT fecha, estado, efectivo_sistema, efectivo_contado,
                   transferencias, fiado_otorgado, caja_chica, diferencia,
                   snapshot, cerrado_por, cerrado_at
              FROM cash_closures
             ORDER BY fecha DESC
             LIMIT $1
            """,
            max(1, min(int(limite), 120)),
        )
        return [_cierre_dict(fila) for fila in filas]


def _f(valor: Any) -> float | None:
    if valor is None:
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _iso(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.isoformat()
    return str(valor)


def _json(valor: Any) -> str:
    import json

    return json.dumps(valor, ensure_ascii=False, default=str)


def _json_objeto(valor: Any) -> dict[str, Any]:
    """Normaliza un jsonb: asyncpg puede devolverlo como texto crudo."""
    if isinstance(valor, str):
        import json

        try:
            valor = json.loads(valor)
        except ValueError:
            return {}
    return dict(valor) if isinstance(valor, Mapping) else {}


def _orden_dict(fila: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "orden_id": fila["id"],
        "numero": fila["numero"],
        "cliente_id": fila["cliente_id"],
        "cliente": fila.get("cliente"),
        "resistencia": fila["resistencia"],
        "volumen_m3": _f(fila["volumen_m3"]),
        "planta": fila.get("planta"),
        "forma_pago": fila["forma_pago"],
        "precio_m3": _f(fila["precio_m3"]),
        "total": _f(fila["total"]),
        "estado": fila["estado"],
        "excede_cupo_credito": bool(fila.get("excede_cupo_credito")),
        "creada_por": fila.get("creada_por"),
        "created_at": _iso(fila.get("created_at")),
    }


def _cierre_dict(fila: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fecha": _iso(fila["fecha"]),
        "estado": fila["estado"],
        "efectivo_sistema": _f(fila["efectivo_sistema"]),
        "efectivo_contado": _f(fila["efectivo_contado"]),
        "transferencias": _f(fila["transferencias"]),
        "fiado_otorgado": _f(fila["fiado_otorgado"]),
        "caja_chica": _f(fila["caja_chica"]),
        "diferencia": _f(fila["diferencia"]),
        "snapshot": dict(fila.get("snapshot") or {}),
        "cerrado_por": fila.get("cerrado_por"),
        "cerrado_at": _iso(fila.get("cerrado_at")),
    }


# ---------------------------------------------------------------------------
# Memoria (tests y demos sin PostgreSQL)
# ---------------------------------------------------------------------------
@dataclass
class MemorySecretariaStore:
    """Datos de demostracion con la misma forma que las vistas reales."""

    clientes: list[dict[str, Any]] = field(default_factory=list)
    ordenes: list[dict[str, Any]] = field(default_factory=list)
    viajes: list[dict[str, Any]] = field(default_factory=list)
    movimientos: list[dict[str, Any]] = field(default_factory=list)
    cierres: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.clientes:
            return
        self.clientes = [
            {
                "cliente_id": "11111111-1111-1111-1111-111111111111",
                "nombre": "Constructora Reyes",
                "constructora": "Ing. Reyes",
                "ruc": "2290000000001",
                "telefono": "+593990000201",
                "estado": "ACTIVO",
                "notas": "Cliente de demostracion",
                "credit_limit_usd": 1500.0,
                "total_m3": 52.0,
                "total_facturado": 6136.0,
                "total_cobrado": 3000.0,
                "total_fiado": 3136.0,
                "saldo_pendiente": 3136.0,
            },
            {
                "cliente_id": "22222222-2222-2222-2222-222222222222",
                "nombre": "Petroconstrucciones",
                "constructora": "Petroconstrucciones S.A.",
                "ruc": "2290000000002",
                "telefono": "+593990000202",
                "estado": "ACTIVO",
                "notas": "Proyecto via Auca",
                "credit_limit_usd": 1500.0,
                "total_m3": 24.0,
                "total_facturado": 2832.0,
                "total_cobrado": 2832.0,
                "total_fiado": 0.0,
                "saldo_pendiente": 0.0,
            },
        ]
        self.ordenes = [
            {
                "orden_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "numero": 1001,
                "cliente_id": self.clientes[0]["cliente_id"],
                "cliente": self.clientes[0]["nombre"],
                "resistencia": "FC-210",
                "volumen_m3": 52.0,
                "planta": "Planta Fija El Coca",
                "forma_pago": "FIADO",
                "precio_m3": 118.0,
                "total": 6136.0,
                "estado": "CONFIRMADA",
                "excede_cupo_credito": True,
                "creada_por": "Secretaria",
                "created_at": f"{date.today().isoformat()}T12:00:00+00:00",
            }
        ]
        self.viajes = [
            {
                "dispatch_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
                "orden_numero": 1001,
                "resistencia": "FC-210",
                "planta": "Planta Fija El Coca",
                "viaje_numero": 1,
                "total_viajes": 7,
                "mixer_codigo": "MIXER-01",
                "chofer_nombre": "Pedro Andy",
                "volumen_m3": 8.0,
                "estado_actual": "EN_RUTA",
                "juez": {
                    "despacho_validado": True,
                    "recepcion_validada": False,
                    "incidencia_detectada": False,
                },
                "salida_planta": datetime.now(timezone.utc).isoformat(),
                "limite_termico_fraguado": None,
                "evidencias": [
                    "https://horminor.b-cdn.net/sandbox/evidencias/MIXER-01/viaje-1.jpg"
                ],
            }
        ]
        self.movimientos = [
            {
                "id": "p-1",
                "order_id": self.ordenes[0]["orden_id"],
                "tipo_movimiento": "COBRO",
                "metodo": "EFECTIVO",
                "monto": 500.0,
                "fecha": date.today(),
                "created_at": f"{date.today().isoformat()}T12:10:00+00:00",
            },
            {
                "id": "p-2",
                "tipo_movimiento": "GASTO_CAJA_CHICA",
                "metodo": "EFECTIVO",
                "monto": 25.0,
                "fecha": date.today(),
                "created_at": f"{date.today().isoformat()}T12:20:00+00:00",
            },
        ]

    async def listar_clientes(self, busqueda: str | None = None) -> list[dict[str, Any]]:
        texto = (busqueda or "").strip().lower()
        return [
            copy.deepcopy(cliente)
            for cliente in self.clientes
            if not texto
            or texto in str(cliente["nombre"]).lower()
            or texto in str(cliente.get("constructora") or "").lower()
        ]

    async def _cliente(self, cliente_id: str) -> dict[str, Any] | None:
        return next(
            (c for c in self.clientes if c["cliente_id"] == cliente_id), None
        )

    async def obtener_carpeta(self, cliente_id: str) -> dict[str, Any] | None:
        cliente = await self._cliente(cliente_id)
        if cliente is None:
            return None
        ordenes = await self.listar_ordenes(cliente_id=cliente_id, limite=30)
        viajes = [
            copy.deepcopy(v)
            for v in self.viajes
            if any(o["orden_id"] and o["numero"] == v["orden_numero"] for o in ordenes)
        ]
        evidencias = [
            {
                "url": url,
                "dispatch_id": viaje["dispatch_id"],
                "orden_numero": viaje["orden_numero"],
                "viaje_numero": viaje["viaje_numero"],
                "vehiculo": viaje["mixer_codigo"],
            }
            for viaje in viajes
            for url in viaje.get("evidencias", [])
        ]
        timeline = [
            {
                "fecha": viaje["salida_planta"],
                "tipo": "Salida de planta",
                "detalle": (
                    f"Orden #{viaje['orden_numero']} - viaje "
                    f"{viaje['viaje_numero']}/{viaje['total_viajes']}"
                ),
            }
            for viaje in viajes
            if viaje.get("salida_planta")
        ]
        return {
            "cliente": copy.deepcopy(cliente),
            "saldo": {
                "total_m3": cliente["total_m3"],
                "total_facturado": cliente["total_facturado"],
                "total_cobrado": cliente["total_cobrado"],
                "total_fiado": cliente["total_fiado"],
                "saldo_pendiente": cliente["saldo_pendiente"],
            },
            "ordenes": ordenes,
            "viajes": viajes,
            "evidencias": evidencias,
            "timeline": timeline,
        }

    async def listar_ordenes(
        self, cliente_id: str | None = None, limite: int = 50
    ) -> list[dict[str, Any]]:
        filas = [
            copy.deepcopy(o)
            for o in self.ordenes
            if cliente_id is None or o["cliente_id"] == cliente_id
        ]
        return filas[: max(1, int(limite))]

    def _ordenes_del_dia(self, fecha: date) -> list[dict[str, Any]]:
        return [
            o
            for o in self.ordenes
            if str(o.get("created_at") or "")[:10] == fecha.isoformat()
            and o.get("estado") != "ANULADA"
        ]

    def _movimientos_del_dia(self, fecha: date) -> list[dict[str, Any]]:
        return [m for m in self.movimientos if m.get("fecha") == fecha]

    async def resumen_cierre(
        self, fecha: date, efectivo_contado: Decimal | None = None
    ) -> dict[str, Any]:
        resumen = calcular_resumen_caja(
            fecha=fecha,
            ordenes=self._ordenes_del_dia(fecha),
            movimientos=self._movimientos_del_dia(fecha),
            efectivo_contado=efectivo_contado,
        )
        cierre = next(
            (c for c in self.cierres if c["fecha"] == fecha.isoformat()), None
        )
        resumen["cierre"] = copy.deepcopy(cierre)
        resumen["cerrado"] = cierre is not None and cierre["estado"] == "CERRADO"
        return resumen

    async def cerrar_caja(
        self,
        *,
        fecha: date,
        efectivo_contado: Decimal | None,
        cerrado_por: str | None = None,
        observaciones: str | None = None,
    ) -> dict[str, Any]:
        resumen = await self.resumen_cierre(
            fecha, efectivo_contado=efectivo_contado
        )
        cierre = {
            "fecha": fecha.isoformat(),
            "estado": "CERRADO",
            "efectivo_sistema": resumen["efectivo_sistema"],
            "efectivo_contado": resumen["efectivo_contado"],
            "transferencias": resumen["cobros"]["transferencia"],
            "fiado_otorgado": resumen["ventas"]["fiado"],
            "caja_chica": resumen["caja_chica"],
            "diferencia": resumen["diferencia"],
            "snapshot": {k: v for k, v in resumen.items() if k not in {"cierre", "cerrado"}},
            "cerrado_por": cerrado_por,
            "cerrado_at": datetime.now(timezone.utc).isoformat(),
        }
        if observaciones:
            cierre["snapshot"]["observaciones"] = observaciones
        self.cierres = [c for c in self.cierres if c["fecha"] != cierre["fecha"]]
        self.cierres.insert(0, cierre)
        return cierre

    async def listar_cierres(self, limite: int = 30) -> list[dict[str, Any]]:
        return copy.deepcopy(self.cierres[: max(1, int(limite))])
