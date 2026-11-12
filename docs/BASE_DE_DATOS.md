# Base de datos — cómo está creada y quién responde por ella

> Última verificación: **2026-11-11**
> Evidencia: consultas ejecutadas contra `orminorth-postgres` (ver secciones 8 y 9).
> Regla de este documento: lo que no está probado o designado se marca como
> **PENDIENTE**, no se rellena con supuestos.

---

## 1. Resumen en una frase

La base es **PostgreSQL 15** levantado por **Docker Compose**; el esquema se
crea y actualiza con **migraciones SQL versionadas** (`db/migrations/*.sql`)
que aplica la propia API al arrancar (`AUTO_MIGRATE=true`) con un *advisory
lock* y registro en `schema_migrations`.

No hay un servidor de base de datos "por fuera": la base vive en el volumen
Docker `orminorth-pgdata`, en el mismo VPS donde corre el resto de la pila.

---

## 2. Cómo se crea la base de datos

### 2.1 Contenedor

Archivo: `docker-compose.yml`

| Elemento | Valor |
|---|---|
| Imagen | `postgres:15-alpine` |
| Contenedor | `orminorth-postgres` |
| Usuario / base | `orminorth` / `orminorth` (por defecto, vía `.env`) |
| Puerto local | `5433` → `5432` dentro del contenedor |
| Volumen persistente | `orminorth-pgdata` → `/var/lib/postgresql/data` |
| Zona horaria | `America/Guayaquil` |
| Healthcheck | `pg_isready -U orminorth -d orminorth` |

Comando de arranque:

```powershell
Copy-Item .env.example .env   # solo la primera vez
docker compose up -d --build
```

### 2.2 Migraciones

Archivo: `db/migrations/`. Se aplican en orden alfabético y **son
idempotentes**.

- Runner: `services/core-api/app/db.py` → `run_migrations()`.
- Al arrancar la API: `AUTO_MIGRATE=true` (por defecto) ejecuta lo pendiente.
- Manual: `python scripts/db_migrate.py`.
- Bloqueo: `pg_advisory_lock(918273645)` evita que dos procesos migren a la vez.
- Control: cada archivo aplicado se registra en `schema_migrations`
  (`version`, `aplicada_at`). Si una migración ya está registrada, no se repite.

Variables relevantes (`services/core-api/app/settings.py` y `.env.example`):

| Variable | Valor por defecto | Para qué |
|---|---|---|
| `DATABASE_URL` | `postgresql://orminorth:orminorth@localhost:5433/orminorth` | Conexión asyncpg |
| `MIGRATIONS_DIR` | `db/migrations` (en Docker: `/app/db/migrations`) | Carpeta de SQL |
| `AUTO_MIGRATE` | `true` | Migrar al arrancar |

### 2.3 Migraciones aplicadas hoy (verificado)

| Versión | Aplicada (hora local) |
|---|---|
| `001_init.sql` | 2026-11-08 15:52 |
| `010_seed_settings.sql` | 2026-11-08 15:52 |
| `020_seed_recipes.sql` | 2026-11-08 15:52 |
| `030_umbral_termico.sql` | 2026-11-08 15:53 |
| `040_ratificacion_hito3.sql` | 2026-11-08 17:25 |
| `050_seed_oficial_superadmin.sql` | 2026-11-08 17:55 |
| `060_modulos_3_4_sandbox.sql` | 2026-11-08 18:40 |
| `061_benchmarks_limpieza.sql` | 2026-11-08 18:46 |
| `062_rebrand_horminor.sql` | 2026-11-08 21:35 |
| `063_custodio_core.sql` | 2026-11-09 12:50 |
| `064_custodio_views.sql` | 2026-11-09 12:50 |
| `065_http_gate_v44.sql` | 2026-11-09 16:17 |
| `066_iva_default_v44.sql` | 2026-11-09 16:22 |
| `067_operacion_compras_y_agenda.sql` | 2026-11-09 21:00 |
| `068_agenda_config_y_usuarios_acl.sql` | 2026-11-09 22:06 |
| `069_clientes_sabueso.sql` | 2026-11-09 23:22 |
| `070_chat_clientes.sql` | 2026-11-11 22:28 |
| `071_media_clientes.sql` | 2026-11-11 23:01 |
| `072_bancos_detalle.sql` | 2026-11-12 17:00 |
| `073_facturas_internas.sql` | 2026-11-12 22:00 |
| `074_gato_memoria.sql` | 2026-11-12 22:15 |

No hay migraciones pendientes: son **21 de 21**. La v4.4.0 del router HTTP se
aplicó después de probarla en el clon `orminorth_v43`; agrega parámetros
`system_settings` y apaga el IVA por defecto (`finanzas.iva_default_aplica =
false`). No toca datos de negocio ni órdenes existentes.

`069_clientes_sabueso.sql` agrega `clients.ciudad`, `clients.direccion_obra` y
el índice normalizado del buscador. `070_chat_clientes.sql` agrega el historial
de conversaciones por cliente; nace vacío y se detalla en la sección 9.

---

## 3. Qué existe en la base hoy (verificado)

### 3.1 Tablas

