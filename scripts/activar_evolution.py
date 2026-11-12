"""Activa Evolution API en `system_settings` usando las credenciales del .env.

No imprime la API key. Verifica que la instancia exista y que su estado sea
`open` antes de apagar el sandbox, salvo que se pase `--force`.

Uso:
    docker compose run --rm --no-deps core-api python scripts/activar_evolution.py
    docker compose run --rm --no-deps core-api python scripts/activar_evolution.py --force
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import _path  # noqa: F401

import asyncpg
import httpx

from app.settings import get_settings


async def main() -> int:
    parser = argparse.ArgumentParser(description="Activa Evolution en system_settings")
    parser.add_argument("--force", action="store_true", help="Activa aunque la instancia no este open")
    args = parser.parse_args()

    settings = get_settings()
    url = (settings.evolution_url or "").strip().rstrip("/")
    instancia = (settings.evolution_instance or "").strip()
    api_key = (settings.evolution_api_key or "").strip()
    if not (url and instancia and api_key):
        print("[FALLO] faltan EVOLUTION_URL, EVOLUTION_INSTANCE o EVOLUTION_API_KEY en .env")
        return 1

    estado = "desconocido"
    try:
        async with httpx.AsyncClient(timeout=15) as cliente:
            r = await cliente.get(
                f"{url}/instance/connectionState/{instancia}",
                headers={"apikey": api_key},
            )
        if r.status_code < 300:
            datos = r.json()
            estado = (
                (datos.get("instance") or {}).get("state")
                or datos.get("state")
                or "desconocido"
            )
        else:
            print(f"[AVISO] Evolution respondio HTTP {r.status_code} al consultar la instancia")
    except httpx.HTTPError as exc:
        print(f"[AVISO] no se pudo consultar Evolution: {type(exc).__name__}")
        if not args.force:
            print("        usa --force solo si sabes que la instancia existe")
            return 1

    if estado != "open" and not args.force:
        print(f"[FALLO] la instancia {instancia} esta en estado '{estado}', no 'open'")
        print("        escanea el QR y vuelve a ejecutar; o usa --force")
        return 1

    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=2)
    try:
        valor = {
            "url": url,
            "instancia": instancia,
            "api_key": api_key,
            "sandbox": False,
        }
        await pool.execute(
            """
            UPDATE system_settings
               SET value = $1::jsonb
             WHERE key = 'integraciones.evolution'
            """,
            json.dumps(valor),
        )
    finally:
        await pool.close()

    print(f"[OK] Evolution activado: instancia={instancia} estado={estado} sandbox=false")
    print("     clave: configurada (no se imprime)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
