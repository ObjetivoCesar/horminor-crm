# Etapa 1 — arnés del experimento D vs D+

> **Fecha:** 2026-11-16 · **Experimento:** `d-vs-dmas-1.0`
> **Prompts congelados:** `a1-v1`, `a2-v1`, `a3-v1`, `d-v1`, `arb-v1`
> **Contratos:** `contracts-1.0` · **Conciliación:** `reconcile-1.0`
> **Huellas:** `FREEZE.json`
>
> **Qué es y qué no es.** Esta etapa construye y valida el instrumento. Los
> números de calidad de 3 casos **no** son resultados del experimento: la
> referencia es preliminar y no humana.

---

## 1. Qué se construyó

| Archivo | Función |
|---|---|
| `contracts.py` | hechos, órdenes, restricciones, conflictos, catálogos cerrados, soporte semántico |
| `prompts.py` | cinco prompts congelados, independientes del corpus |
| `llm.py` | cliente con latencia, tokens, errores y reintento de JSON |
| `reconcile.py` | conciliación determinística por cita, referente y ámbito |
| `arms.py` | brazos V7, D, D+ y D+ARB |
| `reference.py` | carga del corpus y adaptador de la referencia preliminar |
| `evaluate.py` | métricas por caso y por brazo |
| `spike.py` | medición de paralelismo |
| `freeze.py` | congelación con SHA-256 |

Nada de esto importa la base de datos ni escribe en tablas de negocio. El brazo
V7 importa el prompt y el compilador productivos **en modo lectura**.

---

## 2. Evidencia de paralelismo (medición real)

Spike de 5 repeticiones; en cada una, tres lecturas simultáneas y una llamada
sola de control. Modelo `deepseek-chat`, temperatura 0.

| Modo | p50 | p95 | media | mínimo | máximo |
|---|---|---|---|---|---|
| 3 en paralelo | **1.892 ms** | 2.409 ms | 1.930 ms | 1.627 ms | 2.409 ms |
| 1 llamada sola | **1.528 ms** | 2.097 ms | 1.573 ms | 1.235 ms | 2.097 ms |

- **Sobrecoste de paralelizar: ~364 ms en p50 (24 %).** No es 3×.
- **0 errores** en 20 llamadas.
- Tokens: paralelo 10.825 entrada / 2.122 salida (5 × 3 llamadas); sola 3.835 /
  870 (5 llamadas).
- El p95 en paralelo (2,4 s) sigue por debajo del máximo observado del motor
  actual en producción (6,6 s en 49 extracciones).

**Conclusión:** el proveedor actual soporta tres lecturas simultáneas sin
degradación significativa. La latencia no es el obstáculo; el coste en tokens sí
se triplica.

---

## 3. Validación del arnés (3 casos, referencia NO válida)

| Brazo | p50 | tokens entrada | tokens salida | errores |
|---|---|---|---|---|
| V7 | 1.224 ms | 8.112 | 335 | 0 |
| D | 1.589 ms | 1.725 | 548 | 0 |
| D+ | 1.666 ms | 6.459 | 1.148 | 0 |
| D+ARB | 1.673 ms | 6.736 | 1.245 | 0 |

- Los cuatro brazos corren de punta a punta y producen órdenes conciliadas.
- D+ usa **~3,7×** los tokens de entrada de D (tres lectores con prompts
  propios) y tarda ~80 ms más en p50.
- Las métricas de “omitidas/inventadas” de esta corrida **no se interpretan**:
  la guía preliminar reduce frases a tipos y no describe canales, responsables
  ni restricciones.

---

## 4. Reglas incorporadas de la revisión

1. **Asociación semántica de restricciones:** el conciliador resuelve referente
   directo, demostrativo, ordinal y anáfora; si hay más de un candidato o el
   analizador marca `ambiguo`, se abre conflicto y no se elige.
2. **Responsable ≠ canal:** la orden separa `responsable_ejecucion`,
   `destinatario_comunicacion`, `ambito`, `medio` y `ejecutor`. Una llamada
   siempre queda en manos de un humano; el Cerebro no la ejecuta.
3. **A3 caído:** ninguna orden avanza; todas quedan `BLOQUEADA` con motivo
   «restricciones no verificadas». Aplica también a encargos internos.
4. **Idempotencia:** el diseño no deduplica por texto. Distingue `mensaje_id`
   (instrucción nueva) de `intent_id` (reintento técnico); implementarlo en el
   evaluador queda para la etapa 2.
5. **Citas:** se localizan en el texto normalizado y se valida que la cita
   **sostenga el tipo** de orden; una cita que solo comparte palabras se rechaza.
6. **Coste y latencia:** medidos antes de fijar umbrales; no hay límite
   aprobado todavía.
7. **Seguridad estadística:** 3 casos no demuestran nada. El informe separa
   *arnés validado* de *resultado experimental* y de *listo para producción*.

---

## 5. Estado del motor productivo

- Sin cambios en `services/core-api/app/`.
- Sin cambios en prompts operativos, migraciones, tablas ni Gato.
- Los experimentos viven en `experiments/d_vs_dmas/` y no se cargan desde la API.
- La base de negocio no recibió escrituras durante esta etapa.

Verificación: `git status` solo muestra archivos nuevos en `experiments/` y los
documentos; `pytest` no se ve afectado porque no se tocó `app/`.

---

## 6. Lo que falta para comparar de verdad

1. **Referencia humana** de los 40 dictados: tipo, responsable, canal, ámbito,
   restricciones y citas. La guía preliminar no sirve para aprobar nada.
2. **Ejecución completa** de los cuatro brazos sobre los 40 casos.
3. **Análisis de errores** por caso: primer punto de divergencia.
4. **Coste en USD:** configurar precios por millón de tokens y registrar
   `usage`; hoy solo se miden tokens.
5. **Idempotencia y reintentos** en el arnés (etapa 2), con `intent_id`.

Ninguna de estas tareas modifica el motor.
