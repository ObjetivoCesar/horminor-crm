"""Compatibilidad: la agenda vive en ``app.agenda`` desde la v6.2.

Se mantiene este modulo para no romper imports historicos de
``app.m3_secretaria.agenda``. El servicio real esta en ``app/agenda/``.
"""

from ..agenda import (  # noqa: F401
    ESTADOS_INACTIVOS,
    PostgresAgendaStore,
    a_hhmm,
    a_minutos,
    conflicto_mixer,
    evaluar_disponibilidad,
    mixers_activos,
    se_solapan,
    validar_ventana,
)

__all__ = [
    "ESTADOS_INACTIVOS",
    "PostgresAgendaStore",
    "a_hhmm",
    "a_minutos",
    "conflicto_mixer",
    "evaluar_disponibilidad",
    "mixers_activos",
    "se_solapan",
    "validar_ventana",
]
