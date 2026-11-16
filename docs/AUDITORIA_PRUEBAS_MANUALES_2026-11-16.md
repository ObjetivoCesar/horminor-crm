# Auditoría de las pruebas manuales del 16 de noviembre de 2026

Documento de evidencia. Describe **lo que quedó registrado** de las pruebas
manuales hechas por Julio en el laboratorio del router, sin modificar el código
auditado.

- **Sistema observado:** prototipo aislado `experiments/router_horminor`,
  versión `router-1.7`, servido en `http://localhost:8055`.
- **Naturaleza:** laboratorio de desarrollo. Propone un plan; **no ejecuta**
  tareas, no envía mensajes ni crea órdenes.
- **Fecha de los hechos:** 2026-11-16, entre 14:12 y 14:25 (hora de Ecuador,
  UTC-5).
- **Código auditado:** commits `beb9218` (router 1.7), `e688a99` y `91f614c`
  (solo laboratorio). Hashes en `experiments/router_horminor/VERSION.json`.
- **Extracción de la traza:** `docs/auditoria_pruebas_manuales_2026-11-16/traza_manual.json`

---

## 1. Qué se conserva y qué no

El laboratorio escribe una traza append-only en
`experiments/router_horminor/evidencias/errores.jsonl` **solo cuando hay una
corrección o una aclaración**. No guarda:

- el dictado original de cada prueba;
- el mensaje que el Cerebro mostró;
- las preguntas de aclaración;
- el plan devuelto al confirmar;
- las confirmaciones sin corrección.

Por eso este informe **no puede reconstruir las diez pruebas completas**. Lo que
sí se puede afirmar es lo que está en la traza: seis interacciones de la ventana
manual, con la frase exacta de Julio y el cambio aplicado. Las otras cuatro
pruebas no dejaron rastro y no son auditables con la evidencia actual.

### Cómo se separó la traza manual

`errores.jsonl` tenía 16 entradas. Diez corresponden a ejecuciones internas del
equipo:

| Entradas | Ventana (UTC) | Contenido | Origen |
|---|---|---|---|
| 1–5 | 18:20:47–18:30:21 | corrección «no es Díaz Sur es DIALSUR…» repetida | pruebas internas del laboratorio |
| 6 | 18:34:14 | «Todo esta ok» | prueba interna confirmar vs corregir |
| 7–10 | 18:43:32–19:06:57 | aclaración de Las Palmeras repetida | corridas internas (pruebas automáticas y guion de flujo; ver hallazgo F3) |

Las seis entradas de 19:12:35 en adelante son las de la ventana manual.

---

## 2. Casos documentados

En todos, `version_antes = 1` y `version_despues = 2`: cada prueba partió de un
dictado nuevo y recibió **una sola** corrección antes de terminar.

### Caso 1 — 14:12:35 · corrección puntual de una palabra

> «No, donde dije bomba me refería a la mezcladora. Lo demás está correcto, no
> cambies las otras tareas.»

Registrado:

- `E2.que_hacer`: «…y la **bomba** estén preparadas» → «…y la **mezcladora**
  estén preparadas».
- `confirmacion`: `RESTO_APROBADO`.

Lectura: el sistema aplicó un cambio quirúrgico y respetó el resto, tal como se
le pidió. Es el comportamiento correcto para una corrección de vocabulario.

### Caso 2 — 14:13:31 · confirmación de dato con orden nueva

> «Ya me confirmaron que son 42 metros. Ahora sí prepara la cotización, pero la
> reviso yo antes de enviarla.»

Registrado:

- `cotizacion.volumen_m3`: 42 → 42 (sin cambio real).
- Nada más.

Lectura: **fallo de cobertura**. El sistema reconoció la confirmación del
volumen, pero descartó dos instrucciones nuevas: la tarea «preparar la
cotización» no se creó, y la restricción «la reviso yo antes de enviarla» no se
registró en ninguna condición. El mensaje del Cerebro habría dado la aclaración
por resuelta sin reflejar el encargo nuevo.

### Caso 3 — 14:14:27 · condición con canal preferido

> «Si mañana todavía no aparece el dinero, que secretaría llame al ingeniero.
> Prefiero llamada, no WhatsApp. La planificación de los camiones sigue
> adelante.»

Registrado:

- `E1.condiciones`: se añade «Si mañana todavía no aparece el dinero, secretaría
  debe llamar al ingeniero Ricardo (por llamada, no por WhatsApp)».
- `E2.estado`: `CONDICIONADO` → `PROPUESTO`.

Lectura: **parcial**. La condición y la preferencia de canal quedaron escritas
dentro del texto de la condición, y la tarea que estaba bloqueada se liberó,
que es lo que pedía la última frase. Pero el canal del encargo no cambió: la
preferencia «llamada, no WhatsApp» vive como prosa, no como atributo del
encargo, así que un ejecutor posterior tendría que interpretarla.

### Caso 4 — 14:23:48 · dejar una decisión pendiente

> «El descuento déjalo como solicitud pendiente de mi decisión. Las otras dos
> tareas sí quiero que queden asignadas.»

