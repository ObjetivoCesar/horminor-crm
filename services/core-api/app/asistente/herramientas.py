"""Herramientas deterministas del Gato. Cada una devuelve fichas verificables."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .bibliotecario import Bibliotecario
from .fichas import Resultado, ficha


def _dec(valor: Any, decimales: int = 2) -> str | None:
    if valor is None:
        return None
    return f"{Decimal(str(valor)):.{decimales}f}"


def _cant(valor: Any, decimales: int = 3) -> str | None:
    """Cantidad sin ceros de relleno: 120.000 -> '120'."""
    if valor is None:
        return None
    texto = f"{Decimal(str(valor)):.{decimales}f}".rstrip("0").rstrip(".")
    return texto or "0"


async def ejecutar(nombre: str, params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    if nombre == "cliente_buscar":
        return await _cliente_buscar(params, biblio)
    if nombre == "cartera_cliente":
        return await _cartera_cliente(params, biblio)
    if nombre == "cliente_facturas":
        return await _cliente_facturas(params, biblio)
    if nombre == "cartera_total":
        return await _cartera_total(params, biblio)
    if nombre == "cierre_dia":
        return await _cierre(params, biblio)
    if nombre == "stock_actual":
        return await _stock(params, biblio)
    if nombre == "banco_detalle":
        return await _bancos(params, biblio)
    if nombre == "agenda_obras":
        return await _agenda(params, biblio)
    if nombre == "orden_timeline":
        return await _orden(params, biblio)
    if nombre == "cliente_ordenes":
        return await _orden({"cliente": params["texto"]}, biblio)
    if nombre == "recetas_precio_publico":
        return await _precios(params, biblio)
    if nombre == "cliente_ficha":
        return await _cliente_ficha(params, biblio)
    if nombre == "movimientos_dia":
        return await _movimientos(params, biblio)
    if nombre == "stock_proyectado":
        return await _stock_proyectado(params, biblio)
    if nombre == "viaje_estado":
        return await _viaje(params, biblio)
    if nombre == "balance":
        return await _balance(params, biblio)
    if nombre == "resultados":
        return await _resultados(params, biblio)
    if nombre == "compras_pendientes":
        return await _compras(params, biblio)
    if nombre == "por_pagar":
        return await _por_pagar(params, biblio)
    if nombre == "disponibilidad_agenda":
        return await _disponibilidad(params, biblio)
    if nombre == "banco_movimientos":
        return await _banco_movimientos(params, biblio)
    if nombre == "cuota_mercado":
        return await _cuota_mercado(params, biblio)
    if nombre == "empresa_info":
        return await _empresa(params, biblio)
    if nombre == "salud_sistema":
        return await _salud(params, biblio)
    return Resultado(
        consulta_id=nombre,
        estado="NO_CONECTADA",
        nota=f"La consulta {nombre} aún no está conectada en este prototipo.",
    )


async def _cliente_buscar(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    r = await biblio.buscar_clientes(params["texto"], int(params.get("limite", 5)))
    filtros = {"texto": params["texto"]}
    if not r["datos"]:
        return Resultado("cliente_buscar", "VACIO", fuente=["clients"], filtros=filtros,
                         nota="No encontré clientes con ese texto.")
    fichas = [
        ficha("cliente_buscar", "cliente", c["nombre"], tipo_valor="TEXTO",
              fuente=["clients"], filtros={**filtros, "cliente_id": str(c["id"])})
        for c in r["datos"]
    ]
    return Resultado("cliente_buscar", "OK", datos=r["datos"], fichas=fichas,
                     fuente=["clients"], filtros=filtros)


async def _cartera_cliente(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    r = await biblio.cartera_cliente(params["cliente_id"])
    d = r["datos"]
    filtros = {"cliente_id": params["cliente_id"]}
    if not d:
        return Resultado("cartera_cliente", "VACIO", fuente=["v_cliente_saldo"], filtros=filtros,
                         nota="El cliente no existe o no tiene saldo registrado.")
    fichas = [
        ficha("cartera_cliente", "saldo_pendiente", _dec(d["saldo_pendiente"]), unidad="USD",
              fuente=["v_cliente_saldo"], filtros=filtros),
        ficha("cartera_cliente", "total_fiado", _dec(d["total_fiado"]), unidad="USD",
              fuente=["v_cliente_saldo"], filtros=filtros),
        ficha("cartera_cliente", "total_cobrado", _dec(d["total_cobrado"]), unidad="USD",
              fuente=["v_cliente_saldo"], filtros=filtros),
    ]
    if d.get("credit_limit_usd") is not None:
        fichas.append(
            ficha("cartera_cliente", "cupo", _dec(d["credit_limit_usd"]), unidad="USD",
                  fuente=["v_cliente_saldo"], filtros=filtros)
        )
        disponible = max(
            Decimal("0"),
            Decimal(str(d["credit_limit_usd"])) - Decimal(str(d["saldo_pendiente"])),
        )
        fichas.append(
            ficha("cartera_cliente", "cupo_disponible", _dec(disponible), unidad="USD",
                  fuente=["v_cliente_saldo"], filtros=filtros)
        )
    return Resultado("cartera_cliente", "OK", datos=d, fichas=fichas,
                     fuente=["v_cliente_saldo"], filtros=filtros)


async def _cliente_facturas(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    filtros = {"cliente_id": params["cliente_id"]}
    r = await biblio.facturas_cliente(params["cliente_id"])
    filas = r["datos"]
    if not filas:
        return Resultado(
            "cliente_facturas", "VACIO", fuente=["client_invoices"], filtros=filtros,
            nota="El cliente no tiene facturas internas adjuntas.",
        )
    fichas = []
    for f in filas:
        detalle = {**filtros, "factura": f["numero"]}
        fichas.extend(
            [
                ficha(
                    "cliente_facturas", "subtotal", _dec(f["subtotal"]),
                    unidad="USD", fuente=["client_invoices"], filtros=detalle,
                ),
                ficha(
                    "cliente_facturas", "iva_monto", _dec(f["iva_monto"]),
                    unidad="USD", fuente=["client_invoices"], filtros=detalle,
                ),
                ficha(
                    "cliente_facturas", "total", _dec(f["total"]), unidad="USD",
                    fuente=["client_invoices"], filtros=detalle,
                ),
            ]
        )
    fichas.append(
        ficha(
            "cliente_facturas", "facturas", len(filas), tipo_valor="ENTERO",
            fuente=["client_invoices"], filtros=filtros,
        )
    )
    return Resultado(
        "cliente_facturas", "OK", datos=filas, fichas=fichas,
        fuente=["client_invoices"], filtros=filtros,
    )


async def _cartera_total(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    r = await biblio.cartera()
    filas = r["datos"]
    if not filas:
        return Resultado("cartera_total", "VACIO", fuente=["v_cliente_saldo"],
                         nota="No hay clientes con saldo pendiente.")
    total = sum(Decimal(str(f["saldo_pendiente"])) for f in filas)
    fichas = []
    for f in filas:
        fichas.append(
            ficha("cartera_total", "saldo_pendiente", _dec(f["saldo_pendiente"]), unidad="USD",
                  fuente=["v_cliente_saldo"], filtros={"cliente": f["nombre"]})
        )
        if f.get("credit_limit_usd") is not None:
            fichas.append(
                ficha("cartera_total", "cupo", _dec(f["credit_limit_usd"]), unidad="USD",
                      fuente=["v_cliente_saldo"], filtros={"cliente": f["nombre"]})
            )
    fichas.append(
        ficha("cartera_total", "total_por_cobrar", _dec(total), unidad="USD",
              fuente=["v_cliente_saldo"], filtros={})
    )
    fichas.append(
        ficha("cartera_total", "clientes_con_saldo", len(filas), tipo_valor="ENTERO",
              fuente=["v_cliente_saldo"], filtros={})
    )
    return Resultado("cartera_total", "OK", datos=filas, fichas=fichas,
                     fuente=["v_cliente_saldo"])


async def _cierre(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    from datetime import date

    f = params["desde"] if isinstance(params["desde"], date) else date.fromisoformat(str(params["desde"]))
    r = await biblio.cierre(f)
    d = r["datos"]
    fuente = ["cash_closures"] if r.get("guardado") else ["payments"]
    filtros = {"fecha": f.isoformat()}
    campos = (
        ("efectivo_sistema", "efectivo_sistema", "USD"),
        ("efectivo_contado", "efectivo_contado", "USD"),
        ("transferencias", "transferencias", "USD"),
        ("fiado_otorgado", "fiado_otorgado", "USD"),
        ("caja_chica", "caja_chica", "USD"),
        ("diferencia", "diferencia", "USD"),
    ) if r.get("guardado") else (
        ("efectivo", "cobros_efectivo", "USD"),
        ("transferencias", "transferencias", "USD"),
        ("gastos", "gastos_caja_chica", "USD"),
    )
    fichas = [
        ficha("cierre_dia", dato, _dec(d.get(campo)), unidad=unidad,
              fuente=fuente, filtros=filtros)
        for dato, campo, unidad in campos
        if d.get(campo) is not None
    ]
    if not fichas:
        return Resultado("cierre_dia", "VACIO", fuente=fuente, filtros=filtros,
                         nota="No hay movimientos ni cierre para esa fecha.")
    return Resultado("cierre_dia", "OK", datos=d, fichas=fichas, fuente=fuente, filtros=filtros)


async def _stock(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    r = await biblio.stock()
    filas = r["datos"]
    if not filas:
        return Resultado("stock_actual", "VACIO", fuente=["v_inventario"],
                         nota="No hay materiales registrados.")
    fichas = []
    for f in filas:
        fichas.append(
            ficha("stock_actual", "stock_actual", _cant(f["stock_actual"], 3), unidad=f.get("unidad"),
                  fuente=["v_inventario"], filtros={"material": f["nombre"]})
        )
        if f.get("stock_minimo") is not None:
            fichas.append(
                ficha("stock_actual", "stock_minimo", _cant(f["stock_minimo"], 3), unidad=f.get("unidad"),
                      fuente=["v_inventario"], filtros={"material": f["nombre"]})
            )
            faltante = max(
                Decimal("0"),
                Decimal(str(f["stock_minimo"])) - Decimal(str(f["stock_actual"] or 0)),
            )
            fichas.append(
                ficha("stock_actual", "faltante_para_minimo", _cant(faltante, 3),
                      unidad=f.get("unidad"), fuente=["v_inventario"],
                      filtros={"material": f["nombre"]})
            )
    return Resultado("stock_actual", "OK", datos=filas, fichas=fichas, fuente=["v_inventario"])


async def _bancos(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    r = await biblio.bancos(params.get("banco"))
    filas = r["datos"]
    filtros = {"banco": params.get("banco")} if params.get("banco") else {}
    if not filas:
        return Resultado("banco_detalle", "VACIO", fuente=["bank_accounts", "v_balance_general"],
                         filtros=filtros, nota="No encontré ese banco en el catálogo.")
    fichas = []
    for b in filas:
        fichas.append(
            ficha("banco_detalle", "saldo_contable", _dec(b["saldo_contable"]), unidad="USD",
                  fuente=["v_balance_general"], filtros={"banco": b["slug"]})
        )
        if b.get("saldo_informado") is not None:
            fichas.append(
                ficha("banco_detalle", "saldo_informado", _dec(b["saldo_informado"]), unidad="USD",
                      fuente=["bank_accounts"], filtros={"banco": b["slug"]})
            )
        for p in b.get("prestamos") or []:
            fichas.append(
                ficha("banco_detalle", "saldo_capital", _dec(p["saldo"]), unidad="USD",
                      fuente=["financial_liabilities"], filtros={"banco": b["slug"]})
            )
            if p.get("cuota") is not None:
                fichas.append(
                    ficha("banco_detalle", "cuota", _dec(p["cuota"]), unidad="USD",
                          fuente=["financial_liabilities"], filtros={"banco": b["slug"]})
                )
    return Resultado("banco_detalle", "OK", datos=filas, fichas=fichas,
                     fuente=["bank_accounts", "v_balance_general", "financial_liabilities"], filtros=filtros)


async def _agenda(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    from datetime import date

    desde = params["desde"] if isinstance(params["desde"], date) else date.fromisoformat(str(params["desde"]))
    hasta = params["hasta"] if isinstance(params["hasta"], date) else date.fromisoformat(str(params["hasta"]))
    r = await biblio.agenda(desde, hasta)
    filas = r["datos"]
    filtros = {"desde": desde.isoformat(), "hasta": hasta.isoformat()}
    if not filas:
        return Resultado("agenda_obras", "VACIO", fuente=["dispatch_schedule"], filtros=filtros,
                         nota="No hay entregas programadas para esas fechas.")
    fichas = [
        ficha("agenda_obras", "volumen_m3", _dec(f["volumen_m3"]), unidad="m3",
              fuente=["dispatch_schedule"], filtros={**filtros, "cliente": f["cliente"]})
        for f in filas
    ]
    total = sum(Decimal(str(f["volumen_m3"])) for f in filas)
    fichas.append(
        ficha("agenda_obras", "total_m3", _dec(total), unidad="m3",
              fuente=["dispatch_schedule"], filtros=filtros)
    )
    fichas.append(
        ficha("agenda_obras", "entregas", len(filas), tipo_valor="ENTERO",
              fuente=["dispatch_schedule"], filtros=filtros)
    )
    return Resultado("agenda_obras", "OK", datos=filas, fichas=fichas,
                     fuente=["dispatch_schedule"], filtros=filtros)


async def _orden(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    r = await biblio.orden(params.get("numero"), params.get("cliente"))
    filas = r["datos"]
    filtros = {k: v for k, v in params.items() if v is not None}
    if not filas:
        return Resultado("orden_timeline", "VACIO", fuente=["orders"], filtros=filtros,
                         nota="No encontré órdenes con ese filtro.")
    fichas = []
    for o in filas:
        fichas.append(
            ficha("orden_timeline", "volumen_m3", _dec(o["volumen_m3"]), unidad="m3",
                  fuente=["orders"], filtros={**filtros, "orden_numero": o["numero"]})
        )
        total = o["total_con_iva"] if o["total_con_iva"] is not None else o["total"]
        if total is not None:
            fichas.append(
                ficha("orden_timeline", "total", _dec(total), unidad="USD",
                      fuente=["orders"], filtros={**filtros, "orden_numero": o["numero"]})
            )
    return Resultado("orden_timeline", "OK", datos=filas, fichas=fichas,
                     fuente=["orders"], filtros=filtros)


async def _precios(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    r = await biblio.precios()
    filas = r["datos"]
    if not filas:
        return Resultado("recetas_precio_publico", "VACIO", fuente=["concrete_recipes"],
                         nota="No hay recetas confirmadas con precio.")
    fichas = [
        ficha("recetas_precio_publico", "precio_m3", _dec(p["precio_m3"]), unidad="USD",
              fuente=["concrete_recipes"], filtros={"resistencia": p["resistencia"]})
        for p in filas
    ]
    return Resultado("recetas_precio_publico", "OK", datos=filas, fichas=fichas,
                     fuente=["concrete_recipes"])

async def _cliente_ficha(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    r = await biblio.cliente_ficha(params["cliente_id"])
    d = r["datos"]
    filtros = {"cliente_id": params["cliente_id"]}
    if not d:
        return Resultado("cliente_ficha", "VACIO", fuente=["clients"],
                         filtros=filtros, nota="No encontré ese cliente.")
    fichas = [
        ficha("cliente_ficha", "saldo_pendiente", _dec(d["saldo_pendiente"]), unidad="USD",
              fuente=["v_cliente_saldo"], filtros=filtros),
        ficha("cliente_ficha", "total_fiado", _dec(d["total_fiado"]), unidad="USD",
              fuente=["v_cliente_saldo"], filtros=filtros),
    ]
    return Resultado("cliente_ficha", "OK", datos=d, fichas=fichas,
                     fuente=["clients", "v_cliente_saldo"], filtros=filtros)


async def _movimientos(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    r = await biblio.movimientos_dia(
        params["desde"], params["hasta"], int(params.get("limite", 50))
    )
    filas = r["datos"]
    filtros = {"desde": str(params["desde"]), "hasta": str(params["hasta"])}
    if not filas:
        return Resultado("movimientos_dia", "VACIO", fuente=["payments"],
                         filtros=filtros, nota="No hay movimientos en esas fechas.")
    fichas = [
        ficha("movimientos_dia", "monto", _dec(f["monto"]), unidad="USD",
              fuente=["payments"], filtros={**filtros, "referencia": f["referencia"]})
        for f in filas
    ]
    return Resultado("movimientos_dia", "OK", datos=filas, fichas=fichas,
                     fuente=["payments"], filtros=filtros)


async def _stock_proyectado(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    r = await biblio.stock_proyectado()
    filas = r["datos"]
    if not filas:
        return Resultado("stock_proyectado", "VACIO", fuente=["v_stock_proyectado"],
                         nota="No hay stock proyectado.")
    fichas = []
    for f in filas:
        if f.get("stock_proyectado_disponible") is not None:
            fichas.append(
                ficha("stock_proyectado", "stock_proyectado", _cant(f["stock_proyectado_disponible"], 3),
                      unidad=f.get("unidad"), fuente=["v_stock_proyectado"],
                      filtros={"material": f["nombre"]})
            )
        if f.get("stock_minimo") is not None:
            fichas.append(
                ficha("stock_proyectado", "stock_minimo", _cant(f["stock_minimo"], 3),
                      unidad=f.get("unidad"), fuente=["v_stock_proyectado"],
                      filtros={"material": f["nombre"]})
            )
            disponible = f.get("stock_proyectado_disponible")
            if disponible is not None:
                faltante = max(
                    Decimal("0"),
                    Decimal(str(f["stock_minimo"])) - Decimal(str(disponible)),
                )
                fichas.append(
                    ficha("stock_proyectado", "faltante_para_minimo", _cant(faltante, 3),
                          unidad=f.get("unidad"), fuente=["v_stock_proyectado"],
                          filtros={"material": f["nombre"]})
                )
    return Resultado("stock_proyectado", "OK", datos=filas, fichas=fichas,
                     fuente=["v_stock_proyectado"])


async def _viaje(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    r = await biblio.viaje_estado(params["dispatch_id"])
    d = r["datos"]
    filtros = {"dispatch_id": params["dispatch_id"]}
    if not d:
        return Resultado("viaje_estado", "VACIO", fuente=["v_dispatch_timeline"],
                         filtros=filtros, nota="No encontré ese viaje.")
    fichas = [
        ficha("viaje_estado", "volumen_m3", _dec(d["volumen_m3"]), unidad="m3",
              fuente=["v_dispatch_timeline"], filtros=filtros)
    ]
    return Resultado("viaje_estado", "OK", datos=d, fichas=fichas,
                     fuente=["v_dispatch_timeline"], filtros=filtros)


async def _balance(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    r = await biblio.balance()
    filas = r["datos"]
    if not filas:
        return Resultado("balance", "VACIO", fuente=["v_balance_general"],
                         nota="No hay saldos contables.")
    con_saldo = filas
    fichas = [
        ficha("balance", "saldo_neto", _dec(f["saldo_neto"]), unidad="USD",
              fuente=["v_balance_general"], filtros={"cuenta": f["code"]})
        for f in con_saldo
    ]
    return Resultado("balance", "OK", datos=con_saldo, fichas=fichas,
                     fuente=["v_balance_general"])


async def _resultados(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    r = await biblio.resultados(params["desde"], params["hasta"])
    filas = r["datos"]
    filtros = {"desde": str(params["desde"]), "hasta": str(params["hasta"])}
    if not filas:
        return Resultado("resultados", "VACIO", fuente=["v_estado_resultados"],
                         filtros=filtros, nota="No hay movimientos contables en ese rango.")
    fichas = [
        ficha("resultados", "saldo", _dec(f["saldo"]), unidad="USD",
              fuente=["v_estado_resultados"],
              filtros={**filtros, "cuenta": f["code"], "periodo": str(f["periodo"])})
        for f in filas
    ]
    return Resultado("resultados", "OK", datos=filas, fichas=fichas,
                     fuente=["v_estado_resultados"], filtros=filtros)


async def _compras(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    r = await biblio.compras_pendientes(int(params.get("limite", 50)))
    filas = r["datos"]
    if not filas:
        return Resultado("compras_pendientes", "VACIO", fuente=["purchases"],
                         nota="No hay compras pendientes.")
    fichas = []
    for f in filas:
        fichas.append(
            ficha("compras_pendientes", "monto_total", _dec(f["monto_total"]), unidad="USD",
                  fuente=["purchases"], filtros={"proveedor": f["proveedor"]})
        )
        if f.get("saldo_pendiente") is not None:
            fichas.append(
                ficha("compras_pendientes", "saldo_pendiente", _dec(f["saldo_pendiente"]),
                      unidad="USD", fuente=["purchases"], filtros={"proveedor": f["proveedor"]})
            )
    return Resultado("compras_pendientes", "OK", datos=filas, fichas=fichas,
                     fuente=["purchases", "suppliers"])


async def _por_pagar(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    r = await biblio.por_pagar(int(params.get("limite", 50)))
    filas = r["datos"]
    if not filas:
        return Resultado("por_pagar", "VACIO", fuente=["purchases"],
                         nota="No hay cuentas por pagar.")
    fichas = [
        ficha("por_pagar", "saldo_pendiente", _dec(f["saldo_pendiente"]), unidad="USD",
              fuente=["purchases"], filtros={"proveedor": f["proveedor"]})
        for f in filas
    ]
    return Resultado("por_pagar", "OK", datos=filas, fichas=fichas,
                     fuente=["purchases", "suppliers"])


async def _disponibilidad(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    r = await biblio.disponibilidad_agenda(params["fecha"])
    filas = r["datos"]["filas"]
    libres = r["datos"]["libres"]
    filtros = {"fecha": str(params["fecha"])}
    if not filas and not libres:
        return Resultado("disponibilidad_agenda", "VACIO", fuente=["dispatch_schedule"],
                         filtros=filtros, nota="No hay mixers registrados para ese día.")
    return Resultado("disponibilidad_agenda", "OK",
                     datos={"filas": filas, "libres": libres}, fichas=[],
                     fuente=["dispatch_schedule", "system_settings"], filtros=filtros)


async def _banco_movimientos(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    r = await biblio.banco_movimientos(params["banco"], int(params.get("limite", 20)))
    filas = r["datos"]
    filtros = {"banco": params["banco"]}
    if not filas:
        return Resultado("banco_movimientos", "VACIO", fuente=["payments"],
                         filtros=filtros, nota="No hay movimientos para ese banco.")
    fichas = [
        ficha("banco_movimientos", "monto", _dec(f["monto"]), unidad="USD",
              fuente=["payments"], filtros={**filtros, "referencia": f["referencia"]})
        for f in filas
    ]
    return Resultado("banco_movimientos", "OK", datos=filas, fichas=fichas,
                     fuente=["payments", "bank_accounts"], filtros=filtros)


async def _cuota_mercado(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    r = await biblio.cuota_mercado(
        params.get("provincia", "TODAS"), int(params.get("anio", 2026))
    )
    d = r["datos"]
    filtros = {"provincia": params.get("provincia", "TODAS"), "anio": params.get("anio", 2026)}
    if not d:
        return Resultado("cuota_mercado", "VACIO", fuente=["market_benchmarks"],
                         filtros=filtros, nota="No hay benchmark para esa provincia.")
    ventas = Decimal(str(d["ventas_m3"]))
    demanda = Decimal(str(d["demanda_m3"])) if d.get("demanda_m3") else Decimal("0")
    cuota = (ventas / demanda * 100) if demanda else Decimal("0")
    fichas = [
        ficha("cuota_mercado", "demanda_m3", _dec(d["demanda_m3"]), unidad="m3",
              fuente=["market_benchmarks"], filtros=filtros),
        ficha("cuota_mercado", "ventas_m3", _dec(d["ventas_m3"]), unidad="m3",
              fuente=["orders"], filtros=filtros),
        ficha("cuota_mercado", "cuota_pct", _dec(cuota), unidad="%",
              fuente=["market_benchmarks", "orders"], filtros=filtros),
    ]
    d["cuota_pct"] = str(cuota.quantize(Decimal("0.01")))
    return Resultado("cuota_mercado", "OK", datos=d, fichas=fichas,
                     fuente=["market_benchmarks", "orders"], filtros=filtros)


async def _empresa(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    r = await biblio.empresa_info()
    d = r["datos"]
    if not d:
        return Resultado("empresa_info", "VACIO", fuente=["system_settings"],
                         nota="No hay datos públicos de la empresa.")
    return Resultado("empresa_info", "OK", datos=d, fichas=[], fuente=["system_settings"])


async def _salud(params: dict[str, Any], biblio: Bibliotecario) -> Resultado:
    r = await biblio.salud_sistema()
    d = r["datos"]
    fichas = [
        ficha("salud_sistema", "outbox_encolado", int(d["outbox_encolado"]),
              tipo_valor="ENTERO", fuente=["sandbox_outbox"])
    ]
    for e in d["errores"]:
        fichas.append(
            ficha("salud_sistema", f"errores_{e['nivel'].lower()}", int(e["total"]),
                  tipo_valor="ENTERO", fuente=["error_logs"], filtros={"nivel": e["nivel"]})
        )
    return Resultado("salud_sistema", "OK", datos=d, fichas=fichas,
                     fuente=["error_logs", "sandbox_outbox"])
