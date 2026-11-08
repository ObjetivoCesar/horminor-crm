"""Modulo 1 - Router de identidad por rol.

Regla ratificada 2026-11-08:

1. **Identidad primaria:** telefono registrado en ``clients.telefono_whatsapp``
   (cliente) o en ``system_settings.whatsapp.staff`` (personal).
2. **Fallback:** codigo de operador escrito en el mensaje (``#BODEGA``,
   ``#CAJA``, ``#ADMIN``, ``#M1``) para el caso real de un chofer que escribe
   desde el celular prestado de un companero.
3. **Desconocido:** ``LEAD_DESCONOCIDO`` (Gate #4).

Un telefono que ya esta registrado manda sobre el codigo: nadie cambia de rol
escribiendo un prefijo.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

import asyncpg

from ..db import setting
from .models import Rol, normalizar_codigo_mixer, normalizar_telefono

log = logging.getLogger(__name__)

# Codigos de operador por defecto. La base (migracion 040) es autoritativa;
# esto solo permite que el modulo arranque si la migracion aun no corrio.
CODIGOS_POR_DEFECTO: dict[str, str] = {
    "#BODEGA": Rol.BODEGA_PLANTA.value,
    "#CAJA": Rol.CAJA_SECRETARIA.value,
    "#ADMIN": Rol.SUPERADMIN.value,
}

_PREFIJO_MIXER = re.compile(r"#\s*M\s*(\d{1,3})\b", re.IGNORECASE)
_TTL_REGISTRO_SEGUNDOS = 30.0


@dataclass(frozen=True)
class ClienteRegistrado:
    cliente_id: str
    nombre: str
    estado: str = "ACTIVO"
    telefono: str | None = None


@dataclass(frozen=True)
class RegistroIdentidad:
    """Foto de los telefonos conocidos. Se recarga cada pocos segundos."""

    staff: dict[str, Rol] = field(default_factory=dict)
    clientes: dict[str, ClienteRegistrado] = field(default_factory=dict)
    codigos: dict[str, str] = field(default_factory=lambda: dict(CODIGOS_POR_DEFECTO))


@dataclass(frozen=True)
class Identidad:
    rol: Rol
    telefono: str
    origen: str  # registro_staff | registro_cliente | codigo_operador | desconocido
    cliente_id: str | None = None
    nombre: str | None = None
    mixer_codigo: str | None = None

    @property
    def es_operador(self) -> bool:
        return self.rol in {
            Rol.SUPERADMIN,
            Rol.CAJA_SECRETARIA,
            Rol.BODEGA_PLANTA,
            Rol.CHOFER_MIXER,
        }

    def a_dict(self) -> dict[str, Any]:
        return {
            "rol": self.rol.value,
            "telefono": self.telefono,
            "origen": self.origen,
            "cliente_id": self.cliente_id,
            "nombre": self.nombre,
            "mixer_codigo": self.mixer_codigo,
        }


def _codigos_desde_settings(valor: Any) -> dict[str, str]:
    """Normaliza el jsonb de codigos a ``{"#BODEGA": "BODEGA_PLANTA"}``."""
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except ValueError:
            return dict(CODIGOS_POR_DEFECTO)
    if not isinstance(valor, Mapping):
        return dict(CODIGOS_POR_DEFECTO)
    limpio: dict[str, str] = {}
    for clave, destino in valor.items():
        rol = Rol.desde_texto(destino)
        if rol is not None:
            limpio[str(clave).strip().upper()] = rol.value
    return limpio or dict(CODIGOS_POR_DEFECTO)


class IdentityResolver:
    """Resuelve telefono + texto a un rol operativo."""

    def __init__(
        self,
        *,
        pool: asyncpg.Pool | None = None,
        registro: RegistroIdentidad | None = None,
        ttl_segundos: float = _TTL_REGISTRO_SEGUNDOS,
    ) -> None:
        self._pool = pool
        self._registro_fijo = registro
        self._ttl = max(float(ttl_segundos), 0.0)
        self._cache: RegistroIdentidad | None = registro
        self._cache_at = time.monotonic()

    # -- carga ------------------------------------------------------------
    async def _cargar(self) -> RegistroIdentidad:
        if self._pool is None:
            return self._registro_fijo or RegistroIdentidad()

        ahora = time.monotonic()
        if self._cache is not None and (ahora - self._cache_at) < self._ttl:
            return self._cache

        staff_raw = await setting(self._pool, "whatsapp.staff", {}) or {}
        if isinstance(staff_raw, str):
            try:
                staff_raw = json.loads(staff_raw)
            except ValueError:
                staff_raw = {}
        staff: dict[str, Rol] = {}
        if isinstance(staff_raw, Mapping):
            for telefono, rol_crudo in staff_raw.items():
                rol = Rol.desde_texto(rol_crudo)
                clave = normalizar_telefono(telefono)
                if rol is not None and clave:
                    staff[clave] = rol

        clientes: dict[str, ClienteRegistrado] = {}
        filas = await self._pool.fetch(
            """
            SELECT id::text AS cliente_id, nombre, estado, telefono_whatsapp
              FROM clients
             WHERE telefono_whatsapp IS NOT NULL
            """
        )
        for fila in filas:
            clave = normalizar_telefono(fila["telefono_whatsapp"])
            if clave:
                clientes[clave] = ClienteRegistrado(
                    cliente_id=fila["cliente_id"],
                    nombre=fila["nombre"],
                    estado=str(fila["estado"]),
                    telefono=fila["telefono_whatsapp"],
                )

        codigos = _codigos_desde_settings(
            await setting(self._pool, "whatsapp.codigos_operador", CODIGOS_POR_DEFECTO)
        )

        self._cache = RegistroIdentidad(staff=staff, clientes=clientes, codigos=codigos)
        self._cache_at = ahora
        return self._cache

    def invalidar_cache(self) -> None:
        """Fuerza recarga: se llama cuando un lead se convierte en cliente."""
        if self._pool is not None:
            self._cache = None

    # -- resolucion -------------------------------------------------------
    async def resolver(self, telefono: str, texto: str | None = None) -> Identidad:
        clave = normalizar_telefono(telefono)
        registro = await self._cargar()

        if clave and clave in registro.staff:
            return Identidad(
                rol=registro.staff[clave],
                telefono=telefono,
                origen="registro_staff",
            )

        if clave and clave in registro.clientes:
            cliente = registro.clientes[clave]
            if cliente.estado == "ACTIVO":
                return Identidad(
                    rol=Rol.CLIENTE,
                    telefono=telefono,
                    origen="registro_cliente",
                    cliente_id=cliente.cliente_id,
                    nombre=cliente.nombre,
                )
            # PROSPECTO / INACTIVO siguen el flujo de lead, pero conservamos
            # el id para no duplicar la ficha del cliente.
            return Identidad(
                rol=Rol.LEAD_DESCONOCIDO,
                telefono=telefono,
                origen="registro_cliente",
                cliente_id=cliente.cliente_id,
                nombre=cliente.nombre,
            )

        crudo = texto or ""
        mayusculas = crudo.upper()
        # Los codigos de operador escritos por la persona (protocolo interno)
        # mandan sobre la referencia a un mixer: un bodeguero que reporta
        # "salio el mixer #M1 #BODEGA" se identifica como bodega, no como
        # chofer. Los codigos mas largos primero para que "#BODEGA2" no gane
        # por prefijo.
        for codigo in sorted(registro.codigos, key=len, reverse=True):
            if codigo and re.search(re.escape(codigo) + r"\b", mayusculas):
                rol = Rol.desde_texto(registro.codigos[codigo])
                if rol is not None:
                    return Identidad(
                        rol=rol,
                        telefono=telefono,
                        origen="codigo_operador",
                    )

        mixer = _PREFIJO_MIXER.search(crudo)
        if mixer:
            return Identidad(
                rol=Rol.CHOFER_MIXER,
                telefono=telefono,
                origen="codigo_operador",
                mixer_codigo=normalizar_codigo_mixer(mixer.group(1)),
            )

        return Identidad(
            rol=Rol.LEAD_DESCONOCIDO,
            telefono=telefono,
            origen="desconocido",
        )
