# Brief para Carbon — Dashboard de Julio: filtros, capacidad y cobranza

> **Qué es este archivo:** el paquete de contexto que se pega a Carbon para que
> diseñe el sistema de filtros y el tablero de decisión de Julio Villavicencio
> (Horminor) sobre datos reales, no sobre suposiciones.
>
> **Qué debe devolver Carbon:** un plan profundo, contratos de métricas, el
> esquema de configuración de capacidad, la taxonomía de filtros (especialmente
> cobranza), la especificación de UI y el plan de pruebas. No un prototipo.
>
> **Regla madre:** si un dato no está aquí, Carbon debe preguntarlo o marcarlo
> `NO_CONFIGURADO`. No se inventa.

---

## 0. Cómo usar este documento

1. Adjuntar a Carbon, además de este archivo:
   - `docs/PDR_v4.0.txt` (alcance y módulos).
   - `docs/BASE_DE_DATOS.md` (mapa técnico de la base).
   - `docs/DASHBOARD_JULIO_ANALISIS.md` (análisis previo, hipótesis y variables).
   - `docs/CATALOGO_CONSULTAS.json` (consultas nombradas y contratos).
   - `docs/CARBON_ARRANQUE.md` (estándar de skills, si va a tocar la skill).
   - Capturas del panel actual (opcional; se describen en §7).
2. Pegar el **prompt maestro** de §1 y, debajo, el **encargo** de §2.
3. Carbon trabaja en loop y con árbitro adversarial (§12). No aceptar la primera
   versión.
4. Las preguntas que Carbon hará están en §13, con la respuesta ya verificada.
   Las que faltan de verdad están en §14: esas se responden con Julio.

---

## 1. Prompt maestro (pegar tal cual)

```text
Eres Carbon. Trabajas como arquitecto de producto, datos y operaciones para
Horminor, una empresa de hormigón premezclado en El Coca, Ecuador. Tu trabajo no
es escribir un tablero bonito: es diseñar el sistema de decisiones de su dueño,
Julio Villavicencio, con los datos que la empresa ya tiene y con los que le
faltan.

Trabaja en loop: planifica, construye, prueba, revisa, corrige y repite. No me
entregues la primera versión. Usa un árbitro que emplee técnicas adversariales
para auditar y criticar el trabajo hecho hasta el nivel que se pide. No uses
placeholders ni te detengas en un prototipo básico.

Antes de reescribir la solución:
(1) dime qué haría aquí un profesional de primer nivel en este campo que yo no
    estoy pidiendo;
(2) nombra el material más en bruto (raw) del que partiría en lugar de lo que ya
    viene digerido para mí;
(3) nombra los métodos y herramientas específicos que usaría;
(4) nombra qué, aparte de ti o de mí, demostraría que el resultado es correcto.

Luego reescribe la respuesta y entrega el plan que se implementará en el
software.
```

---

## 2. El encargo exacto

Diseña, con el contexto de §3–§14, **el mejor juego de filtros y ventanas para
el dashboard de Julio**, desde su rol y sus decisiones, usando solo lo que la
base tiene o puede configurar. En concreto:

1. **Modelo de decisión.** Cuatro ventanas, en este orden:
   - Operación y capacidad (por defecto, activa en amarillo).
   - Inventario vs ventas.
   - Inventario por fechas.
   - Cobranza y caja.
   Para cada una: pregunta que responde, decisión que habilita, dueño, umbral,
   acción y qué pasa si el dato falta.
2. **Taxonomía de filtros.** Para cada ventana: filtros, semántica exacta, grano,
   fuente, valores permitidos, valor por defecto, combinaciones válidas,
   combinaciones prohibidas y por qué. En cobranza, el "juego de filtros" debe
   permitir ver urgencia financiera y capacidad de recuperar efectivo.
3. **Presets de decisión.** Combinaciones con nombre para el día de Julio (por
   ejemplo "Urgencia 7 días", "Mora", "Clientes grandes", "Sin vencimiento",
   "Cupo excedido"). Cada preset con su SQL lógico y su salida.
4. **Contratos de métrica.** Nombre, fórmula, grano, fuente, política de nulos,
   frescura, umbral y dueño. Montos como texto decimal; nada de floats.
5. **Modelo de capacidad.** Configuración en Superadmin, fórmula, cuello de
   botella, supuestos, estados `NO_CONFIGURADO` / `CONFIGURACION_INCONSISTENTE`.
6. **Modelo de cobranza.** Regla de documento único, aging, caja esperada, DSO,
   riesgo de cupo y qué hacer cuando no hay fechas ni pagos.
7. **Especificación de UI.** Banner `sec-ventanilla` con la ventana activa en
   amarillo sólido, primero y encima de los gráficos; submenú por ventana; 3
   tarjetas KPI que cambian con la ventana; gráficos SVG sin CDN; estados vacíos
   explícitos; responsive; accesibilidad; sin build.
8. **Contratos de backend.** Endpoints, envoltura `fuente/consultado/filtros/
   datos/vacio`, campos exactos, casos vacíos, límites y paginación.
