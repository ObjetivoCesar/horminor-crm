"""Modulo 4 - Dossier Financiero de Pre-Calificacion Bancaria.

Vista imprimible de 1 clic (HTML limpio, sin JS ni dependencias): el navegador
la imprime o la guarda como PDF. Todo numero sale del simulador y de la cuota
de mercado; no hay texto inventado.
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any, Mapping


def _money(valor: Any) -> str:
    if valor is None:
        return "—"
    try:
        return f"${float(valor):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _pct(valor: Any) -> str:
    if valor is None:
        return "—"
    return f"{float(valor):.2f}%"


def _semaforo(valor: Any) -> str:
    color = {"VERDE": "#0f7b3f", "AMBAR": "#a86500", "ROJO": "#a11818"}.get(
        str(valor or ""), "#555"
    )
    return f'<span style="color:{color};font-weight:700">{escape(str(valor or "—"))}</span>'


def construir_dossier_html(
    *,
    empresa: Mapping[str, Any] | None,
    simulador: Mapping[str, Any],
    mercado: Mapping[str, Any] | None,
    kpis: Mapping[str, Any] | None,
    generado_at: datetime | None = None,
) -> str:
    datos = dict(empresa or {})
    nombre = escape(
        str(datos.get("company_name") or "HORMINOR HORMIGONES Y PREFABRICADOS S.A.S.")
    )
    ruc = escape(str(datos.get("ruc") or "—"))
    direccion = escape(str(datos.get("main_plant_address") or "—"))
    fecha = (generado_at or datetime.now()).strftime("%Y-%m-%d %H:%M")

    escenarios = list(simulador.get("escenarios") or [])
    parametros = dict(simulador.get("parametros") or {})
    filas_escenarios = "\n".join(
        f"""
        <tr>
          <td>{escape(str(e.get('nombre') or ''))}</td>
          <td>{_money(e.get('monto_usd'))}</td>
          <td>{int(e.get('plazo_meses') or 0)}</td>
          <td>{_money(e.get('cuota_mensual'))}</td>
          <td>{_money(e.get('total_intereses'))}</td>
          <td>{_money(e.get('flujo_incremental_mensual'))}</td>
          <td>{e.get('dscr_proyectado') if e.get('dscr_proyectado') is not None else '—'}x</td>
          <td>{e.get('dscr_historico') if e.get('dscr_historico') is not None else '—'}x</td>
          <td>{_semaforo(e.get('semaforo'))}</td>
        </tr>
        """
        for e in escenarios
    )

    filas_mercado = ""
    for provincia in (mercado or {}).get("provincias") or []:
        filas_mercado += f"""
        <tr>
          <td>{escape(str(provincia.get('provincia') or ''))}</td>
          <td>{float(provincia.get('demanda_m3') or 0):,.0f} m3</td>
          <td>{float(provincia.get('ventas_m3') or 0):,.0f} m3</td>
          <td>{_pct(provincia.get('cuota_pct'))}</td>
          <td>{_money(provincia.get('valor_mercado_usd'))}</td>
          <td>{_money(provincia.get('competencia_usd'))}</td>
        </tr>
        """

    kpi_caja = dict((kpis or {}).get("kpi_caja") or {})
    kpi_operacion = dict((kpis or {}).get("kpi_operacion") or {})
    kpi_bodega = dict((kpis or {}).get("kpi_bodega") or {})

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Dossier Financiero de Pre-Calificacion Bancaria — Horminor</title>
<style>
  @page {{ size: A4; margin: 18mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: "Segoe UI", Arial, sans-serif; color:#15181c; margin:0; }}
  header {{ border-bottom: 3px solid #0b3d6b; padding-bottom: 12px; margin-bottom: 20px; }}
  h1 {{ font-size: 22px; margin:0 0 6px; color:#0b3d6b; }}
  h2 {{ font-size: 15px; margin: 26px 0 8px; color:#0b3d6b;
        text-transform: uppercase; letter-spacing:.06em; }}
  p, td, th {{ font-size: 11.5px; line-height: 1.45; }}
  .muted {{ color:#5b6470; }}
  table {{ width:100%; border-collapse: collapse; margin-top: 6px; }}
  th {{ text-align:left; background:#eef2f6; padding:7px 8px; border-bottom:1px solid #c9d3dd;
        font-size:10.5px; text-transform:uppercase; letter-spacing:.04em; }}
  td {{ padding:7px 8px; border-bottom:1px solid #e3e8ee; }}
  .kpis {{ display:flex; gap:10px; flex-wrap:wrap; }}
  .kpi {{ flex:1; min-width:150px; border:1px solid #d7dee6; border-radius:6px; padding:10px 12px; }}
  .kpi .label {{ font-size:10px; text-transform:uppercase; color:#5b6470; letter-spacing:.05em; }}
  .kpi .value {{ font-size:16px; font-weight:700; margin-top:4px; }}
  .nota {{ background:#f6f8fa; border-left:3px solid #0b3d6b; padding:10px 12px; margin-top:14px; }}
  footer {{ margin-top: 28px; border-top:1px solid #c9d3dd; padding-top:10px;
            font-size:10px; color:#5b6470; }}
  @media print {{ .no-print {{ display:none; }} }}
</style>
</head>
<body>
<header>
  <p class="muted" style="margin:0 0 4px;font-size:10px;letter-spacing:.12em;text-transform:uppercase">
    Documento de trabajo — no constituye solicitud formal de credito
  </p>
  <h1>Dossier Financiero de Pre-Calificacion Bancaria — Horminor</h1>
  <p class="muted" style="margin:0">{nombre} · RUC {ruc} · {direccion}</p>
  <p class="muted" style="margin:4px 0 0">Generado: {fecha}</p>
</header>

<h2>1. Pulso operativo de hoy</h2>
<div class="kpis">
  <div class="kpi"><div class="label">Cobrado hoy</div>
    <div class="value">{_money(kpi_caja.get('cobrado_hoy'))}</div></div>
  <div class="kpi"><div class="label">Cartera por cobrar</div>
    <div class="value">{_money(kpi_caja.get('por_cobrar_total'))}</div></div>
  <div class="kpi"><div class="label">m3 del mes</div>
    <div class="value">{float(kpi_operacion.get('m3_mes') or 0):,.0f} m3</div></div>
  <div class="kpi"><div class="label">Mixers en ruta</div>
    <div class="value">{int(kpi_operacion.get('mixers_en_ruta') or 0)}</div></div>
  <div class="kpi"><div class="label">Autonomia FC-210</div>
    <div class="value">{float(kpi_bodega.get('m3_fc210_disponibles') or 0):,.0f} m3</div></div>
</div>

<h2>2. Simulacion de financiamiento (amortizacion francesa)</h2>
<p class="muted">
  Tasa nominal anual {parametros.get('tasa_anual_pct', '—')}% capitalizable mensual
  (tasa mensual {parametros.get('tasa_mensual_pct', '—')}%).
  Margen neto operativo: {_money(parametros.get('margen_neto_m3'))} por m3.
  Flujo historico mensual: {_money(parametros.get('flujo_historico_mensual'))}.
</p>
<table>
  <thead>
    <tr>
      <th>Escenario</th><th>Monto</th><th>Plazo</th><th>Cuota</th>
      <th>Intereses</th><th>Flujo incremental</th>
      <th>DSCR activo</th><th>DSCR historico</th><th>Semáforo</th>
    </tr>
  </thead>
  <tbody>
    {filas_escenarios}
  </tbody>
</table>
<div class="nota">
  <strong>Lectura:</strong> el DSCR proyectado mide solo el flujo incremental del
  equipo (m3 extra x margen neto). El DSCR respaldado suma el flujo operativo
  historico de Horminor. Un valor igual o superior a 1.50x se considera verde
  para pre-calificacion.
</div>

<h2>3. Cuota de mercado y valorizacion de la competencia</h2>
<table>
  <thead>
    <tr>
      <th>Provincia</th><th>Demanda anual</th><th>Ventas Horminor</th>
      <th>Cuota</th><th>Valor del mercado</th><th>En manos de la competencia</th>
    </tr>
  </thead>
  <tbody>
    {filas_mercado or '<tr><td colspan="6">Sin benchmarks cargados.</td></tr>'}
  </tbody>
</table>
<p class="muted">
  Periodo: {escape(str((mercado or {}).get('periodo') or '—'))} ·
  Precio de valorizacion: {_money((mercado or {}).get('precio_valorizacion_m3'))} / m3
  ({(mercado or {}).get('resistencia_valorizacion') or 'FC-210'}).
</p>

<h2>4. Declaracion de alcance</h2>
<p>
  Horminor opera con planta fija en El Coca y planta movil en campamento.
  El presente dossier usa exclusivamente datos registrados en el sistema
  (ordenes, cobros, inventario y benchmarks cargados por Direccion).
  No incluye facturacion electronica SRI, que esta fuera de alcance.
</p>

<footer>
  Horminor / Centinela · Dossier generado automaticamente por el Modulo 4.
  Los datos provisionales son editables desde el Centro de Configuracion Superadmin.
</footer>
<p class="no-print" style="margin-top:18px">
  <button onclick="window.print()" style="padding:10px 16px;font-size:13px;cursor:pointer">
    Imprimir / Guardar como PDF
  </button>
</p>
</body>
</html>"""