| Tabla | Para qué | Filas hoy |
|---|---|---|
| `system_settings` | Parámetros maestros `key → value` (JSONB) | 33 |
| `plants` | Plantas fija y móvil | 2 |
| `concrete_recipes` | Dosificación por resistencia | 5 |
| `clients` | Clientes y prospectos | 6 |
| `orders` | Orden de hormigón (la venta) | 4 |
| `mixer_dispatches` | Viajes de mixer | 51 |
| `materials` | Stock real por material | 5 |
| `inventory_movements` | Kardex (teórico / real / compra / ajuste / anulación) | 249 |
| `payments` | Cobros, gastos de caja y gastos bancarios | 0 |
| `cash_closures` | Cierre de caja diario (snapshot) | 0 |
| `market_benchmarks` | Benchmarks de mercado Orellana/Sucumbíos | 4 |
| `error_logs` | Errores del sistema | — |
| `sandbox_outbox` | Cola de salida del modo SANDBOX | — |
| `processed_requests` | Idempotencia del Gate (`request_id` + hash) | 0 |
| `accounting_accounts` | Plan de cuentas del Custodio | 30 |
| `suppliers` | Proveedores | 0 |
| `purchases` | Compras multi-ítem | 0 |
| `purchase_items` | Ítems de compra | 0 |
| `goods_receipts` | Recepciones de material | 0 |
| `supplier_payments` | Pagos a proveedores | 0 |
| `fixed_assets` | Activos fijos | 0 |
| `depreciation_runs` | Corridas de depreciación mensual | 0 |
| `financial_liabilities` | Préstamos y obligaciones bancarias | 0 |
| `loan_payments` | Pagos de préstamos | 0 |
| `ledger_entries` | Libro mayor inmutable (partida doble) | 0 |
| `audit_witness_log` | Testigo forense de correcciones | 0 |
| `approval_requests` | Cola de aprobación de Julio | 0 |
| `dispatch_schedule` | Agenda de entregas y despachos (`067`) | 0 |
| `panel_users_acl` | Usuarios simulados del panel y sus módulos (`068`) | 5 (semilla) |
| `chat_conversaciones` | Un hilo de conversación por cliente y canal (`070`) | 0 |
| `chat_mensajes` | Mensajes del historial, append-only (`070`) | 0 |
| `media_assets` | Índice de fotos, videos, audios y documentos del cliente (`071`) | 0 |
| `bank_accounts` | Catálogo de cuentas bancarias y saldo informado (`072`) | 3 (semilla) |
| `client_invoices` | Facturas internas (PDF o foto) adjuntas al cliente (`073`) | 1 (ficticia de prueba) |
| `gato_turnos` | Memoria de Gato: pregunta, respuesta y estado por conversación (`074`) | 0 (los turnos de prueba se limpiaron) |
| `schema_migrations` | Control del runner (no es de negocio) | 21 |

> **Nota:** `schema_migrations` la crea el runner, no una migración.
> `sandbox_outbox` la agrega `060_modulos_3_4_sandbox.sql`. Las 14 tablas del
> Custodio (`processed_requests` … `approval_requests`) las agrega
> `063_custodio_core.sql`. `dispatch_schedule` y `panel_users_acl` vienen de
> `067` y `068`; las dos tablas de chat de `070`; `media_assets` de `071`;
> `bank_accounts` de `072`; `client_invoices` de `073`; `gato_turnos` de `074`. En total hay **36 tablas base** y **7 vistas** en
> `public`. El plan de cuentas pasó de 27 a 30 filas: `072` agregó las hijas
> `1102.01`, `1102.02` y `1102.03` para cada banco.

### 3.2 Vistas

| Vista | Qué entrega |
|---|---|
| `v_cliente_saldo` | Por cliente: `id`, `nombre`, `estado`, `total_m3`, `total_facturado`, `total_cobrado`, `total_fiado`, `saldo_pendiente`, `ruc`, `credit_limit_usd` y `saldo_a_favor`. Conserva las 8 columnas originales y agrega 3 al final |
| `v_dispatch_timeline` | Un viaje de mixer con sus sellos de tiempo y veredictos del Juez |
| `v_inventario` | Stock físico por material y estado (`SIN_LEVANTAR`, `SIN_UMBRAL`, `CRITICO`, `OK`) |
| `v_stock_proyectado` | Stock físico + consumos `TEORICO` posteriores al último conteo; `ANULACION` se suma en valor absoluto. Sin fecha de conteo no aplica teóricos y marca `SIN_FECHA_CONTEO` |
| `v_balance_general` | Saldo por cada una de las 26 cuentas contables según su naturaleza; respeta `merged_into_id` sin reescribir el libro mayor |
| `v_estado_resultados` | Ingresos y gastos agrupados por mes y cuenta para el estado de resultados |
| `v_chat_conversacion` | Por hilo: `total_mensajes`, `no_leidos`, `ultimo_mensaje_at` y `ultimo_mensaje_preview`. Alimenta la pestaña CHAT y las consultas del bot |

**Compatibilidad de `v_cliente_saldo`:** la vista usa
`COALESCE(total_con_iva, total)` para `total_facturado` y `total_fiado`. Así una
orden histórica sin `total_con_iva` no desaparece del saldo. Desde el refactor
del 2026-11-09, `crear_orden` escribe siempre el bruto en ventas nuevas; el
fallback queda solo para las órdenes anteriores. `total_cobrado` solo suma
`payments` con `tipo_movimiento = 'COBRO'`, `metodo <> 'FIADO'` y
`deleted_at IS NULL`.

La definición de las 3 vistas originales está en `db/migrations/001_init.sql`;
las 3 nuevas y la versión v4.3 de `v_cliente_saldo` están en
`db/migrations/064_custodio_views.sql`; `v_chat_conversacion` está en
`db/migrations/070_chat_clientes.sql`. Se pueden releer con `\d+ <vista>` o
`pg_get_viewdef()`.

---

## 4. Cómo se registra un ingreso (modelo v4.3)

### 4.1 El modelo: venta ≠ cobro

Hay dos tablas separadas a propósito:

1. **`orders` = la venta (factura).** Se crea cuando Secretaría da de alta la
   orden. `total` es una columna generada `round(volumen_m3 * precio_m3, 2)`
   (`NULL` si no hay precio). Desde v4.3 tiene además:
   - `aplica_iva`, `iva_pct`, `iva_monto`;
   - `total_con_iva = total + iva_monto` (total bruto de la venta).
   `forma_pago` sigue siendo `EFECTIVO`, `TRANSFERENCIA`, `ABONO` o `FIADO`.
   Un `FIADO` factura igual, pero **no** significa dinero recibido.
2. **`payments` = el dinero que entra o sale de caja.** Cada fila es un
   movimiento con `tipo_movimiento`:
   - `COBRO` → dinero recibido.
   - `GASTO_CAJA_CHICA` → salida de caja chica.
   - `GASTO_BANCARIO` → salida desde banco.
   - `REEMBOLSO_CAJA` → devolución o reposición de caja.
   `metodo`: `EFECTIVO`, `TRANSFERENCIA` o `FIADO`. `bolsa` distingue
   `CAJA_DIARIA` de `BANCO_GERENCIA`; `account_id` enlaza la cuenta contable;
   `es_anticipo` marca cobros sin orden; `deleted_at` es borrado lógico.

El **cierre de caja** (`cash_closures` + `/api/v1/secretaria/cierre-caja`)
calcula:

