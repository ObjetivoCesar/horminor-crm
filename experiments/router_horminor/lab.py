"""Laboratorio web del router (aislado). ASCII puro en el codigo.

    python -m experiments.router_horminor.lab
    abrir http://localhost:8055

No ejecuta tareas: al confirmar devuelve el plan de lo que se crearia.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from experiments.d_vs_dmas.llm import nuevo_cliente

from . import errores
from .confirmacion import planificar, verificar_correspondencia
from .conversacion import (
    es_confirmacion,
    respuesta_confirmacion,
    respuesta_correccion,
)
from .correccion import corregir
from .model import BorradorRouter
from .router import construir

app = FastAPI(title="Router Horminor (prototipo)")

HTML = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>Router Horminor</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--line:#2a2f3a;--txt:#e8eaed;--dim:#9aa3af;
--ok:#f2c14e;--danger:#e06c75}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.45 system-ui,sans-serif}
header{padding:16px 22px;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:center}
header b{font-size:17px} header span{color:var(--dim);font-size:12px}
main{max-width:980px;margin:0 auto;padding:22px;display:grid;gap:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
textarea{width:100%;min-height:110px;background:#11141a;color:var(--txt);
border:1px solid var(--line);border-radius:8px;padding:12px;font:inherit;resize:vertical}
button{background:#222834;color:var(--txt);border:1px solid var(--line);border-radius:8px;
padding:9px 14px;font:inherit;cursor:pointer}
button.primary{background:var(--ok);color:#161616;border-color:var(--ok);font-weight:600}
button.ghost{padding:5px 9px;font-size:12px}
button:disabled{opacity:.5;cursor:default}
.resumen{font-size:16px;margin:0;white-space:pre-line}
.errores{display:grid;gap:8px;font-size:13px}
.error{border:1px solid var(--line);border-radius:8px;padding:8px 10px;background:#141821}
.error b{color:var(--ok)}
.error .antes{color:var(--danger);text-decoration:line-through}
.error .despues{color:#8fd3a8}
.burbuja{background:#1b2230;border-left:3px solid var(--ok);border-radius:0 12px 12px 0;
padding:14px 16px;margin:0 0 14px;font-size:16px;line-height:1.55}
.quien{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--ok);
margin-bottom:6px}
.encargo{border:1px solid var(--line);border-radius:10px;padding:12px;margin:10px 0;display:grid;gap:6px}
.encargo h3{margin:0;font-size:15px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.pill{font-size:11px;padding:2px 8px;border-radius:99px;border:1px solid var(--line);color:var(--dim)}
.pill.sec{color:#8fd3a8;border-color:#2e5c3f}
.pill.plan{color:#8fb8f0;border-color:#2d4769}
.pill.julio{color:#f2c14e;border-color:#6b5a25}
.pill.warn{color:#e0a35c;border-color:#6b4a25}
.detalle{color:var(--dim);font-size:13px}
.acciones{display:flex;gap:8px;flex-wrap:wrap;margin-top:6px;align-items:center}
pre{background:#0c0e13;border:1px solid var(--line);border-radius:8px;padding:12px;
overflow:auto;font-size:12px;max-height:360px}
.aviso{color:var(--dim);font-size:12px}
.preguntas{color:#e0a35c}
.conv{display:grid;gap:8px;margin:14px 0;max-height:320px;overflow:auto}
.msg{max-width:86%;padding:10px 12px;border-radius:12px;white-space:pre-line;font-size:14px;line-height:1.45}
.msg.julio{background:#243044;margin-left:auto}
.msg.cerebro{background:#1b2230;border-left:3px solid var(--ok)}
.msg .quien{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);margin-bottom:4px}
.responder{display:flex;gap:8px;align-items:flex-end;margin-top:8px}
.responder textarea{min-height:56px}
</style></head><body>
<header><b>Router Horminor</b><span>prototipo aislado &middot; propone, no ejecuta</span></header>
<main>
  <section class="card">
    <textarea id="dictado" placeholder="Escribe lo que diria Julio..."></textarea>
    <div class="acciones" style="margin-top:10px">
      <button class="primary" id="btnInterpretar">Interpretar</button>
      <button id="btnEjemplo">Poner ejemplo</button>
      <span class="aviso">Al confirmar se muestra el plan; no se crea nada real.</span>
    </div>
  </section>
  <section class="card" id="resultado" style="display:none">
    <div class="burbuja"><div class="quien">Cerebro</div><p class="resumen" id="resumen"></p></div>
    <div id="encargos"></div>
    <div id="preguntas" class="preguntas"></div>
    <div id="notas" class="detalle"></div>
    <div class="acciones" style="margin-top:14px">
      <button class="primary" id="btnConfirmar">Confirmar seleccionados</button>
      <button id="btnTodo">Seleccionar todo</button>
    </div>
    <div id="plan" style="margin-top:14px"></div>
    <div class="conv" id="conv"></div>
    <div class="responder">
      <textarea id="respuesta" rows="2" placeholder="Responde al Cerebro: corrige, cancela o confirma..."></textarea>
      <button class="primary" id="btnResponder">Enviar</button>
    </div>
  </section>
  <section class="card" id="erroresCard">
    <h3 style="margin-top:0">Errores y correcciones</h3>
    <div class="errores" id="errores"><span class="detalle">Sin correcciones todavia.</span></div>
  </section>
</main>
<script>
let borrador = null;
const $ = (id) => document.getElementById(id);
const color = (r) => r === 'SECRETARIA' ? 'sec' : r === 'JEFE_PLANTA' ? 'plan' : r === 'JULIO' ? 'julio' : 'warn';
async function post(ruta, cuerpo) {
  const r = await fetch(ruta, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(cuerpo)});
  const d = await r.json();
  if (!r.ok) throw new Error(d.detail ? JSON.stringify(d.detail) : 'Error');
  return d;
}
function pintar() {
  $('resultado').style.display = 'block';
  $('resumen').textContent = borrador.resumen;
  const caja = $('encargos'); caja.innerHTML = '';
  borrador.encargos.forEach((e) => {
    const div = document.createElement('div'); div.className = 'encargo';
    const h = document.createElement('h3');
    const chk = document.createElement('input'); chk.type = 'checkbox'; chk.checked = true; chk.dataset.id = e.id;
    const titulo = document.createElement('span'); titulo.textContent = e.id + ' - ' + e.titulo;
    const pill = document.createElement('span'); pill.className = 'pill ' + color(e.responsable);
    pill.textContent = e.responsable + (e.responsable_sugerido ? ' (sugerido)' : '');
    h.append(chk, titulo, pill);
    div.appendChild(h);
    const d = document.createElement('div'); d.className = 'detalle'; d.textContent = e.que_hacer; div.appendChild(d);
    if (e.por_investigar.length) { const p = document.createElement('div'); p.className='detalle'; p.textContent='Por investigar: ' + e.por_investigar.join('; '); div.appendChild(p); }
    if (e.resultado_esperado) { const p = document.createElement('div'); p.className='detalle'; p.textContent='Resultado esperado: ' + e.resultado_esperado; div.appendChild(p); }
    if (e.condiciones.length) { const p = document.createElement('div'); p.className='detalle'; p.textContent='Condiciones: ' + e.condiciones.join('; '); div.appendChild(p); }
    if (e.requiere_autorizacion) { const p = document.createElement('div'); p.className='detalle'; p.textContent='Requiere autorizacion de ejecucion: ' + (e.autorizado ? 'si' : 'no'); div.appendChild(p); }
    const acc = document.createElement('div'); acc.className = 'acciones';
    const b1 = document.createElement('button'); b1.className='ghost'; b1.textContent='Corregir responsable';
    b1.onclick = async () => {
      const frase = prompt('Como lo corrige Julio?', 'No era para ' + e.responsable.toLowerCase() + ', era para el jefe de planta');
      if (!frase) return;
      const d = await post('/api/corregir', {borrador, frase});
      if (d.errores.length) { alert(d.errores.join('\\n')); return; }
      borrador = d.borrador; pintar(); cargarErrores();
    };
    const b2 = document.createElement('button'); b2.className='ghost'; b2.textContent='Cancelar';
    b2.onclick = async () => {
      const frase = prompt('Que cancela?', 'cancela ' + e.id);
      if (!frase) return;
      const d = await post('/api/corregir', {borrador, frase});
      if (d.errores.length) { alert(d.errores.join('\\n')); return; }
      borrador = d.borrador; pintar(); cargarErrores();
    };
    acc.append(b1, b2); div.appendChild(acc);
    caja.appendChild(div);
  });
  $('preguntas').textContent = borrador.preguntas.length ? 'Antes de confirmar: ' + borrador.preguntas.join(' ') : '';
  $('notas').textContent = borrador.notas.length ? borrador.notas.join(' - ') : '';
  $('plan').innerHTML = '';
}
async function cargarErrores() {
  try {
    const d = await (await fetch('/api/errores')).json();
    const caja = $('errores'); caja.innerHTML = '';
    if (!d.errores.length) {
      const s = document.createElement('span'); s.className='detalle';
      s.textContent = 'Sin correcciones todavia.'; caja.appendChild(s); return;
    }
    d.errores.forEach((e) => {
      const div = document.createElement('div'); div.className='error';
      const b = document.createElement('b');
      b.textContent = e.fecha + ' · ' + (e.tipo || 'CORRECCION');
      div.appendChild(b);
      const m = document.createElement('div');
      m.textContent = 'Julio: «' + (e.mensaje_julio || '') + '»';
      div.appendChild(m);
      (e.cambios || []).forEach((c) => {
        const p = document.createElement('div');
        p.textContent = c.campo + ': ';
        const a = document.createElement('span'); a.className='antes';
        a.textContent = String(c.antes === null ? '—' : c.antes);
        const s = document.createElement('span'); s.className='despues';
        s.textContent = '  →  ' + String(c.despues);
        p.append(a, s); div.appendChild(p);
      });
      caja.appendChild(div);
    });
  } catch (e) { /* silencio */ }
}
cargarErrores();

function agregar(quien, texto) {
  const caja = $('conv');
  const div = document.createElement('div');
  div.className = 'msg ' + quien;
  const q = document.createElement('div');
  q.className = 'quien';
  q.textContent = quien === 'julio' ? 'Julio' : 'Cerebro';
  const cuerpo = document.createElement('div');
  cuerpo.textContent = texto;
  div.append(q, cuerpo);
  caja.appendChild(div);
  caja.scrollTop = caja.scrollHeight;
}

async function responder() {
  const frase = $('respuesta').value.trim();
  if (!frase || !borrador) return;
  $('btnResponder').disabled = true;
  try {
    const d = await post('/api/responder', {borrador, frase});
    agregar('julio', frase);
    $('respuesta').value = '';
    if (d.tipo === 'ERROR') {
      agregar('cerebro', d.mensaje);
      return;
    }
    borrador = d.borrador;
    pintar();
    agregar('cerebro', d.mensaje);
    if (d.plan) {
      $('plan').innerHTML = '<h3>Plan de confirmacion</h3><pre>'
        + JSON.stringify(d.plan, null, 1) + '</pre>'
        + '<p class="detalle">Correspondencia: '
        + (d.problemas && d.problemas.length ? d.problemas.join('; ') : 'OK') + '</p>';
    }
    cargarErrores();
  } catch (e) {
    agregar('cerebro', 'No pude responder: ' + e.message);
  } finally {
    $('btnResponder').disabled = false;
  }
}

$('btnResponder').onclick = responder;
$('respuesta').addEventListener('keydown', (ev) => {
  if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); responder(); }
});

$('btnInterpretar').onclick = async () => {
  const texto = $('dictado').value.trim();
  if (!texto) return;
  $('btnInterpretar').disabled = true;
  try {
    const d = await post('/api/dictar', {texto});
    if (d.error) { alert(d.error); return; }
    borrador = d.borrador;
    pintar();
    $('conv').innerHTML = '';
    agregar('julio', texto);
    agregar('cerebro', borrador.resumen);
  } catch (e) { alert(e.message); } finally { $('btnInterpretar').disabled = false; }
};
$('btnEjemplo').onclick = () => {
  $('dictado').value = 'Tres cosas para hoy: que secretaria revise el pago de La Pradera, que contacte al cliente para confirmar la fecha de entrega, y que el jefe de planta prepare la coordinacion del despacho. La salida del camion queda condicionada a que se confirme el anticipo.';
};
$('btnTodo').onclick = () => document.querySelectorAll('#encargos input[type=checkbox]').forEach(c => c.checked = true);
$('btnConfirmar').onclick = async () => {
  const ids = [...document.querySelectorAll('#encargos input[type=checkbox]:checked')].map(c => c.dataset.id);
  if (!ids.length) return;
  const d = await post('/api/confirmar', {borrador, confirmados: ids});
  $('plan').innerHTML = '<h3>Plan de confirmacion</h3><pre>' + JSON.stringify(d.plan, null, 1) + '</pre>'
    + '<p class="detalle">Correspondencia: ' + (d.problemas.length ? d.problemas.join('; ') : 'OK') + '</p>';
};
</script></body></html>
"""