9. **Plan de pruebas y reconciliación.** Unitarias, integración, datos dorados,
   pruebas de doble conteo, sobrecapacidad, nulos, mes vacío.
10. **Auditoría adversarial.** Qué objetaría un árbitro y cómo se responde.
11. **Preguntas abiertas** para Julio, con impacto y valor por defecto seguro.
12. **Secuencia de implementación** con criterios de cierre verificables.

**Formato de entrega:** archivos completos, sin placeholders. Sugerido:
`PLAN_DECISIONES.md`, `TAXONOMIA_FILTROS.md`, `CONTRATO_METRICAS.json`,
`CONFIG_CAPACIDAD.json`, `CONSULTAS.sql`, `UI_SPEC.md`, `TEST_PLAN.md`,
`AUDITORIA_ADVERSARIA.md`.

---

## 3. El negocio en 30 segundos

- **Cliente:** Julio Villavicencio — **Horminor**, hormigón premezclado y planta
  móvil. El Coca / Francisco de Orellana, Orellana y Sucumbíos, Ecuador.
- **Operación:** planta fija en El Coca, planta móvil para campamentos, mixers
  propios, recetas FC-180/210/240/280/350, venta por m³ con equipo y bombeo.
- **Mercado:** Orellana 120.000 m³/año; Sucumbíos 95.000 m³/año
  (`market_benchmarks`). La cuota de Horminor es pequeña (0,31 % y 0,02 % en la
  foto actual).
- **Dolor de Julio:** no sabe, en una sola pantalla, cuánto puede producir y
  entregar, si el material alcanza para lo vendido, y cuánto efectivo puede
  recuperar. Hoy el dashboard muestra tarjetas y filtros que no responden esas
  preguntas.
- **Restricción que dio Dirección (2026-11-13):** 2 camiones de 7 m³, máximo 3
  viajes/día cada uno → **42 m³/día**. Debe configurarse desde Superadmin, no
  cablearse. Es una nota que la skill que lee datos debe respetar.

### 3.1 Lo que Julio pidió textualmente (recuperado)

> "Lo principal la ocupación de sus mixers · el inventario frente a las ventas
> (cruzar la información) · inventario por fechas · cuentas por cobrar para ver
> disposición de efectivo y necesidad de cobrar cuentas."
>
> "Los gráficos que se muestren por default sean los de la 4ta captura
> [Mercado, Ventas, Dónde vendes], pero añadimos en los de la tercera captura
> [Ventanilla] sacando los filtros para que en base de eso asomen los gráficos
> BASADOS EN LAS BASES DE DATOS, no de adorno."
>
> "En todas las páginas usamos esto con un fondo amarillo para la ventana
> activa; es lo primero y debe estar encima de los gráficos."

---

## 4. Restricciones inviolables

1. **Cero datos de negocio inventados.** Recetas, precios, teléfonos, stock,
   capacidades, umbrales: o salen de la base/Cliente, o van `NULL` y marcados.
2. **Cero datos de negocio en el código.** Todo parámetro vive en
   `system_settings` o en tablas maestras.
3. **La IA no calcula.** Sumas, márgenes, capacidad y aging se hacen en SQL o
   Python con `Decimal`. Un LLM solo lee la ficha.
4. **El JSONB manda.** `mixer_dispatches.tracking_payload` es el contrato; las
   columnas planas las sincroniza un trigger.
5. **No se edita una migración aplicada.** La capacidad va en `system_settings`
   (parámetro), no en una migración.
6. **Vacío explícito.** `SIN_VENCIMIENTO`, `SIN_CONTEO_FISICO`,
   `NO_CONFIGURADO`, `CONFIGURACION_INCONSISTENTE` son respuestas válidas. Un
   cero sin explicación es un dato falso.
7. **Nada de cálculo de negocio en JavaScript.** El backend suma; el navegador
   solo dibuja.
8. **Sin CDN ni build.** Panel HTML único, Poppins local, SVG propio, tema
   día/noche.
9. **No romper los tests.** Al último cierre: **386 tests** en verde. Si se
   cambian textos/IDs del HTML, se actualizan los asserts en el mismo cambio.
10. **No exponer secretos.** Tokens, API keys y teléfonos reales no entran en
    documentos ni ejemplos.

---

## 5. El sistema actual (para que Carbon sepa dónde encaja)

- **Stack:** PostgreSQL 15 + Redis 7 + FastAPI + Evolution API + Bunny.net, todo
  en Docker. Objetivo final: VPS Linux.
- **Panel:** `/panel`, un solo HTML sin build, servido por FastAPI. Marca
  HORMINOR, sidebar CRM, tema día/noche, tipografía Poppins local.
- **Base:** 26 migraciones aplicadas, **37 tablas**, **8 vistas**. Última:
  `079_vencimiento_cobranza.sql`.
