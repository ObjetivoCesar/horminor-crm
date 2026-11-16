"""Tareas internas: instrucciones al equipo con reloj y metadatos (v9.1)."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.cerebro import Contexto, Evidencia, HechoCitado, compilar
from app.cerebro.internas import (
    crear,
    detectar_rol_interno,
    es_instruccion_interna,
    minutos_entre,
    persona_dictada,
    puede_transicionar,
)

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]


def _migracion() -> Path:
    for base in (RAIZ_SERVICIO, *RAIZ_SERVICIO.parents):
        candidato = base / "db" / "migrations" / "088_cerebro_tareas_internas.sql"
        if candidato.is_file():
            return candidato
    raise FileNotFoundError("088_cerebro_tareas_internas.sql no encontrada")


def hecho(clave: str, valor, tipo: str = "TEXTO", *, cita: str | None = None):
    texto = cita if cita is not None else str(valor)
    return HechoCitado(
        clave=clave,
        valor=valor,
        estado="EXTRAIDO",
        tipo=tipo,
        evidencia=Evidencia(
            cita=texto,
            sostiene=texto,
            crudo_inicio=0,
            crudo_fin=len(texto),
            start_ms=0,
            end_ms=900,
            confianza=0.9,
            hablante="SUPERADMIN",
        ),
    )


def _contexto(texto: str) -> Contexto:
    return Contexto(hoy=date(2026, 11, 15), sandbox=True, texto=texto)


# ---------------------------------------------------------------------------
# Lectura del dictado
# ---------------------------------------------------------------------------
def test_detecta_el_area_nombrada() -> None:
    assert (
        detectar_rol_interno("que revisen en secretaría cómo van los despachos")
        == "SECRETARIA"
    )
    assert detectar_rol_interno("que bodega confirme el stock") == "BODEGA"
    assert detectar_rol_interno("que contabilidad pase el saldo") == "CONTADORA"


def test_no_inventa_area_donde_no_la_hay() -> None:
    assert detectar_rol_interno("envíale el comprobante al ingeniero") is None
    assert detectar_rol_interno("llevamos la planta móvil al sitio") is None


def test_reconoce_un_encargo_sin_destinatario() -> None:
    assert es_instruccion_interna("que revisen cómo van los despachos")
    assert es_instruccion_interna("verifica que el depósito ya esté hecho")
    assert not es_instruccion_interna("envíale la cotización a Mauricio")


def test_el_area_no_se_guarda_como_nombre_de_persona() -> None:
    assert persona_dictada("Secretaría", "SECRETARIA") is None
    assert persona_dictada("Mauricio Santander", "SECRETARIA") == "Mauricio Santander"
    assert persona_dictada(None, "SECRETARIA") is None


# ---------------------------------------------------------------------------
# Estados y reloj
# ---------------------------------------------------------------------------
def test_las_transiciones_no_se_saltan_pasos() -> None:
    assert puede_transicionar("NOTIFICADA", "RESUELTA")
    assert puede_transicionar("NOTIFICADA", "JUSTIFICADA")
    assert puede_transicionar("RESUELTA", "REGISTRADA")
    assert puede_transicionar("JUSTIFICADA", "REGISTRADA")
    assert not puede_transicionar("NOTIFICADA", "REGISTRADA")
    assert not puede_transicionar("REGISTRADA", "RESUELTA")


def test_el_reloj_se_mide_en_minutos() -> None:
    inicio = datetime(2026, 11, 15, 9, 0, tzinfo=timezone.utc)

    assert minutos_entre(inicio, inicio + timedelta(minutes=42)) == 42
    assert minutos_entre(inicio, None) is None


def test_una_instruccion_vacia_no_crea_tarea() -> None:
    resultado = asyncio.run(
        crear(
            None,  # no toca la base: valida antes
            instruccion="   ",
            creado_por="Julio",
            rol_actor="SUPERADMIN",
            clave_externa="prueba-vacia",
        )
    )

    assert resultado.estado == "FALTA_PARAMETRO"
    assert resultado.parametro_faltante == "instruccion"


# ---------------------------------------------------------------------------
# Compilador
# ---------------------------------------------------------------------------
def test_una_instruccion_sin_telefono_es_tarea_interna() -> None:
    texto = (
        "Oye, que revisen en secretaría cómo van los despachos de esta semana. "
        "Necesito saber qué está pendiente."
    )
    hechos = [
        hecho(
            "tarea.mensaje",
            "que revisen en secretaría cómo van los despachos de esta semana",
            cita="que revisen en secretaría cómo van los despachos de esta semana",
        )
    ]

    borrador = compilar(hechos, _contexto(texto))

    assert [a.nombre for a in borrador.acciones] == ["crear_tarea_interna"]
    parametros = borrador.acciones[0].parametros
    assert parametros["asignado_rol"] == "SECRETARIA"
    assert parametros["asignado_a"] is None
    assert "despachos" in parametros["instruccion"]
    assert borrador.estado == "PENDIENTE_CONFIRMACION"
    assert not any(p.clave == "tarea.telefono" for p in borrador.preguntas)


def test_una_persona_sin_telefono_queda_como_tarea_interna_asignada() -> None:
    texto = "Que Mauricio revise si el trabajo ya empezó."
    hechos = [
        hecho("tarea.destinatario", "Mauricio", cita="Mauricio"),
        hecho(
            "tarea.mensaje",
            "revise si el trabajo ya empezó",
            cita="revise si el trabajo ya empezó",
        ),
    ]

    borrador = compilar(hechos, _contexto(texto))

    assert [a.nombre for a in borrador.acciones] == ["crear_tarea_interna"]
    assert borrador.acciones[0].parametros["asignado_a"] == "Mauricio"


def test_con_telefono_sigue_siendo_recordatorio_de_whatsapp() -> None:
    texto = "Recuérdale a Mauricio al 0965555555 que pase el comprobante."
    hechos = [
        hecho("tarea.destinatario", "Mauricio"),
        hecho("tarea.telefono", "0965555555", "TELEFONO"),
        hecho("tarea.mensaje", "que pase el comprobante"),
    ]

    borrador = compilar(hechos, _contexto(texto))

    assert [a.nombre for a in borrador.acciones] == ["crear_tarea_recordatorio"]


def test_el_compilador_no_pide_telefono_para_una_tarea_interna() -> None:
    texto = "Que secretaría confirme si el depósito ya está hecho."
    hechos = [hecho("tarea.mensaje", "confirmar si el depósito ya está hecho")]

    borrador = compilar(hechos, _contexto(texto))

    assert borrador.preguntas == ()
    assert borrador.estado == "PENDIENTE_CONFIRMACION"


# ---------------------------------------------------------------------------
# Migración y cableado
# ---------------------------------------------------------------------------
def test_migracion_088_tiene_estados_reloj_y_historial() -> None:
    sql = _migracion().read_text(encoding="utf-8")

    assert "CREATE TABLE cerebro_tareas_internas" in sql
    assert "cerebro_tareas_internas_eventos" in sql
    assert "trg_cerebro_tareas_internas_eventos_immutable" in sql
    assert "CREATE OR REPLACE VIEW v_cerebro_tareas_internas" in sql
    assert "minutos_hasta_resolucion" in sql
    assert "minutos_hasta_registro" in sql
    assert "'NOTIFICADA'" in sql and "'RESUELTA'" in sql
    assert "'JUSTIFICADA'" in sql and "'REGISTRADA'" in sql


def test_el_router_expone_el_ciclo_de_la_tarea_interna() -> None:
    fuente = (
        RAIZ_SERVICIO / "app" / "cerebro" / "router.py"
    ).read_text(encoding="utf-8")

    assert '"crear_tarea_interna"' in fuente
    assert '"/tareas-internas"' in fuente
    assert '"/tareas-internas/{tarea_id}/resolver"' in fuente
    assert '"/tareas-internas/{tarea_id}/registrar"' in fuente
    assert '"internas": internas' in fuente


def test_el_prompt_ensena_a_extraer_la_instruccion_interna() -> None:
    from app.cerebro.extractor import PROMPT, VERSION_PROMPT

    assert "tarea interna" in PROMPT
    assert VERSION_PROMPT == "cerebro-v7"
    # Un audio puede traer varias instrucciones sin ordinales.
    assert "encargo" in PROMPT


def test_el_resumen_habla_de_tarea_interna_y_no_inventa_hora() -> None:
    from app.cerebro.revision import resumen_legible

    hechos = [
        hecho("tarea.mensaje", "revisen los despachos de la semana"),
        hecho("tarea.destinatario", "secretaría"),
        hecho("tarea.cuando", "hoy"),
    ]

    resumen = resumen_legible(
        hechos, texto="Que revisen en secretaría los despachos hoy."
    )

    assert "una tarea interna para secretaría" in resumen
    assert "a las hoy" not in resumen
    assert "(hoy)" in resumen


def test_el_panel_tiene_aviso_persistente_y_no_solo_un_popout() -> None:
    html = (
        RAIZ_SERVICIO / "app" / "web" / "templates" / "panel.html"
    ).read_text(encoding="utf-8")

    # El popout se puede cerrar/minimizar: el aviso pegado arriba no.
    assert 'id="aviso-internas"' in html
    assert "function renderAvisoInternas()" in html
    assert "function abrirTareas()" in html
    assert "renderAvisoInternas();" in html
    assert 'onclick="abrirTareas()"' in html
    # El aviso no depende del "ya lo vi" del navegador.
    aviso = html.split('id="aviso-internas"', 1)[1].split("</div>", 1)[0]
    assert "localStorage" not in aviso


def test_migracion_089_admite_un_borrador_sin_acciones() -> None:
    ruta = None
    for base in (RAIZ_SERVICIO, *RAIZ_SERVICIO.parents):
        candidato = base / "db" / "migrations" / "089_cerebro_sin_acciones.sql"
        if candidato.is_file():
            ruta = candidato
            break
    assert ruta is not None

    sql = ruta.read_text(encoding="utf-8")
    assert "DROP CONSTRAINT IF EXISTS cerebro_borradores_estado_check" in sql
    assert "'SIN_ACCIONES'" in sql

