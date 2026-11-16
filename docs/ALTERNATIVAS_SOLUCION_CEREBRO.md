# Alternativas de solución — arquitectura del Cerebro

> **Qué es esto.** Comparación técnica de estrategias para corregir las causas
> comunes de P1–P7. **No es una decisión tomada ni una implementación.**
> **Fecha:** 2026-11-16. **Corte:** `2a5fd93`.
>
> Se evalúan cuatro caminos. A, B y C fueron solicitados; D surge del
> diagnóstico y combina lo mejor de B y C sin la duplicación de autoridad.

---

## 0. Criterio de comparación

Las tres preguntas que debe resolver cualquier alternativa:

1. **Separar hechos de intención:** que describir no sea ordenar.
2. **Separar destinatario de responsable:** a quién se le habla ≠ quién ejecuta.
3. **Representar restricciones y dependencias:** «no cobren», «antes de pagar»,
   «hasta que confirme» deben afectar a acciones concretas, no a todo el dictado.

Y no puede romper: trazabilidad con cita, correcciones versionadas, confirmación
humana, permisos por rol, idempotencia, dinero con doble confirmación, tareas con
seguimiento y aislamiento interno/externo.

---

## Alternativa A — Reforzar la arquitectura actual

**Qué cambia.** Sin estructuras nuevas: se amplían listas y guardas existentes.
- `ALIAS_ROL` y `MARCAS_ENCARGO` incluyen planta, logística, «que me avisen».
- `detectar_intencion_tarea` deja de asumir ENVIAR: si no hay canal explícito,
  DELEGAR.
- `_texto_del_grupo` deja de devolver el dictado completo para el encargo 1.
- `dictado_revocado` deja de cortar todo: se aplica por encargo.
- `_condiciones` reconoce «no cobrar», «no autorizar», «hasta que».
- `_completar_cuando_de_tarea` no toma la hora de entrega como plazo de tarea.

**Qué se conserva.** Todo: tablas, contratos, API, pruebas, correcciones,
idempotencia, confirmación.

**Problemas que resuelve.** Los siete casos concretos, con poco riesgo y sin
migración.

**Problemas que no resuelve.** La causa raíz: sigue sin existir una
representación de *orden*, *restricción* y *dependencia*. La próxima frase nueva
volverá a caer en una lista que no la contiene. La intención seguirá derivándose
de hechos en algunos caminos (cotización).

**Riesgos nuevos.** Ninguno estructural; el riesgo es la falsa sensación de
cierre y la deuda creciente de listas.

**Complejidad.** Baja (~1–2 días). **Aprendizaje de Julio:** intacto.
**WhatsApp:** no cambia nada; hereda los mismos límites.

**Pruebas para demostrarlo.** Suite adversarial con las 7 frases reales y
variantes: debe fallar primero (hoy falla) y pasar después. Además: «una
instrucción con dos áreas», «un área desconocida», «no cobren» y «revoco solo
lo segundo».

**Veredicto.** Necesaria como contención, **insuficiente como solución**.

---

## Alternativa B — Representación intermedia explícita (IR) antes de compilar

**Qué cambia.** Entre hechos y acciones se agrega un artefacto **Orden**:

```
Hecho (dato citado)  →  Orden (intención + responsable + canal + restricciones + dependencias)  →  Acción
```

Cada `Orden` tiene: `tipo` (COTIZAR, ENVIAR_MENSAJE, DELEGAR, CONSULTAR, REGISTRAR,
CONSTANCIA), `responsable` (rol/persona), `canal` (INTERNO, WHATSAPP, LLAMADA,
CRM), `objeto` (cliente, volumen…), `restricciones[]`, `depende_de[]`,
`autorizacion` (rol requerido), y `evidencia` (citas).

El compilador **solo** convierte órdenes en acciones; nunca infiere una orden de
la presencia de datos. Una orden con `tipo` vacío no produce acción: produce
pregunta o queda pendiente para secretaría.

