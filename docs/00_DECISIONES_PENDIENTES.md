# Decisiones pendientes y datos que el PDR no trae

Última actualización: 2026-11-08
Estado: **Hitos 1, 2 y 3 construidos y verificados localmente. Hito 1 CERRADO
con semilla oficial; el Hito 3 sigue abierto solo por credenciales y teléfonos
reales. El Centro de Configuración Superadmin opera sin login en esta etapa.**

Este documento existe porque el PDR v4.0 define la arquitectura pero **no**
define varios datos de negocio. Nada de lo que falta se rellenó con supuestos:
o quedó vacío (`NULL`), o quedó marcado como provisional y el motor se niega a
usarlo. Aquí está el inventario exacto de lo que falta y dónde se corrige.

---

## A. Hito 1 — CERRADO con semilla oficial (2026-11-08)

> **Decisión de Dirección (2026-11-08):** no se esperó la entrega manual de
> Julio. Todos los parámetros de negocio pasan a ser dinámicos y editables
> desde el **Centro de Configuración Superadmin**; la migración
> `050_seed_oficial_superadmin.sql` carga el punto de partida oficial. El
> candado del Hito 1 se ejecutó y terminó en `[CANDADO CERRADO]`.

### A1. Recetas de hormigón — RESUELTO

La semilla oficial de Orellana/Sucumbíos quedó cargada con sacos de 50 kg:

| Resistencia | Cemento sacos/m³ | Arena m³/m³ | Ripio m³/m³ | Agua L/m³ | Retardante L/m³ | Precio/m³ sin IVA | Uso comercial |
|---|---|---|---|---|---|---|---|
| FC-180 | 6.500 | 0.5600 | 0.6800 | 190 | 1.000 | $108.00 | Contrapisos, veredas y obras livianas |
| FC-210 | 7.500 | 0.5200 | 0.6800 | 185 | 1.200 | $118.00 | Losas, vigas, columnas residenciales y muros |
| FC-240 | 8.500 | 0.5000 | 0.6600 | 182 | 1.400 | $126.00 | Galpones industriales y pavimentos urbanos |
| FC-280 | 9.500 | 0.4800 | 0.6500 | 178 | 1.600 | $136.00 | Puentes, vías de carga pesada y plataformas |
| FC-350 | 11.000 | 0.4500 | 0.6200 | 172 | 2.000 | $158.00 | Plataformas petroleras y cimentaciones especiales |

Las cinco quedan `confirmado = true`, con `iva_pct = 15.00` editable y
`uso_comercial` para el bot. Se pueden cambiar sin tocar código desde
`PUT /api/v1/superadmin/config/formulas_y_precios` o el CRUD de recetas.

**Evidencia:** `hito1_lock_test.py` reporta 5 recetas confirmadas, precio y
dosificación completa, y **235 movimientos de kardex** generados para el pedido
del Ing. Reyes (320 m³ FC-210 + 52 m³ FC-350).

### A2. Flota real de mixers — RESUELTO (placas y choferes pendientes)

`flota.mixers` arranca con `MIXER-01` (8.0 m³), `MIXER-02` (8.0 m³) y
`MIXER-03` (7.0 m³), todos activos. `placa` y `chofer_asignado` quedan `null`
porque Julio no los entregó: son editables en
`flota_y_operacion`. No se inventó ninguna placa.

### A3. Política de reparto del último viaje — RESUELTO

`operacion.politica_redondeo_viajes = "PARCIAL"` (52 m³ → 6×8 + 4). El API
acepta los alias `PARCIAL | COMPLETO | UNIFORME`, editables en caliente.

### A4. Inventario inicial y umbrales — RESUELTO

Planta Central El Coca: cemento 3500/500/$8.20, arena 450/80/$14.00, ripio
550/100/$16.50 y retardante 600/100/$3.80. La llave
`bodega.umbrales_por_planta` permite ajustar por sucursal.

### A5. Precios — RESUELTO

