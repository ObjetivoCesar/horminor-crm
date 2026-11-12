# Despliegue en el VPS — Horminor CRM

> Estado: **2026-11-12**. Primera subida del CRM al VPS de Contabo.
> El panel sigue **sin login**, así que no se expone a Internet: se usa por
> túnel SSH. Solo `/health` y el webhook de Evolution son públicos.

## 1. Servidor

| Dato | Valor |
|---|---|
| IP | `178.238.238.158` |
| Proveedor | Contabo |
| Usuario | `root` |
| Ruta del proyecto | `/opt/horminor` |
| Host público (TLS) | `horminor.178.238.238.158.sslip.io` |
| Core API | `127.0.0.1:8012` (solo loopback) |
| PostgreSQL / Redis | sin puertos publicados |
| Proxy | Caddy (ya existente en el VPS) |

`sslip.io` resuelve el nombre al IP y Caddy emite el certificado. Cuando exista
un dominio propio, solo se cambia el bloque de Caddy.

## 2. Llaves

| Llave | Uso | Dónde vive |
|---|---|---|
| `horminor_vps` | Entrar al VPS por SSH | `vps-entrada/` (local, privada) |
| `horminor_vps.pub` | Autorizada en `/root/.ssh/authorized_keys` | VPS |
| `horminor_github_deploy` | Clonar/actualizar el repo desde el VPS | `/root/.ssh/` en el VPS |
| `horminor_github_deploy.pub` | Deploy Key **read-only** del repo | GitHub |

Reglas:

- La carpeta `vps-entrada/` **nunca** se sube al repositorio (`.gitignore`).
- Las llaves privadas no se pegan en el chat, la bitácora ni documentación.
- La deploy key es de solo lectura: el VPS no puede hacer push.

## 3. GitHub

- Repo: `https://github.com/ObjetivoCesar/horminor-crm.git`
- Rama: `main`
- Deploy key: `horminor-vps-deploy-2026-11-12` (read-only).
- El VPS clona por SSH:

```bash
GIT_SSH_COMMAND="ssh -i /root/.ssh/horminor_github_deploy -o IdentitiesOnly=yes" \
  git clone git@github.com:ObjetivoCesar/horminor-crm.git /opt/horminor
```

## 4. Secretos

- `.env` real: `/opt/horminor/.env` en el VPS, permisos `600`, fuera de git.
- Copia local de trabajo: `vps-entrada/horminor.env` (también fuera de git).
- `POSTGRES_PASSWORD`, `AGENCY_MASTER_KEY`, `SENTINEL_MASTER_KEY`,
  `CUSTODIO_TOKEN_*` y `GATE_API_KEY` se generaron nuevos para el VPS.
- La API key de Evolution se cargó en `.env` y en
  `system_settings.integraciones.evolution`.
- **Rotar la API key de Evolution** si se compartió por chat.

## 5. Comandos de operación

```bash
# Entrar
ssh -i vps-entrada/horminor_vps root@178.238.238.158

# Actualizar código
cd /opt/horminor
git pull
docker compose -f docker-compose.yml -f docker-compose.vps.yml up -d --build

# Estado
docker compose -f docker-compose.yml -f docker-compose.vps.yml ps
curl http://127.0.0.1:8012/health

# Logs
docker compose -f docker-compose.yml -f docker-compose.vps.yml logs -f core-api
```

## 6. Acceso al panel (sin login)

El panel **no** está publicado. Se usa un túnel SSH:

```bash
ssh -i vps-entrada/horminor_vps -L 8012:127.0.0.1:8012 root@178.238.238.158
```

Luego abrir `http://localhost:8012/panel`.

Cuando se implemente el login (`panel_users`, cookie `HttpOnly`), se puede
abrir el host público completo en Caddy.

## 7. Caddy

- Archivo: `/etc/caddy/Caddyfile`.
- Respaldo: `/etc/caddy/Caddyfile.bak.2026-11-12-horminor`.
- Bloque:

```caddyfile
horminor.178.238.238.158.sslip.io {
    encode gzip zstd
    @publico path /health /api/v1/whatsapp/webhook
    handle @publico { reverse_proxy localhost:8012 }
    handle { respond "Panel privado..." 403 }
}
```

Validar y recargar:

```bash
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

## 8. Evolution API

| Dato | Valor |
|---|---|
| API | `http://178.238.238.158:8080` |
| Instancia | `horminor` |
| Webhook | `https://horminor.178.238.238.158.sslip.io/api/v1/whatsapp/webhook` |
| Eventos | `MESSAGES_UPSERT`, `CONNECTION_UPDATE`, `QRCODE_UPDATED` |
| Desde el contenedor | `http://host.docker.internal:8080` |

El QR se guarda en `vps-entrada/horminor_qr.png` (privado). Si expira, se
regenera con:

```bash
GET /instance/connect/horminor
```

Una vez escaneado, el estado debe pasar a `open`:

```bash
docker compose run --rm --no-deps core-api python scripts/activar_evolution.py
```

## 9. Pendientes antes de abrir el panel a Internet

1. Login de usuario final (`panel_users`, hash, cookie `HttpOnly`).
2. Backups diarios y copia fuera del VPS.
3. Dominio propio (opcional; hoy se usa sslip.io).
4. Probar webhook real y persistencia del entrante en el hilo.
5. Rotar la API key de Evolution.
