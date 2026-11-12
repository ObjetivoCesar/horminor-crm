"""Tests puros del Gato (sin base de datos)."""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.asistente.bibliotecario import _norm_busqueda  # noqa: E402
from app.asistente.fichas import Resultado, ficha  # noqa: E402
from app.asistente.guardas import CifraNoVerificada, verificar  # noqa: E402
from app.asistente.orquestador import Actor, Respuesta, _con_descargas, planear  # noqa: E402
from app.asistente.persona import NOMBRE, PROMPT_GATO, render_prompt  # noqa: E402
from app.asistente.pilares import permite  # noqa: E402
from app.asistente.redactor import money, numero, redactar  # noqa: E402
from app.asistente.texto import fecha_de  # noqa: E402


def test_prompt_del_gato_tiene_reglas_clave() -> None:
    assert NOMBRE == "Gato"
    assert "español de Ecuador" in PROMPT_GATO
    assert "Cero invención" in PROMPT_GATO
    assert "fichas" in PROMPT_GATO
    assert "miau" in PROMPT_GATO
    assert "HISTORIAL" in PROMPT_GATO
    assert "Descargar:" in PROMPT_GATO


def test_prompt_se_renderiza_con_actor() -> None:
    texto = render_prompt("Julio", "SUPERADMIN", datetime(2026, 11, 12, 9, 0))
    assert "Julio" in texto
    assert "SUPERADMIN" in texto
    assert "{{actor_nombre}}" not in texto


def test_plan_cartera_total() -> None:
    plan = planear("¿Quién me debe?")
    assert plan.pasos == [("cartera-cobros", "cartera_total", {})]


def test_plan_cliente() -> None:
    plan = planear("¿Cuánto debe Los Andes?")
    assert plan.pasos == [("cartera-cobros", "cliente_saldo", {"texto": "los andes"})]


def test_plan_cierre_ayer() -> None:
    plan = planear("¿Cómo cerró la caja ayer?")
    pilar, accion, params = plan.pasos[0]
    assert (pilar, accion) == ("caja-cierre", "cierre_dia")
    assert params["desde"] == date.today() - timedelta(days=1)


def test_plan_banco_pichincha() -> None:
    plan = planear("¿Cuánto hay en el Pichincha?")
    assert plan.pasos == [("banca-mercado", "banco_detalle", {"banco": "pichincha"})]


def test_plan_banco_sin_nombre_pide_aclaracion() -> None:
    plan = planear("¿Cuánto debo del préstamo?")
    assert plan.faltante is not None
    assert "banco" in plan.faltante.lower()


def test_plan_agenda_manana() -> None:
    plan = planear("¿Qué entregas hay mañana?")
    pilar, accion, params = plan.pasos[0]
    assert (pilar, accion) == ("agenda-obras-visitas", "agenda_obras")
    assert params["desde"] == date.today() + timedelta(days=1)


def test_plan_orden_por_numero() -> None:
    plan = planear("¿Cómo va la orden #58?")
    assert plan.pasos == [("cartera-cobros", "orden_estado", {"numero": 58})]


def test_plan_orden_por_cliente() -> None:
    plan = planear("¿Cómo va la orden de Los Andes?")
    assert plan.pasos == [("cartera-cobros", "orden_cliente", {"texto": "los andes"})]


def test_plan_balance() -> None:
    plan = planear("Dame el balance")
    assert plan.pasos == [("contabilidad-reportes", "balance", {})]


def test_plan_compras() -> None:
    plan = planear("¿Qué compras están pendientes?")
    assert plan.pasos == [("compras-proveedores", "compras_pendientes", {})]


def test_plan_por_pagar() -> None:
    plan = planear("¿Cuánto debo a proveedores?")
    assert plan.pasos == [("compras-proveedores", "por_pagar", {})]


def test_plan_disponibilidad() -> None:
    plan = planear("¿Hay mixers libres mañana?")
    pilar, accion, params = plan.pasos[0]
    assert (pilar, accion) == ("agenda-obras-visitas", "disponibilidad")
    assert params["fecha"] == date.today() + timedelta(days=1)


