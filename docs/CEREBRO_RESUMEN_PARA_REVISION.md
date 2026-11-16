# El Cerebro de Horminor — resumen para revisión

> **Para qué sirve este documento.** Explica, sin código ni tecnicismos, qué hace
> el módulo **Cerebro**, cómo decide, qué guarda y qué no hace todavía. Sirve
> para leerlo con calma, revisarlo con Julio y decidir los puntos abiertos del
> final.
>
> **Fecha:** 2026-11-15 · **Estado:** fases 0–2 + incremento v2 (migración 090)
> construidos y verificados en local. **586 pruebas automatizadas en verde.**
> **Datos de ejemplo:** todos los nombres, teléfonos y montos que aparecen acá son
> **ficticios** (Díaz Sur/Dualsur, 0963444444, 0985454545, 0965555555, 27.000 USD).
>
> **Actualización v2 (2026-11-15).** Este documento se corrigió para distinguir
> retención de audio de "baúl de entrenamiento", separar aviso / vista / acuse,
> explicar los datos tentativos y aclarar que lo que se mide es **tiempo entre
> eventos**, no el trabajo de una persona. El detalle técnico de las brechas está
> en `docs/CEREBRO_MATRIZ_BRECHAS.md` y el contrato del canal en
> `docs/CONTRATO_WHATSAPP_CEREBRO.md`.

---

## 1. Qué es, en una frase

El Cerebro convierte **un dictado** —voz o texto— en un **borrador de acciones**
que Julio o la secretaría leen, corrigen y confirman; recién entonces el sistema
escribe algo en el negocio.

No es un chatbot. Es una **aduana**: el lenguaje entra por un lado, y del otro
salen solo datos sostenidos por el audio y acciones que un humano aprobó.

---

## 2. Los tres principios que no se negocian

1. **Cero datos inventados.** Si el audio no lo dice, el dato no existe: se
   marca `NO_DIJO`, se deja vacío o se **pregunta**. Nunca un valor "razonable".
2. **El LLM no calcula ni escribe.** El modelo solo propone datos **con cita**.
   La aritmética y las reglas las hace el backend; la escritura la autoriza un
   humano.
3. **Todo queda registrado.** El audio, la transcripción, lo que se entendió, lo
   que se corrigió y lo que se ejecutó se guardan como filas nuevas. Nada se
   reescribe por atrás.

---

## 3. El recorrido completo

```
AUDIO o TEXTO
   │
   ├─ 1. Normalización        "27 mil" → 27.000 · "0963-444-444" → un teléfono
   │
   ├─ 2. Hechos con cita      el modelo propone; el backend verifica que la
   │                          frase exista en el texto y la marca en el audio
   │
   ├─ 3. Compilador           reglas duras: qué acción se puede proponer
   │                          y qué pregunta bloquearla
   │
   ├─ 4. Borrador             acciones numeradas + preguntas + estado
   │
   ├─ 5. Lectura en voz alta  "Entendí: …" — lo que el sistema creyó oír
   │
   ├─ 6. Corrección           Julio arregla un dato; el borrador se rehace
   │                          como versión nueva (no se borra la anterior)
   │
   ├─ 7. Confirmación         un humano identificado aprueba acción por acción
   │
   └─ 8. Ejecución            recién acá se escribe (tarea, recordatorio, etc.)
```

Cada paso deja rastro. Si algo sale mal, se puede reconstruir **qué se dijo, qué
se entendió, quién lo cambió y cuándo**.

---

## 4. Paso por paso, en palabras

### 4.1 Voz

- El audio se guarda con su huella (hash) y se transcribe con **Groq/Whisper**
  (`whisper-large-v3`), en español de Ecuador.
- **Qué se guarda y para qué.** El audio y su transcripción se conservan como
  **evidencia**: permiten reconstruir qué se dijo y qué se entendió. No son un
  "baúl de voces para entrenar": no se usan para reentrenar el modelo. El plazo
  de retención y el consentimiento (LOPDP) están **pendientes de decisión**; hoy
  se guardan en la base local del piloto.
