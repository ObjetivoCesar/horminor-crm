# Proceso 01 — Arrancar el entorno local

Requisitos: Docker Desktop, PowerShell. No hace falta Python instalado en el
host: todo corre en contenedores.

## 1. Verificar que el motor de Docker responde

```powershell
docker info
```

Si falla con `open //./pipe/dockerDesktopLinuxEngine: El sistema no puede
encontrar el archivo especificado`, Docker Desktop no está corriendo:

```powershell
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
# esperar a que el engine responda (suele tardar 30–60 s)
```

## 2. Crear `.env` (solo la primera vez)

```powershell
Copy-Item .env.example .env
```

Revisar `AGENCY_MASTER_KEY`. Mientras siga en `change-me`, el endpoint del
Centinela responde `503` a propósito.

## 3. Levantar

```powershell
docker compose up -d --build
docker ps --filter name=orminorth --format "{{.Names}}  {{.Status}}"
```

Se esperan tres contenedores `healthy`: `orminorth-postgres`,
`orminorth-redis`, `orminorth-core-api`.

Las migraciones se aplican solas al arrancar la API (`AUTO_MIGRATE=true`).

## 4. Verificar

```powershell
Invoke-RestMethod http://localhost:8000/health
docker compose run --rm --no-deps core-api python scripts/db_migrate.py
```

`db_migrate.py` debe decir "Sin migraciones pendientes".

## 5. Servicios

| Servicio | URL / host |
|---|---|
| API + Swagger | `http://localhost:8000/docs` |
| PostgreSQL | `localhost:5433` — usuario/base `orminorth` |
| Redis | `localhost:6380` |

## Operaciones frecuentes

```powershell
# logs de la API en vivo
docker compose logs -f core-api

# reiniciar solo la API (no toca la base)
docker compose restart core-api

# apagar conservando datos
docker compose stop

# BORRAR TODO (base incluida) — solo en local y con intención
docker compose down -v
```

## Troubleshooting conocido

| Síntoma | Causa | Solución |
|---|---|---|
| `pipe dockerDesktopLinuxEngine` no existe | Docker Desktop apagado | Iniciarlo y esperar |
| Puerto 5433/6380/8000 ocupado | Otro servicio local | Cambiar el puerto en `.env` |
| La API arranca y muere | Error de importación o migración | `docker compose logs core-api` |
| `503` en daily-audit | Clave maestra por defecto | Cambiar `AGENCY_MASTER_KEY` en `.env` y reiniciar |
| `psql` no existe en el host | No está instalado | Usar `docker exec -it orminorth-postgres psql -U orminorth -d orminorth` |