- **Módulos:** M0 datos/config, M1 WhatsApp, M2 motor determinístico, M3
  Secretaría/Caja, M4 Dashboard, M5 Centinela. El dashboard es **solo lectura**.
- **Estado:** Hito 1 cerrado, Hito 3 en SANDBOX, M3 y M4 construidos y
  verificados. El panel se afina en local; login pendiente antes del VPS.

### 5.1 Endpoints que ya existen

| Método | Ruta | Devuelve |
|---|---|---|
| GET | `/api/v1/dashboard/hero-kpis?fecha=` | caja, operación, bodega |
| GET | `/api/v1/dashboard/mercado?periodo=&anio=` | cuota por provincia |
| GET | `/api/v1/dashboard/simulador` | escenarios bancarios |
| GET | `/api/v1/dashboard/benchmarks` | competencia/demanda |
| GET | `/api/v1/dashboard/bancos` | cuentas y saldos |
| GET | `/api/v1/dashboard/bancos/{slug}` | detalle de banco |
| PUT | `/api/v1/dashboard/bancos/{slug}` | editar datos del banco |
| GET | `/api/v1/dashboard/inventario` | stock de 4 materiales |
| GET | `/api/v1/dashboard/cobranza` | cubos + clientes |
| GET | `/api/v1/dashboard/dossier` | dossier HTML |
| GET | `/api/v1/orders`, `/orders/{id}` | órdenes |
| GET | `/api/v1/inventory` | inventario |
| GET | `/api/v1/secretaria/clientes` | cartera |
| GET | `/api/v1/panel/agenda` | agenda de entregas |

### 5.2 Envoltura obligatoria de los endpoints del tablero

```json
{
  "fuente": ["tabla_o_vista_real"],
  "consultado": "2026-11-13T11:00:00-05:00",
  "filtros": {"desde": "2026-11-01", "hasta": "2026-11-30"},
  "datos": {},
  "vacio": {"motivo": "SIN_FECHAS_CAPTURADAS", "mensaje": "..."}
}
```

`fuente` es la tabla/vista real; `vacio` es `null` si hay datos; `consultado` es
hora del servidor; sin `LIMIT` silencioso.

---

## 6. Inventario de datos real (foto verificada)

> Todo lo de esta sección se consultó en la base local el 2026-11-13. Es la
> verdad que Carbon debe usar.

### 6.1 Volúmenes

| Tabla | Filas | Nota |
|---|---:|---|
| `orders` | 4 | todas `CONFIRMADA` |
| `mixer_dispatches` | 51 | 49 `PROGRAMADO`, 1 `CONFIRMADO_CLIENTE`, 1 `INCIDENCIA_RECLAMO` |
| `inventory_movements` | 249 | **todos `TEORICO`**, sin `REAL` |
| `clients` | 6 | 2 con ventas, 3 leads, 1 debug |
| `materials` | 5 | CEMENTO, ARENA, RIPIO, RETARDANTE, AGUA |
| `concrete_recipes` | 5 | FC-180/210/240/280/350, confirmadas |
| `payments` | 0 | sin cobros registrados |
| `ledger_entries` | 0 | sin asientos |
| `cash_closures` | 0 | sin cierres |
| `dispatch_schedule` | 0 | agenda vacía |
| `client_invoices` | 1 | `PRUEBA-0001`, ficticia |
| `bank_accounts` | 3 | sin saldo informado |
| `market_benchmarks` | 4 | Orellana y Sucumbíos, 2025/2026 |

### 6.2 Órdenes

| # | Fecha | Cliente | Resistencia | m³ | Total con IVA | Pago | Estado |
|---|---|---|---:|---:|---:|---|---|
| 9 | 2026-11-08 | Debug | FC-210 | 16 | NULL | FIADO | CONFIRMADA |
| 55 | 2026-11-09 | Ing. Reyes (prueba Hito 1) | FC-210 | 320 | 43.424,00 | FIADO | CONFIRMADA |
| 56 | 2026-11-09 | Ing. Reyes (prueba Hito 1) | FC-350 | 52 | 9.448,40 | FIADO | CONFIRMADA |
| 57 | 2026-11-09 | Cliente Prueba Hito 3 | FC-210 | 16 | 2.171,20 | FIADO | CONFIRMADA |

**Total vendido:** 404 m³; **bruto con IVA:** 55.043,60; **cobrado:** 0.

### 6.3 Flota configurada (¡contradice a Dirección!)

```json
[
  {"codigo": "MIXER-01", "placa": "OAA-1024", "capacidad_m3": 8.0, "activo": true, "chofer": "Pedro Andy"},
  {"codigo": "MIXER-02", "placa": "OAA-1088", "capacidad_m3": 8.0, "activo": true, "chofer": "Carlos Grefa"},
  {"codigo": "MIXER-03", "placa": "PBA-4512", "capacidad_m3": 7.0, "activo": true, "chofer": "Luis Zambrano"}
]
```