- La transcripción trae **palabras con tiempos**, y la confianza por palabra es
  una referencia, no una verdad calibrada.
- El **normalizador** es determinístico y es donde se arreglan las trampas del
  habla ecuatoriana:
  - «27 mil» → `27000`; «27 mil 500» → `27500`.
  - «0963-444-444» → un solo teléfono: `0963444444`.
  - «de 240» en hormigón → resistencia `FC-240`, **no** precio.
  - Una hora suelta («a las seis de la mañana») **no** es una fecha.

### 4.2 Hechos con cita

Un **hecho** no es un valor suelto. Es un dato + la **frase exacta** que lo
sostiene + el instante del audio + quién lo dijo.

Si el modelo propone «el cliente es Dualsur» y esa frase no está en el texto, el
hecho **se descarta** y queda una nota. El sistema prefiere no entender antes que
entender mal.

Esto es lo que impide que un modelo "alucine" un precio, un teléfono o un nombre.

**Pero una cita perfecta no garantiza la intención.** Si Julio dice «no le hagan
todavía el descuento del 13 %», la frase existe y la cifra es verdadera, aunque
la orden sea **no aplicarla**. Por eso el hecho lleva un **estado**:

| Estado | Qué significa |
|---|---|
| `EXTRAIDO` | el dictado lo afirma |
| `TENTATIVO` | el hablante dudó o aproximó («300 y pico», «o el sábado»). **No se usa para decidir**; se pregunta |
| `CORREGIDO_EN_AUDIO` | el hablante se corrigió en el mismo audio; vale el último valor |
| `NO_DIJO` | se habló del tema pero no se afirmó el dato |
| `INAUDIBLE_NO_ENTENDI` | no se entendió |

Además, una **guarda determinística** revisa la frase: si el dictado **niega o
condiciona** un descuento («no le hagan todavía», «primero tengo que revisar el
precio»), el descuento **no se aplica** aunque el modelo lo haya extraído con
cita; queda anotado «Descuento NO aplicado: el dictado pidió esperar».

Un dato tentativo **acompaña** a la tarea (aparece como «sin confirmar» en la
ficha y en el resumen), pero **nunca** se convierte en volumen, fecha o monto
definitivo.

### 4.3 Compilador

Es la parte **determinística** (reglas, no IA). Decide qué acción se puede
proponer y qué pregunta la bloquea. Ejemplos reales:

| Si el dictado dice… | El compilador… |
|---|---|
| «25 m³ de FC-210 para el sábado en La Joya» | propone cotización con volumen, resistencia, receta y fecha |
| «todo el hormigón es de 240» | usa `FC-240` del catálogo, **no** inventa precio |
| «hay que llevar la planta móvil» | lo anota como condición, sin cotizar transporte |
| «nos van a hacer una transferencia de 27.000» | **no** registra abono: pregunta si el dinero ya entró |
| «que revisen en secretaría cómo van los despachos» | crea una **tarea interna** con reloj (ver §8) |
| «envíale un recordatorio al 0965555555 a las 18:00» | propone recordatorio de WhatsApp a esa hora |

### 4.4 Borrador

El borrador es la propuesta, no la escritura. Tiene:

- **acciones numeradas** (crear cliente, cotizar, registrar abono, recordar…);
- **preguntas** que bloquean lo que no se puede decidir sin un humano;
- un **estado** (ver §10);
- los **hechos** que lo sostienen, cada uno con su cita.

El LLM **no arma** el borrador final: solo aporta los hechos. El borrador lo
arma el compilador.

---

## 5. Lectura en voz alta: «Lo que entendí»

Antes de confirmar, el sistema le devuelve a la persona, en una frase, lo que
creyó entender:

