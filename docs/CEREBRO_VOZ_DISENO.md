# Cerebro y Voz — diseño canónico v1.5

> **Estado:** diseño cerrado para implementar por fases. **Fases 0 y 1
> cerradas**: servicios extraídos y migración **085 aplicada** (10 tablas de
> voz/cerebro, settings y módulos ACL). El adaptador real de STT queda
> pendiente; sin credenciales el audio se guarda y se avisa.
> **v1.1 (2026-11-14):** incorpora la revisión profunda externa; ver §1.1.
> **v1.2 (2026-11-15):** tareas de WhatsApp conectadas a Gato, contactos y
> dinero no recibido; ver §3.2.
> **v1.3 (2026-11-15):** varios contactos, condiciones del contrato y popout de
> tareas en el panel; ver §3.3.
> **v1.4 (2026-11-15):** correcciones humanas con bóveda (migración **087**),
> lectura en voz alta, guarda de dinero e informe semanal; ver §3.4.
> **v1.5 (2026-11-15):** tareas internas con reloj y metadatos (migración
> **088**) y borrador sin acciones (migración **089**); ver §3.5.
> **Base:** brief `docs/BRIEF_CEREBRO_VOZ.md` + respuesta del modelo externo
> (ronda 2) + auditoría contra el esquema real del 2026-11-14.
> **Regla:** si algo no está acá ni en `system_settings`, va `PENDIENTE`; no se
> inventa.

## 0. Qué se construye

Dos piezas independientes y un punto de unión:

| Pieza | Responsabilidad | No hace |
|---|---|---|
| `app/voz/` | ingesta del audio, hash, almacenamiento, transcripción y normalización es-EC | interpretar, consultar clientes, escribir negocio |
| `app/cerebro/` | convertir texto/transcripción en un sobre con provenance, armar borradores y ejecutar acciones confirmadas | ver SQL, calcular dinero, mutar sin confirmación |
| `app/asistente/` (Gato) | preguntas de solo lectura con guarda de cifras | manejar audios ni borradores |

La normalización determinística ya existe: `services/core-api/app/voz/normalizador_ec.py`
(16 tests). El resto se construye por fases (§7).

## 1. Decisiones de Dirección resueltas

Las tres preguntas que quedaron abiertas se resuelven así. Son reversibles:
cada una se puede cambiar sin reescribir datos ya guardados.

1. **Fecha tentativa de entrega.** Se agregan dos columnas *nullable* a
   `cotizaciones`: `fecha_entrega_tentativa date` y
   `hora_entrega_tentativa time`. No se usa `timestamptz` porque «el próximo
   sábado» no trae hora y no se va a inventar una. La fecha firme sigue
   viviendo en `dispatch_schedule.fecha_entrega` cuando exista orden.
2. **Precio no dicho en el audio.** La cotización se crea siempre en
   `BORRADOR`. Si la receta tiene `precio_m3`, se precarga **ese** valor con su
   `precio_estado` real (`PROVISIONAL`/`OFICIAL`); no es un dato inventado, es
   la lista vigente. Si no hay precio, queda `NULL`. En ningún caso se envía
   automáticamente: `enviar_cotizacion_whatsapp` bloquea si
   `precio_estado = PROVISIONAL` y el entorno no es SANDBOX.
3. **Minería de WhatsApp.** Es **Fase 3 y está bloqueada** hasta que M1
   persista los mensajes entrantes en `chat_mensajes`. Hoy esa tabla está
   vacía y solo la escribe el panel; minar algo que no existe sería fingir.
   La Fase 3 arranca con la ingesta de entrantes, no antes.

## 1.1 Adoptado de la revisión profunda (2026-11-14)

Seis piezas pasan al diseño. El resto de la revisión queda como material de
trabajo, no como decisión.

1. **Hecho citado ≠ comando.** El extractor produce un AST de hechos con cita,
   posición y hablante; un **compilador determinístico** los convierte en
   acciones y falla si no se cumplen los invariantes del dominio. El LLM no
   arma el borrador final.
