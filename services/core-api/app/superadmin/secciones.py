"""Centro de Configuracion Superadmin - contratos y textos del bot.

Este paquete concentra dos cosas:

1. Las **7 secciones** editables que el Frontend consume por HTTP.
2. La composicion deterministica de la respuesta publica del bot (Gate #4).

La respuesta del bot se arma con datos leidos en vivo de PostgreSQL. No hay
LLM en la matematica ni en los precios: el Juez solo decide si el mensaje es
una solicitud de cotizacion.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

SECCION_FORMULAS = "formulas_y_precios"
SECCION_WHATSAPP = "whatsapp_evolution_y_cdn"
SECCION_EMPRESA = "empresa_bot_publico"
SECCION_FLOTA = "flota_y_operacion"
SECCION_DIRECTORIO = "directorio_roles_whatsapp"
SECCION_BODEGA = "bodega_y_umbrales"
SECCION_FINANZAS = "finanzas_y_ases_gerenciales"

SECCIONES: tuple[str, ...] = (
    SECCION_FORMULAS,
    SECCION_WHATSAPP,
    SECCION_EMPRESA,
    SECCION_FLOTA,
    SECCION_DIRECTORIO,
    SECCION_BODEGA,
    SECCION_FINANZAS,
)

_ALIAS_SECCIONES = {
    "FORMULAS_Y_PRECIOS": SECCION_FORMULAS,
    "FORMULAS": SECCION_FORMULAS,
    "RECETAS": SECCION_FORMULAS,
    "WHATSAPP_EVOLUTION_Y_CDN": SECCION_WHATSAPP,
    "WHATSAPP": SECCION_WHATSAPP,
    "EMPRESA_BOT_PUBLICO": SECCION_EMPRESA,
    "EMPRESA": SECCION_EMPRESA,
    "BOT_PUBLICO": SECCION_EMPRESA,
    "FLOTA_Y_OPERACION": SECCION_FLOTA,
    "FLOTA": SECCION_FLOTA,
    "DIRECTORIO_ROLES_WHATSAPP": SECCION_DIRECTORIO,
    "DIRECTORIO": SECCION_DIRECTORIO,
    "BODEGA_Y_UMBRALES": SECCION_BODEGA,
    "BODEGA": SECCION_BODEGA,
    "FINANZAS_Y_ASES_GERENCIALES": SECCION_FINANZAS,
    "FINANZAS": SECCION_FINANZAS,
}


class SeccionDesconocidaError(ValueError):
    pass


def normalizar_seccion(nombre: str) -> str:
    """Acepta el nombre exacto o un alias en mayusculas/minusculas."""
    crudo = (nombre or "").strip().lower()
    for seccion in SECCIONES:
        if crudo == seccion:
            return seccion
    alias = _ALIAS_SECCIONES.get(crudo.upper())
    if alias is not None:
        return alias
    raise SeccionDesconocidaError(
        f"Seccion '{nombre}' no existe. Use una de: {', '.join(SECCIONES)}"
    )


# ---------------------------------------------------------------------------
# Respuesta publica del bot (Gate #4)
# ---------------------------------------------------------------------------
def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def _lista_texto(valor: Any) -> list[str]:
    if isinstance(valor, str):
        return [valor.strip()] if valor.strip() else []
    if isinstance(valor, Iterable):
        return [str(item).strip() for item in valor if str(item or "").strip()]
    return []


def _precio(valor: Any) -> str:
    if valor is None or valor == "":
        return "precio a cotizar"
    try:
        return f"${float(valor):,.2f}"
    except (TypeError, ValueError):
        return "precio a cotizar"


def _linea_receta(receta: Mapping[str, Any]) -> str:
    resistencia = _texto(receta.get("resistencia")) or "Resistencia"
    precio = _precio(receta.get("precio_m3"))
    uso = _texto(receta.get("uso_comercial"))
    detalle = f"- {resistencia}: {precio}/m3"
    if uso:
        detalle += f" — {uso}"
    return detalle


def componer_respuesta_lead(
    config: Mapping[str, Any] | None,
    recetas: Iterable[Mapping[str, Any]] | None = None,
) -> str:
    """Arma la respuesta de atencion al publico usando el ADN de Orminorth.

    Todo sale de ``empresa.bot_publico`` y de ``concrete_recipes``. Si un dato
    no existe, la linea se omite: el bot nunca inventa RUC, cuentas ni horario.
    """
    datos = dict(config or {})
    empresa = _texto(datos.get("company_name")) or "Orminorth Hormigones"
    direccion = _texto(datos.get("main_plant_address"))
    zonas = _lista_texto(datos.get("coverage_zones"))
    horario = _texto(datos.get("business_hours"))
    planta_movil = _texto(datos.get("mobile_plant_pitch"))
    servicios = _lista_texto(datos.get("extra_services"))
    cuentas = datos.get("bank_accounts") or []
    ruc = _texto(datos.get("ruc"))

    lineas: list[str] = [
        f"Hola, le saluda {empresa}. Gracias por escribirnos.",
    ]
    if direccion:
        lineas.append(f"Planta principal: {direccion}.")
    if zonas:
        lineas.append(f"Cobertura: {', '.join(zonas)}.")
    if ruc:
        lineas.append(f"RUC: {ruc}.")

    confirmadas = [
        receta
        for receta in (recetas or [])
        if receta.get("confirmado", True) and receta.get("precio_m3") is not None
    ]
    if confirmadas:
        lineas.append("Resistencias disponibles (precio por m3, sin IVA):")
        lineas.extend(_linea_receta(receta) for receta in confirmadas)
    else:
        lineas.append(
            "Tenemos hormigon premezclado en varias resistencias; "
            "un asesor le confirma el precio segun el volumen."
        )

    if planta_movil:
        lineas.append(f"{planta_movil}.")
    if servicios:
        lineas.append(f"Servicios adicionales: {', '.join(servicios)}.")
    if horario:
        lineas.append(f"Horario de atencion: {horario}.")
    if isinstance(cuentas, list) and cuentas:
        partes = []
        for cuenta in cuentas:
            if not isinstance(cuenta, Mapping):
                continue
            banco = _texto(cuenta.get("banco") or cuenta.get("bank"))
            tipo = _texto(cuenta.get("tipo") or cuenta.get("tipo_cuenta"))
            numero = _texto(cuenta.get("numero") or cuenta.get("numero_cuenta"))
            titular = _texto(cuenta.get("titular"))
            detalle = " ".join(p for p in (banco, tipo, numero) if p)
            if titular:
                detalle = f"{detalle} (titular: {titular})" if detalle else titular
            if detalle:
                partes.append(detalle)
        if partes:
            lineas.append("Transferencias: " + "; ".join(partes) + ".")

    lineas.append(
        "Un asesor de secretaria le contactara para confirmar volumen, "
        "direccion de obra y forma de pago."
    )
    return "\n".join(lineas)
