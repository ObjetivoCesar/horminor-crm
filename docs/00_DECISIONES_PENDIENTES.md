# Decisiones pendientes y datos que el PDR no trae

Última actualización: 2026-11-09
Estado: **Hitos 1 y 3 cerrados; el Hito 3 en modo SANDBOX. Módulos 3
(Secretaría + Caja) y 4 (Dashboard de Julio y Ases) construidos y verificados
localmente. La especificación del Custodio v4.4.0 (`063`/`064`/`065`/`066`)
está aplicada en la base real y el circuito HTTP está cerrado: Gate, pagos,
anticipos, reembolsos y rol CONTADORA. Quedan pendientes operativos (tasas
financieras, conteo físico, formulario del panel, login de usuario y backups),
no decisiones de negocio.** El Centro de Configuración Superadmin opera sin
login en esta etapa. Las credenciales reales y los teléfonos ya no bloquean: se
cargan en caliente y se apaga el switch SANDBOX.

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

### A2. Flota real de mixers — RESUELTO (semilla de demostración)

`flota.mixers` arranca con `MIXER-01` (8.0 m³), `MIXER-02` (8.0 m³) y
`MIXER-03` (7.0 m³), todos activos. La migración 060 carga además las placas
`OAA-1024`, `OAA-1088` y `PBA-4512` con los choferes Pedro Andy, Carlos Grefa y
Luis Zambrano, y una cuarta unidad. Son **datos de demostración entregados para
la puesta en marcha**, editables en `flota_y_operacion`; reemplazarlos por la
flota definitiva antes de operar.

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

### B3. Semillas administrativas y datos aún abiertos

La migración 060 carga la razón social `ORMINORTH HORMIGONES Y PREFABRICADOS
S.A.S.`, RUC `2290000000001`, dirección y horario, cuentas de Banco Pichincha y
BanEcuador, placas/choferes y `finanzas.tope_credito_auto` (cupo por defecto
$1.500, mora máxima 15 días). La migración **062** corrigió la marca a
`HORMINOR HORMIGONES Y PREFABRICADOS S.A.S.` / `Horminor Hormigones` y el host
Bunny a `horminor.b-cdn.net`, sin editar la 060 ya aplicada. Son **datos de
puesta en marcha**, editables en caliente. Siguen `NULL`/`NO_CONFIGURADO` el precio de mercado por provincia, el
umbral de merma y el webhook real del CRM; el bot y el panel los omiten en
lugar de inventarlos.

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

### B4. Credenciales e instancias existentes — ABIERTO, ya no bloqueante

- Evolution API: URL, nombre de instancia, API key (hoy `SANDBOX`).
- Bunny.net: Storage Zone, host CDN, API key (hoy `SANDBOX`).
- Gemini: API key (sin ella se usa el juez determinístico).
- Teléfonos reales del personal y número de WhatsApp de prueba.

En SANDBOX el WhatsApp se encola en `sandbox_outbox`, Bunny devuelve URLs
deterministas bajo `/sandbox/` y el Juez es determinístico; el Centinela lo
publica como `modo=SANDBOX` y `judge_mode=DETERMINISTIC_FALLBACK`. Al cargar
las credenciales y apagar los switches, los mismos contratos pasan a
producción sin tocar el pipeline.

---

## C. Decisiones de Hitos 4 y 5 — RESUELTAS (2026-11-08)