2. **Mapa de alineación obligatorio.** `normalizar_texto` hoy reescribe el
   texto («veinticinco cubos» → «25 m3»), así que los offsets del texto
   normalizado **no existen** en la transcripción cruda ni en los tiempos del
   STT. La normalización debe devolver `token_normalizado → span_crudo →
   palabras STT`, o el modelo de evidencia no se puede implementar. Es el
   hueco técnico más serio de la propuesta externa.
3. **Gold set con `dev` y `held-out`.** La mitad del corpus queda sellada por
   hash y no se usa para escribir prompts ni reglas; si se usa, deja de medir.
4. **Modo sombra con reconciliación.** 3 semanas o 50 audios; cada borrador
   sombra se cruza contra lo que el humano cargó y los desacuerdos se clasifican
   en: fallo del Cerebro, olvido humano o ambigüedad real.
5. **Redacción de PII y orden de degradación.** Cédulas, teléfonos y nombres
   fuera de los logs; al agotar cuota se apaga primero minería, luego audios
   largos, luego el LLM; el audio siempre se conserva.
6. **Umbrales por costo, no por F1.** Un monto mal confirmado no cuesta lo
   mismo que una pregunta extra. La matriz de costos la fija Dirección; hasta
   entonces, los umbrales son hipótesis.

## 2. Correcciones aplicadas a la ronda 2

Además de lo que ya traía, se corrigen estos puntos antes de escribir una
línea de migración:

| # | Corrección | Motivo |
|---|---|---|
| 1 | `system_settings` usa `descripcion`, no `description` | El `INSERT` de la ronda 2 falla contra la tabla real |
| 2 | No se siembran topes de gasto (5 USD / 2 USD) | Serían política inventada; quedan `null` + `PENDIENTE` |
| 3 | `VOZ_ENABLED` y `CEREBRO_ENABLED` nacen **false** | Sin proveedor STT/LLM no se finge; se activan al configurar |
| 4 | No se crea `VOZ_MAX_MB`: se reutiliza el límite de audio existente | Ya existe `media_max_audio_mb` (40 MB) en `settings.py` |
| 5 | Se siembran los módulos `voz` y `cerebro` en `panel_users_acl.modulos_permitidos` (false) | Sin la clave, el ACL no puede filtrar; el checklist de Superadmin los muestra |
| 6 | `crear_cotizacion_borrador` exige `obra_direccion` **antes** de crear | La columna es `NOT NULL`: no se puede crear un borrador «bloqueado sin obra» |
| 7 | `resistencia` es **código de texto** con FK a `concrete_recipes(resistencia)`, no un `resistencia_id` | Es la PK real de la tabla de recetas |
| 8 | `cerebro_borradores` gana trigger que prohíbe cambiar `acciones_propuestas_json` | El payload es inmutable; solo cambian estado y `lock_version` |
| 9 | El hash de `client_facts` incluye fecha del hecho y fuente | Dos acuerdos idénticos en fechas distintas no son el mismo hecho |
| 10 | `client_fact_supersedes` usa PK `(superado, nuevo)` y único parcial sobre `nuevo` | Un hecho puede superarse más de una vez; uno nuevo no puede reemplazar a dos |
| 11 | `voz_ingesta_media_links` usa PK `(ingesta_id, media_asset_id)` | Permite vincular una ingesta a más de un expediente si se reenvía |
| 12 | `storage_bucket` usa `BUNNY`/`SANDBOX`, igual que `media_assets.backend` | Evita dos vocabularios para lo mismo |
| 13 | `idempotency_key` de extracción incluye `version_prompt` | Re-extraer con prompt nuevo no debe chocar con el `UNIQUE` |
| 14 | No se agrega `capacidad_planta_mixers` en el MVP | La flota operativa no está modelada con fiabilidad; Caso C responde con `disponibilidad_agenda` y dice qué no sabe |
| 15 | El traslado caja→banco queda como **intent nuevo con saldo real** | `1101` es Caja y `1102.0x` Bancos; hoy no existe el asiento y el saldo de caja debe salir de `v_balance_general` |
| 16 | Se extrae `services/cotizaciones.py` antes de conectar el Cerebro | El alta vive inline en el router (numeración, IVA, versión, eventos); duplicarla rompe la cadena |

