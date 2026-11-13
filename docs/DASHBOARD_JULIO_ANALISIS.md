# Dashboard de Julio — análisis profundo, capacidad y cobranza

> **Estado:** diseño y razonamiento. No hay código nuevo en esta sesión.
> **Fecha:** 2026-11-13.
> **Origen:** instrucción de Dirección del 2026-11-13 09:35, recuperada de la
> sesión anterior, más la nota de capacidad del 2026-11-13 (2 camiones de 7 m³,
> 3 viajes/día, 42 m³/día, configurable desde Superadmin).
>
> Este documento reemplaza el plan superficial de `DASHBOARD_OPERATIVO.md` §5b.
> El diseño visual se mantiene; lo que cambia es el **modelo mental**: el
> tablero no es un reporte, es un tablero de decisiones con restricciones.

---

## 0. La hipótesis

**HIPÓTESIS H1.** Julio puede decidir su día en menos de dos minutos si el
tablero le responde tres preguntas en este orden:

1. **¿Cuánto puedo producir y entregar hoy?** → capacidad real (flota × viajes ×
   m³, limitada por planta y jornada) contra lo ya comprometido.
2. **¿El material alcanza para lo que ya vendí?** → explosión de materiales de
   las órdenes confirmadas contra el stock proyectado, con cobertura y cuello de
   botella.
3. **¿Cuánto efectivo puedo recuperar y cuándo?** → documentos por cobrar por
   antigüedad, cliente y fecha, separando lo vencido de lo que aún no vence.

El resto —mixers, agenda, movimientos, clientes— es **drill-down** de esas tres.
Si el tablero no cambia una decisión de Julio, no debería estar arriba.

**Hipótesis de implementación H2.** No hace falta una migración para la
capacidad. Es un **parámetro de negocio** y, por la decisión 12 del proyecto,
todo parámetro vive en `system_settings` y se edita desde el Superadmin. La
capacidad se **declara**, no se estima con el histórico.

**Hipótesis de riesgo H3.** Los dos números que hoy parecen más sólidos
(capacidad y cobranza) son justamente los que están mal definidos:
- La flota configurada no coincide con la flota real (3 mixers de 8/8/7 en la
  semilla contra 2 camiones de 7 m³ que declara Dirección).
- El total documental por cobrar **duplica** la orden #55 porque la factura
  `PRUEBA-0001` documenta la misma venta: 55.043,60 + 43.424,00 = 98.467,60.
  El saldo real es 55.043,60. Si el tablero muestra 98.467,60 como "por cobrar",
  miente.

La primera fase del trabajo no es dibujar: es **reconciliar** y **declarar**.

---

## 1. Qué haría aquí un profesional de primer nivel que no estás pidiendo

No es una lista de deseos: cada punto cambia el diseño.

1. **Diseño guiado por decisiones, no por datos.** Cada ventana tendría dueño,
   decisión, umbral y acción. "Ocupación 87%" no es un dato: es "no prometas
   más de 5 m³ hoy sin reprogramar".
2. **Contrato de métrica antes del gráfico.** Nombre, fórmula, grano, fuente,
   política de nulos, frescura y dueño. Sin eso, dos pantallas contradicen.
3. **Modelo de restricciones, no de totales.** La capacidad es
   `min(flota, planta, jornada, demanda)`; el tablero debe decir cuál restringe.
4. **Unidad económica por m³ y por viaje.** Costo directo (materiales + receta),
   margen de contribución, punto de equilibrio. Hoy no existe y el precio es
   manual.
5. **Ciclo de conversión de efectivo (CCC).** DIO + DSO − DPO. Conecta
   inventario, cobranza y compras en un solo número.
6. **Gestión por excepción.** "Qué cambió desde ayer", "qué está en riesgo",
   "qué vence esta semana". No un tablero estático que hay que leer completo.
7. **Separar hecho, proyección y meta.** Un hecho (viaje ejecutado), una
   proyección (capacidad futura) y una meta (42 m³/día) se ven distinto y no se
   mezclan en la misma barra.
8. **Calidad del dato instrumentada.** Fechas de vencimiento faltantes, conteos
   físicos faltantes, pedidos sin agendar. El tablero muestra la deuda, no la
   esconde con un cero.
