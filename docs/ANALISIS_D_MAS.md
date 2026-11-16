# Alternativa D+ — análisis paralelo especializado

> **Tipo:** investigación y diseño. **No implementado.**
> **Fecha:** 2026-11-16. **Corte del motor actual:** `2a5fd93` (620 casos).
> **Pregunta:** ¿D+ (tres lectores independientes + conciliación) supera de
> verdad a D (una lectura estructurada de órdenes con validación del backend)?
>
> **Regla de este documento:** no se cambia código, prompt vigente ni
> migraciones. Todo lo que sigue es diseño y plan de prueba.

---

## 1. Resumen y recomendación

**D+ es conceptualmente superior a D para los fallos P1–P7**, pero no por el
hecho de llamar tres veces al modelo: por **separar la lectura de hechos de la
lectura de órdenes y de la lectura de restricciones**, y por **conciliar con
citas** en lugar de confiar en una sola salida.

Mi recomendación:

1. **No aprobar D+ todavía.** Diseñarlo y medirlo contra D con un corpus humano.
2. Tomar **D con contrato de órdenes** como línea base (una llamada, órdenes
   explícitas, validación determinística). Es el competidor honesto.
3. Adoptar D+ **solo si** la comparación demuestra: **0 acciones inventadas**,
   reducción medible de tareas omitidas y restricciones perdidas, y un coste
   aceptable (≤ 3,5× y p95 ≤ 10 s).
4. Si D iguala a D+ en lo esencial, quedarse con D: menos piezas, menos coste,
   menos superficie de fallo.

**Por qué no basta con “tres lecturas”:** tres analistas pueden equivocarse en
lo mismo. La mejora viene de los **contratos** (quién puede afirmar qué), de la
**conciliación por cita** y del **fallo cerrado**, no del paralelismo.

---

## 2. D frente a D+

| Aspecto | D (original) | D+ (propuesta) |
|---|---|---|
| Llamadas al LLM | 1 | 3 en paralelo + conciliación |
| Salida del modelo | órdenes + restricciones juntas | hechos / órdenes / restricciones por separado |
| Separación de asuntos | la propone el mismo lector | la define A2 (órdenes) con citas |
| Restricciones | dependen de que el mismo lector las vea | A3 las busca de forma independiente |
| Conciliación | el backend valida la única salida | compara tres lecturas por cita y ámbito |
| Coste por dictado | 1× | ~3× (o ~4× con conciliador LLM) |
| Latencia | 1 llamada (hoy 1,8–6,6 s) | máximo de 3 en paralelo + conciliación |
| Punto único de error semántico | sí | se reduce, no desaparece |
| Complejidad | media | alta |

---

## 3. Qué se conserva del extractor actual

| Pieza actual | Se conserva | Cambio |
|---|---|---|
| `normalizar_con_mapa` (es-EC) | **Sí**, intacto | ninguno |
| `extraer()` con prompt y claves | **Sí** como base de A1 | se le quita la asignación de encargos |
| `SobreIn` / `HechoIn` | **Sí** | se separa el contrato de hechos del de órdenes |
| `construir_hechos`, `validar_hecho`, cita y checksum | **Sí**, intacto | es la garantía de trazabilidad |
| `_ajustar_incertidumbre` | **Sí** | se alimenta solo de A1 |
| `_degradar_pago_no_declarado` | **Sí** | se mantiene como guarda de dinero |
| `segmentar` / `asignar` por ordinales | **Se retira del camino principal** | A2 define asuntos; ordinales quedan de respaldo |
| `compilar()` | **Se reduce** | solo compila órdenes; deja de inferir órdenes desde hechos |
| `_texto_del_grupo` y la síntesis de `tarea.mensaje` | **Se retiran** | eran la causa de P2/P3 duplicados |
| Correcciones versionadas, encargos, confirmación, idempotencia | **Sí**, intactos | la corrección apunta a la orden |
| Guardas de dinero y rol | **Sí**, intactas | el LLM no las toca |

---

## 4. Especialización y contratos

Los tres analizadores reciben **el mismo dictado normalizado** y **el mismo
contexto autorizado** (clientes conocidos, vocabulario aprendido, fecha, zona).
Ninguno ve la respuesta de los otros. El contexto **nunca** incluye permisos
efectivos ni límites de dinero: eso lo aplica el backend después.