## 3. Modelo de datos (migración 085)

| Tabla | Qué guarda | Inmutable |
|---|---|---|
| `voz_ingestas` | audio crudo: sha256, canal, emisor, storage, mime, bytes, duración | sí |
| `voz_ingesta_media_links` | vínculo diferido a `media_assets` cuando se resuelve el cliente | sí |
| `voz_trabajos_stt` | cola y estado por intento (`PENDIENTE`…`DEGRADADO_SIN_CREDENCIAL`) | no (estado) |
| `voz_transcripciones` | texto crudo y normalizado, segmentos y confianza | sí |
| `cerebro_extracciones` | sobre JSON, modelo, prompt, tokens, latencia y costo | sí |
| `cerebro_borradores` | acciones propuestas, preguntas, estado y `lock_version` | payload sí |
| `cerebro_ejecuciones` | un registro por intento de cada acción; único éxito por `request_id` | sí |
| `client_facts` | hechos del expediente con provenance y hablante | sí |
| `client_fact_supersedes` | qué hecho reemplaza a cuál y por qué | sí |
| `whatsapp_mineria_cursores` | avance de la minería por teléfono | no |

Reglas de integridad que no se negocian:

- Un solo trabajo `COMPLETADO` por ingesta (índice único parcial), pero se
  puede reintentar después de `FALLIDO` o `DEGRADADO`.
- Una sola ejecución `EXITOSA` por `request_id_custodio`; los fallos se
  registran con `intento_num` creciente.
- Hecho superado se marca insertando en `client_fact_supersedes`, nunca con
  `UPDATE`.
- `media_assets.cliente_id` es `NOT NULL`: por eso el audio primero vive en
  `voz_ingestas` y se vincula cuando el cliente existe.
- La migración **086** agrega `cerebro_extracciones.texto_directo`: el Cerebro
  también acepta texto pegado o dictado, no solo una transcripción.

### 3.1 De hecho citado a comando

```
SobreExtraccion (LLM)            Compilador (Python)               Borrador
hechos[] con cita, offset   -->  valida invariantes           -->  acciones[]
y hablante                       resuelve cliente (Sabueso)        preguntas[]
confianza por campo              aplica reglas de dominio
                                 si no compila -> REQUIERE_ACLARACION
```

El compilador **no llama al LLM**. Si un hecho no tiene cita alineada con el
texto y con los tiempos del STT, no compila y no se convierte en acción. Las
reglas que aplica son las que ya existen en el dominio: `obra_direccion` no
nula, `resistencia` en el catálogo, `precio_estado` bloqueando el envío fuera de
SANDBOX, saldo de caja 1101 antes de un traslado.

**Implementado (2026-11-14):** `normalizar_con_mapa` devuelve cada token con su
span crudo; `localizar_palabras` y `alinear_secuencias` lo atan a las palabras
del STT, a su ventana de milisegundos y a la confianza mínima **sin contar los
conectores** («que más»). Una cédula dictada en dos tramos queda como un solo
dato con dos palabras de valor. Si no hay palabras del STT, el dato queda sin
ventana y no se puede confirmar con un clic.

También está implementado el compilador: `app/cerebro/hechos.py` construye y
valida hechos citados, y `app/cerebro/compilador.py` los convierte en un
borrador con invariantes (obra, resistencia, precio, permisos, doble
confirmación de dinero, saldo de caja). No escribe en la base: la persistencia
del borrador viene después.

**Audio (2026-11-14):** `app/voz/proveedores/groq.py` transcribe con Whisper y
devuelve palabras con tiempos. El extractor (`app/cerebro/extractor.py`) toma la
transcripción, verifica cada cita y produce el borrador. Probado de punta a
punta: el STT confundió una cédula y el verificador **la descartó** en vez de
inventarla.

**Reglas del caso Joaquín (2026-11-15):**

- Un teléfono dictado en grupos («0965 555 555») se une a un solo número; una
  cédula en tres grupos también, sin corregir el dígito verificador.
