"""Corrección en lenguaje natural del borrador del router.

Aplica solo lo indicado, crea una versión nueva, conserva la anterior y deja
traza en el registro de errores. No ejecuta nada.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
from pydantic import BaseModel, Field

from experiments.d_vs_dmas.contracts import plano
from experiments.d_vs_dmas.llm import llamar

from . import errores
from .model import BorradorRouter

PROMPT = """Recibes un borrador de encargos y una corrección de Julio en lenguaje
natural. Indica SOLO los cambios, sin reescribir los demás encargos.

Roles permitidos: JULIO, SECRETARIA, JEFE_PLANTA, POR_DEFINIR.
Campos de encargo permitidos: responsable, titulo, que_hacer, plazo, destinatario,
por_investigar, condiciones, estado (PROPUESTO|CONDICIONADO|POR_DEFINIR).
Cambios globales permitidos: cliente (nombre correcto del cliente),
destinatarios (lista de personas que reciben un recordatorio),
confirmar_resto (true si Julio dice "el resto está bien").

Devuelve SOLO JSON:
{"cambios":[{"encargo":"E1","campo":"responsable","valor":"JEFE_PLANTA"}],
 "cancelar":["E2"],
 "cliente": null,
 "destinatarios": null,
 "confirmar_resto": false,
 "aclaracion":"..."}

