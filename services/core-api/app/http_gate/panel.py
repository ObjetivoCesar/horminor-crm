"""Puente interno del panel web con el Custodio v4.4.0.

El navegador no recibe ``CUSTODIO_TOKEN_*``. Mientras el login de usuario
final (Paso 3) no exista, el panel llama a estas rutas y el servidor resuelve
un actor de panel por ``X-Panel-Role`` (default SECRETARIA). Cuando se agregue
la sesión, este archivo se reemplaza por la dependencia de sesión y las rutas
pueden quedar como fachada interna.

v6.0 agrega la puerta de compras/proveedores, el inventario enriquecido y el
motor real de agendamiento. Todo pasa por el Custodio: el panel no escribe
asientos ni stock por su cuenta.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ..custodio.gate import Actor
from ..m3_secretaria.agenda import (
    PostgresAgendaStore,
    conflicto_mixer,
    evaluar_disponibilidad,
    mixers_activos,
)
from .auth import ActorContext
from .payments import (
    PagoCreate,
    _es_reintento,
    _resolver_request_id,
    _solicitud,
)
from .router import _gate, http_response

router = APIRouter(prefix="/api/v1/panel", tags=["panel"])

ROLES_PANEL = ("SUPERADMIN", "CONTADORA", "SECRETARIA")
ROLES_BODEGA = ROLES_PANEL + ("BODEGA", "BODEGA_PLANTA")

def _pool(request: Request):
    """Acepta asyncpg.Pool o un envoltorio con ``acquire`` (tests/clon)."""
    pool = getattr(request.app.state, "pool", None)
    if pool is None or not hasattr(pool, "acquire"):
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "pool no disponible"},
        )
    return pool


def _contexto_panel(
    rol: str, actor_id: str | None, permitidos: tuple[str, ...] = ROLES_PANEL
) -> ActorContext:
    rol = str(rol or "SECRETARIA").strip().upper()
    if rol not in permitidos:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "UNAUTHORIZED_DOMAIN_ACCESS",
                "message": "el rol no opera esta sección del panel",
            },
        )
    identificador = str(actor_id or "").strip() or f"{rol}_PANEL"
    return ActorContext(actor=Actor(role=rol, id=identificador), channel="WEB_PANEL")


async def _leer_setting(pool, key: str) -> Any:
    """Lee un valor de ``system_settings`` tal como esta guardado.

    Puede ser objeto (``secretaria.pagos``) o arreglo (``flota.mixers``). Los
    consumidores que esperan objeto usan ``_reglas_dict``.
    """
    try:
        valor = await pool.fetchval(
            "SELECT value FROM system_settings WHERE key = $1", key
        )
    except Exception:
        return {}
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except ValueError:
            return {}
    return valor


def _reglas_dict(valor: Any) -> dict[str, Any]:
    return dict(valor) if isinstance(valor, dict) else {}


def _solicitud_gate(request_id: str, intent: str, payload: dict[str, Any]) -> dict:
    return {
        "contract_version": "1.3.0",
        "request_id": request_id,
        "channel": "WEB_PANEL",
        "intent": intent,
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# Catálogo y cobros/gastos
# ---------------------------------------------------------------------------
@router.get("/catalog")
async def catalogo_panel(request: Request) -> dict[str, Any]:
    """Solo las cuentas que la ventanilla puede usar."""
    filas = await _pool(request).fetch(
        """
        SELECT id::text, code, slug, name, account_type, normal_balance,
               parent_group, default_bolsa, requires_voucher,
               is_system_locked, visible_en_ventanilla
          FROM accounting_accounts
         WHERE deleted_at IS NULL
           AND visible_en_ventanilla = true
         ORDER BY CASE slug
                    WHEN 'viaticos_peajes_caja_chica' THEN 0
                    WHEN 'materiales_oficina_papeleria' THEN 1
                    WHEN 'mantenimiento_repuestos_mixers' THEN 2
                    ELSE 3
                  END,
                  code
        """
    )
    return {"cuentas": [dict(f) for f in filas]}


@router.get("/pagos/reglas")
async def reglas_pago_panel(request: Request) -> dict[str, Any]:
    """Tope y reglas editables de la ventanilla (Superadmin las cambia)."""
    reglas = await _leer_setting(_pool(request), "secretaria.pagos")
    return {"reglas": _reglas_dict(reglas)}


def excede_tope_caja(
    tope: Any, monto: Decimal, autorizado_exceso: bool = False
) -> Decimal | None:
    """Devuelve el limite si el gasto en efectivo lo supera; si no, ``None``.

    El tope es un parametro de ``system_settings``. Un valor invalido o vacio
    se trata como "sin tope" en vez de romper la ventanilla.
    """
    if autorizado_exceso or tope is None:
        return None
    try:
        limite = Decimal(str(tope))
    except Exception:
        return None
    return limite if monto > limite else None


@router.post("/pagos")
async def registrar_pago_panel(
    request: Request,
    body: PagoCreate = Body(...),
    rol: str = Header(default="SECRETARIA", alias="X-Panel-Role"),
    actor_id: str | None = Header(default=None, alias="X-Panel-Actor"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Fachada interna: mismo contrato y mismas reglas que el endpoint oficial."""
    ctx = _contexto_panel(rol, actor_id)

    # Tope de caja chica: solo aplica a gastos en efectivo. Lo que supera el
    # tope sale por banco o exige autorizacion explicita.
    if body.tipo_movimiento != "COBRO" and body.metodo == "EFECTIVO":
        pool = getattr(request.app.state, "pool", None)
        if pool is not None and hasattr(pool, "acquire"):
            reglas = _reglas_dict(
                await _leer_setting(pool, "secretaria.pagos")
            )
            limite = excede_tope_caja(
                reglas.get("caja_chica_max_monto_usd"),
                body.monto,
                body.autorizado_exceso_caja,
            )
            if limite is not None:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "CAJA_CHICA_LIMIT_EXCEEDED",
                        "message": (
                            "el gasto supera el tope de caja chica "
                            f"({limite:.2f} USD); usa transferencia o "
                            "marca la autorizacion de exceso"
                        ),
                        "limite": float(limite),
                    },
                )

    request_id = _resolver_request_id(body, idempotency_key)
    gate = _gate(request)
    reintento = await _es_reintento(gate, request_id)
    respuesta = await gate.mutar(_solicitud(request_id, body, ctx), ctx.actor)
    return http_response(respuesta, success_code=200 if reintento else 201)