def test_plan_salud() -> None:
    plan = planear("¿Cómo está el sistema?")
    assert plan.pasos == [("salud-sistema", "salud", {})]


def test_plan_empresa() -> None:
    plan = planear("¿Cuál es el RUC de la empresa?")
    assert plan.pasos == [("configuracion-precios", "empresa_info", {})]


def test_plan_stock_y_cliente_multi_paso() -> None:
    plan = planear("¿Cuánto debe Los Andes y hay cemento?")
    acciones = {(p, a) for p, a, _ in plan.pasos}
    assert ("cartera-cobros", "cliente_saldo") in acciones
    assert ("planta-inventario", "stock_actual") in acciones


def test_plan_precios() -> None:
    plan = planear("¿Cuánto está el FC-210?")
    assert plan.pasos == [("configuracion-precios", "precios", {})]


def test_plan_propuesta_costo() -> None:
    plan = planear("¿Cuánto cuesta el costo del FC-210?")
    assert plan.propuesta == "configuracion-precios/costo"


def test_plan_saludo() -> None:
    assert planear("Hola Gato").saludo is True


def test_plan_sin_intencion() -> None:
    plan = planear("contame un chiste")
    assert plan.pasos == [] and plan.faltante is None and not plan.saludo


def test_permisos_por_rol() -> None:
    assert permite("cartera-cobros", "cartera_total", "SUPERADMIN")
    assert not permite("cartera-cobros", "cartera_total", "SECRETARIA")
    assert permite("cartera-cobros", "cliente_saldo", "SECRETARIA")
    assert not permite("planta-inventario", "stock_actual", "SECRETARIA")
    assert permite("planta-inventario", "stock_actual", "BODEGA")
    assert not permite("banca-mercado", "banco_detalle", "SECRETARIA")
    assert permite("banca-mercado", "banco_detalle", "CONTADORA")


def test_actor() -> None:
    actor = Actor(nombre="Julio", rol="SUPERADMIN")
    assert actor.rol == "SUPERADMIN"


def test_formato_de_dinero() -> None:
    assert money(1234.5) == "$1.234,50"
    assert money(-20) == "-$20,00"
    assert money(None) == "sin dato"


def test_formato_de_numero() -> None:
    assert numero(8216, 2) == "8.216,00"
    assert numero(120, 0) == "120"


def test_fecha_de() -> None:
    assert fecha_de("ayer") == date.today() - timedelta(days=1)
    assert fecha_de("mañana") == date.today() + timedelta(days=1)
    assert fecha_de("hoy") == date.today()


def test_guarda_acepta_cifra_con_ficha() -> None:
    f = ficha("cartera_cliente", "saldo_pendiente", "2360.00", unidad="USD",
               fuente=["v_cliente_saldo"], filtros={"cliente": "Los Andes"})
    verificar("Jefe, el saldo es $2.360,00.", [f])


def test_guarda_acepta_formato_estadounidense() -> None:
    f = ficha("cartera_total", "total_por_cobrar", "63619.60", unidad="USD",
               fuente=["v_cliente_saldo"])
    verificar("Jefe, el total es $63,619.60.", [f])
    verificar("Jefe, el total es $63.619,60.", [f])


def test_guarda_acepta_negativos_y_codigos_fc() -> None:
    f = ficha("cierre_dia", "diferencia", "-20.00", unidad="USD",
               fuente=["cash_closures"])
    verificar("Diferencia -$20.00. Precios FC-210 y FC-280.", [f])


def test_guarda_bloquea_cantidad_inventada() -> None:
    f = ficha("stock_actual", "stock_actual", "120.000", unidad="saco",
               fuente=["v_inventario"])
    try:
        verificar("Hay 999 sacos en bodega.", [f])
    except CifraNoVerificada as exc:
        assert "999" in str(exc)
    else:
        raise AssertionError("La guarda debió rechazar 999 sacos")