Reglas:
1. Si la corrección no identifica el encargo, deja "cambios" vacío y explica.
2. No inventes encargos nuevos.
3. "no era para secretaría, era para el jefe de planta" cambia el responsable.
4. "el segundo" se refiere a E2.
5. "no es Díaz Sur, es DIALSUR" cambia el cliente, no el encargo.
6. "notifícales a los dos" llena "destinatarios" con las dos personas.
7. "por lo demás todo correcto" pone confirmar_resto en true.
"""

_ROLES = {
    "secretaria": "SECRETARIA",
    "jefe de planta": "JEFE_PLANTA",
    "jefe planta": "JEFE_PLANTA",
    "planta": "JEFE_PLANTA",
    "julio": "JULIO",
}

_ORDINALES = {
    "primero": 0,
    "primer": 0,
    "segundo": 1,
    "tercero": 2,
    "tercer": 2,
    "cuarto": 3,
}

_STOP = {
    "secretaria",
    "jefe",
    "planta",
    "julio",
    "para",
    "era",
    "cambia",
    "cambiar",
    "corrige",
    "corregir",
    "encargo",
    "tarea",
    "responsable",
    "asigna",
    "asignar",
    "quiero",
    "que",
}


class CambioIn(BaseModel):
    encargo: str
    campo: str
    valor: Any


class CorreccionIn(BaseModel):
    cambios: list[CambioIn] = Field(default_factory=list)
    cancelar: list[str] = Field(default_factory=list)
    cliente: str | None = None
    destinatarios: list[str] | None = None
    confirmar_resto: bool = False
    aclaracion: str | None = None


def _rol(texto: str) -> str | None:
    t = plano(texto)
    for alias, rol in _ROLES.items():
        if plano(alias) in t:
            return rol
    return None


def _objetivo_por_ordinal(frase: str, borrador: BorradorRouter) -> str | None:
    t = plano(frase)
    for palabra, indice in _ORDINALES.items():
        if re.search(rf"\b{palabra}\b", t) and indice < len(borrador.encargos):
            return borrador.encargos[indice].id
    return None


def _objetivo_por_titulo(frase: str, borrador: BorradorRouter) -> str | None:
    palabras = [p for p in plano(frase).split() if len(p) > 3 and p not in _STOP]
    candidatos = []
    for encargo in borrador.encargos:
        base = plano(encargo.titulo + " " + encargo.que_hacer)
        if any(p in base for p in palabras):
            candidatos.append(encargo.id)
    return candidatos[0] if len(candidatos) == 1 else None


def _contactos(borrador: BorradorRouter) -> list[str]:
    datos = borrador.datos_contexto.get("contactos") or []
    return [str(c["nombre"]) for c in datos if isinstance(c, dict) and c.get("nombre")]


def _reemplazar(texto: str, viejo: str, nuevo: str) -> str:
    if not texto or not viejo:
        return texto
    patron = re.compile(re.escape(viejo), re.IGNORECASE)
    return patron.sub(nuevo, texto)


def _aplicar(
    borrador: BorradorRouter,
    *,
    cambios: list[CambioIn],
    cancelar: list[str],
    explicacion: str,
    cliente: str | None = None,
    destinatarios: list[str] | None = None,
    confirmar_resto: bool = False,
) -> tuple[BorradorRouter | None, list[str], list[dict[str, Any]]]:
    ids = {e.id for e in borrador.encargos}
    if any(c.encargo not in ids for c in cambios) or any(c not in ids for c in cancelar):
        return None, ["La corrección apunta a un encargo que no existe."], []

    nuevo = borrador.cambio([explicacion], padre=borrador.version)
    registrados: list[dict[str, Any]] = []

    if cliente:
        anterior = nuevo.datos_contexto.get("cliente.nombre")
        nuevo.datos_contexto["cliente.nombre"] = cliente
        if anterior and plano(str(anterior)) != plano(cliente):
            for encargo in nuevo.encargos:
                encargo.titulo = _reemplazar(encargo.titulo, str(anterior), cliente)
                encargo.que_hacer = _reemplazar(encargo.que_hacer, str(anterior), cliente)
                if encargo.destinatario:
                    encargo.destinatario = _reemplazar(
                        encargo.destinatario, str(anterior), cliente
                    )
        registrados.append(
            {"campo": "cliente.nombre", "antes": anterior, "despues": cliente}
        )

    if destinatarios:
        objetivo = [
            e
            for e in nuevo.encargos
            if "recordatorio" in plano(e.titulo + " " + e.que_hacer)
            or "mensaje" in plano(e.titulo + " " + e.que_hacer)
        ]
        for encargo in objetivo:
            anterior = encargo.destinatario
            encargo.destinatario = " y ".join(destinatarios)
            registrados.append(
                {
                    "campo": f"{encargo.id}.destinatario",
                    "antes": anterior,
                    "despues": encargo.destinatario,
                }
            )
        nuevo.preguntas = [
            p for p in nuevo.preguntas if "recordatorio va para" not in plano(p)
        ]

    for cambio in cambios:
        encargo = next(e for e in nuevo.encargos if e.id == cambio.encargo)
        if cambio.campo == "responsable":
            valor = _rol(str(cambio.valor)) or str(cambio.valor).upper()
            if valor not in ("JULIO", "SECRETARIA", "JEFE_PLANTA", "POR_DEFINIR"):
                return None, [f"Rol inválido: {cambio.valor}"], []
            anterior = encargo.responsable
            encargo.responsable = valor  # type: ignore[assignment]
            encargo.responsable_sugerido = False
            if valor != "POR_DEFINIR" and encargo.estado == "POR_DEFINIR":
                encargo.estado = "PROPUESTO"
            registrados.append(
                {
                    "campo": f"{encargo.id}.responsable",
                    "antes": anterior,
                    "despues": valor,
                }
            )
        elif cambio.campo in ("titulo", "que_hacer", "plazo", "destinatario"):
            anterior = getattr(encargo, cambio.campo)
            setattr(encargo, cambio.campo, cambio.valor)
            registrados.append(
                {
                    "campo": f"{encargo.id}.{cambio.campo}",
                    "antes": anterior,
                    "despues": cambio.valor,
                }
            )
        elif cambio.campo == "por_investigar":
            if isinstance(cambio.valor, list):
                anterior = list(encargo.por_investigar)
                encargo.por_investigar = [str(x) for x in cambio.valor]
                registrados.append(
                    {
                        "campo": f"{encargo.id}.por_investigar",
                        "antes": anterior,
                        "despues": encargo.por_investigar,
                    }
                )
        elif cambio.campo == "condiciones":
            if isinstance(cambio.valor, list):
                anterior = list(encargo.condiciones)
                encargo.condiciones = [str(x) for x in cambio.valor]
                registrados.append(
                    {
                        "campo": f"{encargo.id}.condiciones",
                        "antes": anterior,
                        "despues": encargo.condiciones,
                    }
                )
        elif cambio.campo == "estado":
            if cambio.valor in ("PROPUESTO", "CONDICIONADO", "POR_DEFINIR"):
                anterior = encargo.estado
                encargo.estado = cambio.valor
                registrados.append(
                    {
                        "campo": f"{encargo.id}.estado",
                        "antes": anterior,
                        "despues": cambio.valor,
                    }
                )
        else:
            return None, [f"Campo no permitido: {cambio.campo}"], []

    if cancelar:
        for identificador in cancelar:
            registrados.append({"campo": f"{identificador}.estado", "antes": "PROPUESTO", "despues": "CANCELADO"})
        nuevo.encargos = [e for e in nuevo.encargos if e.id not in cancelar]

    if confirmar_resto:
        nuevo.notas.append("Julio aprobó el resto del borrador")
        registrados.append(
            {"campo": "confirmacion", "antes": None, "despues": "RESTO_APROBADO"}
        )

    nuevo.notas.append(
        "Corrección aplicada a "
        + ", ".join(sorted({c.encargo for c in cambios} | set(cancelar)))
    )
    from .router import resumen_conversacional

    nuevo.resumen = resumen_conversacional(nuevo)
    return nuevo, [], registrados


def _correccion_directa(
    borrador: BorradorRouter, frase: str
) -> tuple[BorradorRouter | None, list[str], dict[str, Any]] | None:
    """Casos claros sin LLM: nombre del cliente, «a los dos» y «el resto bien»."""
    cliente = None
    coincidencia = re.search(
        r"no es ([^,\.]+?)\s+es\s+([^,\.]+)", frase, re.IGNORECASE
    )
    if coincidencia:
        cliente = coincidencia.group(2).strip()

    destinatarios = None
    if re.search(r"a los dos|a ambos|notificales a los dos", plano(frase)):
        contactos = _contactos(borrador)
        if len(contactos) >= 2:
            destinatarios = contactos[:2]

    confirmar_resto = bool(
        re.search(r"por lo demas|todo correcto|el resto esta bien", plano(frase))
    )

    if not cliente and not destinatarios and not confirmar_resto:
        return None

    nuevo, errores_aplicados, registrados = _aplicar(
        borrador,
        cambios=[],
        cancelar=[],
        explicacion="Corrección directa de Julio",
        cliente=cliente,
        destinatarios=destinatarios,
        confirmar_resto=confirmar_resto,
    )
    if nuevo is None:
        return None, errores_aplicados, {"via": "deterministica"}
    return (
        nuevo,
        [],
        {
            "via": "deterministica",
            "cambios": registrados,
            "destinatarios": destinatarios,
        },
    )


async def corregir(
    cliente_http: httpx.AsyncClient, borrador: BorradorRouter, frase: str
) -> tuple[BorradorRouter | None, list[str], dict[str, Any]]:
    """Devuelve (borrador nuevo, errores, meta). No ejecuta nada."""
    meta: dict[str, Any] = {"via": "llm"}

    directa = _correccion_directa(borrador, frase)
    if directa is not None:
        nuevo, errores_aplicados, meta = directa
        if nuevo is not None:
            entrada = errores.registrar(
                mensaje=frase,
                cambios=meta.get("cambios") or [],
                version_antes=borrador.version,
                version_despues=nuevo.version,
                contexto={
                    "cliente": nuevo.datos_contexto.get("cliente.nombre"),
                    "carriles": len(nuevo.encargos),
                },
            )
            meta["registro"] = entrada["id"]
        return nuevo, errores_aplicados, meta

    # Camino determinístico antiguo: "no era para X, era para Y"
    if re.search(r"\bno era para\b|\bno es para\b|\bno,? para\b", plano(frase)):
        destino = None
        posicion = -1
        t = plano(frase)
        for alias, rol in _ROLES.items():
            for coincidencia in re.finditer(
                rf"\bera para (el |la )?{re.escape(plano(alias))}", t
            ):
                if coincidencia.start() > posicion:
                    posicion = coincidencia.start()
                    destino = rol
        if destino:
            objetivo = (
                _objetivo_por_ordinal(frase, borrador)
                or _objetivo_por_titulo(frase, borrador)
                or (borrador.encargos[0].id if len(borrador.encargos) == 1 else None)
            )
            if objetivo is None:
                return None, ["¿A cuál de los encargos le cambio el responsable?"], meta
            nuevo, errores_aplicados, registrados = _aplicar(
                borrador,
                cambios=[
                    CambioIn(encargo=objetivo, campo="responsable", valor=destino)
                ],
                cancelar=[],
                explicacion=f"Responsable corregido a {destino} en {objetivo}",
            )
            if nuevo is not None:
                entrada = errores.registrar(
                    mensaje=frase,
                    cambios=registrados,
                    version_antes=borrador.version,
                    version_despues=nuevo.version,
                )
                meta = {
                    "via": "deterministica_rol",
                    "cambios": registrados,
                    "registro": entrada["id"],
                }
            return nuevo, errores_aplicados, meta

    # Camino LLM
    r = await llamar(
        cliente_http,
        system=PROMPT,
        user=json.dumps(
            {
                "borrador": json.loads(borrador.model_dump_json()),
                "correccion": frase,
            },
            ensure_ascii=False,
        ),
        max_tokens=1200,
    )
    meta["llamada"] = {
        "ok": r.get("ok"),
        "latency_ms": r.get("latency_ms"),
        "usage": r.get("usage") or {},
        "error": r.get("error"),
    }
    if not r.get("ok"):
        return None, [f"No pude interpretar la corrección: {r.get('error')}"], meta

    try:
        correccion = CorreccionIn.model_validate(r["data"])
    except Exception as exc:
        return None, [f"La corrección no cumple el contrato: {exc}"], meta

    if (
        not correccion.cambios
        and not correccion.cancelar
        and not correccion.cliente
        and not correccion.destinatarios
        and not correccion.confirmar_resto
    ):
        return None, [correccion.aclaracion or "No entendí qué corregir."], meta

    nuevo, errores_aplicados, registrados = _aplicar(
        borrador,
        cambios=correccion.cambios,
        cancelar=correccion.cancelar,
        explicacion=correccion.aclaracion or "Corrección de Julio",
        cliente=correccion.cliente,
        destinatarios=correccion.destinatarios,
        confirmar_resto=correccion.confirmar_resto,
    )
    if nuevo is not None:
        entrada = errores.registrar(
            mensaje=frase,
            cambios=registrados,
            version_antes=borrador.version,
            version_despues=nuevo.version,
            contexto={"via": "llm"},
        )
        meta.update({"cambios": registrados, "registro": entrada["id"]})
    return nuevo, errores_aplicados, meta
