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

No hay migraciones pendientes: son 9 de 9.

---

## 3. Qué existe en la base hoy (verificado)

### 3.1 Tablas

| Tabla | Para qué | Filas hoy |
|---|---|---|
| `system_settings` | Parámetros maestros `key → value` (JSONB) | 29 |
| `plants` | Plantas fija y móvil | 2 |
| `concrete_recipes` | Dosificación por resistencia | 5 |
| `clients` | Clientes y prospectos | 6 |
| `orders` | Orden de hormigón (la venta) | 4 |
| `mixer_dispatches` | Viajes de mixer | 51 |
| `materials` | Stock real por material | — |
| `inventory_movements` | Kardex (teórico / real / compra / ajuste) | — |
| `payments` | Cobros y gastos de caja chica | 0 |
| `cash_closures` | Cierre de caja diario (snapshot) | 0 |
| `market_benchmarks` | Benchmarks de mercado Orellana/Sucumbíos | — |
| `error_logs` | Errores del sistema | — |
| `sandbox_outbox` | Cola de salida del modo SANDBOX | — |
| `schema_migrations` | Control del runner (no es de negocio) | 9 |

> **Nota:** `schema_migrations` la crea el runner, no una migración.
> `sandbox_outbox` la agrega `060_modulos_3_4_sandbox.sql`.

### 3.2 Vistas

| Vista | Qué entrega |
|---|---|
| `v_cliente_saldo` | Por cliente: `total_m3`, `total_facturado`, `total_cobrado`, `total_fiado`, `saldo_pendiente` |
| `v_dispatch_timeline` | Un viaje de mixer con sus sellos de tiempo y veredictos del Juez |
| `v_inventario` | Stock por material y estado (`SIN_LEVANTAR`, `SIN_UMBRAL`, `CRITICO`, `OK`) |

La definición completa está en `db/migrations/001_init.sql` y se puede
releer con `\d+ <vista>` o `pg_get_viewdef()`.

---

## 4. Cómo se registra un ingreso (lo que preguntaste)

### 4.1 El modelo: venta ≠ cobro

Hay dos tablas separadas a propósito:

1. **`orders` = la venta (factura).** Se crea cuando Secretaría da de alta la
   orden. Su `total` es una columna generada `volumen_m3 * precio_m3`
   (`NULL` si no hay precio). Tiene `forma_pago`:
   `EFECTIVO`, `TRANSFERENCIA`, `ABONO`, `FIADO`.
   Un `FIADO` factura igual, pero **no** significa dinero recibido.
2. **`payments` = el dinero que entra o sale de caja.** Cada fila es un
   movimiento con `tipo_movimiento`:
   - `COBRO` → dinero recibido (efectivo, transferencia o fiado).
   - `GASTO_CAJA_CHICA` → salida de caja chica.
   Y `metodo`: `EFECTIVO`, `TRANSFERENCIA`, `FIADO`.

El **cierre de caja** (`cash_closures` + `/api/v1/secretaria/cierre-caja`)
calcula:

- `ventas_*` = suma de `orders.total` del día por `forma_pago`.
- `cobros_*` = suma de `payments` con `tipo_movimiento = 'COBRO'` por método.
- `caja_chica` = suma de `payments` con `tipo_movimiento = 'GASTO_CAJA_CHICA'`.
- `efectivo_esperado` = `cobros EFECTIVO` − `caja_chica`.
- `diferencia` = `efectivo_contado` − `efectivo_esperado`.

### 4.2 Flujo actual, paso a paso

| Paso | Qué pasa | Estado |
|---|---|---|
| 1 | Secretaría crea la orden con `POST /api/v1/secretaria/ordenes` o `POST /api/v1/orders` | ✅ funciona |
| 2 | La orden guarda `forma_pago` y `total`; si es `FIADO`, se marca y se cruza el cupo de crédito | ✅ funciona |
| 3 | El cobro real (abono o pago total) debería registrarse en `payments` | ❌ **no hay endpoint POST** |
| 4 | Secretaría ve los cobros en modo lectura y hace el cierre de caja | ✅ funciona |
| 5 | Cartera y saldo por cliente salen de `v_cliente_saldo` | ✅ funciona |

**La brecha real:** hoy se puede crear la venta, pero **no existe un endpoint
para registrar un pago o abono nuevo**. `payments` está creada y las vistas la
consumen, pero la única forma de insertar un cobro es manual (SQL) o todavía no
existe desde la interfaz. Por eso el panel muestra los cobros en **solo
lectura**.

### 4.3 Qué falta para registrar ingresos desde la aplicación

Decisión pendiente contigo, no una suposición:

1. **Endpoint** `POST /api/v1/secretaria/pagos` (o `/cobros`) con:
   `cliente_id`, `order_id` (opcional), `fecha`, `tipo_movimiento`,
   `metodo`, `monto`, `referencia`.
2. **Regla de negocio:** si el cobro es `EFECTIVO`/`TRANSFERENCIA`, ¿se
   permite abonar parcial? ¿Se valida contra el saldo de `v_cliente_saldo`?
3. **Formulario** en la vista de Secretaría para capturarlo.
4. **Permisos:** hoy `/api/v1/secretaria/*` no tiene login.

Sin esas definiciones no se implementa, para no inventar reglas de cobro.

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
   persiste, pero no hay política de backup/restauración escrita.
3. **Sin endpoint de pagos/abonos** (sección 4.3).
4. **Credenciales por defecto** (`orminorth`/`orminorth`). Antes de producción
   hay que cambiarlas en `.env`.
5. **`payments` vacía** (0 filas) y `cash_closures` vacía (0 filas): la lógica
   existe, pero aún no hay cobros reales registrados.

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

Comandos y salida real:

```text
docker ps
→ orminorth-postgres   Up 18 hours (healthy)   0.0.0.0:5433->5432/tcp
→ orminorth-core-api   Up 10 hours (healthy)   0.0.0.0:8000->8000/tcp

docker exec orminorth-postgres psql -U orminorth -d orminorth -c "SELECT version();"
→ PostgreSQL 15.19 on x86_64-pc-linux-musl

SELECT version FROM schema_migrations ORDER BY version;
→ 9 filas (001 a 062), última aplicada 2026-11-08 21:35

SELECT table_name, table_type FROM information_schema.tables WHERE table_schema='public';
→ 14 BASE TABLE + 3 VIEW

SELECT count(*) FROM payments;   → 0
SELECT count(*) FROM orders;     → 4
SELECT count(*) FROM clients;    → 6
SELECT count(*) FROM mixer_dispatches; → 51

\d payments
→ tipo_movimiento CHECK IN ('COBRO','GASTO_CAJA_CHICA')
→ metodo CHECK IN ('EFECTIVO','TRANSFERENCIA','FIADO')
→ monto > 0
```

---

## 9. Documentos relacionados

- `docs/MODELO_DATOS.md` — descripción corta de las 12 tablas y vistas.
- `db/migrations/001_init.sql` — esquema base.
- `db/migrations/060_modulos_3_4_sandbox.sql` — columnas M3/M4 y `sandbox_outbox`.
- `services/core-api/app/db.py` — runner de migraciones.
- `services/core-api/app/settings.py` — variables de conexión.
- `docker-compose.yml` — contenedor, volumen y puertos.
- `docs/00_DECISIONES_PENDIENTES.md` — datos de negocio que faltan.