Dirección dice **2 camiones de 7 m³, 3 viajes/día → 42 m³/día**. La semilla dice
3 mixers (8/8/7) y **no tiene `viajes_max_dia`**. No se corrige por código: se
corrige en Superadmin con Julio. Mientras tanto, el tablero debe mostrar
`CONFIGURACION_INCONSISTENTE`.

### 6.4 Horario y operación

```json
"agenda.parametros": {
  "hora_apertura": "07:00", "hora_cierre": "18:00",
  "dias_laborables": ["LUN","MAR","MIE","JUE","VIE","SAB"],
  "intervalo_slot_min": 30, "duracion_entrega_default_min": 90
}
```

- `operacion.reloj_termico_minutos` = **150**.
- `operacion.alerta_temprana_minutos_antes` = 60.
- `operacion.por_vencer_critico_minutos_antes` = 30.
- `operacion.alerta_viaje_sin_llegada_minutos` = 90.
- `operacion.hora_limite_cierre_caja` = 19:00.
- `operacion.politica_redondeo_viajes` = PARCIAL.
- `operacion.merma_cemento_pct_alerta` = **NULL**.
- `inventario.conteo` = `{"fecha": null, "estado": "PENDIENTE"}`.

### 6.5 Recetas (factores por m³)

| Resistencia | Cemento sacos/m³ | Arena m³/m³ | Ripio m³/m³ | Agua L/m³ | Retardante L/m³ | Precio m³ |
|---|---:|---:|---:|---:|---:|---:|
| FC-180 | 6,5 | 0,56 | 0,68 | 190 | 1,0 | 108,00 |
| FC-210 | 7,5 | 0,52 | 0,68 | 185 | 1,2 | 118,00 |
| FC-240 | 8,5 | 0,50 | 0,66 | 182 | 1,4 | 126,00 |
| FC-280 | 9,5 | 0,48 | 0,65 | 178 | 1,6 | 136,00 |
| FC-350 | 11,0 | 0,45 | 0,62 | 172 | 2,0 | 158,00 |

> Los precios son **ficticios** y se marcarán `PROVISIONAL` hasta que Julio dé
> los reales. No usarlos como margen.

### 6.6 Materiales y stock

| Código | Unidad | Stock declarado | Mínimo | Costo unitario | Último conteo |
|---|---|---:|---:|---:|---|
| CEMENTO | saco | 3.500 | 500 | 8,20 | NULL |
| ARENA | m³ | 450 | 80 | 14,00 | NULL |
| RIPIO | m³ | 550 | 100 | 16,50 | NULL |
| RETARDANTE | litro | 600 | 100 | 3,80 | NULL |
| AGUA | litro | NULL | NULL | NULL | NULL |

**Hallazgo crítico:** el kardex registra **-3.092 sacos de cemento** (49 viajes
del 9-nov) y **-507,2 L de retardante**, pero `materials.stock_actual` sigue en
3.500/600 porque **no hay conteo físico**. La vista `v_stock_proyectado`
devuelve `consumo_teorico_acumulado = 0` y `stock_proyectado = stock_actual`
cuando `ultimo_levantamiento_at` es NULL. Consecuencia:
- Si el stock declarado es el inicial, el stock real sería **408 sacos**
  (3.500 − 3.092), **por debajo del mínimo de 500 → CRÍTICO**.
- Si el stock declarado es el actual, el kardex no se ha aplicado y el consumo
  está duplicado.
- El tablero **no puede mostrar 3.500 como verdad**: debe mostrar las dos
  lecturas y la inconsistencia.

### 6.7 Movimientos de inventario

| Día | Material | Tipo | Movs | Cantidad |
|---|---|---|---:|---:|
| 2026-11-08 | CEMENTO | TEORICO | 2 | -120,000 |
| 2026-11-08 | RETARDANTE | TEORICO | 2 | -19,200 |
| 2026-11-09 | AGUA | TEORICO | 49 | -71.104,000 |
| 2026-11-09 | ARENA | TEORICO | 49 | -198,120 |
| 2026-11-09 | CEMENTO | TEORICO | 49 | -3.092,000 |
| 2026-11-09 | RETARDANTE | TEORICO | 49 | -507,200 |
| 2026-11-09 | RIPIO | TEORICO | 49 | -260,720 |

No hay `COMPRA`, `REAL`, `AJUSTE` ni `ANULACION`.

### 6.8 Viajes y ejecución

| Día | Viajes | m³ |
|---|---:|---:|
| 2026-11-08 | 2 | 16 |
| 2026-11-09 | 49 | 388 |

- **49 de 51 viajes están `PROGRAMADO`** y sin `mixer_codigo`.
- Solo **2 viajes** tienen `salida_planta`; **1** tiene `llegada_obra_chofer` y
  `confirmacion_whatsapp_cliente`.
- No hay `dosificado_planta` en ninguno.
- Por eso hoy no se puede medir tiempo de ciclo real ni utilización real: hay
  plan, no ejecución.

### 6.9 Cobranza

