# Decisiones pendientes y datos que el PDR no trae

Última actualización: 2026-11-08
Estado: **Hitos 1, 2 y 3 construidos y verificados localmente; candados aún
abiertos solo por datos de negocio y credenciales.**

Este documento existe porque el PDR v4.0 define la arquitectura pero **no**
define varios datos de negocio. Nada de lo que falta se rellenó con supuestos:
o quedó vacío (`NULL`), o quedó marcado como provisional y el motor se niega a
usarlo. Aquí está el inventario exacto de lo que falta y dónde se corrige.

---

## A. Bloqueantes para cerrar el Hito 1

### A1. Recetas de hormigón (la más importante)

**Qué falta:** la dosificación real por m³ de FC-180, FC-210, FC-280 y FC-350:
sacos de cemento, m³ de arena, m³ de ripio, litros de agua y litros de
retardante. También el **peso del saco** (¿50 kg?).

**Qué hay hoy** en `concrete_recipes`:

| Resistencia | Cemento sacos/m³ | Retardante L/m³ | Arena/Ripio/Agua | Estado |
|---|---|---|---|---|
| FC-180 | NULL | NULL | NULL | PROVISIONAL |
| FC-210 | 7.500 | 1.200 | NULL | PROVISIONAL |
| FC-280 | NULL | NULL | NULL | PROVISIONAL |
| FC-350 | NULL | NULL | NULL | PROVISIONAL |

El 7.5 y el 1.2 **no son una receta**: salen del único ejemplo numérico del
PDR (`60 sacos` y `9.6 L` para `8 m³`), y están marcados `confirmado = false`
con esa fuente escrita al lado.

**Efecto (actualizado 2026-11-08):** la orden **sí se crea** y la venta sigue
(`permitir_receta_provisional = True`); el viaje queda marcado con
`"receta_provisional": true` en su `tracking_payload`, **no** se genera kardex
teórico y el Centinela lo reporta como `WARN` en `recetas_provisionales`. Se
descartó bloquear la venta: detener una operación real por un dato
administrativo pendiente cuesta más que el aviso visible.

**Cómo se cierra:**

```sql
UPDATE concrete_recipes
   SET cemento_sacos_m3     = :sacos,
       arena_m3_m3          = :arena,
       ripio_m3_m3          = :ripio,
       agua_litros_m3       = :agua,
       retardante_litros_m3 = :retardante,
       saco_kg              = :kg,
       confirmado           = true,
       fuente               = 'Dosificación validada por Julio Villavicencio el :fecha'
 WHERE resistencia = 'FC-210';
```

Luego: `python scripts/hito1_lock_test.py` debe mostrar `kardex generado: 80`
(40 viajes × cemento + retardante) sin el aviso de provisional.

### A2. Flota real de mixers

**Qué falta:** cuántos mixers hay, sus códigos y su capacidad (el PDR menciona
7 m³ y 8 m³, pero solo nombra `MIXER-01`).

**Qué hay hoy:** `system_settings['flota.mixers']` con un solo mixer de 8 m³,
marcado como ejemplo del PDR.

**Cómo se cierra:** actualizar el JSON:

```sql
UPDATE system_settings
   SET value = '[{"codigo":"MIXER-01","capacidad_m3":8,"activo":true},
                 {"codigo":"MIXER-02","capacidad_m3":7,"activo":true}]'::jsonb
 WHERE key = 'flota.mixers';
```

### A3. Política de reparto del último viaje

**Qué falta:** qué hace Orminorth cuando el volumen no es múltiplo de la
capacidad del mixer. El PDR solo dice "40 viajes de 8 m³" para 320 m³.

**Qué hay hoy:** `operacion.politica_redondeo_viajes = "ultimo_parcial"`.
Consecuencia: 52 m³ → 6 viajes de 8 + 1 de 4. Alternativas ya implementadas:
`ultimo_completo` (7 viajes de 8, reporta 4 m³ de excedente) y
`distribucion_uniforme` (7 viajes de 7.43 m³).

