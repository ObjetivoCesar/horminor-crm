from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.cerebro import extractor, router
from app.cerebro.compilador import ClienteResuelto, Receta
from app.cerebro.hechos import HechoCitado


def _hecho(clave, valor, tipo="TEXTO"):
    return HechoCitado(clave=clave, valor=valor, estado="EXTRAIDO", tipo=tipo)


@pytest.mark.asyncio
async def test_prepara_cotizacion_y_conserva_contacto_despues_del_alta(monkeypatch):
    async def receta(pool, hechos):
        return Receta("FC-210", Decimal("100"), "OFICIAL")

    async def no_buscar_cliente(*args):
        pytest.fail("Una revisión reutiliza el ID confirmado y no vuelve a elegir cliente.")

    monkeypatch.setattr(extractor, "_resolver_receta", receta)
    monkeypatch.setattr(extractor, "_resolver_cliente", no_buscar_cliente)
    cliente = ClienteResuelto("id-confirmado", "Empresa de prueba")
    hechos = [
        _hecho("cliente.nombre", "EMPRESA DE PRUEBA"),
        _hecho("cotizacion.obra_direccion", "Entrada de prueba"),
        _hecho("cotizacion.resistencia", "FC-210"),
        _hecho("cotizacion.volumen_m3", Decimal("150"), "DECIMAL"),
        _hecho("contacto.nombre", "Responsable de prueba"),
        _hecho("contacto.telefono", "0990000000", "TELEFONO"),
    ]
    borrador, _, vinculado = await extractor._borrador_desde_hechos(
        object(), hechos, intencion="MUTACION", sandbox=True,
        hoy=date(2026, 11, 24), cliente_confirmado=cliente,
        texto="Agrega el contacto de esta obra y prepara una cotización.",
    )
    assert vinculado == cliente
    assert [a.nombre for a in borrador.acciones] == ["crear_cotizacion_borrador"]
    assert borrador.acciones[0].parametros["cliente_id"] == cliente.id
    assert borrador.acciones[0].depende_de is None
    assert any(h.clave == "contacto.telefono" for h in borrador.hechos)

    with pytest.raises(extractor.ClienteConfirmadoDistinto):
        await extractor._borrador_desde_hechos(
            object(), [*hechos, _hecho("cliente.nombre", "Empresa distinta")],
            intencion="MUTACION", sandbox=True, hoy=date(2026, 11, 24),
            cliente_confirmado=cliente,
        )


@pytest.mark.asyncio
async def test_revision_acepta_solo_alta_y_protege_acciones_ya_ejecutadas():
    alta = {
        "accion_nombre": "crear_cliente", "entidad_destino_tabla": "clients",
        "cliente_id": "id-confirmado", "cliente_nombre": "Empresa de prueba",
    }

    class DB:
        filas = [alta]

        async def fetch(self, sql, borrador, conversacion):
            assert "WITH RECURSIVE" in sql and "b.conversacion_id = $2::uuid" in sql
            assert (borrador, conversacion) == ("revision", "hilo")
            return self.filas

    db = DB()
    assert await router._cliente_fijado_en_revision(db, "revision", "hilo") == ClienteResuelto(
        "id-confirmado", "Empresa de prueba",
    )
    for accion in ("crear_cotizacion_borrador", "reservar_mixer", "CANCELADO"):
        db.filas = [alta, {**alta, "accion_nombre": accion}]
        with pytest.raises(HTTPException, match="otras acciones") as exc:
            await router._cliente_fijado_en_revision(db, "revision", "hilo")
        assert exc.value.status_code == 409
