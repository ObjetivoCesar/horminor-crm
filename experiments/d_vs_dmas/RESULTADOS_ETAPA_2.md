# Etapa 2 — evaluación controlada D vs D+ (exploratoria)

> **Fecha:** 2026-11-16 · **Arnés:** `harness-1.1` · **Prompts:** `a1-v1`,
> `a2-v1`, `a3-v1`, `d-v1`, `arb-v1` (**sin cambios**, misma huella que la
> etapa 1) · **Contratos:** `contracts-1.0` · **Conciliación:** `reconcile-1.0`
>
> **Estado de la referencia:** **NO validada por humanos.** Sin referencia
> humana, esta etapa es **exploratoria** y no concluyente. Los números de
> calidad sirven para validar el instrumento y detectar fallos, no para elegir
> arquitectura.

---

## 1. Codificación: causa, alcance y corrección

**El texto se corrompió antes de enviarse**, no en la recepción ni al serializar.

Causa: durante la etapa 1 el arnés se editó con PowerShell
(`Get-Content -Raw` + `Set-Content -Encoding utf8`). PowerShell 5.1 leyó los
archivos UTF-8 sin BOM como ANSI y volvió a escribirlos: los literales quedaron
doblemente codificados (`secretaría` → `secretarÃ­a`). El dictado fijo de
`spike.py` ya estaba corrupto en el código fuente, así que se envió así al
modelo y el JSON lo registró fielmente.

| Punto | Estado |
|---|---|
| Fuente (`spike.py`) | **corrupto** (literal `Ã`) |
| Construcción del payload | correcto (httpx usa UTF-8) |
| Recepción | correcto |
| Serialización de evidencia | correcta (UTF-8) |

**Corrección:** reversión de la doble codificación (cp1252→UTF-8) en
`spike.py` y `arms.py`, sin BOM. `tests_encoding.py` verifica fuente → payload
→ respuesta → archivo con tildes, ñ y `¿`. Resultado: **OK**.

**Versiones:** arnés `harness-1.1`; `prompts.py` conserva exactamente la misma
huella que en la etapa 1
(`d262945245ae6be886cc6a99826dd3de7663b500f1a434cb1528ea9f3a14e6da`), lo que
prueba que **no se modificó ningún prompt**.

El diccionario de datos del corpus no estaba afectado: se lee con
`encoding="utf-8"` y las 3 pruebas de arnés usaron esos textos.

---

## 2. Integridad de la evaluación

- **E01–E03 excluidos por diseño** (`--excluir`). La corrida evaluó **37 casos**.
- **La referencia no entra en ningún mensaje**: los prompts solo reciben fecha,
  lista de clientes y dictado.
- **Salidas originales conservadas** en `experiments/d_vs_dmas/runs/`.
- **Prompts congelados** antes de la corrida y sin cambios después.
- La corrida usó la **guía preliminar de IA** solo como marcador; el evaluador
  la identifica como `referencia_validada: false`.

---

## 3. Referencias para revisión humana

| Archivo | Contenido |
|---|---|
| `docs/revision_humana/FICHAS_REVISION.md` | 40 fichas legibles: dictado, órdenes, descriptivo, condiciones, aclaraciones, prohibidas y firmas |
| `docs/revision_humana/PROCEDIMIENTO_REVISION_CIEGA.md` | revisión ciega, dos revisores, adjudicación y prioridades |
| `docs/revision_humana/referencia_revision.jsonl` | plantilla estructurada para el evaluador |

- **21 de 40** casos están marcados `[PRIORIDAD]` (pagos, comunicaciones
  externas, revocaciones, despachos y permisos).
- **Ninguna ficha está firmada.** Por tanto **no existe referencia humana** y
  los resultados de esta etapa son exploratorios.
- Limitación registrada: no hubo dos revisores independientes; el propio
  constructor del arnés no cuenta como revisor independiente.

---

## 4. Resultados de la corrida (37 casos, referencia NO humana)

| Brazo | Errores | Órdenes bloqueadas | Incompletas | Conflictos | Restricciones | p50 | p95 | Tokens in/out |
|---|---|---|---|---|---|---|---|---|
| V7 | 0 | 0 | 0 | 0 | **0** | 1.626 ms | 2.105 ms | 100.324 / 8.918 |
| D | **5** | — | — | 10 | 21 | 1.734 ms | 2.148 ms | 21.551 / 10.288 |
| D+ | **1** | — | — | 26 | 23 | 1.814 ms | 2.094 ms | 80.489 / 20.216 |
| D+ARB | 1 | — | — | 27 | 20 | 1.825 ms | 2.277 ms | 85.141 / 21.809 |

**Fallos de contrato (catálogo cerrado):**
- **D: 5/37** (E11 `CANCELACION`, E20 `LIMITACION`, E23 `SECUENCIA`,
  E25 `CANTIDAD`, E26 `CORRECCION`). El modelo inventó tipos fuera del catálogo
  y el caso se perdió completo.
- **D+: 1/37** (E23 `ANAfora`, un problema de mayúsculas). Al fallar A3, **todas
  las órdenes quedaron bloqueadas** (fallo cerrado), no perdidas.

Las métricas de omitidas/inventadas **no se interpretan**: la guía preliminar
tiene una frase por caso y no describe responsables, canales ni restricciones.
Se conservan en el JSON para trazabilidad.

---

## 5. Latencia por componente y total

Del spike (5 repeticiones, mismas condiciones):

| Componente | p50 | mínimo | máximo |
|---|---|---|---|
| A1 hechos | 1.892 ms | 1.627 ms | 2.409 ms |
| A2 órdenes | 1.608 ms | 1.155 ms | 1.966 ms |
| A3 restricciones | 1.041 ms | 862 ms | 1.300 ms |
| **3 en paralelo** | **1.892 ms** | 1.627 ms | 2.409 ms |

