# Brief — El Cerebro de Horminor, versión profunda

**Para:** modelo de IA externo (arquitecto/ingeniero senior con criterio de
investigación aplicada).
**De:** Dirección de Horminor + agente de desarrollo.
**Fecha:** 2026-11-14.
**Estado:** el componente de voz ya existe (Fase 1). El Cerebro es la Fase 2 y
**todavía no se ha escrito**. Este documento no pide más alcance: pide
profundidad sobre el riesgo central.

---

## 0. Cómo usar este documento

1. Pega el bloque de **§1** como primer mensaje.
2. Pega después **§2 a §9**.
3. El modelo debe responder **primero las cuatro preguntas** de §1 y **después**
   ejecutar la petición de §6. Si mezcla el orden, la respuesta no sirve.

---

## 1. Prompt (copiar tal cual)

```text
Quiero una versión más profunda de esta tarea, no una más grande. Antes de
reescribirla: (1) dime qué haría aquí un profesional de primer nivel en este
campo que yo no estoy pidiendo; (2) nombra el material más en bruto (raw) del
que partiría en lugar de lo que ya viene digerido para mí; (3) nombra los
métodos y herramientas específicos que usaría; (4) nombra qué, aparte de ti o
de mí, demostraría que el resultado es correcto. Luego (haz la petición)
```

La petición está en **§6**. No la adelantes.

---

## 2. Contexto mínimo

**Horminor** vende hormigón premezclado con planta móvil en El Coca (Orellana)
y Sucumbíos, Ecuador. Julio (dueño) vende y cobra; una secretaria cotiza,
cobra y agenda; bodega despacha. Hoy la información se pierde entre audios de
WhatsApp, memoria y un ERP que alguien transcribe cuando puede.

**Lo que ya existe y funciona:**

- ERP/CRM modular en PostgreSQL 15 + FastAPI + Redis + Docker, panel HTML sin
  build.
- **Gato**: asistente interno con *function calling* sobre 22 consultas de solo
  lectura, catálogo con permisos por rol y **guarda de cifras** (todo número de
  la respuesta debe existir en la salida de una herramienta).
- **Custodio**: gate contable con ledger append-only, testigo, idempotencia y
  14 intenciones de mutación (abono, gasto, compra, orden…).
- **Sabueso**: búsqueda de clientes tolerante a tildes, orden de nombre y
  errores.
- **Cotizaciones** con numeración, IVA en `Decimal`, versiones y eventos.
- **Voz (Fase 1, recién construida):** el audio se valida, se hashea, se guarda
  y se registra; sin proveedor STT queda `DEGRADADO_SIN_CREDENCIAL` sin
  inventar texto. Normalizador determinístico de números/cédulas/teléfonos en
  español ecuatoriano, con 16 tests.
- Migración **085**: 10 tablas para ingestas, trabajos STT, transcripciones,
  extracciones, borradores, ejecuciones y hechos de cliente con provenance.
- 445 tests automatizados y 2 pruebas de candado en verde.

**Lo que NO existe todavía:** proveedor STT real, extractor, borradores en la
interfaz, modo sombra, gold set y minería de WhatsApp (bloqueada porque los
mensajes entrantes aún no se persisten).

**El problema real no es “extraer datos”.** Es que Julio confíe en lo extraído
sin tener que revisar todo, y que cuando se equivoque se pueda demostrar qué
se dijo, quién lo dijo y qué hizo el sistema. La pregunta de este brief es
**cómo se sabe que el Cerebro acierta**, no cómo se le agregan funciones.

---

## 3. Mi propuesta actual (critícala, no la copies)

Para que tengas algo concreto que romper:

1. **Dos capas.** Un extractor LLM que devuelve un sobre JSON con intenciones,
   entidades, evidencia (frase + milisegundo + hablante), faltantes y
   ambigüedades; y un **verificador determinístico** en Python que exige que
   cada número, cédula y fecha exista en el texto normalizado, valida el dígito
   verificador y resuelve el cliente contra Sabueso.
2. **Nada se escribe sin confirmar.** El extractor produce un **borrador
   versionado**; un humano lo confirma. El dinero exige doble confirmación. Las
   correcciones crean una versión nueva; el historial es append-only.
3. **Trazabilidad.** El audio y la transcripción cruda se guardan sin editar;
   cada dato del borrador apunta a una cita y a un instante.
4. **Nueve acciones** (crear cliente, cotización, enviar, pedir ubicación,
   abono, traslado caja-banco, gasto, tarea, hecho de carpeta) que llaman a los
   servicios existentes, nunca a SQL propio.
