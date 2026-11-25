"""Política de permisos y huellas de confirmación para las skills de Gato.

No ejecuta nada. Responde dos preguntas:
  - ¿Este actor puede hacer esto?
  - ¿Esta huella corresponde a lo que se mostró?
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def huella_texto(actor_id: str, accion: str, parametros: Mapping[str, Any]) -> str:
    """Hash determinístico que vincula una confirmación a lo mostrado.

    La misma acción con distintos parámetros produce distinta huella.
    Se incluye el actor para que un "sí" de Julio no ejecute la acción
    de Secretaría si ambas están pendientes al mismo tiempo.
    """
    cuerpo = json.dumps(
        {"actor": actor_id, "accion": accion, "params": dict(parametros)},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(cuerpo.encode()).hexdigest()[:32]


def permisos_envio_cotizacion(actor_rol: str, config: Mapping[str, Any]) -> bool:
    """¿Puede este rol enviar la cotización?

    - SUPERADMIN: siempre puede.
    - SECRETARIA: solo si 'gato.secretaria_envia_cotizacion_aprobada' es true.
    - Cualquier otro rol: nunca.
    """
    if actor_rol == "SUPERADMIN":
        return True
    if actor_rol == "SECRETARIA":
        return bool(config.get("gato.secretaria_envia_cotizacion_aprobada", False))
    return False


def precio_bloqueado(
    precio_estado: str | None,
    sandbox: bool,
    actor_rol: str,
    config: Mapping[str, Any],
) -> tuple[bool, str]:
    """¿El precio provisional bloquea el envío?

    Returns (bloqueado: bool, motivo: str).
    En sandbox nunca bloquea (permitimos pruebas completas).
    En producción, si precio_estado es PROVISIONAL y quien_aprueba es SUPERADMIN,
    solo el SUPERADMIN puede enviar.
    """
    if sandbox:
        return False, ""
    if precio_estado != "PROVISIONAL":
        return False, ""
    quien = str(config.get("cotizaciones.quien_aprueba_precio") or "SUPERADMIN").upper()
    if quien == "SUPERADMIN" and actor_rol != "SUPERADMIN":
        return True, "El precio es provisional. Solo Julio puede enviar esta cotización."
    return False, ""