9. **Reconciliación con el documento fuente.** Cada cifra debe cerrar contra
   orden, guía, factura, extracto o conteo. Si no cierra, se muestra la
   diferencia.
10. **Pensar en el incentivo.** Un tablero de capacidad puede empujar a vender
    de más; uno de cobranza, a cobrar solo lo fácil. Las métricas deben castigar
    la venta que no cabe y la cobranza que quema al cliente.
11. **Modo "sombra".** Antes de confiar, correr el tablero en paralelo con la
    operación real y medir el error: capacidad prometida vs viajes reales;
    cobranza proyectada vs cobrado.
12. **Auditoría por diseño.** Cada número con `fuente`, `consultado`, `filtros`
    y consulta nombrada. Ya existe la envoltura; hay que usarla en todas.

---

## 2. La materia prima real (raw), no lo digerido

El punto de partida no son las tarjetas ni las vistas. Es **el flujo de eventos
con marca de tiempo + la configuración de restricciones**:

```
Compromiso        →  Plan           →  Ejecución        →  Material        →  Dinero
orders            dispatch_schedule   mixer_dispatches    inventory_movements  payments
(fecha, m³,       (fecha, hora,       (dosificado,        (tipo, cantidad,     (fecha,
 resistencia,      mixer, duración)    salida, llegada,    costo, orden,        método,
 precio, cupo)                        confirmación)       viaje)               monto, bolsa)
```

Todo lo demás —saldo, cobertura, ocupación, aging— es una **proyección** de esos
cinco flujos. La regla de trabajo:

> Si un número del tablero no se puede reconstruir desde eventos y configuración,
> es una opinión, no un dato.

Y la restricción también es materia prima: `system_settings.flota.mixers`,
`system_settings.agenda.parametros`, `system_settings.operacion.*`. La capacidad
**no se infiere del histórico**: se declara y se compara. El histórico sirve
para medir el error de la declaración, no para reemplazarla.

---

## 3. Métodos y herramientas específicos

| Dominio | Método | Herramienta concreta en este repo |
|---|---|---|
| Capacidad | `min(flota, planta, jornada)`, utilización, cuello de botella, Little's Law | SQL sobre `system_settings`, `dispatch_schedule`, `v_dispatch_timeline`; `Decimal` en Python |
| Tiempo de ciclo | Marcas `dosificado → salida → llegada → confirmación` | `v_dispatch_timeline`; percentiles con `percentile_cont` |
| Inventario | Explosión MRP: `m³ vendido × factor de receta`; punto de reorden; stock de seguridad | `orders` × `concrete_recipes` × `materials`; `v_stock_proyectado` |
| Compras | Lead time, recepción parcial, costo promedio ponderado | `purchases`, `purchase_items`, `goods_receipts`, kardex |
| Cobranza | Aging FIFO, DSO, CEI, promesas de pago, recuperación esperada | `v_cobranza_documentos`, `v_cliente_saldo`, `payments` |
| Caja | Flujo 13 semanas, waterfall de efectivo, brecha de caja | `payments`, `bank_accounts`, `financial_liabilities` |
| Margen | Contribución por m³, punto de equilibrio, sensibilidad | `concrete_recipes`, `materials.costo_unitario`, `system_settings` |
| Datos | Contrato de métrica, event sourcing, SCD2 de precios/cupos, `Decimal` | PostgreSQL, asyncpg, vistas de lectura, migraciones idempotentes |
| Pruebas | Unitarias de fórmula, golden files, propiedades, reconciliación | `pytest`, fixtures contra clon con `ROLLBACK` |
| Visual | Bullet chart contra meta, small multiples, waterfall, Gantt, heatmap de aging | SVG propio del panel, sin CDN ni build |
| Producto | Jobs-to-be-done, jerarquía de métricas, revelación progresiva | `sec-ventanilla` + submenús + detalle |

**Lo que NO se usa:** un LLM para sumar, inferir capacidad o decidir urgencia.
Gato puede **leer** la ficha; la aritmética es SQL + `Decimal`.

---

## 4. Qué demuestra que el resultado es correcto (aparte de nosotros)

1. **El documento fuente.** Orden firmada, guía de despacho, factura, extracto
   bancario, conteo físico. La cifra del tablero debe cerrar contra el papel.
