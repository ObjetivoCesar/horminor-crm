# Proceso 03 — Migraciones de base de datos

Motor: SQL plano, sin ORM. Runner: `app/db.py` (`run_migrations`), con
`schema_migrations` y `pg_advisory_lock` (dos procesos no pueden migrar a la vez).

## Reglas

1. **Nunca editar una migración ya aplicada.** Si la base ya corrió
   `001_init.sql`, ese archivo es historia. Cualquier cambio es un archivo nuevo.
2. **Nombre:** `0NN_descripcion_corta.sql`, numeración correlativa
   (`001`, `010`, `020`, `030`, ...). Los números redondos dejan espacio.
3. **Idempotencia cuando se pueda:** `CREATE TABLE IF NOT EXISTS`,
   `INSERT ... ON CONFLICT DO NOTHING`.
4. **Una migración = un cambio con sentido.** No mezclar esquema y datos de
   negocio nuevos.
5. **Los datos de negocio no van en migraciones de esquema.** Recetas, precios
   y stock real se cargan con el proceso 04. Los seeds de ejemplo sí van, pero
   marcados como provisionales.
6. **Sin `DROP` destructivo en producción.** Si hay que eliminar algo, primero
   se agrega lo nuevo, se migra el dato y recién después se elimina.

## Cómo agregar una migración

1. Crear `db/migrations/040_lo_que_sea.sql` con encabezado:

```sql
-- =====================================================================
-- ORMINORTH - Migracion 040: titulo corto
-- Motivo: por que existe
-- =====================================================================
```

2. Escribir el SQL.
3. Aplicar:

```powershell
docker compose run --rm --no-deps core-api python scripts/db_migrate.py
```

4. Verificar que el runner la reporte como aplicada y que el esquema quedó bien.
5. Registrar en la bitácora: número, qué hace y por qué.

La API también aplica pendientes al arrancar (`AUTO_MIGRATE=true`), pero en
producción conviene correr el script a mano antes de reiniciar.

## Rollback

- **Local:** `docker compose down -v` y volver a levantar (borra datos).
- **VPS/producción:** no hay rollback automático. Se escribe una migración
  correctiva hacia adelante (`041_fix_...`). Nunca se borra una fila de
  `schema_migrations`.

## Cambiar un parámetro (no requiere migración)

`system_settings` está pensado para esto:

```sql
UPDATE system_settings SET value = '"nuevo_valor"'::jsonb WHERE key = 'operacion.politica_redondeo_viajes';
INSERT INTO system_settings (key, value, descripcion)
VALUES ('nueva.llave', '123'::jsonb, 'Para qué sirve')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, actualizado_at = now();
```

El código debe leer la llave con `setting(pool, "nueva.llave", default)`.
No se escribe el valor en Python.
