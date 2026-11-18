"""Espejo bidireccional del WhatsApp autorizado dentro del CRM.

La lista blanca vive en ``whatsapp_espejo_numeros`` y se aplica en el
backend: webhook, backfill y sincronizacion. Nada fuera de esa lista se
persiste en ``chat_conversaciones`` ni ``chat_mensajes``.
"""

from .espejo import (
    EspejoNoAutorizado,
    EspejoWhatsApp,
    ResultadoSincronizacion,
)
from .eventos import BusEventos
from .evolution import (
    EvolutionEspejo,
    EvolutionError,
    EvolutionNoConfigurado,
    configuracion_evolution,
)
from .identidad import (
    IdentidadJid,
    es_ecuador_movil,
    jid_de_telefono,
    resolver_jid,
    telefono_canonico,
)
from .mensajes import MensajeEspejo, desde_registro, estado_entrega
from .repositorio import (
    MemoryRepositorioEspejo,
    NumeroEspejo,
    PostgresRepositorioEspejo,
    RepositorioEspejo,
)

__all__ = [
    "EspejoNoAutorizado",
    "EspejoWhatsApp",
    "EvolutionEspejo",
    "EvolutionError",
    "EvolutionNoConfigurado",
    "IdentidadJid",
    "MemoryRepositorioEspejo",
    "MensajeEspejo",
    "NumeroEspejo",
    "PostgresRepositorioEspejo",
    "RepositorioEspejo",
    "ResultadoSincronizacion",
    "configuracion_evolution",
    "desde_registro",
    "es_ecuador_movil",
    "estado_entrega",
    "jid_de_telefono",
    "resolver_jid",
    "telefono_canonico",
]
