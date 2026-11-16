# Trazabilidad de las pruebas manuales P1–P7

> **Qué es esto.** Inventario de lo que quedó registrado de las siete pruebas
> que Julio ejecutó a mano en `/panel/cerebro`, con el primer punto donde la
> interpretación correcta se convierte en una equivocada.
>
> **Método:** consultas de solo lectura a PostgreSQL y a los logs del contenedor.
> No se reejecutó ninguna prueba ni se modificó ningún registro.
> **Corte del código:** commit `2a5fd93`.
> **Datos completos:** `docs/auditoria_cerebro/p1_p7_registros.json`.

---

## 1. Inventario general

Las ocho ejecuciones están en la base (P7 se ejecutó dos veces). Todas usaron
`deepseek-chat`, prompt `cerebro-v7`, desde el perfil Julio Villavicencio
(SUPERADMIN). **Ninguna tuvo corrección, cancelación ni ejecución**: son
borradores propuestos, sin decisiones humanas posteriores.

| Caso | Borrador | Extracción | Hora (local) | Estado | Latencia |
|---|---|---|---|---|---|
| P1 | `2604865d-3448-490b-8152-54060ed6b8f6` | `c3ddcb6c-ff4a-4aea-8213-706189ffe4c6` | 09:52:03 | REQUIERE_ACLARACION | 4.010 ms |
| P2 | `ffbb1996-a479-4ac8-be07-6df021622cf5` | `7daf8756-c240-4787-9145-e23cc008fef4` | 09:52:37 | REQUIERE_ACLARACION | 2.904 ms |
| P3 | `c088c80d-f689-4c08-ab66-59a080537437` | `fe3421ff-c5b0-4acc-bfc4-1727cb987baa` | 09:53:13 | REQUIERE_ACLARACION | 2.814 ms |
| P4 | `7f56adb4-2d3b-4153-b86e-82e5c68fc3a4` | `213faab7-45df-47cc-be1d-338a5356ea6e` | 09:53:56 | SIN_ACCIONES | 2.331 ms |
| P5 | `f0c24656-14dd-4bb8-9be8-162574d80043` | `b993dc38-118f-4471-a834-4e93f9197867` | 09:56:24 | PENDIENTE_CONFIRMACION | 3.894 ms |
| P6 | `160e47a3-705e-4c37-a687-f910b8936476` | `8c732900-b993-46d3-95fc-562cc1f6f437` | 09:57:43 | SIN_ACCIONES | 1.809 ms |
| P7a | `291f84eb-9193-4bc8-b769-00e8918e45bc` | `d2e8b236-252e-4142-9fb0-e34f3d4f04cf` | 09:58:03 | REQUIERE_ACLARACION | 2.317 ms |
| P7b | `72978235-6f6e-4c13-8db4-b54cd32187e5` | `a8e335a0-2371-4d25-a8a6-342010915eec` | 09:58:15 | REQUIERE_ACLARACION | 2.858 ms |

Los `POST /api/v1/cerebro/interpretar` aparecen en el log del contenedor a las
14:52:03Z, 14:52:37Z, 14:53:13Z, 14:53:56Z, 14:56:24Z, 14:57:43Z, 14:58:03Z y
14:58:15Z, exactamente 30–50 ms después de cada borrador. **P7 se envió dos
veces** con 12 segundos de diferencia: el sistema creó dos borradores y no hay
deduplicación en la interpretación (la idempotencia existe al crear la tarea,
no al interpretar).

---

## 2. Qué se conserva y qué no

| Dato | Clasificación | Dónde / por qué |
|---|---|---|
| Texto de entrada | **RECUPERADO** | `cerebro_extracciones.texto_directo` (texto, no audio) |
| Respuesta del extractor (sobre) | **RECUPERADO** | `cerebro_extracciones.sobre_json`. Es el sobre **validado** por `SobreIn`; no es el cuerpo HTTP crudo. |
| Cuerpo HTTP crudo del LLM | **NO DISPONIBLE** | No se registra; solo se guarda el JSON validado |
| Prompt exacto enviado | **NO DISPONIBLE** como registro | Se conoce la plantilla `cerebro-v7` y las claves; el mensaje incluye lista de clientes y vocabulario del momento, que no se guardaron |
| Hechos citados (`HechoCitado`) | **RECONSTRUIBLE** | No hay tabla de hechos; se derivan del sobre + texto con el código del corte. **No se reejecutó** en esta investigación |
| Encargos resultantes | **RECUPERADO** | `cerebro_borradores.encargos_json` |
| Acciones propuestas | **RECUPERADO** | `cerebro_borradores.acciones_propuestas_json` |
| Preguntas | **RECUPERADO** | `cerebro_borradores.preguntas_pendientes_json` |
| Condiciones | **RECUPERADO** | `cerebro_borradores.condiciones_json` (vacío en P1–P7) |
| Notas del verificador | **NO DISPONIBLE** | Se devuelven al panel y no se guardan |
| Decisión ENVIAR/DELEGAR y rol | **RECONSTRUIBLE** | Se deduce de las acciones guardadas; no se guarda el valor intermedio |
| Reglas del compilador que se activaron | **RECONSTRUIBLE** | Determinístico desde el sobre; no instrumentado |
| Correcciones y ejecuciones | **NO APLICA** | No hubo: 0 correcciones y 0 ejecuciones en los 8 borradores |
| Log de acceso | **RECUPERADO** (parcial) | Hora y ruta `POST /interpretar`, sin cuerpo ni id de borrador |

