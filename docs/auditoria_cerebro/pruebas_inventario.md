# Inventario de la suite del Cerebro — qué cubre y qué no

> Corte: commit `2a5fd93` (620 casos). Medición hecha sobre
> `services/core-api/tests/` sin modificar ninguna prueba.

## Totales

| Medición | Valor |
|---|---|
| Archivos `test_*.py` | 41 |
| Funciones `def test_` | 455 |
| Funciones `async def test_` | 98 |
| Casos recogidos por pytest (con `parametrize`) | 620 |
| Archivos con pruebas del Cerebro (v87–v96) | 10 |
| Pruebas del Cerebro (v87–v96) | 160 |
| Pruebas de voz y alineación (v85–v86) | 37 |

## Por archivo (Cerebro)

| Archivo | Casos | Cómo construye la entrada |
|---|---|---|
| `test_v85_voz_ingesta.py` | 6 | audio simulado, sin LLM |
| `test_v85_voz_normalizador.py` | 21 | texto directo al normalizador |
| `test_v86_voz_alineacion.py` | 10 | tokens y palabras sintéticas |
| `test_v87_cerebro_compilador.py` | 43 | **hechos a mano** → `compilar` |
| `test_v88_groq.py` | 7 | HTTP del proveedor simulado |
| `test_v89_extractor.py` | 11 | `SobreIn` escrito a mano + `construir_hechos` / `interpretar` con LLM simulado |
| `test_v90_cerebro_correcciones.py` | 13 | hechos a mano |
| `test_v91_tareas_internas.py` | 17 | hechos a mano + `compilar` |
| `test_v92_adversarial.py` | 22 | hechos a mano + `compilar` |
| `test_v93_manual_funcional.py` | 13 | documentos (no comportamiento) |
| `test_v94_conservacion.py` | 15 | hechos a mano + `compilar` |
| `test_v95_encargos.py` | 9 | hechos a mano + `compilar` |
| `test_v96_natural.py` | 10 | hechos a mano + `compilar` |

## Cobertura por tipo

| Pregunta | Respuesta |
|---|---|
| ¿Cuántas usan hechos construidos manualmente? | **129** (6 archivos) |
| ¿Cuántas recorren extractor y compilador juntos? | **11**, con un `SobreIn` escrito por una persona y el LLM simulado |
| ¿Cuántas usan una respuesta **real** de un modelo? | **0** |
| ¿Cuántas recorren el flujo HTTP completo del Cerebro? | **0** |
| ¿Cuántas comprueban solo que «hay acciones»? | varias; p. ej. `test_v87` afirma los nombres de acción esperados, pero ninguna afirma que **no** exista la acción indebida |
| ¿Cuántas cubren ausencia de acciones no autorizadas? | 8 apariciones de `SIN_ACCIONES`, concentradas en revocación y dinero |
| ¿Cuántas cubren duplicación entre encargos? | 1 (`test_v95`, misma clave en dos encargos) |
| ¿Cuántas cubren revocación **parcial**? | **0** |
| ¿Cuántas cubren área/destinatario desconocidos? | **0** |
| ¿Cuántas cubren ambigüedad de hora (entrega vs tarea)? | **0** |

## Por qué P1–P7 pasaron inadvertidas

1. Las pruebas del compilador parten de **hechos ya correctos**: validan reglas,
   no la cadena completa.
2. El único archivo que recorre extractor + compilador usa un sobre **ideal**,
   sin la variabilidad de un modelo real.
3. No hay prueba que compare «orden esperada» con «acción propuesta»; se afirma
   la presencia de una acción, no la ausencia de otra.
4. Los casos con frases espontáneas (P1–P7) no forman parte del corpus.
5. La suite mide cantidad de reglas cubiertas, no representatividad del lenguaje
   de Julio.

## Qué pruebas harían falta (propuesta, no implementada)

1. **Corpus real etiquetado:** 30–50 dictados con la orden esperada (tipo, canal,
   responsable, restricciones), no solo con la acción.
2. **Prueba de canal:** área desconocida («chicos de planta», «logística») no
   debe producir WhatsApp.
3. **Prueba de revocación por asunto:** «no lo hagas» sobre un encargo no debe
   borrar los demás.
4. **Prueba de restricción:** «no cobren» bloquea cobranza y no la tarea de
   revisión.
5. **Prueba de hora:** una hora de entrega no se convierte en plazo de tarea.
6. **Prueba de orden ausente:** datos suficientes sin orden no crean cotización.
7. **Prueba de duplicación:** un dictado con una instrucción no genera dos
   tareas.

Ninguna de estas pruebas se agregó: esta tarea es de investigación.
