"""Panel web (Modulos 3 y 4 + Superadmin) en un solo HTML.

Sin build, sin autenticacion en esta etapa. El HTML vive en
``templates/panel.html`` y se sirve tal cual; toda la interaccion va por los
endpoints HTTP ya probados.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["panel"])

_RUTA = Path(__file__).resolve().parent / "templates" / "panel.html"


@router.get("/panel", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def panel() -> HTMLResponse:
    return HTMLResponse(_RUTA.read_text(encoding="utf-8"))