**No hay evidencia de las respuestas visibles del panel.** Para completar la
comparación con lo que Julio vio, hacen falta esas capturas o transcripciones;
este documento solo describe lo persistido.

---

## 3. Caso por caso

### P1 — «Mauricio Cueva», «chicos de planta», «28 metros»

**Entrada.** «…que secretaría revise si ya está listo el despacho de mañana para
la obra del ingeniero Mauricio Cueva. Son 28 metros cúbicos de hormigón de 240.
Que los chicos de planta tengan todo preparado desde temprano… al ingeniero
Mauricio, al 0965555555, hay que enviarle por WhatsApp un recordatorio… Todavía
no le envíes nada hasta que yo confirme el mensaje.»

**El modelo propuso 3 encargos** (3 destinatarios: secretaría, chicos de planta,
Mauricio). Hechos: `tarea.mensaje` para los tres, volumen 28 y resistencia 240 en
el encargo 1, teléfono en el 3.

**Resultado guardado:**
1. `crear_tarea_interna` para secretaría — correcto.
2. `crear_tarea_recordatorio` **a «chicos de planta»** — incorrecto: es una
   instrucción interna, no un WhatsApp.
3. `crear_tarea_recordatorio` a 0965555555 con
   `mensaje_por_confirmar = false` — incorrecto: Julio dijo que no se enviara
   hasta que él confirmara el mensaje.

**Primer punto de divergencia:**
- Encargo 2: el extractor hizo lo correcto (destinatario + mensaje). El
  compilador llamó a `detectar_intencion_tarea` (`internas.py:199`), que devolvió
  `None` porque «chicos de planta» no está en `ALIAS_ROL` ni hay verbo de
  encargo reconocido; `_compilar_asunto` (`compilador.py:918-928`) **asume
  ENVIAR**. **Falló el código, no el modelo.**
- Encargo 3: `mensaje_es_final` (`compilador.py:748`) devolvió `true` porque el
  mensaje contiene «confirme»; la prohibición «todavía no le envíes nada» quedó
  solo en `ambiguedades` (texto libre) y el compilador **no lee ambigüedades**.
  Falla de representación: no hay hecho de restricción.

**Evidencia:** RECUPERADO (texto, sobre, acciones, preguntas). Notas del
verificador: NO DISPONIBLE.

---

### P2 — «constructora El Valle», «35 o 38»

**Entrada.** «…obra en Catamayo para la constructora El Valle. Creo que
necesitan unos 35 o 38 metros cúbicos, no estoy seguro… Lo que sí está
confirmado es que el hormigón es de 240. Que secretaría llame al residente de
obra y confirme el volumen exacto antes de preparar cualquier cotización. No
quiero que le den un precio todavía.»

**El modelo propuso 2 encargos.** El volumen quedó `TENTATIVO` (38), la
resistencia `EXTRAIDO` (240) y el precio `NO_DIJO`. El encargo 2 es la
instrucción a secretaría.

**Resultado guardado:** encargo 1 → `crear_cliente` + **una tarea interna con
todo el párrafo como instrucción**; encargo 2 → otra tarea interna con la
instrucción. Pregunta: `cotizacion.volumen_m3`. **Dos tareas para una sola
instrucción.**

**Primer punto de divergencia:** `_texto_del_grupo` (`compilador.py:1396`). Como
el dictado **no tiene ordinales**, `segmentar()` devuelve un único segmento con
índice 1; para el encargo 1, `texto_de(segmentos, 1)` devuelve **el dictado
completo**. Ese texto contiene «secretaría» y verbos de encargo, así que la
síntesis de `tarea.mensaje` (`compilador.py:1467-1500`) crea una tarea con todo
el párrafo. **Falló el compilador, no el modelo.** El modelo separó bien.

