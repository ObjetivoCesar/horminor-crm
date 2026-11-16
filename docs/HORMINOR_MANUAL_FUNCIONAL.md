# Manual Vivo de Horminor

> **Qué es.** La explicación oficial de qué hace cada función del CRM, por qué
> existe, quién la usa y qué consecuencias tiene. No es un diccionario técnico:
> es el documento que permite a Julio, a la secretaría, a administración y a
> cualquier agente de IA entender el sistema sin preguntarle al programador.
>
> **Estado:** v1 — 2026-11-15. Cubre el **Cerebro** y su relación con el CRM, las
> tareas, secretaría, WhatsApp y los módulos ejecutores.
>
> **Regla de oro:** acá solo se documenta lo que **existe y funciona**. Si una
> función no está implementada, se dice explícitamente en «Todavía no existe».
>
> **Una sola fuente.** Este documento es la fuente oficial de definiciones. Los
> documentos técnicos (`docs/CEREBRO_VOZ_DISENO.md`,
> `docs/CONTRATO_WHATSAPP_CEREBRO.md`, `docs/CEREBRO_MATRIZ_BRECHAS.md`) explican
> el *cómo*; acá se explica el *qué* y el *para qué*. No se duplican glosarios.

---

## 1. Cómo se usa este manual

- **Si eres Julio o la secretaría:** busca el botón o la palabra que ves en
  pantalla en el índice (§6) o en «Nombres visibles» (§8).
- **Si eres administración:** lee el mapa (§3) y el capítulo de tareas (§5.3).
- **Si eres desarrollador o agente de IA:** lee el término completo; cada uno
  tiene su referencia técnica. No inventes funciones: si no está acá, se
  pregunta y se documenta.
- **Si cambias una función:** actualiza este manual el mismo día (§9).

---

## 2. Los tres lenguajes

Horminor usa tres nombres para lo mismo, y conviene no mezclarlos:

| Lenguaje | Ejemplo | Dónde se usa |
|---|---|---|
| **Técnico** | `ACUSADA`, `acusada_en`, `cerebro_tareas_internas` | código, base de datos, API |
| **Visible** | «Recepción confirmada» | panel, botones, mensajes |
| **Cotidiano** | «la secretaria confirmó que recibió el encargo» | conversación con Julio |

**No se cambian los nombres técnicos** que ya funcionan: cambiarlos rompería
datos e integraciones. Lo que se cuida es el **nombre visible**.

### Estados, eventos y acciones no son lo mismo

| Tipo | Qué es | Ejemplo | Se guarda en |
|---|---|---|---|
| **Estado** | la situación actual de una tarea o un borrador | `NOTIFICADA`, `RESUELTA`, `REGISTRADA` | columna `estado` |
| **Evento** | un hecho que ocurrió y quedó registrado | «se consultó», «se confirmó la recepción», «se elevó» | `cerebro_tareas_internas_eventos` |
| **Acción** | lo que una persona puede hacer ahora | «Confirmar que recibí la tarea» | botón del panel |

Por eso **«vista» y «acusada» no son estados**: son eventos. La tarea sigue
`NOTIFICADA` aunque alguien la haya consultado o confirmado su recepción.

---

## 3. Mapa funcional

### 3.1 Recorrido de una instrucción

```
Julio dicta (audio o texto) por WhatsApp o por el laboratorio
        │
        ▼
[1] Se guarda y se transcribe            ← automático (Voz)
        │
        ▼
[2] Se normaliza el habla ecuatoriana    ← automático (Normalizador)
        │
        ▼
[3] El modelo propone hechos CON CITA    ← automático (Extractor)
        │
        ▼
[4] El backend verifica cada cita        ← automático (Hechos)
        │
        ▼
[5] El compilador arma el borrador       ← automático (Compilador)
        │        con acciones y preguntas
        ▼
[6] Se lee en voz alta «Lo que entendí»  ← automático (Resumen)
        │
        ▼
[7] Julio corrige lo que está mal        ← HUMANO (panel; WhatsApp: pendiente)
        │
        ▼
[8] Julio confirma acción por acción     ← HUMANO (obligatorio)
        │
        ▼
[9] Se crea la tarea o el recordatorio   ← automático al confirmar
        │
        ▼
[10] La secretaría recibe el aviso       ← automático (panel)
        │
        ▼
[11] Consulta, confirma recepción        ← HUMANO (eventos: vista, acuse)
        │
        ▼
[12] Hace el trabajo o lo justifica      ← HUMANO (resuelta / justificada)
        │
        ▼
[13] Registra el resultado con datos     ← HUMANO (registrada)
        │
        ▼
[14] Julio puede consultar qué pasó      ← panel (WhatsApp: pendiente)
```

### 3.2 Quién hace qué

| Paso | Automático | Humano | Otro módulo |
|---|---|---|---|
| Transcribir | ✅ | | |
| Interpretar y proponer | ✅ | | |
| Corregir | | ✅ Julio / secretaría | |
| Confirmar | | ✅ Julio / secretaría | |
| Enviar WhatsApp | | | ✅ módulo WhatsApp |
| Crear cliente / cotización | | | ⏳ todavía no conectado |
| Registrar dinero | | ✅ doble confirmación | ✅ caja / contabilidad |
| Avisar la tarea | ✅ | | |
| Confirmar recepción | | ✅ secretaría | |
| Resolver / justificar | | ✅ secretaría | |
| Registrar resultado | | ✅ secretaría / supervisor | |
| Elevar al supervisor | | ✅ Julio (SUPERADMIN) | |

### 3.3 Los dos Cerebros que no son dos

- **Cerebro (laboratorio y panel):** interpreta dictados, propone y delega.
- **Gato:** responde consultas de solo lectura sobre los datos del CRM y gestiona
  recordatorios por conversación. **No** interpreta dictados ni arma borradores.
- **WhatsApp:** es un **canal**. La fase conversacional está pendiente; el
  contrato ya está escrito (`docs/CONTRATO_WHATSAPP_CEREBRO.md`).

### 3.4 Cómo se conectará todo (arquitectura futura, **no implementada**)

Esta es la dirección aprobada el 2026-11-15. **Hoy no está construida**: se deja
escrita para no confundirla con lo que existe.

```
FLUJO INTERNO (Julio y secretaría)
  Julio/secretaría ── hablan con ──► GATO (interfaz conversacional)
                                        │  usa herramientas autorizadas
                                        ▼
                                     CEREBRO (inteligencia interna)
                                        │  interpreta, recuerda, estructura, propone
                                        ▼
                                  MÓDULOS (clientes, cotizaciones, caja, WhatsApp)
                                        │  ejecutan y verifican
                                        ▼
                                  Resultado y seguimiento
```

```
FLUJO EXTERNO (clientes por WhatsApp)
  Cliente ──► Atención comercial (herramientas y conocimiento LIMITADOS)
                 │  horarios, ubicación, productos, precios oficiales
                 │  NO ve memoria, documentos ni herramientas internas
                 │  NO negocia descuentos ni crédito
                 ▼
             Transferencia a Julio o al responsable
                 (resumen SOLO de la conversación del cliente)
```

**Reglas de esta arquitectura:**

1. El Cerebro **no será un módulo visible** para el usuario final: el laboratorio
   es de prueba. En producción, la cara es Gato.
2. **Hoy no se conecta Gato con el Cerebro.** Primero se termina de probar y
   documentar el Cerebro.
3. El Cerebro **no duplica** las herramientas operativas que ya tiene Gato.
4. Los dos flujos se separan por **permisos, herramientas y fuentes de
   conocimiento**, no por instrucciones en el prompt.
5. El flujo externo no accede al contexto privado; la transferencia lleva un
   resumen limitado a esa conversación.
6. Los módulos siguen siendo los responsables de ejecutar y verificar.

El detalle completo y las prioridades están en `docs/CONTINUIDAD_CEREBRO.md`.