# ---------------------------------------------------------------------------
# Proveedores
# ---------------------------------------------------------------------------
class ProveedorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=2, max_length=160)
    identificacion: str | None = Field(default=None, max_length=40)
    telefono: str | None = Field(default=None, max_length=40)


@router.get("/suppliers")
async def listar_proveedores(request: Request) -> dict[str, Any]:
    filas = await _pool(request).fetch(
        """
        SELECT id::text, nombre, identificacion, telefono, activo, created_at
          FROM suppliers
         WHERE activo = true
         ORDER BY nombre
        """
    )
    return {"suppliers": [dict(f) for f in filas]}


@router.post("/suppliers")
async def crear_proveedor_panel(
    request: Request,
    body: ProveedorCreate = Body(...),
    rol: str = Header(default="SECRETARIA", alias="X-Panel-Role"),
    actor_id: str | None = Header(default=None, alias="X-Panel-Actor"),
):
    ctx = _contexto_panel(rol, actor_id, ROLES_BODEGA)
    gate = _gate(request)
    payload = {
        "nombre": body.nombre.strip(),
        "identificacion": (body.identificacion or "").strip() or None,
        "telefono": (body.telefono or "").strip() or None,
    }
    respuesta = await gate.mutar(
        _solicitud_gate(str(uuid4()), "CREATE_SUPPLIER", payload), ctx.actor
    )
    return http_response(respuesta, success_code=201)


# ---------------------------------------------------------------------------
# Compras de material
# ---------------------------------------------------------------------------
class CompraItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_id: UUID | None = None
    account_slug: str = "inventario_insumos_silos"
    descripcion: str = Field(min_length=2, max_length=160)
    cantidad: Decimal = Field(gt=0, max_digits=14, decimal_places=4)
    costo_unitario: Decimal = Field(ge=0, max_digits=14, decimal_places=4)


class CompraIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: UUID
    fecha_compra: date
    modalidad_pago: Literal[
        "CONTADO_EFECTIVO",
        "CONTADO_TRANSFERENCIA",
        "CREDITO_PROVEEDOR",
        "MIXTO_ABONO_CREDITO",
    ]
    modo_recepcion: Literal["INMEDIATA", "EN_TRANSITO"] = "INMEDIATA"
    referencia_comprobante: str | None = Field(default=None, max_length=120)
    iva_monto: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    monto_pagado_hoy: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    bolsa_pago_hoy: Literal["CAJA_DIARIA", "BANCO_GERENCIA"] | None = None
    fecha_vencimiento: date | None = None
    items: list[CompraItemIn] = Field(min_length=1)


