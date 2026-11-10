"""Perfiles de panel y checklist de modulos (v6.2).

La tabla ``panel_users_acl`` define que modulos ve cada usuario y si opera en
``EDICION`` o ``SOLO_LECTURA``. Mientras no exista login, el panel simula un
usuario con el header ``X-Panel-User``. Sin header se mantiene el

comportamiento historico (Superadmin con todos los modulos) para no romper
scripts ni tests existentes.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Protocol
from uuid import UUID

import asyncpg
from fastapi import HTTPException, Request

MODULOS: tuple[str, ...] = (
    "dashboard_gerencial",
    "secretaria_ventanilla",
    "secretaria_cobros_gastos",
    "secretaria_cierre_caja",
    "agenda_despachos",
    "compras_materiales",
    "planta_kardex",
    "clientes_cartera",
    "finanzas_balance_auditoria",
    "superadmin_config",
)

ROLES_BASE: tuple[str, ...] = (
    "SUPERADMIN",
    "SECRETARIA",
    "CONTADORA",
    "BODEGA",
    "CHOFER",
    "VENDEDOR",
    "AUDITOR_EXTERNO",
)

MODOS_ACCESO = ("SOLO_LECTURA", "EDICION")


def modulos_vacios() -> dict[str, bool]:
    return {modulo: False for modulo in MODULOS}


def modulos_todos() -> dict[str, bool]:
    return {modulo: True for modulo in MODULOS}


def normalizar_modulos(valor: Any) -> dict[str, bool]:
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except ValueError:
            valor = {}
    datos = valor if isinstance(valor, Mapping) else {}
    return {modulo: bool(datos.get(modulo, False)) for modulo in MODULOS}


def modulos_activos(valor: Any) -> list[str]:
    return [modulo for modulo, activo in normalizar_modulos(valor).items() if activo]


def _perfil_publico(fila: Mapping[str, Any]) -> dict[str, Any]:
    modulos = normalizar_modulos(fila.get("modulos_permitidos"))
    return {
        "id": str(fila["id"]) if fila.get("id") else None,
        "nombre": fila.get("nombre"),
        "rol_base": fila.get("rol_base"),
        "telefono_whatsapp": fila.get("telefono_whatsapp"),
        "activo": bool(fila.get("activo", True)),
        "modulos_permitidos": modulos,
        "modulos_activos": [m for m, activo in modulos.items() if activo],
        "modo_acceso": fila.get("modo_acceso", "EDICION"),
    }


PERFIL_DEFECTO = _perfil_publico(
    {
        "id": None,
        "nombre": "Julio Villavicencio",
        "rol_base": "SUPERADMIN",
        "telefono_whatsapp": None,
        "activo": True,
        "modulos_permitidos": modulos_todos(),
        "modo_acceso": "EDICION",
    }
)


def _validar_texto(valor: Any, campo: str, *, obligatorio: bool, max_len: int) -> str | None:
    texto = str(valor or "").strip()
    if not texto:
        if obligatorio:
            raise ValueError(f"{campo} es obligatorio")
        return None
    if len(texto) > max_len:
        raise ValueError(f"{campo} supera {max_len} caracteres")
    return texto


def validar_usuario(datos: Mapping[str, Any], *, parcial: bool = False) -> dict[str, Any]:
    """Normaliza y valida un usuario/perfil. Lanza ``ValueError``."""
    salida: dict[str, Any] = {}
    if not parcial or "nombre" in datos:
        salida["nombre"] = _validar_texto(
            datos.get("nombre"), "nombre", obligatorio=True, max_len=120
        )
    if not parcial or "rol_base" in datos:
        rol = str(datos.get("rol_base") or "").strip().upper()
        if rol not in ROLES_BASE:
            raise ValueError(f"rol_base invalido: {rol or '(vacio)'}")
        salida["rol_base"] = rol
    if not parcial or "modo_acceso" in datos:
        modo = str(datos.get("modo_acceso") or "EDICION").strip().upper()
        if modo not in MODOS_ACCESO:
            raise ValueError(f"modo_acceso invalido: {modo}")
        salida["modo_acceso"] = modo
    if "telefono_whatsapp" in datos or not parcial:
        salida["telefono_whatsapp"] = _validar_texto(
            datos.get("telefono_whatsapp"),
            "telefono_whatsapp",
            obligatorio=False,
            max_len=30,
        )
    if "activo" in datos or not parcial:
        salida["activo"] = bool(datos.get("activo", True))
    if "modulos_permitidos" in datos or not parcial:
        modulos = normalizar_modulos(datos.get("modulos_permitidos"))
        if not any(modulos.values()):
            raise ValueError("marca al menos un modulo en el checklist")
        salida["modulos_permitidos"] = modulos
    return salida


class PanelUserStore(Protocol):
    async def listar(self, solo_activos: bool = True) -> list[dict[str, Any]]: ...

    async def obtener(self, usuario_id: str) -> dict[str, Any] | None: ...

    async def crear(self, datos: Mapping[str, Any]) -> dict[str, Any]: ...

    async def actualizar(
        self, usuario_id: str, datos: Mapping[str, Any]
    ) -> dict[str, Any] | None: ...

    async def eliminar(self, usuario_id: str) -> bool: ...


def _fila_a_dict(fila: Mapping[str, Any]) -> dict[str, Any]:
    datos = dict(fila)
    datos["modulos_permitidos"] = normalizar_modulos(datos.get("modulos_permitidos"))
    return _perfil_publico(datos)


class PostgresPanelUserStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def listar(self, solo_activos: bool = True) -> list[dict[str, Any]]:
        where = "deleted_at IS NULL"
        if solo_activos:
            where += " AND activo = true"
        filas = await self._pool.fetch(
            f"""
            SELECT id, nombre, rol_base, telefono_whatsapp, activo,
                   modulos_permitidos, modo_acceso, created_at, updated_at
              FROM panel_users_acl
             WHERE {where}
             ORDER BY nombre
            """
        )
        return [_fila_a_dict(fila) for fila in filas]

    async def obtener(self, usuario_id: str) -> dict[str, Any] | None:
        try:
            UUID(str(usuario_id))
        except ValueError:
            return None
        fila = await self._pool.fetchrow(
            """
            SELECT id, nombre, rol_base, telefono_whatsapp, activo,
                   modulos_permitidos, modo_acceso, created_at, updated_at
              FROM panel_users_acl
             WHERE id = $1 AND deleted_at IS NULL
            """,
            usuario_id,
        )
        return _fila_a_dict(fila) if fila else None

    async def crear(self, datos: Mapping[str, Any]) -> dict[str, Any]:
        fila = await self._pool.fetchrow(
            """
            INSERT INTO panel_users_acl
                (nombre, rol_base, telefono_whatsapp, activo,
                 modulos_permitidos, modo_acceso)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6)
            RETURNING id
            """,
            datos["nombre"],
            datos["rol_base"],
            datos.get("telefono_whatsapp"),
            bool(datos.get("activo", True)),
            json.dumps(datos["modulos_permitidos"]),
            datos["modo_acceso"],
        )
        return await self.obtener(str(fila["id"]))

    async def actualizar(
        self, usuario_id: str, datos: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        if not datos:
            return await self.obtener(usuario_id)
        columnas = {
            "nombre": "nombre",
            "rol_base": "rol_base",
            "telefono_whatsapp": "telefono_whatsapp",
            "activo": "activo",
            "modo_acceso": "modo_acceso",
        }
        asignaciones: list[str] = []
        valores: list[Any] = []
        indice = 1
        for campo, columna in columnas.items():
            if campo in datos:
                asignaciones.append(f"{columna} = ${indice}")
                valores.append(datos[campo])
                indice += 1
        if "modulos_permitidos" in datos:
            asignaciones.append(f"modulos_permitidos = ${indice}::jsonb")
            valores.append(json.dumps(datos["modulos_permitidos"]))
            indice += 1
        if not asignaciones:
            return await self.obtener(usuario_id)
        valores.append(usuario_id)
        fila = await self._pool.fetchrow(
            f"""
            UPDATE panel_users_acl
               SET {', '.join(asignaciones)}, updated_at = now()
             WHERE id = ${indice} AND deleted_at IS NULL
            RETURNING id
            """,
            *valores,
        )
        return await self.obtener(str(fila["id"])) if fila else None

    async def eliminar(self, usuario_id: str) -> bool:
        try:
            UUID(str(usuario_id))
        except ValueError:
            return False
        fila = await self._pool.fetchrow(
            """
            UPDATE panel_users_acl
               SET activo = false, deleted_at = now(), updated_at = now()
             WHERE id = $1 AND deleted_at IS NULL
            RETURNING id
            """,
            usuario_id,
        )
        return fila is not None


class MemoryPanelUserStore:
    """Store en memoria para tests y simulacion sin PostgreSQL."""

    def __init__(self, usuarios: list[Mapping[str, Any]] | None = None) -> None:
        from uuid import uuid4

        self._uuid4 = uuid4
        self.usuarios: list[dict[str, Any]] = []
        for usuario in usuarios or []:
            datos = dict(usuario)
            datos.setdefault("id", str(uuid4()))
            datos.setdefault("activo", True)
            datos.setdefault("modo_acceso", "EDICION")
            datos["modulos_permitidos"] = normalizar_modulos(
                datos.get("modulos_permitidos")
            )
            self.usuarios.append(datos)

    def _publico(self, fila: Mapping[str, Any]) -> dict[str, Any]:
        return _perfil_publico(fila)

    async def listar(self, solo_activos: bool = True) -> list[dict[str, Any]]:
        return [
            self._publico(u)
            for u in self.usuarios
            if not u.get("deleted_at") and (u.get("activo", True) or not solo_activos)
        ]

    async def obtener(self, usuario_id: str) -> dict[str, Any] | None:
        for usuario in self.usuarios:
            if str(usuario.get("id")) == str(usuario_id) and not usuario.get("deleted_at"):
                return self._publico(usuario)
        return None

    async def crear(self, datos: Mapping[str, Any]) -> dict[str, Any]:
        usuario = dict(datos)
        usuario["id"] = str(self._uuid4())
        usuario["modulos_permitidos"] = normalizar_modulos(
            datos.get("modulos_permitidos")
        )
        self.usuarios.append(usuario)
        return self._publico(usuario)

    async def actualizar(
        self, usuario_id: str, datos: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        for usuario in self.usuarios:
            if str(usuario.get("id")) == str(usuario_id) and not usuario.get("deleted_at"):
                usuario.update(datos)
                if "modulos_permitidos" in datos:
                    usuario["modulos_permitidos"] = normalizar_modulos(
                        datos["modulos_permitidos"]
                    )
                return self._publico(usuario)
        return None

    async def eliminar(self, usuario_id: str) -> bool:
        for usuario in self.usuarios:
            if str(usuario.get("id")) == str(usuario_id) and not usuario.get("deleted_at"):
                usuario["deleted_at"] = True
                usuario["activo"] = False
                return True
        return False


def _store(request: Request) -> PanelUserStore:
    configurado = getattr(request.app.state, "panel_user_store", None)
    if configurado is not None:
        return configurado
    pool = getattr(request.app.state, "pool", None)
    if not isinstance(pool, asyncpg.Pool):
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "pool no disponible"},
        )
    store = PostgresPanelUserStore(pool)
    request.app.state.panel_user_store = store
    return store


async def resolver_perfil(request: Request) -> dict[str, Any]:
    """Perfil simulado por ``X-Panel-User``; sin header usa el perfil base."""
    usuario_id = (request.headers.get("X-Panel-User") or "").strip()
    if not usuario_id:
        return PERFIL_DEFECTO
    perfil = await _store(request).obtener(usuario_id)
    if perfil is None or not perfil.get("activo", True):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "INVALID_PANEL_USER",
                "message": "el usuario simulado no existe o esta inactivo",
            },
        )
    return perfil


async def exigir_modulos(
    request: Request,
    modulos: tuple[str, ...] | set[str] | str,
    *,
    mutacion: bool = False,
    requiere_todos: bool = False,
) -> dict[str, Any]:
    """Valida el perfil activo contra uno o varios modulos."""
    perfil = await resolver_perfil(request)
    if mutacion and perfil.get("modo_acceso") == "SOLO_LECTURA":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "READ_ONLY_PROFILE",
                "message": "el perfil simulado es de solo lectura",
            },
        )
    requeridos = (modulos,) if isinstance(modulos, str) else tuple(modulos)
    permitidos = perfil.get("modulos_permitidos") or {}
    if requeridos:
        if requiere_todos:
            autorizado = all(permitidos.get(m) for m in requeridos)
        else:
            autorizado = any(permitidos.get(m) for m in requeridos)
        if not autorizado:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "MODULE_NOT_ALLOWED",
                    "message": "el perfil no tiene permiso sobre este modulo",
                    "modulos": list(requeridos),
                },
            )
    return perfil


async def exigir_modulo(
    request: Request, modulo: str, *, mutacion: bool = False
) -> dict[str, Any]:
    return await exigir_modulos(request, modulo, mutacion=mutacion)
