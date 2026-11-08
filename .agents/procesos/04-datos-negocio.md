# Proceso 04 — Cargar datos de negocio (sin tocar código)

Todo lo que Julio cambia en la operación se cambia aquí, con SQL. Si te ves
escribiendo una receta o un precio en Python, detente: está mal.

## Regla

| Dato | Dónde vive | Si falta |
|---|---|---|
| Recetas | `concrete_recipes` | `NULL` + `confirmado = false` |
| Precios | `system_settings['precios.hormigon']` | `{}` → `orders.total = NULL` |
| Flota | `system_settings['flota.mixers']` | solo el ejemplo del PDR |
| Teléfonos y roles | `clients.telefono_whatsapp` + `system_settings['whatsapp.staff']` | vacío |
| Stock | `materials.stock_actual` / `stock_minimo` | `NULL` (no 0) |
| Umbral de merma | `system_settings['operacion.merma_cemento_pct_alerta']` | `null` → Centinela `NO_CONFIGURADO` |

## 1. Recetas

```sql
UPDATE concrete_recipes
   SET cemento_sacos_m3     = 8.000,   -- sacos por m3
       arena_m3_m3          = 0.520,
       ripio_m3_m3          = 0.780,
       agua_litros_m3       = 180.00,
       retardante_litros_m3 = 1.200,
       saco_kg              = 50.00,
       confirmado           = true,
       fuente               = 'Validado por Julio Villavicencio el 2026-11-09',
       updated_at           = now()
 WHERE resistencia = 'FC-210';
```

Después de confirmar, verificar:

```powershell
docker compose run --rm --no-deps core-api python scripts/hito1_lock_test.py
```

El aviso "receta PROVISIONAL" debe desaparecer y el kardex debe generarse.

## 2. Precios

```sql
UPDATE system_settings
   SET value = '{"FC-180": 0, "FC-210": 0, "FC-280": 0, "FC-350": 0}'::jsonb
 WHERE key = 'precios.hormigon';
```

(Reemplazar los ceros por los precios reales. El sistema no los usa si están en 0
para no facturar en falso; se recomienda dejarlos fuera del JSON hasta tenerlos.)

## 3. Flota

```sql
UPDATE system_settings
   SET value = '[
     {"codigo":"MIXER-01","capacidad_m3":8,"activo":true},
     {"codigo":"MIXER-02","capacidad_m3":7,"activo":true}
   ]'::jsonb
 WHERE key = 'flota.mixers';
```

## 4. Stock

```sql
UPDATE materials SET stock_actual = 1200,  stock_minimo = 300 WHERE codigo = 'CEMENTO';
UPDATE materials SET stock_actual = 45.5,  stock_minimo = 10  WHERE codigo = 'ARENA';
UPDATE materials SET stock_actual = 60.0,  stock_minimo = 15  WHERE codigo = 'RIPIO';
UPDATE materials SET stock_actual = 5000,  stock_minimo = 1000 WHERE codigo = 'AGUA';
UPDATE materials SET stock_actual = 90.0,  stock_minimo = 20  WHERE codigo = 'RETARDANTE';
```

## 5. Personal de WhatsApp (pendiente de decisión)

```sql
UPDATE system_settings
   SET value = '{"+593999999999": "BODEGUERO", "+593988888888": "CHOFER"}'::jsonb
 WHERE key = 'whatsapp.staff';
```

**Antes de cargar esto hay que definir la regla de identificación** (ver
`docs/00_DECISIONES_PENDIENTES.md`, punto B1). Cargar números sin la regla no
sirve de nada.

## 6. Umbral de merma

```sql
UPDATE system_settings
   SET value = '5'::jsonb
 WHERE key = 'operacion.merma_cemento_pct_alerta';
```

Mientras siga en `null`, el chequeo de merma del Centinela reporta
`NO_CONFIGURADO` en lugar de alertar. Eso es correcto, no un bug.

## Cómo saber si un dato es real o provisional

```sql
SELECT resistencia, cemento_sacos_m3, confirmado, fuente
  FROM concrete_recipes
 ORDER BY resistencia;

SELECT key, value, descripcion
  FROM system_settings
 WHERE key LIKE 'whatsapp.%' OR key LIKE 'precios.%' OR key LIKE 'flota.%';
```

Si `confirmado = false` o el valor es `null`, es un dato pendiente.
