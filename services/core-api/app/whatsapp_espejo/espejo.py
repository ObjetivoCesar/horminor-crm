"""Espejo de WhatsApp - servicio de ingesta y sincronizacion.

Principio que no se negocia: **la lista blanca manda en el backend**. El
webhook, el backfill y cualquier sincronizacion pasan por
:meth:`EspejoWhatsApp.ingerir`; si el telefono no esta activo en
``whatsapp_espejo_numeros`` el mensaje no se guarda en ninguna tabla del
espejo.

El modulo no toca el pipeline del Modulo 1: no evalua compuertas, no crea
leads, no responde. Solo copia la conversacion real a ``chat_mensajes``.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ..services import media as media_svc
from .eventos import BusEventos
from .evolution import (
    EvolutionEspejo,
    EvolutionNoConfigurado,
    configuracion_evolution,
)
from .identidad import IdentidadJid, resolver_jid
from .mensajes import (
    MensajeEspejo,
    desde_registro,
    estado_entrega,
    eventos_del_payload,
)
from .repositorio import NumeroEspejo, RepositorioEspejo

log = logging.getLogger(__name__)

IMPORTADO = "IMPORTADO"
DUPLICADO = "DUPLICADO"
NO_AUTORIZADO = "NO_AUTORIZADO"
AMBIGUO = "AMBIGUO"
IGNORADO = "IGNORADO"
SIN_CLIENTE = "SIN_CLIENTE"

# Tipo del CRM -> mediatype de Evolution.
_MEDIATYPE = {
    "IMAGEN": "image",
    "VIDEO": "video",
    "AUDIO": "audio",
    "DOCUMENTO": "document",
}


class EspejoNoAutorizado(RuntimeError):
    """El cliente o el telefono no estan en la lista blanca."""


@dataclass(frozen=True)
class ResultadoSincronizacion:
    telefono: str
    cliente_id: str | None
    importados: int
    duplicados: int
    paginas: int
    jids: tuple[str, ...]
    ultimo_mensaje_at: datetime | None
    omitidos: int = 0

    def a_dict(self) -> dict[str, Any]:
        return {
            "telefono": self.telefono,
            "cliente_id": self.cliente_id,
            "importados": self.importados,
            "duplicados": self.duplicados,
            "paginas": self.paginas,
            "jids": list(self.jids),
            "ultimo_mensaje_at": self.ultimo_mensaje_at,
            "omitidos": self.omitidos,
        }


class EspejoWhatsApp:
    def __init__(
        self,
        repo: RepositorioEspejo,
        *,
        settings: Any = None,
        evolution: EvolutionEspejo | None = None,
        evolution_factory: Callable[[], Any] | None = None,
        tamano_pagina: int = 100,
        max_paginas: int = 50,
        parar_si_pagina_conocida: bool = True,
        eventos: BusEventos | None = None,
    ) -> None:
        self.repo = repo
        self.settings = settings
        self._evolution = evolution
        self._evolution_factory = evolution_factory
        self.tamano_pagina = max(1, int(tamano_pagina))
        self.max_paginas = max(1, int(max_paginas))
        self.parar_si_pagina_conocida = parar_si_pagina_conocida
        # Aviso en vivo para el panel: si nadie escucha, no cambia nada.
        self.eventos = eventos
        # LIDs que ya se buscaron y no tienen telefono conocido en el historial.
        self._lids_sin_telefono: set[str] = set()

    def _avisar(self, evento: dict[str, Any]) -> None:
        """Publica un aviso en vivo; un fallo aqui nunca rompe la ingesta."""
        if self.eventos is None:
            return
        try:
            self.eventos.publicar(evento)
        except Exception:  # noqa: BLE001
            log.debug("espejo: no se pudo publicar el aviso %s", evento, exc_info=True)

    # -- configuracion ----------------------------------------------------
    async def cliente_evolution(self) -> EvolutionEspejo | None:
        if self._evolution is not None:
            return self._evolution
        if self._evolution_factory is not None:
            self._evolution = self._evolution_factory()
            return self._evolution
        if self.settings is None:
            return None
        cfg = await self.repo.config_evolution()
        resuelta = configuracion_evolution(self.settings, cfg)
        cliente = EvolutionEspejo(
            base_url=resuelta["url"],
            instancia=resuelta["instancia"],
            api_key=resuelta["api_key"],
        )
        if not cliente.configurado():
            return None
        self._evolution = cliente
        return cliente

    async def numero_de_cliente(self, cliente_id: str) -> NumeroEspejo | None:
        return await self.repo.numero_de_cliente(cliente_id)

    async def telefono_de_cliente(self, cliente_id: str) -> str | None:
        return await self.repo.telefono_de_cliente(cliente_id)

    async def enviar_texto(self, telefono: str, texto: str) -> dict[str, Any]:
        """Envia texto por Evolution con el cliente propio del espejo.

        No pasa por el notificador del Modulo 1: asi el bot informativo
        conserva su modo SANDBOX y solo el numero autorizado puede responder
        desde el CRM.
        """
        cliente = await self.cliente_evolution()
        if cliente is None:
            raise EvolutionNoConfigurado(
                "Evolution API sin URL, instancia o API key para enviar"
            )
        return await cliente.enviar_texto(telefono, texto)

    async def enviar_media(
        self,
        telefono: str,
        *,
        tipo: str,
        datos: bytes,
        mime: str,
        nombre: str,
        caption: str | None = None,
    ) -> dict[str, Any]:
        """Envia una imagen, audio, video o documento por el cliente del espejo."""
        cliente = await self.cliente_evolution()
        if cliente is None:
            raise EvolutionNoConfigurado(
                "Evolution API sin URL, instancia o API key para enviar"
            )
        mediatype = _MEDIATYPE.get(str(tipo or "").upper(), "document")
        return await cliente.enviar_media(
            telefono,
            mediatype=mediatype,
            mimetype=mime,
            nombre=nombre,
            datos=datos,
            caption=caption,
        )

    async def estado_cliente(self, cliente_id: str) -> dict[str, Any]:
        numero = await self.repo.numero_de_cliente(cliente_id)
        if numero is None:
            return {"disponible": True, "autorizado": False}
        return {
            "disponible": True,
            "autorizado": True,
            "telefono": numero.telefono,
            "etiqueta": numero.etiqueta,
            "ultima_sincronizacion_at": numero.ultima_sincronizacion_at,
            "ultimo_mensaje_at": numero.ultimo_mensaje_at,
            "mensajes_importados": numero.mensajes_importados,
        }

    # -- webhook ----------------------------------------------------------
    async def procesar_payload(self, payload: Any) -> dict[str, int]:
        """Procesa un POST de Evolution sin dejar que un error rompa el webhook."""
        tipo, registros = eventos_del_payload(payload)
        resumen = {IMPORTADO: 0, DUPLICADO: 0, NO_AUTORIZADO: 0, AMBIGUO: 0, IGNORADO: 0, SIN_CLIENTE: 0}
        if tipo == "update":
            for item in registros:
                await self._procesar_actualizacion(item)
            return resumen
        if tipo != "upsert":
            return resumen
        for registro in registros:
            try:
                resultado = await self.ingerir(registro)
            except Exception:  # una fila mala no tumba el resto del lote
                log.exception("espejo: fallo ingiriendo un registro del webhook")
                continue
            resumen[resultado] = resumen.get(resultado, 0) + 1
            if resultado != IMPORTADO:
                # Deja rastro de por que no entro: sin esto el webhook responde
                # 200 y el mensaje parece perdido.
                clave = registro.get("key") if isinstance(registro, dict) else {}
                clave = clave if isinstance(clave, dict) else {}
                log.info(
                    "espejo: %s jid=%s alt=%s id=%s",
                    resultado,
                    clave.get("remoteJid"),
                    clave.get("remoteJidAlt"),
                    clave.get("id"),
                )
        return resumen

    async def _procesar_actualizacion(self, item: dict[str, Any]) -> None:
        clave = item.get("key") if isinstance(item.get("key"), dict) else {}
        mensaje_id = str(clave.get("id") or item.get("id") or "").strip()
        if not mensaje_id:
            return
        actualizacion = item.get("update") if isinstance(item.get("update"), dict) else {}
        crudo = (
            item.get("status")
            or actualizacion.get("status")
            or item.get("messageStatus")
            or clave.get("status")
        )
        if crudo is None:
            return
        try:
            cambiados = await self.repo.actualizar_estado(
                mensaje_id, estado_entrega(crudo)
            )
        except Exception:
            log.exception("espejo: no se pudo actualizar el estado de %s", mensaje_id)
            return
        if cambiados:
            self._avisar(
                {
                    "tipo": "estado",
                    "mensaje_id": mensaje_id,
                    "estado_entrega": estado_entrega(crudo),
                }
            )

    # -- ingesta ----------------------------------------------------------
    async def ingerir(
        self,
        registro: Any,
        *,
        numeros: dict[str, NumeroEspejo] | None = None,
        alias: dict[str, str] | None = None,
    ) -> str:
        """Guarda un mensaje solo si su telefono esta autorizado."""
        mensaje = desde_registro(registro)
        if mensaje is None:
            return IGNORADO

        if numeros is None:
            numeros = await self.repo.numeros_activos()
        if not numeros:
            return NO_AUTORIZADO
        if alias is None:
            alias = await self.repo.mapa_jids()

        identidad = resolver_jid(
            mensaje.jid, mensaje.remote_jid_alt, alias=alias
        )
        if identidad.ignorado:
            return IGNORADO
        if identidad.ambiguo and identidad.motivo == "LID_SIN_TELEFONO":
            # WhatsApp omite remoteJidAlt en muchos mensajes de chats @lid.
            # El par LID->telefono si existe en el historial de Evolution: se
            # aprende una vez, se guarda como alias y el mensaje se importa.
            telefono_lid = await self._telefono_de_lid(mensaje.jid)
            if telefono_lid:
                await self.repo.registrar_jid(mensaje.jid, telefono_lid, "LID")
                alias[mensaje.jid] = telefono_lid
                identidad = resolver_jid(
                    mensaje.jid, mensaje.remote_jid_alt, alias=alias
                )
        if identidad.ambiguo:
            await self._guardar_ambiguo(mensaje, identidad)
            return AMBIGUO

        telefono = identidad.telefono
        if not telefono:
            await self._guardar_ambiguo(mensaje, identidad)
            return AMBIGUO
        if telefono not in numeros:
            return NO_AUTORIZADO

        numero = numeros[telefono]
        if numero.cliente_id is None:
            # Numero autorizado pero sin carpeta: no se inventa un cliente.
            return SIN_CLIENTE

        # Un mismo JID no puede apuntar a dos telefonos autorizados.
        existente = alias.get(mensaje.jid)
        if existente is not None and existente != telefono:
            await self.repo.guardar_pendiente(
                jid=mensaje.jid,
                remote_jid_alt=mensaje.remote_jid_alt,
                mensaje_id=mensaje.mensaje_id,
                motivo="JID_CONFLICTO",
                from_me=mensaje.from_me,
                tipo=mensaje.tipo,
            )
            return AMBIGUO

        await self._registrar_alias(mensaje, identidad, alias)
        jid_hilo = identidad.jid_telefono or mensaje.jid
        conversacion_id = await self.repo.asegurar_conversacion(
            numero.cliente_id, jid_hilo
        )
        insertado = await self.repo.insertar_mensaje(
            conversacion_id=conversacion_id,
            mensaje=mensaje,
            telefono=telefono,
        )
        if insertado:
            await self._guardar_multimedia(mensaje, numero, conversacion_id)
            self._avisar(
                {
                    "tipo": "mensaje",
                    "cliente_id": numero.cliente_id,
                    "conversacion_id": conversacion_id,
                    "mensaje_id": mensaje.mensaje_id,
                    "direccion": mensaje.direccion,
                    "estado_entrega": mensaje.estado_entrega,
                    "adjuntos": len(mensaje.adjuntos),
                    "enviado_at": (
                        mensaje.enviado_at.isoformat() if mensaje.enviado_at else None
                    ),
                }
            )
            return IMPORTADO
        # El mensaje ya existia: el webhook puede traer un estado mas nuevo
        # que el guardado (SERVER_ACK -> DELIVERY_ACK -> READ). Se avanza, nunca
        # se retrocede; el repositorio aplica esa regla.
        if mensaje.from_me:
            cambiados = await self.repo.actualizar_estado(
                mensaje.mensaje_id, mensaje.estado_entrega
            )
            if cambiados:
                self._avisar(
                    {
                        "tipo": "estado",
                        "conversacion_id": conversacion_id,
                        "mensaje_id": mensaje.mensaje_id,
                        "estado_entrega": mensaje.estado_entrega,
                    }
                )
        return DUPLICADO

    async def _registrar_alias(
        self,
        mensaje: MensajeEspejo,
        identidad: IdentidadJid,
        alias: dict[str, str],
    ) -> None:
        if not identidad.telefono:
            return
        pares: list[tuple[str, str]] = []
        if identidad.jid_telefono:
            pares.append((identidad.jid_telefono, "PN"))
        if mensaje.jid != identidad.jid_telefono:
            pares.append((mensaje.jid, "LID" if identidad.origen == "LID" else "ALT"))
        for jid, origen in pares:
            if alias.get(jid) == identidad.telefono:
                continue
            await self.repo.registrar_jid(jid, identidad.telefono, origen)
            alias[jid] = identidad.telefono

    async def _telefono_de_lid(self, lid: str) -> str | None:
        """Telefono real de un ``@lid``, aprendido del historial de Evolution."""
        if lid in self._lids_sin_telefono:
            return None
        cliente = await self.cliente_evolution()
        if cliente is None:
            return None
        buscar = getattr(cliente, "telefono_de_lid", None)
        if not callable(buscar):
            return None
        try:
            telefono = await buscar(lid)
        except Exception:
            log.warning("espejo: no se pudo resolver el LID %s", lid, exc_info=True)
            return None
        if not telefono:
            self._lids_sin_telefono.add(lid)
            return None
        return telefono

    async def _guardar_multimedia(
        self,
        mensaje: MensajeEspejo,
        numero: NumeroEspejo,
        conversacion_id: str,
    ) -> None:
        """Baja el binario de Evolution y lo guarda como adjunto del hilo.

        Aprovecha la estructura de WhatsApp: el mensaje ya trae el tipo
        (``imageMessage``, ``audioMessage``, ...) y Evolution entrega el binario
        en base64. Un fallo aqui nunca tumba el mensaje de texto.
        """
        adjuntos = [dict(a) for a in mensaje.adjuntos if isinstance(a, dict)]
        if not adjuntos or numero.cliente_id is None or self.settings is None:
            return
        pendientes = [
            a for a in adjuntos if a.get("whatsapp_media") and not a.get("media_id")
        ]
        if not pendientes:
            return

        cliente = await self.cliente_evolution()
        obtener = getattr(cliente, "obtener_media_base64", None) if cliente else None
        if not callable(obtener):
            return
        datos_cliente = await self.repo.datos_cliente(numero.cliente_id)
        if not datos_cliente:
            return

        adjunto = pendientes[0]
        try:
            detalle = await obtener(mensaje.mensaje_id, mensaje.jid, mensaje.from_me)
        except Exception:
            log.warning(
                "espejo: no se pudo descargar la multimedia de %s",
                mensaje.mensaje_id,
                exc_info=True,
            )
            return
        if not detalle:
            return

        try:
            binario = base64.b64decode(detalle.get("base64") or "")
        except Exception:
            log.warning("espejo: base64 invalido en %s", mensaje.mensaje_id)
            return
        if not binario:
            return

        mime = detalle.get("mimetype") or adjunto.get("mime")
        nombre = detalle.get("nombre") or adjunto.get("nombre") or "archivo"
        try:
            tipo = media_svc.detectar_tipo(nombre, mime, adjunto.get("tipo"))
        except Exception:
            tipo = str(adjunto.get("tipo") or "DOCUMENTO")

        guardado = binario
        mime_final = str(mime or "application/octet-stream")
        extension = media_svc.extension(nombre) or "bin"
        if tipo == "IMAGEN":
            try:
                procesada = media_svc.comprimir_imagen(binario, self.settings)
                guardado = procesada.datos
                mime_final = procesada.mime
                extension = procesada.extension
            except Exception:
                pass  # se guarda el original
        elif tipo == "VIDEO":
            # El video entrante se recomprime igual que el que sube el panel.
            # Si dura mas que el tope, o ffmpeg no esta, se guarda el original:
            # perder el video es peor que guardarlo pesado.
            try:
                with media_svc.directorio_temporal() as tmp:
                    entrada = Path(tmp) / "entrada.bin"
                    entrada.write_bytes(binario)
                    procesada = await media_svc.procesar_video(entrada, self.settings)
                guardado = procesada.datos
                mime_final = procesada.mime
                extension = procesada.extension
            except Exception:
                log.info(
                    "espejo: el video %s se guarda sin recomprimir",
                    mensaje.mensaje_id,
                    exc_info=True,
                )

        carpeta = media_svc.carpeta_cliente(
            str(datos_cliente.get("nombre") or ""),
            datos_cliente.get("cedula"),
            datos_cliente.get("ruc"),
            numero.cliente_id,
        )
        bunny = await self._bunny_configurado()
        prefijo = str(bunny.get("prefijo") or "") if bunny else ""
        storage_path = media_svc.ruta_media(
            carpeta, tipo, extension, prefijo=prefijo
        )

        backend = "SANDBOX"
        cdn_url: str | None = None
        if bunny:
            try:
                cdn_url = await self._subir_a_bunny(
                    bunny, storage_path, guardado, mime_final
                )
                backend = "BUNNY"
            except Exception:
                log.warning(
                    "espejo: Bunny rechazo %s; se guarda en local", storage_path,
                    exc_info=True,
                )
        if backend == "SANDBOX":
            try:
                media_svc.guardar_sandbox(self.settings.media_dir, storage_path, guardado)
            except OSError:
                log.warning("espejo: no se pudo escribir %s", storage_path, exc_info=True)
                return

        try:
            media_id = await self.repo.guardar_media_entrante(
                cliente_id=numero.cliente_id,
                conversacion_id=conversacion_id,
                media={
                    "tipo": tipo,
                    "storage_path": storage_path,
                    "nombre": nombre,
                    "mime_original": mime,
                    "mime_final": mime_final,
                    "bytes": len(guardado),
                    "sha256": media_svc.sha256(guardado),
                },
                backend=backend,
                cdn_url=cdn_url,
            )
        except Exception:
            log.warning("espejo: no se pudo registrar la media", exc_info=True)
            return

        adjunto.update(
            {
                "media_id": media_id,
                "tipo": tipo,
                "mime": mime_final,
                "bytes": len(guardado),
                "nombre": nombre,
                "pendiente_descarga": False,
            }
        )
        # Reemplaza solo el adjunto resuelto, conserva el resto.
        resueltos = [
            adjunto if a.get("whatsapp_media") == adjunto.get("whatsapp_media") else a
            for a in adjuntos
        ]
        await self.repo.actualizar_adjuntos_mensaje(
            conversacion_id, mensaje.mensaje_id, resueltos
        )

    async def _bunny_configurado(self) -> dict[str, Any] | None:
        """Devuelve la config de Bunny solo si esta completa y no esta en sandbox."""
        try:
            cfg = await self.repo.config_bunny()
        except Exception:
            return None
        if not cfg:
            return None
        if cfg.get("sandbox") is True or str(cfg.get("sandbox")).lower() == "true":
            return None
        if not (cfg.get("storage_zone") and cfg.get("api_key") and cfg.get("cdn_host")):
            return None
        return cfg

    async def _subir_a_bunny(
        self,
        cfg: dict[str, Any],
        storage_path: str,
        datos: bytes,
        mime: str,
    ) -> str:
        from ..m1_whatsapp.bunny import BunnyHttpStorageClient

        cliente = BunnyHttpStorageClient(
            storage_zone=str(cfg["storage_zone"]),
            api_key=str(cfg["api_key"]),
            cdn_host=str(cfg["cdn_host"]),
            endpoint=str(
                cfg.get("endpoint")
                or getattr(self.settings, "bunny_storage_endpoint", "")
                or "https://storage.bunnycdn.com"
            ),
        )
        return await cliente.subir(
            nombre_archivo=storage_path, contenido=datos, mimetype=mime
        )

    async def _guardar_ambiguo(
        self, mensaje: MensajeEspejo, identidad: IdentidadJid
    ) -> None:
        """Solo identificadores: el contenido de un numero ajeno no se guarda."""
        await self.repo.guardar_pendiente(
            jid=mensaje.jid,
            remote_jid_alt=mensaje.remote_jid_alt,
            mensaje_id=mensaje.mensaje_id,
            motivo=identidad.motivo or "IDENTIDAD_AMBIGUA",
            from_me=mensaje.from_me,
            tipo=mensaje.tipo,
        )

    # -- backfill ---------------------------------------------------------
    async def sincronizar(
        self,
        *,
        cliente_id: str | None = None,
        telefono: str | None = None,
        max_paginas: int | None = None,
        tamano_pagina: int | None = None,
    ) -> ResultadoSincronizacion:
        """Trae el historial disponible del numero autorizado, por paginas."""
        numero = await self._resolver_numero(
            cliente_id=cliente_id, telefono=telefono
        )
        cliente = await self.cliente_evolution()
        if cliente is None:
            raise EvolutionNoConfigurado(
                "Evolution API sin URL, instancia o API key para leer el historial"
            )

        jids: list[str] = []
        for jid in [f"{numero.telefono}@s.whatsapp.net", *await self.repo.jids_de(numero.telefono)]:
            if jid and jid not in jids:
                jids.append(jid)

        numeros = await self.repo.numeros_activos()
        alias = await self.repo.mapa_jids()
        tope = max(1, int(max_paginas or self.max_paginas))
        pagina_tamano = max(1, int(tamano_pagina or self.tamano_pagina))

        importados = duplicados = paginas = omitidos = 0
        ultimo: datetime | None = None
        desde = numero.desde
        for jid in jids:
            pagina = 1
            while pagina <= tope:
                datos = await cliente.buscar_mensajes(
                    jid, page=pagina, offset=pagina_tamano
                )
                registros = datos.get("records") or []
                paginas += 1
                conocidos = 0
                anterior_a_pagina = 0
                for registro in registros:
                    previo = desde_registro(registro)
                    if previo is not None and desde is not None:
                        if previo.enviado_at < desde:
                            # Antes de que fuera cliente/lead: no se copia.
                            omitidos += 1
                            anterior_a_pagina += 1
                            conocidos += 1
                            continue
                    resultado = await self.ingerir(
                        registro, numeros=numeros, alias=alias
                    )
                    if resultado == IMPORTADO:
                        importados += 1
                        mensaje = desde_registro(registro)
                        if mensaje and (
                            ultimo is None or mensaje.enviado_at > ultimo
                        ):
                            ultimo = mensaje.enviado_at
                    elif resultado == DUPLICADO:
                        duplicados += 1
                        conocidos += 1
                    elif resultado in (NO_AUTORIZADO, IGNORADO, AMBIGUO, SIN_CLIENTE):
                        conocidos += 1
                total_paginas = int(datos.get("pages") or 0)
                if not registros:
                    break
                if total_paginas and pagina >= total_paginas:
                    break
                if self.parar_si_pagina_conocida and conocidos == len(registros):
                    break
                pagina += 1

        await self.repo.registrar_sincronizacion(
            telefono=numero.telefono,
            importados=importados,
            paginas=paginas,
            ultimo_mensaje_at=ultimo,
        )
        self._avisar(
            {
                "tipo": "sincronizado",
                "cliente_id": numero.cliente_id,
                "telefono": numero.telefono,
                "importados": importados,
            }
        )
        return ResultadoSincronizacion(
            telefono=numero.telefono,
            cliente_id=numero.cliente_id,
            importados=importados,
            duplicados=duplicados,
            paginas=paginas,
            jids=tuple(jids),
            ultimo_mensaje_at=ultimo,
            omitidos=omitidos,
        )

    async def _resolver_numero(
        self, *, cliente_id: str | None, telefono: str | None
    ) -> NumeroEspejo:
        if telefono:
            numeros = await self.repo.numeros_activos()
            numero = numeros.get(telefono)
            if numero is None:
                raise EspejoNoAutorizado(
                    f"el telefono {telefono} no esta autorizado en el espejo"
                )
            return numero
        if cliente_id:
            numero = await self.repo.numero_de_cliente(cliente_id)
            if numero is None:
                raise EspejoNoAutorizado(
                    "el cliente no tiene un telefono autorizado en el espejo"
                )
            return numero
        raise EspejoNoAutorizado("indica un cliente o un telefono autorizado")