- Si el LLM no captura el teléfono, el backend propone el único `09…` del audio
  como hecho `INFERIDO` y el compilador obliga a confirmarlo («¿El teléfono del
  cliente es…?»). Un hecho inferido sirve para preguntar, nunca para resolver
  identidad por sí solo.
- Una hora suelta («a las 6 de la mañana») no sostiene `fecha_entrega`: se
  guarda como `cotizacion.hora_entrega` (`HH:MM`) y `fecha_entrega_tentativa`
  queda nula hasta que se diga la fecha. El compilador vuelve a validar la cita
  antes de usar una fecha.
- Si el teléfono o la cédula ya existen a nombre de otro cliente, no se resuelve
  en silencio: se pregunta «¿Es el mismo cliente?».

### 3.2 Tareas, contactos y dinero que todavía no entró (2026-11-15)

El dictado también ordena cosas que no son una cotización ni un abono. Se
separaron las claves para no confundirlas:

| Clave | Qué es | Regla |
|---|---|---|
| `contacto.nombre` / `contacto.rol` / `contacto.telefono` | maestro, encargado o ingeniero del cliente | ese teléfono **no** es `cliente.telefono` |
| `pago.recibido` | boolean: el dinero ya entró | `false` («todavía no me envía el comprobante») impide registrar el abono |
| `pago.cuenta_destino` | banco o cuenta donde el cliente transfiere | no se convierte en `traslado.cuenta_banco` |
| `traslado.cuenta_banco` | mover efectivo de caja al banco | solo si el audio lo ordena; nunca para una transferencia del cliente |
| `tarea.telefono` / `tarea.destinatario` / `tarea.mensaje` / `tarea.cuando` / `tarea.adjuntar_factura` | recordatorio por WhatsApp | el mensaje se copia del dictado, sin agregarle montos ni fechas |

Reglas implementadas:

1. «Enviar un recordatorio / pedir el comprobante» compila
   `crear_tarea_recordatorio`, no `cotizacion.enviar`.
2. Si no se dicta hora, se propone `cuando = "ahora"` y el parámetro
   `programado_inferido = true` lo deja visible en la confirmación. El envío
   ocurre al confirmar, no antes.
3. Un abono con `pago.recibido = false` no se propone: la nota explica que
   falta el comprobante. Cuando llegue, un dictado nuevo con `pago.recibido =
   true` genera la acción.
4. Resistencia dicha como número («210») se completa contra el catálogo
   (`FC-210`) en el compilador; la cita sigue siendo el número dictado.
5. La confirmación de la pantalla **es** la ratificación: `recordatorios.crear`
   recibe `confirmado_por` y la fila nace `PENDIENTE` en `gato_recordatorios`.
   No hay doble «sí» entre Cerebro y Gato. El despachador de Gato envía a su
   hora; en SANDBOX queda en el outbox.
6. El ejecutor solo está conectado para `crear_tarea_recordatorio`. Las demás
   acciones se proponen, pero el endpoint responde 501 en vez de simular una
   escritura.

**Pendiente de decisión:** las tareas internas sin WhatsApp («que revisen en
secretaría los despachos») no tienen tabla propia todavía. `gato_recordatorios`
exige teléfono. Se propone una migración 087 con una tabla de tareas internas,
o resolverlas como un recordatorio al teléfono de Secretaría.

### 3.3 Varios contactos, condiciones y aviso al panel (2026-11-15)

**Contactos múltiples.** Un dictado puede nombrar al responsable del contrato y
al jefe de obra, cada uno con su número. El primero va en `contacto.*`; los
siguientes en `contacto.2.*` y `contacto.3.*`. El compilador:

- si hay un solo contacto con teléfono, lo usa como destino;
- si hay varios y el dictado no dice a quién, pregunta con las opciones
  («¿A quién le envío el recordatorio: Julio Alvarado o Mauricio Santander?»);
- si el destinatario nombrado coincide con un contacto, usa su teléfono;
- nunca usa un nombre de contacto como `cliente.telefono`.

