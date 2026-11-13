# Dashboard operativo — Ocupación, Inventario, Cobranza (v6.20)

> **Estado:** diseño cerrado; implementación pendiente (fase 2).
> Reemplaza los “Filtros de obras” del panel actual.
> Toda cifra sale de la base. Si falta el dato, se muestra el vacío explícito, no
> un cero ni un promedio inventado.

## 1. Qué se elimina

- La tarjeta **“Filtros de obras”** (planta, resistencia, pago). No filtraba:
  solo `f-planta` llegaba al backend y el resto filtraba tarjetas en JavaScript.
- El cálculo de totales en el navegador sobre `/orders?limit=50`. Con más de 50
  órdenes cualquier suma es falsa.
- El período oculto fijo en 2026.

## 2. Qué se mantiene

La **cuarta captura** (mercado, ventas, provincias) queda como resumen anual
**comprimido** arriba de las pestañas. Es un reporte de año, no un tablero del
día, y así debe leerse.

## 3. Las cuatro ventanas (C5/C6)

El banner `sec-ventanilla` es el primer bloque del dashboard; la ventana activa
se pinta en **amarillo sólido** (`.sec-accion.primary`). Al cambiar de ventana
mutan el submenú, las 3 tarjetas KPI y los gráficos.

| Ventana | Pregunta | Fuente | Estado |
|---|---|---|---|
| **Operación y capacidad** (por defecto) | ¿cuánto puedo producir y entregar hoy? | `system_settings`, `dispatch_schedule`, `v_dispatch_timeline` | real; capacidad pendiente de confirmar |
| **Inventario vs ventas** | ¿alcanza el material para lo vendido? | `orders` × `concrete_recipes`, `materials`, kardex | triple lectura; sin conteo físico |
| **Inventario por fechas** | ¿cómo se movió el material y cuándo se contó? | `inventory_movements` | real; sin `REAL` ni `COMPRA` |
| **Cobranza y caja** | ¿qué está vencido y cuánto entra? | `orders`, `client_invoices`, `payments`, `v_cliente_saldo` | documento único; sin fechas ni pagos |

### 3.1 Operación y capacidad

- Capacidad declarada `min(flota, planta, jornada)`; no se estima.
- Comprometido hoy/semana/mes, cola sin plan y sin despachar.
- Serie por día: ejecutado vs programado; mezcla por resistencia.
- Submenú: `Resumen`, `Mixers`, `Agenda`.

### 3.2 Inventario vs ventas

- Explosión MRP: m³ vendidos × receta.
- Tres lecturas: declarada, kardex y corregida por asimetría.
- Cobertura por material, material crítico y m³ FC-210 disponibles.
- Submenú: `Cobertura`, `Detalle`.

### 3.3 Inventario por fechas

- Consumo diario por material (kardex), en su unidad nativa.
- Último conteo o `SIN CONTEO`; detector de asimetrías.
- Submenú: `Consumo`, `Conteos`.

### 3.4 Cobranza y caja

- Documento único: factura real reemplaza la orden; ficticia excluida.
- Aging de 8 cubos y bandeja de documentos.
- Exigibilidad: confirmado/facturado, con salida, sin salir.
- Presets: Todos, Urgencia 7 días, Mora, Clientes grandes, Sin vencimiento,
  Cupo excedido, Listo para cobrar.
- Submenú: `Resumen`, `Clientes`.

## 4. Contrato de los endpoints

Cada endpoint devuelve la misma envoltura, para que la UI no adivine:

```json
{
  "fuente": "v_cobranza_documentos",
  "consultado": "2026-11-13T10:20:00-05:00",
  "filtros": {"desde": "2026-11-01", "hasta": "2026-11-30"},
  "datos": [],
  "vacio": {
    "motivo": "SIN_FECHAS_CAPTURADAS",
    "mensaje": "Ningun documento tiene fecha de vencimiento."
  }
}
```

Reglas:

- `fuente` es la tabla o vista real, no una etiqueta inventada.
- `vacio` es `null` cuando hay datos. Nunca se devuelve una lista vacía sin
  explicar por qué.
- `consultado` es la hora del servidor: sirve para saber si el dato está viejo.
- Sin `LIMIT` silencioso: si se pagina, se pagina explícito.

Rutas: `GET /api/v1/dashboard/operacion`, `/inventario`, `/cobranza`.

Estado al 2026-11-13 (C0–C3):

- `/operacion`: **implementado**. Lee la capacidad declarada de
  `system_settings`, calcula `min(flota, planta, jornada)`, devuelve
  `CONFIGURACION_INCONSISTENTE` con la semilla actual y separa
  `sin_plan_m3` (404) de `sin_despachar_m3` (388).
- `/inventario`: **extendido** con explosión MRP, lectura declarada, lectura
  neta registrada y lectura corregida por la asimetría del 8-nov.
- `/cobranza`: **extendido** con documento único, exclusión de la factura
  ficticia, aging de 8 cubos, desglose de exigibilidad y presets.
- Capacidad en Superadmin: `viajes_max_dia` y `planta_asignada` por mixer,
  `capacidad_plantas`, `supuestos_capacidad` y `umbrales_ocupacion` en
  `system_settings` (sin migración).