### A1 — Hechos, entidades, cifras, fechas e incertidumbre

Es el extractor actual sin la responsabilidad de agrupar. Devuelve:

```json
{
  "hechos": [
    { "clave": "cotizacion.volumen_m3", "valor": 30, "tipo": "DECIMAL",
      "estado": "TENTATIVO", "cita": "treinta metros", "hablante": "SUPERADMIN" }
  ],
  "faltantes": ["cotizacion.obra_direccion"],
  "ambiguedades": ["..."]
}
```

- **No** asigna `encargo`: eso era duplicar la lectura de A2 y produjo el bug del
  índice 1.
- **Sí** conserva cita, estado y validación.

### A2 — Intenciones, órdenes, responsables y asuntos

Devuelve **órdenes sin valores numéricos**; solo referencias y citas:

```json
{
  "asuntos": [
    { "id": "A", "citas": ["que secretaría revise …", "…falta uno"] }
  ],
  "ordenes": [
    { "asunto": "A", "tipo": "VERIFICAR", "responsable": "SECRETARIA",
      "canal": "INTERNO", "citas": ["que secretaría revise …"],
      "datos_requeridos": ["despachos"], "confianza": 0.8 }
  ]
}
```

- `tipo` ∈ {COTIZAR, ENVIAR_MENSAJE, DELEGAR, VERIFICAR, REGISTRAR, CONSTANCIA,
  CONSULTAR, LLAMAR, COORDINAR}.
- `canal` ∈ {INTERNO, WHATSAPP, LLAMADA, CRM}. **Obligatorio**; sin canal la
  orden no es ejecutable.
- `responsable` es un área/persona **propuesta**; el backend la valida contra los
  roles reales. A2 no puede otorgar permisos.
- **No emite montos, volúmenes, fechas ni teléfonos**: solo `datos_requeridos`.
  Así no puede inventar una cifra.

### A3 — Negaciones, rectificaciones, restricciones, condiciones y dependencias

```json
{
  "restricciones": [
    { "tipo": "PROHIBICION", "alcance": "ASUNTO", "sujeto": "A",
      "citas": ["no quiero que le den un precio todavía"],
      "texto": "No cotizar" },
    { "tipo": "DEPENDENCIA", "alcance": "ORDEN", "sujeto": "B",
      "antes_de": "autorizar despacho",
      "citas": ["hasta que no tengamos confirmado ese depósito"] }
  ],
  "rectificaciones": [ { "reemplaza": "cotización", "por": "recordatorio",
                         "citas": ["la cotización, no la cotización, el recordatorio"] } ]
}
```

- `tipo` ∈ {PROHIBICION, CONDICION, DEPENDENCIA, PLAZO, RECTIFICACION,
  REVOCACION, ACLARACION}.
- `alcance` ∈ {ORDEN, ASUNTO, GLOBAL}. **GLOBAL exige una cita con marca global**
  («no hagas nada», «ninguna de esas cosas», «todo queda suspendido»). Si la
  cita está dentro de un asunto, el alcance no puede ser GLOBAL: se degrada a
  ASUNTO. Esta regla es la que arregla P4.
- **No emite valores**; solo citas y a qué se refieren.

### Conciliador (determinístico)

No es un cuarto lector. Es código:

1. **Asuntos:** cada asunto de A2 es un rango de citas. Los hechos de A1 se
   asignan al asunto cuyo rango contiene su cita (solape de offsets). Un hecho
   sin asunto queda `SIN_ASUNTO` y no se usa para ejecutar.
2. **Órdenes:** se validan contra el contrato y se les adjuntan los hechos
   requeridos del mismo asunto. Si falta un hecho → orden `INCOMPLETA`.
3. **Restricciones:** se adjuntan por solape de cita y por `sujeto`. Si el
   alcance declarado contradice la posición de la cita → **se degrada** y se
   marca `ALCANCE_AJUSTADO` (auditable).
4. **Seguridad:** toda orden con `PROHIBICION` o `DEPENDENCIA` no satisfecha
   nace **BLOQUEADA** (visible, no ejecutable). El bloqueo no borra la orden.

### Árbitro (LLM, opcional)