5. **Interruptores apagados** hasta que exista proveedor y Dirección apruebe.

**Sospecho que esto es insuficiente en cinco puntos** y quiero que los ataques:
evaluación, calibración de confianza, taxonomía de fallos, flujo humano real y
privacidad. No me des más tablas: profundiza estos.

---

## 4. Corpus semilla (los únicos audios que hay)

Son inventados por Dirección para fijar el nivel de exigencia. Están crudos, con
repeticiones y muletillas, como se habla de verdad.

**A. Alta completa en una sola respiración**

> «Crea un cliente llamado Jorge Bailón con número de cédula dictame tu cédula
> 110256 que mas 1531, listo, es del coca y quiere 25m3 para el próximo sábado…
> el teléfono de él es 0965555555 y vive a la vuelta del estadio de la santísima
> Caridad … ¿cuánto me vas a dar? Ya me acaba de dar $1000 de abono y hay que
> enviarle una cotización a su whatsapp indicando que me entrego en efectivo,
> eso es todo»

**B. Dinero en dos pasos**

> «Acabo de recibir un abono del inge Reyes de 12000 en efectivo, lo voy a
> depositar en la cuenta del Pichincha»

**C. Consulta que suena a orden**

> «Nos salió un trabajito para mañana tenemos que entregar 12 m3 a las 3pm,
> revisa como estamos con los mixers a ver si avanzamos con la entrega de
> mañana a atenderle o ver que hacemos»

Cada uno tiene trampas: la cédula se dicta en dos tramos; «¿cuánto me vas a
dar?» lo dice Julio, no el cliente; «recibí» y «deposité» son dos movimientos;
«revisa» es consulta, no orden. El detalle está en §9.

---

## 5. Material en bruto que podemos conseguir

Lo que sigue no está digerido y es lo que un profesional pediría antes de
escribir prompts. Todavía no lo tenemos todo; dilo si lo necesitas.

| Material | Por qué es más valioso que un resumen |
|---|---|
| **Audio original** (ogg/opus de WhatsApp, con ruido de planta) | el STT real falla distinto que un texto limpio |
| **Transcripción palabra por palabra con timestamps**, sin corregir | conserva titubeos, correcciones y solapamientos |
| **Export crudo de WhatsApp** de 3–5 clientes (texto y audios) | muestra cómo se negocia de verdad, no cómo se escribe un caso |
| **Lo que la secretaria cargó a mano** para esos mismos casos | *ground truth* operativo, no una etiqueta inventada |
| **Correcciones de Julio sobre borradores** (cuando existan) | mide dónde falla el sistema, no dónde falla el ejemplo |
| **Cierres de caja y movimientos del Custodio** del mismo período | permite reconciliar montos contra el ledger |
| **Entrevista grabada con Julio y la secretaria** | revela el vocabulario y las excepciones que no aparecen en un brief |
| **Esquema real de la base y eventos de cotización** | evita diseñar sobre columnas que no existen |

Condición: audio y chats de clientes requieren consentimiento y una política de
retención. Si tu diseño asume que se pueden usar sin eso, está mal.

---

## 6. La petición

Diseña el Cerebro como un **sistema de evidencia**, no como un prompt grande.
Quiero **seis piezas profundas**, no doce entregables superficiales. Cada una
con decisión, porqué, alternativa descartada y **cómo se probaría**.

### P1. Modelo de evidencia y taxonomía de fallos

- ¿Qué es exactamente un “dato sostenido” en este sistema? Define el vínculo
  entre valor, frase, offset de carácter, instante de audio y hablante.
- ¿Cómo se propaga la confianza del STT a la entidad? ¿Qué pasa cuando el STT
  duda de una palabra que es justamente la cédula o el monto?
- Taxonomía de fallos: audio inaudible, hablante equivocado, número mal
  dictado, dato ausente, dato contradictorio, cliente ambiguo, acción
  dependiente, intención mal clasificada. Para cada uno: ¿preguntar, bloquear,
  degradar o escalar? ¿Con qué texto exacto al usuario?

### P2. Gold set y medición

- Protocolo para construir un **conjunto de oro** con Julio y la secretaria:
  muestreo, guía de anotación, doble anotación, adjudicación de desacuerdos,
  versionado y tamaño mínimo.
- Métricas **por campo** (no un “accuracy” global): precisión y recall de
  cédula, teléfono, monto, volumen, fecha, cliente; **tasa de invención** (debe
  ser 0); **tasa de corrección humana**; tiempo hasta confirmar; tasa de
  escalamiento.