| Documento | Cliente | Monto | Vencimiento | Estado |
|---|---|---:|---|---|
| FACTURA PRUEBA-0001 | Ing. Reyes | 43.424,00 | NULL | SIN_VENCIMIENTO |
| ORDEN 55 | Ing. Reyes | 43.424,00 | NULL | SIN_VENCIMIENTO |
| ORDEN 56 | Ing. Reyes | 9.448,40 | NULL | SIN_VENCIMIENTO |
| ORDEN 57 | Cliente Prueba Hito 3 | 2.171,20 | NULL | SIN_VENCIMIENTO |
| ORDEN 9 | Debug | 0,00 | NULL | SIN_VENCIMIENTO |

- La factura `PRUEBA-0001` documenta la **misma** orden #55: el total documental
  **98.467,60** está duplicado. El saldo real es **55.043,60**.
- `payments = 0` → no hay DSO, ni comportamiento, ni cobrado.
- `v_cliente_saldo` cuenta **todas** las órdenes no anuladas como facturadas,
  incluidas las `CONFIRMADA` no entregadas. Es una decisión pendiente.

### 6.10 Clientes

| Cliente | Provincia | Cupo | RUC | Teléfono |
|---|---|---:|---|---|
| Ing. Reyes (prueba Hito 1) | Orellana | NULL | NULL | NULL |
| Cliente Prueba Hito 3 | Sucumbíos | NULL | NULL | sí |
| Debug | NULL | NULL | NULL | sí |
| 3 leads de WhatsApp | NULL | NULL | NULL | sí |

---

## 7. El panel actual y su componente visual

- Un solo HTML: `services/core-api/app/web/templates/panel.html`.
- Componente **Ventanilla** (el que hay que reutilizar):

```html
<div class="card sec-ventanilla">
  <div>
    <span class="sec-eyebrow">VENTANILLA</span>
    <h2>¿Qué vas a registrar hoy?</h2>
    <p class="small muted">...</p>
  </div>
  <div class="sec-acciones">
    <button class="sec-accion primary">...</button>  <!-- amarillo sólido -->
    <button class="sec-accion">...</button>
  </div>
</div>
```

- La clase `.primary` es la ventana activa: fondo amarillo, texto oscuro, flecha.
- El dashboard actual tiene: `metric-grid` (3 tarjetas), `dash-tabs` (3 tarjetas
  con tinte ámbar, **no** amarillo sólido), `dash-subnavs`, `dash-panel`,
  `dash-subview`, `inv-grid`, `cob-cubos`, `hero-kpis`.
- **Bug conocido:** la vista `agenda` no existe; el calendario quedó suelto como
  hijo directo del panel y se ve siempre. El botón "Agenda" no hace nada.
- El resumen superior actual (captura 4) tiene: Mercado El Coca, Ventas 2026,
  Dónde vendes. Debe ser el contenido por defecto de la ventana 1 y **cambiar**
  al cambiar de ventana.

---

## 8. Hallazgos que el diseño debe resolver (no ignorar)

| # | Hallazgo | Evidencia | Implicación |
|---|---|---|---|
| H1 | Flota inconsistente | 3 mixers 8/8/7 en settings vs 2×7 de Dirección | `CONFIGURACION_INCONSISTENTE`; no calcular 42 ni 69 |
| H2 | Capacidad no configurada | falta `viajes_max_dia`, `produccion_m3_hora` | `NO_CONFIGURADO`; no estimar del histórico |
| H3 | 404 m³ vendidos sin agendar | 4 órdenes, `dispatch_schedule` = 0 | Mostrar "vendido sin agenda"; no fingir ocupación |
| H4 | Cobranza duplicada | 55.043,60 + 43.424,00 = 98.467,60 | Documento único por venta; aging real |
| H5 | Sin fechas de vencimiento | 5/5 `SIN_VENCIMIENTO` | No hay aging; capturar fecha en formularios |
| H6 | Sin pagos | `payments` = 0 | No hay DSO ni comportamiento; mostrar vacío |
| H7 | Sin conteo físico | `ultimo_levantamiento_at` NULL | Stock declarado ≠ stock real; mostrar inconsistencia |
| H8 | Kardex no aplicado a stock | 3.092 sacos consumidos, stock sigue 3.500 | Si el stock es inicial, quedan 408 < mínimo 500 |
| H9 | Viajes sin ejecución | 49/51 `PROGRAMADO`, 0 dosificados | No hay tiempos reales; la ocupación es plan |
| H10 | Precios ficticios | `concrete_recipes.precio_m3` | No calcular margen como si fuera real |
| H11 | Agenda rota | falta `data-sub-view="agenda"` | Corregir la estructura, no solo el botón |
| H12 | Cubos en $0 | 3 de 4 cubos sin monto | Mostrar el motivo, no un gráfico vacío |

---

## 9. Lo que Julio necesita ver (modelo de decisión)

### 9.1 Ventana 1 — Operación y capacidad (por defecto, amarilla)