### 3.5 Router conversacional: fase cerrada (solo laboratorio)

Entre el 15 y el 16 de noviembre se probó una variante del Cerebro pensada para
el trabajo diario de Julio: escucha un dictado, lo separa en encargos, propone
responsable, pide aclaraciones, recibe correcciones y entrega un plan para
confirmar.

**Esa fase se cierra** con la versión `router-1.7`, conservada tal como está en
`experiments/router_horminor/`. No se agregan analizadores, reglas, interfaces
ni cambios de arquitectura. Los errores que aparezcan se corrigen por la vía
que ya existe: la caja de respuesta y la traza de correcciones.

**Importante:** el router **no está conectado al CRM**. Vive en un laboratorio
local, no escribe en la base, no crea tareas ni cotizaciones y no envía nada.
`/panel/cerebro` sigue ejecutando el motor anterior (V07). Ni el laboratorio ni
`/panel/cerebro` son la experiencia final del usuario.

El detalle técnico, las limitaciones y el backlog están en
`docs/ROUTER_CONVERSACIONAL_CIERRE.md`.

---

## 4. Capítulo 1 — El Cerebro y sus piezas

### Término: Cerebro

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `app/cerebro/`, endpoints `/api/v1/cerebro/*` |
| **Nombre para el usuario** | El Cerebro |
| **Qué significa** | La pieza que convierte un dictado en un borrador de acciones y hace seguimiento de lo delegado. |
| **Para qué existe** | Que una instrucción dictada no se pierda y no se ejecute sin control humano. |
| **Quién lo utiliza** | Julio (dicta y confirma), secretaría (recibe y cierra tareas), administración (supervisa). |
| **Qué lo activa** | Un texto o audio que entra por el laboratorio (`/panel/cerebro`) o por la API. |
| **Qué sucede después** | Se crea una extracción con hechos citados y un borrador; nada se escribe en el negocio hasta que un humano confirma. |
| **Qué NO significa** | No es un chatbot general ni reemplaza a Gato, a secretaría ni al módulo de WhatsApp. |
| **Ejemplo** | Julio dicta un pedido; el Cerebro propone cotización y tarea; Julio confirma; secretaría la recibe. |
| **Dónde se encuentra** | `/panel/cerebro` (laboratorio) y, cuando se confirma, en `/panel`. |
| **Referencia técnica** | `app/cerebro/`, migraciones 085–090. |

### Término: Hecho citado

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `HechoCitado` (`clave`, `valor`, `estado`, `tipo`, `evidencia`) |
| **Nombre para el usuario** | Dato con su frase |
| **Qué significa** | Un dato acompañado de la frase exacta que lo sostiene, el instante del audio y quién lo dijo. |
| **Para qué existe** | Impedir que el sistema invente un precio, un teléfono o un nombre. |
| **Quién lo utiliza** | El sistema, para decidir; Julio, para auditar. |
| **Qué lo activa** | El modelo propone hechos a partir del texto; el backend comprueba que la cita exista en el texto normalizado. |
| **Qué sucede después** | Si la cita no existe, el hecho se descarta y queda una nota. Si existe, pasa al compilador. |
| **Qué NO significa** | Una cita correcta no garantiza la intención (ver «dato tentativo» y «negación»). |
| **Ejemplo** | «nos van a hacer una transferencia de 27.000 USD» sostiene `pago.monto = 27000`. |
| **Dónde se encuentra** | Tabla de hechos del laboratorio, con su cita. |
| **Referencia técnica** | `app/cerebro/hechos.py`, `cerebro_extracciones.sobre_json`. |

### Término: Borrador

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `cerebro_borradores`, `borrador_id`, `version` |
| **Nombre para el usuario** | Propuesta |
| **Qué significa** | La lista numerada de acciones y preguntas que el sistema propone antes de escribir nada. |
| **Para qué existe** | Separar «entender» de «hacer»; el humano aprueba la propuesta. |
| **Quién lo utiliza** | Julio y secretaría, para revisar y confirmar. |
| **Qué lo activa** | Un dictado interpretado. |
| **Qué sucede después** | Si se confirma, se ejecutan sus acciones. Si se corrige, nace una versión nueva. |
| **Qué NO significa** | No es una acción hecha: es una propuesta. Nada está escrito todavía. |
| **Ejemplo** | «1. Crear cliente · 2. Crear cotización · 3. Recordatorio». |
| **Dónde se encuentra** | `/panel/cerebro`, panel de resultado. |
| **Referencia técnica** | `cerebro_borradores`, `/api/v1/cerebro/borradores/{id}`. |

### Término: Compilador

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `app/cerebro/compilador.py` |
| **Nombre para el usuario** | Las reglas del Cerebro |
| **Qué significa** | La parte que decide, con reglas fijas, qué acciones se pueden proponer y qué preguntas bloquean lo que falta. |
| **Para qué existe** | Que la IA no decida dinero, estados ni permisos; que el resultado sea predecible y auditable. |
| **Quién lo utiliza** | El sistema. |
| **Qué lo activa** | Un conjunto de hechos verificados. |
| **Qué sucede después** | Devuelve acciones, preguntas y un estado; no escribe en la base. |
| **Qué NO significa** | No es el modelo de lenguaje: no «opina», aplica reglas. |
| **Ejemplo** | Si falta la dirección de la obra, no cotiza: pregunta. |
| **Dónde se encuentra** | Interno; su efecto se ve en el borrador. |
| **Referencia técnica** | `compilar()`, `ROLES_ACCIONES`, `_guarda de dinero`. |

### Término: Encargo (asunto del dictado)

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `encargo` en `cerebro_borradores.encargos_json`, `cerebro_ejecuciones` y `cerebro_correcciones` |
| **Nombre para el usuario** | Encargo |
| **Qué significa** | Cada instrucción independiente dentro de un mismo dictado. Un audio con «primero… segundo… tercero…» son tres encargos, cada uno con sus datos, sus preguntas y su estado. |
| **Para qué existe** | Que un asunto no contamine a otro: antes, «secretaría» de un encargo convertía el recordatorio externo de otro en tarea interna, y dos mensajes se pisaban. |
| **Quién lo utiliza** | Julio y secretaría al revisar la propuesta. |
| **Qué lo activa** | El extractor numera cada instrucción independiente (cambia de asunto, destinatario o acción) aunque no haya ordinales. Si no las separó y el dictado trae varias, el compilador pregunta antes de proponer. Los ordinales («primero, segundo») siguen siendo el respaldo determinístico. |
| **Qué sucede después** | Cada encargo se compila con su propio texto. Se puede corregir, cancelar o confirmar uno sin tocar los demás. |
| **Qué NO significa** | No es un hilo de conversación ni un expediente: es un asunto dentro de un dictado. |
| **Ejemplo** | «Tres cosas: revisar medidas, recordatorio a Mauricio, revisar despachos» → encargos 1, 2 y 3. |
| **Dónde se encuentra** | Bloque **Encargos del dictado** del laboratorio. |
| **Referencia técnica** | `app/cerebro/encargos.py`, migración 092. |

### Término: Cancelación de un encargo

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `cerebro_encargos_decisiones` (`CANCELADO`) |
| **Nombre para el usuario** | Encargo cancelado |
| **Qué significa** | Julio decide no ejecutar ese asunto. No es lo mismo que revocar el dictado: los otros encargos siguen vigentes. |
| **Para qué existe** | Cancelar una propuesta todavía no ejecutada sin perder el resto del trabajo, con motivo y autor. |
| **Quién lo utiliza** | Julio y secretaría, desde el laboratorio. |
| **Qué lo activa** | El botón **Cancelar encargo** (o `POST /borradores/{id}/encargos/{n}/cancelar`). |
| **Qué sucede después** | Se registra la decisión (append-only). Confirmar una acción de ese encargo responde `ENCARGO_CANCELADO`. |
| **Qué NO significa** | No cancela los demás encargos ni el dictado. Si el encargo ya generó un recordatorio **PENDIENTE**, se cancela ese recordatorio; si ya se **ENVIÓ**, no se puede cancelar y se avisa (`ENCARGO_YA_ENVIADO`). |
| **Ejemplo** | Cancelar el recordatorio a Mauricio deja intactas la revisión de medidas y la de despachos. |
| **Dónde se encuentra** | Laboratorio, lista de encargos. |
| **Referencia técnica** | `router.cancelar_encargo`, `recordatorios.cancelar`. |

