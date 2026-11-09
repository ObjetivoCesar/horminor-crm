"""Modulo 1 - Notificaciones de salida.

Dos caminos distintos, a proposito:

- **WhatsApp** (Evolution API) para avisar al cliente que el mixer salio.
- **Push webhook al CRM Central** (PDR 4.2) para alertas al Nodo Centinela.
  Si ``AGENCY_CRM_WEBHOOK_URL`` o la clave maestra estan vacias, la alerta
  degrada a ``NO_CONFIGURADO``: se registra en ``error_logs`` y no se inventa
  un envio que no ocurrio.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

from ..settings import CLAVE_INSEGURA
from .repositorio import RepositorioWhatsApp

log = logging.getLogger(__name__)

ESTADO_ENVIADO = "ENVIADO"
ESTADO_NO_CONFIGURADO = "NO_CONFIGURADO"
ESTADO_FALLIDO = "FALLIDO"


class Notifier(Protocol):
    nombre: str

    async def enviar_texto(self, telefono: str, texto: str) -> bool: ...


@dataclass
class RecordingNotifier:
    """Doble de prueba: guarda los mensajes en lugar de enviarlos."""

    nombre: str = "memoria"
    enviados: list[dict[str, str]] = field(default_factory=list)

    async def enviar_texto(self, telefono: str, texto: str) -> bool:
        self.enviados.append({"telefono": telefono, "texto": texto})
        return True


class EvolutionNotifier:
    """Envia texto por la instancia existente de Evolution API."""

    nombre = "evolution"

    def __init__(
        self,
        *,
        base_url: str | None,
        instancia: str | None,
        api_key: str | None,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._url = (base_url or "").rstrip("/")
        self._instancia = instancia or ""
        self._api_key = api_key or ""
        self._http = http_client
        self._timeout = timeout

    def configurado(self) -> bool:
        return bool(self._url and self._instancia and self._api_key)

    async def enviar_texto(self, telefono: str, texto: str) -> bool:
        if not self.configurado():
            log.warning("Evolution API sin configurar: no se envia el WhatsApp")
            return False
        endpoint = f"{self._url}/message/sendText/{self._instancia}"
        cuerpo = {"number": telefono, "text": texto}
        try:
            if self._http is not None:
                respuesta = await self._http.post(
                    endpoint,
                    json=cuerpo,
                    headers={"apikey": self._api_key},
                    timeout=self._timeout,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as cliente:
                    respuesta = await cliente.post(
                        endpoint,
                        json=cuerpo,
                        headers={"apikey": self._api_key},
                    )
        except httpx.HTTPError as exc:
            log.warning("fallo enviando WhatsApp a %s: %s", telefono, exc)
            return False
        return 200 <= respuesta.status_code < 300


class NullNotifier:
    """Sin Evolution configurado: no finge envios."""

    nombre = "no_configurado"

    async def enviar_texto(self, telefono: str, texto: str) -> bool:
        return False


@dataclass(frozen=True)
class ResultadoAlerta:
    estado: str
    codigo: str
    http_status: int | None = None
    detalle: str = ""

    def a_dict(self) -> dict[str, Any]:
        return {
            "estado": self.estado,
            "codigo": self.codigo,
            "http_status": self.http_status,
            "detalle": self.detalle,
        }


@dataclass
class SentinelAlerter:
    """Push de alertas del Modulo 1 al CRM Central (y a ``error_logs``)."""

    webhook_url: str | None
    master_key: str | None
    repo: RepositorioWhatsApp
    http_client: httpx.AsyncClient | None = None
    timeout: float = 5.0

    def configurado(self) -> bool:
        url = (self.webhook_url or "").strip()
        clave = (self.master_key or "").strip()
        return bool(url and clave and clave != CLAVE_INSEGURA)

    async def alertar(
        self,
        *,
        codigo: str,
        mensaje: str,
        contexto: dict[str, Any] | None = None,
        order_id: str | None = None,
        dispatch_id: str | None = None,
        nivel: str = "ERROR",
    ) -> ResultadoAlerta:
        """Registra la incidencia y, si hay configuracion, la empuja al CRM."""
        await self.repo.registrar_log(
            nivel=nivel,
            mensaje=mensaje,
            contexto={"codigo": codigo, **(contexto or {})},
            order_id=order_id,
            dispatch_id=dispatch_id,
        )

        if not self.configurado():
            return ResultadoAlerta(
                estado=ESTADO_NO_CONFIGURADO,
                codigo=codigo,
                detalle=(
                    "AGENCY_CRM_WEBHOOK_URL o SENTINEL_MASTER_KEY vacias: "
                    "alerta registrada solo en error_logs"
                ),
            )

        cuerpo = {
            "cliente": "HORMINOR",
            "evento": codigo,
            "mensaje": mensaje,
            "generado_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "datos": contexto or {},
        }
        cabeceras = {
            "X-Agency-Master-Key": (self.master_key or "").strip(),
            "Content-Type": "application/json",
        }
        try:
            if self.http_client is not None:
                respuesta = await self.http_client.post(
                    self.webhook_url, json=cuerpo, headers=cabeceras, timeout=self.timeout
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as cliente:
                    respuesta = await cliente.post(
                        self.webhook_url, json=cuerpo, headers=cabeceras
                    )
        except httpx.HTTPError as exc:
            log.warning("no se pudo empujar la alerta %s: %s", codigo, exc)
            return ResultadoAlerta(
                estado=ESTADO_FALLIDO,
                codigo=codigo,
                detalle=f"{type(exc).__name__}: {exc}",
            )

        estado = ESTADO_ENVIADO if 200 <= respuesta.status_code < 300 else ESTADO_FALLIDO
        return ResultadoAlerta(
            estado=estado,
            codigo=codigo,
            http_status=respuesta.status_code,
            detalle=f"HTTP {respuesta.status_code}",
        )
