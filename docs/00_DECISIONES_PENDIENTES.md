# Decisiones pendientes y datos que el PDR no trae

Última actualización: 2026-11-08
Estado: **Hito 1 construido y verificado localmente; candado aún abierto.**

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

**Efecto:** el motor determinístico lanza `RecetaNoConfirmadaError` y **no**
genera kardex teórico. Esto es intencional: preferimos un sistema bloqueado a
un inventario silenciosamente equivocado.

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

## B. Bloqueantes para el Hito 3 (WhatsApp)

### B1. Identificación de quién escribe (crítico)

El PDR dice que **todo** entra por un único número corporativo: bodeguero,
chofer, cliente y desconocidos. Pero los Gates #1, #2 y #3 dependen de saber
quién habla. El documento no define cómo se resuelve esa identidad.

**Qué hay hoy:** `whatsapp.staff = {}` (vacío) y `whatsapp.grupo_operativo =
null`. **No se inventaron números ni roles.**

**Opciones a decidir (elige una o combina):**
1. Números registrados: `clients.telefono_whatsapp` + un mapa `whatsapp.staff`
   teléfono → rol (`BODEGUERO`, `CHOFER`, `GERENCIA`).
2. Código en el mensaje: el bodeguero escribe `SALIDA #104 V2` y el bot enruta
   por número de orden/viaje.
3. Grupo operativo: bodeguero y choferes en un grupo, clientes en chat privado.

Sin esta decisión no se puede implementar el Módulo 1 sin adivinar.

### B2. Gate #2 cuando el cliente confirma y se queja a la vez

"Ya llegó pero tarde" no es ni `true` limpio ni `false` limpio con el contrato
`{cumple: bool, codigo_accion}`. Hay que decidir: ¿gana la alerta? ¿Se guarda
el sello y además se abre incidencia? (Recomendación de ingeniería: sellar
recepción y marcar `incidencia_detectada = true`, pero es decisión de negocio).

### B3. Gate #3 con archivo inválido

Si el juez binario dice NO, ¿el archivo se sube igual a Bunny para revisión
humana de la secretaria, o se descarta y se le pide al chofer que reenvíe?
El PDR solo describe el camino `true`.

### B4. Credenciales e instancias existentes

- Evolution API: URL, nombre de instancia, API key (hoy vacíos).
- Bunny.net: Storage Zone, host CDN, API key (hoy vacíos).
- Número de WhatsApp de prueba para el Hito 3 y ventana de corte si el número
  actual ya está en producción.

Sin esto, el Centinela los reporta correctamente como `NO_CONFIGURADO`.

---

## C. Decisiones para Hitos 4 y 5

| # | Tema | Qué falta decidir | Dónde impacta |
|---|---|---|---|
| C1 | Cierre de caja | ¿Es inmutable? ¿Quién puede reabrirlo? ¿Qué pasa con un abono que llega después de cerrar? | `cash_closures` (tabla creada, sin endpoints aún) |
| C2 | Cuota de mercado | ¿Año calendario o 12 meses móviles? ¿Qué precio se usa para valorizar lo que factura la competencia? ¿A qué año corresponden los 120.000 / 95.000 m³? | `market_benchmarks.anio` está en NULL |
| C3 | Simulador bancario | Confirmar amortización francesa, 11,2 % nominal anual capitalizable mensual, y **sobre qué período de flujo** se calcula el DSCR | Hito 5; los valores 3.283,35 / 77,3 m³ / 2,33x se usarán como test de regresión |
| C4 | Facturación electrónica SRI | ¿Está en alcance? El PDR habla de ERP y RUC pero no hay módulo de comprobantes | Ninguna tabla de facturación existe a propósito |
| C5 | Panel web | Stack real de Aquatech a reutilizar; usuarios y roles; dominio/subdominio y TLS (la lista de contenedores del PDR no incluye proxy inverso) | Hito 4 |
| C6 | Webhook del CRM | URL real (el PDR trae `crm-tu-empresa.com` como marcador) | Módulo 5 push |
| C7 | Respaldos | Política de backup de PostgreSQL y retención de `error_logs` | Operación del VPS |
| C8 | Aviso térmico | Hoy `POR_VENCER` se marca 30 min antes del límite (parámetro `operacion.umbral_por_vencer_minutos`, propuesto por ingeniería) | Solo color del panel |

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
7. **El motor se niega a operar con recetas no confirmadas.** Se puede forzar
   solo desde script, con `--provisional`, y el kardex queda marcado como
   `referencia = 'provisional'` para poder purgarlo después.
8. **Latencia del Centinela.** En caliente responde 20–25 ms (el PDR exige
   <200 ms). La primera llamada tras arrancar tarda ~250–400 ms porque abre
   conexiones; se puede eliminar con un precalentamiento en el `lifespan`.