### Término: Duda asociada al dato

| Campo | Contenido |
|---|---|
| **Nombre técnico** | estado `TENTATIVO` acotado por cercanía (`_ajustar_incertidumbre`) |
| **Nombre para el usuario** | Sin confirmar |
| **Qué significa** | Cuando Julio duda («creo», «me parece», «más o menos»), la duda se ata al dato más cercano, no a la frase completa. «Creo que eran treinta metros de hormigón de 240» deja el volumen sin confirmar y la resistencia como dato firme. |
| **Para qué existe** | No convertir un dato firme en pregunta redundante ni tratar una aproximación como definitiva. |
| **Quién lo utiliza** | El sistema al interpretar; Julio lo ve en el resumen y en la ficha. |
| **Qué lo activa** | Una marca de duda en el dictado; se asigna al hecho cuya cita está más cerca y se quita de los demás. Si la duda está antes («creo que…»), se aplica a lo que sigue. |
| **Qué sucede después** | Solo el dato dudoso se pregunta y se muestra «sin confirmar»; los demás se usan con normalidad. |
| **Qué NO significa** | No es un error del audio ni una invalidación del dato: es una confirmación pendiente de ese dato concreto. |
| **Ejemplo** | «El colegio Central, creo que eran 30 m³ de 240» → pregunta por los m³; 240, el cliente y la obra no se preguntan por esa duda. |
| **Dónde se encuentra** | Resumen «Lo que entendí», tabla de hechos y ficha de la tarea. |
| **Referencia técnica** | `extractor._ajustar_incertidumbre`, `hechos.es_tentativo`. |

### Término: Condición conservada

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `cerebro_borradores.condiciones_json`, claves `entrega.plazo`, `entrega.contra_pago`, `expediente.completar` |
| **Nombre para el usuario** | Condición conservada |
| **Qué significa** | Una condición o un encargo que Julio dictó y que no cabe dentro de una acción (por ejemplo, un plazo, «contra entrega del pago» o «hay que añadir ese expediente»). Se guarda con la frase exacta que la sostiene. |
| **Para qué existe** | Que una instrucción no desaparezca porque todavía no existe un ejecutor para ella. Antes, si la cotización no se podía armar (faltaba la dirección de obra), el plazo se perdía con ella. |
| **Quién lo utiliza** | Julio y secretaría, al revisar la propuesta. |
| **Qué lo activa** | Un dictado con condiciones. Las detecta el compilador con reglas fijas sobre el texto, aunque el modelo no las haya extraído. |
| **Qué sucede después** | Se muestran en el bloque **Condiciones y encargos conservados** y en el resumen «Lo que entendí», con la cita. El encargo al expediente además crea una tarea interna para secretaría. |
| **Qué NO significa** | No autoriza nada: no despacha, no condiciona el precio ni aprueba crédito. No afirma que los documentos ya llegaron. |
| **Ejemplo** | «Nos han dado un plazo de 2 meses» → «Plazo de entrega: 2 meses. Falta precisar desde cuándo se cuenta». |
| **Dónde se encuentra** | `/panel/cerebro`, bloque de condiciones, y resumen «Lo que entendí». |
| **Referencia técnica** | `compilador._condiciones()`, migración 091. |

### Término: Mensaje autorizado del recordatorio

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `mensaje_por_confirmar`, `mensaje_final`, `programado_inferido` |
| **Nombre para el usuario** | Mensaje y momento autorizados |
| **Qué significa** | La diferencia entre lo que Julio dictó (la instrucción), lo que el sistema propone y el texto que finalmente recibe la persona. Si lo dictado describe el encargo («el recordatorio del pago que tiene que hacernos»), el sistema no lo envía: pide el mensaje exacto. |
| **Para qué existe** | Que un recordatorio no salga con una frase interna que el destinatario no entendería, y que un envío inmediato no se dé por supuesto. |
| **Quién lo utiliza** | Julio y secretaría, en el laboratorio y en el panel. |
| **Qué lo activa** | El compilador marca `mensaje_por_confirmar` cuando la frase no es un mensaje dirigido a la persona, y `programado_inferido` cuando el dictado no dio hora. |
| **Qué sucede después** | Al confirmar, el sistema exige el texto y la aceptación del envío inmediato. Sin ellos responde `MENSAJE_POR_CONFIRMAR` o `CONFIRMAR_ENVIO_INMEDIATO` y no programa nada. |
| **Qué NO significa** | No es redacción automática: el texto lo escribe una persona. La instrucción original se conserva como constancia. |
| **Ejemplo** | «Hay que pasarle el recordatorio del pago» → pide el texto; «Dile: ingeniero, le recuerdo el anticipo» → se puede enviar tal cual. |
| **Dónde se encuentra** | Botón **Confirmar y programar** del laboratorio y de la ficha. |
| **Referencia técnica** | `compilador.mensaje_es_final()`, `router.validar_confirmacion_recordatorio()`. |

### Término: Ingreso sin confirmar

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `pago.recibido` con estado `INFERIDO` |
| **Nombre para el usuario** | Sin ingreso confirmado |
| **Qué significa** | El dictado habla de un pago que todavía no consta, pero no declara expresamente que no se haya recibido. Se conserva como referencia, no como estado financiero. |
| **Para qué existe** | Distinguir «el cliente no ha pagado» (afirmación) de «no tenemos confirmación del ingreso» (duda). |
| **Quién lo utiliza** | Julio, secretaría y contadora al leer el resumen. |
| **Qué lo activa** | El extractor marca el hecho como inferido si la cita no contiene una negación explícita («no ha pagado», «todavía no», «queda pendiente»). |
| **Qué sucede después** | No se registra ningún abono; el resumen dice «sin ingreso confirmado». Si el dictado lo declara, dice «que todavía no entra». |
| **Qué NO significa** | No es un pago perdido ni una deuda reconocida: es una verificación pendiente. |
| **Ejemplo** | «El recordatorio del pago que tiene que hacernos» → «un pago de 17000 USD (sin ingreso confirmado)». |
| **Dónde se encuentra** | Resumen «Lo que entendí» y notas del verificador. |
| **Referencia técnica** | `extractor._degradar_pago_no_declarado()`, `revision.resumen_legible()`. |

### Término: Dato sin confirmar (`TENTATIVO`)

| Campo | Contenido |
|---|---|
| **Nombre técnico** | estado `TENTATIVO` |
| **Nombre para el usuario** | Sin confirmar |
| **Qué significa** | El hablante dudó o aproximó («300 y pico», «o el sábado»). El dato se conserva como dicho, pero no se usa para decidir. |
| **Para qué existe** | No convertir una aproximación en un volumen, una fecha o un monto exactos. |
| **Quién lo utiliza** | El sistema; Julio lo ve en el resumen y en la ficha. |
| **Qué lo activa** | El modelo marca el hecho como tentativo o el texto usa expresiones de duda. |
| **Qué sucede después** | El resumen dice «sin confirmar», la acción que lo necesita no se arma y se pregunta citando la frase. |
| **Qué NO significa** | No es un error ni un dato descartado: es una referencia pendiente. |
| **Ejemplo** | «Creo que eran 300 y pico» → no se cotiza; se pregunta «Dijiste “300 y pico”. ¿Cuántos m³ exactos?». |
| **Dónde se encuentra** | Resumen «Lo que entendí» y ficha de la tarea. |
| **Referencia técnica** | `hechos.py` (`es_tentativo`), `revision.py`, `compilador._dicho_tentativo`. |