- `ventas_*` = suma de `orders.total` del día por `forma_pago`.
- `cobros_*` = suma de `payments` con `tipo_movimiento = 'COBRO'` por método.
- `caja_chica` = suma de `payments` con `tipo_movimiento = 'GASTO_CAJA_CHICA'`.
- `efectivo_esperado` = `cobros EFECTIVO` − `caja_chica`.
- `diferencia` = `efectivo_contado` − `efectivo_esperado`.

### 4.2 Regla de negocio confirmada (2026-11-09)

1. **Venta de contado** (`EFECTIVO` o `TRANSFERENCIA`): al crear la orden se
   registra un `payments` tipo `COBRO` por el **total con IVA** y en la bolsa
   que corresponda. La venta no debe quedar como deuda.
2. **Venta con abono inicial** (`ABONO`): la orden guarda el total y se registra
   un `COBRO` por el abono inicial; el resto queda como saldo pendiente.
3. **Venta fiada** (`FIADO`): **no** genera `COBRO`. Aumenta la deuda del
   cliente y el cupo se evalúa sobre el total bruto. Si se excede, la orden se
   registra igual con `excede_cupo_credito = true`; no se bloquea.
4. **Cobro posterior:** un pago o abono nuevo se registra como `COBRO` con su
   método y bolsa. El pago con `deleted_at` no cuenta para caja ni para saldo.
5. **IVA:** las ventas nuevas usan el `iva_pct` de la receta (15 % en la semilla
   oficial). Los históricos anteriores al 2026-11-09 quedaron sin IVA
   (`total_con_iva = total`) hasta que Julio confirme el tratamiento retroactivo.
6. **Saldo del cliente:** `total_facturado − total_cobrado`, con
   `COALESCE(total_con_iva, total)` y sin sumar `FIADO` como cobrado. El
   resultado vive en `v_cliente_saldo`.

### 4.3 Flujo esperado, paso a paso

| Paso | Quién | Qué pasa | Regla v4.3 |
|---|---|---|---|
| 1 | Secretaría | Crea la orden con `POST /api/v1/secretaria/ordenes` o `POST /api/v1/orders` | Guarda `forma_pago`, `total`, IVA y `total_con_iva` |
| 2 | Servicio de órdenes | Calcula el IVA desde la receta confirmada | 15 % por defecto; el histórico queda sin IVA |
| 3 | Servicio de órdenes | Si es contado o abono, inserta el `COBRO` inicial | `EFECTIVO` → `CAJA_DIARIA`; `TRANSFERENCIA` → `BANCO_GERENCIA` |
| 4 | Secretaría | Registra cobros posteriores | `COBRO` con método, bolsa y referencia |
| 5 | Caja | Calcula el cierre del día | Ventas desde `orders`; cobros y gastos desde `payments` sin borrados |
| 6 | Dashboard | Lee cartera y saldo | `v_cliente_saldo` |
| 7 | Custodio | Asienta la partida doble | `Gate.mutar()` registra el asiento en la misma transacción; el pago inicial de una compra va en un asiento `SUPPLIER_PAYMENT` separado |

### 4.4 Estado real del código hoy

El código de ventas, caja, dashboard, kardex y el Custodio **ya consume v4.4**
desde el 2026-11-09. El circuito HTTP está cerrado con autenticación de
servicio y reglas oficiales:

| Pieza | Base v4.4 | Código actual | Qué falta |
|---|---|---|---|
| IVA en la orden | Columnas y CHECK listos | `crear_orden` lee `finanzas.iva_default_aplica` y el `iva_pct` de `concrete_recipes`, y escribe `aplica_iva`, `iva_pct`, `iva_monto` y `total_con_iva`; los históricos no se backfillean | Nada para ventas nuevas |
| COBRO automático de contado | `payments` acepta `COBRO`, bolsa y cuenta | `crear_orden` inserta el `COBRO` de `EFECTIVO`/`TRANSFERENCIA` y el abono inicial de `ABONO` en la misma transacción; `FIADO` no genera cobro | Nada para ventas nuevas |
| Endpoint de pagos/abonos | Tabla lista | `POST /api/v1/secretaria/pagos` acepta `COBRO`, `GASTO_CAJA_CHICA` y `GASTO_BANCARIO`; valida saldo, abono parcial y anticipo; es idempotente por `request_id`/`Idempotency-Key` | Formulario del panel (opcional) |
| Cierre de caja | `payments.deleted_at` disponible | `_movimientos()` filtra `deleted_at`; `ventas_*` usa `total_con_iva` con fallback a `total` | Nada |
| Dashboard | `v_cliente_saldo` ya usa bruto y filtra borrados | `hero_kpis()` y `flujo_operativo_mensual()` filtran `deleted_at`; `fiado_hoy` usa el bruto | Nada |
| Kardex | `ANULACION`, `costo_unitario_snapshot` y promedio disponibles | `kardex.py` calcula promedio ponderado en `COMPRA`, guarda `costo_unitario_snapshot` en todos los movimientos y anula `TEORICO` con una fila `ANULACION` idempotente; las correcciones físicas usan `AJUSTE` | Nada |
| Gate y testigo | Tablas, triggers y contratos v1.3.0 listos | `app/custodio/` implementa 14 intents, 9 consultas, idempotencia por `request_id` + SHA-256, partida doble, reversa del asiento vigente y testigo inmutable | Nada; expuesto por `/api/v1/custodio/*` |

**Consecuencia verificada hoy:** las 4 órdenes reales son la #9 histórica
(`total` y `total_con_iva` `NULL`, FIADO) y las #55/#56/#57 recreadas por los
candados con el código nuevo. Las tres tienen IVA 15 % explícito y bruto:
**$43,424.00**, **$9,448.40** y **$2,171.20**. La cartera sigue en
**55,043.60 / 2 clientes / fiado 55,043.60**. El fallback de la vista queda
solo para la #9 y para cualquier orden histórica sin bruto. Los costos de
materiales siguen en **8.2000 / 14.0000 / 16.5000 / 3.8000** y el stock en
**3,500 / 450 / 550 / 600**; ni el kardex ni el Custodio alteraron datos reales.

### 4.5 Cómo se registra un ingreso hoy