Por caso (37): p50 1.626–1.825 ms y p95 2.094–2.277 ms según brazo.
**Duración total de la corrida: 4 min 46 s** para 148 casos-brazo (≈1,93 s por
caso-brazo), medida por marca de tiempo del archivo de salida.
El p95 de 5 repeticiones **no** se toma como comportamiento sostenido: hace
falta una corrida de carga dedicada.

---

## 6. Coste estimado

Tarifas DeepSeek Flash usadas: **$0,15 / 1M entrada (cache miss)** y
**$0,60 / 1M salida**, horario **fuera de punta** (la corrida fue a las 16:19
UTC). Se asume **0 % de aciertos de caché** (conservador; la caché no se midió).

| Brazo | USD total (37) | USD/caso | vs D |
|---|---|---|---|
| V7 | $0,02040 | $0,000551 | 2,17× |
| D | $0,00941 | $0,000254 | 1,00× |
| D+ | $0,02420 | $0,000654 | **2,57×** |
| D+ARB | $0,02586 | $0,000699 | 2,75× |

En hora punta las tarifas se duplican. Para 40 dictados al día, el orden de
magnitud es centavos: **el coste no es el factor decisivo; la seguridad sí.**

---

## 7. Casos concretos: dónde gana cada uno

### Gana D

**E07 — `wa_condicion`:** «…no mandes nada hasta obtener el número».
- **D** deja el WhatsApp **BLOQUEADO** y asocia la prohibición correctamente.
- **D+** no logra asociarla (dos conflictos `RESTRICCION_SIN_SUJETO`) y lo deja
  **INCOMPLETA** por falta de teléfono. El bloqueo por prohibición se pierde.

**E14 — `dependencia_pago`:** «…no autorizamos salida de camiones hasta
verificar el dinero».
- **D** bloquea las dos órdenes con la prohibición y la dependencia.
- **D+** abre tres conflictos (ambigua / sin sujeto) y las deja incompletas.

### Gana D+

**E27 — `cita_no_aprobada`:** «anulen todas las órdenes… No hagas ninguna de
esas cosas; que contabilidad revise».
- **D** deja la revisión **LISTA** y la prohibición queda como conflicto sin
  sujeto: la orden podría avanzar.
- **D+** la deja **BLOQUEADA** con la prohibición y la dependencia. Más seguro,
  aunque agrega una dependencia espuria.

**E11 — `revocacion_parcial`:** «cancela la llamada… pero mantén la revisión».
- **D** falla por contrato (`CANCELACION`) y pierde el caso completo.
- **D+** conserva la revisión de combustible y marca la llamada cancelada como
  restricción sin sujeto (mejorable, pero no pierde el encargo válido).

### Errores compartidos

- **Asociación de restricciones frágil en ambos.** D+ falla en E07/E14; D en
  E27. El problema no es el número de lectores, sino **cómo se resuelve el
  referente** («eso», «ese pago», «hasta obtenerlo»).
- **Catálogos cerrados:** los dos sufren cuando el modelo inventa un tipo; D
  pierde el caso, D+ lo bloquea. Falta una normalización auditada de sinónimos.
- **E15 / E39:** ambos terminan sin órdenes y con conflictos; correcto en
  seguridad, pobre en utilidad (no ofrecen una constancia consultable).

---

## 8. Idempotencia (`mensaje_id` / `intent_id`)

`python -m experiments.d_vs_dmas.idempotencia` → **6/6**:

| Prueba | Resultado |
|---|---|
| Reintento técnico (mismo mensaje e intent) | 1 ejecución |
| Mismo mensaje, otro intent | 1 ejecución |
| Texto idéntico, mensaje distinto | 2 ejecuciones (instrucción legítima) |
| `intent_id` reutilizado con otro mensaje | error de inconsistencia |
| 5 duplicados concurrentes | 1 ejecución |
| Reintento tras timeout | 1 ejecución |

No se tocó persistencia ni migraciones del CRM.

---

## 9. Limitaciones

1. **No hay referencia humana.** Los números de calidad no son concluyentes.
2. **Un solo constructor**, sin dos revisores independientes.
3. **Corpus sintético**: 40 dictados, uno por categoría; no refleja la
   distribución real de Julio.
4. **Contratos estrictos** castigan sinónimos del modelo; falta normalización
   auditada.
5. **Tres lectores del mismo modelo** no garantizan independencia estadística.
6. **V7 sin base de datos**: no resuelve cliente/receta, así que no crea
   cotizaciones; la comparación es de interpretación, no de ejecución.
7. **p95 con 5 repeticiones** no es comportamiento sostenido.

---

## 10. Recomendación (provisional, no decisión)

**No elegiría todavía D+.** Tampoco D. La evidencia exploratoria muestra que:

- **D+ no domina a D**: pierde asociación de restricciones en E07/E14 y cuesta
  2,6×.
- **D no domina a D+**: deja avanzar una orden en E27 y pierde 5 casos por
  contrato.
- **El factor decisivo es la asociación semántica de restricciones**, no el
  número de llamadas. D+ ayuda solo cuando esa asociación funciona.

**Condición para decidir:** completar la referencia humana (dos revisores),
pre-registrar dos correcciones —normalización auditada de sinónimos y mejora
del resolvedor de referentes— y repetir la corrida completa. Si D+ no reduce
restricciones perdidas y órdenes omitidas **sin inventar ninguna acción**, la
arquitectura recomendada será **D** (más simple y 2,6× más barata).

**Nada de esto se implementa en el motor.** Gato sigue desconectado y el
Cerebro productivo está intacto.