**Qué se conserva.** Hechos citados, correcciones versionadas, encargos,
compilador como capa determinística, confirmación, idempotencia, tareas.

**Problemas que resuelve.** Los tres criterios de §0 de raíz. P3 deja de crear
cotización sin orden; P4 puede revocar una orden y no el dictado; P1 y P7
distinguen canal; P5 expresa «no cobrar» como restricción de la orden.

**Problemas que no resuelve.** Quién produce las órdenes: si las produce el LLM,
vuelve el problema de fiabilidad (pero ahora *visible y validable*). Si las
produce el código a partir de hechos, se reconstruye el problema actual con otro
nombre. Además, sin una política de autorización explícita, una orden mal
tipada sigue siendo peligrosa.

**Riesgos nuevos.** Más piezas y un contrato nuevo que versionar; riesgo de que
la orden duplique el hecho y se desincronice; la UI debe mostrar órdenes, no
solo acciones.

**Complejidad.** Media-alta (~1–2 semanas + migración). **Aprendizaje:** el
vocabulario aprendido sigue igual; las correcciones ahora pueden apuntar a la
orden (mejor). **WhatsApp:** muy favorable: la orden es el «asunto» que un hilo
puede corregir o cancelar.

**Pruebas.** Un corpus de 20–30 dictados reales con la orden esperada; pruebas
de que una orden sin `tipo` no genera acción; de que una restricción impide la
acción relacionada y no las demás.

---

## Alternativa C — Revisar el reparto LLM / backend

**Qué cambia.** El LLM deja de proponer hechos sueltos y devuelve **una lectura
semántica estructurada**: órdenes, responsables, canales, restricciones,
dependencias y dudas, con citas. El backend **no reinterpreta el lenguaje**:
valida estructura, permisos, dinero y ejecuta.

**Qué se conserva.** Todo lo determinístico pasa a ser *verificación*: roles,
precios, doble confirmación, idempotencia, auditoría. La cita sigue siendo
obligatoria.

**Problemas que resuelve.** La ambigüedad «hechos vs intención» desaparece del
código: la intención es un dato declarado y auditable. El código deja de tener
listas de alias como fuente de verdad.

**Problemas que no resuelve.** La variabilidad del modelo: una orden mal
clasificada ahora es un dato estructurado equivocado. Exige **guardas de
consistencia** (¿la orden tiene cita?, ¿el responsable existe?, ¿el canal es
coherente con el destinatario?). Sin ellas, es peor que hoy.

**Riesgos nuevos.** Dependencia del proveedor y de su versión; coste por token;
regresiones silenciosas al cambiar de modelo; necesidad de *evaluación continua*
con corpus real. Y el riesgo político: «el LLM decide» si no hay validación
fuerte.

**Complejidad.** Media (~1 semana de contrato + evaluación). **Aprendizaje:** el
vocabulario y las correcciones se vuelven ejemplos few-shot; mejora. **WhatsApp:**
favorable, porque el mensaje ya llega estructurado.

**Pruebas.** Evaluación offline con corpus etiquetado (orden esperada por
dictado); tasa de acierto por campo; pruebas de que el backend rechaza órdenes
sin cita, con responsable inválido o canal incoherente.

---

## Alternativa D — Órdenes explícitas + autoridad separada (B + C acotado)

**Qué cambia.** Se adopta la IR de B, pero **la produce el LLM como propuesta** y
el backend la **valida y autoriza** con reglas determinísticas. Tres capas con
responsabilidades nítidas:

1. **Comprensión (LLM):** texto → órdenes propuestas con citas y dudas.
2. **Validación (código):** estructura, coherencia, permisos, dinero,
   restricciones y dependencias. Puede **degradar** una orden (pedir
   aclaración), nunca inventarla.
3. **Ejecución (módulos):** las mismas herramientas actuales, con idempotencia.

La regla clave: **una orden sin evidencia suficiente, sin responsable válido o
con canal incoherente no se ejecuta; se pregunta o queda pendiente.**

**Qué se conserva.** Todo lo de B, y además la autoridad final sigue en código:
el LLM propone, el backend dispone.