def _payload_compra(body: CompraIn) -> dict[str, Any]:
    subtotal = sum(
        (item.cantidad * item.costo_unitario for item in body.items),
        Decimal("0"),
    ).quantize(Decimal("0.01"))
    total = subtotal + body.iva_monto

    if body.modalidad_pago in ("CONTADO_EFECTIVO", "CONTADO_TRANSFERENCIA"):
        pagado = total
        bolsa = (
            "CAJA_DIARIA"
            if body.modalidad_pago == "CONTADO_EFECTIVO"
            else "BANCO_GERENCIA"
        )
    elif body.modalidad_pago == "MIXTO_ABONO_CREDITO":
        pagado = body.monto_pagado_hoy or Decimal("0")
        bolsa = body.bolsa_pago_hoy or "CAJA_DIARIA"
    else:
        pagado = Decimal("0")
        bolsa = None

    payload: dict[str, Any] = {
        "supplier_id": str(body.supplier_id),
        "fecha_compra": body.fecha_compra.isoformat(),
        "modalidad_pago": body.modalidad_pago,
        "modo_recepcion": body.modo_recepcion,
        "iva_monto": format(body.iva_monto, ".2f"),
        "monto_pagado_hoy": format(pagado, ".2f"),
        "items": [
            {
                "material_id": str(item.material_id) if item.material_id else None,
                "account_slug": item.account_slug,
                "descripcion": item.descripcion,
                "cantidad": format(item.cantidad, ".4f"),
                "costo_unitario": format(item.costo_unitario, ".4f"),
            }
            for item in body.items
        ],
    }
    if bolsa is not None:
        payload["bolsa_pago_hoy"] = bolsa
    if body.referencia_comprobante:
        payload["referencia_comprobante"] = body.referencia_comprobante
    if body.fecha_vencimiento:
        payload["fecha_vencimiento"] = body.fecha_vencimiento.isoformat()
    return payload


@router.post("/purchases")
async def registrar_compra_panel(
    request: Request,
    body: CompraIn = Body(...),
    rol: str = Header(default="SECRETARIA", alias="X-Panel-Role"),
    actor_id: str | None = Header(default=None, alias="X-Panel-Actor"),
):
    ctx = _contexto_panel(rol, actor_id, ROLES_BODEGA)
    gate = _gate(request)
    respuesta = await gate.mutar(
        _solicitud_gate(str(uuid4()), "REGISTER_PURCHASE", _payload_compra(body)),
        ctx.actor,
    )
    return http_response(respuesta, success_code=201)


@router.post("/purchases/items/{item_id}/receive")
async def recibir_compra_panel(
    request: Request,
    item_id: str,
    body: dict[str, Any] = Body(...),
    rol: str = Header(default="BODEGA", alias="X-Panel-Role"),
    actor_id: str | None = Header(default=None, alias="X-Panel-Actor"),
):
    ctx = _contexto_panel(rol, actor_id, ROLES_BODEGA)
    gate = _gate(request)
    payload = {
        "purchase_item_id": item_id,
        "cantidad_recibida": str(body.get("cantidad_recibida") or ""),
    }
    if body.get("guia_remision"):
        payload["guia_remision"] = body["guia_remision"]
    respuesta = await gate.mutar(
        _solicitud_gate(str(uuid4()), "RECEIVE_PURCHASED_MATERIAL", payload),
        ctx.actor,
    )
    return http_response(respuesta, success_code=200)


@router.get("/purchases")
async def listar_compras(request: Request, limite: int = Query(default=30, ge=1, le=200)):
    pool = _pool(request)
    compras = await pool.fetch(
        """
        SELECT p.id::text, p.fecha_compra, p.modalidad_pago, p.subtotal,
               p.iva_monto, p.monto_total, p.monto_pagado, p.saldo_pendiente,
               p.estado_recepcion, p.referencia_comprobante, p.created_at,
               s.nombre AS proveedor
          FROM purchases p
          JOIN suppliers s ON s.id = p.supplier_id
         WHERE p.deleted_at IS NULL
         ORDER BY p.created_at DESC
         LIMIT $1
        """,
        limite,
    )
    return {"purchases": [dict(f) for f in compras]}