Solo se invoca si el conciliador deja **conflictos abiertos**. Recibe únicamente
el conflicto y las citas; no el dictado completo. Devuelve una recomendación
**con cita** y una etiqueta de confianza. **No puede crear órdenes nuevas ni
cambiar hechos.** Si su salida no cita, se descarta y se pregunta al humano.

### Auditor adversarial (opcional)

Corre después del conciliador y **solo señala**:

- orden sin cita imperativa;
- restricción sin sujeto;
- hecho usado por una orden que no existe en A1;
- asunto sin orden y con verbo de encargo.

No agrega órdenes, no corrige, no ejecuta. Su salida es una lista de hallazgos
para el humano.

---

## 5. Cómo se relacionan citas y encargos

```
A1: hecho ----------- cita [117–145] ---------------- valor 30
A2: asunto A -------- citas [0–200] ------------------ orden VERIFICAR
A3: restricción ----- cita [201–240] ----------------- prohibición
                         │
        conciliador: solape de rangos + sujeto declarado
                         ↓
Orden A: VERIFICAR · INTERNO · SECRETARIA · hechos [volumen 30] · BLOQUEADA por R1
```

- La cita es el único identificador común. No se compara texto libre.
- Si dos analizadores citan el mismo fragmento con distinto significado → es un
  conflicto, no una votación.
- El encargo (asunto) deja de ser un número que el modelo elige: es un **rango
  de citas** definido por A2. Eso elimina el bug del índice 1.

---

## 6. Conciliación sin votación

Reglas, en orden:

1. **Hecho sin cita válida:** se descarta. No se sustituye por el valor de otro
   analizador.
2. **Orden sin cita imperativa:** se descarta y se registra el descarte. No se
   “arregla”.
3. **Dos órdenes sobre la misma cita con tipos distintos:** conflicto →
   `POR_ACLARAR`; si el árbitro existe, recomienda con cita; decide el humano.
4. **Restricción con alcance incoherente:** se degrada al ámbito de su cita
   (nunca se amplía).
5. **Prohibición vs orden:** la orden queda **BLOQUEADA** (fallo cerrado). No
   gana la mayoría ni la confianza mayor.
6. **Dato en disputa (30 vs 35):** si ambos tienen cita válida → `TENTATIVO` y
   pregunta. Nunca se elige el más repetido.
7. **Rectificación:** reemplaza el objeto citado, no el asunto completo. Si la
   cita de rectificación no contiene el término reemplazado → `POR_ACLARAR`.
8. **Sin regla aplicable:** se pregunta. El conciliador **no inventa** una
   decisión.

**Invariante de oro:** *ninguna orden existe si no hay una cita que la sostenga
y un tipo del catálogo cerrado.* El compilador solo ve órdenes; nunca hechos
sueltos. Eso hace imposible el fallo P3 (cotización sin orden).

---

## 7. Cómo se impide inventar órdenes

| Puerta | Regla |
|---|---|
| Contrato de A2 | `tipo` y `canal` de catálogo cerrado; sin valores numéricos |
| Validación | cita obligatoria y verificable contra el texto; si no, descarte |
| Conciliador | solo adjunta hechos; no crea órdenes |
| Compilador | solo compila órdenes; no lee hechos para decidir acciones |
| Árbitro | no crea; solo recomienda con cita |
| Auditor | no crea; solo señala |
| Humano | confirma; nada se ejecuta antes |

---

## 8. Fallos y tiempos de espera

Cada analizador: timeout propio (20 s), un reintento, y **resultado parcial
marcado**.

| Falla | Efecto | Decisión propuesta |
|---|---|---|
| A1 (hechos) | no hay valores verificables | **Fallo cerrado**: no se proponen órdenes; se pide repetir |
| A2 (órdenes) | no hay intención | se conservan hechos como lectura; **sin acciones**; se avisa |
| A3 (restricciones) | no hay control de negaciones | **Fallo cerrado** si hay dinero o canal externo; si no, se marca `RESTRICCIONES_NO_VERIFICADAS` y se exige confirmación explícita |
| Conciliador | error de código | no se ejecuta nada; se registra |
| Árbitro | timeout | el conflicto queda `POR_ACLARAR`; decide el humano |
| Repetición del mismo dictado | dos borradores (hoy pasa: P7a/P7b) | deduplicar por hash de texto + ventana de 5 min; el segundo enlace al primero |

Principio: **un analizador que falta nunca se sustituye por una suposición.**

