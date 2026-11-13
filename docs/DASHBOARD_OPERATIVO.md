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

## 3. Las tres pestañas

| Pestaña | Pregunta que responde | Fuente | Estado del dato |
|---|---|---|---|
| **Ocupación** (por defecto) | ¿qué está haciendo la planta hoy y qué puedo prometer? | `mixer_dispatches`, `dispatch_schedule`, capacidad | **real desde el día uno** |
| **Inventario** | ¿alcanza el material para lo comprometido? | `v_stock_proyectado`, kardex, conteo | bloqueado hasta el conteo físico |
| **Cobranza** | ¿qué está vencido y qué vence esta semana? | `v_cobranza_documentos`, `v_cliente_saldo` | listo el esqueleto; faltan fechas |

Cada pestaña tiene su **submenú propio** (mismo patrón visual que Ventanilla,
activo en ámbar). No hay filtros globales.

### 3.1 Ocupación

- Timeline de mixers del día: en planta, cargando, en ruta, en obra, volviendo.
- Capacidad comprometida vs. disponible (m³ y viajes).
- Tabla del día: orden, cliente, obra, volumen pactado, despachado, estado.
- Barra **“horas fuera de jornada”** cuando exista `jornada_eventos` (fase 081).
- Submenú: `Hoy`, `Semana`, `Mixers`, `Calendario`.

### 3.2 Inventario

- Stock por material: **CEMENTO, ARENA, RIPIO, RETARDANTE**. El agua no es stock;
  sigue en la receta y en el costo.
- Submenú: `Stock`, `Por fechas`, `Kardex`, `Compras`.
- “Inventario por fechas” es un filtro **dentro** de Inventario, no una pestaña.
- Sin conteo físico: cada material muestra `SIN_LEVANTAR` o `SIN_FECHA_CONTEO`,
  nunca un número estimado presentado como real.

### 3.3 Cobranza

- Cubos de `v_cobranza_documentos`: `SIN_VENCIMIENTO`, `VENCIDA`,
  `POR_VENCER_7`, `CORRIENTE`.
- Saldo real por cliente desde `v_cliente_saldo`.
- Submenú: `Vencidos`, `Por vencer`, `Clientes`, `Documentos`.
- Límite escrito: `monto_documento` es el total del documento, **no** el saldo
  pendiente. El aging por factura espera la regla de imputación pago → documento.

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

Estado al 2026-11-13:

- `/inventario` y `/cobranza`: **implementados** en
  `services/core-api/app/m4_dashboard/operativo.py`, con tests.
- `/operacion`: pendiente. La pestaña Ocupación usa por ahora las órdenes y los
  KPIs existentes.

## 5. Reglas duras

1. **Nada de cálculo de negocio en JavaScript.** El backend suma con `Decimal`.
2. **Vacío explícito.** `SIN_VENCIMIENTO`, `SIN_LEVANTAR` y `NO_CONFIGURADO` son
   respuestas válidas; el cero no.
3. **La pestaña por defecto es Ocupación** porque es la única con datos reales.
4. **No se mezcla pipeline con ingreso.** Cotizaciones abiertas y excedente
   despachado van como indicadores, no como ventas.
5. **Sin datos de negocio inventados.** Ni un precio, ni una tarifa, ni un
   umbral que Julio no haya entregado.

## 6. Fases

| Fase | Qué | Criterio |
|---|---|---|
| D1 | Migración 079: vencimiento y vista de cobranza | **hecho** (2026-11-13) |
| D2 | Endpoints `inventario` y `cobranza` | **hecho**: envoltura completa, tests y vacío explícito |
| D3 | Pestañas y submenús en el panel | **hecho**: tres pestañas, activa en ámbar, sin “Filtros de obras” |
| D4 | `GET /dashboard/operacion` + timeline de mixers | Timeline y tabla del día desde la base |
| D5 | Indicadores de cotizaciones y excedente | Pipeline y fuga de margen visibles |
