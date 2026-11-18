"""Espejo de WhatsApp - resolucion de identidad.

Todo aqui es puro: no toca base de datos, Redis ni red. El espejo solo
importa conversaciones de telefonos autorizados, asi que la primera decision
siempre es **de quien es este JID**.

WhatsApp entrega tres formas para el mismo contacto:

* ``593991234567@s.whatsapp.net`` (PN, el telefono real)
* ``153459886145727@lid`` (LID, un identificador opaco)
* ``key.remoteJidAlt`` (el otro extremo del par, cuando existe)

Regla dura: un LID **no es un telefono**. Si no hay alias conocido ni
``remoteJidAlt`` con forma de telefono, la identidad es ambigua y el mensaje
no se vincula ni se importa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from ..m1_whatsapp.models import formato_whatsapp

# JIDs que nunca son una conversacion de cliente con el negocio.
SUFIJOS_IGNORADOS = ("@g.us", "@broadcast", "@newsletter", "status@broadcast")

SUFIJO_PN = "@s.whatsapp.net"
SUFIJO_LID = "@lid"


class JidInvalido(ValueError):
    """El JID no tiene una forma reconocible."""


def telefono_canonico(valor: object) -> str | None:
    """Devuelve el telefono en la forma de Evolution (digitos + pais).

    ``0991234567``, ``991234567``, ``+593 99 123 4567`` y ``593991234567``
    producen ``593991234567``. Si no hay digitos suficientes para ser un
    telefono, devuelve ``None``: no inventa un pais.
    """
    digitos = re.sub(r"\D", "", str(valor or ""))
    if not digitos:
        return None
    canonico = formato_whatsapp(digitos)
    if len(canonico) < 10 or len(canonico) > 15:
        return None
    return canonico


def es_ecuador_movil(canonico: str | None) -> bool:
    """True si el canonico parece un movil ecuatoriano (593 + 9 + 8)."""
    return bool(
        canonico
        and len(canonico) == 12
        and canonico.startswith("593")
        and canonico[3] == "9"
    )


def jid_de_telefono(canonico: str) -> str:
    """JID de telefono (PN) que usa Evolution para ese numero."""
    return f"{canonico}{SUFIJO_PN}"


@dataclass(frozen=True)
class IdentidadJid:
    """Resultado de resolver un JID contra la lista blanca."""

    jid: str
    telefono: str | None = None
    origen: str = "DESCONOCIDO"  # PN | LID | ALT | IGNORADO | DESCONOCIDO
    jid_telefono: str | None = None
    ambiguo: bool = False
    motivo: str | None = None

    @property
    def ignorado(self) -> bool:
        return self.origen == "IGNORADO"


def _usuario(jid: str) -> str:
    return str(jid or "").split("@", 1)[0].strip()


def _sufijo(jid: str) -> str:
    texto = str(jid or "").strip()
    return "@" + texto.split("@", 1)[1] if "@" in texto else ""


def resolver_jid(
    remote_jid: object,
    remote_jid_alt: object = None,
    *,
    alias: Mapping[str, str] | None = None,
) -> IdentidadJid:
    """Clasifica un JID sin consultar la base; ``alias`` es jid -> telefono.

    * Grupo, canal o estado: ``ignorado`` (no aplica al espejo).
    * ``@s.whatsapp.net``: el usuario es el telefono.
    * ``@lid``: se resuelve por alias conocido o por ``remoteJidAlt``.
    * ``@lid`` sin ninguna de las dos: ambiguo, no se importa.
    """
    jid = str(remote_jid or "").strip()
    if not jid:
        return IdentidadJid(jid="", origen="DESCONOCIDO", ambiguo=True, motivo="JID_VACIO")

    minuscula = jid.lower()
    for sufijo in SUFIJOS_IGNORADOS:
        if minuscula.endswith(sufijo):
            return IdentidadJid(jid=jid, origen="IGNORADO", motivo="GRUPO_O_CANAL")

    alt = str(remote_jid_alt or "").strip() or None
    sufijo = _sufijo(jid)

    if sufijo == SUFIJO_LID:
        conocido = (alias or {}).get(jid)
        if conocido:
            return IdentidadJid(
                jid=jid,
                telefono=conocido,
                origen="LID",
                jid_telefono=jid_de_telefono(conocido),
            )
        if alt and _sufijo(alt) == SUFIJO_PN:
            telefono = telefono_canonico(_usuario(alt))
            if telefono:
                return IdentidadJid(
                    jid=jid,
                    telefono=telefono,
                    origen="ALT",
                    jid_telefono=alt,
                )
        return IdentidadJid(
            jid=jid,
            origen="DESCONOCIDO",
            ambiguo=True,
            motivo="LID_SIN_TELEFONO",
        )

    if sufijo in ("", SUFIJO_PN):
        telefono = telefono_canonico(_usuario(jid))
        if telefono is None:
            return IdentidadJid(
                jid=jid,
                origen="DESCONOCIDO",
                ambiguo=True,
                motivo="NUMERO_INVALIDO",
            )
        return IdentidadJid(
            jid=jid,
            telefono=telefono,
            origen="PN",
            jid_telefono=jid,
        )

    # Un LID que viene como remoteJidAlt (el par invertido) tambien sirve.
    if alt and _sufijo(alt) == SUFIJO_LID:
        conocido = (alias or {}).get(alt)
        if conocido:
            return IdentidadJid(
                jid=jid,
                telefono=conocido,
                origen="ALT",
                jid_telefono=jid_de_telefono(conocido),
            )

    return IdentidadJid(
        jid=jid,
        origen="DESCONOCIDO",
        ambiguo=True,
        motivo="JID_DESCONOCIDO",
    )