> «Entendí: el cliente es Dualsur, 380 m³ de 240, con 13 % de descuento, entrega
> con plazo de un mes, trabajando sábados y domingos, llevando la planta móvil al
> sitio, contactos: Julio Alvarado Meneses (ingeniero) al 0963444444; Mauricio
> Santander (ingeniero) al 0985454545, un pago de 27.000 USD por transferencia
> (sin confirmar si ya entró), un recordatorio para Mauricio Santander: «que nos
> haga la transferencia de este monto».»

Ese resumen se arma **solo con hechos entendidos**: no redacta, no completa, no
inventa. Si el audio habló de dinero pero no dijo si entró, lo dice
explícitamente.

**Esta lectura es la que se corrige.** Cada hecho tiene un botón **Corregir**.

---

## 6. Correcciones: la bóveda que hace que el sistema aprenda

Cuando alguien corrige un dato («Díaz Sur» → «Dualsur»), el sistema:

1. **No reescribe** el borrador viejo: crea una **versión nueva**.
2. Marca el anterior como **superado por corrección**.
3. Guarda la corrección como una fila nueva: qué se dijo, qué se corrigió,
   quién, cuándo y con qué cita del audio.
4. **Reaplica** las correcciones anteriores de la cadena: corregir el
   destinatario no borra el nombre que ya se había corregido.
5. Alimenta el **vocabulario aprendido**: la próxima vez que alguien dicte algo
   parecido, el sistema ya sabe que «Díaz Sur» suele ser «Dualsur».

Esto es la **bóveda de errores**: no es un log que nadie lee, es memoria que
mejora la siguiente extracción y material para el informe semanal.

> Probado en vivo: tras corregir «Díaz Sur» → «Dualsur», el dictado siguiente ya
> devolvió «Dualsur» sin que nadie lo corrigiera.

---

## 7. Dinero: la parte más delicada

- **Doble confirmación:** las acciones de dinero (abono, traslado de caja) se
  confirman dos veces. No hay un solo clic para tocar caja.
- **Guarda de "ya entró":** registrar un abono exige una frase **en pasado**
  («ya me depositó», «nos transfirió»). Si el audio dice «nos van a hacer una
  transferencia», el sistema **no** registra nada: pregunta «¿Los 27.000 USD ya
  entraron?».
- Aunque el modelo afirme que el dinero entró, si el dictado no lo sostiene, el
  sistema lo trata como **duda**.
- Una **corrección humana** de ese dato manda sobre la guarda.
- La IA **nunca** suma, resta, aplica descuentos ni decide un saldo. Eso lo hace
  el motor contable con aritmética exacta.

---

## 8. Tareas: dos caminos, un mismo seguimiento

Un dictado puede pedir dos cosas muy distintas, y **la decisión no la toma el
teléfono sino la intención**:

| Si Julio quiere **enviar un mensaje** a alguien | Si quiere que **alguien haga algo** |
|---|---|
| **Recordatorio de WhatsApp** | **Tarea interna** para alguien del equipo |
| Necesita número y permiso; se envía a su hora | Vive y se cierra en el panel del CRM |

Primero se decide **qué quiere** (enviar o delegar); después **quién** es el
responsable; después **el canal**. Si pide delegar y menciona un teléfono, ese
número es un dato de contacto: **no** se manda ningún mensaje. Si pide enviar y
no hay número, se pide el número (o se ofrece dejarlo como tarea interna).

### 8.1 Tarea interna: aviso, vista, acuse y cierre

Julio lo pidió así: *"no se trata de asumir el rol de un niño que dice 'yo ya
dije'; es ofrecer una solución"*. Por eso cada tarea interna registra **actos
distintos**, cada uno con su hora:

| Momento | Qué significa | Qué se guarda |
|---|---|---|
| **Avisada** | el sistema dejó el aviso en el panel y **arranca el reloj** | fecha y hora |
| **Vista** | una persona abrió el detalle. **No** es acuse | quién y cuándo |
| **Acusada** | la persona confirmó que **recibió el encargo**. No significa que lo hizo | quién y cuándo |
| **Resuelta** o **Justificada** | se hizo, o se explica por qué no hacía falta / no se pudo. **La nota es obligatoria** | quién, cuándo y qué dijo |
| **Registrada** | el cierre queda **con metadatos** (referencia, comprobante, comentario). **Sin metadatos no cierra** | quién, cuándo y con qué respaldo |

