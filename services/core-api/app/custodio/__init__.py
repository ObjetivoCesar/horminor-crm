"""Custodio ejecutable de la base de datos de Horminor.

Paquete con el Gate, el libro mayor, el testigo forense y la higiene del
catalogo contable. La especificacion vive en ``db/migrations/063`` y ``064``
y en los contratos v1.3.0.
"""

from .gate import Actor, Gate, ejecutar_consulta, ejecutar_mutacion, ejecutar_testigo

__all__ = [
    "Actor",
    "Gate",
    "ejecutar_consulta",
    "ejecutar_mutacion",
    "ejecutar_testigo",
]