# ---------------------------------------------------------------------------
# Inventario enriquecido
# ---------------------------------------------------------------------------
@router.get("/inventory-overview")
async def inventario_panel(request: Request) -> dict[str, Any]:
    pool = _pool(request)
    materiales = await pool.fetch(
        """
        SELECT m.id::text, m.codigo, m.nombre, m.unidad, m.stock_actual,
               m.stock_minimo, m.costo_unitario, v.estado,
               m.ultimo_levantamiento_at
          FROM materials m
          LEFT JOIN v_inventario v ON v.codigo = m.codigo
         ORDER BY m.codigo
        """
    )
    en_transito = await pool.fetch(
        """
        SELECT pi.id::text AS purchase_item_id, p.id::text AS purchase_id,
               p.fecha_compra, s.nombre AS proveedor,
               m.codigo AS material_codigo, m.nombre AS material,
               m.unidad, pi.cantidad_comprada, pi.cantidad_recibida,
               (pi.cantidad_comprada - pi.cantidad_recibida) AS pendiente,
               pi.costo_unitario
          FROM purchase_items pi
          JOIN purchases p ON p.id = pi.purchase_id
          JOIN materials m ON m.id = pi.material_id
          JOIN suppliers s ON s.id = p.supplier_id
         WHERE p.deleted_at IS NULL
           AND p.estado_recepcion IN ('PENDIENTE', 'PARCIAL')
           AND pi.cantidad_recibida < pi.cantidad_comprada
         ORDER BY p.fecha_compra DESC
         LIMIT 50
        """
    )
    movimientos = await pool.fetch(
        """
        SELECT im.id, m.nombre AS material, m.unidad, im.tipo, im.cantidad,
               im.referencia, im.costo_unitario_snapshot, im.created_at
          FROM inventory_movements im
          JOIN materials m ON m.id = im.material_id
         ORDER BY im.id DESC
         LIMIT 20
        """
    )
    return {
        "materiales": [dict(f) for f in materiales],
        "en_transito": [dict(f) for f in en_transito],
        "movimientos": [dict(f) for f in movimientos],
    }


# ---------------------------------------------------------------------------
# Agendamiento real de entregas
# ---------------------------------------------------------------------------
class AgendaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: UUID | None = None
    cliente_id: UUID
    planta_id: UUID | None = None
    mixer_codigo: str | None = Field(default=None, max_length=40)
    chofer_nombre: str | None = Field(default=None, max_length=120)
    receta_codigo: str | None = Field(default=None, max_length=40)
    volumen_m3: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    fecha_entrega: date
    hora_inicio: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    duracion_estimada_min: int = Field(default=90, ge=30, le=720)
    direccion_obra: str = Field(min_length=3, max_length=300)
    contacto_obra_telefono: str | None = Field(default=None, max_length=40)
    estado: Literal[
        "RESERVA_CAMPO",
        "PROGRAMADO",
        "EN_PLANTA",
        "EN_RUTA",
        "COMPLETADO",
        "REAGENDADO",
        "CANCELADO",
    ] = "PROGRAMADO"
    notas: str | None = Field(default=None, max_length=500)


class AgendaPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: UUID | None = None
    cliente_id: UUID | None = None
    planta_id: UUID | None = None
    mixer_codigo: str | None = Field(default=None, max_length=40)
    chofer_nombre: str | None = Field(default=None, max_length=120)
    receta_codigo: str | None = Field(default=None, max_length=40)
    volumen_m3: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    fecha_entrega: date | None = None
    hora_inicio: str | None = Field(
        default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$"
    )
    duracion_estimada_min: int | None = Field(default=None, ge=30, le=720)
    direccion_obra: str | None = Field(default=None, min_length=3, max_length=300)
    contacto_obra_telefono: str | None = Field(default=None, max_length=40)
    estado: Literal[
        "RESERVA_CAMPO",
        "PROGRAMADO",
        "EN_PLANTA",
        "EN_RUTA",
        "COMPLETADO",
        "REAGENDADO",
        "CANCELADO",
    ] | None = None
    motivo_reagendamiento: str | None = Field(default=None, max_length=300)
    notas: str | None = Field(default=None, max_length=500)


def _store_agenda(request: Request) -> PostgresAgendaStore:
    return PostgresAgendaStore(_pool(request))


async def _mixers(pool) -> list[dict[str, Any]]:
    flota = await _leer_setting(pool, "flota.mixers")
    return mixers_activos(flota)


def _conflicto_o_409(
    *,
    filas: list[dict[str, Any]],
    mixer_codigo: str | None,
    fecha: date,
    hora: str,
    duracion: int,
    excluir_id: str | None = None,
) -> None:
    choque = conflicto_mixer(
        filas=filas,
        mixer_codigo=mixer_codigo,
        fecha=fecha,
        hora=hora,
        duracion_min=duracion,
        excluir_id=excluir_id,
    )
    if choque:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MIXER_SCHEDULE_CONFLICT",
                "message": (
                    f"el {mixer_codigo} ya esta ocupado de "
                    f"{choque['hora_inicio']} a {choque['hora_fin']}"
                ),
                "conflicto": choque,
            },
        )