class DictarIn(BaseModel):
    texto: str


class CorregirIn(BaseModel):
    borrador: dict
    frase: str


class ConfirmarIn(BaseModel):
    borrador: dict
    confirmados: list[str] | None = None
    autorizaciones: dict[str, bool] = {}


class ResponderIn(BaseModel):
    borrador: dict
    frase: str
    confirmados: list[str] | None = None


@app.get("/", response_class=HTMLResponse)
async def inicio() -> str:
    return HTML


@app.post("/api/dictar")
async def dictar(body: DictarIn) -> dict:
    async with nuevo_cliente(concurrencia=6) as cliente:
        resultado = await construir(cliente, body.texto)
    return {
        "error": resultado.error,
        "borrador": resultado.borrador.model_dump(),
        "llamadas": resultado.llamadas,
    }


@app.post("/api/corregir")
async def corregir_api(body: CorregirIn) -> dict:
    borrador = BorradorRouter.model_validate(body.borrador)
    async with nuevo_cliente(concurrencia=4) as cliente:
        nuevo, errores, meta = await corregir(cliente, borrador, body.frase)
    return {
        "errores": errores,
        "borrador": nuevo.model_dump() if nuevo else None,
        "meta": meta,
    }


@app.post("/api/confirmar")
async def confirmar_api(body: ConfirmarIn) -> dict:
    borrador = BorradorRouter.model_validate(body.borrador)
    plan = planificar(
        borrador,
        confirmados=body.confirmados,
        autorizaciones=body.autorizaciones,
    )
    problemas = verificar_correspondencia(borrador, plan, confirmados=body.confirmados)
    return {"plan": plan.model_dump(), "problemas": problemas}