**Cómo se cierra:** cambiar el parámetro. No se toca código.

### A4. Inventario inicial y umbrales

**Qué falta:** stock físico inicial, stock mínimo y unidad real de cada
material (¿el saco es de 50 kg? ¿arena y ripio en m³ sueltos o compactados?).

**Qué hay hoy:** los 5 materiales existen con `stock_actual = NULL` y
`stock_minimo = NULL`. La vista `v_inventario` los reporta como
`SIN_LEVANTAR` / `SIN_UMBRAL`. **No se asumió stock 0** porque 0 es un dato
falso que dispararía alertas.

**Cómo se cierra:**

```sql
UPDATE materials SET stock_actual = 1200, stock_minimo = 300 WHERE codigo = 'CEMENTO';
UPDATE materials SET stock_actual = 45.5, stock_minimo = 10  WHERE codigo = 'ARENA';
```

### A5. Precios

**Qué falta:** precio por m³ de cada resistencia (y si incluye IVA).

**Qué hay hoy:** `precios.hormigon = {}` y `orders.total = NULL`. El dashboard
no puede calcular facturación todavía.

---

## B. Hito 3 (WhatsApp) — decisiones ratificadas y bloqueos restantes

> **Ratificado 2026-11-08.** B1, B2 y B3 quedaron resueltos por Dirección y ya
> están implementados en `services/core-api/app/m1_whatsapp/` y en la migración
> `040_ratificacion_hito3.sql`. El detalle histórico se conserva abajo; los
> puntos que siguen abiertos son solo B4 (credenciales y teléfonos reales).

### B1. Identificación de quién escribe — RESUELTO

Regla implementada (no se inventaron números):

1. **Primaria:** teléfono registrado. `clients.telefono_whatsapp` (clientes) y
   `system_settings['whatsapp.staff']` (personal) definen el rol:
   `SUPERADMIN`, `CAJA_SECRETARIA`, `BODEGA_PLANTA`, `CHOFER_MIXER`, `CLIENTE`.
2. **Fallback:** prefijo en el texto del mensaje (`#M1`, `#BODEGA`, `#CAJA`,
   `#ADMIN`). Los códigos de operador ganan sobre la referencia a un mixer.
   `#CLIENTE` no se acepta: un cliente se identifica por su número registrado.
3. **Sin coincidencia:** `LEAD_DESCONOCIDO` y Gate #4 (prospecto).

Un número desconocido que escribe como bodeguero no se trata como personal: se
marca como lead salvo que use un código de operador.

### B2. Gate #2 cuando el cliente confirma y se queja a la vez — RESUELTO

Si el mensaje contiene un reclamo, **no se sella la recepción**: el viaje pasa
a `INCIDENCIA_RECLAMO`, se marca `incidencia_detectada = true` y se alerta al
Centinela (que lo registra en `error_logs` y lo empuja al CRM si hay webhook).

### B3. Gate #3 con archivo inválido — RESUELTO

Si el chofer reporta llegada **sin adjunto**, el Juez devuelve
`EVIDENCIA_FALTANTE`: el viaje queda en `EVIDENCIA_PENDIENTE` y se le pide
reenviar. Si el adjunto existe pero Bunny falla o no está configurado, se
registra `EVIDENCIA_BUNNY_FALLIDA` como incidencia; no se finge una URL.

### B4. Credenciales e instancias existentes — ABIERTO

- Evolution API: URL, nombre de instancia, API key (hoy vacíos).
- Bunny.net: Storage Zone, host CDN, API key (hoy vacíos).
- Gemini: API key (sin ella se usa el juez determinístico).
- Teléfonos reales del personal y número de WhatsApp de prueba.

Sin esto, el Centinela los reporta correctamente como `NO_CONFIGURADO` y el
Módulo 1 funciona en local con el juez determinístico.

---

## C. Decisiones para Hitos 4 y 5

