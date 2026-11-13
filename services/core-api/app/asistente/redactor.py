"""Redactor de Gato: convierte fichas/resultados en texto corto y trazable."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .fichas import Resultado


def money(valor: Any) -> str:
    if valor is None:
        return "sin dato"
    numero = Decimal(str(valor))
    signo = "-" if numero < 0 else ""
    texto = f"{abs(numero):,.2f}"
    return signo + "$" + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def numero(valor: Any, decimales: int = 2) -> str:
    if valor is None:
        return "sin dato"
    d = Decimal(str(valor))
    return f"{d:,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _traza(r: Resultado) -> str:
    fuente = ", ".join(r.fuente) if r.fuente else "sin fuente"
    filtros = ", ".join(f"{k}={v}" for k, v in r.filtros.items()) if r.filtros else "ninguno"
    return f"Fuente: {fuente} · Filtros: {filtros} · Consultado: {r.consultado_en}"


def _saludo(rol: str, nombre: str) -> str:
    if rol == "SUPERADMIN":
        return "Jefe"
    return nombre or "Señor(a)"


def _cartera_total(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    filas = r.datos or []
    total = next((f.valor for f in r.fichas if f.dato == "total_por_cobrar"), None)
    lineas = [f"{_saludo(actor_rol, actor_nombre)}, hay {len(filas)} clientes con saldo:"]
    for f in filas:
        cupo = f.get("credit_limit_usd")
        extra = f" (cupo {money(cupo)})" if cupo is not None else ""
        lineas.append(f"- {f['nombre']}: {money(f['saldo_pendiente'])}{extra}")
    lineas.append(f"Total por cobrar: {money(total)}.")
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _cartera_cliente(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    d = r.datos
    lineas = [f"{_saludo(actor_rol, actor_nombre)}, {d['nombre']}:"]
    lineas.append(f"- Saldo pendiente: {money(d['saldo_pendiente'])}")
    lineas.append(f"- Fiado: {money(d['total_fiado'])} · Cobrado: {money(d['total_cobrado'])}")
    if d.get("credit_limit_usd") is not None:
        lineas.append(f"- Cupo: {money(d['credit_limit_usd'])}")
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _fecha(valor: Any) -> str:
    if hasattr(valor, "strftime"):
        return valor.strftime("%d/%m/%Y")
    return str(valor)


def _facturas(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    filas = r.datos or []
    cliente = r.filtros.get("cliente") or "el cliente"
    lineas = [f"{_saludo(actor_rol, actor_nombre)}, facturas internas de {cliente}:"]
    for f in filas:
        ficticia = " · FICTICIA (prueba)" if f.get("es_ficticia") else ""
        orden = f" · orden #{f['orden_numero']}" if f.get("orden_numero") else ""
        lineas.append(
            f"- {f['numero']} · {_fecha(f['fecha'])} · {money(f['total'])} · "
            f"{f['estado']}{orden}{ficticia}"
        )
        if f.get("url"):
            descarga = str(f["url"]).split("?")[0] + "?download=1"
            lineas.append(f"  Descargar: {descarga}")
    if any(f.get("es_ficticia") for f in filas):
        lineas.append(
            "Las marcadas FICTICIA son documentos de prueba: no son comprobantes "
            "electrónicos del SRI ni sirven para cobro."
        )
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _cierre(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    d = r.datos
    guardado = r.fuente == ["cash_closures"]
    fecha = d.get("fecha", r.filtros.get("fecha", ""))
    lineas = [f"{_saludo(actor_rol, actor_nombre)}, el cierre del {_fecha(fecha)}:"]
    if guardado:
        lineas.append(f"- Efectivo del sistema: {money(d['efectivo_sistema'])}")
        lineas.append(f"- Efectivo contado: {money(d['efectivo_contado'])}")
        lineas.append(f"- Transferencias: {money(d['transferencias'])}")
        lineas.append(f"- Fiado: {money(d['fiado_otorgado'])} · Caja chica: {money(d['caja_chica'])}")
        lineas.append(f"- Diferencia: {money(d['diferencia'])}")
    else:
        lineas.append("- No hay cierre guardado; con los movimientos del día:")
        lineas.append(f"- Cobros en efectivo: {money(d['efectivo'])}")
        lineas.append(f"- Transferencias: {money(d['transferencias'])}")
        lineas.append(f"- Gastos de caja chica: {money(d['gastos'])}")
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _stock(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    criticos = [f for f in (r.datos or []) if f["estado"] == "CRITICO"]
    if not criticos:
        return f"{_saludo(actor_rol, actor_nombre)}, no hay materiales críticos en bodega.\n{_traza(r)}"
    lineas = [f"{_saludo(actor_rol, actor_nombre)}, esto está crítico en bodega:"]
    for f in criticos:
        unidad = {"saco": "sacos", "m3": "m³", "litro": "litros"}.get(f.get("unidad") or "", f.get("unidad") or "")
        lineas.append(f"- {f['nombre']}: {numero(f['stock_actual'], 0)} {unidad} (mínimo {numero(f['stock_minimo'], 0)})")
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _bancos(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    lineas = [f"{_saludo(actor_rol, actor_nombre)}, así están los bancos:"]
    for b in r.datos:
        informado = money(b["saldo_informado"]) if b["saldo_informado"] is not None else "sin cargar"
        lineas.append(f"- {b['nombre']}: contable {money(b['saldo_contable'])} · informado {informado}")
        for p in b.get("prestamos") or []:
            lineas.append(
                f"  Préstamo {p['entidad']}: capital {money(p['saldo'])} · "
                f"cuota {money(p['cuota'])} · {p['plazo']} meses"
            )
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _agenda(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    lineas = [f"{_saludo(actor_rol, actor_nombre)}, agenda:"] if r.datos else [
        f"{_saludo(actor_rol, actor_nombre)}, no hay entregas para esas fechas."
    ]
    for f in r.datos or []:
        lineas.append(
            f"- {f['hora_inicio'].strftime('%H:%M')} · {numero(f['volumen_m3'])} m³ · "
            f"{f['cliente']} · {f['mixer_codigo'] or 'sin mixer'}"
        )
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _orden(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    filas = r.datos or []
    if not filas:
        return f"{_saludo(actor_rol, actor_nombre)}, no encontré esa orden.\n{_traza(r)}"
    lineas = [f"{_saludo(actor_rol, actor_nombre)}, órdenes encontradas:"]
    for o in filas:
        total = o["total_con_iva"] if o["total_con_iva"] is not None else o["total"]
        lineas.append(
            f"- #{o['numero']} · {o['cliente']} · {numero(o['volumen_m3'])} m³ {o['resistencia']} · "
            f"{o['forma_pago']} · {money(total)} · {o['estado']}"
        )
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _precios(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    lineas = [f"{_saludo(actor_rol, actor_nombre)}, precios por m³ (sin IVA):"]
    for p in r.datos or []:
        lineas.append(f"- {p['resistencia']}: {money(p['precio_m3'])}")
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _clientes_encontrados(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    nombres = ", ".join(c["nombre"] for c in r.datos or [])
    return (
        f"{_saludo(actor_rol, actor_nombre)}, encontré varios clientes: {nombres}. "
        "¿Cuál de ellos?"
    )


def _cliente_ficha(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    d = r.datos
    lineas = [f"{_saludo(actor_rol, actor_nombre)}, ficha de {d['nombre']}:"]
    if d.get("ruc"):
        lineas.append(f"- RUC: {d['ruc']}")
    if d.get("telefono_whatsapp"):
        lineas.append(f"- Teléfono: {d['telefono_whatsapp']}")
    if d.get("ciudad") or d.get("provincia"):
        lineas.append(f"- Ubicación: {d.get('ciudad') or ''} {d.get('provincia') or ''}".strip())
    lineas.append(f"- Saldo pendiente: {money(d['saldo_pendiente'])}")
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _movimientos(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    lineas = [f"{_saludo(actor_rol, actor_nombre)}, movimientos:"]
    for m in r.datos:
        lineas.append(
            f"- {m['fecha']} · {m['tipo_movimiento']} · {m['metodo']} · "
            f"{money(m['monto'])} · {m['referencia'] or 'sin referencia'}"
        )
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _stock_proyectado(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    lineas = [f"{_saludo(actor_rol, actor_nombre)}, stock proyectado:"]
    for f in r.datos:
        unidad = {"saco": "sacos", "m3": "m³", "litro": "litros"}.get(
            f.get("unidad") or "", f.get("unidad") or ""
        )
        disponible = f.get("stock_proyectado_disponible")
        valor = f"{numero(disponible, 0)} {unidad}".strip() if disponible is not None else "sin dato"
        lineas.append(f"- {f['nombre']}: {valor} · alerta {f['estado_alerta_proyectada']}")
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _viaje(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    d = r.datos
    lineas = [
        f"{_saludo(actor_rol, actor_nombre)}, viaje {d['viaje_numero']}/{d['total_viajes_orden']} "
        f"de la orden #{d['orden_numero']} ({d['cliente']}):",
        f"- Estado: {d['estado_actual']}",
        f"- Mixer: {d['mixer_codigo'] or 'sin mixer'} · Chofer: {d['chofer_nombre'] or 'sin chofer'}",
        f"- Volumen: {numero(d['volumen_m3'])} m³",
    ]
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _balance(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    visibles = [
        f for f in (r.datos or [])
        if Decimal(str(f["saldo_neto"])) != 0
    ]
    if not visibles:
        return (
            f"{_saludo(actor_rol, actor_nombre)}, todas las cuentas están en cero.\n"
            f"{_traza(r)}"
        )
    lineas = [f"{_saludo(actor_rol, actor_nombre)}, balance por cuenta:"]
    for f in visibles:
        lineas.append(f"- {f['code']} {f['name']}: {money(f['saldo_neto'])}")
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _resultados(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    lineas = [f"{_saludo(actor_rol, actor_nombre)}, resultados:"]
    for f in r.datos:
        lineas.append(f"- {f['periodo']} · {f['code']} {f['name']}: {money(f['saldo'])}")
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _compras(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    lineas = [f"{_saludo(actor_rol, actor_nombre)}, compras pendientes:"]
    for f in r.datos:
        lineas.append(
            f"- {f['proveedor']} · {f['fecha_compra']} · total {money(f['monto_total'])} · "
            f"saldo {money(f['saldo_pendiente'])} · {f['estado_recepcion']}"
        )
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _por_pagar(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    lineas = [f"{_saludo(actor_rol, actor_nombre)}, por pagar:"]
    for f in r.datos:
        lineas.append(f"- {f['proveedor']}: {money(f['saldo_pendiente'])}")
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _disponibilidad(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    filas = (r.datos or {}).get("filas", [])
    libres = (r.datos or {}).get("libres", [])
    lineas = [f"{_saludo(actor_rol, actor_nombre)}, mixers para ese día:"]
    for f in filas:
        lineas.append(
            f"- {f['mixer_codigo'] or 'sin mixer'} · {f['hora_inicio']}–{f['hora_fin_estimada']} · {f['estado']}"
        )
    lineas.append(f"- Libres: {', '.join(libres) if libres else 'ninguno'}")
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _banco_movimientos(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    lineas = [f"{_saludo(actor_rol, actor_nombre)}, movimientos del banco:"]
    for m in r.datos:
        lineas.append(
            f"- {m['fecha']} · {m['tipo_movimiento']} · {m['metodo']} · "
            f"{money(m['monto'])} · {m['referencia'] or 'sin referencia'}"
        )
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _cuota(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    d = r.datos
    lineas = [
        f"{_saludo(actor_rol, actor_nombre)}, mercado {d['provincia']} {r.filtros.get('anio', '')}:",
        f"- Demanda: {numero(d['demanda_m3'])} m³",
        f"- Ventas: {numero(d['ventas_m3'])} m³",
        f"- Cuota: {numero(d['cuota_pct'])}%",
    ]
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _empresa(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    d = r.datos or {}
    lineas = [f"{_saludo(actor_rol, actor_nombre)}, datos de la empresa:"]
    for clave in ("company_name", "ruc", "business_hours", "main_plant_address"):
        if d.get(clave):
            lineas.append(f"- {clave}: {d[clave]}")
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _salud(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    d = r.datos
    lineas = [f"{_saludo(actor_rol, actor_nombre)}, salud del sistema:"]
    for e in d.get("errores", []):
        lineas.append(f"- Errores {e['nivel']}: {e['total']}")
    lineas.append(f"- Outbox encolado: {d.get('outbox_encolado', 0)}")
    lineas.append(_traza(r))
    return "\n".join(lineas)


def _recordatorio(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    if r.estado in ("ACL", "NO_CONECTADA", "PROPUESTA", "ERROR"):
        return f"{_saludo(actor_rol, actor_nombre)}, {r.nota or 'no puedo con esa acción'}."
    if r.consulta_id == "recordatorio_listar" and r.ok:
        filas = r.datos or []
        lineas = [f"{_saludo(actor_rol, actor_nombre)}, recordatorios pendientes:"]
        for f in filas:
            lineas.append(f"- {f['programado_local']} · {f['destinatario']}: {f['mensaje']}")
        lineas.append(_traza(r))
        return "\n".join(lineas)
    # crear, cancelar y los vacios devuelven la nota tal cual: ya viene redactada.
    return r.nota or "Listo."


def _parte(r: Resultado, actor_rol: str, actor_nombre: str) -> str:
    if r.consulta_id in (
        "recordatorio_crear",
        "recordatorio_confirmar",
        "recordatorio_descartar",
        "recordatorio_listar",
        "recordatorio_cancelar",
    ):
        return _recordatorio(r, actor_rol, actor_nombre)
    if r.estado in ("ACL", "NO_CONECTADA", "PROPUESTA", "ERROR"):
        return ""
    if r.estado == "VACIO":
        return f"{_saludo(actor_rol, actor_nombre)}, no hay datos: {r.nota}"
    if r.consulta_id == "cartera_total":
        return _cartera_total(r, actor_rol, actor_nombre)
    if r.consulta_id == "cartera_cliente":
        return _cartera_cliente(r, actor_rol, actor_nombre)
    if r.consulta_id == "cliente_facturas":
        return _facturas(r, actor_rol, actor_nombre)
    if r.consulta_id == "cierre_dia":
        return _cierre(r, actor_rol, actor_nombre)
    if r.consulta_id == "stock_actual":
        return _stock(r, actor_rol, actor_nombre)
    if r.consulta_id == "banco_detalle":
        return _bancos(r, actor_rol, actor_nombre)
    if r.consulta_id == "agenda_obras":
        return _agenda(r, actor_rol, actor_nombre)
    if r.consulta_id == "orden_timeline":
        return _orden(r, actor_rol, actor_nombre)
    if r.consulta_id == "recetas_precio_publico":
        return _precios(r, actor_rol, actor_nombre)
    if r.consulta_id == "cliente_ficha":
        return _cliente_ficha(r, actor_rol, actor_nombre)
    if r.consulta_id == "movimientos_dia":
        return _movimientos(r, actor_rol, actor_nombre)
    if r.consulta_id == "stock_proyectado":
        return _stock_proyectado(r, actor_rol, actor_nombre)
    if r.consulta_id == "viaje_estado":
        return _viaje(r, actor_rol, actor_nombre)
    if r.consulta_id == "balance":
        return _balance(r, actor_rol, actor_nombre)
    if r.consulta_id == "resultados":
        return _resultados(r, actor_rol, actor_nombre)
    if r.consulta_id == "compras_pendientes":
        return _compras(r, actor_rol, actor_nombre)
    if r.consulta_id == "por_pagar":
        return _por_pagar(r, actor_rol, actor_nombre)
    if r.consulta_id == "disponibilidad_agenda":
        return _disponibilidad(r, actor_rol, actor_nombre)
    if r.consulta_id == "banco_movimientos":
        return _banco_movimientos(r, actor_rol, actor_nombre)
    if r.consulta_id == "cuota_mercado":
        return _cuota(r, actor_rol, actor_nombre)
    if r.consulta_id == "empresa_info":
        return _empresa(r, actor_rol, actor_nombre)
    if r.consulta_id == "salud_sistema":
        return _salud(r, actor_rol, actor_nombre)
    if r.consulta_id == "cliente_buscar" and len(r.datos or []) > 1:
        return _clientes_encontrados(r, actor_rol, actor_nombre)
    return ""


def redactar(resultados: list[Resultado], actor_rol: str, actor_nombre: str) -> str:
    partes = [_parte(r, actor_rol, actor_nombre) for r in resultados]
    return "\n\n".join(p for p in partes if p)