2. **El Custodio.** El libro mayor de doble entrada debe cuadrar; el testigo
   registra cada corrección. Si el tablero y el ledger discrepan, gana el ledger.
3. **Recomputación independiente.** La misma cifra por dos caminos: SQL de la
   vista contra un script Python con `Decimal`, al centavo. Diferencia ≠ 0 →
   no se publica.
4. **El operador.** Julio, la secretaria y bodega reconocen el número y actúan.
   Un tablero que no cambia una decisión no está validado.
5. **La prueba de capacidad en sombra.** Capacidad declarada vs viajes reales
   durante 2 semanas. Si el error es > 10 %, el supuesto está mal, no el tablero.
6. **La prueba de cobranza.** Suma de documentos únicos vs saldo de
   `v_cliente_saldo`. Hoy: 98.467,60 documental contra 55.043,60 real. Esa
   diferencia es la prueba de que el modelo actual está mal.
7. **Los tests.** Casos vacíos, nulos, sobrecapacidad, doble conteo, mes sin
   datos, cliente sin cupo. Cada uno con salida esperada escrita.
8. **La auditoría de la skill.** `scripts/auditar_skills.py` debe seguir en
   verde; la consulta de capacidad entra al catálogo con fuente y contrato.

---

## 5. Las variables de la empresa

Leyenda de estado: **T** = la tenemos y se usa · **P** = la tenemos pero
incompleta o sin capturar · **F** = falta · **D** = la tiene el cliente y no está
en el sistema.

### 5.1 Comercial y demanda

| Variable | Estado | Dónde vive / dónde debería |
|---|---|---|
| Cliente, RUC, teléfono, provincia, ciudad, obra | T/P | `clients` (RUC y ciudad casi todos `NULL`) |
| Cupo de crédito | P | `clients.credit_limit_usd` (vacío) + `finanzas.tope_credito_auto` |
| Días de crédito por cliente | F | nueva columna o setting por cliente |
| Orden: número, fecha, resistencia, m³, precio, IVA, forma de pago, estado | T | `orders` |
| Precio por resistencia | T/P | `concrete_recipes.precio_m3` (ficticio, sin `precio_estado`) |
| Descuentos, recargos, extras | F | migración 080 de cotizaciones (`cotizacion_extras`) |
| Cotizaciones y pipeline | F | tabla `cotizaciones` (080) |
| Fecha de entrega comprometida | F | falta en `orders`; hoy solo `dispatch_schedule` |
| Fecha de vencimiento de cobro | P | `orders.fecha_vencimiento` existe, formularios no la capturan |
| Demanda de mercado por provincia | T/D | `market_benchmarks` (Orellana 120.000, Sucumbíos 95.000) |
| Estacionalidad / obra petrolera | D | no está; se pregunta |
| Competencia y precio de mercado | D | `market_benchmarks.precio_promedio_m3` vacío |

### 5.2 Capacidad y operación

| Variable | Estado | Dónde vive / dónde debería |
|---|---|---|
| Mixers: código, placa, capacidad m³, activo, chofer | T/P | `system_settings.flota.mixers` (3 unidades 8/8/7) |
| **Viajes máximos por mixer por día** | **F** | **nuevo campo en `flota.mixers`** |
| **Capacidad de planta m³/hora** | **F** | **nuevo en `flota_y_operacion` o `plants`** |
| **Horas efectivas por turno** | P | `agenda.parametros` (07:00–18:00, lun–sáb) |
| Ciclo de viaje (min) por obra/zona | F/P | derivable de `v_dispatch_timeline`; default 90 min |
| Jornada real y horas extra | F | `jornada_eventos` (081) |
| Mantenimiento y paradas | F | no está |
| Distancia/tiempo por obra | F | no está; se puede derivar de marcas |
| Combustible y peajes | F | no está |
| Agenda de entregas | T/F | `dispatch_schedule` (0 filas hoy) |
| Ejecución de viajes y tiempos | T | `mixer_dispatches`, `v_dispatch_timeline` |
| Semáforo térmico (150 min) | T | `system_settings.operacion.reloj_termico_minutos` |
| Incidencias y reclamos | T | `tracking_payload.juez_binario_jeb`, chat |
| Capacidad comprometida vs disponible | F | cálculo nuevo (backend) |

