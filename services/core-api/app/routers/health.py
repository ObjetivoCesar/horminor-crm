"""Endpoint de salud simple (el diagnostico completo vive en el Modulo 5)."""

from __future__ import annotations

from time import perf_counter

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request):
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        return JSONResponse(status_code=503, content={"status": "sin_pool"})

    inicio = perf_counter()
    try:
        await pool.fetchval("SELECT 1")
    except Exception as exc:  # pragma: no cover - depende del entorno
        return JSONResponse(
            status_code=503,
            content={"status": "db_error", "detalle": str(exc)},
        )
    latencia = (perf_counter() - inicio) * 1000
    return {"status": "ok", "db": "ok", "db_latencia_ms": round(latencia, 2)}