### Término: Corrección versionada

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `cerebro_correcciones`, `SUPERADO_POR_CORRECCION` |
| **Nombre para el usuario** | Existe una versión corregida |
| **Qué significa** | Cuando una persona arregla un dato, se crea una versión nueva del borrador y la anterior queda marcada como superada. |
| **Para qué existe** | Auditoría: saber qué se entendió, qué se corrigió y quién lo hizo, sin borrar el pasado. |
| **Quién lo utiliza** | Julio y secretaría, con el botón **Corregir**. |
| **Qué lo activa** | Una corrección desde el panel o la API. |
| **Qué sucede después** | El borrador pasa a versión +1; las correcciones anteriores se reaplican; la anterior no se puede confirmar. |
| **Qué NO significa** | No es un «deshacer»: la versión antigua queda guardada, no se elimina. |
| **Ejemplo** | «Díaz Sur» → «Dualsur»; el borrador v1 queda superado y v2 es el vigente. |
| **Dónde se encuentra** | Botón **Corregir** en cada hecho. |
| **Referencia técnica** | `revision.py`, `POST /borradores/{id}/corregir`. |

### Término: Vocabulario aprendido y retiro

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `v_cerebro_vocabulario`, `cerebro_vocabulario_retiros` |
| **Nombre para el usuario** | Lo que el Cerebro ya aprendió |
| **Qué significa** | Pares de «lo que se transcribió» → «lo que la persona quiso decir» que se usan como pista en la siguiente interpretación. |
| **Para qué existe** | Reducir correcciones repetidas sin reentrenar ningún modelo. |
| **Quién lo utiliza** | El sistema al interpretar; Julio al retirar un par equivocado. |
| **Qué lo activa** | Una corrección confirmada. |
| **Qué sucede después** | La pista se incluye en el prompt; si el par estaba mal, se retira con un motivo y deja de usarse. |
| **Qué NO significa** | No es una regla universal: es una pista. No modifica montos ni descuentos por sí sola. |
| **Ejemplo** | Tras corregir «Díaz Sur» → «Dualsur», el dictado siguiente ya devuelve «Dualsur». |
| **Dónde se encuentra** | Interno; el efecto se ve en la interpretación. |
| **Referencia técnica** | migración 087 y 090, `_vocabulario()`. |

### Término: Negación y revocación

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `_condicion_negada`, `dictado_revocado` |
| **Nombre para el usuario** | «Dijiste que no» |
| **Qué significa** | El sistema distingue negar un dato («no le hagan todavía el descuento») de cancelar toda la orden («mejor no hagas nada»). Las marcas se leen como **palabras completas**: «mejor nos abastecemos» no es «mejor no». La revocación se aplica al encargo donde aparece; solo «no hagas nada» corta el dictado completo. |
| **Para qué existe** | Que una cita verdadera no se ejecute contra la intención del hablante. |
| **Quién lo utiliza** | El sistema. |
| **Qué lo activa** | Frases de negación o de revocación en el dictado. |
| **Qué sucede después** | Si se niega un dato, ese dato no se aplica y queda una nota. Si se revoca la orden, ese encargo no propone acciones; los demás siguen. Si la revocación es total, no se propone nada. |
| **Qué NO significa** | No es «el modelo se equivocó»: es una guarda de seguridad sobre el texto. |
| **Ejemplo** | «No, mejor no hagas nada todavía» → borrador sin acciones. «Mejor nos abastecemos ahí» → no revoca: es una frase del relato. |
| **Dónde se encuentra** | Interno; se refleja en el resumen y en el borrador. |
| **Referencia técnica** | `compilador._condicion_negada`, `dictado_revocado`, `revocacion_global`. |

### Término: Router conversacional (laboratorio)

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `experiments/router_horminor/`, versión `router-1.7` |
| **Nombre para el usuario** | El asistente de Julio (prototipo) |
| **Qué significa** | La pieza que escucha un dictado, lo separa en encargos, propone responsable, pide aclaraciones y entrega un plan para confirmar. **Solo existe en el laboratorio.** |
| **Para qué existe** | Probar, sin tocar el CRM ni conectar Gato, si el Cerebro sirve como asistente de dirección: útil, corregible y comprensible. |
| **Quién lo utiliza** | El equipo técnico, para diagnosticar. Julio solo en pruebas. |
| **Qué lo activa** | Un dictado escrito en `http://localhost:8055`. |
| **Qué sucede después** | Devuelve un borrador con encargos, preguntas y un resumen natural. Nada se ejecuta. |
| **Qué NO significa** | No está conectado al CRM, no crea clientes, tareas ni cotizaciones, no envía mensajes y no autoriza despachos. `/panel/cerebro` no lo ejecuta. |
| **Ejemplo** | «Que secretaría revise el pago y el jefe de planta prepare el despacho, pero no manden nada hasta confirmar el anticipo» → dos encargos, uno condicionado, y la condición conservada. |
| **Dónde se encuentra** | Laboratorio interno `:8055`; no es una pantalla del producto. |
| **Referencia técnica** | `docs/ROUTER_CONVERSACIONAL_CIERRE.md`, `experiments/router_horminor/`. |

### Término: Corrección registrada

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `correccion.py`, `errores.py`, `evidencias/errores.jsonl` |
| **Nombre para el usuario** | Corrección |
| **Qué significa** | Un cambio que Julio pide en lenguaje natural sobre un borrador ya propuesto, con el antes y el después guardados. |
| **Para qué existe** | Que el sistema se equivoque de forma corregible y que cada error deje rastro para mejorar después. |
| **Quién lo utiliza** | Julio, desde la caja de respuesta; el equipo, al revisar la traza. |
| **Qué lo activa** | Una frase como «no es Díaz Sur, es DIALSUR» o «cancela el tercer encargo». |
| **Qué sucede después** | Nace una versión nueva del borrador y se agrega una entrada append-only con el mensaje, los campos cambiados y las versiones. |
| **Qué NO significa** | No reescribe el pasado ni borra la versión anterior. Tampoco ejecuta el cambio en el CRM. |
| **Ejemplo** | «Notifícales a los dos» → el destinatario pasa de una persona a dos y el resto del borrador se conserva. |
| **Dónde se encuentra** | Laboratorio, caja de respuesta e historial de correcciones. |
| **Referencia técnica** | `correccion._correccion_directa`, `errores.registrar`. |

### Término: Aclaración respondible

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `_aclaraciones`, `_aclaracion_directa`, tipo `ACLARACION` |
| **Nombre para el usuario** | Duda que se responde |
| **Qué significa** | Una duda del dictado convertida en pregunta con opciones, que Julio responde en un solo mensaje. |
| **Para qué existe** | No presentar como confirmado lo que no se sabe, y no obligar a Julio a responder campo por campo. |
| **Quién lo utiliza** | Julio, al responder; el sistema, al actualizar el borrador. |
| **Qué lo activa** | Conflictos detectados: dos volúmenes, dos resistencias, autoridad dudosa, identidad del proyecto o anticipo sin confirmar. |
| **Qué sucede después** | Se actualizan los datos, se retiran las preguntas resueltas y se registra una `ACLARACION` con su antes/después. |
| **Qué NO significa** | No es una pregunta abierta ni una nota: es una decisión pendiente con opciones concretas. |
| **Ejemplo** | «¿Qué volumen confirmamos: 36, 40 o 42 m³?» → Julio responde «42» y la duda desaparece. |
| **Dónde se encuentra** | Resumen del laboratorio y bloque de preguntas. |
| **Referencia técnica** | `router._aclaraciones`, `correccion._aclaracion_directa`. |

