"""Espejo de WhatsApp - cliente HTTP de Evolution API.

Solo dos operaciones, las que el espejo necesita de verdad:

* ``POST /chat/findMessages/{instancia}`` para el historial paginado.
* ``POST /message/sendText/{instancia}`` para responder desde el CRM.

La lectura se permite tambien en SANDBOX (no envia nada); el envio real
depende del notificador que arma el runtime del Modulo 1.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from .identidad import telefono_canonico
from .mensajes import estado_entrega


class EvolutionError(RuntimeError):
    """Evolution respondio con error o no se pudo contactar."""


class EvolutionNoConfigurado(EvolutionError):
    """Faltan URL, instancia o API key."""


def configuracion_evolution(settings: Any, cfg: dict[str, Any] | None = None) -> dict[str, str]:
    """Resuelve URL/instancia/clave con la misma regla que el runtime.

    La configuracion de ``system_settings`` manda solo si trae URL y clave
    completas; una fila a medias no debe pisar el ``.env``.
    """
    datos = cfg or {}
    if datos.get("url") and datos.get("api_key"):
        return {
            "url": str(datos.get("url") or "").rstrip("/"),
            "instancia": str(datos.get("instancia") or getattr(settings, "evolution_instance", "")),
            "api_key": str(datos.get("api_key") or ""),
        }
    return {
        "url": str(getattr(settings, "evolution_url", "") or "").rstrip("/"),
        "instancia": str(getattr(settings, "evolution_instance", "") or ""),
        "api_key": str(getattr(settings, "evolution_api_key", "") or ""),
    }


class EvolutionEspejo:
    """Cliente minimo contra la instancia ya conectada."""

    def __init__(
        self,
        *,
        base_url: str,
        instancia: str,
        api_key: str,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._url = (base_url or "").rstrip("/")
        self._instancia = instancia or ""
        self._api_key = api_key or ""
        self._http = http_client
        self._timeout = timeout

    def configurado(self) -> bool:
        return bool(self._url and self._instancia and self._api_key)

    async def _post(self, ruta: str, cuerpo: dict[str, Any], *, timeout: float | None = None) -> Any:
        if not self.configurado():
            raise EvolutionNoConfigurado(
                "Evolution API sin URL, instancia o API key"
            )
        endpoint = f"{self._url}{ruta}"
        try:
            if self._http is not None:
                respuesta = await self._http.post(
                    endpoint,
                    json=cuerpo,
                    headers={"apikey": self._api_key},
                    timeout=timeout or self._timeout,
                )
            else:
                async with httpx.AsyncClient(timeout=timeout or self._timeout) as cliente:
                    respuesta = await cliente.post(
                        endpoint,
                        json=cuerpo,
                        headers={"apikey": self._api_key},
                    )
        except httpx.HTTPError as exc:
            raise EvolutionError(f"{type(exc).__name__}: {exc}") from exc

        if not 200 <= respuesta.status_code < 300:
            detalle = respuesta.text[:300]
            raise EvolutionError(f"HTTP {respuesta.status_code}: {detalle}")
        try:
            return respuesta.json()
        except ValueError:
            return {}

    async def buscar_mensajes(
        self, jid: str, *, page: int = 1, offset: int = 100
    ) -> dict[str, Any]:
        """Una pagina del historial de un JID, con totales de Evolution."""
        datos = await self._post(
            f"/chat/findMessages/{self._instancia}",
            {"where": {"key": {"remoteJid": jid}}, "page": page, "offset": offset},
        )
        bloque = datos.get("messages") if isinstance(datos, dict) else None
        if isinstance(bloque, list):
            return {"records": bloque, "total": len(bloque), "pages": 1, "page": 1}
        if not isinstance(bloque, dict):
            return {"records": [], "total": 0, "pages": 0, "page": page}
        registros = bloque.get("records")
        return {
            "records": registros if isinstance(registros, list) else [],
            "total": int(bloque.get("total") or 0),
            "pages": int(bloque.get("pages") or 0),
            "page": int(bloque.get("currentPage") or page),
        }

    async def obtener_media_base64(
        self, mensaje_id: str, jid: str, from_me: bool
    ) -> dict[str, Any] | None:
        """Descarga el binario de un mensaje multimedia desde Evolution.

        Evolution lo entrega en base64 con su mimetype y nombre reales: es la
        via oficial para bajar imagen, audio, video, documento y sticker.
        """
        if not mensaje_id:
            return None
        cuerpo = {
            "message": {
                "key": {
                    "id": str(mensaje_id),
                    "remoteJid": str(jid or ""),
                    "fromMe": bool(from_me),
                }
            },
            "convertToMp4": False,
        }
        datos = await self._post(
            f"/chat/getBase64FromMediaMessage/{self._instancia}", cuerpo, timeout=60
        )
        if not isinstance(datos, dict):
            return None
        crudo = datos.get("base64")
        if not crudo:
            return None
        return {
            "base64": str(crudo),
            "mimetype": datos.get("mimetype"),
            "nombre": datos.get("fileName"),
        }

    async def telefono_de_lid(self, lid: str) -> str | None:
        """Aprende el telefono real de un ``@lid`` desde el propio historial.

        WhatsApp no siempre pone ``remoteJidAlt`` en el ``key`` (sobre todo en
        los mensajes que salen del telefono), pero Evolution guarda el par en
        los que si lo traen. Se lee una pagina del hilo y se devuelve el primer
        telefono valido. Sin dato no se inventa nada.
        """
        if not str(lid or "").endswith("@lid"):
            return None
        datos = await self._post(
            f"/chat/findMessages/{self._instancia}",
            {"where": {"key": {"remoteJid": lid}}, "page": 1, "offset": 60},
        )
        bloque = datos.get("messages") if isinstance(datos, dict) else None
        if isinstance(bloque, list):
            registros = bloque
        elif isinstance(bloque, dict):
            registros = bloque.get("records") or []
        else:
            registros = []
        for registro in registros:
            if not isinstance(registro, dict):
                continue
            clave = registro.get("key") if isinstance(registro.get("key"), dict) else {}
            alt = clave.get("remoteJidAlt") or registro.get("remoteJidAlt")
            texto = str(alt or "").strip()
            if not texto:
                continue
            usuario = texto.split("@", 1)[0]
            telefono = telefono_canonico(usuario)
            if telefono:
                return telefono
        return None

    async def enviar_media(
        self,
        telefono: str,
        *,
        mediatype: str,
        mimetype: str,
        nombre: str,
        datos: bytes,
        caption: str | None = None,
    ) -> dict[str, Any]:
        """Envia imagen, video, audio o documento (base64) por Evolution."""
        cuerpo: dict[str, Any] = {
            "number": telefono,
            "mediatype": mediatype,
            "mimetype": mimetype,
            "fileName": nombre,
            "media": base64.b64encode(datos).decode("ascii"),
        }
        if caption:
            cuerpo["caption"] = caption
        respuesta = await self._post(
            f"/message/sendMedia/{self._instancia}", cuerpo, timeout=120
        )
        clave = respuesta.get("key") if isinstance(respuesta, dict) else None
        message_id = None
        if isinstance(clave, dict):
            message_id = clave.get("id")
        return {
            "ok": True,
            "message_id": str(message_id) if message_id else None,
            "estado": estado_entrega(
                (respuesta or {}).get("status"), from_me=True
            ),
            "http_status": 200,
        }

    async def enviar_texto(self, telefono: str, texto: str) -> dict[str, Any]:
        """Envia texto y devuelve el ``key.id`` para conciliar el eco."""
        datos = await self._post(
            f"/message/sendText/{self._instancia}",
            {"number": telefono, "text": texto},
        )
        clave = datos.get("key") if isinstance(datos, dict) else None
        message_id = None
        if isinstance(clave, dict):
            message_id = clave.get("id")
        return {
            "ok": True,
            "message_id": str(message_id) if message_id else None,
            # Evolution responde PENDING/SERVER_ACK/...; el CHECK de
            # chat_mensajes solo admite el vocabulario del CRM.
            "estado": estado_entrega((datos or {}).get("status"), from_me=True),
            "http_status": 200,
        }