**Pregunta:** ¿cuánto puedo producir y entregar hoy, y qué puedo prometer?
**Decisión:** aceptar, reprogramar o rechazar un pedido; asignar mixers.
**Dueño:** Julio / jefe de planta.
**Umbral:** < 70 % libre, 70–90 % ajustado, > 90 % saturado (configurable).
**Acción:** si saturado, no prometer más sin reprogramar.

Datos:
- `capacidad_dia = min(capacidad_flota, capacidad_planta, capacidad_jornada)`.
- `capacidad_flota = Σ(activos × capacidad_m3 × viajes_max_dia)` → 42 con 2×7×3.
- `comprometido_hoy`, `comprometido_semana`, `comprometido_mes`.
- `vendido_sin_agendar = Σ m³ órdenes confirmadas − Σ m³ agendados`.
- `dias_de_capacidad_vendida = m3_vendidos / capacidad_dia` → 404/42 = 9,6.
- Serie de despacho por día (14 días) desde `v_dispatch_timeline`.
- Mezcla por resistencia desde `orders`.
- Estado de mixers (en ruta, minutos, semáforo térmico).
- Cuello de botella y supuestos.

### 9.2 Ventana 2 — Inventario vs ventas

**Pregunta:** ¿el material alcanza para lo que ya vendí?
**Decisión:** comprar, reprogramar, priorizar obra o cambiar receta.
**Dueño:** Julio / bodega.
**Umbral:** cobertura < 100 % = falta; 100–120 % = ajustado; > 120 % = holgado.

Datos:
- Explosión MRP: `Σ(orden.m3 × receta.factor)` por material.
- Stock declarado, stock físico, stock proyectado, mínimo.
- Cobertura = stock / necesario; días de cobertura = stock / consumo diario.
- Material crítico (el de menor cobertura).
- `m3_comprometidos` vs `m3_fc210_disponibles` (466,7).
- Serie de consumo (kardex) para contexto.

### 9.3 Ventana 3 — Inventario por fechas

**Pregunta:** ¿cómo se movió el material y cuándo fue el último conteo?
**Decisión:** ajustar compras, detectar merma, ordenar conteo.
**Dueño:** bodega.
**Umbral:** merma > umbral configurado; conteo vencido > 30 días.

Datos:
- Serie diaria por material (14/30 días) desde `inventory_movements`.
- Movimientos por tipo; compras y recepciones.
- Último conteo por material o `SIN_CONTEO`.
- Stock proyectado `v_stock_proyectado`.
- Merma teórico vs real cuando exista `cemento_sacos_real`.

### 9.4 Ventana 4 — Cobranza y caja

**Pregunta:** ¿cuánto tengo por cobrar, qué está vencido y cuánto efectivo puedo
recuperar esta semana?
**Decisión:** a quién llamar, qué cobrar primero, a quién no fiar.
**Dueño:** Julio / secretaría / contadora.
**Umbral:** mora > días configurados; cupo excedido; caja < compromisos.

Datos:
- Documento único por venta (factura si existe, si no orden).
- Aging: `VENCIDA >90`, `61–90`, `31–60`, `1–30`, `POR_VENCER_7`,
  `POR_VENCER_30`, `CORRIENTE`, `SIN_VENCIMIENTO`.
- `caja_esperada_7d` = Σ documentos con vencimiento ≤ 7 días.
- `caja_esperada_30d` = Σ documentos con vencimiento ≤ 30 días.
- `cobrado_30d` = Σ `payments` últimos 30 días.
- `DSO = saldo / ventas × días` (solo si hay pagos y ventas).
- `cupo_excedido` = saldo > `credit_limit_usd`.
- Presets: Urgencia 7 días, Mora, Clientes grandes, Sin vencimiento, Cupo
  excedido.
- Sin fechas: mostrar `SIN_FECHAS_CAPTURADAS`; sin pagos: `SIN_PAGOS`.

---

## 10. Modelo de capacidad (lo que Carbon debe cerrar)

### 10.1 Configuración propuesta

```json
{
  "mixers": [
    {"codigo":"MIXER-01","placa":"OAA-1024","capacidad_m3":7.0,
     "viajes_max_dia":3,"activo":true,"chofer_asignado":"Pedro Andy"},
    {"codigo":"MIXER-02","placa":"OAA-1088","capacidad_m3":7.0,
     "viajes_max_dia":3,"activo":true,"chofer_asignado":"Carlos Grefa"}
  ],
  "plantas": {
    "PLANTA-COCA": {"produccion_m3_hora": null, "horas_efectivas_dia": null}
  },
  "supuestos": {
    "ciclo_viaje_min": 110,
    "fuente": "Direccion 2026-11-13"
  }
}
```

### 10.2 Fórmula

```
cap_flota   = Σ(activo × capacidad_m3 × viajes_max_dia)
cap_planta  = produccion_m3_hora × horas_efectivas_dia
cap_jornada = (hora_cierre − hora_apertura) / ciclo_viaje_min
              × capacidad_promedio_viaje × mixers_activos
capacidad   = min(cap_flota, cap_planta, cap_jornada)
ocupacion   = comprometido / capacidad
```

