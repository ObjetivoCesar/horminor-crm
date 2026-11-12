# Modelo de datos — Módulo 0

Motor: PostgreSQL 15. Esquema base en `db/migrations/001_init.sql`.
Migraciones aplicadas automáticamente al arrancar la API (idempotentes, con
`pg_advisory_lock` y registro en `schema_migrations`).

> **Actualización 2026-11-12 — v6.13 (facturas internas).** Se suma
> `client_invoices` (`073_facturas_internas.sql`): factura interna adjunta al
> cliente como PDF o foto, con montos tomados de la orden o cargados por el
> usuario. `es_ficticia` marca los documentos de prueba. No es facturación
> electrónica del SRI.
>
> **Actualización 2026-11-12 — v6.13.1 (memoria de Gato).** Se suma
> `gato_turnos` (`074_gato_memoria.sql`): cada pregunta/respuesta de Gato con
> su `conversacion_id` y actor. El backend reconstruye los últimos 8 turnos
> para resolver "esa factura" o "descárgala".

> **Actualización 2026-11-12 — v6.11 (bancos).** Se suma `bank_accounts`
> (`072_bancos_detalle.sql`): catálogo de las cuentas de Pichincha, Guayaquil e
> Internacional, con `saldo_informado` y una cuenta contable hija por banco
> (`1102.01`–`1102.03`). El saldo contable sale del libro mayor; los préstamos
> de `financial_liabilities` y los movimientos de `payments`. Detalle en
> `docs/BASE_DE_DATOS.md` §10.
>
> **Actualización 2026-11-11 — v6.9 (multimedia).** Se suma `media_assets`
> (`071_media_clientes.sql`), el índice de fotos, videos, audios y documentos
> que viven en Bunny.net, y `clients.cedula`. La carpeta del cliente en Bunny
> es `clientes/<nombre>_<cedula>/`; el resto son etiquetas en la base. Reglas
> en `docs/WHATSAPP_Y_MEDIA.md`.
>
> **Actualización 2026-11-11 — v6.8 (CHAT por cliente).** Se suman
> `chat_conversaciones`, `chat_mensajes` y la vista `v_chat_conversacion`
> (`070_chat_clientes.sql`). El historial de conversaciones vive en PostgreSQL,
> es append-only y queda disponible para el bot. Detalle completo en
> `docs/BASE_DE_DATOS.md` §9. También entran `dispatch_schedule` (067) y
> `panel_users_acl` (068).
>
> **Actualización 2026-11-09 — Custodio v4.4.0.** Al esquema base se suman 14
> tablas contables/operativas y 3 vistas nuevas. El detalle de creación,
> responsables y flujo de ingresos está en `docs/BASE_DE_DATOS.md`; las
> migraciones son `063_custodio_core.sql`, `064_custodio_views.sql`,
> `065_http_gate_v44.sql` y `066_iva_default_v44.sql`.
> `crear_orden` escribe IVA/bruto cuando el contrato envía `aplica_iva=true` y
> registra el `COBRO` de contado o abono; caja y dashboard filtran
> `payments.deleted_at` y usan el bruto; el kardex calcula costo promedio
> ponderado, guarda `costo_unitario_snapshot` y anula consumos `TEORICO` con
> `ANULACION`. El Custodio (`app/custodio/`) implementa el Gate con 14 intents,
> 9 consultas, idempotencia por `request_id` + hash, partida doble, reversa del
> asiento vigente y testigo inmutable. `app/http_gate/` lo expone con tokens de
> servicio y una ventanilla única de pagos/gastos.

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
| 27 | `dispatch_schedule` | Agenda de entregas | Fecha, cliente, orden y estado; borrado lógico (`067`) |
| 28 | `panel_users_acl` | Usuarios simulados del panel | Rol base, módulos permitidos y modo `EDICION` / `SOLO_LECTURA` (`068`) |
| 29 | `chat_conversaciones` | Hilo por cliente y canal | `UNIQUE (cliente_id, canal)`; la carpeta de conversación (`070`) |
| 30 | `chat_mensajes` | Mensajes del historial | Append-only; `direccion`, `autor_tipo`, `whatsapp_msg_id` único y `busqueda` tsvector (`070`) |
| 31 | `media_assets` | Índice de multimedia | Binario en Bunny; aquí ruta, mime, bytes, hash y etiquetas (`071`) |
| 32 | `bank_accounts` | Cuentas bancarias | Pichincha, Guayaquil e Internacional; saldo informado y cuenta contable hija (`072`) |
| 33 | `client_invoices` | Facturas internas | PDF o foto adjunta al cliente; montos desde la orden o carga manual; `es_ficticia` (`073`) |
| 34 | `gato_turnos` | Memoria de Gato | Pregunta, respuesta, estado, actor y `conversacion_id`; historial de 8 turnos (`074`) |

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

### `v_chat_conversacion`
Resumen por hilo: `total_mensajes`, `no_leidos` (entrantes sin
`leido_panel_at`), `ultimo_mensaje_at` y `ultimo_mensaje_preview`. Alimenta el
contador de la pestaña CHAT y las consultas del bot.

## Custodio: Gate, libro mayor y testigo

- **`Gate.mutar()`** valida el contrato v1.3.0, autoriza por rol y canal,
  comprueba idempotencia (`request_id` + SHA-256 del payload) y ejecuta la
  mutación y su asiento en **una sola transacción**. Si el asiento no cuadra,
  no queda la mutación.
- **`ledger_entries`** es inmutable. Una corrección inserta una reversa del
  asiento vigente (el que aún no tiene reversa) y luego el asiento nuevo; no
  reescribe el pasado.
- **`audit_witness_log`** guarda el valor anterior, el nuevo y el motivo de cada
  corrección. Pagos y pagos a proveedor revierten y rehacen su asiento; una
  compra solo se corrige si es de servicio y tiene una única línea.
- **Anulación y valoración:** una orden con cobros activos queda
  `PENDING_JULIO_APPROVAL`; al aprobar, Julio indica `modo_resolucion_cobro`
  (`CONVERTIR_A_ANTICIPO_CLIENTE` o `DEVOLVER_DINERO_CAJA_O_BANCO`).
  Valoración 10 años y DSCR leen `finanzas.parametros_contables`; si faltan
  tasas, devuelven la foto real con `UNCONFIRMED_FINANCIAL_RATES`.

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
   corrección revierte únicamente el asiento vigente (`is_reversal = true`) y
   deja un testigo nuevo; el histórico anterior no se toca.
8. `processed_requests` es idempotente por `request_id` + hash; el mismo
   payload devuelve la misma respuesta y un hash distinto se rechaza.
9. `v_stock_proyectado` no aplica consumos teóricos si
   `materials.ultimo_levantamiento_at` es NULL: marca `SIN_FECHA_CONTEO`.
