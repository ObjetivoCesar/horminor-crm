"""Aplica las migraciones pendientes. Uso: python scripts/db_migrate.py"""

from __future__ import annotations

import asyncio

import _path  # noqa: F401  (ajusta sys.path)

from app.db import create_pool, run_migrations
from app.settings import get_settings


async def main() -> None:
    settings = get_settings()
    pool = await create_pool(settings.database_url)
    try:
        aplicadas = await run_migrations(pool, settings.migrations_dir)
    finally:
        await pool.close()
    if aplicadas:
        print("Migraciones aplicadas:")
        for nombre in aplicadas:
            print(f"  + {nombre}")
    else:
        print("Sin migraciones pendientes.")


if __name__ == "__main__":
    asyncio.run(main())
