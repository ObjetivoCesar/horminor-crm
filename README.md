# ORMINORTH — Núcleo Centinela (Hitos 1 y 2)

Implementación del **Módulo 0 (PostgreSQL + JSONB)**, **Módulo 2 (motor determinístico de planta)** y **Módulo 5 (Nodo Centinela)** del PDR v4.0.

Estado actual: **Hito 1 ejecutado localmente**. La estructura responde y los tests pasan; el candado definitivo depende de que Julio entregue las recetas reales (ver `docs/00_DECISIONES_PENDIENTES.md`).

## Estructura

```
orminorth/
├─ docker-compose.yml          postgres 15 + redis 7 + core-api
├─ db/migrations/              SQL versionado (se aplica solo al arrancar)
│  ├─ 001_init.sql             esquema (12 tablas + 3 vistas de contrato)
│  ├─ 010_seed_settings.sql    parámetros maestros (system_settings)
│  ├─ 020_seed_recipes.sql     recetas + materiales (con datos PENDIENTES marcados)
│  └─ 030_umbral_termico.sql   parámetro de aviso térmico
├─ services/core-api/
│  ├─ app/m2_planta/           motor determinístico (dosificador, kardex)
│  ├─ app/m5_sentinel/         salud de infraestructura, canales y operación
│  ├─ app/services/            alta de órdenes (M0 + M2)
│  ├─ app/routers/             health, catálogo, órdenes
│  └─ tests/                   pytest
├─ scripts/
│  ├─ db_migrate.py            aplica migraciones a mano
│  └─ hito1_lock_test.py       Test de Candado del Hito 1 (pedido Ing. Reyes)
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
# unitarios del motor (sin base de datos)
docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto

# Test de Candado del Hito 1 contra la base real
docker compose run --rm --no-deps core-api python scripts/hito1_lock_test.py

# mismo test calculando el kardex con la receta provisional derivada del PDR
docker compose run --rm --no-deps core-api python scripts/hito1_lock_test.py --provisional
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
| GET | `/api/v1/sentinel/daily-audit` | diagnóstico para el CRM de la agencia (header `X-Agency-Master-Key`) |

## Memoria del proyecto (`.agents/`)

Este repositorio está pensado para trabajarse en sesiones de varios días. Antes
de tocar nada:

1. `AGENTS.md` — reglas de trabajo.
2. `.agents/ESTADO.md` — en qué va el proyecto y qué está bloqueado.
3. `.agents/BITACORA.md` — qué pasó la última vez.

Al terminar, toda sesión se registra en la bitácora. Si no está ahí, no pasó.
Índice completo en `.agents/README.md`.

## Principios que el código respeta1. **Nada de negocio en el código.** Recetas, precios, teléfonos, flota y umbrales viven en `system_settings` / `concrete_recipes`.
2. **El JSONB es el contrato.** `mixer_dispatches.tracking_payload` manda; las columnas planas las sincroniza un trigger y existen solo para consultar.
3. **La IA no calcula.** El Módulo 2 es aritmética con `Decimal`; si una receta no está confirmada, el motor se niega a operar.
4. **El Centinela no tumba la API.** Cada chequeo degrada a `NO_CONFIGURADO` en vez de lanzar excepciones.
