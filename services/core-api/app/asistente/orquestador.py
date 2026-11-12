"""Orquestador de Gato: pilares → acciones → herramientas → redacción."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from . import catalogo, pilares, proveedores
from .bibliotecario import Bibliotecario
from .fichas import Resultado
from .guardas import CifraNoVerificada, verificar
from .herramientas import ejecutar as ejecutar_herramienta
from .redactor import redactar
from .texto import extraer_cliente, fecha_de, normalizar


@dataclass
class Actor:
    nombre: str
    rol: str
    actor_id: str = "panel"
    ahora: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Plan:
    pasos: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    faltante: str | None = None
    saludo: bool = False
    propuesta: str | None = None


@dataclass
class Respuesta:
    texto: str
    estado: str
    resultados: list[Resultado] = field(default_factory=list)


def _quiere(t: str, palabras: tuple[str, ...]) -> bool:
    return any(p in t for p in palabras)


def planear(pregunta: str) -> Plan:
    t = normalizar(pregunta)
    plan = Plan()

    es_saludo = _quiere(t, ("hola", "buenas", "que tal")) or t.strip() == "gato"
    if es_saludo and not _quiere(
        t,
        ("debe", "cartera", "cierre", "caja", "stock", "bodega", "banco",
         "pichincha", "guayaquil", "internacional", "prestamo", "entrega",
         "agenda", "orden", "precio", "fc-", "cupo", "cliente", "material",
         "factura"),
    ):
        plan.saludo = True
        return plan

    if _quiere(t, ("costo", "margen", "rentabilidad")):
        plan.propuesta = "configuracion-precios/costo"
        return plan

    if _quiere(t, ("factura", "comprobante")):
        if _quiere(t, ("sri", "electronica", "electronico")):
            plan.propuesta = "facturacion-sri"
            return plan
        cliente = extraer_cliente(pregunta)
        if cliente is None:
            match = re.search(
                r"facturas?\s+(?:de|del|tiene|tienen)\s+(.+)$", t
            )
            cliente = match.group(1).strip(" ?¿.!") if match else None
        if cliente:
            plan.pasos.append(
                ("cartera-cobros", "facturas_cliente", {"texto": cliente})
            )
        else:
            plan.faltante = "¿De qué cliente quieres las facturas?"
        return plan

    if "orden" in t:
        numero = re.search(r"#?\s*(\d{1,6})", t)
        if numero:
            plan.pasos.append(
                ("cartera-cobros", "orden_estado", {"numero": int(numero.group(1))})
            )
        else:
            match = re.search(r"orden\s+(?:de\s+|del\s+)?(.+)$", t)
            cliente = match.group(1).strip(" ?¿.!") if match else extraer_cliente(pregunta)
            if cliente:
                plan.pasos.append(
                    ("cartera-cobros", "orden_cliente", {"texto": cliente})
                )
            else:
                plan.faltante = "¿Qué número de orden o cliente necesitas?"
        return plan

    if _quiere(t, ("quien me debe", "cuanto me deben", "cartera total")):
        plan.pasos.append(("cartera-cobros", "cartera_total", {}))
    elif _quiere(t, ("por cobrar", "cartera")) and not extraer_cliente(pregunta):
        plan.pasos.append(("cartera-cobros", "cartera_total", {}))
    else:
        cliente = extraer_cliente(pregunta)
        if _quiere(t, ("debe", "saldo", "cupo", "cliente", "como va", "ficha")) and not _quiere(
            t, ("proveedor", "prestamo", "banco", "pichincha", "guayaquil", "internacional")
        ):
            if cliente:
                plan.pasos.append(("cartera-cobros", "cliente_saldo", {"texto": cliente}))
            else:
                plan.faltante = "¿Qué cliente necesitas (nombre o RUC)?"

    if _quiere(t, ("cierre", "caja", "efectivo", "cuadre")):
        fecha = fecha_de(pregunta)
        if fecha is None:
            plan.faltante = "¿De qué fecha quieres el cierre?"
        else:
            plan.pasos.append(
                ("caja-cierre", "cierre_dia", {"desde": fecha, "hasta": fecha})
            )

    if _quiere(t, ("banco", "pichincha", "guayaquil", "internacional", "prestamo")):
        banco = next((c for c in ("pichincha", "guayaquil", "internacional") if c in t), None)
        if banco is None:
            plan.faltante = "¿Qué banco: Pichincha, Guayaquil o Internacional?"
        elif "movimiento" in t:
            plan.pasos.append(("banca-mercado", "banco_movimientos", {"banco": banco}))
        else:
            plan.pasos.append(("banca-mercado", "banco_detalle", {"banco": banco}))

    if "proyectado" in t and _quiere(t, ("stock", "bodega", "inventario", "material")):
        plan.pasos.append(("planta-inventario", "stock_proyectado", {}))
    elif _quiere(t, ("stock", "bodega", "inventario", "cemento", "arena", "ripio", "material")):
        plan.pasos.append(("planta-inventario", "stock_actual", {}))

    if _quiere(t, ("agenda", "entrega", "despacho", "agendado", "mixer", "libre", "disponibilidad")):
        fecha = fecha_de(pregunta)
        if fecha is None:
            plan.faltante = "¿Para qué fecha quieres la agenda?"
        elif _quiere(t, ("disponibilidad", "libre", "ocupad")):
            plan.pasos.append(("agenda-obras-visitas", "disponibilidad", {"fecha": fecha}))
        else:
            plan.pasos.append(
                ("agenda-obras-visitas", "agenda_obras", {"desde": fecha, "hasta": fecha})
            )

    if "viaje" in t:
        viaje = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", t)
        if viaje:
            plan.pasos.append(
                ("agenda-obras-visitas", "viaje_estado", {"dispatch_id": viaje.group(0)})
            )
        else:
            plan.faltante = "¿Qué viaje? Necesito el código del despacho."

    if _quiere(t, ("precio", "tarifa", "fc-", "precios")):
        plan.pasos.append(("configuracion-precios", "precios", {}))

    if "balance" in t:
        plan.pasos.append(("contabilidad-reportes", "balance", {}))

    if _quiere(t, ("resultado", "ganancia", "perdida")):
        desde = fecha_de(pregunta)
        if desde is None:
            plan.faltante = "¿De qué mes o rango quieres los resultados?"
        else:
            plan.pasos.append(
                ("contabilidad-reportes", "resultados", {"desde": desde, "hasta": desde})
            )

    if _quiere(t, ("por pagar", "debo a proveedor", "deuda proveedor")):
        plan.pasos.append(("compras-proveedores", "por_pagar", {}))
    elif _quiere(t, ("compra", "compras")):
        plan.pasos.append(("compras-proveedores", "compras_pendientes", {}))

    if _quiere(t, ("salud", "errores", "sistema")):
        plan.pasos.append(("salud-sistema", "salud", {}))

    if re.search(r"\b(empresa|ruc|horario|cobertura)\b", t):
        plan.pasos.append(("configuracion-precios", "empresa_info", {}))

    if _quiere(t, ("cuota", "mercado")):
        provincia = (
            "ORELLANA" if "orellana" in t else "SUCUMBIOS" if "sucumbios" in t else None
        )
        if provincia is None:
            plan.faltante = "¿De qué provincia: Orellana o Sucumbíos?"
        else:
            plan.pasos.append(
                ("banca-mercado", "cuota_mercado", {"provincia": provincia, "anio": date.today().year})
            )

    if "movimiento" in t and "caja" in t and not _quiere(
        t, ("banco", "pichincha", "guayaquil", "internacional")
    ):
        desde = fecha_de(pregunta)
        if desde is None:
            plan.faltante = "¿De qué fecha quieres los movimientos?"
        else:
            plan.pasos.append(("caja-cierre", "movimientos", {"desde": desde, "hasta": desde}))

    return plan


async def _ejecutar_accion(
    pilar: str, nombre: str, params: dict[str, Any], biblio: Bibliotecario
) -> list[Resultado]:
    accion = pilares.accion(pilar, nombre)
    pasos = accion.get("pasos") or (accion["consulta"],)
    resultados: list[Resultado] = []

    if pasos == ("cliente_buscar", "cartera_cliente"):
        r = await ejecutar_herramienta("cliente_buscar", params, biblio)
        resultados.append(r)
        if r.ok and len(r.datos or []) == 1:
            r2 = await ejecutar_herramienta(
                "cartera_cliente", {"cliente_id": str(r.datos[0]["id"])}, biblio
            )
            resultados.append(r2)
        return resultados

    if pasos == ("cliente_buscar", "cliente_facturas"):
        r = await ejecutar_herramienta("cliente_buscar", params, biblio)
        resultados.append(r)
        if r.ok and len(r.datos or []) == 1:
            r2 = await ejecutar_herramienta(
                "cliente_facturas", {"cliente_id": str(r.datos[0]["id"])}, biblio
            )
            r2.filtros["cliente"] = r.datos[0]["nombre"]
            resultados.append(r2)
        return resultados

    if pasos == ("cliente_ordenes",):
        return [await ejecutar_herramienta("cliente_ordenes", params, biblio)]

    for consulta in pasos:
        info = catalogo.CONSULTAS.get(consulta, {})
        if not info.get("handler"):
            resultados.append(
                Resultado(
                    consulta_id=consulta,
                    estado="NO_CONECTADA",
                    nota=f"La consulta {consulta} aún no está conectada.",
                )
            )
            continue
        resultados.append(await ejecutar_herramienta(info["handler"], params, biblio))
    return resultados


def _con_descargas(r: Respuesta) -> Respuesta:
    """Garantiza un enlace de descarga cuando la respuesta trae facturas."""
    enlaces: list[tuple[str, str]] = []
    vistos: set[str] = set()
    for resultado in r.resultados:
        if resultado.consulta_id != "cliente_facturas":
            continue
        for factura in resultado.datos or []:
            url = factura.get("url")
            if not url:
                continue
            base = str(url).split("?")[0]
            descarga = base + "?download=1"
            if base in r.texto or descarga in r.texto or descarga in vistos:
                continue
            vistos.add(descarga)
            enlaces.append((str(factura.get("numero") or "archivo"), descarga))
    if enlaces:
        bloque = "\n\nDescargar:\n" + "\n".join(f"- {n}: {u}" for n, u in enlaces)
        r.texto = (r.texto or "").rstrip() + bloque
    return r


async def responder(
    pregunta: str,
    actor: Actor,
    biblio: Bibliotecario,
    historial: list[dict[str, str]] | None = None,
) -> Respuesta:
    if proveedores.disponible():
        try:
            r = await proveedores.responder_llm(
                pregunta, actor, biblio, historial=historial
            )
            if r is not None:
                return _con_descargas(r)
        except Exception:  # noqa: BLE001
            pass

    plan = planear(pregunta)

    if plan.faltante:
        return Respuesta(plan.faltante, "FALTA_PARAMETRO")

    if plan.propuesta == "facturacion-sri":
        return Respuesta(
            "La facturación electrónica del SRI está fuera del alcance del "
            "contrato, jefe: no hay comprobantes electrónicos, claves de acceso "
            "ni autorización. Lo que sí puedo mostrarte son las facturas "
            "internas (PDF o foto) adjuntas a un cliente. Dime el cliente.",
            "PROPUESTA",
        )

    if plan.propuesta:
        return Respuesta(
            "Esa consulta (costo/margen por receta) está en estado PROPUESTA: "
            "todavía no está habilitada en producción.",
            "PROPUESTA",
        )

    if plan.saludo:
        opciones = {
            "SUPERADMIN": "cartera, cierre, bodega, bancos, agenda, órdenes, facturas o precios",
            "CONTADORA": "cartera, cierre, bancos, bodega, agenda, órdenes, facturas o precios",
            "SECRETARIA": "cartera por cliente, cierre, agenda, órdenes, facturas o precios",
            "BODEGA": "bodega, agenda u órdenes",
        }.get(actor.rol, "las consultas de tu perfil")
        saludo = "Jefe" if actor.rol == "SUPERADMIN" else actor.nombre or "Señor(a)"
        return Respuesta(
            f"Miau. Soy Gato, el gato del CRM. {saludo}, dime qué necesitas: {opciones}.",
            "OK",
        )

    if not plan.pasos:
        return Respuesta(
            "No entendí. Prueba con: ¿quién me debe?, ¿cómo cerró la caja ayer?, "
            "¿qué entregas hay mañana?, ¿cómo va la orden #58?",
            "SIN_INTENCION",
        )

    resultados: list[Resultado] = []
    for pilar, nombre, params in plan.pasos:
        accion = pilares.accion(pilar, nombre)
        if not accion:
            resultados.append(
                Resultado(consulta_id=nombre, estado="NO_CONECTADA",
                          nota=f"La acción {nombre} no existe.")
            )
            continue
        if not pilares.permite(pilar, nombre, actor.rol):
            resultados.append(
                Resultado(
                    consulta_id=accion["consulta"],
                    estado="ACL",
                    nota=f"El pilar {pilar} no está habilitado para tu rol.",
                )
            )
            continue
        resultados.extend(await _ejecutar_accion(pilar, nombre, params, biblio))

    rechazos = [r for r in resultados if r.estado == "ACL"]
    no_conectadas = [r for r in resultados if r.estado == "NO_CONECTADA"]

    texto = redactar(resultados, actor.rol, actor.nombre)
    if rechazos:
        texto = "No tengo permiso para esa consulta con tu rol." + (
            "\n\n" + texto if texto else ""
        )
    if no_conectadas and not texto:
        texto = "Esa consulta todavía no está conectada en este prototipo."
    if not texto:
        texto = "No encontré datos para esa consulta."

    fichas = [f for r in resultados for f in r.fichas]
    try:
        verificar(texto, fichas)
    except CifraNoVerificada as exc:
        return Respuesta(
            "No pude verificar una cifra contra la base; no te la voy a mostrar "
            f"sin fuente. Detalle: {exc}.",
            "ERROR",
            resultados,
        )

    estado = "ACL" if rechazos else "OK"
    return _con_descargas(Respuesta(texto, estado, resultados))