**Condiciones del contrato.** `cotizacion.resistencia` (240) no es
`cotizacion.precio_m3`. El plazo («en un mes») va en
`cotizacion.plazo_entrega`, el descuento en `cotizacion.descuento_pct`, los
días en `cotizacion.dias_trabajo` y la planta móvil en
`operacion.planta_movil`. El compilador los resume en `notas` de la
cotización; no inventa una fecha ni aplica el descuento al precio.

**Hora del recordatorio.** Si el LLM no extrae `tarea.cuando` pero la frase del
recordatorio dice «a las 18:00», el backend toma la hora de esa misma oración
(`_completar_cuando_de_tarea`). Un recordatorio no puede salir «ahora» cuando
el dictado fijó una hora. `validar_hecho` acepta `HH:MM` explícito además de
«a las seis de la tarde».

**Aviso al panel (popout + campanita).**

- `GET /api/v1/cerebro/tareas/pendientes` devuelve los recordatorios
  `PENDIENTE`/`ENVIANDO` con destinatario, mensaje y hora local.
- `/panel` abre un `<dialog>` «Tareas pendientes» al entrar si hay tareas
  nuevas; «Entendido» guarda los ids en `localStorage['horminor.tareas.vistas']`
  para no repetir el popout. La campanita también las lista.
- `/panel/cerebro` muestra el mismo popout al confirmar una tarea.

**Decisión de arquitectura (para el Bibliotecario de datos).** No se crea una
tabla de notificaciones ni se duplica la cola: `gato_recordatorios` sigue
siendo la única fuente de tareas programadas. La consulta del panel es directa
y **no** está en `docs/CATALOGO_CONSULTAS.json`; si Gato debe responder «¿qué
tareas tengo?», primero se agrega una consulta nombrada al catálogo. Las claves
`contacto.2.*`, `pago.recibido`, `tarea.cuando`, etc. son hechos del borrador,
no columnas nuevas. Alternativa descartada: tabla `notificaciones` propia, que
obligaría a sincronizar dos estados de la misma tarea.

### 3.4 Correcciones humanas, bóveda de errores y guarda de dinero (2026-11-15)

El dictado es la primera lectura, no la verdad. Antes de confirmar, el sistema
lee en voz alta lo que entendió y la persona lo corrige.

**Lectura en voz alta.** `/interpretar` y `/corregir` devuelven `resumen`
(«Entendí: el cliente es Dualsur, 380 m3 de 240, …»), armado solo con hechos
`utilizable`: no redacta, no completa y no inventa. Si el audio habló de dinero
pero no dijo si entró, dice «(sin confirmar si ya entró)». En `/panel/cerebro`
el resumen va arriba, con un botón **Corregir** por hecho.

**Corrección = fila nueva.** `POST /api/v1/cerebro/borradores/{id}/corregir`
inserta un borrador **versión +1** con `borrador_padre_id`, marca el anterior
`SUPERADO_POR_CORRECCION` y registra la corrección en `cerebro_correcciones`
(migración **087**, append-only con trigger). No se reescribe el payload del
borrador viejo y no se vuelve a llamar al LLM: los hechos se reconstruyen desde
`sobre_json` + texto con `_hechos_reconstruidos`.

- Las correcciones previas de la cadena se reaplican en orden antes de la nueva:
  corregir el destinatario no borra el nombre ya corregido.
- `CORREGIDO_POR_HUMANO` es autoridad: el valor puede no estar en el audio y el
  hecho nuevo puede no tener cita (no se finge evidencia).
- `v_cerebro_vocabulario` agrupa los pares («Díaz Sur» → «Dualsur») y el
  extractor los pasa al prompt como `CORRECCIONES CONOCIDAS`. Probado en vivo:
  tras una corrección, la extracción siguiente ya devolvió `Dualsur`.

**Guarda de dinero** (`app/cerebro/dinero.py`, compartida por compilador y
resumen). Registrar un abono toca caja y cartera: solo se propone si hay una
frase en pasado («ya me depositó», «nos transfirió») en la cita o en la ventana
del texto alrededor de la cifra (la cita de un monto numérico es solo el
número). Si el LLM afirma `pago.recibido = true` sin esa frase, se degrada a
«no lo sé» y se pregunta. Una corrección humana de ese hecho manda sobre la
guarda.

