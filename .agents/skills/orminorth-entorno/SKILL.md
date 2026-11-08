---
name: orminorth-entorno
description: Levanta, reinicia o verifica el stack local de Orminorth (PostgreSQL, Redis y FastAPI en Docker). Usar cuando los contenedores no responden, hay que arrancar el proyecto, cambió el .env o hay que comprobar salud antes de trabajar.
---

# Skill: entorno local de Orminorth

Trabajar siempre desde la carpeta `orminorth/`.

## Diagnóstico rápido

```powershell
docker ps --filter name=orminorth --format "{{.Names}}  {{.Status}}"
```

- Tres contenedores `Up ... (healthy)` → listo, no tocar nada.
- `open //./pipe/dockerDesktopLinuxEngine` → Docker Desktop está apagado:

```powershell
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
# esperar 30–60 s y repetir docker info
```

## Levantar / reconstruir

```powershell
docker compose up -d --build
docker compose logs -f core-api   # Ctrl+C para salir
```

La API aplica migraciones pendientes al arrancar. Si la API muere, el log dice
por qué (import roto o SQL inválido).

## Verificar que quedó bien

```powershell
Invoke-RestMethod http://localhost:8000/health
docker compose run --rm --no-deps core-api python scripts/db_migrate.py
```

Esperado: `{"status":"ok","db":"ok",...}` y "Sin migraciones pendientes".

## Reinicios selectivos

```powershell
docker compose restart core-api     # no toca la base
docker compose stop                 # apaga conservando datos
docker compose down -v              # BORRA la base (solo local, con intención)
```

## Reglas

- No uses `down -v` para "arreglar" un error: primero mira el log.
- No edites contenedores a mano (`docker exec`); todo cambio va al compose o al
  código, o se pierde.
- Si cambias `.env`, hay que recrear el contenedor: `docker compose up -d core-api`.
- `.env` no se versiona. Los valores reales los administra Nohan/Abel.
