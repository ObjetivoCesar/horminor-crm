"""Pool asyncpg y runner de migraciones (idempotente, con advisory lock)."""

from __future__ import annotations

import logging
from pathlib import Path

import asyncpg

log = logging.getLogger(__name__)

_MIGRATION_LOCK_ID = 918_273_645


async def create_pool(dsn: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn=dsn, min_size=1, max_size=10, command_timeout=30
    )


async def run_migrations(pool: asyncpg.Pool, migrations_dir: str) -> list[str]:
    """Aplica los .sql pendientes en orden alfabetico. Devuelve los aplicados."""
    directory = Path(migrations_dir)
    if not directory.is_dir():
        raise RuntimeError(f"No existe el directorio de migraciones: {directory.resolve()}")

    applied: list[str] = []
    async with pool.acquire() as conn:
        await conn.execute("SELECT pg_advisory_lock($1)", _MIGRATION_LOCK_ID)
        try:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version      text PRIMARY KEY,
                    aplicada_at  timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            done = {
                row["version"]
                for row in await conn.fetch("SELECT version FROM schema_migrations")
            }
            for path in sorted(directory.glob("*.sql")):
                if path.name in done:
                    continue
                sql = path.read_text(encoding="utf-8")
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES ($1)", path.name
                    )
                applied.append(path.name)
                log.info("migracion aplicada: %s", path.name)
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", _MIGRATION_LOCK_ID)
    return applied


async def setting(pool: asyncpg.Pool, key: str, default=None):
    """Lee un parametro maestro. El codigo nunca fija valores de negocio."""
    row = await pool.fetchrow("SELECT value FROM system_settings WHERE key = $1", key)
    if row is None:
        return default
    # asyncpg devuelve jsonb como str si no se registra codec; normalizamos.
    value = row["value"]
    if isinstance(value, str):
        import json

        value = json.loads(value)
    return value