**Bóveda de errores e informe semanal.** `scripts/informe_cerebro_errores.py`
genera un markdown con, por cada dictado corregido: transcripción, hechos,
acciones propuestas, qué corrigió quién, ejecuciones y vocabulario aprendido,
más «qué revisar». Lo lee Abelito para decidir si el problema es STT, prompt,
normalizador o compilador. Solo lee.

**Alternativa descartada.** Reescribir el borrador en sitio (UPDATE) para
«dejar limpio» el resultado: rompe la auditoría y el `payload` inmutable de
085. Se prefiere cadena de versiones.

### 3.5 Tareas internas con reloj (2026-11-15)

Un audio puede dar una instrucción a alguien del equipo sin teléfono: «que
revisen en secretaría cómo van los despachos», «verifica que el depósito ya esté
hecho». No es un WhatsApp; es una tarea interna y el seguimiento vive en el CRM.

**Cómo se decide (determinístico, sin LLM).** Si hay `tarea.telefono`, o el
destinatario nombrado es un contacto del cliente con teléfono, va
`crear_tarea_recordatorio` (WhatsApp). Si no hay teléfono y el dictado nombra un
área (`SECRETARIA`, `BODEGA`, `CONTADORA`, `VENDEDOR`), una persona sin
teléfono, o un verbo de encargo («que revisen», «verifica», «que confirme»), va
`crear_tarea_interna`. Nunca se inventa un número para convertir una tarea
interna en WhatsApp.

**Los tres momentos, cada uno con su hora** (migración **088**,
`cerebro_tareas_internas` + `cerebro_tareas_internas_eventos` append-only):

| Paso | Qué registra | Quién |
|---|---|---|
| **Notificada** | el sistema dejó el aviso en el panel y arranca el reloj | el humano que confirmó el borrador; el aviso lo deja el sistema |
| **Resuelta** / **Justificada** | se hizo, o por qué no hacía falta / no se pudo; la nota es obligatoria | quien la atiende |
| **Registrada** | cierre **con metadatos** (referencia, comprobante, comentario) | quien la atiende o supervisa |

`v_cerebro_tareas_internas` calcula `minutos_hasta_resolucion`,
`minutos_hasta_registro`, `minutos_abierta` y `vencida_24h`. Así se sabe cuánto
tardó de verdad, sin que nadie lo declare.

**No se saltan pasos.** `NOTIFICADA → RESUELTA|JUSTIFICADA → REGISTRADA`. El
registro sin resolución y la resolución sin nota se rechazan con 422/409.

**Dónde se ve.** `GET /cerebro/tareas/pendientes` devuelve también `internas`;
el panel las muestra en **un aviso fijo arriba** (siempre visible mientras haya
tareas abiertas, con el conteo y los minutos de la más antigua, sin depender de
`localStorage`), en la campanita y en el popout, con botones **Resolver**,
**Justificar** y **Registrar con metadatos**. El popout se puede cerrar o quedar
minimizado; el aviso fijo no. En el laboratorio, el popout de confirmación
distingue «Tarea interna» de «Tarea programada».

**Decisión.** La tabla es propia (no se reutiliza `gato_recordatorios`) porque
una tarea interna no tiene teléfono ni despachador, y su ciclo de vida es otro.
Alternativa descartada: usar el teléfono de Secretaría y fingir un WhatsApp, que
no mediría el trabajo ni dejaría el rastro de la nota y los metadatos.

## 4. Catálogo de acciones (MVP)

Solo estas nueve. Toda acción pasa por borrador + confirmación humana.