### 5.3 Inventario y compras

| Variable | Estado | Dónde vive / dónde debería |
|---|---|---|
| Materiales, unidad, stock, mínimo, costo | T/P | `materials` (5; agua sin stock) |
| Receta por m³ (cemento, arena, ripio, agua, retardante) | T | `concrete_recipes` (5 confirmadas) |
| Movimientos de kardex | T | `inventory_movements` (249, todos `TEORICO`) |
| Stock proyectado | T/P | `v_stock_proyectado` (sin conteo → `SIN_FECHA_CONTEO`) |
| Último conteo físico | F | `materials.ultimo_levantamiento_at` vacío |
| Merma real (teórico vs real) | P | `tracking_payload.consumo_materiales.cemento_sacos_real` vacío |
| Umbral de merma | F | `operacion.merma_cemento_pct_alerta` en `NULL` |
| Compras, proveedores, recepción | T/F | `purchases`, `purchase_items`, `suppliers` (1), `goods_receipts` (0) |
| Lead time de proveedor | F | no está |
| Stock de seguridad / punto de reorden | F | solo `stock_minimo` |
| Lotes, calidad, humedad de áridos | F | no está |

### 5.4 Finanzas y cobranza

| Variable | Estado | Dónde vive / dónde debería |
|---|---|---|
| Documentos por cobrar | T/P | `v_cobranza_documentos` (5; **duplica la orden #55**) |
| Saldo por cliente | T/P | `v_cliente_saldo` (cuenta órdenes `CONFIRMADA` como facturadas) |
| Pagos: fecha, método, monto, bolsa, cuenta, anticipo | T | `payments` (0 registros) |
| Cobrado vs facturado | T | `payments`, `v_cliente_saldo` |
| Bancos y saldos | P | `bank_accounts` (3), `saldo_informado` vacío |
| Caja chica y cierre | T/F | `cash_closures` (0), `payments` |
| Deudas y préstamos | F | `financial_liabilities` (0), `loan_payments` (0) |
| WACC, impuesto, inflación, DSCR | F | `finanzas.parametros_contables` (todo `NULL`) |
| Días de mora y comportamiento de pago | F | derivable cuando haya pagos |
| Promesas de pago | F | no está |
| Costo financiero de la mora | F | no está |
| Notas de crédito / reembolsos | T | regla `finanzas.regla_reembolso` |
| Flujo de caja proyectado | F | cálculo nuevo (13 semanas) |

### 5.5 Personas, calidad y riesgo

| Variable | Estado | Dónde vive / dónde debería |
|---|---|---|
| Usuarios y roles | T | `panel_users_acl` (5), `whatsapp.staff` |
| Salarios, anticipos, horas extra | F | 081 (`contratos`, `anticipos_salario`, `jornada_eventos`) |
| Productividad por chofer/mixer | P | derivable de viajes y tiempos |
| Incidencias por viaje | T | `tracking_payload` + Juez Jeb |
| Cumplimiento térmico | T | `limite_termico_fraguado` vs confirmación |
| Riesgo de crédito | P | cupo + mora (cuando existan fechas) |
| Riesgo operativo | F | capacidad, mantenimiento, clima, vías |
| Contratos de suministro y trabajo | F | docs aprobados, tablas 081 |

---

## 6. Distribución de la base: dónde se guarda cada cosa

### 6.1 Tablas de eventos (la verdad)

| Tabla | Grano | Campos clave | Estado hoy |
|---|---|---|---|
| `orders` | una orden | `numero`, `cliente_id`, `resistencia`, `volumen_m3`, `precio_m3`, `total_con_iva`, `forma_pago`, `estado`, `fecha_vencimiento` | 4 filas |
| `dispatch_schedule` | un slot agendado | `fecha_entrega`, `hora_inicio`, `duracion_estimada_min`, `mixer_codigo`, `volumen_m3`, `estado` | 0 filas |
| `mixer_dispatches` | un viaje | `order_id`, `viaje_numero`, `volumen_m3`, `estado_actual`, `tracking_payload` | 51 filas |
| `inventory_movements` | un movimiento | `material_id`, `tipo`, `cantidad`, `order_id`, `dispatch_id`, `costo_unitario_snapshot` | 249 filas |
| `payments` | un pago/cobro | `fecha`, `tipo_movimiento`, `metodo`, `monto`, `bolsa`, `account_id`, `es_anticipo` | 0 filas |
| `ledger_entries` | un asiento | `cuenta`, `debe`, `haber`, `source_type`, `source_id` | 0 filas |
| `cash_closures` | un cierre | `fecha`, `efectivo_sistema`, `efectivo_contado`, `diferencia` | 0 filas |
| `client_invoices` | una factura | `numero`, `orden_id`, `fecha`, `total`, `fecha_vencimiento`, `es_ficticia` | 1 fila |

### 6.2 Vistas de lectura (proyecciones)

| Vista | Responde | Riesgo detectado |
|---|---|---|
| `v_dispatch_timeline` | viaje con tiempos y consumo | base sólida para capacidad |
| `v_stock_proyectado` | stock físico + consumo post-conteo | sin conteo todo es `SIN_FECHA_CONTEO` |
| `v_cliente_saldo` | facturado, cobrado, saldo | cuenta órdenes `CONFIRMADA` no entregadas |
| `v_cobranza_documentos` | aging por documento | **duplica orden + factura de la misma venta** |
| `v_balance_general` | balance contable | sin asientos, vacío |
| `v_estado_resultados` | resultados | sin asientos, vacío |

### 6.3 Configuración (los parámetros que se editan en Superadmin)

| Clave | Qué controla | Sección |
|---|---|---|
| `flota.mixers` | capacidad, placas, choferes, activos | `flota_y_operacion` |
| `agenda.parametros` | horario, días, slot, duración | `flota_y_operacion` |
| `operacion.*` | reloj térmico, alertas, cierre de caja | `flota_y_operacion` |
| `bodega.umbrales_por_planta` | stock, mínimo y costo por planta | `bodega_y_umbrales` |
| `mercado.valorizacion` | precio de valorización y período | `finanzas_y_ases_gerenciales` |
| `finanzas.*` | IVA, simulador, cupo, reembolso | `finanzas_y_ases_gerenciales` |
| `empresa.bot_publico` | RUC, horario, cuentas, zonas | `empresa_bot_publico` |
| `precios.hormigon` | precios públicos | `formulas_y_precios` |

### 6.4 Lo que falta crear (propuesta, no migración aplicada)

| Necesidad | Dónde | Por qué no una migración ya |
|---|---|---|
| `viajes_max_dia` por mixer | `flota.mixers` (JSON) | es parámetro, decisión 12 |
| `produccion_m3_hora` y `horas_efectivas` por planta | `flota_y_operacion` | parámetro, no esquema |
| `ciclo_viaje_min` por zona | setting | parámetro |
| Fecha de entrega comprometida | `orders.fecha_entrega` | requiere migración nueva (080/081) |
| Promesa de pago | tabla nueva o `payments` | decisión de negocio |
| `dias_credito` por cliente | `clients` | decisión de negocio |
| Cotizaciones y contratos | 080/081 ya planificadas | no adelantar |

---

## 7. Modelo de capacidad instalada

### 7.1 Fórmula

```
capacidad_flota_dia   = Σ (mixer.activo × mixer.capacidad_m3 × mixer.viajes_max_dia)
capacidad_planta_dia  = planta.produccion_m3_hora × planta.horas_efectivas_dia
capacidad_jornada_dia = (hora_cierre − hora_apertura) / ciclo_viaje_min
                        × capacidad_promedio_por_viaje × mixers_activos
capacidad_dia         = min(capacidad_flota_dia, capacidad_planta_dia,
                            capacidad_jornada_dia)
ocupacion_pct         = comprometido_m3 / capacidad_dia × 100
cuello_botella        = el término que da el mínimo
```

Con el dato de Dirección: `2 × 7 × 3 = 42 m³/día`. Si la planta no declara
capacidad, **no se inventa**: `capacidad_planta_dia = null` y el tablero dice
`PLANTA_NO_CONFIGURADA`. El mínimo se calcula solo con las restricciones
declaradas y se marca el supuesto.

### 7.2 La discrepancia que hay que resolver antes de mostrar

La semilla dice **3 mixers** (8, 8 y 7 m³, los tres activos). Dirección dice
**2 camiones de 7 m³**. No se corrige por código: se corrige en Superadmin con
el dato de Julio. Mientras no se corrija, el tablero debe mostrar
`CONFIGURACION_INCONSISTENTE` y no un 42 ni un 69.

Esto es una regla de la skill:

> La capacidad es una **restricción declarada**. Si falta o es inconsistente,
> se devuelve `NO_CONFIGURADO` / `CONFIGURACION_INCONSISTENTE` con la fuente.
> Nunca se estima desde el histórico ni desde un promedio.

### 7.3 Configuración propuesta (JSON de `flota_y_operacion`)

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
  "supuestos": {"ciclo_viaje_min": 110, "fuente": "Direccion 2026-11-13"}
}
```

`capacidad_dia = 42` se **calcula**, no se guarda. Si Julio cambia un camión o un
viaje, el tablero cambia sin migración ni reinicio.

### 7.4 Qué muestra el tablero

- **Hoy:** `comprometido_hoy / 42 m³` y `viajes_comprometidos / 6`.
- **Semana y mes:** capacidad × días laborables vs agenda y órdenes.
- **Vendido sin agendar:** `Σ m³ de órdenes confirmadas − Σ m³ agendados`. Hoy
  son **404 m³ sin agenda**: el tablero debe decirlo, no esconderlo.
- **Días de capacidad vendida:** `404 / 42 = 9,6 días` de planta.
- **Cuello de botella:** flota, planta o jornada; si planta no está configurada,
  se dice.
- **Semáforo:** < 70 % libre, 70–90 % ajustado, > 90 % saturado. El umbral se
  configura; no se inventa.

### 7.5 La skill que lee estos datos

Agregar al catálogo una consulta `capacidad_operativa` (primero `PROPUESTA`,
luego `IMPLEMENTADA` cuando exista endpoint y test):

- **Fuente:** `system_settings`, `dispatch_schedule`, `orders`,
  `v_dispatch_timeline`.
- **Devuelve:** capacidad por restricción, capacidad efectiva, cuello de botella,
  comprometido, ocupación, vendido sin agendar, supuestos y `configurado`.
- **Regla dura:** si falta configuración, `NO_CONFIGURADO`; nunca un número
  estimado. Gato puede decir "no hay capacidad configurada", no "unos 42 m³".

---

## 8. Modelo de cobranza y urgencia financiera

### 8.1 Primero, reconciliar (bloqueante)

Hoy `v_cobranza_documentos` suma órdenes y facturas. La factura `PRUEBA-0001`
documenta la orden #55, así que su monto se cuenta dos veces:

```
Órdenes:   43.424,00 + 9.448,40 + 2.171,20 + 0,00 = 55.043,60
Factura:   43.424,00
Total vista: 98.467,60   ← no es una cuenta por cobrar real
Saldo real (`v_cliente_saldo`): 55.043,60
```

Regla propuesta: **un documento cobrable por venta**. Si existe factura, la
factura es el documento y la orden no se suma; si no existe, la orden es el
documento. Se implementa en la vista o en el endpoint, con test de no-duplicación.
Decisión de Julio/contadora: ¿la orden confirmada pero no entregada ya es
cobrable? Mi criterio: **no**; se cobra lo entregado/facturado. La orden sin
entrega es compromiso, no cuenta por cobrar.

### 8.2 Cubos y filtros (el "juego" que pide Julio)

**Cubos de antigüedad** (por documento único):
`VENCIDA > 90`, `VENCIDA 61–90`, `VENCIDA 31–60`, `VENCIDA 1–30`,
`POR_VENCER_7`, `POR_VENCER_30`, `CORRIENTE`, `SIN_VENCIMIENTO`.

**Filtros de decisión (no de vanidad):**

| Preset | Qué responde | Filtro |
|---|---|---|
| **Urgencia 7 días** | ¿qué entra de caja esta semana? | vencido + por vencer 7 |
| **Mora** | ¿a quién hay que llamar? | días de mora > umbral, ordenado por monto |
| **Clientes grandes** | ¿dónde está concentrado el riesgo? | top 5 por saldo y % del total |
| **Sin vencimiento** | ¿qué documento no puedo priorizar? | `SIN_VENCIMIENTO` |
| **Cupo excedido** | ¿a quién no se le fía más? | saldo > `credit_limit_usd` |

**Drill-down:** cliente, provincia, forma de pago, tipo de documento, monto,
antigüedad, última promesa. Cada filtro se aplica en backend; el navegador no
suma.

**Recuperación de efectivo:**

```
caja_esperada_7d  = Σ documentos con vencimiento ≤ 7 días
caja_esperada_30d = Σ documentos con vencimiento ≤ 30 días
cobrado_30d       = Σ payments de los últimos 30 días
DSO               = (saldo / ventas del período) × días del período
```

No se pondera por "probabilidad de pago" hasta que exista historial. Se muestra
el monto y la fecha; la probabilidad sería un dato inventado.

### 8.3 Lo que falta para que funcione

1. Capturar `fecha_vencimiento` en los formularios de orden y factura (hoy todo
   cae en `SIN_VENCIMIENTO`).
2. Regla de imputación pago → documento (hoy `payments.order_id`).
3. Decidir si la orden `CONFIRMADA` sin entrega es cobrable.
4. Corregir el doble conteo orden/factura.
5. Registrar pagos reales: hoy `payments = 0`, así que no hay DSO ni
   comportamiento.

---

## 9. Contrato de los endpoints (lo que se implementa)

Todos con la envoltura existente: `fuente`, `consultado`, `filtros`, `datos`,
`vacio`. Sin `LIMIT` silencioso. Montos como texto decimal.

### 9.1 `GET /api/v1/dashboard/operacion`

```json
{
  "fuente": ["system_settings", "dispatch_schedule", "orders", "v_dispatch_timeline"],
  "consultado": "2026-11-13T11:00:00-05:00",
  "filtros": {"desde": "2026-11-13", "hasta": "2026-11-13", "planta": null},
  "datos": {
    "capacidad": {
      "flota_m3_dia": "42",
      "planta_m3_dia": null,
      "jornada_m3_dia": null,
      "efectiva_m3_dia": "42",
      "cuello_botella": "FLOTA",
      "supuestos": {"ciclo_viaje_min": 110, "viajes_max_dia": 3},
      "configurado": true
    },
    "comprometido": {"hoy_m3": "0", "semana_m3": "0", "mes_m3": "404"},
    "sin_agendar": {"ordenes": 4, "m3": "404"},
    "serie_dias": [{"fecha": "2026-11-13", "viajes": 0, "m3": "0"}],
    "por_resistencia": [{"resistencia": "FC-210", "m3": "352", "ordenes": 3}],
    "mixers": [{"codigo": "MIXER-01", "estado": "SIN_LECTURA", "viajes": 0}]
  },
  "vacio": null
}
```

### 9.2 `GET /api/v1/dashboard/inventario`

Agregar a lo actual:

```json
"datos": {
  "materiales": [{"codigo":"CEMENTO","stock":"3500","stock_minimo":"500",
                  "consumo_30d":"3212","necesario_ventas":"3212",
                  "cobertura_pct":"109","dias_cobertura":"9.6",
                  "estado":"AJUSTADO"}],
  "ventas": {"m3_comprometidos":"404","m3_fc210_disponibles":"466.7"},
  "serie_consumo": [{"fecha":"2026-11-09","CEMENTO":"-2640","ARENA":"-183"}]
}
```

### 9.3 `GET /api/v1/dashboard/cobranza`

Agregar:

```json
"datos": {
  "documentos": [{"tipo":"ORDEN","numero":"55","cliente":"...",
                  "fecha":"2026-11-09","vencimiento":null,
                  "monto":"43424.00","dias_mora":null,
                  "estado":"SIN_VENCIMIENTO"}],
  "aging": [{"cubo":"VENCIDA_31_60","monto":"0","documentos":0}],
  "caja": {"esperada_7d":"0","esperada_30d":"0","cobrado_30d":"0"},
  "dso": null,
  "total_documental_unico": "55043.60",
  "duplicados_excluidos": 1
}
```

---

## 10. La respuesta reescrita (lo que se implementa)

### 10.1 Diseño de pantalla

```
┌─ BANNER sec-ventanilla (primero, encima de todo) ─────────────────────┐
│ TABLERO DE JULIO                                                      │
│ ¿Qué necesitas decidir hoy?                                           │
│ [Operación y capacidad] [Inventario vs ventas] [Inventario por fechas] [Cobranza y caja]
│        AMARILLO              tarjeta               tarjeta              tarjeta
└───────────────────────────────────────────────────────────────────────┘
        ↓ submenú de la ventana activa (pills, patrón Ventanilla)
