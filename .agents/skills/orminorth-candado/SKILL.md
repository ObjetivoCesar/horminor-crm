---
name: orminorth-candado
description: Ejecuta e interpreta los Tests de Candado de Orminorth (Hito 1 - Módulo 0 - y Hito 3 - Módulo 1 WhatsApp). Usar cuando hay que comprobar si un módulo está listo para cerrarse, cuando se cargaron recetas nuevas o cuando se conectaron credenciales reales.
---

# Skill: Tests de Candado

Hay dos candados independientes. El Hito 1 valida la estructura y el reparto de
viajes; el Hito 3 valida las cuatro compuertas de WhatsApp contra PostgreSQL
real. Ninguno sustituye la revisión de datos de negocio.

## Candado del Hito 1 (Módulo 0)

```powershell
docker compose run --rm --no-deps core-api python scripts/hito1_lock_test.py
```

El script es idempotente: borra y recrea solo las órdenes con
`notas = 'HITO1-LOCK'`. No toca datos reales.

Modo diagnóstico (calcula el kardex con la receta provisional derivada del PDR):

```powershell
docker compose run --rm --no-deps core-api python scripts/hito1_lock_test.py --provisional
```

### Qué verifica

1. Migraciones aplicadas y 12 tablas creadas.
2. 320 m³ FC-210 → exactamente 40 viajes de 8 m³.
3. 52 m³ FC-350 → 7 viajes (6×8 + 4) con política `ultimo_parcial`.
4. La suma de volúmenes coincide con lo pedido.
5. `mixer_dispatches` y `v_dispatch_timeline` devuelven las filas.
6. `v_inventario` devuelve los 5 materiales.

### Cómo interpretar

- Todos `[OK]`, "CANDADO ABIERTO", 0 movimientos de kardex → estructura
  correcta, **recetas sin confirmar**. Es el estado esperado mientras Julio no
  entregue la dosificación.
- Todos `[OK]` + "receta PROVISIONAL" en el listado → falta validar la receta.
- Con `--provisional`: 80 movimientos (40 viajes × cemento + retardante) y
  2.400 sacos / 384 L para 320 m³. Si no cuadra, el motor está mal; **no** el dato.
- Cualquier `[FALLA]` → el script sale con código 1. No se cierra el hito.

## Candado del Hito 3 (Módulo 1 WhatsApp)

```powershell
docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py
```

Simula tres celulares (bodega, chofer y cliente) sobre una orden creada en la
base real. Es idempotente: limpia solo lo que llevan `notas = 'HITO3-LOCK'`.
No usa Evolution, Gemini ni Bunny reales: usa el Juez determinístico, un
notificador en memoria y un Bunny en memoria.

### Qué verifica (28 aserciones)

1. La orden se crea con receta provisional permitida y 2 viajes de 8 m³.
2. **Gate #1:** bodega confirma salida → `EN_RUTA`, sello `salida_planta`,
   límite térmico = salida + 150 min y aviso encolado al cliente.
3. **Gate #3:** chofer envía evidencia → URL en `evidencias_bunny_cdn`,
   sello `llegada_obra_chofer`.
4. **Gate #2:** los 4 fragmentos del cliente se agrupan en un solo lote por el
   debounce y sellan `CONFIRMADO_CLIENTE` con el mensaje literal.
5. **Reclamo:** el cliente reporta demora → `INCIDENCIA_RECLAMO` y alerta
   `NO_CONFIGURADO` (sin webhook no se finge el envío), registrada en
   `error_logs` con `origen = 'M1_WHATSAPP'`.
6. El trigger proyecta el JSONB a las columnas planas en los dos viajes y
   `v_dispatch_timeline` expone los sellos y validaciones.

### Cómo interpretar

- `28 [OK]` / `0 [FALLA]` + `[CANDADO ABIERTO]` → el Módulo 1 funciona contra
  PostgreSQL real. **No** significa que el Hito 3 esté cerrado: faltan
  credenciales reales y teléfonos del personal.
- Cualquier `[FALLA]` → código de salida 1. No se cierra nada; primero se
  corrige el código o el dato.

## Regla de cierre

El **Hito 1** solo se marca 🟢 cuando, con las recetas reales cargadas
(`procesos/04-datos-negocio.md`):

1. El candado da todos `[OK]`.
2. El kardex se genera **sin** aviso de provisional.
3. La salida queda registrada en `.agents/BITACORA.md` y en `ESTADO.md`.

El **Hito 3** solo se marca 🟢 cuando, además del candado en verde, se repite
con Evolution API, Bunny.net y Gemini reales, y con los teléfonos reales del
personal cargados en `system_settings['whatsapp.staff']`.

Nunca "arregles" un candado bajando el criterio (por ejemplo, aceptando 6 viajes
para 52 m³ sin que el cliente haya definido esa política).