1. **Endpoint:** `POST /api/v1/secretaria/pagos` con
   `tipo_movimiento` (`COBRO`, `GASTO_CAJA_CHICA`, `GASTO_BANCARIO`),
   `cliente_id`, `order_id` (opcional), `fecha`, `metodo`, `bolsa`, `monto`,
   `referencia`, `descripcion` y `es_anticipo`.
2. **Idempotencia:** `request_id` es opcional y se genera si falta; para
   reintentos seguros se reenvía el mismo `request_id` o `Idempotency-Key`.
3. **Saldo:** si `monto > saldo_pendiente` y `es_anticipo=false`, el Gate
   rechaza con `PAYMENT_EXCEEDS_PENDING_BALANCE`. Si `es_anticipo=true`, la
   parte que cubre la deuda va a `1103` y el excedente a `2102`.
4. **Roles:** `SUPERADMIN`, `CONTADORA` y `SECRETARIA` pueden cobrar;
   `BODEGA` y `CHOFER` no.
5. **Autenticación:** tokens de servicio `CUSTODIO_TOKEN_*` + `X-Actor-Id` +
   `X-Channel`. No es login de usuario final.

La regla de contado/abono inicial/fiado sigue aplicada en `crear_orden`:
la venta de contado y el abono inicial generan su `COBRO` en la misma
transacción; el fiado no genera cobro.

---

## 5. ¿Quién es el responsable de la base de datos?

Esta es la parte que **no está documentada como designación formal**. Lo que
sí se puede probar:

| Rol | Quién / qué | Evidencia | Estado |
|---|---|---|---|
| **Cliente / dueño del negocio** | Julio Villavicencio (Orminorth, El Coca) | `docs/PDR_v4.0.txt` línea 5: "Cliente: Julio Villavicencio" | ✅ documentado |
| **Desarrollo técnico** | César Reyes (`CesarReyesJaramillo`) | Autor del repositorio y de los commits; `README.md` y `BITACORA.md` | ✅ documentado |
| **Custodio operativo de la BD en producción** | — | Sin designación en `docs/`, `.agents/` ni `README.md` | ⚠️ **PENDIENTE de confirmar** |
| **Responsable de datos de negocio** (recetas, precios, stock, teléfonos) | Julio | `00_DECISIONES_PENDIENTES.md` y bitácora lo nombran como dueño del dato | ✅ documentado |
| **DBA formal** | — | No existe la figura en ningún documento | ⚠️ **PENDIENTE** |

### Cómo interpretarlo hoy

- **Técnicamente**, el esquema y las migraciones los mantiene quien desarrolla
  (César Reyes). Es quien crea tablas, vistas, migraciones y quien puede
  reconstruir la base desde cero con `docker compose up` + migraciones.
- **Del negocio**, el dueño de los datos es Julio Villavicencio: él define
  precios, recetas, stock, cupos y quién puede cobrar.
- **En operación diaria**, la base la usan Secretaría/Caja (ventas y cobros),
  Bodega/Planta (kardex) y Gerencia (dashboard), pero **ninguno está designado
  formalmente como custodio de la BD**. Eso hay que confirmarlo contigo.

> Para cerrar esta sección necesito que confirmes: **¿quién responde por la
> base en el VPS de producción?** (¿tú, el proveedor del VPS, la agencia, o
> César?). Mientras no lo confirmes, queda marcado como pendiente.

---

## 6. Riesgos y pendientes técnicos

1. **Sin autenticación** en `/panel`, `/api/v1/secretaria/*` y
   `/api/v1/superadmin/*`. No exponer a Internet hasta implementar login.
2. **Sin respaldo automático documentado.** El volumen `orminorth-pgdata`
   persiste y existe un respaldo manual previo a v4.3
   (`.agents/evidencias/pre_v43_orminorth.dump`), pero no hay política
   automática de backup/restauración ni retención.
3. **Sin login de usuario final.** El router del Custodio usa tokens de
   servicio `CUSTODIO_TOKEN_*`; no hay login de Secretaría/Superadmin. No
   exponer el panel a Internet sin autenticación de usuario.
4. **Sin login de usuario final.** El panel ya tiene formularios de cobro,
   abono y gasto, y el endpoint `POST /api/v1/panel/pagos` funciona; falta el
   login y la protección de todas las rutas antes de exponerlo a Internet.
5. **Credenciales por defecto** (`orminorth`/`orminorth`). Antes de producción
   hay que cambiarlas en `.env`.
6. **`payments` vacía** (0 filas) y `cash_closures` vacía (0 filas). No es un
   error: las 3 órdenes reales de los candados son FIADO y el fiado no genera
   `COBRO`. El camino de contado/abono se verificó en el clon
   `orminorth_v43` con `scripts/refactor_v43_check.py`.
7. **IVA histórico resuelto.** La orden #9 (histórica) sigue con
   `total`/`total_con_iva` `NULL`; las órdenes #55/#56/#57 se crearon con IVA
   15 % explícito. No se backfillea ninguna orden anterior:
   `finanzas.iva_historico_pct = null` y `finanzas.iva_default_aplica = false`.
   Las ventas nuevas solo llevan IVA si el contrato envía `aplica_iva=true`.
8. **Fecha de conteo sin confirmar.** `materials.ultimo_levantamiento_at` sigue
   `NULL` en los 5 materiales; por eso `v_stock_proyectado` no aplica consumos
   teóricos y marca `SIN_FECHA_CONTEO`.
9. **Valoración/DSCR parametrizados.** Leen `finanzas.parametros_contables`.
   Si las tasas están `null`, devuelven la foto real y
   `UNCONFIRMED_FINANCIAL_RATES`; no se inventa una vista especulativa
   `v_valoracion_proyeccion_10y`.
10. **Rol `CONTADORA` habilitado.** `contabilidad.rol_contadora` queda activo;
    consulta reportes, ejecuta apertura/depreciación y cuentas, pero no aprueba
    solicitudes. `SECRETARIA` puede crear rubros solo si
    `secretaria_can_create_categories=true`.
11. **Reembolso y nota de crédito implementados.** Una anulación con cobros
    activos exige `modo_resolucion_cobro`; sin él la aprobación sigue
    `PENDING`. Una compra con inventario o varias líneas se rechaza con
    `PURCHASE_REQUIRES_CREDIT_NOTE` (Fase 1).

---

## 7. Cómo reconstruir la base desde cero