- Evidencia: `.agents/evidencias/dashboard_c0_c3_2026-11-13.txt`.

## 5. Reglas duras

1. **Nada de cálculo de negocio en JavaScript.** El backend suma con `Decimal`.
2. **Vacío explícito.** `SIN_VENCIMIENTO`, `SIN_LEVANTAR` y `NO_CONFIGURADO` son
   respuestas válidas; el cero no.
3. **La pestaña por defecto es Ocupación** porque es la única con datos reales.
4. **No se mezcla pipeline con ingreso.** Cotizaciones abiertas y excedente
   despachado van como indicadores, no como ventas.
5. **Sin datos de negocio inventados.** Ni un precio, ni una tarifa, ni un
   umbral que Julio no haya entregado.

## 5b. Diseño aprobado por Dirección (recuperado 2026-11-13 09:35)

> Esta sección existe porque la instrucción se dio en una sesión anterior y se
> perdió. No se vuelve a decidir desde cero: se implementa esto.
>
> **Modelo completo (capacidad, variables, base y cobranza):**
> `docs/DASHBOARD_JULIO_ANALISIS.md`. Esta sección queda como resumen visual;
> el análisis profundo manda cuando haya contradicción.

**Reglas de diseño (todas las páginas):**

1. El banner de ventanas usa el componente `sec-ventanilla` + `sec-acciones` de
   Secretaría/Superadmin. La ventana activa va con **fondo amarillo sólido**
   (`.sec-accion.primary`), texto oscuro y flecha.
2. Ese banner es **lo primero** del dashboard y va **encima de los gráficos**.
3. Cada ventana tiene su **submenú** (mismo patrón de pills que Ventanilla), no
   filtros sueltos. El patrón "botón que abre ventana desplegable" de Carpetas
   de Clientes es la referencia para los detalles.
4. Se eliminan los filtros de obra (planta, resistencia, pago): no respondían
   una pregunta de Julio.

**Las cuatro ventanas (preguntas de Julio, no dimensiones del negocio):**

| # | Ventana | Pregunta | Por defecto |
|---|---|---|---|
| 1 | Ocupación de mixers | ¿qué está haciendo mi planta hoy y qué puedo prometer? | **sí (amarilla)** |
| 2 | Inventario vs ventas | ¿el material alcanza para lo que ya vendí? | |
| 3 | Inventario por fechas | ¿cómo se movió el material y cuándo fue el último conteo? | |
| 4 | Cuentas por cobrar | ¿cuánto tengo por cobrar y cuánto efectivo puedo disponer? | |

**Contenido:**

1. Las **3 tarjetas del resumen** (Mercado El Coca, Ventas, Dónde vendes) son el
   contenido por defecto de la ventana 1 y **cambian** con la ventana activa:
   - Ocupación → Mercado / Ventas / Dónde vendes.
   - Inventario vs ventas → m³ comprometidos / cobertura / material crítico.
   - Inventario por fechas → movimientos / consumo / último conteo.
   - Cuentas por cobrar → saldo real / facturado / clientes con saldo.
2. Debajo de las tarjetas, **gráficos dibujados con datos de la base**, no
   ilustración decorativa. Sin CDN ni librería: SVG propio del panel.
3. Si la serie está vacía, se muestra el vacío con su motivo; nunca un gráfico
   de adorno ni un cero que parezca dato.

**Gráficos aprobados (fuente real):**

| Ventana | Gráfico | Fuente |
|---|---|---|
| Ocupación | Despacho por día (m³ y viajes, 14 días) | `v_dispatch_timeline` |
| Ocupación | Mezcla por resistencia (m³) | `orders` + `concrete_recipes` |
| Ocupación | Estado de mixers y minutos en ruta | `v_dispatch_timeline`, KPI operación |
| Inventario vs ventas | Cobertura por material: stock vs consumo comprometido | `orders` × `concrete_recipes` × `materials` |
| Inventario vs ventas | m³ comprometidos vs m³ FC-210 disponibles | `orders`, `v_stock_proyectado` |
| Inventario por fechas | Consumo diario por material (14 días) | `inventory_movements` |
| Inventario por fechas | Último conteo por material o vacío explícito | `materials.ultimo_levantamiento_at` |
| Cuentas por cobrar | Saldo por cliente (barras) | `v_cliente_saldo` |
| Cuentas por cobrar | Antigüedad por documento (cubos) | `v_cobranza_documentos` |

## 6. Fases

| Fase | Qué | Criterio |
|---|---|---|
| D1 | Migración 079: vencimiento y vista de cobranza | **hecho** (2026-11-13) |
| D2 | Endpoints `inventario` y `cobranza` | **hecho**: envoltura completa, tests y vacío explícito |
| D3 | Ventanas y submenús en el panel | **hecho**: banner Ventanilla, 4 ventanas, activa en amarillo sólido, sin “Filtros de obras” |
| D4 | `GET /dashboard/operacion` + timeline de mixers | **hecho**: capacidad declarada, cola sin plan/despacho, serie por fecha del viaje |
| D5 | Indicadores de cotizaciones y excedente | Pipeline y fuga de margen visibles |
