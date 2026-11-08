"""Centro de Configuracion Superadmin - persistencia en Modulo 0.

Dos implementaciones del mismo contrato:

- :class:`PostgresConfigStore` -> la real (PostgreSQL).
- :class:`MemoryConfigStore`   -> tests y simulacion, sin base de datos.

Las secciones leen y escriben en ``system_settings``, ``concrete_recipes``,
``materials`` y ``market_benchmarks``. Nada se cachea en el proceso: un cambio
hecho por el Superadmin se ve en la siguiente peticion de cualquier modulo.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Mapping, Protocol

import asyncpg

from ..m2_planta import normalizar_politica
from .secciones import (
    SECCION_BODEGA,
    SECCION_DIRECTORIO,
    SECCION_EMPRESA,
    SECCION_FINANZAS,
    SECCION_FLOTA,
    SECCION_FORMULAS,
    SECCION_WHATSAPP,
    SECCIONES,
)

_DESCRIPCIONES = {
    "integraciones.evolution": (
        "Configuracion de Evolution API. Editable en Superadmin > "
        "whatsapp_evolution_y_cdn."
    ),
    "integraciones.bunny": (
        "Storage Zone, host CDN y API key de Bunny.net. Editable en Superadmin > "
        "whatsapp_evolution_y_cdn."
    ),
    "operacion.debounce_segundos": (
        "Ventana de agrupacion de mensajes de WhatsApp. Editable en Superadmin."
    ),
    "empresa.bot_publico": (
        "ADN publico de Orminorth que usa el bot para responder leads. "
        "Editable en Superadmin > empresa_bot_publico."
    ),
    "flota.mixers": (
        "Flota de mixers. Editable en Superadmin > flota_y_operacion."
    ),
    "operacion.politica_redondeo_viajes": (
        "Politica del ultimo viaje: PARCIAL | COMPLETO | UNIFORME."
    ),
    "operacion.reloj_termico_minutos": (
        "Ventana maxima de fraguado desde la salida de planta."
    ),
    "operacion.alerta_temprana_minutos_antes": (
        "Minutos antes del limite para ALERTA_TEMPRANA."
    ),
    "operacion.por_vencer_critico_minutos_antes": (
        "Minutos antes del limite para POR_VENCER_CRITICO."
    ),
    "whatsapp.staff": (
        "Mapa telefono -> rol: SUPERADMIN | CAJA_SECRETARIA | BODEGA_PLANTA | "
        "CHOFER_MIXER. Editable en Superadmin > directorio_roles_whatsapp."
    ),
    "whatsapp.codigos_operador": (
        "Codigos PIN de fallback por mensaje. Editable en Superadmin > "
        "directorio_roles_whatsapp."
    ),
    "bodega.umbrales_por_planta": (
        "Umbrales y costos por planta. Editable en Superadmin > bodega_y_umbrales."
    ),
    "finanzas.tope_credito_auto": (
        "Tope de fiado automatico sin clave gerencial. NULL = no autorizado."
    ),
    "finanzas.simulador": (
        "Parametros del Simulador Bancario. Editable en Superadmin > "
        "finanzas_y_ases_gerenciales."
    ),
}

_POLITICA_CORTA = {
    "ultimo_parcial": "PARCIAL",
    "ultimo_completo": "COMPLETO",
    "distribucion_uniforme": "UNIFORME",
}


# ---------------------------------------------------------------------------
# Normalizacion de valores JSON / numericos
# ---------------------------------------------------------------------------
def _json(valor: Any, por_defecto: Any = None) -> Any:
    if valor is None:
        return por_defecto
    if isinstance(valor, str):
        try:
            return json.loads(valor)
        except ValueError:
            return por_defecto
    return valor


def _num(valor: Any) -> float | None:
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _texto(valor: Any) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _booleano(valor: Any) -> bool:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        return valor.strip().lower() in {"1", "true", "si", "sí", "yes"}
    return bool(valor)


# ---------------------------------------------------------------------------
# Contrato
# ---------------------------------------------------------------------------
class ConfigStore(Protocol):
    async def leer_todo(self) -> dict[str, Any]: ...

    async def leer_seccion(self, seccion: str) -> dict[str, Any]: ...

    async def guardar_seccion(
        self, seccion: str, datos: Mapping[str, Any]
    ) -> dict[str, Any]: ...

    async def listar_recetas(self) -> list[dict[str, Any]]: ...

    async def upsert_receta(self, datos: Mapping[str, Any]) -> dict[str, Any]: ...

    async def eliminar_receta(self, resistencia: str) -> bool: ...

    async def listar_flota(self) -> list[dict[str, Any]]: ...

    async def upsert_mixer(self, datos: Mapping[str, Any]) -> dict[str, Any]: ...

    async def eliminar_mixer(self, codigo: str) -> bool: ...


# ---------------------------------------------------------------------------
# Helpers de recetas / flota (compartidos por ambos backends)
# ---------------------------------------------------------------------------
_CAMPOS_RECETA = (
    "cemento_sacos_m3",
    "arena_m3_m3",
    "ripio_m3_m3",
    "agua_litros_m3",
    "retardante_litros_m3",
    "saco_kg",
    "precio_m3",
)


def _normalizar_receta(datos: Mapping[str, Any]) -> dict[str, Any]:
    resistencia = _texto(datos.get("resistencia") or datos.get("codigo"))
    if not resistencia:
        raise ValueError("La receta necesita 'resistencia' (ej. FC-210)")
    receta: dict[str, Any] = {
        "resistencia": resistencia.upper().replace(" ", "-"),
        "confirmado": _booleano(datos.get("confirmado", True)),
        "fuente": _texto(datos.get("fuente")),
        "uso_comercial": _texto(datos.get("uso_comercial")),
    }
    for campo in _CAMPOS_RECETA:
        receta[campo] = _num(datos.get(campo))
    receta["iva_pct"] = _num(datos.get("iva_pct"))
    if receta["iva_pct"] is None:
        receta["iva_pct"] = 15.0
    return receta


def _normalizar_mixer(datos: Mapping[str, Any]) -> dict[str, Any]:
    codigo = _texto(datos.get("codigo") or datos.get("codigo_mixer"))
    if not codigo:
        raise ValueError("El mixer necesita 'codigo' (ej. MIXER-01)")
    capacidad = _num(datos.get("capacidad_m3"))
    if capacidad is None or capacidad <= 0:
        raise ValueError("El mixer necesita 'capacidad_m3' mayor que 0")
    return {
        "codigo": codigo.upper(),
        "placa": _texto(datos.get("placa")),
        "capacidad_m3": capacidad,
        "chofer_asignado": _texto(
            datos.get("chofer_asignado") or datos.get("chofer")
        ),
        "activo": _booleano(datos.get("activo", True)),
    }


def _upsert_lista(
    lista: list[dict[str, Any]], item: dict[str, Any], clave: str
) -> list[dict[str, Any]]:
    resultado = [dict(elemento) for elemento in lista]
    for indice, elemento in enumerate(resultado):
        if str(elemento.get(clave, "")).upper() == str(item[clave]).upper():
            resultado[indice] = {**elemento, **item}
            return resultado
    resultado.append(item)
    return resultado


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------
class PostgresConfigStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # -- settings ---------------------------------------------------------
    async def _setting(self, clave: str, por_defecto: Any = None) -> Any:
        fila = await self._pool.fetchrow(
            "SELECT value FROM system_settings WHERE key = $1", clave
        )
        if fila is None:
            return por_defecto
        return _json(fila["value"], por_defecto)

    async def _guardar_setting(self, clave: str, valor: Any) -> None:
        await self._pool.execute(
            """
            INSERT INTO system_settings (key, value, descripcion)
            VALUES ($1, $2::jsonb, $3)
            ON CONFLICT (key) DO UPDATE
               SET value = EXCLUDED.value,
                   descripcion = COALESCE(EXCLUDED.descripcion, system_settings.descripcion),
                   actualizado_at = now()
            """,
            clave,
            json.dumps(valor, ensure_ascii=False, default=str),
            _DESCRIPCIONES.get(clave),
        )

    # -- recetas ----------------------------------------------------------
    async def listar_recetas(self) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT resistencia, cemento_sacos_m3, arena_m3_m3, ripio_m3_m3,
                   agua_litros_m3, retardante_litros_m3, saco_kg, confirmado,
                   fuente, precio_m3, iva_pct, uso_comercial
              FROM concrete_recipes
             ORDER BY resistencia
            """
        )
        return [
            {
                "resistencia": fila["resistencia"],
                "cemento_sacos_m3": _num(fila["cemento_sacos_m3"]),
                "arena_m3_m3": _num(fila["arena_m3_m3"]),
                "ripio_m3_m3": _num(fila["ripio_m3_m3"]),
                "agua_litros_m3": _num(fila["agua_litros_m3"]),
                "retardante_litros_m3": _num(fila["retardante_litros_m3"]),
                "saco_kg": _num(fila["saco_kg"]),
                "confirmado": bool(fila["confirmado"]),
                "fuente": fila["fuente"],
                "precio_m3": _num(fila["precio_m3"]),
                "iva_pct": _num(fila["iva_pct"]),
                "uso_comercial": fila["uso_comercial"],
            }
            for fila in filas
        ]

    async def upsert_receta(self, datos: Mapping[str, Any]) -> dict[str, Any]:
        crudo = dict(datos)
        clave = _texto(datos.get("resistencia") or datos.get("codigo"))
        if clave:
            existente = await self._pool.fetchrow(
                "SELECT * FROM concrete_recipes WHERE resistencia = $1",
                clave.upper().replace(" ", "-"),
            )
            if existente is not None:
                crudo = {**dict(existente), **crudo}
        receta = _normalizar_receta(crudo)
        await self._pool.execute(
            """
            INSERT INTO concrete_recipes
                (resistencia, cemento_sacos_m3, arena_m3_m3, ripio_m3_m3,
                 agua_litros_m3, retardante_litros_m3, saco_kg, confirmado,
                 fuente, precio_m3, iva_pct, uso_comercial)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (resistencia) DO UPDATE
               SET cemento_sacos_m3     = EXCLUDED.cemento_sacos_m3,
                   arena_m3_m3          = EXCLUDED.arena_m3_m3,
                   ripio_m3_m3          = EXCLUDED.ripio_m3_m3,
                   agua_litros_m3       = EXCLUDED.agua_litros_m3,
                   retardante_litros_m3 = EXCLUDED.retardante_litros_m3,
                   saco_kg              = EXCLUDED.saco_kg,
                   confirmado           = EXCLUDED.confirmado,
                   fuente               = EXCLUDED.fuente,
                   precio_m3            = EXCLUDED.precio_m3,
                   iva_pct              = EXCLUDED.iva_pct,
                   uso_comercial        = EXCLUDED.uso_comercial,
                   updated_at           = now()
            """,
            receta["resistencia"],
            receta["cemento_sacos_m3"],
            receta["arena_m3_m3"],
            receta["ripio_m3_m3"],
            receta["agua_litros_m3"],
            receta["retardante_litros_m3"],
            receta["saco_kg"],
            receta["confirmado"],
            receta["fuente"],
            receta["precio_m3"],
            receta["iva_pct"],
            receta["uso_comercial"],
        )
        return receta

    async def eliminar_receta(self, resistencia: str) -> bool:
        fila = await self._pool.fetchrow(
            "DELETE FROM concrete_recipes WHERE resistencia = $1 RETURNING resistencia",
            resistencia.upper().replace(" ", "-"),
        )
        return fila is not None

    # -- flota ------------------------------------------------------------
    async def listar_flota(self) -> list[dict[str, Any]]:
        datos = await self._setting("flota.mixers", [])
        return [dict(m) for m in datos] if isinstance(datos, list) else []

    async def upsert_mixer(self, datos: Mapping[str, Any]) -> dict[str, Any]:
        flota = await self.listar_flota()
        codigo = _texto(datos.get("codigo") or datos.get("codigo_mixer")) or ""
        actual = next(
            (
                m
                for m in flota
                if str(m.get("codigo", "")).upper() == codigo.upper()
            ),
            None,
        )
        crudo = {**actual, **dict(datos)} if actual else dict(datos)
        mixer = _normalizar_mixer(crudo)
        flota = _upsert_lista(flota, mixer, "codigo")
        await self._guardar_setting("flota.mixers", flota)
        return mixer

    async def eliminar_mixer(self, codigo: str) -> bool:
        flota = await self.listar_flota()
        filtrada = [
            m
            for m in flota
            if str(m.get("codigo", "")).upper() != codigo.upper()
        ]
        if len(filtrada) == len(flota):
            return False
        await self._guardar_setting("flota.mixers", filtrada)
        return True

    # -- secciones --------------------------------------------------------
    async def leer_seccion(self, seccion: str) -> dict[str, Any]:
        if seccion == SECCION_FORMULAS:
            return {"recetas": await self.listar_recetas()}

        if seccion == SECCION_WHATSAPP:
            evolution = await self._setting("integraciones.evolution", {}) or {}
            bunny = await self._setting("integraciones.bunny", {}) or {}
            debounce = await self._setting("operacion.debounce_segundos", 14)
            return {
                "evolution_api_url": evolution.get("url"),
                "evolution_instance_name": evolution.get("instancia"),
                "evolution_api_key": evolution.get("api_key"),
                "debounce_seconds": _num(debounce) or 14.0,
                "bunny_storage_zone": bunny.get("storage_zone"),
                "bunny_api_key": bunny.get("api_key"),
                "bunny_cdn_domain": bunny.get("cdn_host"),
            }

        if seccion == SECCION_EMPRESA:
            return dict(await self._setting("empresa.bot_publico", {}) or {})

        if seccion == SECCION_FLOTA:
            mixers = await self.listar_flota()
            politica = await self._setting(
                "operacion.politica_redondeo_viajes", "PARCIAL"
            )
            maximo = _num(
                await self._setting("operacion.reloj_termico_minutos", 150)
            ) or 150.0
            antes_temprana = _num(
                await self._setting("operacion.alerta_temprana_minutos_antes", 60)
            ) or 60.0
            antes_critica = _num(
                await self._setting("operacion.por_vencer_critico_minutos_antes", 30)
            ) or 30.0
            return {
                "mixers": mixers,
                "politica_ultimo_viaje": _POLITICA_CORTA.get(
                    normalizar_politica(str(politica)), "PARCIAL"
                ),
                "reloj_termico": {
                    "max_fraguado_minutes": int(maximo),
                    "alerta_temprana_min": int(maximo - antes_temprana),
                    "alerta_critica_min": int(maximo - antes_critica),
                },
            }

        if seccion == SECCION_DIRECTORIO:
            return {
                "staff": dict(await self._setting("whatsapp.staff", {}) or {}),
                "codigos_operador": dict(
                    await self._setting("whatsapp.codigos_operador", {}) or {}
                ),
            }

        if seccion == SECCION_BODEGA:
            filas = await self._pool.fetch(
                """
                SELECT codigo, nombre, unidad, stock_actual, stock_minimo,
                       costo_unitario
                  FROM materials
                 ORDER BY codigo
                """
            )
            return {
                "materiales": [
                    {
                        "codigo": fila["codigo"],
                        "nombre": fila["nombre"],
                        "unidad": fila["unidad"],
                        "stock_actual": _num(fila["stock_actual"]),
                        "stock_minimo": _num(fila["stock_minimo"]),
                        "costo_unitario": _num(fila["costo_unitario"]),
                    }
                    for fila in filas
                ],
                "por_planta": dict(
                    await self._setting("bodega.umbrales_por_planta", {}) or {}
                ),
            }

        if seccion == SECCION_FINANZAS:
            filas = await self._pool.fetch(
                """
                SELECT provincia, anio, demanda_m3, precio_promedio_m3, fuente
                  FROM market_benchmarks
                 ORDER BY provincia
                """
            )
            return {
                "tope_credito_auto": await self._setting(
                    "finanzas.tope_credito_auto"
                ),
                "simulador": dict(
                    await self._setting("finanzas.simulador", {}) or {}
                ),
                "benchmarks": [
                    {
                        "provincia": fila["provincia"],
                        "anio": fila["anio"],
                        "demanda_m3": _num(fila["demanda_m3"]),
                        "precio_promedio_m3": _num(fila["precio_promedio_m3"]),
                        "fuente": fila["fuente"],
                    }
                    for fila in filas
                ],
            }

        raise ValueError(f"Seccion no soportada: {seccion}")

    async def leer_todo(self) -> dict[str, Any]:
        return {seccion: await self.leer_seccion(seccion) for seccion in SECCIONES}

    async def guardar_seccion(
        self, seccion: str, datos: Mapping[str, Any]
    ) -> dict[str, Any]:
        cuerpo = dict(datos or {})

        if seccion == SECCION_FORMULAS:
            recetas = cuerpo.get("recetas")
            if isinstance(recetas, list):
                for receta in recetas:
                    await self.upsert_receta(receta)
            elif cuerpo.get("resistencia"):
                await self.upsert_receta(cuerpo)

        elif seccion == SECCION_WHATSAPP:
            evolution = await self._setting("integraciones.evolution", {}) or {}
            bunny = await self._setting("integraciones.bunny", {}) or {}
            mapa = {
                "evolution_api_url": ("url", evolution),
                "evolution_instance_name": ("instancia", evolution),
                "evolution_api_key": ("api_key", evolution),
                "bunny_storage_zone": ("storage_zone", bunny),
                "bunny_api_key": ("api_key", bunny),
                "bunny_cdn_domain": ("cdn_host", bunny),
            }
            for campo, (destino, contenedor) in mapa.items():
                if campo in cuerpo:
                    contenedor[destino] = _texto(cuerpo.get(campo))
            if "debounce_seconds" in cuerpo:
                numero = _num(cuerpo.get("debounce_seconds"))
                if numero is not None and numero >= 0:
                    await self._guardar_setting(
                        "operacion.debounce_segundos", numero
                    )
            await self._guardar_setting("integraciones.evolution", evolution)
            await self._guardar_setting("integraciones.bunny", bunny)

        elif seccion == SECCION_EMPRESA:
            actual = dict(await self._setting("empresa.bot_publico", {}) or {})
            actual.update(cuerpo)
            await self._guardar_setting("empresa.bot_publico", actual)

        elif seccion == SECCION_FLOTA:
            if isinstance(cuerpo.get("mixers"), list):
                for mixer in cuerpo["mixers"]:
                    await self.upsert_mixer(mixer)
            if "politica_ultimo_viaje" in cuerpo:
                await self._guardar_setting(
                    "operacion.politica_redondeo_viajes",
                    normalizar_politica(str(cuerpo["politica_ultimo_viaje"])).upper(),
                )
            reloj = cuerpo.get("reloj_termico")
            if isinstance(reloj, Mapping):
                maximo = _num(reloj.get("max_fraguado_minutes"))
                if maximo is not None and maximo > 0:
                    await self._guardar_setting(
                        "operacion.reloj_termico_minutos", maximo
                    )
                    temprana = _num(reloj.get("alerta_temprana_min"))
                    critica = _num(reloj.get("alerta_critica_min"))
                    if temprana is not None:
                        await self._guardar_setting(
                            "operacion.alerta_temprana_minutos_antes",
                            max(0.0, maximo - temprana),
                        )
                    if critica is not None:
                        await self._guardar_setting(
                            "operacion.por_vencer_critico_minutos_antes",
                            max(0.0, maximo - critica),
                        )

        elif seccion == SECCION_DIRECTORIO:
            if isinstance(cuerpo.get("staff"), Mapping):
                await self._guardar_setting(
                    "whatsapp.staff", dict(cuerpo["staff"])
                )
            codigos = cuerpo.get("codigos_operador", cuerpo.get("codigos"))
            if isinstance(codigos, Mapping):
                await self._guardar_setting(
                    "whatsapp.codigos_operador", dict(codigos)
                )

        elif seccion == SECCION_BODEGA:
            materiales = cuerpo.get("materiales")
            if isinstance(materiales, list):
                for material in materiales:
                    codigo = _texto(material.get("codigo"))
                    if not codigo:
                        continue
                    await self._pool.execute(
                        """
                        UPDATE materials
                           SET stock_actual = COALESCE($2, stock_actual),
                               stock_minimo = COALESCE($3, stock_minimo),
                               costo_unitario = COALESCE($4, costo_unitario),
                               updated_at = now()
                         WHERE codigo = $1
                        """,
                        codigo,
                        _num(material.get("stock_actual")),
                        _num(material.get("stock_minimo")),
                        _num(material.get("costo_unitario")),
                    )
            if isinstance(cuerpo.get("por_planta"), Mapping):
                await self._guardar_setting(
                    "bodega.umbrales_por_planta", dict(cuerpo["por_planta"])
                )

        elif seccion == SECCION_FINANZAS:
            if "tope_credito_auto" in cuerpo:
                await self._guardar_setting(
                    "finanzas.tope_credito_auto", cuerpo.get("tope_credito_auto")
                )
            if isinstance(cuerpo.get("simulador"), Mapping):
                actual = dict(await self._setting("finanzas.simulador", {}) or {})
                actual.update(cuerpo["simulador"])
                await self._guardar_setting("finanzas.simulador", actual)
            benchmarks = cuerpo.get("benchmarks")
            if isinstance(benchmarks, list):
                for benchmark in benchmarks:
                    provincia = _texto(benchmark.get("provincia"))
                    if not provincia:
                        continue
                    anio = benchmark.get("anio")
                    await self._pool.execute(
                        """
                        DELETE FROM market_benchmarks
                         WHERE provincia = $1
                           AND coalesce(anio, 0) = coalesce($2, 0)
                        """,
                        provincia,
                        anio,
                    )
                    await self._pool.execute(
                        """
                        INSERT INTO market_benchmarks
                            (provincia, anio, demanda_m3, precio_promedio_m3, fuente)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        provincia,
                        anio,
                        _num(benchmark.get("demanda_m3")) or 0,
                        _num(benchmark.get("precio_promedio_m3")),
                        _texto(benchmark.get("fuente")),
                    )

        else:
            raise ValueError(f"Seccion no soportada: {seccion}")

        return await self.leer_seccion(seccion)


# ---------------------------------------------------------------------------
# Memoria (tests)
# ---------------------------------------------------------------------------
_DEFAULTS_RECETAS: list[dict[str, Any]] = [
    {
        "resistencia": "FC-180",
        "cemento_sacos_m3": 6.5,
        "arena_m3_m3": 0.56,
        "ripio_m3_m3": 0.68,
        "agua_litros_m3": 190.0,
        "retardante_litros_m3": 1.0,
        "saco_kg": 50.0,
        "confirmado": True,
        "fuente": "semilla de prueba",
        "precio_m3": 108.0,
        "iva_pct": 15.0,
        "uso_comercial": "Contrapisos, veredas y obras livianas.",
    },
    {
        "resistencia": "FC-210",
        "cemento_sacos_m3": 7.5,
        "arena_m3_m3": 0.52,
        "ripio_m3_m3": 0.68,
        "agua_litros_m3": 185.0,
        "retardante_litros_m3": 1.2,
        "saco_kg": 50.0,
        "confirmado": True,
        "fuente": "semilla de prueba",
        "precio_m3": 118.0,
        "iva_pct": 15.0,
        "uso_comercial": "Losas, vigas y columnas residenciales.",
    },
]

_DEFAULTS_MIXERS: list[dict[str, Any]] = [
    {
        "codigo": "MIXER-01",
        "placa": None,
        "capacidad_m3": 8.0,
        "chofer_asignado": None,
        "activo": True,
    },
    {
        "codigo": "MIXER-02",
        "placa": None,
        "capacidad_m3": 8.0,
        "chofer_asignado": None,
        "activo": True,
    },
    {
        "codigo": "MIXER-03",
        "placa": None,
        "capacidad_m3": 7.0,
        "chofer_asignado": None,
        "activo": True,
    },
]


class MemoryConfigStore:
    """Implementacion en memoria con la misma forma que PostgreSQL."""

    def __init__(
        self,
        *,
        recetas: list[dict[str, Any]] | None = None,
        mixers: list[dict[str, Any]] | None = None,
    ) -> None:
        self.recetas = copy.deepcopy(recetas or _DEFAULTS_RECETAS)
        self.mixers = copy.deepcopy(mixers or _DEFAULTS_MIXERS)
        self.settings: dict[str, Any] = {
            "operacion.politica_redondeo_viajes": "PARCIAL",
            "operacion.reloj_termico_minutos": 150,
            "operacion.alerta_temprana_minutos_antes": 60,
            "operacion.por_vencer_critico_minutos_antes": 30,
            "operacion.debounce_segundos": 14,
            "integraciones.evolution": {
                "url": None,
                "instancia": None,
                "api_key": None,
            },
            "integraciones.bunny": {
                "storage_zone": None,
                "cdn_host": None,
                "api_key": None,
            },
            "empresa.bot_publico": {
                "company_name": "Orminorth Hormigones",
                "ruc": None,
                "main_plant_address": "El Coca, Orellana",
                "coverage_zones": ["Orellana", "Sucumbios"],
                "business_hours": None,
                "mobile_plant_pitch": (
                    "Instalamos planta movil en sitio para proyectos "
                    "desde 1,000 m3"
                ),
                "bank_accounts": [],
                "extra_services": ["Bomba pluma de hormigon"],
            },
            "whatsapp.staff": {},
            "whatsapp.codigos_operador": {
                "#BODEGA": "BODEGA_PLANTA",
                "#CAJA": "CAJA_SECRETARIA",
                "#ADMIN": "SUPERADMIN",
            },
            "bodega.umbrales_por_planta": {"PLANTA-COCA": {}},
            "finanzas.tope_credito_auto": None,
            "finanzas.simulador": {
                "pluma_monto_usd": 100000,
                "combo_china_monto_usd": 240000,
                "tasa_anual_pct": 11.2,
                "plazos_meses": [36, 48],
            },
        }
        self.benchmarks: list[dict[str, Any]] = [
            {
                "provincia": "Orellana",
                "anio": None,
                "demanda_m3": 120000.0,
                "precio_promedio_m3": None,
                "fuente": "prueba",
            },
            {
                "provincia": "Sucumbios",
                "anio": None,
                "demanda_m3": 95000.0,
                "precio_promedio_m3": None,
                "fuente": "prueba",
            },
        ]

    async def listar_recetas(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self.recetas)

    async def upsert_receta(self, datos: Mapping[str, Any]) -> dict[str, Any]:
        clave = _texto(datos.get("resistencia") or datos.get("codigo")) or ""
        actual = next(
            (
                r
                for r in self.recetas
                if str(r.get("resistencia", "")).upper() == clave.upper().replace(" ", "-")
            ),
            None,
        )
        crudo = {**actual, **dict(datos)} if actual else dict(datos)
        receta = _normalizar_receta(crudo)
        self.recetas = _upsert_lista(self.recetas, receta, "resistencia")
        return receta

    async def eliminar_receta(self, resistencia: str) -> bool:
        clave = resistencia.upper().replace(" ", "-")
        antes = len(self.recetas)
        self.recetas = [
            r for r in self.recetas if r["resistencia"].upper() != clave
        ]
        return len(self.recetas) != antes

    async def listar_flota(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self.mixers)

    async def upsert_mixer(self, datos: Mapping[str, Any]) -> dict[str, Any]:
        codigo = _texto(datos.get("codigo") or datos.get("codigo_mixer")) or ""
        actual = next(
            (
                m
                for m in self.mixers
                if str(m.get("codigo", "")).upper() == codigo.upper()
            ),
            None,
        )
        crudo = {**actual, **dict(datos)} if actual else dict(datos)
        mixer = _normalizar_mixer(crudo)
        self.mixers = _upsert_lista(self.mixers, mixer, "codigo")
        return mixer

    async def eliminar_mixer(self, codigo: str) -> bool:
        antes = len(self.mixers)
        self.mixers = [
            m for m in self.mixers if m["codigo"].upper() != codigo.upper()
        ]
        return len(self.mixers) != antes

    async def leer_seccion(self, seccion: str) -> dict[str, Any]:
        if seccion == SECCION_FORMULAS:
            return {"recetas": await self.listar_recetas()}
        if seccion == SECCION_WHATSAPP:
            evolution = self.settings["integraciones.evolution"]
            bunny = self.settings["integraciones.bunny"]
            return {
                "evolution_api_url": evolution.get("url"),
                "evolution_instance_name": evolution.get("instancia"),
                "evolution_api_key": evolution.get("api_key"),
                "debounce_seconds": float(
                    self.settings["operacion.debounce_segundos"]
                ),
                "bunny_storage_zone": bunny.get("storage_zone"),
                "bunny_api_key": bunny.get("api_key"),
                "bunny_cdn_domain": bunny.get("cdn_host"),
            }
        if seccion == SECCION_EMPRESA:
            return copy.deepcopy(self.settings["empresa.bot_publico"])
        if seccion == SECCION_FLOTA:
            maximo = float(self.settings["operacion.reloj_termico_minutos"])
            antes_temprana = float(
                self.settings["operacion.alerta_temprana_minutos_antes"]
            )
            antes_critica = float(
                self.settings["operacion.por_vencer_critico_minutos_antes"]
            )
            return {
                "mixers": await self.listar_flota(),
                "politica_ultimo_viaje": _POLITICA_CORTA.get(
                    normalizar_politica(
                        str(self.settings["operacion.politica_redondeo_viajes"])
                    ),
                    "PARCIAL",
                ),
                "reloj_termico": {
                    "max_fraguado_minutes": int(maximo),
                    "alerta_temprana_min": int(maximo - antes_temprana),
                    "alerta_critica_min": int(maximo - antes_critica),
                },
            }
        if seccion == SECCION_DIRECTORIO:
            return {
                "staff": copy.deepcopy(self.settings["whatsapp.staff"]),
                "codigos_operador": copy.deepcopy(
                    self.settings["whatsapp.codigos_operador"]
                ),
            }
        if seccion == SECCION_BODEGA:
            return {
                "materiales": [
                    {
                        "codigo": "CEMENTO",
                        "nombre": "Cemento",
                        "unidad": "saco",
                        "stock_actual": 3500.0,
                        "stock_minimo": 500.0,
                        "costo_unitario": 8.2,
                    },
                    {
                        "codigo": "ARENA",
                        "nombre": "Arena",
                        "unidad": "m3",
                        "stock_actual": 450.0,
                        "stock_minimo": 80.0,
                        "costo_unitario": 14.0,
                    },
                ],
                "por_planta": copy.deepcopy(
                    self.settings["bodega.umbrales_por_planta"]
                ),
            }
        if seccion == SECCION_FINANZAS:
            return {
                "tope_credito_auto": self.settings["finanzas.tope_credito_auto"],
                "simulador": copy.deepcopy(self.settings["finanzas.simulador"]),
                "benchmarks": copy.deepcopy(self.benchmarks),
            }
        raise ValueError(f"Seccion no soportada: {seccion}")

    async def leer_todo(self) -> dict[str, Any]:
        return {seccion: await self.leer_seccion(seccion) for seccion in SECCIONES}

    async def guardar_seccion(
        self, seccion: str, datos: Mapping[str, Any]
    ) -> dict[str, Any]:
        cuerpo = dict(datos or {})
        if seccion == SECCION_FORMULAS:
            recetas = cuerpo.get("recetas")
            if isinstance(recetas, list):
                for receta in recetas:
                    await self.upsert_receta(receta)
            elif cuerpo.get("resistencia"):
                await self.upsert_receta(cuerpo)
        elif seccion == SECCION_WHATSAPP:
            evolution = self.settings["integraciones.evolution"]
            bunny = self.settings["integraciones.bunny"]
            mapa = {
                "evolution_api_url": ("url", evolution),
                "evolution_instance_name": ("instancia", evolution),
                "evolution_api_key": ("api_key", evolution),
                "bunny_storage_zone": ("storage_zone", bunny),
                "bunny_api_key": ("api_key", bunny),
                "bunny_cdn_domain": ("cdn_host", bunny),
            }
            for campo, (destino, contenedor) in mapa.items():
                if campo in cuerpo:
                    contenedor[destino] = _texto(cuerpo.get(campo))
            if "debounce_seconds" in cuerpo:
                numero = _num(cuerpo.get("debounce_seconds"))
                if numero is not None and numero >= 0:
                    self.settings["operacion.debounce_segundos"] = numero
        elif seccion == SECCION_EMPRESA:
            actual = dict(self.settings["empresa.bot_publico"])
            actual.update(cuerpo)
            self.settings["empresa.bot_publico"] = actual
        elif seccion == SECCION_FLOTA:
            if isinstance(cuerpo.get("mixers"), list):
                for mixer in cuerpo["mixers"]:
                    await self.upsert_mixer(mixer)
            if "politica_ultimo_viaje" in cuerpo:
                self.settings["operacion.politica_redondeo_viajes"] = (
                    normalizar_politica(str(cuerpo["politica_ultimo_viaje"])).upper()
                )
            reloj = cuerpo.get("reloj_termico")
            if isinstance(reloj, Mapping):
                maximo = _num(reloj.get("max_fraguado_minutes"))
                if maximo is not None and maximo > 0:
                    self.settings["operacion.reloj_termico_minutos"] = maximo
                    temprana = _num(reloj.get("alerta_temprana_min"))
                    critica = _num(reloj.get("alerta_critica_min"))
                    if temprana is not None:
                        self.settings[
                            "operacion.alerta_temprana_minutos_antes"
                        ] = max(0.0, maximo - temprana)
                    if critica is not None:
                        self.settings[
                            "operacion.por_vencer_critico_minutos_antes"
                        ] = max(0.0, maximo - critica)
        elif seccion == SECCION_DIRECTORIO:
            if isinstance(cuerpo.get("staff"), Mapping):
                self.settings["whatsapp.staff"] = dict(cuerpo["staff"])
            codigos = cuerpo.get("codigos_operador", cuerpo.get("codigos"))
            if isinstance(codigos, Mapping):
                self.settings["whatsapp.codigos_operador"] = dict(codigos)
        elif seccion == SECCION_BODEGA:
            if isinstance(cuerpo.get("por_planta"), Mapping):
                self.settings["bodega.umbrales_por_planta"] = dict(
                    cuerpo["por_planta"]
                )
        elif seccion == SECCION_FINANZAS:
            if "tope_credito_auto" in cuerpo:
                self.settings["finanzas.tope_credito_auto"] = cuerpo.get(
                    "tope_credito_auto"
                )
            if isinstance(cuerpo.get("simulador"), Mapping):
                actual = dict(self.settings["finanzas.simulador"])
                actual.update(cuerpo["simulador"])
                self.settings["finanzas.simulador"] = actual
            if isinstance(cuerpo.get("benchmarks"), list):
                self.benchmarks = copy.deepcopy(cuerpo["benchmarks"])
        else:
            raise ValueError(f"Seccion no soportada: {seccion}")
        return await self.leer_seccion(seccion)
