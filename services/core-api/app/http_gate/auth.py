"""Autenticacion de servicio para el router HTTP del Custodio v4.4.0.

No es login de usuario final. El servidor resuelve el rol desde un token de
servicio (``X-Actor-Token``) o, en desarrollo, desde ``X-Actor-Role`` cuando
``CUSTODIO_ALLOW_DEV_HEADER=true``. El rol nunca se toma del JSON.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request

from ..custodio.gate import ROLES, Actor
from ..settings import CLAVE_INSEGURA, get_settings

CHANNELS = ("WEB_PANEL", "WHATSAPP", "SYSTEM_CRON", "TEST")
ROLES_PAGOS = ("SUPERADMIN", "CONTADORA", "SECRETARIA", "CAJA_SECRETARIA")

# Tokens oficiales v4.4.0 -> rol. SYSTEM_CRON se conserva para el cron.
_TOKEN_FIELDS = {
    "SUPERADMIN": "custodio_token_superadmin",
    "CONTADORA": "custodio_token_contadora",
    "SECRETARIA": "custodio_token_secretaria",
    "BODEGA": "custodio_token_bodega",
    "CHOFER": "custodio_token_chofer",
    "SYSTEM_CRON": "custodio_token_system_cron",
}


@dataclass(frozen=True)
class ActorContext:
    actor: Actor
    channel: str


def _settings(request: Request):
    """Permite inyectar settings en tests sin tocar el entorno global."""
    return getattr(request.app.state, "settings", None) or get_settings()


def _tokens_configurados(settings) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for rol, campo in _TOKEN_FIELDS.items():
        valor = str(getattr(settings, campo, "") or "").strip()
        if valor:
            tokens[rol] = valor
    return tokens


def _rol_por_token(tokens: dict[str, str], token: str) -> str | None:
    if not token:
        return None
    for rol, configurado in tokens.items():
        if hmac.compare_digest(configurado, token):
            return rol
    return None


def _clave_legacy_configurada(settings) -> bool:
    configurada = str(getattr(settings, "gate_api_key", "") or "").strip()
    return bool(configurada and configurada != CLAVE_INSEGURA)


def _clave_legacy_valida(settings, authorization: str | None, x_gate_key: str | None) -> bool:
    configurada = str(getattr(settings, "gate_api_key", "") or "").strip()
    if not _clave_legacy_configurada(settings):
        return False
    recibida = (x_gate_key or "").strip()
    if not recibida and authorization:
        esquema, _, valor = authorization.partition(" ")
        if esquema.lower() == "bearer":
            recibida = valor.strip()
    return bool(recibida) and hmac.compare_digest(configurada, recibida)


def _resolver_rol(
    settings,
    *,
    x_actor_token: str | None,
    x_actor_role: str | None,
    authorization: str | None,
    x_gate_key: str | None,
) -> str:
    tokens = _tokens_configurados(settings)
    if tokens:
        rol = _rol_por_token(tokens, str(x_actor_token or "").strip())
        if rol is None:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "UNAUTHORIZED_ACTOR",
                    "message": "X-Actor-Token invalido o ausente",
                },
            )
        return rol

    # Sin tokens configurados: solo desarrollo explicito o clave legacy.
    if bool(getattr(settings, "custodio_allow_dev_header", False)):
        rol = str(x_actor_role or "").strip().upper()
        if rol not in ROLES:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "UNAUTHORIZED_ACTOR",
                    "message": "X-Actor-Role invalido o ausente",
                },
            )
        return rol

    if _clave_legacy_valida(settings, authorization, x_gate_key):
        rol = str(x_actor_role or "").strip().upper()
        if rol not in ROLES:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "UNAUTHORIZED_ACTOR",
                    "message": "X-Actor-Role invalido o ausente",
                },
            )
        return rol

    if not _tokens_configurados(settings) and not _clave_legacy_configurada(settings):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "GATE_AUTH_NOT_CONFIGURED",
                "message": (
                    "no hay CUSTODIO_TOKEN_* configurados y "
                    "CUSTODIO_ALLOW_DEV_HEADER=false"
                ),
            },
        )
    raise HTTPException(
        status_code=401,
        detail={"code": "UNAUTHORIZED_ACTOR", "message": "actor no resuelto"},
    )


async def require_gate_actor(
    request: Request,
    x_actor_token: str | None = Header(default=None, alias="X-Actor-Token"),
    x_actor_role: str | None = Header(default=None, alias="X-Actor-Role"),
    x_actor_id: str | None = Header(default=None, alias="X-Actor-Id"),
    x_channel: str | None = Header(default=None, alias="X-Channel"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_gate_key: str | None = Header(default=None, alias="X-Gate-Key"),
) -> ActorContext:
    settings = _settings(request)
    rol = _resolver_rol(
        settings,
        x_actor_token=x_actor_token,
        x_actor_role=x_actor_role,
        authorization=authorization,
        x_gate_key=x_gate_key,
    )
    actor_id = str(x_actor_id or "").strip() or f"{rol}_DEFAULT"
    canal = str(x_channel or "WEB_PANEL").strip().upper()
    if canal not in CHANNELS:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "UNAUTHORIZED_DOMAIN_ACCESS",
                "message": f"canal no permitido: {canal}",
            },
        )
    if (rol == "SYSTEM_CRON") != (canal == "SYSTEM_CRON"):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "UNAUTHORIZED_ACTOR",
                "message": "SYSTEM_CRON solo opera por el canal SYSTEM_CRON",
            },
        )
    return ActorContext(actor=Actor(role=rol, id=actor_id), channel=canal)


async def require_payment_actor(
    ctx: ActorContext = Depends(require_gate_actor),
) -> ActorContext:
    """Pagos: SUPERADMIN, CONTADORA o SECRETARIA (CAJA legacy)."""
    if ctx.actor.role not in ROLES_PAGOS:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "UNAUTHORIZED_DOMAIN_ACCESS",
                "message": "solo SUPERADMIN, CONTADORA o SECRETARIA registran pagos",
            },
        )
    if ctx.channel == "SYSTEM_CRON":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "UNAUTHORIZED_DOMAIN_ACCESS",
                "message": "los pagos no se registran por SYSTEM_CRON",
            },
        )
    return ctx