---

## 9. Cuándo conviene un árbitro

Solo si el conciliador deja conflictos abiertos:

- dos órdenes con tipos incompatibles sobre la misma cita;
- una restricción sin sujeto claro;
- una orden cuyos hechos están en dos asuntos;
- una rectificación que no identifica qué reemplaza.

No se usa para “mejorar la redacción” ni para elegir entre dos lecturas
plausibles: eso lo decide el humano con la cita delante.

---

## 10. Cobertura esperada de P1–P7

| Caso | ¿D+ lo corrige? | Cómo / por qué no |
|---|---|---|
| P1 canal interno | **Parcial** | A2 debe declarar canal; si no conoce «chicos de planta», sigue sin poder. Necesita taxonomía de áreas o que A2 pueda proponer área y el backend validarla. |
| P1 «no envíes hasta que confirme» | **Sí** | A3 lo extrae como PROHIBICION con alcance de la orden; nace bloqueada. |
| P2 tarea duplicada | **Sí** | desaparece la síntesis; las órdenes vienen de A2 con su asunto. |
| P3 cotización no pedida | **Sí** | sin orden COTIZAR no hay acción; el compilador deja de inferir. |
| P4 revocación total | **Sí** | A3 con alcance por asunto; la regla de “GLOBAL exige cita global” evita el borrado total. |
| P5 «sin cobrar» | **Parcial** | A3 lo captura; pero asignar el área (planta/bodega) sigue dependiendo de la taxonomía. |
| P6 constancia | **Sí** | A2 puede emitir CONSTANCIA; falta decidir el objeto de registro. |
| P7 hora de entrega vs plazo | **Parcial** | A1 debe dejar de post-procesar la hora como `tarea.cuando`; A3 puede expresar PLAZO con alcance, pero el compilador debe dejar de inferir plazos. |

**Lo que D+ no resuelve:** la taxonomía de áreas, el significado de una hora sin
una regla explícita, la calidad del modelo, el coste, y las decisiones de
producto (qué es una constancia). Tampoco sustituye la confirmación humana.

---

## 11. Paralelismo, latencia y coste

**Lo medido hoy** (49 extracciones reales): latencia promedio **3.401 ms**,
máximo **6.600 ms**. Los campos `tokens_entrada`, `tokens_salida` y
`costo_llm_usd` están **en 0**: el coste no se mide.

**Estimación D+ con conciliación determinística:**

| Escenario | Latencia | Coste |
|---|---|---|
| 3 llamadas en paralelo | ~máximo de las tres (2–6 s) + 50 ms | ~3× tokens de entrada + 3× salida |
| + árbitro en conflictos (~10–15 % de casos) | +2–4 s en esos casos | +1 llamada en esos casos |
| Conciliador LLM en todos | 5–9 s | ~4× |

**Viabilidad con el proveedor actual:** sí desde el punto de vista técnico
(`httpx.AsyncClient` + `asyncio.gather` ya se usa para el Centinela). Falta
medir límites de tasa y latencia real en paralelo; eso es el **paso 0** del plan.

**Riesgo de coste:** si el dictado típico son 300–600 palabras, tres lecturas
pueden ser aceptables para un uso de oficina (decenas al día), no para cientos.

---

## 12. Comparación controlada (diseño)

### 12.1 Corpus

| Conjunto | Uso | Regla |
|---|---|---|
| P1–P7 recuperados (8) | **regresión** | ya se usaron para entender fallos: no sirven para medir de forma limpia |
| 30–40 dictados nuevos | **evaluación** | escritos por Julio/secretaría, **no** usados para ajustar prompts hasta cerrar la medición |
| Casos sintéticos de seguridad | adversarial | inyección de órdenes, cifras sin cita, canal incoherente |

Estratificación mínima: multi-asunto (≥8), interno vs externo (≥8), negación y
rectificación (≥6), duda (≥5), condición/dependencia (≥5), dinero (≥4),
constancia (≥2), dictado largo (≥3).

### 12.2 Referencia humana

Para cada dictado, dos personas producen la **orden esperada** (tipo, canal,
responsable, asunto, restricciones, datos requeridos) y las citas. Los
desacuerdos los resuelve Julio. **La referencia no es la salida de ningún
sistema.**

### 12.3 Métricas