```powershell
# 1. Detener y borrar el volumen (destruye los datos)
docker compose down -v

# 2. Levantar de nuevo (PostgreSQL crea la base y la API migra)
docker compose up -d --build

# 3. Verificar
docker exec orminorth-postgres psql -U orminorth -d orminorth -c "SELECT version FROM schema_migrations ORDER BY version;"
```

Alternativa para migrar sin reiniciar:

```powershell
docker compose run --rm --no-deps core-api python scripts/db_migrate.py
```

---

## 8. Evidencia ejecutada (2026-11-09)

La evidencia completa está en
`.agents/evidencias/revision_v43_2026-11-09.txt`, con los logs separados de
pytest, candados, pruebas SQL y contratos. El refactor del código dejó además
`refactor_v43_check_2026-11-09.txt`, `pytest_refactor_v43_2026-11-09.txt`,
`hito1_lock_refactor_v43_2026-11-09.txt` y
`hito3_lock_refactor_v43_2026-11-09.txt`. El refactor del kardex agregó
`kardex_v43_check_2026-11-09.txt`, `pytest_kardex_v43_2026-11-09.txt`,
`hito1_lock_kardex_v43_2026-11-09.txt` y
`hito3_lock_kardex_v43_2026-11-09.txt`. Resumen de comandos y salida real:

```text
docker ps --filter name=orminorth
→ orminorth-postgres  Up 21 hours (healthy)  0.0.0.0:5433->5432/tcp
→ orminorth-core-api  Up 14 hours (healthy)  0.0.0.0:8000->8000/tcp
→ orminorth-redis     Up 21 hours (healthy)  0.0.0.0:6380->6379/tcp

SELECT version();
→ PostgreSQL 15.19 on x86_64-pc-linux-musl

SELECT version FROM schema_migrations ORDER BY version;
→ 13 filas: 001_init … 066_iva_default_v44
→ 063 y 064 aplicadas el 2026-11-09 12:50

SELECT count(*) FROM information_schema.tables
 WHERE table_schema='public' AND table_type='BASE TABLE';
→ 28

SELECT count(*) FROM pg_views WHERE schemaname='public';
→ 6

SELECT count(*) FROM accounting_accounts;
→ 26

SELECT numero, total, iva_pct, iva_monto, total_con_iva, forma_pago, creada_por
  FROM orders ORDER BY numero;
→ #9  (histórica, total/total_con_iva NULL, FIADO)
→ #49 $37,760.00 + IVA 5,664.00 = $43,424.00 (FIADO, hito1_lock_test)
→ #50  $8,216.00 + IVA 1,232.40 =  $9,448.40 (FIADO, hito1_lock_test)
→ #51  $1,888.00 + IVA   283.20 =  $2,171.20 (FIADO, hito3_lock_test)

SELECT sum(saldo_pendiente), count(*) FILTER (WHERE saldo_pendiente > 0),
       sum(total_fiado), sum(total_facturado), sum(total_cobrado)
  FROM v_cliente_saldo;
→ por_cobrar = 55,043.60 · clientes = 2 · fiado = 55,043.60
→ facturado = 55,043.60 · cobrado = 0.00 (las 3 órdenes reales son FIADO)

SELECT codigo, stock_real_fisico, stock_proyectado_disponible,
       estado_alerta_proyectada
  FROM v_stock_proyectado ORDER BY codigo;
→ AGUA NULL SIN_LEVANTAR
→ ARENA 450 / 450 SIN_FECHA_CONTEO
→ CEMENTO 3,500 / 3,500 SIN_FECHA_CONTEO
→ RETARDANTE 600 / 600 SIN_FECHA_CONTEO
→ RIPIO 550 / 550 SIN_FECHA_CONTEO

SELECT ordinal_position, column_name FROM information_schema.columns
 WHERE table_name='v_cliente_saldo';
→ 11 columnas: las 8 originales + ruc, credit_limit_usd, saldo_a_favor

docker compose run --rm --no-deps core-api python -m pytest /app/tests -q
→ 242 passed, EXIT=0

docker compose run --rm --no-deps core-api python scripts/hito1_lock_test.py
→ [CANDADO CERRADO], 235 movimientos de kardex, EXIT=0

docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py
→ [CANDADO CERRADO EN SANDBOX], EXIT=0

Refactor v4.3 en el clon orminorth_v43
→ scripts/refactor_v43_check.py: REFACTOR V4.3: OK
→ 4 ventas de 2 m³: EFECTIVO, TRANSFERENCIA y ABONO generan COBRO;
   FIADO no genera COBRO; IVA 15 % = 35.40 y bruto = 271.40
→ cartera: facturado 1,085.60 · cobrado 642.80 · fiado 271.40 ·
   saldo 442.80; pago con deleted_at baja el cobrado y sube el saldo
→ cierre y dashboard: el COBRO borrado no aparece; fiado_hoy usa el bruto
→ 0 registros de prueba al terminar (limpieza verificada)

Kardex v4.3 en el clon orminorth_v43
→ scripts/kardex_v43_check.py: KARDEX V4.3: OK
→ COMPRA 100 @ 8.20 + 100 @ 10.00 = costo promedio 9.1000
→ REAL -50 deja stock 150 y conserva el costo 9.1000
→ TEORICO guarda snapshot 8.2000 sin mover el stock físico del CEMENTO
→ ANULACION +10 devuelve el proyectado de 140 a 150 y es idempotente
→ una COMPRA no se puede anular con ANULACION (se remite a AJUSTE)
→ todos los movimientos de prueba tienen `costo_unitario_snapshot`
→ ROLLBACK total: 0 materiales y 0 movimientos de prueba al terminar

Custodio v4.4 en el clon orminorth_v43
→ scripts/custodio_v43_check.py: CUSTODIO V4.4: OK
→ 14/14 intents de mutación · 30 solicitudes (21 ACCEPT, 6 REJECT,
   3 PENDING) · 8 testigos (6 ACCEPT/2 REJECT) · 4 aprobaciones · 9 consultas
→ asiento de venta balanceado (CAJA/CxC + IVA + ingreso), cobro, gasto,
   compra a crédito con recepción parcial/completa, pago a proveedor,
   corrección con testigo, depreciación, cuota de préstamo, anulación con
   y sin cobros, anticipo con split 1103/2102, apertura de saldos y catálogo
→ ROLLBACK verificado: 17 tablas con el mismo conteo que antes

HTTP v4.4 en el clon orminorth_v43
→ scripts/http_gate_v44_check.py: HTTP GATE V4.4: OK
→ catalog 26 cuentas, mutations, queries, COBRO parcial, anticipo 200,
   gasto de caja chica, replay 200, hash distinto 409, sobrepago 422 y
   BODEGA sin permiso 403
→ ROLLBACK verificado: 17 tablas con el mismo conteo que antes

Pruebas SQL en el clon orminorth_v43
→ 7 guardas OK, 0 FALLO
→ venta contado+COBRO sin deuda fantasma; FIADO sí aumenta deuda;
   pago con deleted_at ignorado; TEORICO -10 baja a 3,490;
   ANULACION -10 devuelve a 3,500; balance y P&L cuadran

Contratos JSON v1.3.0
→ 4 esquemas válidos · 14/14 ramas de mutación · 9 consultas · 4 correcciones
→ rechazados: resistencia_fc entero, changes={}, REJECT sin códigos,
   P&L sin fechas y PENDING sin approval_request_id
```