- Umbrales de despliegue y qué se hace si no se alcanzan.
- ¿Cómo se evita que el gold set se contamine con el prompt?

### P3. Arquitectura extractor + verificador

- Contrato del sobre y del borrador (JSON Schema), validación y reintentos.
- Verificador determinístico: qué comprueba, qué no puede comprobar y qué hace
  cuando no puede.
- Uso de dos modelos o dos pasadas: ¿vale la pena? ¿Cómo se compara?
- Resolución de entidades y deduplicación (cédula, teléfono, nombre) sin crear
  clientes fantasma.
- Costo y latencia por audio; qué se cachea y qué no.

### P4. Flujo humano y modo sombra

- Cómo revisa y corrige una persona en 20 segundos, no en 3 minutos.
- Qué se muestra primero (campos críticos), qué se colapsa y qué se pregunta.
- **Modo sombra:** el Cerebro procesa audios reales durante N semanas sin
  escribir, y se compara con lo que el humano cargó. Define N, la métrica de
  salida y qué hacer con los desacuerdos.
- ¿Cómo se mide si el sistema ahorra tiempo en vez de agregar trabajo?

### P5. Privacidad, consentimiento y operación

- Retención del audio y del texto; consentimiento del cliente; acceso por rol.
- Redacción de PII en logs y trazas.
- Qué pasa si un audio contiene datos de un tercero o una instrucción
  maliciosa.
- Costos: presupuesto por audio, por día y por minería; qué se apaga primero.

### P6. ADR y plan de validación de dos semanas

- Un **ADR** con las decisiones anteriores y las alternativas descartadas.
- Un plan de **dos semanas** para validar las tres suposiciones más riesgosas
  **antes** de construir el Cerebro completo. ¿Qué se prueba primero y con qué
  material?
- Qué **no** construir todavía y por qué.

---

## 7. Restricciones (no se negocian)

1. Cero datos de negocio inventados. Si falta, `PENDIENTE`.
2. El LLM no calcula dinero; la aritmética es `Decimal` o el Custodio.
3. El LLM no ve SQL; solo herramientas con contrato y permisos.
4. Ninguna escritura sin confirmación humana; el dinero exige doble
   confirmación.
5. El historial crudo es append-only; las correcciones son entradas nuevas.
6. Permisos en el backend, nunca en el prompt.
7. Sin credenciales no se finge: se degrada y se avisa.
8. Migraciones aditivas; no se edita una aplicada.

---

## 8. Cómo se juzgará tu respuesta

- ¿Respondiste las cuatro preguntas **antes** de la petición?
- ¿Nombraste métodos y herramientas concretos (no “usar IA”)?
- ¿Dijiste qué evidencia **externa** probaría que funciona?
- ¿Profundizaste o solo agregaste secciones?
- ¿Cada decisión trae porqué y alternativa descartada?
- ¿Marcaste lo que depende de datos que no tienes?
- ¿Evitaste placeholders, “depende” y diagramas decorativos?

Si tu respuesta se puede resumir en “hacer un prompt mejor y probarlo”, no
sirve.

---

## 9. Anexo — Trampas de los tres audios

| Caso | Trampa | Qué debe hacer el Cerebro |
|---|---|---|
| A | «110256 que más 1531» | unir los tramos; si el dígito verificador no cuadra, preguntar, no corregir |
| A | «¿cuánto me vas a dar?» | atribuirlo a Julio, no al cliente |
| A | «próximo sábado» | convertir a fecha absoluta en America/Guayaquil y confirmar si es este o el siguiente |
| A | «a la vuelta del estadio…» | guardarlo como referencia, no como dirección catastral |
| A | «ya me acaba de dar $1000» | es un hecho narrado por Julio; el abono se registra con confirmación |
| B | «recibí 12000 y lo voy a depositar» | dos acciones distintas; el depósito no es un ingreso nuevo |
| B | «inge Reyes» | resolver por Sabueso; si hay dos, preguntar |
| C | «revisa cómo estamos» | consulta de solo lectura; no crear orden ni prometer entrega |
| C | «mañana 3pm» | fecha/hora absoluta; si falta capacidad de flota, decirlo |

---

## 10. Cierre

No quiero un Cerebro que impresione en una demo. Quiero uno que, cuando se
equivoque, muestre la frase exacta que lo confundió y permita corregirlo sin
reescribir la historia.

Diseña eso.