| Métrica | Definición |
|---|---|
| Calidad por campo | exactitud de tipo, canal y responsable |
| Tareas omitidas | órdenes de la referencia que el sistema no propone |
| Acciones inventadas | órdenes del sistema que no están en la referencia (debe ser 0) |
| Duplicaciones | órdenes repetidas para el mismo asunto |
| Restricciones perdidas | restricciones de la referencia no adjuntadas |
| Contradicciones | pares orden/restricción incompatibles no detectados |
| Citas inválidas | órdenes cuya cita no sostiene el tipo |
| Dinero mal tratado | cualquier cifra sin cita o abono sin confirmación (debe ser 0) |
| Latencia | p50 y p95 por dictado |
| Coste | tokens y USD por dictado (capturando `usage` del proveedor) |

### 12.4 Brazos de comparación

1. **Motor actual** (una llamada, prompt v7) — control.
2. **D** (una llamada con contrato de órdenes + validación).
3. **D+ sin árbitro** (tres lectores + conciliador determinístico).
4. **D+ con árbitro** (solo conflictos).
5. Ablaciones: A1+A3 y A1+A2 para saber qué lector aporta qué.

### 12.5 Aislamiento

- Rama o *worktree* aparte; **sin migraciones** en la base de negocio.
- El arnés escribe resultados en archivos o en una base de evaluación.
- Flag apagado en el motor productivo; nada de esto toca el panel.
- Semilla y versión del modelo fijadas en el informe; se registra la fecha.

### 12.6 Criterio de decisión (antes de ver los datos)

Adoptar D+ solo si:

- **0 acciones inventadas** en los 40 casos;
- reduce ≥ 50 % las tareas omitidas y las restricciones perdidas frente a D;
- no introduce contradicciones no detectadas;
- p95 ≤ 10 s;
- coste ≤ 3,5× el de D;
- el humano no tiene que corregir más campos que con D.

Si no cumple, se queda D (o el motor actual, si D tampoco mejora).

---

## 13. Plan de prueba aislado (sin tocar el motor)

| Paso | Qué | Salida |
|---|---|---|
| 0 | **Spike de proveedor:** 3 llamadas pequeñas en paralelo con el cliente actual; medir latencia, tasa de error y `usage` | informe de viabilidad |
| 1 | Congelar guion de prompts A1/A2/A3 (sin ajustar con el corpus de evaluación) | 3 prompts versionados |
| 2 | Arnés de evaluación: lee un JSONL de dictados + referencia, llama a los brazos 1–4, guarda salidas y métricas | script + resultados |
| 3 | Anotación humana del corpus (ciega a las salidas del sistema) | referencia |
| 4 | Correr los 5 brazos y calcular métricas | tabla comparativa |
| 5 | Análisis de errores: por caso, primer punto de divergencia | informe |
| 6 | Recomendación final y decisión | go / no-go |

Nada de esto crea tablas ni modifica el motor. Si D+ se aprueba, la migración y
el cambio de contrato se planifican después, con su propia revisión.

---

## 14. Riesgos y límites

- **Tres lectores no garantizan tres opiniones independientes:** el mismo modelo
  con el mismo texto puede repetir el mismo sesgo. La independencia es de
  contrato, no estadística.
- **El coste se triplica** y hoy no se mide: sin instrumentar `usage`, la
  decisión de coste sería a ciegas.
- **La taxonomía de áreas** sigue siendo una decisión de producto.
- **El corpus humano es el recurso escaso:** sin él, la comparación no vale.
- **D+ no arregla la confianza del usuario:** si el resumen no explica el
  bloqueo, el humano confirmará igual.

---

## 15. Anexo — contratos mínimos

```
Hecho       { clave, valor, tipo, estado, cita, hablante }
Asunto      { id, citas[] }
Orden       { asunto, tipo, canal, responsable, citas[], datos_requeridos[],
              restricciones[], confianza }
Restriccion { tipo, alcance, sujeto, antes_de?, citas[], texto? }
Conflicto   { tipo, citas[], lecturas[], estado: POR_ACLARAR }
Hallazgo    { codigo, orden?, cita?, detalle }
```

Catálogos cerrados: `tipo` de orden, `canal`, `tipo` de restricción, `alcance`.
Todo lo que no esté en el catálogo se rechaza, no se “interpreta”.