### Término: Encargo sugerido

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `responsable_sugerido` |
| **Nombre para el usuario** | Responsable propuesto |
| **Qué significa** | Cuando el dictado no nombra un área, el sistema propone jefe de planta o secretaría según el tipo de trabajo y lo marca como sugerencia. |
| **Para qué existe** | No devolverle a Julio la decisión de a quién asignar, sin ocultar que fue una propuesta del sistema. |
| **Quién lo utiliza** | Julio, al revisar; el responsable, al recibir. |
| **Qué lo activa** | Un encargo sin área explícita. |
| **Qué sucede después** | Julio lo acepta o lo corrige con una frase. |
| **Qué NO significa** | No es una asignación definitiva ni una orden ejecutada. |
| **Ejemplo** | «Revisar el acceso por el puente» → jefe de planta, marcado como sugerido. |
| **Dónde se encuentra** | Resumen y lista de encargos del laboratorio. |
| **Referencia técnica** | `router._asignar_por_defecto`. |

---

## 5. Capítulo 2 — Tareas internas y su ciclo

### Término: Aviso dejado (`NOTIFICADA`)

| Campo | Contenido |
|---|---|
| **Nombre técnico** | estado `NOTIFICADA`, `notificada_en` |
| **Nombre para el usuario** | Aviso dejado |
| **Qué significa** | El sistema dejó la tarea en el panel y desde ese momento corre el reloj. |
| **Para qué existe** | Medir la respuesta real desde que la instrucción llegó al equipo. |
| **Quién lo utiliza** | El sistema al confirmar la tarea; secretaría lo ve. |
| **Qué lo activa** | La confirmación de una acción `crear_tarea_interna`. |
| **Qué sucede después** | La tarea aparece en la franja, la campanita y el diálogo; queda `NOTIFICADA`. |
| **Qué NO significa** | No significa que alguien la haya leído. Por eso existen «consultada» y «recepción confirmada». |
| **Ejemplo** | Julio confirma una tarea; aparece en el panel con su hora. |
| **Dónde se encuentra** | `/panel`, franja superior y campanita. |
| **Referencia técnica** | `cerebro_tareas_internas.notificada_en`. |

### Término: Tarea consultada (`VISTA`)

| Campo | Contenido |
|---|---|
| **Nombre técnico** | evento `VISTA`, `vista_en`, `vista_por` |
| **Nombre para el usuario** | Tarea consultada |
| **Qué significa** | Una persona abrió el detalle de la tarea. |
| **Para qué existe** | Saber si el aviso llegó a alguien, sin confundirlo con haberlo aceptado. |
| **Quién lo utiliza** | Secretaría. |
| **Qué lo activa** | El botón **Ver la tarea**. |
| **Qué sucede después** | Se registra quién y cuándo; el estado de la tarea no cambia. |
| **Qué NO significa** | No es acuse de recibo ni inicio del trabajo. |
| **Ejemplo** | La secretaria abre la ficha para leer la instrucción completa. |
| **Dónde se encuentra** | Botón **Ver la tarea**. |
| **Referencia técnica** | evento `VISTA`, `POST /tareas-internas/{id}/vista`. |

### Término: Recepción confirmada (`ACUSADA`)

| Campo | Contenido |
|---|---|
| **Nombre técnico** | evento `ACUSADA`, `acusada_en`, `acusada_por` |
| **Nombre para el usuario** | Recepción confirmada |
| **Qué significa** | La persona encargada confirmó que recibió la tarea y conoce su contenido. |
| **Para qué existe** | Que Julio sepa que la instrucción llegó al responsable, sin obligarlo a preguntar. |
| **Quién lo utiliza** | Secretaría u otro responsable asignado. |
| **Qué lo activa** | El botón **Confirmar que recibí la tarea** (no pide nota). |
| **Qué sucede después** | Se registra el evento; la tarea **sigue** en `NOTIFICADA` hasta que se resuelva. |
| **Qué NO significa** | No significa que el trabajo esté hecho ni que se haya revisado el contenido. |
| **Ejemplo** | Julio pide revisar una transferencia; secretaría confirma recepción; la tarea sigue pendiente. |
| **Dónde se encuentra** | Botón **Confirmar que recibí la tarea**. |
| **Referencia técnica** | evento `ACUSADA`, `POST /tareas-internas/{id}/acusar`. |

### Término: Trabajo realizado (`RESUELTA`)

| Campo | Contenido |
|---|---|
| **Nombre técnico** | estado `RESUELTA`, `resuelta_en`, `resuelta_por`, `resolucion_nota` |
| **Nombre para el usuario** | Trabajo realizado |
| **Qué significa** | La persona declara que hizo lo que se le pidió, con una nota de qué hizo. |
| **Para qué existe** | Cerrar el trabajo con evidencia mínima de lo realizado. |
| **Quién lo utiliza** | Secretaría u otro responsable. |
| **Qué lo activa** | El botón **Trabajo realizado**, que pide una nota. |
| **Qué sucede después** | La tarea queda `RESUELTA`; si faltaba, se completa la recepción confirmada; luego se puede registrar el resultado. |
| **Qué NO significa** | No es el registro formal: falta la constancia con metadatos. |
| **Ejemplo** | «Se revisó la hoja de despachos y se pasó el resumen por el chat interno». |
| **Dónde se encuentra** | Botón **Trabajo realizado**. |
| **Referencia técnica** | `POST /tareas-internas/{id}/resolver` con `RESUELTA`. |

### Término: Cierre con justificación (`JUSTIFICADA`)

| Campo | Contenido |
|---|---|
| **Nombre técnico** | estado `JUSTIFICADA`, `resolucion_nota` |
| **Nombre para el usuario** | Cierre con justificación |
| **Qué significa** | La tarea no se hizo porque no hacía falta, no se pudo o cambió la situación; se explica por qué. |
| **Para qué existe** | Que una tarea no quede abierta para siempre y que la razón quede registrada. |
| **Quién lo utiliza** | Secretaría o el responsable. |
| **Qué lo activa** | El botón **Cerrar con justificación**, que pide el motivo. |
| **Qué sucede después** | Queda cerrada como `JUSTIFICADA`; se puede registrar el cierre. |
| **Qué NO significa** | No es lo mismo que «trabajo realizado»: no se hizo, y se dice por qué. |
| **Ejemplo** | «El cliente canceló el despacho; no había nada que revisar». |
| **Dónde se encuentra** | Botón **Cerrar con justificación**. |
| **Referencia técnica** | `POST /tareas-internas/{id}/resolver` con `JUSTIFICADA`. |

### Término: Resultado registrado (`REGISTRADA`)

| Campo | Contenido |
|---|---|
| **Nombre técnico** | estado `REGISTRADA`, `registrada_en`, `registrada_por`, `metadatos` |
| **Nombre para el usuario** | Resultado registrado |
| **Qué significa** | El cierre quedó con constancia formal: referencia, comprobante o comentario. |
| **Para qué existe** | Poder demostrar qué se hizo y con qué respaldo. |
| **Quién lo utiliza** | Secretaría o un supervisor. |
| **Qué lo activa** | El botón **Registrar resultado**, que pide la referencia o el comprobante. |
| **Qué sucede después** | La tarea queda `REGISTRADA` y sale de la lista de pendientes. |
| **Qué NO significa** | No es «confirmar recepción» ni «declarar que se hizo»: es dejar la constancia. |
| **Ejemplo** | «Resumen de despachos archivado; referencia despachos-semana-45». |
| **Dónde se encuentra** | Botón **Registrar resultado**. |
| **Referencia técnica** | `POST /tareas-internas/{id}/registrar`. |

### Término: Elevada al supervisor (`ESCALADA`)