**Evidencia:** RECUPERADO. Notas: NO DISPONIBLE.

---

### P3 — «Ramiro», «8500», «Zamora Huayco»

**Entrada.** «El ingeniero Ramiro nos ofreció transferir mañana 8500 dólares como
anticipo de la obra del barrio Zamora Huayco. Hasta que no tengamos confirmado
ese depósito no quiero que autoricen el despacho. Que contabilidad revise el
banco y avise a secretaría cuando el dinero esté verificado. Los 60 metros
cúbicos de hormigón de 210 quedan pendientes de programación.»

**El modelo propuso 2 encargos:** el anticipo/obra (con `pago.recibido = false`
citando «hasta que no tengamos confirmado») y la instrucción a contabilidad.

**Resultado guardado:**
- Encargo 1 → **`crear_cotizacion_borrador`** (60 m³, FC-210, precio 118
  PROVISIONAL) + tarea interna con todo el párrafo (otra vez la síntesis del
  índice 1). Pregunta: `cliente.nombre`.
- Encargo 2 → tarea interna a contabilidad — correcto.

**Primer punto de divergencia (acción no pedida):** `_compilar_asunto`
(`compilador.py:817`) crea la cotización porque hay volumen + obra + resistencia
+ precio de receta. El dictado dice «quedan pendientes de programación» y «no
autoricen el despacho», pero **no existe un hecho de intención** que autorice o
niegue cotizar. Es el caso más claro de «hechos confundidos con intención».
La duplicación de la tarea vuelve a ser la síntesis del índice 1.

**Evidencia:** RECUPERADO.

---

### P4 — «ingeniero Sandoval», «no preparen todavía la cotización»

**Entrada.** «Que preparen una cotización de 45 metros cúbicos para el ingeniero
Sandoval. Bueno, no, mejor no preparen todavía la cotización porque vamos a
revisar los precios. Pero sí quiero que secretaría se comunique con el ingeniero
y confirme para qué fecha necesita el hormigón. Eso sí que lo hagan hoy, lo otro
queda suspendido.»

**El modelo propuso 2 encargos** y marcó el volumen como `NO_DIJO`. El encargo 2
es la instrucción válida a secretaría con `cuando = "hoy"`.

**Resultado guardado:** **`SIN_ACCIONES`**, sin acciones, sin preguntas.

**Primer punto de divergencia:** `dictado_revocado` (`compilador.py:451`) busca
«mejor no» en **todo el texto** y devuelve verdadero; `compilar`
(`compilador.py:1433`) corta antes de agrupar. **La revocación parcial se
convierte en total** y se pierde la instrucción que Julio quería que sí se
hiciera. Falla del compilador: la revocación no está ligada a un encargo.

**Evidencia:** RECUPERADO.

---

### P5 — «nos falta un chofer», «suficiente cemento»

**Entrada.** «…revisar cuántas fundidas tenemos para el viernes porque me parece
que nos falta un chofer. También que en bodega comprueben si tenemos suficiente
cemento… Y de paso necesito que secretaría me prepare un informe de los clientes
que tienen facturas vencidas, pero sin cobrarles todavía, primero quiero revisar
esos valores personalmente.»

**El modelo propuso 3 encargos** (revisión general, bodega, secretaría).

**Resultado guardado:** tres `crear_tarea_interna`:
1. a SECRETARIA (el dictado no nombró área; era planta/logística),
2. a BODEGA — correcto,
3. a SECRETARIA con la restricción **dentro del texto** de la instrucción.

**Primer punto de divergencia:**
- Encargo 1: `detectar_rol_interno` no encuentra área y el compilador asigna
  SECRETARIA por defecto (`_compilar_asunto`). El área venía implícita
  («fundidas», «chofer»), no nombrada.
- La restricción «sin cobrarles todavía» no se modela: `_condiciones` solo
  reconoce plazo, entrega contra pago y expediente. Queda como texto; la tarea
  no lleva una condición ni un bloqueo de cobranza.

**Evidencia:** RECUPERADO.

---

### P6 — «anulemos todas sus facturas», «20 por ciento»

**Entrada.** «Te voy a contar lo que me dijo un cliente. Me dijo que anulemos
todas sus facturas, que le hagamos un descuento del 20 por ciento y que le
entreguemos el hormigón sin anticipo. Pero no hagas nada de eso, solamente
quiero que quede constancia de lo que solicitó. Todavía no hemos aceptado
ninguna de esas condiciones.»

