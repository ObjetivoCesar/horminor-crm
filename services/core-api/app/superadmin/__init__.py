"""Centro de Configuracion Superadmin.

Paquete con las 7 secciones editables, la composicion del ADN publico del bot
y las dos implementaciones de persistencia. El router HTTP se importa aparte
(``app.superadmin.router``) para que los modulos de negocio puedan usar este
paquete sin arrastrar FastAPI ni crear ciclos de importacion.
"""

from .secciones import (
    SECCIONES,
    SECCION_BODEGA,
    SECCION_DIRECTORIO,
    SECCION_EMPRESA,
    SECCION_FINANZAS,
    SECCION_FLOTA,
    SECCION_FORMULAS,
    SECCION_WHATSAPP,
    SeccionDesconocidaError,
    componer_respuesta_lead,
    normalizar_seccion,
)
from .store import (
    ConfigStore,
    MemoryConfigStore,
    PostgresConfigStore,
)

__all__ = [
    "ConfigStore",
    "MemoryConfigStore",
    "PostgresConfigStore",
    "SECCIONES",
    "SECCION_BODEGA",
    "SECCION_DIRECTORIO",
    "SECCION_EMPRESA",
    "SECCION_FINANZAS",
    "SECCION_FLOTA",
    "SECCION_FORMULAS",
    "SECCION_WHATSAPP",
    "SeccionDesconocidaError",
    "componer_respuesta_lead",
    "normalizar_seccion",
]
