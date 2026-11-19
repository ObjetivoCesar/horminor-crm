"""Adaptador del canal WhatsApp al nucleo comercial.

El webhook no crea leads ni citas por su cuenta: pide al modulo comercial y
este aplica las reglas. El origen queda fijado por el canal, no por el cuerpo
del mensaje.
"""

from __future__ import annotations

from typing import Any

import asyncpg

from . import citas as citas_svc
from . import leads as leads_svc
from .intencion import parse_cita


class ComercialWhatsApp:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def entrante(
        self, *, telefono: str, nombre: str | None, texto: str | None
    ) -> dict[str, Any]:
        """Registra el contacto y su mensaje (aplica reglas de intencion)."""
        lead = await leads_svc.crear_o_reutilizar(
            self._pool,
            telefono_lead=telefono,
            origen="WHATSAPP",
            nombre=nombre,
        )
        estado = await leads_svc.registrar_mensaje(
            self._pool,
            lead_id=str(lead["id"]),
            texto=texto,
            actor="WHATSAPP",
        )
        return {**lead, **estado}

    async def respuesta(
        self, *, lead_id: str, texto: str | None = None
    ) -> dict[str, Any]:
        """La empresa respondio: el contacto pasa a LEAD."""
        return await leads_svc.registrar_respuesta(
            self._pool, lead_id=lead_id, texto=texto, actor="WHATSAPP_BOT"
        )

    async def solicitar_cita(
        self, *, lead_id: str, texto: str, actor: str = "WHATSAPP"
    ) -> dict[str, Any] | None:
        """Crea la cita SOLICITADA solo si el texto trae fecha y hora."""
        datos = parse_cita(texto)
        if datos.get("fecha") is None or datos.get("hora") is None:
            return None
        return await citas_svc.crear(
            self._pool,
            tipo=str(datos["tipo"]),
            fecha=datos["fecha"],
            hora_inicio=str(datos["hora"]),
            origen="WHATSAPP",
            lead_id=lead_id,
            solicitada_por=actor,
            notas="Solicitada por WhatsApp.",
        )


__all__ = ["ComercialWhatsApp"]