**Lo que se mide es tiempo entre eventos**, no cuánto trabajó una persona: desde
que se dejó el aviso hasta que se acusó, se resolvió o se registró. Sirve para
detectar demoras, no para evaluar el esfuerzo de nadie.

**Prioridad y plazo.** Cada tarea tiene prioridad `NORMAL` o `URGENTE` (la marca
el dictado: «urgente», «inmediatamente», «cuanto antes») y un plazo: **2 horas**
si es urgente, **24 horas** si es normal, salvo que el dictado fije otro. Las
pendientes se ordenan por urgencia y vencimiento. Si una tarea vence **sin
acuse**, se puede **escalar** a un supervisor, y eso queda en el historial.

### 8.2 El aviso no se puede "minimizar"

El riesgo que señaló Julio: un popout se cierra o queda minimizado y la persona
nunca lo ve. Por eso:

- Hay una **franja fija arriba del panel** —«Tienes 1 tarea pendiente · 1 vencida
  · 2 sin acuse»— que **no se puede cerrar**, se ve en todas las vistas y **no
  depende del navegador**.
- Si hay tareas **vencidas**, la franja se pone **roja**.
- La **campanita** también las lista.
- El **popout** queda solo como empujón inicial; se puede reabrir desde la franja
  o la campanita, y cerrarlo ya no silencia nada.
- Dentro del panel, la tarea muestra su **ficha** (tipo, cliente, monto de
  referencia, pendiente, resultado esperado) y sus botones: **Ver detalle**,
  **Acusar recibo**, **Resolver**, **Justificar**, **Registrar** y, si venció,
  **Escalar**.

### 8.3 Cómo distingue el sistema una tarea interna de un WhatsApp

Sin IA, por reglas claras y en este orden:

1. **¿Qué quiere Julio?** Si dice «que revisen», «verifica», «que confirme»,
   «averigüe», o nombra un área («secretaría», «bodega», «contabilidad»,
   «ventas»), quiere **delegar**.
2. Si dice «envíale», «mándale», «escríbele», «avísale», «recuérdale» o
   «whatsapp», quiere **enviar**.
3. Si quiere enviar y hay número (dictado o de un contacto del cliente) →
   recordatorio de WhatsApp.
4. Si quiere enviar y no hay número → se pide el número o se ofrece dejarlo como
   tarea interna.
5. Si quiere delegar → **tarea interna**, aunque el dictado mencione un teléfono
   (ese número es un dato de contacto, no el canal).

**Nunca se inventa un número** para convertir una tarea interna en WhatsApp, y
**nunca se manda un mensaje** que Julio no pidió enviar.

---

## 9. Informe semanal para Abelito

Cada semana se genera un documento (Markdown) con:

- los dictados donde **alguien corrigió** lo que el sistema entendió;
- la **transcripción** completa y los **hechos** que se extrajeron;
- las **acciones** que se propusieron;
- **qué corrigió quién** y con qué cita del audio;
- las **ejecuciones** y sus errores;
- el **vocabulario aprendido** (pares que se repiten);
- las **tareas internas** del periodo, con cuánto tardaron en resolverse y
  registrarse;
- una sección **«qué revisar»** ordenada por frecuencia.

Sirve para decidir si el problema es el **reconocimiento de voz**, el **prompt**,
el **normalizador** o el **compilador** — no para culpar a nadie.

---

## 10. Estados del borrador (qué significan)

| Estado | Qué quiere decir |
|---|---|
| `PENDIENTE_CONFIRMACION` | está todo lo necesario; espera el "sí" de un humano |
| `REQUIERE_ACLARACION` | falta un dato o hay una duda; hay preguntas concretas |
| `SIN_ACCIONES` | el dictado no pide nada ejecutable; se guarda igual como constancia |
| `SUPERADO_POR_CORRECCION` | alguien lo corrigió; hay una versión nueva |
| `EJECUTADO` | todas sus acciones se ejecutaron |
| `RECHAZADO` | un humano decidió no hacerlo |

