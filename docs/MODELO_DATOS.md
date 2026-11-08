# Modelo de datos — Módulo 0

Motor: PostgreSQL 15. Esquema en `db/migrations/001_init.sql`.
Migraciones aplicadas automáticamente al arrancar la API (idempotentes, con
`pg_advisory_lock` y registro en `schema_migrations`).

## Tablas

| # | Tabla | Para qué | Notas |
|---|---|---|---|
| 1 | `system_settings` | Parámetros maestros (`key` → `value` JSONB) | Ningún precio, teléfono, receta ni umbral vive en el código |
| 2 | `plants` | Plantas fija y móvil | Agregar planta = `INSERT`, sin deploy |
| 3 | `concrete_recipes` | Dosificación por m³ y resistencia | `confirmado = false` ⇒ el motor se niega a calcular |
| 4 | `clients` | Clientes y prospectos | `estado = PROSPECTO` para los leads del Gate #4; `telefono_whatsapp` único |
| 5 | `orders` | Orden de hormigón | `total` es columna generada: `volumen × precio` (NULL si no hay precio) |
| 6 | `mixer_dispatches` | Viajes de mixer | `tracking_payload` JSONB es el contrato; columnas proyectadas por trigger |
| 7 | `materials` | Stock real por material | `stock_actual` NULL = inventario no levantado (no se asume 0) |
| 8 | `inventory_movements` | Kardex | `TEORICO` (receta) / `REAL` (bodega) / `COMPRA` / `AJUSTE`, cantidad con signo |
| 9 | `payments` | Cobros y caja chica | `FIADO` es crédito, no efectivo: se reporta aparte en el cierre |
| 10 | `cash_closures` | Cierre diario | `snapshot` JSONB inmutable + totales por método |
| 11 | `market_benchmarks` | Demanda regional (As #1) | `anio` NULL porque el PDR no lo fija |
| 12 | `error_logs` | Errores y eventos | Alimenta el chequeo de errores del Centinela |

## Vistas de contrato

### `v_dispatch_timeline`
Aplana el `tracking_payload` de cada viaje: cliente, resistencia, planta,
sellos forenses (`dosificado_planta`, `salida_planta`, `limite_termico_fraguado`,
`llegada_obra_chofer`, `confirmacion_whatsapp_cliente`), veredictos del juez
binario y consumo de materiales. Es lo que consume el Panel Central del Módulo 3.

### `v_cliente_saldo`
Total comprado ($ y m³), cobrado, fiado y **saldo pendiente**. Alimenta la ficha
financiera del panel izquierdo de la secretaría.

### `v_inventario`
Stock con estado: `OK`, `CRITICO`, `SIN_UMBRAL`, `SIN_LEVANTAR`.

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
