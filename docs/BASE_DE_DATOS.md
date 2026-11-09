# Base de datos — cómo está creada y quién responde por ella

> Última verificación: **2026-11-09**
> Evidencia: consultas ejecutadas contra `orminorth-postgres` (ver sección 8).
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

No hay migraciones pendientes: son **11 de 11**. La v4.3 del Custodio se
aplicó después de probarla en el clon `orminorth_v43` y de guardar el respaldo
`.agents/evidencias/pre_v43_orminorth.dump`.

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
| `accounting_accounts` | Plan de cuentas del Custodio | 26 |
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
| `schema_migrations` | Control del runner (no es de negocio) | 11 |

> **Nota:** `schema_migrations` la crea el runner, no una migración.
> `sandbox_outbox` la agrega `060_modulos_3_4_sandbox.sql`. Las 14 tablas del
> Custodio (`processed_requests` … `approval_requests`) las agrega
> `063_custodio_core.sql`.

### 3.2 Vistas

| Vista | Qué entrega |
|---|---|
| `v_cliente_saldo` | Por cliente: `id`, `nombre`, `estado`, `total_m3`, `total_facturado`, `total_cobrado`, `total_fiado`, `saldo_pendiente`, `ruc`, `credit_limit_usd` y `saldo_a_favor`. Conserva las 8 columnas originales y agrega 3 al final |
| `v_dispatch_timeline` | Un viaje de mixer con sus sellos de tiempo y veredictos del Juez |
| `v_inventario` | Stock físico por material y estado (`SIN_LEVANTAR`, `SIN_UMBRAL`, `CRITICO`, `OK`) |
| `v_stock_proyectado` | Stock físico + consumos `TEORICO` posteriores al último conteo; `ANULACION` se suma en valor absoluto. Sin fecha de conteo no aplica teóricos y marca `SIN_FECHA_CONTEO` |
| `v_balance_general` | Saldo por cada una de las 26 cuentas contables según su naturaleza; respeta `merged_into_id` sin reescribir el libro mayor |
| `v_estado_resultados` | Ingresos y gastos agrupados por mes y cuenta para el estado de resultados |

**Compatibilidad de `v_cliente_saldo`:** la vista usa
`COALESCE(total_con_iva, total)` para `total_facturado` y `total_fiado`. Así una
orden creada por el código actual —que todavía no escribe `total_con_iva`— no
desaparece del saldo. `total_cobrado` solo suma `payments` con
`tipo_movimiento = 'COBRO'`, `metodo <> 'FIADO'` y `deleted_at IS NULL`.

La definición de las 3 vistas originales está en `db/migrations/001_init.sql`;
las 3 nuevas y la versión v4.3 de `v_cliente_saldo` están en
`db/migrations/064_custodio_views.sql`. Se pueden releer con `\d+ <vista>` o
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
| 7 | Custodio | Asienta la partida doble | Pendiente de implementar el Gate |

### 4.4 Estado real del código hoy

La base ya soporta el modelo v4.3, pero **el código todavía no lo usa
completo**. Esta separación es deliberada para no documentar como hecho algo
que aún no ocurre:

| Pieza | Base v4.3 | Código actual | Qué falta |
|---|---|---|---|
| IVA en la orden | Columnas y CHECK listos | `crear_orden` no escribe `aplica_iva`, `iva_pct`, `iva_monto` ni `total_con_iva`; las órdenes nuevas quedan con los defaults | Refactorizar `services/core-api/app/services/ordenes.py` |
| COBRO automático de contado | `payments` acepta `COBRO`, bolsa y cuenta | `crear_orden` no inserta ningún `payments` | Refactorizar `crear_orden` dentro de la misma transacción |
| Endpoint de pagos/abonos | Tabla lista | No existe `POST /api/v1/secretaria/pagos` | Implementar router + reglas de abono parcial y permisos |
| Cierre de caja | `payments.deleted_at` disponible | `_movimientos()` no filtra `deleted_at`; `ventas_*` usa `orders.total` (neto) | Filtrar borrados y decidir si el cierre muestra bruto o neto |
| Dashboard | `v_cliente_saldo` ya usa bruto y filtra borrados | `hero_kpis()` y `flujo_operativo_mensual()` consultan `payments` sin `deleted_at` | Agregar el filtro |
| Kardex | `ANULACION`, `costo_unitario_snapshot` y promedio disponibles | `kardex.py` solo inserta `TEORICO`, `REAL`, `COMPRA` y `AJUSTE`; no calcula promedio ni anulación | Refactorizar kardex y recepción de compras |
| Gate y testigo | Tablas, triggers y contratos v1.3.0 listos | No existe `gate.py`, `witness.py` ni `catalog_hygiene.py` | Implementar los servicios y sus pruebas |

**Consecuencia verificada hoy:** las 4 órdenes reales tienen
`total_con_iva = NULL` porque 3 las recrearon los candados con el código
anterior y la #9 es histórica. La vista usa el fallback y sigue mostrando
**47,864 / 2 clientes / fiado 47,864**. En cuanto se refactorice `crear_orden`,
las ventas nuevas escribirán el bruto y el fallback quedará solo para históricos.

### 4.5 Qué falta para registrar ingresos desde la aplicación

