"""Horminor - Core API (Modulos 0, 1, 2 y 5)."""

from __future__ import annotations

import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .db import create_pool, run_migrations
from .http_gate import custodio_router, payments_router
from .http_gate.panel import router as panel_api_router
from .m1_whatsapp.router import router as whatsapp_router
from .m1_whatsapp.runtime import WhatsAppRuntime, construir_runtime
from .m2_planta import ErrorPlanta
from .m3_secretaria.router import router as secretaria_router
from .m4_dashboard.router import router as dashboard_router
from .m5_sentinel.router import router as sentinel_router
from .routers import catalog, health, orders
from .services.ordenes import OrdenInvalidaError
from .settings import get_settings
from .superadmin.operacion import router as operacion_router
from .superadmin.router import router as superadmin_router
from .superadmin.store import PostgresConfigStore
from .superadmin.usuarios import router as usuarios_router
from .web.panel import router as panel_router

log = logging.getLogger("orminorth")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    app.state.settings = settings
    app.state.whatsapp = None
    app.state.config_store = None

    pool = await create_pool(settings.database_url)
    app.state.pool = pool
    if settings.auto_migrate:
        aplicadas = await run_migrations(pool, settings.migrations_dir)
        if aplicadas:
            log.info("migraciones aplicadas: %s", ", ".join(aplicadas))

    app.state.config_store = PostgresConfigStore(pool)

    runtime: WhatsAppRuntime | None = None
    if settings.whatsapp_worker_enabled:
        try:
            runtime = await construir_runtime(pool, settings)
            app.state.whatsapp = runtime
            runtime.worker.iniciar()
            log.info("Modulo 1 listo: %s", runtime.estado())
        except Exception:  # el bot no puede tumbar la API ni el Centinela
            log.exception("Modulo 1 no pudo inicializarse; la API sigue operativa")

    log.info("core-api lista (entorno=%s)", settings.environment)
    try:
        yield
    finally:
        if runtime is not None:
            await runtime.cerrar()
        await pool.close()


app = FastAPI(
    title="Horminor Core API",
    version="0.3.0",
    description=(
        "Modulos 0 (datos), 1 (WhatsApp), 2 (planta), 3 (Secretaria), "
        "4 (Dashboard) y 5 (Centinela) de Horminor."
    ),
    lifespan=lifespan,
)

mimetypes.add_type("font/woff2", ".woff2")

app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).resolve().parent / "web" / "static"),
    name="static",
)


@app.exception_handler(ErrorPlanta)
async def error_planta_handler(request: Request, exc: ErrorPlanta):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(OrdenInvalidaError)
async def orden_invalida_handler(request: Request, exc: OrdenInvalidaError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


app.include_router(health.router)
app.include_router(catalog.router)
app.include_router(orders.router)
app.include_router(whatsapp_router)
app.include_router(superadmin_router)
app.include_router(operacion_router)
app.include_router(usuarios_router)
app.include_router(secretaria_router)
app.include_router(custodio_router)
app.include_router(payments_router)
app.include_router(panel_api_router)
app.include_router(dashboard_router)
app.include_router(sentinel_router)
app.include_router(panel_router)