| Acción | Destino real | Rol mínimo |
|---|---|---|
| `crear_o_actualizar_cliente` | `services/clients.py` | SUPERADMIN, SECRETARIA, VENDEDOR |
| `crear_cotizacion_borrador` | `services/cotizaciones.py` | SUPERADMIN, SECRETARIA, VENDEDOR |
| `enviar_cotizacion_whatsapp` | cotizaciones + M1 | SUPERADMIN, SECRETARIA, VENDEDOR |
| `solicitar_ubicacion_whatsapp` | M1 outbox | SUPERADMIN, SECRETARIA, VENDEDOR |
| `registrar_abono_cliente` | Custodio `REGISTER_CLIENT_PAYMENT` | SUPERADMIN, SECRETARIA, CONTADORA |
| `registrar_traslado_caja_banco` | Custodio `REGISTER_CASH_TO_BANK_TRANSFER` (nuevo) | SUPERADMIN, CONTADORA |
| `registrar_gasto_caja` | Custodio `REGISTER_EXPENSE` | SUPERADMIN, SECRETARIA, CONTADORA |
| `crear_tarea_recordatorio` | `gato_recordatorios` (Gato) | SUPERADMIN, SECRETARIA |
| `registrar_hecho_carpeta` | `client_facts` | SUPERADMIN, SECRETARIA, VENDEDOR, CONTADORA |

**Regla de oro:** el Cerebro no ejecuta `INSERT` de negocio. Llama al mismo
servicio que el panel. Si el servicio no existe (cotizaciones, clientes), se
extrae primero y se prueban las dos rutas.

## 5. Estados

**Voz:** `PENDIENTE → PROCESANDO → COMPLETADO | FALLIDO | DEGRADADO_SIN_CREDENCIAL`.
Reintento crea `intento_num + 1`; nunca se reescribe el intento anterior.

**Borrador:** `PENDIENTE_CONFIRMACION` (o `REQUIERE_ACLARACION`) →
`CONFIRMADO` → `EJECUTADO | ERROR_EJECUCION`; corrección crea `version + 1` y
marca el anterior `SUPERADO_POR_CORRECCION`; rechazo deja `RECHAZADO`.

## 6. Permisos, cuotas y degradación

- Módulos ACL nuevos: `voz` y `cerebro` (arrancan en `false` para todos; Julio
  los habilita por perfil en Superadmin).
- Oír un audio de cliente: SUPERADMIN, SECRETARIA, CONTADORA, AUDITOR_EXTERNO;
  VENDEDOR solo si él lo creó. BODEGA y CHOFER: 403.
- Sin `STT_API_KEY`: el audio se guarda igual y queda
  `DEGRADADO_SIN_CREDENCIAL`; la API responde 503 explicando que el archivo
  está a salvo. No se inventa una transcripción.
- Sin clave del LLM: el sobre no se genera; se avisa y se conserva el texto.
- Cuota diaria: `VOZ_CUOTA_USD_DIA_LIVE` y `WA_MINERIA_USD_DIA` nacen `null`
  (`PENDIENTE`). Hasta que Dirección fije el tope, el sistema no bloquea por
  gasto, pero **sí registra** el costo por audio y por extracción.

## 7. Fases y criterio de salida

| Fase | Entrega | Criterio de salida |
|---|---|---|
| 0 | `services/cotizaciones.py` y `services/clients.py` extraídos; panel y tests siguen verdes | suite completa en verde y el panel crea/edita igual que antes |
| 1 | migración 085 + `app/voz/` (ingesta, normalizador, adaptador STT con degradación) | audio sube, se hashea, se normaliza y sobrevive sin proveedor; tests de cédula/teléfono/números en verde |
| 2 | `app/cerebro/` + borradores + UI de confirmación en panel | 3 casos del brief generan borradores correctos; cero escrituras sin confirmar |
| 3 | `client_facts` + timeline + minería (requiere entrantes de WhatsApp) | expediente reconstruido de 5 clientes sin duplicar hechos |
| 4 | cuotas, observabilidad y credenciales reales | suite + candados en verde con carga simulada |

### 7.1 Cómo se mide (antes de escribir el Cerebro)