1. **Endpoint** `POST /api/v1/secretaria/pagos` (o `/cobros`) con:
   `cliente_id`, `order_id` (opcional), `fecha`, `metodo`, `bolsa`, `monto`,
   `referencia` y `es_anticipo`.
2. **Regla de abono parcial:** confirmar si se permite y si se valida contra
   `v_cliente_saldo` antes de insertar.
3. **Formulario** en la vista de Secretaría para capturarlo.
4. **Permisos:** hoy `/api/v1/secretaria/*` no tiene login.

Sin esas definiciones no se implementa el endpoint, para no inventar reglas de
cobro. La regla de contado/abono inicial/fiado ya está confirmada y se aplicará
en el refactor de `crear_orden`.

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
3. **Código desactualizado respecto de la base v4.3.** `crear_orden` todavía no
   escribe IVA/`total_con_iva` ni inserta el `COBRO` de contado; caja y dashboard
   no filtran `payments.deleted_at`; el kardex no maneja `ANULACION` ni costo
   promedio. La tabla completa está en la sección 4.4.
4. **Sin endpoint de pagos/abonos** (sección 4.5). Mientras no exista, un cobro
   posterior solo se puede insertar por SQL.
5. **Credenciales por defecto** (`orminorth`/`orminorth`). Antes de producción
   hay que cambiarlas en `.env`.
6. **`payments` vacía** (0 filas) y `cash_closures` vacía (0 filas): la lógica
   existe, pero aún no hay cobros reales registrados.
7. **IVA histórico sin confirmar.** Las órdenes anteriores al 2026-11-09 y las
   que recrean los candados tienen `total_con_iva = NULL`; la vista las muestra
   con fallback, pero Julio debe decidir si se backfillean al 15 %.
8. **Fecha de conteo sin confirmar.** `materials.ultimo_levantamiento_at` sigue
   `NULL` en los 5 materiales; por eso `v_stock_proyectado` no aplica consumos
   teóricos y marca `SIN_FECHA_CONTEO`.
9. **Fórmula de valoración/DSCR sin confirmar.** El PDR describe escenarios y
   parámetros, pero no la fórmula completa; no se creó una vista especulativa
   `v_valoracion_proyeccion_10y`.
10. **Rol `CONTADORA` inexistente.** La base no tiene ese rol; falta decidir si
    se agrega o si el Custodio queda solo en `SUPERADMIN`.

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
pytest, candados, pruebas SQL y contratos. Resumen de comandos y salida real:

```text
docker ps --filter name=orminorth
→ orminorth-postgres  Up 21 hours (healthy)  0.0.0.0:5433->5432/tcp
→ orminorth-core-api  Up 14 hours (healthy)  0.0.0.0:8000->8000/tcp
→ orminorth-redis     Up 21 hours (healthy)  0.0.0.0:6380->6379/tcp

SELECT version();
→ PostgreSQL 15.19 on x86_64-pc-linux-musl

SELECT version FROM schema_migrations ORDER BY version;
→ 11 filas: 001_init … 064_custodio_views
→ 063 y 064 aplicadas el 2026-11-09 12:50

SELECT count(*) FROM information_schema.tables
 WHERE table_schema='public' AND table_type='BASE TABLE';
→ 28

SELECT count(*) FROM pg_views WHERE schemaname='public';
→ 6

SELECT count(*) FROM accounting_accounts;
→ 26

SELECT numero, total, total_con_iva, forma_pago, estado, creada_por
  FROM orders ORDER BY numero;
→ #9  (histórica, total NULL, FIADO)
→ #37 $37,760.00 (total_con_iva NULL, FIADO, hito1_lock_test)
→ #38  $8,216.00 (total_con_iva NULL, FIADO, hito1_lock_test)
→ #39  $1,888.00 (total_con_iva NULL, FIADO, hito3_lock_test)

SELECT sum(saldo_pendiente), count(*) FILTER (WHERE saldo_pendiente > 0),
       sum(total_fiado)
  FROM v_cliente_saldo;
→ por_cobrar = 47,864.00 · clientes = 2 · fiado = 47,864.00

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
→ 180 passed, EXIT=0

docker compose run --rm --no-deps core-api python scripts/hito1_lock_test.py
→ [CANDADO CERRADO], 235 movimientos de kardex, EXIT=0

docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py
→ [CANDADO CERRADO EN SANDBOX], EXIT=0

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

## 9. Documentos relacionados

- `docs/MODELO_DATOS.md` — descripción corta de las 12 tablas y vistas.
- `db/migrations/001_init.sql` — esquema base.
- `db/migrations/060_modulos_3_4_sandbox.sql` — columnas M3/M4 y `sandbox_outbox`.
- `db/migrations/063_custodio_core.sql` — núcleo v4.3: IVA, pagos, plan de cuentas, compras, activos, pasivos, ledger y testigo.
- `db/migrations/064_custodio_views.sql` — `v_cliente_saldo` v4.3, stock proyectado, balance y estado de resultados.
- `.agents/skills/custodio-bd-horminor/contracts/` — contratos JSON v1.3.0 del Gate.
- `services/core-api/app/db.py` — runner de migraciones.
- `services/core-api/app/settings.py` — variables de conexión.
- `docker-compose.yml` — contenedor, volumen y puertos.
- `docs/00_DECISIONES_PENDIENTES.md` — datos de negocio que faltan.