| # | Tema | Decisión vigente | Implementación |
|---|---|---|---|
| C1 | Cierre de caja | Un cierre por día con snapshot inmutable del resumen; se guarda `efectivo_contado` y `diferencia`. Reabrir un cierre requiere una decisión explícita que todavía no se implementa | `cash_closures` + `/api/v1/secretaria/cierre-caja` |
| C2 | Cuota de mercado | Selector `12_MESES_MOVILES` / `ANIO_CALENDARIO`; benchmarks Orellana 120.000 m³ y Sucumbíos 95.000 m³ para 2025/2026; valorización a $118.00/m³ (FC-210); las ventas sin provincia se informan en `sin_provincia_m3` y no se reparten | `/api/v1/dashboard/mercado`, migración 060 |
| C3 | Simulador bancario | Amortización francesa, 11,2 % nominal anual capitalizable mensual, 36 meses/$100.000 y 48 meses/$240.000, margen $42.50/m³, 180 y 450 m³ extra; DSCR activo e histórico | `m4_dashboard/calculos.py`, `/api/v1/dashboard/simulador` |
| C4 | Facturación electrónica SRI | **Fuera de alcance del PDR v4.0 (ratificado 2026-11-08).** No se emite comprobante electrónico ni clave de acceso. | Factura interna adjunta (client_invoices, migración 073) para PDF/foto; no sustituye al SRI |
| C5 | Panel web | HTML/CSS/JS propio servido por FastAPI en `/panel`, sin build ni CDN; selector Secretaría/Gerencial/Superadmin; usuarios/roles y TLS quedan para la etapa de autenticación | `services/core-api/app/web/` |
| C6 | Webhook del CRM | **ABIERTA:** URL real (el PDR trae `crm-tu-empresa.com` como marcador) | Módulo 5 push |
| C7 | Respaldos | **ABIERTA:** política de backup de PostgreSQL y retención de `error_logs` | Operación del VPS |
| C8 | Aviso térmico | **Reemplazado (ratificado 2026-11-08) por dos bandas** sobre `max_fraguado_minutes = 150`: `ALERTA_TEMPRANA` a 60 min antes (minuto 90, WARN) y `POR_VENCER_CRITICO` a 30 min antes (minuto 120, CRÍTICO) | Centinela (`riesgo_termico`) y panel |

---

## D. Custodio v4.3 — decisiones resueltas y pendientes (2026-11-09)

> La base se migró después de probar `063` y `064` en el clon `orminorth_v43`
> y de guardar `.agents/evidencias/pre_v43_orminorth.dump`. Evidencia:
> `.agents/evidencias/revision_v43_2026-11-09.txt`.

### D1. Decisiones de negocio resueltas

| # | Tema | Decisión vigente | Implementación |
|---|---|---|---|
| E1 | Cobro de contado | Cada venta `EFECTIVO`, `TRANSFERENCIA` o `ABONO` inicial genera un `payments` tipo `COBRO` por el total con IVA. `FIADO` no genera `COBRO`: queda como deuda | **Aplicado** en `crear_orden` (refactor 2026-11-09); verificado en el clon con `refactor_v43_check.py` |
| E2 | IVA | Históricos sin backfill. Las ventas nuevas solo llevan IVA si el contrato envía `aplica_iva=true`; el panel lo envía. Saldo, cupo y cartera usan `total_con_iva` cuando existe | `066` apaga `finanzas.iva_default_aplica`; `crear_orden` escribe `aplica_iva`, `iva_pct`, `iva_monto` y `total_con_iva`; `064` usa `COALESCE(total_con_iva, total)` para históricos |
| E3 | Costo de inventario | Promedio ponderado para COGS y valor de inventario | `finanzas.costo_inventario_metodo = "PROMEDIO_PONDERADO"`; **aplicado** en `kardex.py` (promedio en `COMPRA`, snapshot en todos los movimientos); la recepción de compras del Gate usa el mismo kardex |
| E4 | Datos maestros | El Gate puede crear proveedores, activos fijos y pasivos bancarios | **Implementado**: `CREATE_SUPPLIER`, `CREATE_FIXED_ASSET` y `CREATE_FINANCIAL_LIABILITY` en `gate.py`, verificados en `custodio_v43_check.py` |
| E5 | Fecha de conteo | No se inventa: `materials.ultimo_levantamiento_at` queda `NULL` hasta que Julio entregue la fecha real | `063` la deja nullable; `v_stock_proyectado` marca `SIN_FECHA_CONTEO` |

### D2. Pendientes operativos (las decisiones de negocio ya están cerradas)

