"""Modulo 1 - Central de Comunicaciones (WhatsApp + debounce + Jeb + Bunny).

Caja negra del PDR: lee estado del Modulo 0 y actualiza el contrato JSON de
``mixer_dispatches.tracking_payload``. No conoce pantallas web ni el motor
matematico.

Piezas:

- :mod:`models`     contratos puros (roles, mensajes, referencias).
- :mod:`debounce`   ventana de agrupacion en Redis (o memoria en tests).
- :mod:`identity`   telefono registrado + fallback por codigo de operador.
- :mod:`judges`     Juez Binario: Gemini Flash con fallback deterministico.
- :mod:`bunny`      subida de evidencias a Bunny.net.
- :mod:`pipeline`   las 4 compuertas del PDR.
- :mod:`worker`     loop de fondo que vacia la ventana.
- :mod:`router`     webhook de Evolution y endpoints de operacion.
"""

from __future__ import annotations

from .bunny import (
    BunnyHttpStorageClient,
    BunnyStorageClient,
    MemoryBunnyStorageClient,
    NullBunnyStorageClient,
    construir_bunny,
)
from .debounce import (
    DebounceAccumulator,
    MemoryBufferStore,
    RedisBufferStore,
)
from .identity import Identidad, IdentityResolver, RegistroIdentidad
from .judges import (
    BooleanJudgeProvider,
    DeterministicRuleMockJudge,
    GeminiFlashBooleanJudge,
    Veredicto,
    construir_juez,
)
from .models import (
    IncomingMessage,
    MediaAttachment,
    MessageBatch,
    ReferenciaViaje,
    Rol,
    extraer_referencia,
    formato_whatsapp,
    normalizar_telefono,
)
from .pipeline import ResultadoLote, WhatsAppPipeline
from .repositorio import MemoriaRepositorio, PostgresRepositorio, ViajeObjetivo
from .router import router
from .runtime import WhatsAppRuntime, construir_runtime
from .worker import DebounceWorker

__all__ = [
    "BooleanJudgeProvider",
    "BunnyHttpStorageClient",
    "BunnyStorageClient",
    "DebounceAccumulator",
    "DebounceWorker",
    "DeterministicRuleMockJudge",
    "GeminiFlashBooleanJudge",
    "Identidad",
    "IdentityResolver",
    "IncomingMessage",
    "MediaAttachment",
    "MemoriaRepositorio",
    "MemoryBufferStore",
    "MessageBatch",
    "NullBunnyStorageClient",
    "PostgresRepositorio",
    "RedisBufferStore",
    "ReferenciaViaje",
    "RegistroIdentidad",
    "ResultadoLote",
    "Rol",
    "Veredicto",
    "ViajeObjetivo",
    "WhatsAppPipeline",
    "WhatsAppRuntime",
    "construir_bunny",
    "construir_juez",
    "construir_runtime",
    "extraer_referencia",
    "formato_whatsapp",
    "normalizar_telefono",
    "router",
]