@app.post("/api/responder")
async def responder_api(body: ResponderIn) -> dict:
    borrador = BorradorRouter.model_validate(body.borrador)
    if es_confirmacion(body.frase):
        plan = planificar(borrador, confirmados=body.confirmados)
        return {
            "tipo": "CONFIRMACION",
            "mensaje": respuesta_confirmacion(plan),
            "borrador": borrador.model_dump(),
            "plan": plan.model_dump(),
            "problemas": verificar_correspondencia(
                borrador, plan, confirmados=body.confirmados
            ),
        }

    async with nuevo_cliente(concurrencia=4) as cliente:
        nuevo, errores_correccion, meta = await corregir(
            cliente, borrador, body.frase
        )
    if nuevo is None:
        return {
            "tipo": "ERROR",
            "mensaje": "No pude aplicarlo: " + "; ".join(errores_correccion),
            "borrador": borrador.model_dump(),
            "meta": meta,
        }
    return {
        "tipo": "CORRECCION",
        "mensaje": respuesta_correccion(nuevo, meta),
        "borrador": nuevo.model_dump(),
        "meta": meta,
    }


@app.get("/api/errores")
async def errores_api() -> dict:
    return {"errores": errores.listar(30)}


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8055, log_level="warning")


if __name__ == "__main__":
    main()
