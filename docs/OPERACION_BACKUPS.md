# Operación de backups v5.1 (Paso 4)

> Objetivo: backup diario verificable de PostgreSQL, retención de 14 días y
> 6 cierres mensuales, con restauración de prueba mensual. El backup vive
> fuera del volumen `orminorth-pgdata` y se copia a otra máquina/nube.

## 1. Script

`scripts/backup_db.sh` ejecuta dentro del VPS:

```bash
chmod +x scripts/backup_db.sh
BACKUP_DIR=/backups/horminor scripts/backup_db.sh
```

Hace:

1. `pg_dump -Fc` del contenedor `orminorth-postgres`.
2. Verifica que el archivo no esté vacío.
3. Verifica con `pg_restore --list` que el dump sea legible.
4. Guarda una copia mensual (`monthly/horminor_YYYY-MM.dump`).
5. Borra dumps diarios con más de 14 días y conserva los 6 meses más recientes.

Variables:

| Variable | Default | Uso |
|---|---|---|
| `CONTAINER` | `orminorth-postgres` | Contenedor PostgreSQL |
| `POSTGRES_USER` | `orminorth` | Usuario de la base |
| `POSTGRES_DB` | `orminorth` | Base a respaldar |
| `BACKUP_DIR` | `/backups/horminor` | Carpeta destino en el host |
| `BACKUP_DAILY_KEEP_DAYS` | `14` | Días de dumps diarios |
| `BACKUP_MONTHLY_KEEP` | `6` | Meses de cierres mensuales |
| `BACKUP_VERIFY` | `1` | `1` verifica con `pg_restore --list` |

## 2. Cron sugerido

En el VPS, con zona `America/Guayaquil`:

```cron
55 23 * * * /opt/horminor/scripts/backup_db.sh >> /var/log/horminor-backup.log 2>&1
```

El script usa la fecha del host. Verificar que el VPS tenga
`TZ=America/Guayaquil` o que el cron corra en esa zona.

## 3. Restauración de prueba (mensual)

Nunca restaurar sobre `orminorth` en caliente. Usar una base de scratch:

```bash
# 1. Crear base de prueba
docker exec orminorth-postgres createdb -U orminorth orminorth_restore_test

# 2. Restaurar el dump más reciente
LATEST="$(ls -1t /backups/horminor/daily/horminor_*.dump | head -1)"
docker exec -i orminorth-postgres pg_restore -U orminorth -d orminorth_restore_test < "$LATEST"

# 3. Verificar conteos clave
docker exec orminorth-postgres psql -U orminorth -d orminorth_restore_test -c \
  "SELECT count(*) FROM orders; SELECT count(*) FROM inventory_movements;"

# 4. Borrar la base de prueba
docker exec orminorth-postgres dropdb -U orminorth orminorth_restore_test
```

## 4. Seguridad y copia externa

- El backup incluye datos de clientes y contabilidad: tratarlo como
  confidencial.
- Copiar `/backups/horminor` a otra máquina o almacenamiento en la nube; un
  backup en el mismo disco no protege contra la pérdida del VPS.
- Antes de producción, reemplazar los tokens `dev-*-v44` de `.env` por
  secretos reales y rotarlos si el VPS se comparte.
- Probar la restauración al menos una vez al mes y registrar el resultado en
  `.agents/BITACORA.md`.