`concrete_recipes.precio_m3` guarda el precio **sin IVA** y `iva_pct` el
porcentaje aplicable (15%). `orders.total` ya puede calcularse; el Frontend
decide cuándo mostrar el precio con impuesto.

### A6. Reloj térmico — RESUELTO

`max_fraguado_minutes = 150`, `alerta_temprana_min = 90` (faltando 60) y
`alerta_critica_min = 120` (faltando 30). Internamente se guardan los minutos
“antes” que consumen el pipeline y el Centinela; la API expone los absolutos
editables.

---

## B. Centro de Configuración Superadmin (sin login en esta etapa)

> **Ratificado 2026-11-08.** La autenticación de usuarios queda desacoplada para
> el final del proyecto. Las rutas de Superadmin y Secretaría operan abiertas en
> local/desarrollo; solo el endpoint externo del Centinela conserva
> `X-Agency-Master-Key`.

### B1. Qué se puede editar en caliente

| Sección | Contenido | Persistencia |
|---|---|---|
| `formulas_y_precios` | CRUD de recetas: dosificación, precio/m³, IVA, uso comercial | `concrete_recipes` |
| `whatsapp_evolution_y_cdn` | URL/instancia/API key de Evolution, debounce, zona/API/CDN de Bunny | `system_settings` |
| `empresa_bot_publico` | Nombre, RUC, planta, cobertura, horario, planta móvil, bancos, servicios | `system_settings` |
| `flota_y_operacion` | CRUD de mixers, política `PARCIAL/COMPLETO/UNIFORME`, reloj térmico | `system_settings` |
| `directorio_roles_whatsapp` | Teléfono → rol y códigos PIN de fallback | `system_settings` |
| `bodega_y_umbrales` | Stock, mínimo y costo por material y por planta | `materials` + `system_settings` |
| `finanzas_y_ases_gerenciales` | Tope de crédito, simulador bancario, benchmarks | `system_settings` + `market_benchmarks` |

### B2. Efecto en vivo

Al guardar una sección, el router avisa al Módulo 1: se recarga la ventana de
debounce y se invalida la caché de identidad. La siguiente petición ya usa el
valor nuevo, sin reiniciar el servidor. El Gate #4 lee
`empresa.bot_publico` y las recetas confirmadas en cada respuesta.

**Evidencia:** `PUT .../config/whatsapp_evolution_y_cdn` con
`debounce_seconds=9` → `GET /api/v1/whatsapp/health` devuelve
`ventana_segundos=9.0`; al restaurar 14 vuelve a `14.0`.

### B3. Datos que siguen `NULL` a propósito

`empresa.ruc`, `empresa.business_hours`, `empresa.bank_accounts`,
`flota.placa`, `flota.chofer_asignado` y `finanzas.tope_credito_auto` no fueron
entregados. El bot omite esas líneas en lugar de inventarlas.

---

## Bbis. Hito 3 (WhatsApp) — decisiones ratificadas y bloqueos restantes

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
   **Actualización 2026-11-08:** la semilla oficial confirmó las 5 recetas, así
   que en operación normal `receta_provisional` es `false` y el kardex sí se
   genera. El Centinela cruza contra `concrete_recipes.confirmado` para no
   dejar un WARN eterno por viajes históricos.
8. **Latencia del Centinela.** En caliente responde 20–25 ms (el PDR exige
   <200 ms). La primera llamada tras arrancar tarda ~250–400 ms porque abre
   conexiones; se puede eliminar con un precalentamiento en el `lifespan`.
9. **Repositorio solo local hasta el VPS (ratificado 2026-11-08).** El destino
   real es el VPS Linux; GitHub no es requisito para avanzar y el `push` dejó
   de considerarse bloqueo. Se conservan los commits locales como historial y
   red de seguridad. Se descartó insistir con la cuenta `ObjetivoCesar` porque
   no aporta al producto. **Contrapartida asumida:** sin copia fuera de la
   máquina, hay que respaldar el repo periódicamente (otra unidad o nube) hasta
   que exista el VPS.