**Problemas que resuelve.** Los tres criterios, con la ventaja de que el
conocimiento semántico (paráfrasis, áreas implícitas, «me avisen») vive en el
modelo y no en listas. Lo que hoy son bugs de listas pasa a ser un dato
validable.

**Problemas que no resuelve.** Sigue haciendo falta un corpus de evaluación y
un contrato versionado; el coste de tokens sube; la calidad depende del modelo.

**Riesgos nuevos.** El modelo podría «inventar» una orden: se mitiga exigiendo
cita y coherencia y con la confirmación humana. Complejidad de migración de
borradores existentes (los actuales no tienen órdenes).

**Complejidad.** Alta (~2–3 semanas con migración y evaluación). **Aprendizaje:**
mejor: las correcciones de Julio alimentan ejemplos de órdenes. **WhatsApp:**
el mejor encaje: la orden es el asunto que sobrevive entre mensajes.

**Pruebas.** Corpus real + adversarial; inyección de órdenes sin cita;
coherencia canal/destinatario; permisos por rol; doble confirmación de dinero;
idempotencia; y una prueba de que **una orden inválida no produce ninguna
acción**.

---

## Comparación

| Dimensión | A | B | C | D |
|---|---|---|---|---|
| Resuelve P1–P7 | Sí, caso a caso | Sí | Sí | Sí |
| Resuelve la causa raíz | No | Sí | Parcial | Sí |
| Conserva lo construido | Todo | Casi todo | Todo | Casi todo |
| Migración de datos | Ninguna | Media | Baja | Media |
| Dependencia del modelo | Baja | Media | Alta | Media-alta |
| Coste por dictado | Igual | Igual | + tokens | + tokens |
| Riesgo de orden inventada | Bajo | Medio | Alto | Medio (mitigado) |
| Aprendizaje de Julio | Igual | Mejor | Mejor | Mejor |
| Encaje con WhatsApp | Bajo | Alto | Alto | Alto |
| Complejidad | Baja | Media-alta | Media | Alta |
| Demostrable con pruebas | Sí | Sí | Sí (offline) | Sí |

**Lectura preliminar (para la auditoría externa, no decisión):** A no basta; C
sola traslada el riesgo al modelo; B sin C deja la producción de órdenes en
manos del código y reproduce el problema; **D es la que ataca la causa sin
soltar la autoridad**. Su coste es el más alto y exige un corpus de evaluación
que hoy no existe.

---

## Cómo se preservarían las garantías (válido para B, C y D)

| Garantía | Cómo se mantiene |
|---|---|
| Dato trazable a su fuente | cada orden y cada acción exigen cita; sin cita no se ejecuta |
| Correcciones versionadas | la corrección apunta a la orden o al hecho y crea versión nueva |
| Memoria revisable | el vocabulario aprendido se sigue aplicando como pista, no como regla |
| Confirmación humana | se conserva; la orden no ejecuta por sí sola |
| Autorización por rol | la validación de permisos sigue en el backend |
| Idempotencia | clave externa por orden/acción, igual que hoy |
| Dinero | doble confirmación intacta; el LLM no calcula |
| Tareas con seguimiento | la orden DELEGAR crea tarea interna con el mismo ciclo |
| Cerebro ≠ herramientas | la orden se ejecuta con los módulos actuales |
| Aislamiento interno/externo | el flujo externo no recibe órdenes internas; siguen siendo permisos y fuentes |

---

## Qué haría falta para decidir

1. **Corpus real:** 30–50 dictados de Julio con la orden esperada (no la acción).
2. **Evaluación offline** de la propuesta del modelo por campo (tipo, canal,
   responsable, restricciones).
3. **Prueba adversarial** de orden inventada / canal incoherente.
4. **Coste** por dictado con el proveedor actual.
5. **Decisión de producto** sobre constancia (P6): ¿una orden CONSTANCIA crea un
   registro visible o solo el borrador?

Sin 1–3, cualquier elección se apoya en impresiones, no en evidencia.
