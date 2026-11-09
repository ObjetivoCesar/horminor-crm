# HORMINOR — Núcleo Centinela (Hitos 1, 2 y 3)

> La marca visible es **HORMINOR**. La carpeta y los nombres de contenedores
> conservan `orminorth` por compatibilidad con los comandos ya documentados.

Implementación del **Módulo 0 (PostgreSQL + JSONB)**, **Módulo 1 (WhatsApp:
debounce + Juez Binario + Bunny.net)**, **Módulo 2 (motor determinístico de
planta)**, **Módulo 3 (Secretaría + Caja)**, **Módulo 4 (Dashboard gerencial)**
y **Módulo 5 (Nodo Centinela)** del PDR v4.0.

Estado actual: **Hitos 1, 2 y 3 construidos y verificados en local** (**242
tests**, candado del Hito 1 **CERRADO** y candado del Hito 3 **CERRADO EN
SANDBOX**). El Hito 1 quedó cerrado con la semilla oficial de Dirección (5
recetas confirmadas) y el **Centro de Configuración Superadmin** de 7 secciones,
editable en caliente. El Custodio v4.4.0 ya expone el Gate y la ventanilla de
pagos por HTTP con tokens de servicio. La producción real solo espera
credenciales de Evolution/Bunny/Gemini, los teléfonos del personal y el login de
usuario final. Ver `docs/00_DECISIONES_PENDIENTES.md` y
`docs/v4.4.0_HTTP_GATE.md`.

## Estructura

```
orminorth/
├─ docker-compose.yml          postgres 15 + redis 7 + core-api
├─ db/migrations/              SQL versionado (se aplica solo al arrancar)
│  ├─ 001_init.sql             esquema (12 tablas + 3 vistas de contrato)
│  ├─ 010_seed_settings.sql    parámetros maestros (system_settings)
│  ├─ 020_seed_recipes.sql     recetas + materiales (con datos PENDIENTES marcados)
│  ├─ 030_umbral_termico.sql   parámetro de aviso térmico (legado)
│  ├─ 040_ratificacion_hito3.sql  dos umbrales térmicos + códigos de operador
│  ├─ 050_seed_oficial_superadmin.sql  semilla oficial + Centro de Configuración
│  ├─ 060_modulos_3_4_sandbox.sql  tablas M3/M4 + modo SANDBOX
│  ├─ 061_benchmarks_limpieza.sql  limpieza de benchmarks heredados
│  └─ 062_rebrand_horminor.sql     corrección de marca (Horminor)
├─ services/core-api/
│  ├─ app/m1_whatsapp/         webhook, debounce, identidad, Juez "Jeb", Bunny
│  ├─ app/m2_planta/           motor determinístico (dosificador, kardex)
│  ├─ app/m3_secretaria/       ventanilla, carpeta forense y cierre de caja
│  ├─ app/m4_dashboard/        KPIs, cuota de mercado, simulador y dossier
│  ├─ app/superadmin/          configuración en caliente (7 secciones, sin login)
│  ├─ app/m5_sentinel/         salud de infraestructura, canales y operación
│  ├─ app/web/                 panel HTML en `/panel` + estáticos (Poppins, logo)
│  ├─ app/services/            alta de órdenes (M0 + M2)
│  ├─ app/custodio/            Gate contable, ledger, testigo y catálogo
│  ├─ app/http_gate/           router HTTP, tokens y ventanilla de pagos
│  ├─ app/routers/             health, catálogo, órdenes
│  └─ tests/                   pytest (242 tests)
├─ scripts/
│  ├─ db_migrate.py            aplica migraciones a mano
│  ├─ hito1_lock_test.py       Test de Candado del Hito 1 (pedido Ing. Reyes)
│  ├─ hito3_lock_test.py       Test de Candado del Hito 3 (3 celulares simulados)
│  ├─ custodio_v43_check.py    integración del Custodio en el clon (ROLLBACK)
│  └─ http_gate_v44_check.py   integración HTTP v4.4.0 en el clon (ROLLBACK)
└─ docs/                       decisiones pendientes y modelo de datos
```

## Arranque

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

- API: http://localhost:8000/docs
- PostgreSQL: `localhost:5433` (usuario/base `orminorth`)
- Redis: `localhost:6380`

## Tests

```powershell
# unitarios de los Módulos 1, 2 y 5 (sin base de datos)
docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto

# Test de Candado del Hito 1 contra la base real
docker compose run --rm --no-deps core-api python scripts/hito1_lock_test.py

# mismo test calculando el kardex con la receta provisional derivada del PDR
docker compose run --rm --no-deps core-api python scripts/hito1_lock_test.py --provisional

# Test de Candado del Hito 3: bodega, chofer y cliente contra PostgreSQL real
docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py
```

## Endpoints

| Método | Ruta | Uso |
|---|---|---|
| GET | `/health` | salud simple de la API y la base |
| GET | `/api/v1/clients?q=` | clientes con saldo (fiado) |
| POST | `/api/v1/clients` | alta de cliente / prospecto |
| GET | `/api/v1/orders` | órdenes con filtros |
| POST | `/api/v1/orders` | crea orden + viajes + kardex teórico |
| GET | `/api/v1/orders/{id}` | orden + timeline de viajes |
| GET | `/api/v1/inventory` | stock y estado de alerta |
| POST | `/api/v1/whatsapp/webhook` | recibe eventos de Evolution API (responde de inmediato) |
| POST | `/api/v1/whatsapp/simulate` | inyecta un mensaje para QA (header `X-Agency-Master-Key`) |
| POST | `/api/v1/whatsapp/flush` | fuerza el procesamiento del debounce (header `X-Agency-Master-Key`) |
| GET | `/api/v1/whatsapp/health` | estado del Módulo 1 sin exponer secretos |
| GET | `/api/v1/sentinel/daily-audit` | diagnóstico para el CRM de la agencia (header `X-Agency-Master-Key`) |

## Memoria del proyecto (`.agents/`)

Este repositorio está pensado para trabajarse en sesiones de varios días. Antes
de tocar nada:

1. `AGENTS.md` — reglas de trabajo.
2. `.agents/ESTADO.md` — en qué va el proyecto y qué está bloqueado.
3. `.agents/BITACORA.md` — qué pasó la última vez.

Al terminar, toda sesión se registra en la bitácora. Si no está ahí, no pasó.
Índice completo en `.agents/README.md`.

## Principios que el código respeta

1. **Nada de negocio en el código.** Recetas, precios, teléfonos, flota y umbrales viven en `system_settings` / `concrete_recipes`.
2. **El JSONB es el contrato.** `mixer_dispatches.tracking_payload` manda; las columnas planas las sincroniza un trigger y existen solo para consultar.
3. **La IA no calcula.** El Módulo 2 es aritmética con `Decimal`. El Juez Binario solo responde sí/no; la matemática nunca pasa por un LLM. Una receta provisional no bloquea la venta, pero el kardex no se genera y el Centinela lo reporta como WARNING.
4. **El Centinela no tumba la API.** Cada chequeo degrada a `NO_CONFIGURADO` en vez de lanzar excepciones.
5. **Sin credenciales no se finge.** Evolution, Bunny y Gemini degradan a `NO_CONFIGURADO` o al juez determinístico, y las alertas quedan en `error_logs`.
