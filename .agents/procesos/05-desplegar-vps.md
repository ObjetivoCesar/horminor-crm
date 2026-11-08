# Proceso 05 — Despliegue en VPS (aún no ejecutado)

Este documento describe **lo que falta**, no lo que ya se hizo. Hoy todo corre
solo en local. No escribir aquí pasos "probados" hasta haberlos probado.

## Lo que el PDR pide

| Contenedor | Estado |
|---|---|
| `orminorth-postgres` (PostgreSQL 15 Alpine) | definido en compose |
| `orminorth-redis` (Redis 7 Alpine) | definido en compose |
| `orminorth-core-api` (FastAPI) | definido y probado en local |
| `orminorth-web-panel` (frontend) | **no existe todavía** (Hito 4) |
| Evolution API existente | **sin credenciales** |
| Bunny.net Storage Zone | **sin credenciales** |

## Lo que el PDR NO incluye y hay que resolver antes de exponer

1. **Proxy inverso y TLS.** Sin HTTPS no hay webhook de Evolution ni panel
   seguro. Opciones: Caddy (más simple), Nginx + Certbot, o Traefik.
2. **Dominio o subdominio.** Ej. `api.orminorth.com` y `panel.orminorth.com`.
3. **Firewall:** exponer solo 80/443 (y SSH restringido por IP si se puede).
   PostgreSQL y Redis **no** deben publicar puertos en el VPS; en el compose
   local están expuestos solo para desarrollo.
4. **Backups de PostgreSQL.** No definidos. Para un sistema que va a generar
   carpetas bancarias es obligatorio: `pg_dump` diario + copia fuera del VPS +
   prueba de restauración mensual.
5. **Rotación de logs y retención de `error_logs`.**
6. **Secretos:** `.env` en el VPS con permisos restringidos, nunca en git.
7. **Actualización de contenedores:** `docker compose pull && up -d` con
   ventana definida.
8. **Rollback de aplicación:** imagen anterior etiquetada.

## Checklist mínimo antes de decir "está en producción"

- [ ] VPS con Docker y Docker Compose instalados.
- [ ] DNS apuntando al VPS.
- [ ] Proxy inverso con certificado válido.
- [ ] `docker compose up -d` con `AUTO_MIGRATE=true` y migraciones aplicadas.
- [ ] `health` responde 200 desde fuera.
- [ ] `daily-audit` responde con la clave real y sin exponer la clave en logs.
- [ ] PostgreSQL y Redis sin puertos publicados.
- [ ] Backup automático ejecutado al menos una vez y **restaurado en un entorno
      de prueba**.
- [ ] `.env` fuera de git y con permisos correctos.
- [ ] Monitoreo del Centinela enviando al CRM de la agencia (Hito 2 cerrado).

## Observaciones de la ejecución local que aplican al VPS

- La primera llamada al Centinela tarda ~250–400 ms por apertura de conexiones;
  en caliente 20–25 ms. Conviene precalentar el pool en el `lifespan`.
- Python 3.12 en la imagen (`python:3.12-slim`), aunque local se probó también
  con 3.13. Fijar la versión en la imagen es intencional.
- `TZ=America/Guayaquil` está en el servicio de Postgres, pero la zona operativa
  real la lee la aplicación desde `system_settings`.