| Campo | Contenido |
|---|---|
| **Nombre técnico** | evento `ESCALADA`, `escalada_en`, `escalada_por`, prioridad `URGENTE` |
| **Nombre para el usuario** | Elevada al supervisor |
| **Qué significa** | Una tarea vencida y sin recepción confirmada se puso en conocimiento de un responsable superior. |
| **Para qué existe** | Que lo urgente no se pierda por falta de atención. |
| **Quién lo utiliza** | Julio (SUPERADMIN). |
| **Qué lo activa** | El botón **Elevar al supervisor**, con un motivo; solo aparece si la tarea venció o es urgente. |
| **Qué sucede después** | Se registra el motivo y la tarea pasa a prioridad urgente; no se reasigna ni se cierra sola. |
| **Qué NO significa** | No es un castigo ni una sanción: es un aviso para que alguien intervenga. |
| **Ejemplo** | Una revisión de despachos venció sin confirmación; Julio la eleva para que se atienda. |
| **Dónde se encuentra** | Botón **Elevar al supervisor** (solo SUPERADMIN). |
| **Referencia técnica** | `POST /tareas-internas/{id}/escalar`; vista `requiere_escalamiento`. |

### Término: Prioridad y plazo

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `prioridad` (`NORMAL`/`URGENTE`), `plazo_en`, `vencida` |
| **Nombre para el usuario** | Urgente / Normal y fecha límite |
| **Qué significa** | Cuánto apura la tarea y hasta cuándo se espera. |
| **Para qué existe** | Ordenar el trabajo y detectar demoras. |
| **Quién lo utiliza** | Todo el equipo. |
| **Qué lo activa** | El dictado («urgente», «inmediatamente», «cuanto antes») o el valor por defecto. |
| **Qué sucede después** | Urgente = 2 horas; normal = 24 horas; si vence, se marca **vencida** y la franja se pone roja. |
| **Qué NO significa** | No es una multa ni una evaluación de desempeño; es una señal operativa. |
| **Ejemplo** | «Verifica si entró la transferencia, urgente» → plazo de 2 horas. |
| **Dónde se encuentra** | Diálogo de tareas, chips y franja. |
| **Referencia técnica** | `internas.PLAZO_*`, vista `v_cerebro_tareas_internas`. |

### Término: Ficha de la tarea

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `metadatos.ficha` (`tipo`, `accion`, `monto_usd`, `datos_faltantes`, `resultado_esperado`) |
| **Nombre para el usuario** | Qué hay que hacer |
| **Qué significa** | Un resumen ordenado de la instrucción: tipo, cliente, monto de referencia, qué falta y qué se espera. |
| **Para qué existe** | Que secretaría no tenga que escuchar el audio para saber qué hacer. |
| **Quién lo utiliza** | Secretaría. |
| **Qué lo activa** | La creación de una tarea interna, a partir de los hechos. |
| **Qué sucede después** | Se muestra al abrir el detalle; no reemplaza la instrucción original. |
| **Qué NO significa** | No es una redacción nueva ni un formulario obligatorio: si faltan datos, quedan vacíos. |
| **Ejemplo** | Tipo «Verificación», importe «USD 27000», resultado «Informar si se confirmó o no». |
| **Dónde se encuentra** | Botón **Ver la tarea**. |
| **Referencia técnica** | `compilador._ficha_tarea`. |

---

## 6. Capítulo 3 — Dinero, canales y automatizaciones

### Término: Doble confirmación

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `requiere_doble_confirmacion` |
| **Nombre para el usuario** | Confirmación doble |
| **Qué significa** | Las acciones que tocan caja o cartera se confirman dos veces antes de ejecutarse. |
| **Para qué existe** | Que un error de interpretación no mueva dinero. |
| **Quién lo utiliza** | Julio y contabilidad. |
| **Qué lo activa** | Abono, traslado de caja u otra acción de dinero. |
| **Qué sucede después** | La acción queda marcada; se ejecuta solo con la segunda confirmación. |
| **Qué NO significa** | No es una desconfianza al empleado: es un control contable. |
| **Ejemplo** | Registrar un abono de 27.000 USD pide dos confirmaciones. |
| **Dónde se encuentra** | Borrador, acciones de dinero. |
| **Referencia técnica** | `AccionPropuesta.requiere_doble_confirmacion`. |

### Término: Guarda de «el dinero ya entró»

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `_dinero_ya_entro`, `_condicion_negada` |
| **Nombre para el usuario** | ¿Ya entró el dinero? |
| **Qué significa** | El sistema no registra un abono si el dictado no dice, en pasado, que el dinero entró. |
| **Para qué existe** | Que «nos van a transferir» no se convierta en un abono hecho. |
| **Quién lo utiliza** | El sistema; Julio responde la pregunta. |
| **Qué lo activa** | Un monto mencionado sin frase de pago recibido. |
| **Qué sucede después** | Se pregunta «¿Los 27.000 USD ya entraron?» y no se propone el abono hasta saberlo. |
| **Qué NO significa** | No significa que el sistema dude del cliente: duda de su propia lectura. |
| **Ejemplo** | «Nos van a hacer una transferencia de 27.000» → pregunta; no registra. |
| **Dónde se encuentra** | Preguntas del borrador. |
| **Referencia técnica** | `app/cerebro/dinero.py`. |

### Término: Recordatorio de WhatsApp y despachador

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `gato_recordatorios`, despachador de recordatorios |
| **Nombre para el usuario** | Recordatorio programado |
| **Qué significa** | Un mensaje a una persona, con texto, destinatario y hora, que el sistema envía cuando corresponde. |
| **Para qué existe** | Que un aviso no dependa de que alguien se acuerde. |
| **Quién lo utiliza** | Julio y secretaría. |
| **Qué lo activa** | Una acción `crear_tarea_recordatorio` confirmada **con mensaje autorizado y momento confirmado**. |
| **Qué sucede después** | Queda `PENDIENTE`; el despachador revisa la cola cada 20 segundos y lo envía a su hora; el estado pasa a `ENVIADO` o `FALLIDO`. |
| **Qué NO significa** | No es una tarea interna: se envía a un teléfono y no se resuelve en el panel. Tampoco se envía la frase dictada si esa frase describe el encargo en vez de ser el mensaje. |
| **Ejemplo** | «Recuérdale a Mauricio a las 18:00 que pase el comprobante». |
| **Dónde se encuentra** | Popout y campanita de `/panel`. |
| **Referencia técnica** | `app/asistente/recordatorios.py`, `cerebro_ejecuciones`, `validar_confirmacion_recordatorio()`. |

### Término: SANDBOX

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `sandbox_mode`, adaptadores de `app/sandbox.py` |
| **Nombre para el usuario** | Modo de prueba |
| **Qué significa** | El sistema funciona completo, pero los envíos y servicios externos se simulan; no sale nada real. |
| **Para qué existe** | Probar y capacitar sin mandar mensajes ni tocar cuentas reales. |
| **Quién lo utiliza** | El equipo y quien capacita. |
| **Qué lo activa** | La configuración del entorno (por defecto en local). |
| **Qué sucede después** | Los envíos se registran en una bandeja simulada; nada llega a un teléfono real. |
| **Qué NO significa** | No es «sin datos»: los datos de prueba son ficticios, pero el flujo es el real. |
| **Ejemplo** | Un recordatorio «enviado» en SANDBOX aparece en la bandeja simulada, no en WhatsApp. |
| **Dónde se encuentra** | Indicador «SANDBOX» en el panel. |
| **Referencia técnica** | `app/sandbox.py`, `system_settings.sandbox_mode`. |