Estados de una tarea interna: `NOTIFICADA` → `RESUELTA` / `JUSTIFICADA` →
`REGISTRADA`. **No se pueden saltar pasos.**

---

## 11. Dónde se usa

- **`/panel/cerebro`** — el laboratorio: se pega o se dicta el texto (o se sube
  un audio), se ve el texto normalizado, los hechos con su cita, el borrador, el
  resumen «Lo que entendí», el botón **Corregir** y el de **Confirmar**.
- **`/panel`** — el día a día: franja de tareas internas, campanita, popout y
  botones para **Resolver**, **Justificar** y **Registrar con metadatos**.

---

## 12. Decisiones de diseño (y lo que se descartó)

| Decisión | Por qué | Alternativa descartada |
|---|---|---|
| El LLM solo propone hechos con cita | evita datos inventados | dejar que el modelo arme el borrador |
| El compilador aplica reglas duras | dinero y estados no se deciden con IA | pedirle al modelo que "decida" |
| Corregir **versiona**, no reescribe | auditoría y trazabilidad | actualizar el borrador "para dejarlo limpio" |
| Correcciones como filas nuevas | memoria y aprendizaje | sobrescribir el dato anterior |
| Tarea interna con tabla propia | no tiene teléfono ni despachador | usar el teléfono de Secretaría y fingir WhatsApp |
| Reloj desde que se deja el aviso | mide la respuesta real | que la persona declare cuánto tardó |
| Nota y metadatos obligatorios para cerrar | evidencia de qué se hizo | cerrar con un clic |
| Aviso fijo, no solo popout | una ventana se cierra o se minimiza | confiar en el popout |
| Guarda de "ya entró" | un abono toca caja | confiar en el booleano del modelo |

---

## 13. Qué está verificado (y con qué)

Todo lo de abajo se probó en el entorno local; las evidencias están en
`.agents/evidencias/`.

| Qué | Resultado |
|---|---|
| Suite de pruebas | **586 pruebas en verde** |
| Candado del Hito 3 (bodega, chofer, cliente) | en verde, modo SANDBOX |
| Dictado Díaz Sur (dos contactos, descuento, planta móvil, transferencia) | 17 hechos con cita; resistencia ≠ precio; pide la dirección de la obra y a cuál ingeniero |
| Corrección encadenada | v1 → «Dualsur» (v2) → «30 días» (v3): conserva ambas correcciones |
| Vocabulario aprendido | tras corregir, la extracción siguiente ya devuelve «Dualsur» |
| Retiro de una asociación equivocada | el par retirado deja de usarse; la corrección original no se borra |
| Guarda de dinero | 4 casos: sin dato pregunta · modelo afirma sin sustento → pregunta · corrección humana registra · «todavía no» no registra |
| Tarea interna de punta a punta | avisada → acusada → resuelta con nota → registrada con metadatos |
| Aviso, vista y acuse | ver el detalle **no** es acusar; acusar **no** cambia el estado de la tarea |
| Prioridad y plazo | urgente 2 h / normal 24 h; vencida y escalada probadas |
| Idioma tentativo | «300 y pico» no se vuelve 300 m³: se pregunta y queda pendiente |
| Negación | «no le hagan todavía el descuento» → descuento **no aplicado** |
| Intención | delegar con teléfono **no** crea un WhatsApp; enviar a un número sí |
| Instrucción maliciosa o citada | no se ejecuta: queda como texto de la tarea o se pregunta |
| Idempotencia | misma clave → `repetido`; resolver dos veces → rechazado |
| Aviso fijo en el panel | visible con conteo, vencidas y sin acuse; cerrar el diálogo no lo oculta |

---

## 14. Qué NO hace (a propósito, por ahora)

