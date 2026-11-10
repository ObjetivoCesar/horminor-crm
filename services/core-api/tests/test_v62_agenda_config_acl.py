"""Tests v6.2: componente unico de agenda, configuracion y ACL."""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
from fastapi import FastAPI

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.agenda import evaluar_disponibilidad, validar_ventana  # noqa: E402
from app.agenda.parametros import validar_parametros  # noqa: E402
from app.http_gate.panel import excede_tope_caja  # noqa: E402
from app.http_gate.panel import router as panel_api_router  # noqa: E402
from app.panel_acl import MemoryPanelUserStore, modulos_vacios  # noqa: E402
from app.superadmin.operacion import (  # noqa: E402
    MemoryOperacionStore,
    router as operacion_router,
)
from app.superadmin.usuarios import router as usuarios_router  # noqa: E402
from app.web.panel import router as panel_router  # noqa: E402

FECHA = date(2026, 11, 16)  # lunes


def _app(*routers, **estado) -> FastAPI:
    app = FastAPI()
    for router in routers:
        app.include_router(router)
    for clave, valor in estado.items():
        setattr(app.state, clave, valor)
    return app


# ---------------------------------------------------------------------------
# 1. Componente unico
# ---------------------------------------------------------------------------
def test_agenda_component_unified() -> None:
    html = (
        RAIZ_SERVICIO / "app" / "web" / "templates" / "panel.html"
    ).read_text(encoding="utf-8")
    assert "static/horminor-agenda.js" in html
    assert 'id="agenda-mount-dashboard"' in html
    assert 'id="agenda-mount-secretaria"' in html
    assert 'id="agenda-mount-planta"' in html
    assert "HorminorAgenda.mount(" in html
    # El calendario decorativo del Dashboard ya no existe ni lee orders.created_at
    assert "eventosCalendario" not in html
    assert "calendario-grid" not in html
    assert "renderCalendario" not in html


def test_componente_sirve_el_js_estatico() -> None:
    from app.main import app as aplicacion

    assert any(
        getattr(route, "path", "") == "/static" for route in aplicacion.routes
    )


# ---------------------------------------------------------------------------
# 2. Superadmin: caja chica y horarios en caliente
# ---------------------------------------------------------------------------
def test_superadmin_caja_chica_and_horarios() -> None:
    store = MemoryOperacionStore()
    app = _app(operacion_router, operacion_store=store)

    async def flujo() -> None:
        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://test") as c:
            inicial = await c.get("/api/v1/superadmin/operacion/config")
            assert inicial.status_code == 200
            assert inicial.json()["caja_chica"]["caja_chica_max_monto_usd"] == "100.00"
            assert inicial.json()["agenda"]["hora_apertura"] == "07:00"

            cambio = await c.put(
                "/api/v1/superadmin/operacion/config",
                json={
                    "caja_chica": {
                        "caja_chica_max_monto_usd": "150.00",
                        "compras_efectivo_max_monto_usd": "450.00",
                        "fondo_base_caja_chica_usd": "250.00",
                    },
                    "agenda": {
                        "hora_apertura": "06:30",
                        "hora_cierre": "19:00",
                        "duracion_entrega_default_min": 120,
                        "intervalo_slot_min": 15,
                        "dias_laborables": ["LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM"],
                    },
                },
            )
            assert cambio.status_code == 200
            datos = cambio.json()
            assert datos["caja_chica"]["caja_chica_max_monto_usd"] == "150.00"
            assert datos["agenda"]["hora_cierre"] == "19:00"
            assert datos["agenda"]["duracion_entrega_default_min"] == 120

            invalido = await c.put(
                "/api/v1/superadmin/operacion/config",
                json={"agenda": {"hora_apertura": "20:00", "hora_cierre": "06:00"}},
            )
            assert invalido.status_code == 422

    import asyncio

    asyncio.run(flujo())

    # El mismo helper que usa el Gate con el nuevo tope.
    assert excede_tope_caja("150.00", Decimal("160.00")) == Decimal("150.00")
    assert excede_tope_caja("150.00", Decimal("150.00")) is None

    # La disponibilidad respeta el nuevo horario y la duracion.
    params = store.agenda
    resultado = evaluar_disponibilidad(
        filas=[],
        mixers=[{"codigo": "MIXER-01", "capacidad_m3": 8}],
        fecha=FECHA,
        hora="06:30",
        duracion_min=120,
        parametros=params,
    )
    assert resultado["hay_disponible"] is True
    assert resultado["hora_apertura"] == "06:30"

    tarde = evaluar_disponibilidad(
        filas=[],
        mixers=[{"codigo": "MIXER-01"}],
        fecha=FECHA,
        hora="18:30",
        duracion_min=60,
        parametros=params,
    )
    assert tarde["motivo"] == "FUERA_DE_HORARIO"

    error = validar_ventana(
        parametros=params, fecha=FECHA, hora="19:00", duracion_min=60
    )
    assert error and error["code"] == "OUTSIDE_PLANT_HOURS"