**Respaldo previo a la migración:**
`.agents/evidencias/pre_v43_orminorth.dump` (54,571 bytes), generado con
`pg_dump -Fc` antes de aplicar `063` y `064`.

---

## 9. El historial de conversaciones por cliente (v6.8)

La pestaña **💬 Chat** del expediente no guarda nada en el navegador: todo el
historial vive en PostgreSQL, dentro de la misma base `orminorth`. Por eso
sobrevive a recargas, cambios de equipo y limpieza de caché, y el bot puede
leerlo con SQL o con la API sin depender del panel.

### 9.1 Dónde está

| Elemento | Nombre | Migración |
|---|---|---|
| Tabla de hilos | `public.chat_conversaciones` | `070_chat_clientes.sql` |
| Tabla de mensajes | `public.chat_mensajes` | `070_chat_clientes.sql` |
| Vista de resumen | `public.v_chat_conversacion` | `070_chat_clientes.sql` |
| API | `services/core-api/app/routers/chat_clientes.py` | código |
| UI | pestaña `💬 Chat` en `app/web/templates/panel.html` | código |

### 9.2 `chat_conversaciones` — una carpeta por cliente y canal

| Columna | Tipo | Para qué |
|---|---|---|
| `id` | `uuid` | Identificador del hilo |
| `cliente_id` | `uuid` FK → `clients(id)` | Dueño del expediente; borrar el cliente borra el hilo |
| `canal` | `text` | `PANEL`, `WHATSAPP`, `CRM` o `NOTA` |
| `asunto` | `text` | Título opcional |
| `estado` | `text` | `ABIERTA` o `ARCHIVADA` |
| `whatsapp_chat_id` | `text` | Chat remoto de Evolution API cuando se conecte |
| `ultimo_mensaje_at` | `timestamptz` | Lo mantiene el trigger |
| `ultimo_mensaje_preview` | `text` | Primeros 180 caracteres del último mensaje |
| `metadata` | `jsonb` | Espacio para datos del canal |

`UNIQUE (cliente_id, canal)`: hoy hay **un hilo continuo por cliente y canal**.
Es la metáfora de “una carpeta del cliente con un documento que muestra la
conversación”. Si más adelante se necesitan varios hilos por cliente, se quita
la restricción con una migración nueva; el código no depende de ella para leer.

### 9.3 `chat_mensajes` — el documento, append-only

| Columna | Tipo | Para qué |
|---|---|---|
| `id` | `uuid` | Identificador del mensaje |
| `conversacion_id` | `uuid` FK → `chat_conversaciones(id)` | Hilo al que pertenece |
| `direccion` | `text` | `ENTRANTE` (cliente → negocio) o `SALIENTE` (negocio → cliente) |
| `autor_tipo` | `text` | `CLIENTE`, `OPERADOR`, `BOT` o `SISTEMA` |
| `autor_nombre` | `text` | Nombre visible; en el panel sale del perfil ACL |
| `autor_usuario_id` | `text` | `panel_users_acl.id` cuando exista login; `NULL` si es externo |
| `cuerpo` | `text` | Texto del mensaje; `CHECK` no acepta vacíos |
| `adjuntos` | `jsonb` | Lista de adjuntos (URL/ID/tipo); hoy vacía |
| `whatsapp_msg_id` | `text` | Id de Evolution API para no duplicar al reingestar |
| `estado_entrega` | `text` | `PENDIENTE`, `ENVIADO`, `ENTREGADO`, `LEIDO`, `FALLIDO` |
| `leido_panel_at` | `timestamptz` | Cuándo lo leyó el panel (solo entrantes) |
| `metadata` | `jsonb` | Datos del canal |
| `created_at` | `timestamptz` | Sello de tiempo |
| `busqueda` | `tsvector` generado | `to_tsvector('spanish', cuerpo)` para búsqueda |

Índices:

| Índice | Para qué |
|---|---|
| `ux_chat_mensajes_whatsapp` (único parcial) | Idempotencia de WhatsApp: el mismo `whatsapp_msg_id` no entra dos veces |
| `ix_chat_mensajes_conv_fecha` | Leer el hilo en orden sin escanear la tabla |
| `ix_chat_mensajes_pendientes` (parcial) | Contar no leídos sin recorrer todo el historial |
| `ix_chat_mensajes_busqueda` (GIN) | Búsqueda full-text para el bot |
| `ix_chat_conversaciones_cliente` | Abrir la carpeta de un cliente |

El trigger `trg_chat_ultimo_mensaje` actualiza `ultimo_mensaje_at`,
`ultimo_mensaje_preview` y `updated_at` del hilo después de cada `INSERT`. No
hay `UPDATE` ni `DELETE` desde la API: el historial solo crece. Una corrección
futura debe ser un mensaje nuevo o una migración explícita.

### 9.4 Cómo lo lee el bot

1. **Historial completo de un cliente**:
   `GET /api/v1/clients/{cliente_id}/chat?canal=PANEL&limite=200`.
   Devuelve `resumen` (`total_mensajes`, `no_leidos`, último mensaje) y
   `mensajes` en orden cronológico.
