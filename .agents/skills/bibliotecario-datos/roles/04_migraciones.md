# Rol 04 — Migraciones

- **Nivel funcional:** estructura
- **Mecanismo preferido:** Capa 0 (runner determinista)
- **Misión:** garantizar que todo cambio de esquema tenga migración numerada, aprobada y reversible en el clon.

## Reglas inviolables

1. `0NN_descripcion.sql` con `NN = max(seq) + 1`.
2. Una migración aplicada **no se edita**: se corrige hacia adelante.
3. Se prueba contra el clon con `ROLLBACK` antes de la base real.
4. Toda migración se documenta en `docs/BASE_DE_DATOS.md`.
5. Nada de DDL suelto por fuera del runner.
6. El archivo debe incluir su comentario de propósito y su fecha.

## Entradas

Solicitud de cambio de esquema (tabla, columna, índice o vista).

## Salidas

- Archivo de migración con checksum en `schema_migrations`.
- Entrada en `docs/BASE_DE_DATOS.md`.
- Evidencia del clon.

## Evidencia obligatoria

- Salida de `scripts/db_migrate.py` en el clon.
- `ROLLBACK` verificado en las tablas tocadas.
- `SELECT` de `schema_migrations` con el nuevo `seq`.
- Si cambia una vista, `pg_get_viewdef()` antes y después.

## Checklist antes de aplicar

- [ ] El número es `max(seq) + 1`.
- [ ] El archivo es idempotente (`IF NOT EXISTS` donde aplique).
- [ ] No toca una migración ya aplicada.
- [ ] Se probó en el clon con `ROLLBACK`.
- [ ] Se actualizó `docs/BASE_DE_DATOS.md`.
- [ ] Quedó registrado en la bitácora.

## Rechazos automáticos

- `SECUENCIA_DUPLICADA` si el número ya existe.
- `MIGRACION_YA_APLICADA` si se intenta editar una existente.
- `SIN_PRUEBA_EN_CLON` si no hay evidencia de `ROLLBACK`.
- `DDL_FUERA_DEL_RUNNER` si el archivo no sigue la convención.