| # | Tema | Qué falta decidir | Dónde impacta |
|---|---|---|---|
| C1 | Cierre de caja | ¿Es inmutable? ¿Quién puede reabrirlo? ¿Qué pasa con un abono que llega después de cerrar? | `cash_closures` (tabla creada, sin endpoints aún) |
| C2 | Cuota de mercado | ¿Año calendario o 12 meses móviles? ¿Qué precio se usa para valorizar lo que factura la competencia? ¿A qué año corresponden los 120.000 / 95.000 m³? | `market_benchmarks.anio` está en NULL |
| C3 | Simulador bancario | Confirmar amortización francesa, 11,2 % nominal anual capitalizable mensual, y **sobre qué período de flujo** se calcula el DSCR | Hito 5; los valores 3.283,35 / 77,3 m³ / 2,33x se usarán como test de regresión |
| C4 | Facturación electrónica SRI | **Fuera de alcance del PDR v4.0 (ratificado 2026-11-08).** No se implementa en este proyecto | Ninguna tabla de facturación existe a propósito |
| C5 | Panel web | Stack real de Aquatech a reutilizar; usuarios y roles; dominio/subdominio y TLS (la lista de contenedores del PDR no incluye proxy inverso) | Hito 4 |
| C6 | Webhook del CRM | URL real (el PDR trae `crm-tu-empresa.com` como marcador) | Módulo 5 push |
| C7 | Respaldos | Política de backup de PostgreSQL y retención de `error_logs` | Operación del VPS |
| C8 | Aviso térmico | **Reemplazado (ratificado 2026-11-08) por dos bandas** sobre `max_fraguado_minutes = 150`: `ALERTA_TEMPRANA` a 60 min antes (minuto 90, WARN) y `POR_VENCER_CRITICO` a 30 min antes (minuto 120, CRÍTICO). Parámetros: `operacion.alerta_temprana_minutos_antes` y `operacion.por_vencer_critico_minutos_antes` | Centinela (`riesgo_termico`) y panel |

---

## D. Decisiones de ingeniería ya tomadas (no requieren al cliente)

1. **12 tablas en lugar de "10".** El PDR dice "las 10 tablas" pero nunca las
   enumera. Se implementaron 10 de negocio (`system_settings`, `plants`,
   `concrete_recipes`, `clients`, `orders`, `mixer_dispatches`, `materials`,
   `inventory_movements`, `payments`, `cash_closures`) más 2 que el propio PDR
   nombra (`market_benchmarks`, `error_logs`).
2. **JSONB autoritativo.** `mixer_dispatches.tracking_payload` es el contrato;
   las columnas planas (`estado_actual`, `volumen_m3`, etc.) las sincroniza el
   trigger `trg_dispatch_project` y existen solo para indexar/consultar.
3. **Kardex teórico por viaje, no por orden.** Así cada JSON de viaje es
   autosuficiente y el panel puede mostrar consumo aunque la orden siga en curso.
4. **`materials.stock_actual` = stock real.** El teórico se calcula sumando
   `inventory_movements` con `tipo = 'TEORICO'`. Nunca se mezclan.
5. **Zona horaria.** Se guarda `timestamptz` (UTC interno) y la zona operativa
   (`America/Guayaquil`) vive en `system_settings`, no en el código.
6. **Migraciones SQL planas** con `schema_migrations` y advisory lock. Sin ORM
   ni Alembic: el contrato es SQL, no el framework.
7. **Una receta no confirmada no bloquea la venta (ratificado 2026-11-08).**
   `crear_orden` acepta `permitir_receta_provisional = True` por defecto y el
   viaje declara `"receta_provisional": true` en su `tracking_payload`. El
   kardex teórico no se genera y el Centinela reporta `WARN` en
   `recetas_provisionales`; el aviso queda visible, pero la operación sigue.
   El viejo comportamiento (bloquear la orden) se descartó porque detenía una
   venta real por un dato administrativo pendiente.
8. **Latencia del Centinela.** En caliente responde 20–25 ms (el PDR exige
   <200 ms). La primera llamada tras arrancar tarda ~250–400 ms porque abre
   conexiones; se puede eliminar con un precalentamiento en el `lifespan`.