@router.get("/agenda")
async def listar_agenda(
    request: Request,
    desde: date | None = Query(default=None),
    hasta: date | None = Query(default=None),
):
    hoy = date.today()
    desde = desde or hoy
    hasta = hasta or (hoy + timedelta(days=14))
    if hasta < desde:
        raise HTTPException(status_code=422, detail="hasta no puede ser anterior a desde")
    filas = await _store_agenda(request).listar(desde, hasta)
    return {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "agenda": filas}


@router.get("/agenda/disponibilidad")
async def disponibilidad_agenda(
    request: Request,
    fecha: date = Query(...),
    hora: str = Query(..., pattern=r"^([01]\d|2[0-3]):[0-5]\d$"),
    duracion_min: int = Query(default=90, ge=30, le=720),
    mixer_codigo: str | None = Query(default=None),
    excluir_id: str | None = Query(default=None),
):
    pool = _pool(request)
    filas = await _store_agenda(request).listar(fecha, fecha)
    mixers = await _mixers(pool)
    resultado = evaluar_disponibilidad(
        filas=filas,
        mixers=mixers,
        fecha=fecha,
        hora=hora,
        duracion_min=duracion_min,
        excluir_id=excluir_id,
    )
    if mixer_codigo:
        resultado["mixer_consultado"] = mixer_codigo
        resultado["conflicto"] = conflicto_mixer(
            filas=filas,
            mixer_codigo=mixer_codigo,
            fecha=fecha,
            hora=hora,
            duracion_min=duracion_min,
            excluir_id=excluir_id,
        )
    return resultado


@router.post("/agenda")
async def crear_agenda(
    request: Request,
    body: AgendaIn = Body(...),
    rol: str = Header(default="SECRETARIA", alias="X-Panel-Role"),
    actor_id: str | None = Header(default=None, alias="X-Panel-Actor"),
):
    ctx = _contexto_panel(rol, actor_id)
    store = _store_agenda(request)
    filas = await store.listar(body.fecha_entrega, body.fecha_entrega)
    _conflicto_o_409(
        filas=filas,
        mixer_codigo=body.mixer_codigo,
        fecha=body.fecha_entrega,
        hora=body.hora_inicio,
        duracion=body.duracion_estimada_min,
    )
    datos = body.model_dump()
    datos["creado_por_rol"] = ctx.actor.role
    datos["creado_por_id"] = ctx.actor.id
    fila = await store.crear(datos)
    return {"agenda": fila}


@router.patch("/agenda/{agenda_id}")
async def editar_agenda(
    request: Request,
    agenda_id: str,
    body: AgendaPatch = Body(...),
    rol: str = Header(default="SECRETARIA", alias="X-Panel-Role"),
    actor_id: str | None = Header(default=None, alias="X-Panel-Actor"),
):
    _contexto_panel(rol, actor_id)
    store = _store_agenda(request)
    actual = await store.obtener(agenda_id)
    if actual is None:
        raise HTTPException(status_code=404, detail="agendamiento no encontrado")

    cambios = body.model_dump(exclude_unset=True)
    if not cambios:
        return {"agenda": actual}

    fecha = cambios.get("fecha_entrega") or date.fromisoformat(actual["fecha_entrega"])
    hora = cambios.get("hora_inicio") or actual["hora_inicio"]
    duracion = cambios.get("duracion_estimada_min") or actual["duracion_estimada_min"]
    mixer = cambios.get("mixer_codigo", actual.get("mixer_codigo"))
    filas = await store.listar(fecha, fecha)
    _conflicto_o_409(
        filas=filas,
        mixer_codigo=mixer,
        fecha=fecha,
        hora=hora,
        duracion=int(duracion or 90),
        excluir_id=agenda_id,
    )
    fila = await store.actualizar(agenda_id, cambios)
    return {"agenda": fila}


@router.delete("/agenda/{agenda_id}")
async def cancelar_agenda(
    request: Request,
    agenda_id: str,
    rol: str = Header(default="SECRETARIA", alias="X-Panel-Role"),
    actor_id: str | None = Header(default=None, alias="X-Panel-Actor"),
):
    _contexto_panel(rol, actor_id)
    ok = await _store_agenda(request).cancelar(agenda_id)
    if not ok:
        raise HTTPException(status_code=404, detail="agendamiento no encontrado")
    return {"cancelado": True, "id": agenda_id}