| # | Tema | Qué falta | Dueño |
|---|---|---|---|
| P1 | Tasas financieras | El formulario ya está en Superadmin; falta que Julio/Contadora carguen `wacc_anual_pct`, `crecimiento_anual_pct`, `participacion_trabajadores_pct`, `impuesto_renta_pct` y `dscr_minimo_banco`. Mientras sigan `null`, valoración/DSCR devuelven la foto real y `UNCONFIRMED_FINANCIAL_RATES` | Julio / Contadora |
| P2 | Conteo físico | El formulario de conteo ya está en Superadmin; falta que Bodega ejecute el levantamiento real de los 5 materiales. Mientras no se registre, `v_stock_proyectado` marca `SIN_FECHA_CONTEO` y el Gate advierte; no bloquea la venta | Julio / Bodega |
| P3 | Formulario de pagos en el panel | **Implementado**: `/panel` tiene cobro/abono y gasto conectados a `/api/v1/panel/pagos` y al catálogo. Falta validarlo con la secretaria real | Desarrollo / Secretaría |
| P4 | Login de usuario | Pendiente: login de Secretaría/Superadmin y protección de todas las rutas del panel antes de exponerlo a Internet | Desarrollo |
| P5 | Backups y VPS | `scripts/backup_db.sh` listo con retención 14/6 y verificación `pg_restore --list`; falta instalar el cron y copiar los backups fuera del VPS | César / Nohan |
| P6 | Nota de crédito Fase 2 | El intent dedicado `REGISTER_PURCHASE_CREDIT_NOTE` queda agendado si Dirección lo requiere; Fase 1 ya rechaza con `PURCHASE_REQUIRES_CREDIT_NOTE` | Julio / Dirección |
| P7 | Cédula del cliente | `clients.cedula` se agregó en `071` como `NULL`. Falta que Julio la cargue para que la carpeta de Bunny sea `nombre_cedula` sin homónimos. Mientras tanto la API usa RUC o el id | Julio |
| P8 | Credenciales Evolution + Bunny | Cargar URL/instancia/API key de Evolution, Storage Zone/API key/CDN y `BUNNY_TOKEN_KEY` en Superadmin o `.env`; luego apagar `sandbox` en `integraciones.*` | César / Julio |

### D3. Decisiones de implementación del Custodio (2026-11-09)

| # | Decisión | Porqué |
|---|---|---|
| I1 | El pago inicial de una compra va en un asiento `SUPPLIER_PAYMENT` separado del asiento `PURCHASE` | Corregir el pago con testigo revierte solo el pago; la compra conserva su asiento y su trazabilidad |
| I2 | La corrección con testigo revierte solo el asiento vigente (sin reversa previa) | Revertir todo el histórico del documento duplicaba el ajuste en una segunda corrección |
| I3 | Una compra con inventario o varias líneas no se corrige por testigo | La cabecera no redistribuye stock ni costos; hacerlo sería inventar la distribución. Exige nota de crédito (`PURCHASE_REQUIRES_CREDIT_NOTE`) |
| I4 | Valoración/DSCR leen `finanzas.parametros_contables`; anulación con cobros exige `modo_resolucion_cobro` | Si faltan tasas, devuelven la foto real y `UNCONFIRMED_FINANCIAL_RATES`; si faltan cobros, no se consume la aprobación. No se inventan fórmulas ni reembolsos |

---

## E. Decisiones de ingeniería ya tomadas (no requieren al cliente)

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
10. **Modo SANDBOX por adaptadores inyectables (2026-11-08).** `app/sandbox.py`
    implementa `SandboxNotifier` (outbox en PostgreSQL/memoria),
    `SandboxBunnyStorageClient` (URL determinista bajo `/sandbox/`) y el Juez
    determinístico. El pipeline no tiene ramas de sandbox: se inyecta el
    adaptador. Se descartó llenar el código de `if settings.sandbox`.
11. **Outbox persistido, no logs.** `sandbox_outbox` guarda canal, destino,
    tipo, contenido, metadatos y estado `ENCOLADO`; el panel y el candado leen
    lo mismo. Se descartó un mock solo en memoria porque no era auditable.
12. **Cupo de crédito: alerta, no bloqueo.** Si `saldo + orden > cupo`, la
    orden se registra con `excede_cupo_credito=true` y se avisa al Centinela.
    Se descartó bloquear la venta por un parámetro administrativo.
13. **Precio de orden: explícito o de receta.** Si ninguno existe, `total`
    queda `NULL` y la orden se registra; nunca se rellena con un precio
    "razonable". Se descartó rechazar la orden.
14. **`clients.provincia` para la cuota de mercado.** Las ventas sin provincia
    se reportan aparte (`sin_provincia_m3`) y no se reparten por inferencia.
    Se descartó adivinar la provincia por el nombre del cliente.
15. **Panel HTML único, sin build ni CDN.** Sirve en local y en el VPS sin
    toolchain de frontend; se puede migrar a React/Aquatech cuando se decida.
    Se descartó montar Vite/React en esta etapa.
16. **Centinela sin llamadas externas en SANDBOX.** Evolution y Bunny devuelven
    `OK` con detalle de sandbox; antes el `HEAD` al CDN real daba 403 y
    confundía la salud global. Se descartó dejar el WARN artificial.
17. **Migración 061 separada.** La 060 ya estaba aplicada y no se edita una
    migración aplicada; la limpieza de benchmarks heredados (`anio NULL`) va en
    su propio archivo. Se descartó borrar filas a mano en producción.