def test_guarda_exige_ficha_para_conteo_de_clientes() -> None:
    f = ficha("cartera_total", "total_por_cobrar", "63619.60", unidad="USD",
               fuente=["v_cliente_saldo"])
    try:
        verificar("Hay 4 clientes con saldo.", [f])
    except CifraNoVerificada as exc:
        assert "4 clientes" in str(exc)
    else:
        raise AssertionError("La guarda debió rechazar el conteo sin ficha")


def test_guarda_rechaza_cifra_sin_ficha() -> None:
    f = ficha("cartera_cliente", "saldo_pendiente", "2360.00", unidad="USD",
               fuente=["v_cliente_saldo"], filtros={"cliente": "Los Andes"})
    try:
        verificar("Jefe, el saldo es $9.999,00.", [f])
    except CifraNoVerificada as exc:
        assert "$9.999,00" in str(exc)
    else:
        raise AssertionError("La guarda debió rechazar la cifra inventada")


def test_plan_facturas_cliente() -> None:
    plan = planear("¿Qué facturas tiene Ing. Reyes?")
    assert plan.pasos == [
        ("cartera-cobros", "facturas_cliente", {"texto": "ing. reyes"})
    ]


def test_plan_factura_con_del() -> None:
    plan = planear("Pásame la factura del ing reyes")
    assert plan.pasos == [
        ("cartera-cobros", "facturas_cliente", {"texto": "ing reyes"})
    ]


def test_normaliza_puntuacion_de_cliente() -> None:
    assert _norm_busqueda("Ing. Reyes") == "ing reyes"
    assert _norm_busqueda("  ING.   REYES ") == "ing reyes"
    assert _norm_busqueda("José  Pérez") == "jose perez"


def test_agrega_enlace_de_descarga() -> None:
    url = "/api/v1/media/11111111-1111-1111-1111-111111111111/archivo"
    r = Respuesta(
        "Factura PRUEBA-0001.",
        "OK",
        [
            Resultado(
                "cliente_facturas",
                "OK",
                datos=[{"numero": "PRUEBA-0001", "url": url}],
            )
        ],
    )
    texto = _con_descargas(r).texto
    assert "Descargar:" in texto
    assert url + "?download=1" in texto


def test_plan_facturas_sri_es_propuesta() -> None:
    plan = planear("¿Tenemos facturas electrónicas del SRI?")
    assert plan.propuesta == "facturacion-sri"
    assert plan.pasos == []


def test_permisos_facturas_por_rol() -> None:
    assert permite("cartera-cobros", "facturas_cliente", "SUPERADMIN")
    assert permite("cartera-cobros", "facturas_cliente", "SECRETARIA")
    assert not permite("cartera-cobros", "facturas_cliente", "BODEGA")


def test_redactor_pregunta_cual_cliente_si_hay_varios() -> None:
    r = Resultado(
        "cliente_buscar",
        "OK",
        datos=[{"nombre": "Ing. Reyes A"}, {"nombre": "Ing. Reyes B"}],
        fuente=["clients"],
    )
    texto = redactar([r], "SUPERADMIN", "Julio")
    assert "Ing. Reyes A" in texto
    assert "Ing. Reyes B" in texto
    assert "Cuál" in texto


def test_redactor_marca_factura_ficticia() -> None:
    r = Resultado(
        "cliente_facturas",
        "OK",
        datos=[
            {
                "numero": "PRUEBA-0001",
                "fecha": date(2026, 11, 12),
                "total": "43424.00",
                "estado": "EMITIDA",
                "es_ficticia": True,
                "orden_numero": 55,
                "media_id": "11111111-1111-1111-1111-111111111111",
                "url": "/api/v1/media/11111111-1111-1111-1111-111111111111/archivo",
            }
        ],
        fuente=["client_invoices"],
        filtros={"cliente": "Ing. Reyes"},
    )
    texto = redactar([r], "SUPERADMIN", "Julio")
    assert "PRUEBA-0001" in texto
    assert "FICTICIA" in texto
    assert "/api/v1/media/" in texto
    assert "SRI" in texto
