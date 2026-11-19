"""Pruebas del puente Gato -> Cerebro (2026-11-18).

Solo funciones puras: no tocan HTTP ni base de datos.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]
if str(RAIZ_SERVICIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_SERVICIO))

from app.asistente import cerebro_bridge  # noqa: E402


def test_el_puente_solo_se_activa_con_prefijo_explicito() -> None:
    assert cerebro_bridge.es_dictado("cerebro: revisa el stock")
    assert cerebro_bridge.es_dictado("Cerebro, anota que mañana revisen")
    assert cerebro_bridge.es_dictado("dictado: llamar a Paola")
    assert cerebro_bridge.es_dictado("dicta: comprar cemento")
    assert not cerebro_bridge.es_dictado("como va la cartera de Reyes")
    assert not cerebro_bridge.es_dictado("cerebros fuera del alcance")
    assert not cerebro_bridge.es_dictado("")


def test_quita_el_prefijo_antes_de_entregar_al_cerebro() -> None:
    assert (
        cerebro_bridge.texto_limpio("Cerebro, anota que mañana revisen el stock")
        == "anota que mañana revisen el stock"
    )
    assert cerebro_bridge.texto_limpio("dictado: llamar a Paola") == "llamar a Paola"
    assert cerebro_bridge.texto_limpio("sin prefijo") == "sin prefijo"


def test_resumen_incluye_preguntas_y_borrador() -> None:
    datos = {
        "resumen": "Entendi: una tarea para bodega.",
        "borrador_id": "abc-123",
        "borrador": {
            "preguntas": [
                {"clave": "tarea.cuando", "texto": "para cuando es la tarea"},
            ]
        },
    }
    texto = cerebro_bridge.mensaje_de_resumen(datos)
    assert "Entendi: una tarea para bodega." in texto
    assert "para cuando es la tarea" in texto
    assert "/panel/cerebro" in texto


def test_resumen_sin_borrador_no_inventa_enlace() -> None:
    texto = cerebro_bridge.mensaje_de_resumen({"resumen": "Sin acciones."})
    assert texto == "Sin acciones."