### Término: Gato

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `app/asistente/`, `/api/v1/asistente/chat` |
| **Nombre para el usuario** | Gato |
| **Qué significa** | El asistente de consultas del CRM: responde preguntas de solo lectura sobre los datos y gestiona recordatorios por conversación. |
| **Para qué existe** | Consultar cifras y datos sin navegar el panel. |
| **Quién lo utiliza** | Julio, secretaría, administración. |
| **Qué lo activa** | Una pregunta en el chat. |
| **Qué sucede después** | Responde con datos reales y su fuente; no modifica el negocio. |
| **Qué NO significa** | No interpreta audios ni crea borradores: eso es el Cerebro. |
| **Ejemplo** | «¿Cuánto vendimos en El Coca?» → responde con la cifra y su fuente. |
| **Dónde se encuentra** | Widget de chat en `/panel`. |
| **Referencia técnica** | `app/asistente/`, catálogo de consultas. |

### Término: Idempotencia y clave externa

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `clave_externa`, `clave_idempotencia`, `repetido` |
| **Nombre para el usuario** | No se duplica |
| **Qué significa** | La misma instrucción, confirmada dos veces, no crea dos tareas ni dos mensajes. |
| **Para qué existe** | Evitar duplicados por reintentos, doble clic o mensajes repetidos. |
| **Quién lo utiliza** | El sistema. |
| **Qué lo activa** | Una clave única calculada a partir del borrador y la acción. |
| **Qué sucede después** | La segunda vez devuelve el resultado existente con `repetido: true`. |
| **Qué NO significa** | No garantiza por sí solo que un envío externo no salga dos veces si el proveedor no responde; eso requiere reconciliación. |
| **Ejemplo** | Confirmar dos veces la misma tarea devuelve la misma tarea, no otra. |
| **Dónde se encuentra** | Interno; el panel muestra «Ya estaba». |
| **Referencia técnica** | `gato_recordatorios.clave_idempotencia`, `cerebro_tareas_internas.clave_externa`. |

### Término: Retención de audio

| Campo | Contenido |
|---|---|
| **Nombre técnico** | `voz_ingestas`, `voz_transcripciones` |
| **Nombre para el usuario** | Audio guardado |
| **Qué significa** | El audio y su transcripción se conservan como evidencia de qué se dijo y qué se entendió. |
| **Para qué existe** | Auditar y corregir con la fuente original. |
| **Quién lo utiliza** | El sistema; Julio al revisar. |
| **Qué lo activa** | La ingesta de un audio. |
| **Qué sucede después** | Se guarda con su huella (hash), su transcripción y sus tiempos. |
| **Qué NO significa** | No es un «baúl de voces para entrenar»: no se usa para reentrenar el modelo. |
| **Ejemplo** | Un audio de prueba queda con su transcripción para revisar la corrección. |
| **Dónde se encuentra** | Interno; el laboratorio muestra la transcripción. |
| **Referencia técnica** | migración 085; consentimiento y plazo **pendientes** (LOPDP). |

---

## 7. Términos de apoyo (consulta rápida)

| Término técnico | Nombre visible | Qué es |
|---|---|---|
| `EXTRAIDO` | Dato extraído | el dictado lo afirma y la cita existe |
| `INFERIDO` | Deducido | el sistema lo completó; no resuelve identidad |
| `NO_DIJO` | No lo dijo | se habló del tema sin afirmar el dato |
| `INAUDIBLE_NO_ENTENDI` | No se entendió | el audio no permite sostenerlo |
| `CORREGIDO_POR_HUMANO` | Corregido por una persona | la persona es la autoridad del dato |
| `PENDIENTE_CONFIRMACION` | Listo para confirmar | falta solo el «sí» humano |
| `REQUIERE_ACLARACION` | Falta aclarar | hay preguntas concretas |
| `SIN_ACCIONES` | Sin acciones | consulta o dictado revocado; se guarda como constancia |
| `EJECUTADO` | Ejecutado | todas sus acciones se ejecutaron |
| `RECHAZADO` | Rechazado | un humano decidió no hacerlo |
| `cerebro_ejecuciones` | Ejecución | registro de una acción confirmada y su resultado |
| `cerebro_extracciones` | Extracción | lo que el modelo propuso para un dictado |
| `normalizador` | Normalizador | convierte el habla («27 mil», «0963-444-444») en datos |
| `whisper-large-v3` | Transcripción | servicio que convierte audio en texto |
| `informe semanal` | Informe de errores | documento para Abelito con correcciones y tareas |
| `bóveda de correcciones` | Memoria de correcciones | historial de lo que el sistema aprendió |
| `M1` | Módulo de WhatsApp | webhook, identidad, envío y multimedia |
| `Evolution API` | Proveedor de WhatsApp | conexión real con WhatsApp (hoy en SANDBOX) |

---

## 8. Nombres visibles recomendados

Revisión de qué representa cada nombre **antes** de cambiarlo en pantalla:

| Técnico | Tipo | Visible en pantalla | Por qué |
|---|---|---|---|
| `NOTIFICADA` | estado | Aviso dejado | describe el hecho: se dejó el aviso |
| `RESUELTA` | estado | Trabajo realizado | dice el resultado, no el trámite |
| `JUSTIFICADA` | estado | Cierre con justificación | deja claro que no se hizo |
| `REGISTRADA` | estado | Resultado registrado | cierra con constancia |
| `VISTA` | **evento** | Tarea consultada | no es un estado de la tarea |
| `ACUSADA` | **evento** | Recepción confirmada | evita el sentido de «culpa» |
| `ESCALADA` | **evento** | Elevada al supervisor | explica qué pasó |
| `TENTATIVO` | estado de hecho | Sin confirmar | evita «tentativo» en la conversación |
| `SUPERADO_POR_CORRECCION` | estado de borrador | Existe una versión corregida | no parece un error |
| `PENDIENTE_CONFIRMACION` | estado de borrador | Listo para confirmar | dice qué falta |
| `REQUIERE_ACLARACION` | estado de borrador | Falta aclarar | dice qué falta |
| `SIN_ACCIONES` | estado de borrador | Sin acciones | no parece una falla |

**Regla:** los nombres técnicos no cambian en la base ni en la API; cambian solo
las etiquetas visibles.

---

## 9. Preguntas frecuentes (respuestas basadas en lo que existe)

**¿Qué significa que una tarea esté «acusada»?**
Que la persona confirmó que **recibió** el encargo. No significa que lo haya
hecho ni que esté terminada. Se ve como «Recepción confirmada».

**¿Cuál es la diferencia entre resolver y registrar?**
Resolver declara **qué se hizo** (con una nota). Registrar deja la **constancia
formal** con referencia o comprobante. Una tarea puede estar resuelta y todavía
no registrada.

**¿Qué pasa si una tarea se vence?**
Se marca **vencida** y la franja del panel se pone roja. Si además no tiene
recepción confirmada, queda como **requiere escalamiento**; Julio puede
**elevarla al supervisor** con un motivo. Nada se cancela ni se cierra solo.

**¿Por qué el Cerebro me pregunta si una cifra es correcta?**
Porque el dato llegó como duda («300 y pico») o porque el audio no lo dice con
claridad. El sistema no convierte una aproximación en un número exacto: pregunta.

**¿Qué es el compilador y por qué no dejamos que la IA decida todo?**
Es el conjunto de reglas fijas que arma el borrador. La IA propone hechos con
cita; el compilador decide con reglas y el humano confirma. Así el dinero, los
permisos y los estados no dependen de una opinión del modelo.

**¿Qué hace Gato y qué hace el Cerebro?**
Gato **responde consultas** de solo lectura y gestiona recordatorios. El Cerebro
**interpreta dictados**, propone acciones y delega tareas. Comparten datos, no
funciones.

**¿El router conversacional ya está dentro del CRM?**
No. Existe solo en el laboratorio interno `:8055`, con la versión `router-1.7`.
No crea clientes, tareas ni cotizaciones, y no envía nada. `/panel/cerebro`
sigue usando el motor anterior.

**¿Qué pasa si el Cerebro se equivoca en un encargo?**
Julio se lo dice en lenguaje natural y el sistema cambia solo lo corregido,
dejando el resto intacto. El cambio se guarda con su antes y después para poder
revisarlo después. Esa es la vía de mejora: corregir, no rediseñar.

