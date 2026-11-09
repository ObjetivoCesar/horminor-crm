# Modelo de datos — Módulo 0

Motor: PostgreSQL 15. Esquema base en `db/migrations/001_init.sql`.
Migraciones aplicadas automáticamente al arrancar la API (idempotentes, con
`pg_advisory_lock` y registro en `schema_migrations`).

> **Actualización 2026-11-09 — Custodio v4.3.** Al esquema base se suman 14
> tablas contables/operativas y 3 vistas nuevas. El detalle de creación,
> responsables y flujo de ingresos está en `docs/BASE_DE_DATOS.md`; las
> migraciones son `063_custodio_core.sql` y `064_custodio_views.sql`.

## Tablas

| # | Tabla | Para qué | Notas |
|---|---|---|---|
| 1 | `system_settings` | Parámetros maestros (`key` → `value` JSONB) | Ningún precio, teléfono, receta ni umbral vive en el código |
| 2 | `plants` | Plantas fija y móvil | Agregar planta = `INSERT`, sin deploy |
| 3 | `concrete_recipes` | Dosificación por m³ y resistencia | `confirmado = false` ⇒ el motor se niega a calcular |
| 4 | `clients` | Clientes y prospectos | `estado = PROSPECTO` para los leads del Gate #4; `telefono_whatsapp` único |
| 5 | `orders` | Orden de hormigón | `total` generado (`volumen × precio`, NULL si no hay precio); `total_con_iva` es el bruto con IVA |
| 6 | `mixer_dispatches` | Viajes de mixer | `tracking_payload` JSONB es el contrato; columnas proyectadas por trigger |
| 7 | `materials` | Stock real por material | `stock_actual` NULL = inventario no levantado (no se asume 0); `ultimo_levantamiento_at` NULL = sin fecha de conteo |
| 8 | `inventory_movements` | Kardex | `TEORICO` (receta) / `REAL` (bodega) / `COMPRA` / `AJUSTE` / `ANULACION`, cantidad con signo |
| 9 | `payments` | Cobros y caja chica | `COBRO` / `GASTO_CAJA_CHICA` / `GASTO_BANCARIO` / `REEMBOLSO_CAJA`; `FIADO` es crédito, no efectivo |
| 10 | `cash_closures` | Cierre diario | `snapshot` JSONB inmutable + totales por método |
| 11 | `market_benchmarks` | Demanda regional (As #1) | `anio` NULL porque el PDR no lo fija |
| 12 | `error_logs` | Errores y eventos | Alimenta el chequeo de errores del Centinela |
| 13 | `processed_requests` | Idempotencia del Gate | `request_id` + hash del payload; un reintento devuelve la misma respuesta |
| 14 | `accounting_accounts` | Plan de cuentas | 26 cuentas con `code`, `slug`, tipo, naturaleza y `is_system_locked` |
| 15 | `suppliers` | Proveedores | Identificación única cuando no es NULL |
| 16 | `purchases` | Compras | Subtotal, IVA, total, pagado y saldo generado; no permite sobrepago |
| 17 | `purchase_items` | Ítems de compra | `subtotal_item = round(cantidad × costo, 2)` |
| 18 | `goods_receipts` | Recepciones | Enlaza el ítem comprado con el movimiento de inventario |
| 19 | `supplier_payments` | Pagos a proveedores | Método y bolsa; borrado lógico |
| 20 | `fixed_assets` | Activos fijos | Residual ≤ costo y depreciación ≤ base depreciable |
| 21 | `depreciation_runs` | Depreciación mensual | Una corrida por activo y período |
| 22 | `financial_liabilities` | Préstamos bancarios | Entidad + número de operación únicos |
| 23 | `loan_payments` | Pagos de préstamos | Capital + interés; saldo snapshot |
| 24 | `ledger_entries` | Libro mayor | Partida doble inmutable: solo INSERT; correcciones por reversa |
| 25 | `audit_witness_log` | Testigo forense | Inmutable; guarda valor anterior, nuevo y motivo |
| 26 | `approval_requests` | Aprobaciones de Julio | Cola `PENDING` / `APPROVED` / `REJECTED` |

## Vistas de contrato

### `v_dispatch_timeline`
Aplana el `tracking_payload` de cada viaje: cliente, resistencia, planta,
sellos forenses (`dosificado_planta`, `salida_planta`, `limite_termico_fraguado`,
`llegada_obra_chofer`, `confirmacion_whatsapp_cliente`), veredictos del juez
binario y consumo de materiales. Es lo que consume el Panel Central del Módulo 3.

### `v_cliente_saldo`
Total comprado ($ y m³), cobrado, fiado, **saldo pendiente** y **saldo a
favor**. Conserva las 8 columnas originales y agrega `ruc`, `credit_limit_usd`
y `saldo_a_favor` al final. `total_facturado` usa
`COALESCE(total_con_iva, total)` y `total_cobrado` solo suma `COBRO` no
`FIADO` y no borrado. Alimenta la ficha financiera del panel de secretaría.

### `v_inventario`
Stock con estado: `OK`, `CRITICO`, `SIN_UMBRAL`, `SIN_LEVANTAR`.

### `v_stock_proyectado`
Stock físico + consumos `TEORICO` posteriores al último conteo. `ANULACION` se
suma en valor absoluto. Sin `ultimo_levantamiento_at` no aplica teóricos y
marca `SIN_FECHA_CONTEO`.

### `v_balance_general`
Saldo por cuenta contable según su naturaleza (`DEBIT`/`CREDIT`). Respeta
`merged_into_id`: la cuenta fusionada suma en la destino sin reescribir el
ledger.

### `v_estado_resultados`
Ingresos y gastos agrupados por mes y cuenta. El servicio filtra el rango de
fechas y suma los períodos.

## Contrato `tracking_payload`

Definido en el PDR §5.2. Se construye en `app/services/ordenes.py` y se expone
tal cual en `mixer_dispatches.tracking_payload`. Campos que el Módulo 1 irá
completando por WhatsApp:

```json
{
  "dispatch_id": "uuid",
  "viaje_numero": 2,
  "total_viajes_orden": 40,
  "mixer_codigo": "MIXER-01",
  "chofer_nombre": "Pedro",
  "volumen_m3": 8.0,
  "resistencia": "FC-210",
  "estado_actual": "PROGRAMADO",
  "juez_binario_jeb": {
    "despacho_validado": false,
    "recepcion_cliente_validada": false,
    "incidencia_detectada": false
  },
  "tiempos_forenses": {
    "dosificado_planta": null,
    "salida_planta": null,
    "limite_termico_fraguado": null,
    "llegada_obra_chofer": null,
    "confirmacion_whatsapp_cliente": null
  },
  "consumo_materiales": {
    "cemento_sacos_teorico": 60.0,
    "cemento_sacos_real": null,
    "retardante_litros": 9.6
  },
  "evidencias_bunny_cdn": [],
  "mensaje_literal_cliente": null,
  "whatsapp_msg_id_forense": null
}
```

Campos extra que agregamos (compatibles, no rompen el contrato del PDR):
`consumo_materiales.arena_m3`, `ripio_m3`, `agua_litros`, `provisional` y
`campos_faltantes`.

## Invariantes

1. `mixer_dispatches.viaje_numero` y `volumen_m3` siempre coinciden con el JSONB.
2. La suma de `volumen_m3` de los viajes generados es exactamente el volumen
   pedido, salvo política `ultimo_completo` (que reporta `excedente_m3`).
3. Un movimiento `TEORICO` nunca modifica `materials.stock_actual`.
4. `orders.total` es NULL si no hay precio: no se inventa facturación en cero.
5. `cash_closures.fecha` es única: un cierre por día.
6. `orders.total_con_iva = total + iva_monto`; si `aplica_iva = false`, el IVA
   es cero. Los históricos sin IVA confirmado usan `total_con_iva = total`.
7. `ledger_entries` y `audit_witness_log` son inmutables: solo INSERT. Una
   corrección se hace con reversa (`is_reversal = true`) y un testigo nuevo.
8. `processed_requests` es idempotente por `request_id` + hash; el mismo
   payload devuelve la misma respuesta y un hash distinto se rechaza.
9. `v_stock_proyectado` no aplica consumos teóricos si
   `materials.ultimo_levantamiento_at` es NULL: marca `SIN_FECHA_CONTEO`.