| Qué | Cómo | Gate |
|---|---|---|
| Tasa de invención | 0 casos en el `held-out` | 0 observados y cota superior 95 % ≤ 3/n |
| Montos | exact match en `Decimal` | 0 errores; con n < 300 se reporta la cota, no «100 %» |
| Cédula / teléfono | exact match + CER de dígitos | ≥ 95 % y CER < 2 % |
| Cliente | Precision@1 contra Sabueso | ≥ 92 % y **0 falsos match** |
| Consulta vs orden | 0 órdenes creadas desde una consulta | 100 % en el set |
| Corrección humana | borradores editados antes de confirmar | ≤ 20 % |
| Tiempo | p50 panel vs línea base manual | ≤ 25 s y < 70 % del manual |

**Estadística honesta.** Con 60 audios, «0 invención» significa «≤ 5 % con 95 %
de confianza» (regla de tres). Para afirmar ≤ 1 % hacen falta ~300 casos. El
gold set se dimensiona **por campo**, no por audio total: si solo 25 audios
traen monto, la cota para montos es mucho más ancha.

**Acuerdo entre anotadores.** κ de Cohen es sensible a la prevalencia: con
campos obvios y pocos casos difíciles puede verse bajo aunque el acuerdo sea
alto. Se reporta también PABAK/AC1 y el acuerdo en los campos críticos. Con 20
audios el intervalo de κ es demasiado ancho para decidir.

## 8. Riesgos residuales

1. **Sin login**, el puente `X-Panel-User` sigue siendo suplantable en la red
   interna. No exponer a Internet antes del login.
2. **El saldo de caja 1101 puede no reflejar todo el efectivo** (hay pagos con
   `bolsa` y movimientos que no pasan por el ledger). Antes de habilitar el
   traslado caja→banco hay que probarlo contra un cierre real.
3. **Confirmar un audio mal transcrito y plausible.** El resumen del borrador
   debe mostrar los campos críticos primero y exigir lectura; no hay forma de
   evitarlo al 100 %.
4. **Costo del LLM por audio** no está medido. Se registra desde el día uno
   para decidir con datos, no con estimaciones.
5. **Retención de audio y consentimiento** siguen sin política aprobada
   (LOPDP). El diseño permite anonimizar; no lo asume.
6. **Los offsets no sobreviven a la normalización.** Hasta que
   `normalizar_ec` devuelva el mapa `normalizado → crudo → tiempos STT`, el
   modelo de evidencia es una intención, no una capacidad. Es el primer
   trabajo de la Fase 2.
7. **Sin conexión en planta.** El STT es un servicio externo; si no hay red, el
   audio debe quedar en cola local y procesarse después. No está diseñado.
8. **Carga de revisión.** Si entran 40 audios al día, alguien tiene que revisar
   40 borradores. El modo sombra mide el tiempo, pero no la fatiga ni la
   capacidad de la secretaria en un día de cierre.
9. **Error de cara al cliente.** Una cotización mal emitida no solo cuesta
   dinero: cuesta confianza. El costo asimétrico incluye reputación, no solo
   contabilidad.
10. **El LLM no es determinístico.** Aunque se use temperatura 0, el mismo audio
    puede producir sobres distintos. La evaluación debe correr el mismo caso
    varias veces y medir la varianza, no una sola pasada.

## 9. Pendientes de Dirección (negocio, no bloquean Fase 2)

1. Tope diario real de gasto de voz y minería (USD). Hoy ambos están `null`.
2. ¿Se conserva el audio 24 meses, se archiva o se borra? ¿Con qué aviso al
   cliente?
3. ¿Autoriza Deepgram como proveedor primario o solo OpenAI Whisper?
4. Precios oficiales de las recetas: hoy las cinco están `PROVISIONAL`, así que
   el envío fuera de SANDBOX queda bloqueado por diseño.
5. **Matriz de costo por error**: cuánto cuesta un monto mal confirmado, un
   cliente equivocado y una pregunta extra. Sin esos números los umbrales son
   hipótesis.
6. **Asignación de cartera**: el diseño externo limita al VENDEDOR a «sus»
   clientes, pero hoy no existe `vendedor_id` en `clients`. O se agrega el
   modelo o se elimina esa restricción.
7. **Golden set y consentimiento**: quién firma el uso de audios reales, dónde
   se guarda el corpus y cómo se atiende un pedido de borrado.
