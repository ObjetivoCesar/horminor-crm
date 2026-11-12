"""Bibliotecario de datos del asistente interno (solo lectura)."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

import asyncpg

_NOMBRE_SQL = (
    "regexp_replace("
    "translate(lower(coalesce({col}, '')), 'áéíóúüñ', 'aeiouun'), "
    "'[^a-z0-9]+', ' ', 'g')"
)


def _norm_busqueda(texto: str) -> str:
    """Normaliza nombres y consultas: sin tildes, sin puntuación, minúsculas."""
    base = unicodedata.normalize("NFKD", str(texto or ""))
    base = "".join(c for c in base if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", base).strip()


class Bibliotecario:
    """Consultas nombradas. Devuelve datos + fuente; nunca inventa."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def cartera(self) -> dict[str, Any]:
        filas = await self.pool.fetch(
            """
            SELECT nombre, saldo_pendiente, total_fiado, credit_limit_usd
              FROM v_cliente_saldo
             WHERE saldo_pendiente > 0
             ORDER BY saldo_pendiente DESC
            """
        )
        return {"datos": [dict(f) for f in filas], "fuente": "v_cliente_saldo"}

    async def buscar_clientes(self, texto: str, limite: int = 5) -> dict[str, Any]:
        patron = _norm_busqueda(texto)
        if not patron:
            return {"datos": [], "fuente": "clients"}
        campos = (
            _NOMBRE_SQL.format(col="nombre"),
            _NOMBRE_SQL.format(col="constructora"),
            _NOMBRE_SQL.format(col="ciudad"),
            _NOMBRE_SQL.format(col="direccion_obra"),
            "lower(coalesce(ruc, ''))",
            "lower(coalesce(cedula, ''))",
            "lower(coalesce(telefono_whatsapp, ''))",
        )
        where = " OR ".join(f"{campo} LIKE '%' || $1 || '%'" for campo in campos)
        filas = await self.pool.fetch(
            f"""
            SELECT id, nombre, ruc, estado
              FROM clients
             WHERE {where}
             ORDER BY nombre
             LIMIT $2
            """,
            patron,
            limite,
        )
        return {"datos": [dict(f) for f in filas], "fuente": "clients"}

    async def cartera_cliente(self, cliente_id: str) -> dict[str, Any]:
        fila = await self.pool.fetchrow(
            """
            SELECT c.id, c.nombre, c.credit_limit_usd,
                   COALESCE(v.saldo_pendiente, 0) AS saldo_pendiente,
                   COALESCE(v.total_fiado, 0) AS total_fiado,
                   COALESCE(v.total_cobrado, 0) AS total_cobrado
              FROM clients c
              LEFT JOIN v_cliente_saldo v ON v.id = c.id
             WHERE c.id = $1
            """,
            cliente_id,
        )
        return {"datos": dict(fila) if fila else None, "fuente": "v_cliente_saldo"}

    async def cliente(self, texto: str) -> dict[str, Any]:
        patron = _norm_busqueda(texto)
        if not patron:
            return {"datos": None, "fuente": "clients", "vacio": True}
        fila = await self.pool.fetchrow(
            f"""
            SELECT c.id, c.nombre, c.ruc, c.estado, c.provincia, c.ciudad,
                   c.credit_limit_usd,
                   COALESCE(v.saldo_pendiente, 0) AS saldo_pendiente,
                   COALESCE(v.total_fiado, 0) AS total_fiado,
                   COALESCE(v.total_cobrado, 0) AS total_cobrado
              FROM clients c
              LEFT JOIN v_cliente_saldo v ON v.id = c.id
             WHERE {_NOMBRE_SQL.format(col='c.nombre')} LIKE '%' || $1 || '%'
                OR {_NOMBRE_SQL.format(col='c.constructora')} LIKE '%' || $1 || '%'
                OR lower(coalesce(c.ruc, '')) LIKE '%' || $1 || '%'
                OR lower(coalesce(c.cedula, '')) LIKE '%' || $1 || '%'
             ORDER BY c.nombre
             LIMIT 1
            """,
            patron,
        )
        if not fila:
            return {"datos": None, "fuente": "clients", "vacio": True}
        ultima = await self.pool.fetchrow(
            """
            SELECT numero, resistencia, volumen_m3, forma_pago, total, estado
              FROM orders
             WHERE cliente_id = $1
             ORDER BY numero DESC
             LIMIT 1
            """,
            fila["id"],
        )
        datos = dict(fila)
        datos["ultima_orden"] = dict(ultima) if ultima else None
        return {"datos": datos, "fuente": "clients + v_cliente_saldo"}

    async def cierre(self, fecha: date) -> dict[str, Any]:
        fila = await self.pool.fetchrow(
            "SELECT * FROM cash_closures WHERE fecha = $1", fecha
        )
        if fila:
            return {"datos": dict(fila), "fuente": "cash_closures", "guardado": True}
        fila = await self.pool.fetchrow(
            """
            SELECT
              COALESCE(SUM(monto) FILTER (WHERE tipo_movimiento = 'COBRO' AND metodo = 'EFECTIVO'), 0) AS efectivo,
              COALESCE(SUM(monto) FILTER (WHERE tipo_movimiento = 'COBRO' AND metodo = 'TRANSFERENCIA'), 0) AS transferencias,
              COALESCE(SUM(monto) FILTER (WHERE tipo_movimiento = 'GASTO_CAJA_CHICA'), 0) AS gastos
              FROM payments
             WHERE fecha = $1 AND deleted_at IS NULL
            """,
            fecha,
        )
        return {"datos": dict(fila), "fuente": "payments", "guardado": False}

    async def stock(self) -> dict[str, Any]:
        filas = await self.pool.fetch(
            """
            SELECT nombre, unidad, stock_actual, stock_minimo, estado
              FROM v_inventario
             ORDER BY CASE estado
                        WHEN 'CRITICO' THEN 0
                        WHEN 'SIN_UMBRAL' THEN 1
                        WHEN 'SIN_LEVANTAR' THEN 2
                        ELSE 3
                      END, nombre
            """
        )
        return {"datos": [dict(f) for f in filas], "fuente": "v_inventario"}

    async def bancos(self, banco: str | None = None) -> dict[str, Any]:
        filas = await self.pool.fetch(
            """
            SELECT b.slug, b.nombre, b.numero_cuenta, b.estado,
                   b.saldo_informado, b.saldo_informado_at,
                   COALESCE(v.saldo_neto, 0) AS saldo_contable,
                   COALESCE((
                     SELECT json_agg(json_build_object(
                       'entidad', l.entidad_financiera,
                       'saldo', l.saldo_capital_actual,
                       'cuota', l.cuota_mensual_referencial,
                       'tasa', l.tasa_interes_anual_pct,
                       'plazo', l.plazo_restante_meses
                     ))
                       FROM financial_liabilities l
                      WHERE l.bank_account_id = b.id AND l.deleted_at IS NULL
                   ), '[]'::json) AS prestamos
              FROM bank_accounts b
              LEFT JOIN v_balance_general v ON v.account_id = b.accounting_account_id
             ORDER BY b.slug
            """
        )
        datos: list[dict[str, Any]] = []
        for f in filas:
            fila = dict(f)
            prestamos = fila.get("prestamos")
            if isinstance(prestamos, str):
                import json

                fila["prestamos"] = json.loads(prestamos)
            datos.append(fila)
        if banco:
            from .texto import normalizar

            datos = [
                d for d in datos
                if d["slug"] == banco or banco in normalizar(d["nombre"])
            ]
        return {"datos": datos, "fuente": "bank_accounts + v_balance_general"}

    async def agenda(self, desde: date, hasta: date) -> dict[str, Any]:
        filas = await self.pool.fetch(
            """
            SELECT d.fecha_entrega, d.hora_inicio, d.volumen_m3,
                   d.direccion_obra, d.mixer_codigo, d.estado,
                   c.nombre AS cliente
              FROM dispatch_schedule d
              JOIN clients c ON c.id = d.cliente_id
             WHERE d.deleted_at IS NULL
               AND d.fecha_entrega BETWEEN $1 AND $2
             ORDER BY d.fecha_entrega, d.hora_inicio
            """,
            desde,
            hasta,
        )
        return {"datos": [dict(f) for f in filas], "fuente": "dispatch_schedule"}

    async def orden(self, numero: int | None = None, cliente: str | None = None) -> dict[str, Any]:
        filas = await self.pool.fetch(
            """
            SELECT o.numero, c.nombre AS cliente, o.resistencia, o.volumen_m3,
                   o.forma_pago, o.total, o.total_con_iva, o.estado, o.created_at
              FROM orders o
              JOIN clients c ON c.id = o.cliente_id
             WHERE ($1::bigint IS NULL OR o.numero = $1)
               AND ($2::text IS NULL OR lower(c.nombre) LIKE '%' || lower($2) || '%')
             ORDER BY o.numero DESC
             LIMIT 5
            """,
            numero,
            cliente,
        )
        return {"datos": [dict(f) for f in filas], "fuente": "orders"}

    async def precios(self) -> dict[str, Any]:
        filas = await self.pool.fetch(
            """
            SELECT resistencia, precio_m3, iva_pct, uso_comercial
              FROM concrete_recipes
             WHERE confirmado AND precio_m3 IS NOT NULL
             ORDER BY resistencia
            """
        )
        return {"datos": [dict(f) for f in filas], "fuente": "concrete_recipes"}

    async def facturas_cliente(self, cliente_id: str) -> dict[str, Any]:
        filas = await self.pool.fetch(
            """
            SELECT f.numero, f.fecha, f.subtotal, f.iva_pct, f.iva_monto,
                   f.total, f.estado, f.es_ficticia, f.nota,
                   o.numero AS orden_numero, f.media_id::text,
                   m.nombre_original, m.mime_final
              FROM client_invoices f
              LEFT JOIN orders o ON o.id = f.orden_id
              LEFT JOIN media_assets m ON m.id = f.media_id
             WHERE f.cliente_id = $1
             ORDER BY f.fecha DESC, f.created_at DESC
            """,
            cliente_id,
        )
        datos: list[dict[str, Any]] = []
        for fila in filas:
            item = dict(fila)
            item["url"] = (
                f"/api/v1/media/{item['media_id']}/archivo"
                if item.get("media_id")
                else None
            )
            datos.append(item)
        return {"datos": datos, "fuente": "client_invoices"}

    async def cliente_ficha(self, cliente_id: str) -> dict[str, Any]:
        fila = await self.pool.fetchrow(
            """
            SELECT c.id, c.nombre, c.ruc, c.constructora, c.telefono_whatsapp,
                   c.estado, c.provincia, c.ciudad, c.direccion_obra,
                   COALESCE(v.saldo_pendiente, 0) AS saldo_pendiente,
                   COALESCE(v.total_fiado, 0) AS total_fiado
              FROM clients c
              LEFT JOIN v_cliente_saldo v ON v.id = c.id
             WHERE c.id = $1
            """,
            cliente_id,
        )
        return {"datos": dict(fila) if fila else None, "fuente": "clients + v_cliente_saldo"}

    async def movimientos_dia(self, desde: str, hasta: str, limite: int = 50) -> dict[str, Any]:
        filas = await self.pool.fetch(
            """
            SELECT fecha, tipo_movimiento, metodo, monto, referencia
              FROM payments
             WHERE fecha BETWEEN $1 AND $2 AND deleted_at IS NULL
             ORDER BY fecha, created_at
             LIMIT $3
            """,
            desde,
            hasta,
            limite,
        )
        return {"datos": [dict(f) for f in filas], "fuente": "payments"}

    async def stock_proyectado(self) -> dict[str, Any]:
        filas = await self.pool.fetch(
            """
            SELECT nombre, unidad, stock_real_fisico, consumo_teorico_acumulado,
                   stock_proyectado_disponible, stock_minimo, estado_alerta_proyectada
              FROM v_stock_proyectado
             ORDER BY nombre
            """
        )
        return {"datos": [dict(f) for f in filas], "fuente": "v_stock_proyectado"}

    async def viaje_estado(self, dispatch_id: str) -> dict[str, Any]:
        fila = await self.pool.fetchrow(
            """
            SELECT id, orden_numero, cliente, viaje_numero, total_viajes_orden,
                   mixer_codigo, chofer_nombre, estado_actual, volumen_m3,
                   salida_planta, limite_termico_fraguado, incidencia_detectada
              FROM v_dispatch_timeline
             WHERE id = $1
            """,
            dispatch_id,
        )
        return {"datos": dict(fila) if fila else None, "fuente": "v_dispatch_timeline"}

    async def balance(self) -> dict[str, Any]:
        filas = await self.pool.fetch(
            "SELECT code, name, saldo_neto FROM v_balance_general ORDER BY code"
        )
        return {"datos": [dict(f) for f in filas], "fuente": "v_balance_general"}

    async def resultados(self, desde: str, hasta: str) -> dict[str, Any]:
        filas = await self.pool.fetch(
            """
            SELECT periodo, code, name, saldo
              FROM v_estado_resultados
             WHERE periodo BETWEEN $1 AND $2
             ORDER BY periodo, code
            """,
            desde,
            hasta,
        )
        return {"datos": [dict(f) for f in filas], "fuente": "v_estado_resultados"}

    async def compras_pendientes(self, limite: int = 50) -> dict[str, Any]:
        filas = await self.pool.fetch(
            """
            SELECT s.nombre AS proveedor, p.fecha_compra, p.monto_total,
                   p.saldo_pendiente, p.estado_recepcion
              FROM purchases p
              JOIN suppliers s ON s.id = p.supplier_id
             WHERE p.deleted_at IS NULL
               AND p.estado_recepcion IN ('PENDIENTE', 'PARCIAL')
             ORDER BY p.fecha_compra
             LIMIT $1
            """,
            limite,
        )
        return {"datos": [dict(f) for f in filas], "fuente": "purchases + suppliers"}

    async def por_pagar(self, limite: int = 50) -> dict[str, Any]:
        filas = await self.pool.fetch(
            """
            SELECT s.nombre AS proveedor, SUM(p.saldo_pendiente) AS saldo_pendiente
              FROM purchases p
              JOIN suppliers s ON s.id = p.supplier_id
             WHERE p.deleted_at IS NULL AND p.saldo_pendiente > 0
             GROUP BY s.nombre
             ORDER BY saldo_pendiente DESC
             LIMIT $1
            """,
            limite,
        )
        return {"datos": [dict(f) for f in filas], "fuente": "purchases + suppliers"}

    async def disponibilidad_agenda(self, fecha: str) -> dict[str, Any]:
        filas = await self.pool.fetch(
            """
            SELECT mixer_codigo, hora_inicio, hora_fin_estimada, estado
              FROM dispatch_schedule
             WHERE fecha_entrega = $1 AND deleted_at IS NULL
               AND estado NOT IN ('CANCELADO', 'REAGENDADO')
             ORDER BY hora_inicio
            """,
            fecha,
        )
        flota = await self.pool.fetchval(
            "SELECT value FROM system_settings WHERE key = 'flota.mixers'"
        )
        if isinstance(flota, str):
            import json

            try:
                flota = json.loads(flota)
            except json.JSONDecodeError:
                flota = []
        activos = [m["codigo"] for m in (flota or []) if m.get("activo", True)]
        ocupados = {f["mixer_codigo"] for f in filas if f["mixer_codigo"]}
        libres = [c for c in activos if c not in ocupados]
        return {
            "datos": {"filas": [dict(f) for f in filas], "libres": libres},
            "fuente": "dispatch_schedule + system_settings",
        }

    async def banco_movimientos(self, banco: str, limite: int = 20) -> dict[str, Any]:
        filas = await self.pool.fetch(
            """
            SELECT p.fecha, p.tipo_movimiento, p.metodo, p.monto, p.referencia
              FROM payments p
              JOIN bank_accounts b ON b.accounting_account_id = p.account_id
             WHERE b.slug = $1 AND p.deleted_at IS NULL
             ORDER BY p.fecha DESC
             LIMIT $2
            """,
            banco,
            limite,
        )
        return {"datos": [dict(f) for f in filas], "fuente": "payments + bank_accounts"}

    async def cuota_mercado(self, provincia: str, anio: int) -> dict[str, Any]:
        fila = await self.pool.fetchrow(
            """
            SELECT b.provincia, b.demanda_m3,
                   COALESCE(SUM(o.volumen_m3), 0) AS ventas_m3
              FROM market_benchmarks b
              LEFT JOIN clients c ON c.provincia = b.provincia
              LEFT JOIN orders o ON o.cliente_id = c.id
                   AND date_part('year', o.created_at) = b.anio
             WHERE b.anio = $1 AND ($2 = 'TODAS' OR upper(b.provincia) = upper($2))
             GROUP BY b.provincia, b.demanda_m3
            """,
            anio,
            provincia,
        )
        return {"datos": dict(fila) if fila else None, "fuente": "market_benchmarks + orders"}

    async def empresa_info(self) -> dict[str, Any]:
        fila = await self.pool.fetchrow(
            "SELECT value FROM system_settings WHERE key = 'empresa.bot_publico'"
        )
        valor = fila["value"] if fila else None
        if isinstance(valor, str):
            import json

            try:
                valor = json.loads(valor)
            except json.JSONDecodeError:
                valor = None
        return {"datos": valor, "fuente": "system_settings"}

    async def salud_sistema(self) -> dict[str, Any]:
        errores = await self.pool.fetch(
            """
            SELECT nivel, count(*) AS total
              FROM error_logs
             WHERE created_at > now() - interval '1 day'
             GROUP BY nivel
            """
        )
        outbox = await self.pool.fetchval(
            "SELECT count(*) FROM sandbox_outbox WHERE estado = 'ENCOLADO'"
        )
        return {
            "datos": {
                "errores": [dict(e) for e in errores],
                "outbox_encolado": int(outbox or 0),
            },
            "fuente": "error_logs + sandbox_outbox",
        }