2. **Búsqueda global**: `GET /api/v1/chat/buscar?q=Loreto&cliente_id=...`
   devuelve el fragmento con marcas `<< >>` y el nombre del cliente.
3. **SQL directo** (para procesos internos):
   ```sql
   SELECT m.created_at, m.direccion, m.autor_tipo, m.cuerpo
     FROM chat_mensajes m
     JOIN chat_conversaciones cv ON cv.id = m.conversacion_id
    WHERE cv.cliente_id = $1
    ORDER BY m.created_at;
   ```
4. **No leídos**: `SELECT no_leidos FROM v_chat_conversacion WHERE conversacion_id = $1;`

La API exige el módulo `clientes_cartera`; escribir exige `mutacion=True`
(perfil con `EDICION`). Los endpoints de escritura son
`POST .../chat/mensajes` y `POST .../chat/leido`.

### 9.5 Qué NO hace todavía

- **No envía WhatsApp**: solo guarda. El envío real llegará cuando se conecte
  Evolution API; el mismo endpoint aceptará `whatsapp_msg_id` y el índice único
  evitará duplicados si el webhook reintenta.
- **Adjuntos**: desde v6.9 el clip del chat sube fotos, videos, audios y
  documentos. Se comprimen y guardan en Bunny (o en el sandbox local si no hay
  credenciales) y el mensaje solo guarda la referencia `media_id`.
- **No hay borrado ni edición**: por diseño, el historial es append-only.
- **No hay login**: `autor_usuario_id` queda `NULL` con el perfil simulado;
  cuando exista login se llenará con `panel_users_acl.id`.

### 9.6 Multimedia del cliente (v6.9)

La migración `071_media_clientes.sql` agrega `clients.cedula` (NULL hasta que
Julio la cargue) y la tabla `media_assets`, que es el **índice** de archivos:

| Columna | Para qué |
|---|---|
| `cliente_id` | Dueño del archivo |
| `conversacion_id`, `mensaje_id` | Hilo y mensaje al que pertenece |
| `dispatch_id` | Viaje, si es evidencia de mixer |
| `tipo` | `IMAGEN`, `VIDEO`, `AUDIO`, `DOCUMENTO` |
| `backend` | `BUNNY` o `SANDBOX` |
| `storage_path` | Ruta canónica dentro del Storage Zone |
| `cdn_url` | URL sin firmar; la firmada se calcula al leer |
| `mime_final`, `bytes_final`, `ancho`, `alto`, `duracion_seg` | Ficha técnica |
| `sha256` | Integridad y futura deduplicación |
| `etiquetas` | Obra, orden, viaje, etapa |
| `metadata` | Origen y datos extra |

**Carpeta en Bunny:** `clientes/<nombre_cliente>_<cedula>/` y dentro archivos
planos con fecha y tipo. Lo demás (obra, orden, viaje) son **etiquetas JSONB**,
no subcarpetas. Si falta la cédula se usa RUC; si tampoco hay, el id del
cliente. El detalle y las reglas de tamaño, compresión y token están en
`docs/WHATSAPP_Y_MEDIA.md`.

**URL firmada:** `firmar_url_bunny()` en `app/services/media.py` agrega
`?token=...&expires=...` cuando existe `BUNNY_TOKEN_KEY`. La URL firmada no se
guarda en la base: se regenera al leer el hilo.

**Sandbox:** sin credenciales de Bunny el archivo comprimido va al volumen
`orminorth-media` (`/app/media_sandbox`) y se sirve por
`GET /api/v1/media/{id}/archivo`. Solo para desarrollo; producción usa Bunny.

### 9.7 Estado real hoy

Verificado el **2026-11-11**: migraciones `070` y `071` aplicadas, vista
`v_chat_conversacion` creada, `media_assets` en **0 filas** y `pytest` en
**291 passed**. Queda **1 mensaje** (“Hola”) que el usuario envió probando la
UI; se migró del canal `PANEL` al hilo `WHATSAPP` y quedó `PENDIENTE` porque
Evolution todavía no está conectado. No es un dato de negocio.

La prueba funcional de v6.8 envió desde el panel, insertó un entrante por API,
verificó el contador de no leídos, marcó leído y recuperó el hilo tras
recargar. La de v6.9 subió PNG (→ WebP ≤1920), WAV y MP4 (→ H.264 ≤180 s),
comprobó el índice y la descarga, y borró sus archivos al terminar:
`scripts/media_v69_check.py` → `MEDIA V6.9: OK`.

### 9.8 Facturas internas (v6.13)

La migración `073_facturas_internas.sql` crea `client_invoices`: un registro
interno por factura adjunta al cliente, con su PDF o foto en `media_assets`.
**No es facturación electrónica del SRI**; no hay clave de acceso, XML ni
autorización.

| Columna | Para qué |
|---|---|
| `cliente_id` | Dueño de la factura |
| `orden_id` | Venta de la que salen los montos; `NULL` si se cargó manual |
| `numero` | Número de factura; único por cliente |
| `fecha` | Fecha del documento |
| `subtotal`, `iva_pct`, `iva_monto`, `total` | Montos; la tabla exige `total = subtotal + iva_monto` |
| `estado` | `BORRADOR`, `EMITIDA` o `ANULADA` |
| `es_ficticia` | `true` = documento de prueba; el panel y Gato lo marcan **FICTICIA** |
| `nota` | Texto libre del documento |
| `media_id` | PDF o foto en `media_assets` |

La prueba del 2026-11-12 dejó **1 fila**: `PRUEBA-0001`, cliente Ing. Reyes,
orden #55, total **$43.424,00** con IVA. El PDF se genera con
`scripts/factura_prueba.py`; el nombre y los montos salen de la orden, no se
inventan. La factura se puede subir desde **Carpetas de Clientes > Facturas**
(PDF, JPG, PNG o WEBP) o con `POST /api/v1/clients/{id}/facturas`.

### 9.9 Memoria de Gato (v6.13.1)

La migración `074_gato_memoria.sql` crea `gato_turnos`: una fila por turno
(pregunta, respuesta, estado, actor y `conversacion_id`). El endpoint
`POST /api/v1/asistente/chat` devuelve el `conversacion_id`; el widget lo guarda
en `localStorage` por usuario y lo reenvía en cada mensaje. El backend carga los
últimos 8 turnos y los pasa como historial al LLM, así "descárgala" o "y el
saldo" se resuelven sin repetir el cliente. Si el `conversacion_id` pertenece a
otro actor, responde 403. La tabla es append-only y no guarda secretos.