- **No conversa todavía por WhatsApp**: el canal es la fase siguiente. El
  contrato está escrito (`docs/CONTRATO_WHATSAPP_CEREBRO.md`), pero hoy se usa por
  panel y por API.
- **No ejecuta** todavía `crear_cliente` ni `crear_cotizacion_borrador` desde el
  Cerebro: se proponen y el sistema avisa que aún no tienen ejecutor. Es
  deliberado: primero la lectura y la corrección, después la escritura.
- **No entrena un modelo propio ni guarda voces para eso**: el audio se conserva
  como evidencia, no como material de entrenamiento.
- **No persiste** los contactos del cliente (`contacto.*`) en la ficha del
  cliente: se extraen y se usan en el borrador, pero aún no se archivan.
- **No calcula dinero** ni decide saldos: eso es del motor contable.
- **No redacta** mensajes: los reproduce tal como se dictaron.
- **No manda nada** sin confirmación humana, y menos dinero (doble confirmación).
- **No mide el trabajo de una persona**: mide tiempo entre eventos.

---

## 15. Qué falta y qué hay que decidir

1. **WhatsApp conversacional** (siguiente hito de producto): persistir los
   entrantes, abrir el hilo, corregir y confirmar por el mismo chat, y responder
   «¿qué pasó con lo que le encargué ayer a secretaría?».
2. **Conectar la escritura**: `crear_cliente` y `crear_cotizacion_borrador` al
   confirmar, y archivar los contactos en la ficha del cliente.
3. **Bóveda de audios**: ¿se guardan las voces de cada persona para que el
   sistema aprenda su forma de hablar? Requiere consentimiento y retención.
4. **Revisar el aviso fijo con Julio**: tamaño, lugar, y si debe sonar o
   parpadear cuando entra una tarea nueva (hoy solo cambia a rojo si hay
   vencidas).
5. **Cargar datos reales**: precios y recetas oficiales, teléfonos del personal y
   cuentas bancarias. Hasta entonces, el sistema los pide o los deja pendientes.

---

## 16. Glosario mínimo

| Término | Qué es |
|---|---|
| **Hecho citado** | dato + frase textual que lo sostiene + instante del audio + hablante |
| **Sobre** | el conjunto de hechos que el modelo propuso para un dictado |
| **Borrador** | la propuesta de acciones y preguntas, antes de escribir nada |
| **Compilador** | las reglas determinísticas que convierten hechos en acciones |
| **Receta** | la mezcla oficial del catálogo (`FC-210`, `FC-240`…): la define el negocio |
| **Resistencia** | la clase de hormigón; **no** es un precio |
| **Ejecución** | el registro de una acción confirmada y ejecutada |
| **Corrección** | un humano arreglando un dato entendido; queda como fila nueva |
| **Tarea interna** | instrucción a alguien del equipo sin teléfono; se cierra en el CRM |

---

## 17. Cómo revisarlo en 10 minutos

1. Abre **`/panel/cerebro`** con el perfil de Julio.
2. Pega el dictado de prueba de Díaz Sur y pulsa **Interpretar** (6–7 segundos).
3. Lee **«Lo que entendí»** y compáralo con lo que dice el dictado.
4. Pulsa **Corregir** en el nombre del cliente y escribe otro. Verás que el
   borrador pasa a **versión 2** y el anterior queda como superado.
5. Mira las **preguntas**: la obra y a cuál ingeniero. Son dudas reales, no
   errores.
6. Abre **`/panel`**: la franja de tareas internas aparece arriba con el conteo,
   las vencidas y las que están sin acuse. Entra, pulsa **Ver detalle** (queda
   como vista), **Acusar recibo** (no cambia el estado), **Resolver** con una
   nota y **Registrar** con metadatos.
7. Cierra el diálogo: la franja sigue ahí. Ese es el punto.

---

*Documento de revisión, no de implementación. Si algo de lo que dice acá no
coincide con lo que ves en el panel, gana el panel: avísame y lo corregimos.*
