#!/usr/bin/env bash
# HORMINOR - backup diario de PostgreSQL (v5.1, Paso 4)
#
# Uso en el VPS:
#   chmod +x scripts/backup_db.sh
#   BACKUP_DIR=/backups/horminor scripts/backup_db.sh
#
# Cron sugerido (America/Guayaquil, 23:55):
#   55 23 * * * /opt/horminor/scripts/backup_db.sh >> /var/log/horminor-backup.log 2>&1
#
# El dump se genera con pg_dump -Fc dentro del contenedor y se escribe en el
# host. Se verifica con pg_restore --list antes de dar el backup por bueno.

set -euo pipefail

CONTAINER="${CONTAINER:-orminorth-postgres}"
DB_USER="${POSTGRES_USER:-orminorth}"
DB_NAME="${POSTGRES_DB:-orminorth}"
BACKUP_DIR="${BACKUP_DIR:-/backups/horminor}"
DAILY_KEEP_DAYS="${BACKUP_DAILY_KEEP_DAYS:-14}"
MONTHLY_KEEP="${BACKUP_MONTHLY_KEEP:-6}"
VERIFY="${BACKUP_VERIFY:-1}"

mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/monthly"

STAMP="$(date +%F_%H%M)"
OUT="$BACKUP_DIR/daily/horminor_${STAMP}.dump"

echo "[$(date -Iseconds)] generando $OUT"
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -Fc "$DB_NAME" > "$OUT"

if [ ! -s "$OUT" ]; then
  echo "ERROR: el dump quedo vacio: $OUT" >&2
  rm -f "$OUT"
  exit 1
fi

if [ "$VERIFY" = "1" ]; then
  if ! docker exec -i "$CONTAINER" pg_restore --list < "$OUT" > /dev/null; then
    echo "ERROR: pg_restore no pudo leer el dump: $OUT" >&2
    exit 1
  fi
fi

MONTH="$(date +%Y-%m)"
if [ ! -f "$BACKUP_DIR/monthly/horminor_${MONTH}.dump" ]; then
  cp "$OUT" "$BACKUP_DIR/monthly/horminor_${MONTH}.dump"
fi

find "$BACKUP_DIR/daily" -type f -name 'horminor_*.dump' \
  -mtime +"$DAILY_KEEP_DAYS" -delete

OLD_MONTHLY="$(ls -1t "$BACKUP_DIR/monthly"/horminor_*.dump 2>/dev/null \
  | tail -n +$((MONTHLY_KEEP + 1)) || true)"
if [ -n "$OLD_MONTHLY" ]; then
  echo "$OLD_MONTHLY" | while IFS= read -r viejo; do
    rm -f "$viejo"
  done
fi

echo "[$(date -Iseconds)] OK: $OUT"
