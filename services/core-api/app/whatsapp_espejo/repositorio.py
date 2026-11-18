"""Espejo de WhatsApp - acceso a datos.

El servicio habla con :class:`RepositorioEspejo`. La implementacion real usa
PostgreSQL; ``MemoryRepositorioEspejo`` existe para las pruebas unitarias y
replica el mismo contrato sin infraestructura.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

import asyncpg

from .mensajes import MensajeEspejo


@dataclass(frozen=True)
class NumeroEspejo:
    telefono: str
    cliente_id: str | None = None
    etiqueta: str | None = None
    activo: bool = True
    ultima_sincronizacion_at: datetime | None = None
    ultimo_mensaje_at: datetime | None = None
    mensajes_importados: int = 0
    # Corte de historial: no se copian mensajes anteriores (None = sin corte).
    desde: datetime | None = None


class RepositorioEspejo(Protocol):
    async def numeros_activos(self) -> dict[str, NumeroEspejo]: ...

    async def listar_numeros(self) -> list[dict[str, Any]]: ...

    async def numero_de_cliente(self, cliente_id: str) -> NumeroEspejo | None: ...

    async def telefono_de_cliente(self, cliente_id: str) -> str | None: ...

    async def upsert_numero(
        self,
        *,
        telefono: str,
        cliente_id: str | None,
        etiqueta: str | None,
        desde: datetime | None = None,
    ) -> None: ...

    async def activar_numero(self, telefono: str, activo: bool) -> bool: ...

    async def mapa_jids(self) -> dict[str, str]: ...

    async def jids_de(self, telefono: str) -> list[str]: ...

    async def registrar_jid(self, jid: str, telefono: str, origen: str) -> None: ...

    async def guardar_pendiente(
        self,
        *,
        jid: str,
        remote_jid_alt: str | None,
        mensaje_id: str | None,
        motivo: str,
        from_me: bool,
        tipo: str | None,
    ) -> None: ...

    async def asegurar_conversacion(self, cliente_id: str, jid: str) -> str: ...

    async def insertar_mensaje(
        self,
        *,
        conversacion_id: str,
        mensaje: MensajeEspejo,
        telefono: str,
    ) -> bool: ...

    async def actualizar_estado(self, mensaje_id: str, estado: str) -> int: ...

    async def registrar_sincronizacion(
        self,
        *,
        telefono: str,
        importados: int,
        paginas: int,
        ultimo_mensaje_at: datetime | None,
    ) -> None: ...

    async def config_evolution(self) -> dict[str, Any]: ...

    async def cliente_existe(self, cliente_id: str) -> bool: ...

    async def cliente_creado_at(self, cliente_id: str) -> datetime | None: ...

    async def datos_cliente(self, cliente_id: str) -> dict[str, Any] | None: ...

    async def config_bunny(self) -> dict[str, Any]: ...

    async def guardar_media_entrante(
        self,
        *,
        cliente_id: str,
        conversacion_id: str,
        media: dict[str, Any],
        backend: str = "SANDBOX",
        cdn_url: str | None = None,
    ) -> str: ...

    async def actualizar_adjuntos_mensaje(
        self, conversacion_id: str, mensaje_id: str, adjuntos: list[dict[str, Any]]
    ) -> None: ...


class PostgresRepositorioEspejo:
    """Implementacion real sobre las tablas 070 y 093."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def numeros_activos(self) -> dict[str, NumeroEspejo]:
        filas = await self._pool.fetch(
            """
            SELECT telefono_e164, cliente_id::text AS cliente_id, etiqueta,
                   activo, ultima_sincronizacion_at, ultimo_mensaje_at,
                   mensajes_importados, desde
              FROM whatsapp_espejo_numeros
             WHERE activo
            """
        )
        return {
            fila["telefono_e164"]: NumeroEspejo(
                telefono=fila["telefono_e164"],
                cliente_id=fila["cliente_id"],
                etiqueta=fila["etiqueta"],
                activo=fila["activo"],
                ultima_sincronizacion_at=fila["ultima_sincronizacion_at"],
                ultimo_mensaje_at=fila["ultimo_mensaje_at"],
                mensajes_importados=int(fila["mensajes_importados"] or 0),
                desde=fila["desde"],
            )
            for fila in filas
        }

    async def listar_numeros(self) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT n.telefono_e164, n.cliente_id::text AS cliente_id,
                   c.nombre AS cliente_nombre, n.etiqueta, n.activo,
                   n.ultima_sincronizacion_at, n.ultimo_mensaje_at,
                   n.mensajes_importados, n.desde
              FROM whatsapp_espejo_numeros n
              LEFT JOIN clients c ON c.id = n.cliente_id
             ORDER BY n.activo DESC, n.created_at
            """
        )
        return [dict(fila) for fila in filas]

    async def numero_de_cliente(self, cliente_id: str) -> NumeroEspejo | None:
        fila = await self._pool.fetchrow(
            """
            SELECT telefono_e164, cliente_id::text AS cliente_id, etiqueta,
                   activo, ultima_sincronizacion_at, ultimo_mensaje_at,
                   mensajes_importados, desde
              FROM whatsapp_espejo_numeros
             WHERE cliente_id = $1::uuid AND activo
             ORDER BY created_at
             LIMIT 1
            """,
            cliente_id,
        )
        if fila is None:
            return None
        return NumeroEspejo(
            telefono=fila["telefono_e164"],
            cliente_id=fila["cliente_id"],
            etiqueta=fila["etiqueta"],
            activo=fila["activo"],
            ultima_sincronizacion_at=fila["ultima_sincronizacion_at"],
            ultimo_mensaje_at=fila["ultimo_mensaje_at"],
            mensajes_importados=int(fila["mensajes_importados"] or 0),
            desde=fila["desde"],
        )

    async def telefono_de_cliente(self, cliente_id: str) -> str | None:
        numero = await self.numero_de_cliente(cliente_id)
        return numero.telefono if numero else None

    async def upsert_numero(
        self,
        *,
        telefono: str,
        cliente_id: str | None,
        etiqueta: str | None,
        desde: datetime | None = None,
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO whatsapp_espejo_numeros
                (telefono_e164, cliente_id, etiqueta, desde)
            VALUES ($1, $2::uuid, $3, $4)
            ON CONFLICT (telefono_e164) DO UPDATE
               SET cliente_id = EXCLUDED.cliente_id,
                   etiqueta = EXCLUDED.etiqueta,
                   desde = COALESCE(EXCLUDED.desde, whatsapp_espejo_numeros.desde),
                   activo = true,
                   updated_at = now()
            """,
            telefono,
            cliente_id,
            etiqueta,
            desde,
        )

    async def activar_numero(self, telefono: str, activo: bool) -> bool:
        resultado = await self._pool.execute(
            """
            UPDATE whatsapp_espejo_numeros
               SET activo = $2, updated_at = now()
             WHERE telefono_e164 = $1
            """,
            telefono,
            activo,
        )
        return resultado.split()[-1] != "0"

    async def mapa_jids(self) -> dict[str, str]:
        filas = await self._pool.fetch(
            "SELECT jid, telefono_e164 FROM whatsapp_espejo_jids"
        )
        return {fila["jid"]: fila["telefono_e164"] for fila in filas}

    async def jids_de(self, telefono: str) -> list[str]:
        filas = await self._pool.fetch(
            "SELECT jid FROM whatsapp_espejo_jids WHERE telefono_e164 = $1",
            telefono,
        )
        return [fila["jid"] for fila in filas]

    async def registrar_jid(self, jid: str, telefono: str, origen: str) -> None:
        await self._pool.execute(
            """
            INSERT INTO whatsapp_espejo_jids (jid, telefono_e164, origen)
            VALUES ($1, $2, $3)
            ON CONFLICT (jid) DO NOTHING
            """,
            jid,
            telefono,
            origen,
        )

    async def guardar_pendiente(
        self,
        *,
        jid: str,
        remote_jid_alt: str | None,
        mensaje_id: str | None,
        motivo: str,
        from_me: bool,
        tipo: str | None,
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO whatsapp_espejo_pendientes
                (jid, remote_jid_alt, mensaje_id, motivo, from_me, mensaje_tipo)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT DO NOTHING
            """,
            jid,
            remote_jid_alt,
            mensaje_id,
            motivo,
            from_me,
            tipo,
        )

    async def asegurar_conversacion(self, cliente_id: str, jid: str) -> str:
        fila = await self._pool.fetchrow(
            """
            INSERT INTO chat_conversaciones (cliente_id, canal, whatsapp_chat_id)
            VALUES ($1::uuid, 'WHATSAPP', $2)
            ON CONFLICT (cliente_id, canal) DO UPDATE
               SET whatsapp_chat_id = COALESCE(
                       chat_conversaciones.whatsapp_chat_id,
                       EXCLUDED.whatsapp_chat_id
                   )
            RETURNING id::text
            """,
            cliente_id,
            jid,
        )
        if fila is None:
            raise RuntimeError("no se pudo abrir la conversacion del espejo")
        return fila["id"]

    async def insertar_mensaje(
        self,
        *,
        conversacion_id: str,
        mensaje: MensajeEspejo,
        telefono: str,
    ) -> bool:
        metadata = {
            "origen": "evolution_espejo",
            "jid": mensaje.jid,
            "telefono": telefono,
            "from_me": mensaje.from_me,
            "tipo": mensaje.tipo,
        }
        fila = await self._pool.fetchrow(
            """
            INSERT INTO chat_mensajes (
                conversacion_id, direccion, autor_tipo, autor_nombre,
                cuerpo, adjuntos, whatsapp_msg_id, estado_entrega,
                leido_panel_at, metadata, created_at
            ) VALUES (
                $1::uuid, $2, $3, NULL,
                $4, $5::jsonb, $6, $7,
                CASE WHEN $2 = 'SALIENTE' THEN now() ELSE NULL END,
                $8::jsonb, $9
            )
            ON CONFLICT (whatsapp_msg_id) WHERE whatsapp_msg_id IS NOT NULL
            DO NOTHING
            RETURNING id::text
            """,
            conversacion_id,
            mensaje.direccion,
            mensaje.autor_tipo,
            mensaje.cuerpo,
            json.dumps(list(mensaje.adjuntos), ensure_ascii=False),
            mensaje.mensaje_id,
            mensaje.estado_entrega,
            json.dumps(metadata, ensure_ascii=False),
            mensaje.enviado_at,
        )
        return fila is not None

    async def actualizar_estado(self, mensaje_id: str, estado: str) -> int:
        resultado = await self._pool.execute(
            """
            UPDATE chat_mensajes
               SET estado_entrega = $1
             WHERE whatsapp_msg_id = $2
               AND (
                   $1 = 'FALLIDO'
                   OR CASE $1
                        WHEN 'LEIDO' THEN 4
                        WHEN 'ENTREGADO' THEN 3
                        WHEN 'ENVIADO' THEN 2
                        WHEN 'PENDIENTE' THEN 1
                        ELSE 0 END
                    > CASE estado_entrega
                        WHEN 'LEIDO' THEN 4
                        WHEN 'ENTREGADO' THEN 3
                        WHEN 'ENVIADO' THEN 2
                        WHEN 'PENDIENTE' THEN 1
                        ELSE 0 END
               )
            """,
            estado,
            mensaje_id,
        )
        return int(resultado.split()[-1]) if resultado else 0

    async def registrar_sincronizacion(
        self,
        *,
        telefono: str,
        importados: int,
        paginas: int,
        ultimo_mensaje_at: datetime | None,
    ) -> None:
        await self._pool.execute(
            """
            UPDATE whatsapp_espejo_numeros
               SET ultima_sincronizacion_at = now(),
                   ultimo_mensaje_at = GREATEST(
                       COALESCE(ultimo_mensaje_at, $2), COALESCE($2, ultimo_mensaje_at)
                   ),
                   mensajes_importados = mensajes_importados + $3,
                   updated_at = now()
             WHERE telefono_e164 = $1
            """,
            telefono,
            ultimo_mensaje_at,
            importados,
        )
        await self._pool.execute(
            """
            INSERT INTO whatsapp_espejo_cursor
                (telefono_e164, paginas_leidas, updated_at)
            VALUES ($1, $2, now())
            ON CONFLICT (telefono_e164) DO UPDATE
               SET paginas_leidas = whatsapp_espejo_cursor.paginas_leidas
                                    + EXCLUDED.paginas_leidas,
                   updated_at = now()
            """,
            telefono,
            paginas,
        )

    async def config_evolution(self) -> dict[str, Any]:
        valor = await self._pool.fetchval(
            "SELECT value FROM system_settings WHERE key = $1",
            "integraciones.evolution",
        )
        if isinstance(valor, str):
            try:
                valor = json.loads(valor)
            except ValueError:
                return {}
        return dict(valor) if isinstance(valor, dict) else {}

    async def cliente_existe(self, cliente_id: str) -> bool:
        return bool(
            await self._pool.fetchval(
                "SELECT 1 FROM clients WHERE id = $1::uuid", cliente_id
            )
        )

    async def cliente_creado_at(self, cliente_id: str) -> datetime | None:
        return await self._pool.fetchval(
            "SELECT created_at FROM clients WHERE id = $1::uuid", cliente_id
        )

    async def datos_cliente(self, cliente_id: str) -> dict[str, Any] | None:
        fila = await self._pool.fetchrow(
            "SELECT nombre, cedula, ruc FROM clients WHERE id = $1::uuid",
            cliente_id,
        )
        return dict(fila) if fila else None

    async def guardar_media_entrante(
        self,
        *,
        cliente_id: str,
        conversacion_id: str,
        media: dict[str, Any],
        backend: str = "SANDBOX",
        cdn_url: str | None = None,
    ) -> str:
        fila = await self._pool.fetchrow(
            """
            INSERT INTO media_assets (
                cliente_id, conversacion_id, tipo, backend, storage_path,
                cdn_url, nombre_original, mime_original, mime_final,
                bytes_original, bytes_final, sha256, etiquetas, metadata
            ) VALUES (
                $1::uuid, $2::uuid, $3, $4, $5,
                $6, $7, $8, $9,
                $10, $11, $12, '[]'::jsonb, $13::jsonb
            )
            RETURNING id::text
            """,
            cliente_id,
            conversacion_id,
            media["tipo"],
            backend,
            media["storage_path"],
            cdn_url,
            media.get("nombre"),
            media.get("mime_original"),
            media.get("mime_final"),
            int(media.get("bytes") or 0),
            int(media.get("bytes") or 0),
            media.get("sha256"),
            json.dumps({"origen": "whatsapp_espejo"}),
        )
        return str(fila["id"]) if fila else ""

    async def config_bunny(self) -> dict[str, Any]:
        valor = await self._pool.fetchval(
            "SELECT value FROM system_settings WHERE key = $1",
            "integraciones.bunny",
        )
        if isinstance(valor, str):
            try:
                valor = json.loads(valor)
            except ValueError:
                return {}
        return dict(valor) if isinstance(valor, dict) else {}

    async def actualizar_adjuntos_mensaje(
        self, conversacion_id: str, mensaje_id: str, adjuntos: list[dict[str, Any]]
    ) -> None:
        await self._pool.execute(
            """
            UPDATE chat_mensajes
               SET adjuntos = $3::jsonb
             WHERE conversacion_id = $1::uuid AND whatsapp_msg_id = $2
            """,
            conversacion_id,
            mensaje_id,
            json.dumps(adjuntos),
        )


@dataclass
class MemoryRepositorioEspejo:
    """Doble de prueba: mismo contrato, sin PostgreSQL."""

    numeros: dict[str, NumeroEspejo] = field(default_factory=dict)
    jids: dict[str, str] = field(default_factory=dict)
    conversaciones: dict[tuple[str, str], str] = field(default_factory=dict)
    mensajes: list[dict[str, Any]] = field(default_factory=list)
    pendientes: list[dict[str, Any]] = field(default_factory=list)
    clientes: dict[str, bool] = field(default_factory=dict)
    altas_clientes: dict[str, datetime] = field(default_factory=dict)
    media: list[dict[str, Any]] = field(default_factory=list)
    adjuntos_actualizados: list[dict[str, Any]] = field(default_factory=list)
    bunny: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    sync: list[dict[str, Any]] = field(default_factory=list)
    _secuencia: int = 0

    def _id(self, prefijo: str) -> str:
        self._secuencia += 1
        return f"{prefijo}-{self._secuencia}"

    async def numeros_activos(self) -> dict[str, NumeroEspejo]:
        return {t: n for t, n in self.numeros.items() if n.activo}

    async def listar_numeros(self) -> list[dict[str, Any]]:
        return [
            {
                "telefono_e164": n.telefono,
                "cliente_id": n.cliente_id,
                "cliente_nombre": None,
                "etiqueta": n.etiqueta,
                "activo": n.activo,
                "ultima_sincronizacion_at": n.ultima_sincronizacion_at,
                "ultimo_mensaje_at": n.ultimo_mensaje_at,
                "mensajes_importados": n.mensajes_importados,
                "desde": n.desde,
            }
            for n in self.numeros.values()
        ]

    async def numero_de_cliente(self, cliente_id: str) -> NumeroEspejo | None:
        for numero in self.numeros.values():
            if numero.cliente_id == cliente_id and numero.activo:
                return numero
        return None

    async def telefono_de_cliente(self, cliente_id: str) -> str | None:
        numero = await self.numero_de_cliente(cliente_id)
        return numero.telefono if numero else None

    async def upsert_numero(
        self,
        *,
        telefono: str,
        cliente_id: str | None,
        etiqueta: str | None,
        desde: datetime | None = None,
    ) -> None:
        anterior = self.numeros.get(telefono)
        self.numeros[telefono] = NumeroEspejo(
            telefono=telefono,
            cliente_id=cliente_id,
            etiqueta=etiqueta,
            activo=True,
            ultima_sincronizacion_at=(
                anterior.ultima_sincronizacion_at if anterior else None
            ),
            ultimo_mensaje_at=anterior.ultimo_mensaje_at if anterior else None,
            mensajes_importados=anterior.mensajes_importados if anterior else 0,
            desde=desde or (anterior.desde if anterior else None),
        )

    async def activar_numero(self, telefono: str, activo: bool) -> bool:
        numero = self.numeros.get(telefono)
        if numero is None:
            return False
        self.numeros[telefono] = NumeroEspejo(
            telefono=numero.telefono,
            cliente_id=numero.cliente_id,
            etiqueta=numero.etiqueta,
            activo=activo,
            ultima_sincronizacion_at=numero.ultima_sincronizacion_at,
            ultimo_mensaje_at=numero.ultimo_mensaje_at,
            mensajes_importados=numero.mensajes_importados,
        )
        return True

    async def mapa_jids(self) -> dict[str, str]:
        return dict(self.jids)

    async def jids_de(self, telefono: str) -> list[str]:
        return [jid for jid, destino in self.jids.items() if destino == telefono]

    async def registrar_jid(self, jid: str, telefono: str, origen: str) -> None:
        self.jids.setdefault(jid, telefono)

    async def guardar_pendiente(
        self,
        *,
        jid: str,
        remote_jid_alt: str | None,
        mensaje_id: str | None,
        motivo: str,
        from_me: bool,
        tipo: str | None,
    ) -> None:
        clave = (jid, mensaje_id)
        if any((p["jid"], p["mensaje_id"]) == clave for p in self.pendientes):
            return
        self.pendientes.append(
            {
                "jid": jid,
                "remote_jid_alt": remote_jid_alt,
                "mensaje_id": mensaje_id,
                "motivo": motivo,
                "from_me": from_me,
                "tipo": tipo,
                "created_at": datetime.now(timezone.utc),
            }
        )

    async def asegurar_conversacion(self, cliente_id: str, jid: str) -> str:
        clave = (cliente_id, "WHATSAPP")
        if clave not in self.conversaciones:
            self.conversaciones[clave] = self._id("conv")
        return self.conversaciones[clave]

    async def insertar_mensaje(
        self,
        *,
        conversacion_id: str,
        mensaje: MensajeEspejo,
        telefono: str,
    ) -> bool:
        if any(m["whatsapp_msg_id"] == mensaje.mensaje_id for m in self.mensajes):
            return False
        self.mensajes.append(
            {
                "id": self._id("msg"),
                "conversacion_id": conversacion_id,
                "direccion": mensaje.direccion,
                "autor_tipo": mensaje.autor_tipo,
                "autor_nombre": None,
                "cuerpo": mensaje.cuerpo,
                "adjuntos": list(mensaje.adjuntos),
                "whatsapp_msg_id": mensaje.mensaje_id,
                "estado_entrega": mensaje.estado_entrega,
                "telefono": telefono,
                "jid": mensaje.jid,
                "from_me": mensaje.from_me,
                "created_at": mensaje.enviado_at,
            }
        )
        return True

    async def actualizar_estado(self, mensaje_id: str, estado: str) -> int:
        rango = {"PENDIENTE": 1, "ENVIADO": 2, "ENTREGADO": 3, "LEIDO": 4}
        cambiados = 0
        for mensaje in self.mensajes:
            if mensaje["whatsapp_msg_id"] != mensaje_id:
                continue
            actual = mensaje["estado_entrega"]
            if estado == "FALLIDO" or rango.get(estado, 0) > rango.get(actual, 0):
                mensaje["estado_entrega"] = estado
                cambiados += 1
        return cambiados

    async def registrar_sincronizacion(
        self,
        *,
        telefono: str,
        importados: int,
        paginas: int,
        ultimo_mensaje_at: datetime | None,
    ) -> None:
        numero = self.numeros.get(telefono)
        if numero is not None:
            self.numeros[telefono] = NumeroEspejo(
                telefono=numero.telefono,
                cliente_id=numero.cliente_id,
                etiqueta=numero.etiqueta,
                activo=numero.activo,
                ultima_sincronizacion_at=datetime.now(timezone.utc),
                ultimo_mensaje_at=ultimo_mensaje_at or numero.ultimo_mensaje_at,
                mensajes_importados=numero.mensajes_importados + importados,
                desde=numero.desde,
            )
        self.sync.append(
            {"telefono": telefono, "importados": importados, "paginas": paginas}
        )

    async def config_evolution(self) -> dict[str, Any]:
        return dict(self.config)

    async def cliente_existe(self, cliente_id: str) -> bool:
        return bool(self.clientes.get(cliente_id, False))

    async def cliente_creado_at(self, cliente_id: str) -> datetime | None:
        return self.altas_clientes.get(cliente_id)

    async def datos_cliente(self, cliente_id: str) -> dict[str, Any] | None:
        if cliente_id not in self.clientes:
            return None
        return {"nombre": "Cliente", "cedula": None, "ruc": None}

    async def guardar_media_entrante(
        self,
        *,
        cliente_id: str,
        conversacion_id: str,
        media: dict[str, Any],
        backend: str = "SANDBOX",
        cdn_url: str | None = None,
    ) -> str:
        self.media.append(
            {"cliente_id": cliente_id, "backend": backend, "cdn_url": cdn_url, **media}
        )
        return self._id("media")

    async def config_bunny(self) -> dict[str, Any]:
        return dict(self.bunny)

    async def actualizar_adjuntos_mensaje(
        self, conversacion_id: str, mensaje_id: str, adjuntos: list[dict[str, Any]]
    ) -> None:
        self.adjuntos_actualizados.append(
            {"conversacion_id": conversacion_id, "mensaje_id": mensaje_id, "adjuntos": adjuntos}
        )