def test_horarios_invalidos_se_rechazan() -> None:
    for datos in (
        {"hora_apertura": "18:00", "hora_cierre": "07:00"},
        {"duracion_entrega_default_min": 5},
        {"intervalo_slot_min": 1},
        {"dias_laborables": []},
        {"dias_laborables": ["FERIADO"]},
    ):
        try:
            validar_parametros(datos)
        except ValueError:
            continue
        raise AssertionError(f"debio rechazar {datos}")


# ---------------------------------------------------------------------------
# 3. Usuarios ACL: checklist vacio, auditor solo lectura, vendedor
# ---------------------------------------------------------------------------
def _usuario(nombre: str, rol: str, modulos: dict[str, bool], modo: str = "EDICION") -> dict:
    return {
        "nombre": nombre,
        "rol_base": rol,
        "telefono_whatsapp": None,
        "activo": True,
        "modo_acceso": modo,
        "modulos_permitidos": {**modulos_vacios(), **modulos},
    }


def test_user_acl_checklist_and_readonly_auditor() -> None:
    store = MemoryPanelUserStore()
    app = _app(
        usuarios_router,
        panel_api_router,
        panel_user_store=store,
    )

    async def flujo() -> None:
        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://test") as c:
            vacio = await c.post(
                "/api/v1/superadmin/usuarios",
                json=_usuario("Checklist Vacio", "AUDITOR_EXTERNO", modulos_vacios()),
            )
            assert vacio.status_code == 422
            assert vacio.json()["detail"]["code"] == "EMPTY_MODULE_CHECKLIST"

            auditor = await c.post(
                "/api/v1/superadmin/usuarios",
                json=_usuario(
                    "Auditor Externo",
                    "AUDITOR_EXTERNO",
                    {
                        "dashboard_gerencial": True,
                        "finanzas_balance_auditoria": True,
                        "clientes_cartera": True,
                        "secretaria_cierre_caja": True,
                    },
                    "SOLO_LECTURA",
                ),
            )
            assert auditor.status_code == 201
            auditor_id = auditor.json()["usuario"]["id"]

            perfil = await c.get(
                "/api/v1/panel/profile", headers={"X-Panel-User": auditor_id}
            )
            assert perfil.status_code == 200
            cuerpo = perfil.json()["perfil"]
            assert cuerpo["modo_acceso"] == "SOLO_LECTURA"
            assert set(cuerpo["modulos_activos"]) == {
                "dashboard_gerencial",
                "finanzas_balance_auditoria",
                "clientes_cartera",
                "secretaria_cierre_caja",
            }

            bloqueado = await c.post(
                "/api/v1/panel/pagos",
                headers={"X-Panel-User": auditor_id},
                json={
                    "tipo_movimiento": "COBRO",
                    "cliente_id": "11111111-1111-1111-1111-111111111111",
                    "metodo": "EFECTIVO",
                    "monto": 1,
                },
            )
            assert bloqueado.status_code == 403
            assert bloqueado.json()["detail"]["code"] == "READ_ONLY_PROFILE"

            vendedor = await c.post(
                "/api/v1/superadmin/usuarios",
                json=_usuario(
                    "Vendedor de Campo",
                    "VENDEDOR",
                    {
                        "agenda_despachos": True,
                        "clientes_cartera": True,
                        "secretaria_ventanilla": True,
                    },
                ),
            )
            assert vendedor.status_code == 201
            vendedor_id = vendedor.json()["usuario"]["id"]
            perfil_v = await c.get(
                "/api/v1/panel/profile", headers={"X-Panel-User": vendedor_id}
            )
            assert perfil_v.status_code == 200
            assert set(perfil_v.json()["perfil"]["modulos_activos"]) == {
                "agenda_despachos",
                "clientes_cartera",
                "secretaria_ventanilla",
            }

            # Un modulo no permitido se bloquea antes de tocar la base.
            catalogo = await c.get(
                "/api/v1/panel/catalog", headers={"X-Panel-User": vendedor_id}
            )
            assert catalogo.status_code == 403
            assert catalogo.json()["detail"]["code"] == "MODULE_NOT_ALLOWED"

    import asyncio

    asyncio.run(flujo())