### 10.3 Reglas

- La capacidad es una **restricción declarada**, no un promedio histórico.
- Si falta un término: `NO_CONFIGURADO` con el término faltante.
- Si la flota configurada no coincide con la declarada: `CONFIGURACION_INCONSISTENTE`.
- El supuesto (`ciclo_viaje_min`, `fuente`) se muestra al lado del número.
- `42` se calcula; no se guarda.
- La skill que lee datos devuelve la capacidad con `configurado: true|false` y
  los supuestos. Gato puede decir "no hay capacidad configurada", no "unos 42".

---

## 11. Modelo de cobranza (lo que Carbon debe cerrar)

### 11.1 Regla de documento único

```
Si existe factura para la orden → el documento cobrable es la FACTURA.
Si no existe → el documento cobrable es la ORDEN.
Nunca se suman los dos.
```

Decisión pendiente: ¿la orden `CONFIRMADA` no entregada es cobrable? Criterio
propuesto: **no**; se cobra lo entregado/facturado. La orden sin entrega es
compromiso, no cuenta por cobrar.

### 11.2 Aging y caja

- Cubos por documento único.
- `caja_esperada_7d/30d` por fecha de vencimiento.
- `cobrado_30d` por `payments` (cuando existan).
- `DSO` solo con pagos y ventas; si no, `null`.
- No ponderar por "probabilidad de pago" sin historial: sería inventar.

### 11.3 Filtros de decisión

| Preset | Pregunta | Filtro |
|---|---|---|
| Urgencia 7 días | ¿qué entra de caja esta semana? | vencido + por vencer 7 |
| Mora | ¿a quién llamo? | dias_mora > umbral, orden monto |
| Clientes grandes | ¿dónde está el riesgo? | top 5 saldo y % total |
| Sin vencimiento | ¿qué no puedo priorizar? | `SIN_VENCIMIENTO` |
| Cupo excedido | ¿a quién no fío? | saldo > cupo |

---

## 12. Rúbrica adversarial (lo que el árbitro debe castigar)

1. **Número sin fuente.** Cualquier cifra que no apunte a tabla/vista/consulta.
2. **Cero disfrazado.** Un cubo en $0 sin explicar que no hay fechas.
3. **Capacidad inventada.** Estimar 42 sin configurar o ignorar la flota real.
4. **Doble conteo.** Sumar orden + factura de la misma venta.
5. **Cálculo en el navegador.** Sumas o promedios en JS.
6. **Filtro de vanidad.** Un filtro que no cambia una decisión.
7. **Placeholder.** `TODO`, `lorem`, "ejemplo", "aproximado".
8. **Gráfico decorativo.** Ilustración sin serie real.
9. **Supuesto oculto.** `ciclo_viaje_min` sin mostrarlo.
10. **Romper tests/contratos.** Cambiar IDs o textos sin actualizar asserts.
11. **Ignorar el vacío.** No mostrar `NO_CONFIGURADO`/`SIN_FECHAS`.
12. **Confundir hecho, proyección y meta.** Mezclarlos en una misma barra.
13. **Recomendar sin dueño.** Una acción que nadie puede ejecutar.
14. **Métrica sin umbral.** "Cobertura 60 %" sin decir si es bueno o malo.

### 12.1 Evidencia que debe acompañar la entrega

- Reconciliación: total del tablero = suma de documentos únicos (55.043,60).
- Capacidad: 2×7×3 = 42; con 404 m³ → 9,6 días.
- Cobertura: cemento 3.212 necesarios vs stock (mostrar las dos lecturas).
- Casos vacíos: sin fechas, sin pagos, sin conteo, sin agenda.
- `pytest` en verde y `auditar_skills.py` en verde.

---

## 13. Preguntas que Carbon hará (respuestas ya verificadas)

| Pregunta | Respuesta |
|---|---|
| ¿Cuántos mixers hay? | Configuración: 3 (8/8/7). Dirección: 2 de 7. **No resuelto**; usar `CONFIGURACION_INCONSISTENTE`. |
| ¿Capacidad diaria? | 2×7×3 = 42 m³/día según Dirección; configurable. |
| ¿Hay `viajes_max_dia`? | No. Falta agregarlo a `flota.mixers`. |
| ¿Capacidad de planta? | No configurada. |
| ¿Horario? | 07:00–18:00, lunes a sábado. |
| ¿Cuántas órdenes? | 4, todas `CONFIRMADA`, 404 m³. |
| ¿Hay agenda? | `dispatch_schedule` = 0. |
| ¿Hay pagos? | 0. |
| ¿Hay conteo físico? | No; `ultimo_levantamiento_at` NULL. |
| ¿Hay fechas de vencimiento? | No; 5/5 `SIN_VENCIMIENTO`. |
| ¿El saldo real? | 55.043,60; el documental 98.467,60 está duplicado. |
| ¿Qué es `FIADO`? | `orders.forma_pago`; no genera `COBRO` inicial. |
| ¿Cómo se calcula el saldo? | `v_cliente_saldo` (facturado − cobrado). |
| ¿Los precios son reales? | No, ficticios; se marcarán `PROVISIONAL`. |
| ¿Se puede migrar? | No para capacidad: va en `system_settings`. |
| ¿Qué tests hay? | 386 al último cierre. |
| ¿Hay CDN/build? | No; SVG propio y Poppins local. |
| ¿Quién decide? | Julio; secretaría/contadora para cobranza; bodega para conteo. |