**¿Qué significa SANDBOX?**
Modo de prueba: el flujo es real, pero los envíos y servicios externos se
simulan. No sale ningún mensaje real ni se toca una cuenta bancaria.

**¿Cuál es el recorrido de un audio de Julio hasta que secretaría termina?**
Audio → transcripción → normalización → hechos con cita → borrador → «Lo que
entendí» → corrección (si hace falta) → confirmación → tarea o recordatorio →
aviso en el panel → la secretaría consulta, confirma recepción, hace el trabajo
o lo justifica y registra el resultado → Julio puede consultar qué pasó.

**¿El sistema puede explicar una función que todavía no existe?**
No. Este manual solo documenta lo implementado. Las funciones pendientes están
en «Todavía no existe».

**¿Qué se mide con los tiempos de una tarea?**
El tiempo **entre eventos** (avisada, consultada, recepción confirmada,
resuelta, registrada). No mide cuánto trabajó una persona.

---

## 10. Todavía no existe (para no prometerlo)

- Conversación por WhatsApp: corregir y confirmar por el mismo chat, y preguntar
  «¿qué pasó con lo de ayer?». **Contrato escrito, implementación pendiente.**
- Ejecutar `crear_cliente` y `crear_cotizacion_borrador` desde el Cerebro
  (hoy responden 501 a propósito).
- Guardar los contactos del cliente (`contacto.*`) en su ficha.
- Aprender significados («rebaja del cinco» = 5 %) y lugares («debajo del
  Cóndor»): hoy solo hay vocabulario de nombres y jerga.
- Bóveda de audios para entrenamiento: requiere consentimiento y retención
  (LOPDP), que aún no están decididos.
- Ayuda contextual dentro del CRM («¿qué significa este botón?»): este manual es
  la base, la función todavía no existe.
- **Gato usando al Cerebro**: hoy son piezas separadas; la conexión será
  controlada y no se hace todavía (`docs/CONTINUIDAD_CEREBRO.md`).
- **Gato consultando el Manual Vivo**: registrado como pendiente; no es motivo
  para conectar antes el Cerebro.
- **Flujo comercial externo de WhatsApp** con permisos limitados y transferencia
  a un humano: definido en la arquitectura, no implementado.
- El Cerebro como **módulo visible**: el laboratorio es de prueba; en producción
  la cara será Gato.
- **Router conversacional conectado al CRM**: existe solo en el laboratorio; no
  crea clientes, tareas, cotizaciones ni recordatorios.
- **Memoria entre dictados**: cada dictado es un borrador nuevo; mantener el
  hilo de «cancela el segundo» en otro audio es de otra fase.
- **Jev (TypeSafe AI)**: idea de backlog para clasificar o verificar intenciones,
  responsables, órdenes nuevas y malentendidos. No evaluada, sin fecha y sin
  integración.

---

## 11. Índice

### Por nombre técnico

`ACUSADA` §5 · `clave_externa` §6 · `condiciones_json` §4 ·
`cerebro_ejecuciones` §7 · `cerebro_encargos_decisiones` §4 ·
`encargo` §4 · `ESCALADA` §5 · `EXTRAIDO` §7 ·
`gato_recordatorios` §6 · `JUSTIFICADA` §5 · `mensaje_por_confirmar` §4 ·
`NOTIFICADA` §5 · `pago.recibido` (INFERIDO) §4 · `REGISTRADA` §5 ·
`REQUIERE_ACLARACION` §7 · `RESUELTA` §5 · `router-1.7` §3.5 ·
`SANDBOX` §6 · `SIN_ACCIONES` §7 ·
`SUPERADO_POR_CORRECCION` §4 · `TENTATIVO` §4 · `VISTA` §5.
### Por nombre visible

Aviso dejado §5 · Aclaración respondible §4 · Cancelación de un encargo §4 ·
Cierre con justificación §5 · Compilador §4 · Condición conservada §4 ·
Confirmación doble §6 · Corrección registrada §4 ·
Dato sin confirmar §4 · Duda asociada al dato §4 · Elevada al supervisor §5 ·
Encargo §4 · Encargo sugerido §4 · Ficha de la tarea §5 ·
Guarda de «el dinero ya entró» §6 ·
Gato §6 · Hecho citado §4 · Ingreso sin confirmar §4 ·
Mensaje autorizado del recordatorio §4 · Prioridad y plazo §5 ·
Recepción confirmada §5 · Recordatorio programado §6 · Resultado registrado §5 ·
Retención de audio §6 · Router conversacional §4 · Tarea consultada §5 ·
Trabajo realizado §5.

### Por sinónimo

«acuse» → Recepción confirmada §5 · «asistente» → Router conversacional §4 ·
«asunto» → Encargo §4 ·
«avisada» → Aviso dejado §5 · «cita» → Hecho citado §4 ·
«condición» → Condición conservada §4 · «corregir» → Corrección registrada §4 ·
«creo» → Duda asociada al dato §4 ·
«duda» → Dato sin confirmar §4 · «escalar» → Elevada al supervisor §5 ·
«expediente» → Condición conservada §4 · «marcar hecho» → Trabajo realizado §5 ·
«me parece» → Duda asociada al dato §4 ·
«no ha pagado» → Ingreso sin confirmar §4 · «plazo» → Condición conservada §4 ·
«pregunta» → Aclaración respondible §4 ·
«registrar» → Resultado registrado §5 · «responsable» → Encargo sugerido §4 ·
«revisada» → Tarea consultada §5 ·
«sin ordinales» → Encargo §4 · «tres cosas» → Encargo §4 ·
«vencida» → Prioridad y plazo §5.

---

## 12. Regla de mantenimiento

Toda función nueva o cambio de comportamiento de negocio **obliga** a:

1. Actualizar el término en este manual (o agregarlo).
2. Indicar: qué concepto se agregó o cambió, qué comportamiento cambió, qué
   usuarios se ven afectados, con qué componente técnico se relaciona y la
   fecha/versión.
3. Actualizar el índice y, si aplica, el mapa funcional.
4. No describir como existente algo que todavía no está implementado.

**No se considera terminada una funcionalidad de negocio si su explicación en
este manual está ausente o desactualizada.** La suite de pruebas incluye una
verificación de que este manual y la skill de consulta existan y apunten a él.

### Bitácora del manual

| Versión | Fecha | Cambio |
|---|---|---|
| v1 | 2026-11-15 | Manual inicial del Cerebro: mapa, 21 términos, índice, nombres visibles y regla de mantenimiento. |
| v1.1 | 2026-11-15 | Revocación completa del dictado (F) y negación de instrucciones citadas (L); etiquetas visibles en el panel y el laboratorio. |
| v1.2 | 2026-11-15 | Arquitectura futura Cerebro–Gato–módulos y separación de los flujos interno y externo (§3.4); sigue sin implementarse. |
| v1.3 | 2026-11-16 | Condición conservada, Mensaje autorizado del recordatorio e Ingreso sin confirmar (§4); índice actualizado. Conservación de instrucciones ante el dictado espontáneo del 2026-11-16. |
| v1.4 | 2026-11-16 | Encargo y Cancelación de un encargo (§4); un dictado con tres asuntos se administra por separado. Índice actualizado. |
| v1.5 | 2026-11-16 | Duda asociada al dato (§4); separación de encargos en lenguaje natural sin ordinales; etiquetas «Acciones ejecutadas» frente a «Trabajo realizado». |
| v1.6 | 2026-11-16 | Cierre de la fase del router conversacional (§3.5): Router conversacional, Corrección registrada, Aclaración respondible y Encargo sugerido (§4); límites del laboratorio frente al CRM; Jev en backlog. |
| v1.7 | 2026-11-16 | Negación y revocación: marcas como palabras completas y revocación por encargo; «mejor nos abastecemos» ya no revoca el dictado. |