---

## 10. Bancos y su detalle (v6.11)

La cabecera de **Banca y Mercado** dejó de ser decorativa: cada tarjeta abre
un detalle con saldo, préstamos y movimientos. El modelo no inventa cifras:
separa el **saldo contable** (libro mayor) del **saldo informado** (foto que
carga Gerencia).

### 10.1 `bank_accounts`

| Columna | Para qué |
|---|---|
| `slug` | `pichincha`, `guayaquil`, `internacional` |
| `nombre` | Nombre visible |
| `tipo_cuenta` | `CORRIENTE` o `AHORRO` |
| `numero_cuenta` | Número enmascarado; `NULL` = pendiente |
| `titular` | Titular de la cuenta |
| `moneda` | `USD` |
| `accounting_account_id` | Cuenta hija del plan contable |
| `saldo_informado` | Saldo que carga Gerencia; `NULL` hasta que exista |
| `saldo_informado_at` | Cuándo se actualizó ese saldo |
| `estado` | `ACTIVA`, `PENDIENTE` o `CERRADA` |

La migración `072` siembra las tres cuentas y crea las hijas contables
`1102.01 Banco Pichincha`, `1102.02 Banco Guayaquil` y `1102.03 Banco
Internacional`, colgadas de `1102 Bancos y Cuentas Gerencia`. El número de
Pichincha (`2100XXXXXX`) se copia de `empresa.bot_publico` si está presente;
no se escribe a mano.

### 10.2 De dónde sale cada número

| Dato | Fuente |
|---|---|
| Saldo contable | `v_balance_general.saldo_neto` de la cuenta hija |
| Saldo informado | `bank_accounts.saldo_informado` (editable) |
| Entradas / salidas | `payments` con `account_id` = cuenta hija y `deleted_at IS NULL` |
| Movimientos | Los mismos `payments`, últimos 50 |
| Préstamos | `financial_liabilities` por `bank_account_id` o por nombre de entidad |
| Cuota / plazo | `financial_liabilities.cuota_mensual_referencial` y `plazo_restante_meses` |

Si no hay movimientos o préstamos, la API devuelve listas vacías y la UI
muestra “Sin movimientos” o “Sin préstamos”. Nunca un cero que parezca saldo
real cuando no hay dato.

### 10.3 API y UI

- `GET /api/v1/dashboard/bancos` — catálogo con saldo contable y resumen.
- `GET /api/v1/dashboard/bancos/{slug}` — detalle con `resumen`, `prestamos` y `movimientos`.
- `PUT /api/v1/dashboard/bancos/{slug}` — número, tipo, estado, titular, notas y saldo informado; exige `finanzas_balance_auditoria` con mutación.
- UI: la tarjeta seleccionada se pinta en **amarillo** (mismo acento de las action cards); debajo aparece el detalle y el botón **Editar datos** abre el diálogo de la cuenta.

### 10.4 Estado real hoy

- 3 bancos sembrados; Pichincha con `#2100XXXXXX` (provisional).
- Saldo contable `$0.00`, saldo informado `NULL`, 0 préstamos y 0 movimientos.
- El flujo de edición se probó con un valor temporal y se limpió: la base queda sin saldos inventados.
- Para que un movimiento aparezca, el pago debe registrarse contra la cuenta hija del banco (`1102.01`/`02`/`03`). El formulario de pagos todavía usa `1102`; es la siguiente tarea de integración.

---

## 11. Documentos relacionados

- `docs/MODELO_DATOS.md` — descripción corta de las 34 tablas y 7 vistas.
- `db/migrations/001_init.sql` — esquema base.
- `db/migrations/060_modulos_3_4_sandbox.sql` — columnas M3/M4 y `sandbox_outbox`.
- `db/migrations/063_custodio_core.sql` — núcleo v4.3: IVA, pagos, plan de cuentas, compras, activos, pasivos, ledger y testigo.
- `db/migrations/064_custodio_views.sql` — `v_cliente_saldo` v4.3, stock proyectado, balance y estado de resultados.
- `db/migrations/065_http_gate_v44.sql` — parámetros v4.4.0 del router HTTP, pagos, reembolso y rol CONTADORA.
- `db/migrations/066_iva_default_v44.sql` — apaga el IVA por defecto; las ventas nuevas lo piden explícitamente.
- `db/migrations/067_operacion_compras_y_agenda.sql` — agenda de despachos y operación de compras.
- `db/migrations/068_agenda_config_y_usuarios_acl.sql` — configuración de agenda y usuarios simulados del panel.
- `db/migrations/069_clientes_sabueso.sql` — ciudad, obra frecuente e índice del buscador Sabueso.
- `db/migrations/070_chat_clientes.sql` — historial de conversaciones por cliente (sección 9).
- `db/migrations/071_media_clientes.sql` — cédula del cliente e índice `media_assets`.
- `db/migrations/072_bancos_detalle.sql` — catálogo `bank_accounts` y cuentas hijas por banco.
- `docs/WHATSAPP_Y_MEDIA.md` — decisión de WhatsApp como canal, carpetas de Bunny, token, límites y compresión.
- `services/core-api/app/routers/chat_clientes.py` — API del historial CHAT y de adjuntos.
- `services/core-api/app/services/media.py` — compresión, rutas y firma de Bunny.
- `services/core-api/app/m4_dashboard/bancos.py` — consultas de saldo, préstamos y movimientos por banco.
- `docs/BANCOS_PENDIENTES.md` — columnas, cierre de caja por banco y configuración de cuentas (traspaso).
- `docs/v4.4.0_HTTP_GATE.md` — contrato HTTP, tokens, pagos y decisiones oficiales.
- `docs/OPERACION_BACKUPS.md` — backup diario, retención y restauración de prueba.
- `.agents/skills/custodio-bd-horminor/contracts/` — contratos JSON v1.3.0 del Gate.
- `services/core-api/app/db.py` — runner de migraciones.
- `services/core-api/app/settings.py` — variables de conexión.
- `docker-compose.yml` — contenedor, volumen y puertos.
- `docs/00_DECISIONES_PENDIENTES.md` — datos de negocio que faltan.