┌─ 3 tarjetas KPI que CAMBIAN con la ventana ──────────────────────────┐
│ Capacidad hoy · Ventas del mes · Mixers                              │
│ Cobertura · m³ comprometidos · material crítico                      │
│ Movimientos · consumo · último conteo                                │
│ Saldo real · vencido · por vencer 7d                                 │
└───────────────────────────────────────────────────────────────────────┘
┌─ Gráficos SVG con datos de la base ──────────────────────────────────┐
│ bullet capacidad · barras por día · cobertura por material · aging    │
└───────────────────────────────────────────────────────────────────────┘
┌─ Tabla del día / documentos / movimientos ───────────────────────────┐
└───────────────────────────────────────────────────────────────────────┘
```

### 10.2 Orden de implementación

| Fase | Qué | Criterio de cierre |
|---|---|---|
| **C0** | Corregir flota en Superadmin (2×7×3) y agregar `viajes_max_dia` | `capacidad_dia = 42` calculada; test de fórmula |
| **C1** | `GET /operacion` con capacidad, comprometido, sin agendar y serie | JSON con envoltura; caso `NO_CONFIGURADO` |
| **C2** | Extender `/inventario` con explosión MRP y cobertura | cemento 3.212 vs 3.500 = 109 %; test Decimal |
| **C3** | Corregir doble conteo orden/factura y aging | total único 55.043,60; test de no-duplicación |
| **C4** | Extender `/cobranza` con documentos, cubos y caja esperada | `caja_esperada_7d` y `DSO` nulo si no hay pagos |
| **C5** | Banner Ventanilla + 4 ventanas + KPIs que cambian + SVG | 4 ventanas, activa amarilla, sin errores de consola |
| **C6** | Submenús y tablas de detalle; arreglar Agenda rota | Agenda es una vista real, no un bloque suelto |
| **C7** | Catálogo/skill: `capacidad_operativa` | `auditar_skills.py` en verde; regla `NO_CONFIGURADO` |
| **C8** | Pruebas y evidencia | `pytest` en verde; captura; bitácora |

### 10.3 Lo que NO se hace

- No se inventa la capacidad de planta ni el ciclo de viaje: se declaran.
- No se usa el histórico para estimar capacidad.
- No se muestra un gráfico si la serie está vacía: se muestra el motivo.
- No se suma en JavaScript: todo en backend con `Decimal`.
- No se toca una migración aplicada; la capacidad va en `system_settings`.
- No se decide por Julio el dato de flota: se corrige con él.

### 10.4 Decisiones que necesito de Julio/contadora

1. **Flota real:** ¿2 camiones de 7 m³ (y el tercero no existe o está inactivo)?
2. **Capacidad de planta:** m³/hora y horas efectivas.
3. **¿La orden confirmada sin entregar es cobrable?** Mi criterio: no.
4. **Fecha de entrega comprometida:** ¿se captura en la orden o solo en agenda?
5. **Días de crédito por cliente** y umbral de mora para "urgencia".
6. **Umbral de ocupación** para el semáforo (propongo 70/90, configurable).

---

## 11. Resumen ejecutivo

- El tablero actual no está mal por feo: está mal porque **no tiene modelo**.
  Capacidad sin restricciones, inventario sin ventas, cobranza con documentos
  duplicados.
- La capacidad es una **restricción declarada** (42 m³/día con 2×7×3), no un
  promedio histórico. Va en Superadmin y la skill la lee con `NO_CONFIGURADO`
  cuando falta.
- La cobranza necesita **un documento único por venta** y fechas de vencimiento
  antes de dibujar urgencias. Hoy el 98.467,60 es un espejismo; el saldo real es
  55.043,60.
- El orden de valor es: **reconciliar → declarar restricciones → calcular en
  backend → dibujar**. Al revés se construye un tablero bonito que miente.
- Lo que probará que funciona no es la captura: es que Julio decida distinto y
  que la cifra cierre contra la orden, la guía, la factura o el banco.