Registrado:

- `E3.estado`: `CONDICIONADO` → `POR_DEFINIR`.

Lectura: **parcial**. La tarea del descuento dejó de estar condicionada y pasó a
pendiente de decisión, que es el efecto buscado. No hay registro de que las
otras dos tareas se hayan asignado: la traza no distingue «asignada» de
«propuesta», así que esa mitad de la frase no es verificable.

### Caso 5 — 14:24:14 · corrección de referente

> «Cuando dije que secretaría hable con él, me refería a Daniel Torres. Y si hay
> problemas con el acceso, el jefe de planta debe informar primero a
> secretaría, para que ella se comunique con Daniel.»

Registrado:

- `E1.destinatario`: «Daniel Torres» → «Daniel Torres» (**sin cambio real**).
- `E2.condiciones`: se añade la regla de escalamiento por acceso.

Lectura: **fallo de corrección de referente**. El sistema registró una
actualización que no actualizó nada; la corrección «me refería a Daniel Torres»
no tuvo efecto porque el destinatario ya decía eso, y el registro no permite
saber si el «él» original apuntaba a otra persona. La segunda instrucción sí
quedó como condición. Es el caso más delicado para la auditoría: una entrada
`CORRECCION` con antes = después puede leerse como éxito cuando pudo ser un
no-op.

### Caso 6 — 14:25:14 · cancelar uno y confirmar el resto

> «Cancela el tercer encargo, el del WhatsApp. Los otros dos están bien,
> confírmalos y deja el informe de facturas solamente para mi revisión, sin
> iniciar cobros.»

Registrado:

- `E3.estado`: `PROPUESTO` → `CANCELADO`.
- `E1.condiciones`: se añade «El informe es solo para revisión de Julio, sin
  iniciar cobros».
- `confirmacion`: `RESTO_APROBADO`.

Lectura: **el mejor de los seis**. Resolvió «el del WhatsApp» al encargo
correcto, canceló solo ese y dejó constancia de que el informe no autoriza
cobros. La confirmación del resto quedó registrada como `RESTO_APROBADO`, sin
detalle de cuáles eran las otras dos tareas.

---

## 3. Pruebas sin registro

De las diez pruebas manuales, cuatro no produjeron ninguna entrada. No es
posible saber si fueron:

- pruebas en las que el Cerebro respondió bien y Julio confirmó (las
  confirmaciones no se registran), o
- pruebas en las que algo falló y Julio simplemente cerró la pestaña.

**Ninguna de las cuatro es auditable con la evidencia actual.** Atribuirles un
resultado sería inventarlo.

---

## 4. Hallazgos

| ID | Hallazgo | Severidad | Evidencia |
|---|---|---|---|
| F1 | La traza no guarda dictado, mensaje, preguntas ni plan; solo correcciones y aclaraciones | Alta | esquema de `errores.jsonl` |
| F2 | Las confirmaciones sin corrección no dejan rastro; 4 de 10 pruebas son invisibles | Alta | 6 entradas para 10 pruebas |
| F3 | `tests_core` escribe `ACLARACION` en el mismo archivo de evidencia | Media | entradas 7–10 idénticas, una por corrida |
| F4 | Se registran cambios con antes = después como si fueran correcciones | Alta | caso 5, `E1.destinatario` |
| F5 | Las órdenes nuevas dentro de una respuesta se pierden | Alta | caso 2, cotización no creada y restricción no registrada |
| F6 | La preferencia de canal queda como prosa dentro de una condición | Media | caso 3 |
| F7 | `RESTO_APROBADO` no dice qué tareas quedaron aprobadas | Media | casos 1, 4, 6 |

F3 tiene un efecto práctico: la evidencia manual queda mezclada con la de las
pruebas automáticas, y un auditor externo no puede distinguirlas por el
contenido, solo por la hora.

---

## 5. Qué haría falta para una auditoría completa

1. **Registro de corrida**: guardar por cada prueba el dictado, el borrador
   antes y después, el mensaje mostrado, las preguntas y el plan. Append-only,
   en un archivo separado de las pruebas automáticas.
2. **Separar la evidencia de test** de la evidencia manual (F3), para que nadie
   confunda una corrida de `tests_core` con una prueba de Julio.
3. **Distinguir cambio real de no-op** (F4): si antes = después, no debe
   registrarse como corrección aplicada.
4. **Aceptar órdenes nuevas en la respuesta** (F5): una frase como «prepara la
   cotización» debe crear el encargo, no solo confirmar el volumen.

Los puntos 1 a 4 tocan código del prototipo. No se implementaron: este informe
se hizo sin modificar el sistema auditado.

---

## 6. Anexo

- Traza cruda de la ventana manual (6 entradas):
  `docs/auditoria_pruebas_manuales_2026-11-16/traza_manual.json`
- Traza completa (16 entradas):
  `experiments/router_horminor/evidencias/errores.jsonl`
- Versión y hashes: `experiments/router_horminor/VERSION.json`
- Pruebas automáticas al momento del corte: 21/21
  (`python -m experiments.router_horminor.tests_core`)