**El modelo** devolvió `intencion = CONSULTA`, un único hecho
`cotizacion.descuento_pct = 20` en estado `NO_DIJO` y una ambigüedad explicando
que el cliente lo pidió pero el hablante ordena no ejecutarlo.

**Resultado guardado:** `SIN_ACCIONES`, sin preguntas. **No se propuso nada
peligroso: correcto.**

**Punto de divergencia:** no hay error de seguridad. Sí hay una carencia de
producto: «solamente quiero que quede constancia» **no produce una constancia
visible**; el borrador se guarda, pero la respuesta no lo dice ni queda un
registro nombrado. El descuento del 20 % y las facturas no se conservan como
hechos.

**Evidencia:** RECUPERADO.

---

### P7 — «coordine con el chofer», «antes de las seis» (dos ejecuciones)

**Entrada.** «Oye, urgente, que secretaría coordine con el chofer de la
mezcladora porque mañana tenemos que estar en la obra antes de las seis de la
mañana. La fundida empieza a las seis y el equipo tiene que llegar antes.
Todavía no sé exactamente a qué hora debe salir el camión de la planta, eso lo
tiene que calcular y confirmar logística. Y por favor, que me avisen apenas esté
todo coordinado.»

**P7a (09:58:03):** el modelo propuso 3 encargos: secretaría, logística y un
tercero **sin destinatario** para «que me avisen».
**P7b (09:58:15):** el modelo propuso 3 encargos y en el tercero puso
`tarea.destinatario = secretaría`. El resto es idéntico.

**Resultado guardado (ambos):**
- Encargo 1 → `crear_tarea_interna` a secretaría, con
  **`cuando = "06:00"`** y `ficha.plazo_dicho = "06:00"`, prioridad URGENTE.
- Encargos 2 y 3 → **sin acción**; preguntas `tarea.telefono` y `tarea.mensaje`
  (y `tarea.destinatario` en a).

**Primer punto de divergencia (doble):**
1. **Hora de entrega tomada como plazo de la tarea.** El extractor puso
   `cotizacion.hora_entrega = 06:00` (correcto), pero
   `_completar_cuando_de_tarea` (`extractor.py:562`) buscó una hora en la frase
   de la tarea y creó `tarea.cuando = 06:00`. El compilador lo copió a la tarea.
   **Falló el extractor**, en un post-proceso heurístico.
2. **«logística» y «que me avisen» tratados como envío externo.** No están en
   `ALIAS_ROL`; `detectar_intencion_tarea` devuelve `None` y el compilador asume
   ENVIAR. De ahí las preguntas de teléfono y mensaje. **Falló el código.**

P7a y P7b son **la misma prueba enviada dos veces**; no hay deduplicación de
interpretaciones (sí la hay al crear tareas).

**Evidencia:** RECUPERADO para ambas.

---

## 4. Resultado del análisis

| Caso | ¿Dónde nace el error? | Componente | ¿El modelo acertó? |
|---|---|---|---|
| P1 | intención por defecto + restricción no modelada | compilador / extractor | Sí (hechos y encargos) |
| P2 | texto del encargo 1 = dictado completo + síntesis | compilador | Sí |
| P3 | acción derivada de hechos, sin orden | compilador | Parcial (no emitió intención de cotizar) |
| P4 | revocación total del dictado | compilador | Sí (separó los encargos) |
| P5 | área por defecto + restricción sin modelo | compilador / extractor | Parcial (no extrajo «falta un chofer») |
| P6 | sin error de seguridad; falta constancia visible | extractor / respuesta | Sí |
| P7 | hora de entrega → plazo de tarea; área no reconocida | extractor / compilador | Parcial (un encargo sin destinatario) |

**Conclusión de trazabilidad:** en 6 de 7 casos el extractor identificó bien los
datos y los encargos; el error se produce después, al convertir hechos en
intención, canal, responsable o plazo. El modelo falla al no representar
restricciones y al dudar del destinatario interno, pero **no es la causa
principal**.

---

## 5. Límites de la evidencia

1. **No hay notas del verificador ni cuerpo crudo del LLM**: no se guardan.
2. **No hay hechos persistidos**: se derivan del sobre; no se reejecutó.
3. **P7 duplicado**: dos borradores; no se sabe si Julio vio el primero o el
   segundo.
4. **Las respuestas visibles del panel no están en el repositorio**; el
   contraste con lo que Julio vio queda pendiente de su material.
5. **Los tiempos son de creación del borrador**, no del inicio de la petición;
   la latencia del LLM está en `latencia_ms`.
