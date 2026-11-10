/* HorminorAgenda v6.2 - componente unico de calendario de entregas.
 *
 * Lo montan Dashboard, Secretaria y Planta. Lee el servicio unico
 * `/api/v1/panel/agenda` (dispatch_schedule + agenda.parametros). Cualquier
 * cambio dispara `horminor:agenda-updated` y refresca todas las instancias.
 */
(function (global) {
  'use strict';

  var MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
  var DIAS_CORTOS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
  var DIAS_ORDEN = ['LUN', 'MAR', 'MIE', 'JUE', 'VIE', 'SAB', 'DOM'];
  var PARAMS_DEFAULT = {
    hora_apertura: '07:00', hora_cierre: '18:00',
    duracion_entrega_default_min: 90, intervalo_slot_min: 30,
    dias_laborables: ['LUN', 'MAR', 'MIE', 'JUE', 'VIE', 'SAB']
  };
  var instancias = [];

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function isoLocal(d) {
    var y = d.getFullYear();
    var m = String(d.getMonth() + 1).padStart(2, '0');
    var dia = String(d.getDate()).padStart(2, '0');
    return y + '-' + m + '-' + dia;
  }

  function fechaCorta(iso) {
    var p = String(iso || '').split('-');
    return p.length === 3 ? p[2] + '/' + p[1] : String(iso || '');
  }

  function hoyIso() { return isoLocal(new Date()); }

  function esPlanta(inst) { return inst.config.mode === 'PLANTA_CHOFER'; }

  function readOnly(inst) {
    return typeof inst.config.getReadOnly === 'function' ? !!inst.config.getReadOnly() : false;
  }

  function labelNuevo(inst) {
    if (inst.config.mode === 'JULIO') return 'Agendar desde obra (Reserva)';
    if (inst.config.mode === 'PLANTA_CHOFER') return 'Reservar';
    return 'Agendar entrega';
  }

  function layout(inst) {
    var planta = esPlanta(inst);
    var crear = inst.config.allowCreate && !readOnly(inst);
    return '' +
      '<div class="ha">' +
      '<div class="ha-head">' +
        '<div><span class="card-kicker">Agenda real</span>' +
        '<h2 class="ha-title">' + (planta ? 'Cola de despachos' : 'Entregas y mixers') + '</h2></div>' +
        '<div class="ha-actions">' +
          (planta
            ? '<input type="date" class="ha-fecha" value="' + hoyIso() + '" aria-label="Fecha de la cola">'
            : '<div class="cal-nav"><button type="button" class="ha-prev" aria-label="Mes anterior">‹</button>' +
              '<button type="button" class="ha-next" aria-label="Mes siguiente">›</button></div>') +
          (crear ? '<button type="button" class="btn small ha-new">+ ' + esc(labelNuevo(inst)) + '</button>' : '') +
        '</div>' +
      '</div>' +
      '<div class="ha-body' + (planta ? ' ha-body-planta' : '') + '">' +
        (planta ? '' : '<div class="ha-cal"><div class="cal-grid ha-grid"></div></div>') +
        '<div class="ha-list-wrap"><p class="card-kicker ha-list-title">' +
          (planta ? 'Despachos del día' : 'Próximas entregas') + '</p>' +
          '<ul class="agenda-lista ha-list"></ul></div>' +
      '</div>' +
      '<div class="ha-msg"></div>' +
      '</div>';
  }

  function bind(inst) {
    var host = inst.host;
    var prev = host.querySelector('.ha-prev');
    var next = host.querySelector('.ha-next');
    var nuevo = host.querySelector('.ha-new');
    var fecha = host.querySelector('.ha-fecha');
    if (prev) prev.addEventListener('click', function () { mover(inst, -1); });
    if (next) next.addEventListener('click', function () { mover(inst, 1); });
    if (nuevo) nuevo.addEventListener('click', function () {
      var f = inst.state.selected || (fecha ? fecha.value : hoyIso());
      if (inst.config.onCreate) inst.config.onCreate(f);
    });
    if (fecha) fecha.addEventListener('change', function () {
      inst.state.selected = fecha.value;
      render(inst);
    });
    var grid = host.querySelector('.ha-grid');
    if (grid) grid.addEventListener('click', function (e) {
      var celda = e.target.closest('[data-fecha]');
      if (!celda) return;
      inst.state.selected = celda.getAttribute('data-fecha');
      render(inst);
    });
    var lista = host.querySelector('.ha-list');
    if (lista) lista.addEventListener('click', function (e) {
      var editar = e.target.closest('[data-editar]');
      if (editar && inst.config.onEdit) inst.config.onEdit(editar.getAttribute('data-editar'));
      var crear = e.target.closest('[data-crear-fecha]');
      if (crear && inst.config.onCreate) inst.config.onCreate(crear.getAttribute('data-crear-fecha'));
    });
  }

  function mover(inst, delta) {
    if (inst.state.y == null) {
      var n = new Date();
      inst.state.y = n.getFullYear();
      inst.state.m = n.getMonth();
    }
    inst.state.m += delta;
    if (inst.state.m < 0) { inst.state.m = 11; inst.state.y--; }
    if (inst.state.m > 11) { inst.state.m = 0; inst.state.y++; }
    inst.state.selected = null;
    inst.load();
  }

  function params(inst, callback) {
    var api = inst.config.api || global.api;
    if (inst.state.params) { callback(inst.state.params); return; }
    Promise.resolve(api('/api/v1/panel/agenda/parametros'))
      .then(function (r) { inst.state.params = (r && r.parametros) || PARAMS_DEFAULT; })
      .catch(function () { inst.state.params = PARAMS_DEFAULT; })
      .then(function () { callback(inst.state.params); });
  }

  function load(inst) {
    var api = inst.config.api || global.api;
    if (typeof api !== 'function') {
      inst.state.error = 'API del panel no disponible';
      render(inst);
      return;
    }
    inst.state.loading = true;
    renderMensaje(inst, 'Leyendo agenda…', 'info');
    params(inst, function () {
      var ahora = new Date();
      if (inst.state.y == null) {
        inst.state.y = ahora.getFullYear();
        inst.state.m = ahora.getMonth();
      }
      var desde = isoLocal(new Date(inst.state.y, inst.state.m, 1));
      var hasta = isoLocal(new Date(inst.state.y, inst.state.m + 2, 0));
      api('/api/v1/panel/agenda?desde=' + desde + '&hasta=' + hasta)
        .then(function (r) {
          inst.state.agenda = (r && r.agenda) || [];
          inst.state.error = null;
        })
        .catch(function (e) { inst.state.error = e.message || String(e); })
        .then(function () {
          inst.state.loading = false;
          render(inst);
        });
    });
  }

  function renderMensaje(inst, texto, tipo) {
    var el = inst.host.querySelector('.ha-msg');
    if (!el) return;
    el.innerHTML = texto ? '<div class="notice ' + (tipo || 'info') + '">' + esc(texto) + '</div>' : '';
  }

  function filtrarMixer(inst, filas) {
    var mixer = typeof inst.config.getFilterMixer === 'function'
      ? inst.config.getFilterMixer()
      : inst.config.filterMixer;
    if (!mixer) return filas;
    return filas.filter(function (a) { return String(a.mixer_codigo || '') === String(mixer); });
  }

  function render(inst) {
    var host = inst.host;
    var state = inst.state;
    var paramsActual = state.params || PARAMS_DEFAULT;
    var titulo = host.querySelector('.ha-title');
    var planta = esPlanta(inst);
    if (titulo) {
      titulo.textContent = planta
        ? 'Cola de despachos'
        : 'Entregas y mixers · ' + MESES[state.m] + ' ' + state.y;
    }

    var filas = filtrarMixer(inst, state.agenda || []);
    var porDia = {};
    filas.forEach(function (a) { (porDia[a.fecha_entrega] = porDia[a.fecha_entrega] || []).push(a); });

    var grid = host.querySelector('.ha-grid');
    if (grid) {
      var y = state.y, m = state.m;
      var offset = (new Date(y, m, 1).getDay() + 6) % 7;
      var dias = new Date(y, m + 1, 0).getDate();
      var celdas = DIAS_CORTOS.map(function (d) { return '<div class="cal-dow">' + d + '</div>'; });
      for (var i = 0; i < offset; i++) celdas.push('<div class="cal-cell blank"></div>');
      var hoy = hoyIso();
      for (var d = 1; d <= dias; d++) {
        var iso = y + '-' + String(m + 1).padStart(2, '0') + '-' + String(d).padStart(2, '0');
        var tiene = !!porDia[iso];
        var clases = ['cal-cell'];
        if (tiene) clases.push('has-event');
        if (iso === hoy) clases.push('today');
        if (iso === state.selected) clases.push('selected');
        celdas.push('<div class="' + clases.join(' ') + '" data-fecha="' + iso + '" title="' +
          (tiene ? porDia[iso].length + ' entrega(s)' : 'Sin entregas') + '">' + d + '</div>');
      }
      grid.innerHTML = celdas.join('');
    }

    var fechaCola = host.querySelector('.ha-fecha');
    if (planta && fechaCola && !state.selected) state.selected = fechaCola.value || hoyIso();

    var lista = host.querySelector('.ha-list');
    if (!lista) return;
    var visibles;
    if (planta) {
      visibles = (porDia[state.selected] || []).slice();
    } else if (state.selected) {
      visibles = (porDia[state.selected] || []).slice();
    } else {
      var hoyKey = hoyIso();
      visibles = filas.filter(function (a) {
        return a.fecha_entrega >= hoyKey && a.estado !== 'CANCELADO';
      }).sort(function (a, b) {
        return (a.fecha_entrega + a.hora_inicio).localeCompare(b.fecha_entrega + b.hora_inicio);
      }).slice(0, 10);
    }
    visibles.sort(function (a, b) {
      return (a.fecha_entrega + a.hora_inicio).localeCompare(b.fecha_entrega + b.hora_inicio);
    });

    var tituloLista = host.querySelector('.ha-list-title');
    if (tituloLista) {
      tituloLista.textContent = planta
        ? 'Despachos del ' + fechaCorta(state.selected)
        : (state.selected ? 'Entregas del ' + fechaCorta(state.selected) : 'Próximas entregas');
    }

    var puedeEditar = !readOnly(inst) && typeof inst.config.onEdit === 'function' &&
      (inst.config.allowReschedule || inst.config.allowCreate !== false);

    if (!visibles.length) {
      lista.innerHTML = '<li class="muted small ha-empty">Sin entregas en este rango.' +
        (inst.config.allowCreate && !readOnly(inst)
          ? ' <button type="button" class="link-btn" data-crear-fecha="' + esc(state.selected || hoyIso()) + '">+ Agendar</button>'
          : '') + '</li>';
      renderMensaje(inst, '', 'info');
      return;
    }

    lista.innerHTML = visibles.map(function (a) {
      var estado = String(a.estado || 'PROGRAMADO');
      var badge = estado === 'EN_RUTA' ? 'ok' : estado === 'CANCELADO' ? 'bad' :
        estado === 'RESERVA_CAMPO' ? 'warn' : 'neutral';
      return '<li class="agenda-item">' +
        '<span class="hora">' + esc(a.hora_inicio || '--:--') + '</span>' +
        '<div class="detalle"><strong>' + esc(a.cliente || 'Sin cliente') + ' · ' + Number(a.volumen_m3 || 0) + ' m³</strong>' +
        '<span>' + esc(fechaCorta(a.fecha_entrega)) + ' · ' + esc(a.mixer_codigo || 'sin mixer') +
        ' · ' + esc(a.direccion_obra || 'sin dirección') + '</span></div>' +
        '<div class="acciones"><span class="badge ' + badge + '">' + esc(estado) + '</span>' +
        (puedeEditar ? '<button type="button" class="btn small ghost" data-editar="' + esc(a.id) + '">Editar</button>' : '') +
        '</div></li>';
    }).join('');
    renderMensaje(inst, state.error || '', 'bad');
  }

  function mount(selector, config) {
    var host = typeof selector === 'string' ? document.querySelector(selector) : selector;
    if (!host) return null;
    if (host.__horminorAgenda) {
      host.__horminorAgenda.config = Object.assign({}, host.__horminorAgenda.config, config || {});
      host.__horminorAgenda.state.params = null;
      host.__horminorAgenda.host.innerHTML = layout(host.__horminorAgenda);
      bind(host.__horminorAgenda);
      host.__horminorAgenda.load();
      return host.__horminorAgenda;
    }
    var inst = {
      host: host,
      config: Object.assign({ mode: 'SECRETARIA', allowCreate: false }, config || {}),
      state: { y: null, m: null, agenda: [], params: null, selected: null, loading: false, error: null }
    };
    inst.load = function () { load(inst); };
    host.__horminorAgenda = inst;
    instancias.push(inst);
    host.innerHTML = layout(inst);
    bind(inst);
    inst.load();
    if (!global.__horminorAgendaListener) {
      global.addEventListener('horminor:agenda-updated', function () { refreshAll(); });
      global.__horminorAgendaListener = true;
    }
    return inst;
  }

  function refreshAll() {
    instancias.forEach(function (inst) {
      // No consultar agendas de tarjetas ocultas (perfil sin modulo o vista
      // inactiva): evita 403 en consola y lecturas innecesarias.
      if (inst.host.offsetParent === null) return;
      inst.state.params = null;
      inst.load();
    });
  }

  function notifyChanged() {
    global.dispatchEvent(new CustomEvent('horminor:agenda-updated'));
  }

  global.HorminorAgenda = {
    mount: mount,
    refreshAll: refreshAll,
    notifyChanged: notifyChanged,
    DIAS_ORDEN: DIAS_ORDEN
  };
})(window);