---

## 14. Preguntas que faltan de verdad (para Julio)

1. **Flota real:** ¿2 camiones de 7 m³? ¿El tercero de la semilla existe o está
   inactivo?
2. **Capacidad de planta:** m³/hora y horas efectivas.
3. **¿La orden confirmada sin entregar es cobrable?** Criterio propuesto: no.
4. **Fecha de entrega comprometida:** ¿en la orden o solo en agenda?
5. **Días de crédito por cliente** y umbral de mora para "urgencia".
6. **Umbral de ocupación** para el semáforo (propuesto 70/90).
7. **Stock físico actual:** ¿3.500 sacos es el stock de hoy o el inicial? ¿Los
   249 movimientos son consumos reales?
8. **Precios reales** por resistencia y fecha de vigencia.
9. **Merma aceptable** (%) y política de conteo.
10. **¿La factura PRUEBA-0001 se elimina o se marca ficticia?** (Hoy duplica la
    orden #55).

Mientras no haya respuesta: `NULL`, `NO_CONFIGURADO` o
`CONFIGURACION_INCONSISTENTE`, y el tablero lo dice.

---

## 15. Lo que NO debe hacer Carbon

- No inventar capacidades, precios, plazos, teléfonos, stock ni umbrales.
- No proponer filtros genéricos de BI (fecha/planta/estado) sin dueño ni
  decisión.
- No usar librerías de gráficos, CDN ni build.
- No calcular en JavaScript.
- No tocar migraciones aplicadas.
- No cambiar contratos, IDs ni textos que los tests verifican sin actualizarlos.
- No convertir el tablero en un chatbot ni en un reporte PDF.
- No prometer "predicción con IA" donde no hay datos.
- No ignorar los hallazgos H1–H12.
- No entregar la primera versión.

---

## 16. Criterio de aceptación del entregable de Carbon

El plan se acepta si, y solo si:

1. Cada una de las 4 ventanas tiene pregunta, decisión, dueño, umbral y acción.
2. Cada filtro tiene semántica, fuente, grano, valores y combinaciones.
3. Cada métrica tiene contrato (fórmula, fuente, nulos, frescura).
4. La capacidad se declara y nunca se estima; los estados de falta son
   explícitos.
5. La cobranza usa documento único y no duplica orden + factura.
6. Hay al menos 5 presets de cobranza con SQL lógico.
7. La UI respeta el banner Ventanilla, el amarillo sólido y el orden pedido.
8. Hay plan de pruebas con casos vacíos, nulos y doble conteo.
9. Hay auditoría adversarial con objeciones y respuestas.
10. Hay secuencia de implementación con criterios de cierre verificables.
11. No hay placeholders ni datos inventados.
12. Se puede implementar sin reabrir decisiones cerradas ni romper los 386
    tests.

---

## 17. Anexo: archivos del repo que Carbon puede pedir

| Archivo | Para qué |
|---|---|
| `docs/PDR_v4.0.txt` | alcance, módulos, contrato JSON |
| `docs/BASE_DE_DATOS.md` | tablas, vistas, migraciones, responsables |
| `docs/DASHBOARD_JULIO_ANALISIS.md` | hipótesis, variables, DB, plan previo |
| `docs/DASHBOARD_OPERATIVO.md` | diseño visual de las 4 ventanas |
| `docs/CATALOGO_CONSULTAS.json` | consultas nombradas y estados |
| `docs/SKILLS_PILARES_HORMINOR.md` | estándar de skills |
| `docs/CARBON_ARRANQUE.md` | formato de entrega de skills |
| `docs/00_DECISIONES_PENDIENTES.md` | datos que faltan del cliente |
| `services/core-api/app/m4_dashboard/operativo.py` | endpoints actuales |
| `services/core-api/app/web/templates/panel.html` | UI actual |
| `services/core-api/tests/test_v72_dashboard_operativo.py` | tests del tablero |

---

## 18. Resumen para pegar al final del prompt

```text
Con todo lo anterior, entrega el plan profundo del dashboard de Julio:
- 4 ventanas con decisión, dueño, umbral y acción.
- Taxonomía completa de filtros y presets (especialmente cobranza).
- Contratos de métrica y de endpoints.
- Configuración de capacidad en Superadmin y fórmula con cuello de botella.
- Regla de documento único y aging real.
- UI con banner Ventanilla, activa en amarillo, primero y encima de los gráficos.
- Pruebas, reconciliación y auditoría adversarial.
Sin placeholders. Sin datos inventados. Sin primera versión.
```
