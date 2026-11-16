"""El Manual Vivo: documentación funcional, índice y lenguaje visible (v9.3)."""

from __future__ import annotations

from pathlib import Path

from app.cerebro.internas import ESTADOS

RAIZ_SERVICIO = Path(__file__).resolve().parents[1]


def _manual() -> Path:
    for base in (RAIZ_SERVICIO, *RAIZ_SERVICIO.parents):
        candidato = base / "docs" / "HORMINOR_MANUAL_FUNCIONAL.md"
        if candidato.is_file():
            return candidato
    raise FileNotFoundError("HORMINOR_MANUAL_FUNCIONAL.md no encontrado")


def _skill() -> Path:
    for base in (RAIZ_SERVICIO, *RAIZ_SERVICIO.parents):
        candidato = (
            base
            / ".agents"
            / "skills"
            / "orminorth-manual-funcional"
            / "SKILL.md"
        )
        if candidato.is_file():
            return candidato
    raise FileNotFoundError("skill orminorth-manual-funcional no encontrada")


def test_el_manual_tiene_mapa_indice_y_regla_de_mantenimiento() -> None:
    texto = _manual().read_text(encoding="utf-8")

    assert "## 3. Mapa funcional" in texto
    assert "## 8. Nombres visibles recomendados" in texto
    assert "## 9. Preguntas frecuentes" in texto
    assert "## 10. Todavía no existe" in texto
    assert "## 11. Índice" in texto
    assert "## 12. Regla de mantenimiento" in texto


def test_cada_termino_tiene_los_campos_que_pidio_direccion() -> None:
    texto = _manual().read_text(encoding="utf-8")

    for campo in (
        "**Nombre técnico**",
        "**Nombre para el usuario**",
        "**Qué significa**",
        "**Para qué existe**",
        "**Quién lo utiliza**",
        "**Qué lo activa**",
        "**Qué sucede después**",
        "**Qué NO significa**",
        "**Ejemplo**",
        "**Dónde se encuentra**",
        "**Referencia técnica**",
    ):
        assert texto.count(campo) >= 15, campo


def test_el_manual_documenta_todos_los_estados_de_la_tarea() -> None:
    texto = _manual().read_text(encoding="utf-8")

    for estado in ESTADOS:
        assert estado in texto, estado


def test_el_manual_documenta_eventos_y_estados_como_cosas_distintas() -> None:
    texto = _manual().read_text(encoding="utf-8")

    assert "**Estado**" in texto
    assert "**Evento**" in texto
    assert "**Acción**" in texto
    assert "«vista» y «acusada» no son estados" in texto


def test_el_manual_responde_las_preguntas_del_criterio() -> None:
    texto = _manual().read_text(encoding="utf-8")

    preguntas = (
        "¿Qué significa que una tarea esté «acusada»?",
        "¿Cuál es la diferencia entre resolver y registrar?",
        "¿Qué pasa si una tarea se vence?",
        "¿Por qué el Cerebro me pregunta si una cifra es correcta?",
        "¿Qué es el compilador y por qué no dejamos que la IA decida todo?",
        "¿Qué hace Gato y qué hace el Cerebro?",
        "¿Qué significa SANDBOX?",
        "¿Cuál es el recorrido de un audio de Julio hasta que secretaría termina?",
    )
    for pregunta in preguntas:
        assert pregunta in texto, pregunta


def test_el_manual_no_promete_lo_que_no_existe() -> None:
    texto = _manual().read_text(encoding="utf-8")
    pendientes = texto.split("## 10. Todavía no existe", 1)[1].split("## 11.", 1)[0]

    assert "Conversación por WhatsApp" in pendientes
    assert "crear_cliente" in pendientes
    assert "bóveda de audios" in pendientes.lower()


def test_la_skill_apunta_al_manual_y_no_lo_duplica() -> None:
    texto = _skill().read_text(encoding="utf-8")

    assert "docs/HORMINOR_MANUAL_FUNCIONAL.md" in texto
    assert "Una sola fuente" in texto or "única fuente" in texto
    # La skill no redefine estados: no debe tener bloques de definición propios.
    assert "**Qué significa**" not in texto


def test_agents_obliga_a_mantener_el_manual() -> None:
    ruta = RAIZ_SERVICIO / "AGENTS.md"
    texto = ruta.read_text(encoding="utf-8")

    assert "HORMINOR_MANUAL_FUNCIONAL.md" in texto
    assert "No se\n    considera terminada una funcionalidad sin esa explicación" in texto
    assert "orminorth-manual-funcional" in texto


def test_el_panel_usa_lenguaje_para_la_persona() -> None:
    html = (
        RAIZ_SERVICIO / "app" / "web" / "templates" / "panel.html"
    ).read_text(encoding="utf-8")

    assert "Confirmar que recibí la tarea" in html
    assert "Trabajo realizado" in html
    assert "Cerrar con justificación" in html
    assert "Registrar resultado" in html
    assert "Elevar al supervisor" in html
    assert "ETIQUETA_ESTADO_TAREA" in html


def test_el_laboratorio_traduce_los_estados_tecnicos() -> None:
    html = (
        RAIZ_SERVICIO / "app" / "web" / "templates" / "cerebro_lab.html"
    ).read_text(encoding="utf-8")

    assert "Sin confirmar" in html
    assert "Existe una versión corregida" in html
    assert "ETIQUETA_HECHO" in html
    assert "ETIQUETA_BORRADOR" in html


def _continuidad() -> Path:
    for base in (RAIZ_SERVICIO, *RAIZ_SERVICIO.parents):
        candidato = base / "docs" / "CONTINUIDAD_CEREBRO.md"
        if candidato.is_file():
            return candidato
    raise FileNotFoundError("CONTINUIDAD_CEREBRO.md no encontrado")


def test_la_continuidad_registra_la_arquitectura_y_las_prioridades() -> None:
    texto = _continuidad().read_text(encoding="utf-8")

    assert "no será un módulo visible" in texto
    assert "Gato" in texto and "Cerebro" in texto
    assert "flujo externo" in texto.lower()
    assert "se conecta Gato con el Cerebro" in texto
    assert "permisos, herramientas y fuentes" in texto
    assert "## 4. Prioridades para la próxima conversación" in texto
    assert "## 7. Invariantes" in texto


def test_agents_permite_localizar_la_continuidad() -> None:
    texto = (RAIZ_SERVICIO / "AGENTS.md").read_text(encoding="utf-8")

    assert "docs/CONTINUIDAD_CEREBRO.md" in texto
    assert "retomar el proyecto o abrir una conversación nueva" in texto


def test_el_mapa_funcional_marca_la_arquitectura_como_futura() -> None:
    texto = _manual().read_text(encoding="utf-8")

    assert "### 3.4 Cómo se conectará todo (arquitectura futura, **no implementada**)" in texto
    assert "FLUJO INTERNO" in texto
    assert "FLUJO EXTERNO" in texto
    assert "no será un módulo visible" in texto
    pendientes = texto.split("## 10. Todavía no existe", 1)[1]
    assert "Gato usando al Cerebro" in pendientes
    assert "Flujo comercial externo" in pendientes
