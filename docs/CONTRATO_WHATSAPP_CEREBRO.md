# Contrato de integración — WhatsApp ↔ Cerebro ↔ CRM

> **Para qué sirve.** Definir, antes de construir el canal, cómo se identifican
> los mensajes, las conversaciones, las correcciones, las confirmaciones y las
> tareas, para que **el panel y WhatsApp usen el mismo Cerebro** y no haya dos
> lógicas ni dos verdades.
>
> **Estado:** documento de contrato. El panel ya cumple este contrato; la fase
> de WhatsApp lo implementará. **Fecha:** 2026-11-15.

---

## 1. Principio

**Un solo Cerebro, dos canales.** Lo que cambia entre el panel y WhatsApp es el
transporte, no la lógica:

- la interpretación produce **hechos con cita**;
- la corrección crea una **versión nueva**;
- la confirmación es de un **humano identificado**;
- la tarea se crea **una sola vez** por clave;
- la ejecución la hace el **módulo dueño** (recordatorios, clientes, caja).

Ningún canal escribe datos de negocio por su cuenta.

---

## 2. Actores

| Actor | Qué puede hacer |
|---|---|
| **Julio (SUPERADMIN)** | dictar, corregir, confirmar, cancelar, preguntar estado, escalar |
| **Secretaría** | ver y acusar tareas, resolver o justificar, registrar metadatos |
| **Otros roles** | según `panel_users_acl` y el riesgo de la acción |
| **Cerebro** | interpretar, proponer, preguntar, medir; **no** ejecuta dinero |
| **Módulos** | ejecutar lo que se les pide y devolver un resultado explícito |

---

## 3. Sobre del mensaje entrante

Todo mensaje que entra al Cerebro —venga del panel o de WhatsApp— se describe
con los mismos campos:

| Campo | Tipo | Qué es | De dónde sale |
|---|---|---|---|
| `mensaje_id` | uuid | identificador interno, único | lo genera el CRM |
| `wa_message_id` | texto único | id del proveedor (Evolution) | webhook |
| `canal` | `PANEL` \| `WHATSAPP` \| `AUDIO` | por dónde entró | webhook / panel |
| `remitente_id` | uuid | usuario del panel o contacto identificado | identidad M1 |
| `remitente_rol` | texto | rol autorizado | `panel_users_acl` |
| `telefono_origen` | texto | número del que escribe (si aplica) | webhook |
| `conversacion_id` | uuid | hilo al que pertenece | M1 / CRM |
| `asunto_id` | uuid | solicitud o encargo al que responde | Cerebro |
| `responde_a` | uuid | mensaje que corrige o confirma | Cerebro |
| `tipo` | `NUEVA` \| `CORRECCION` \| `CONFIRMACION` \| `CANCELACION` \| `PREGUNTA` | intención del mensaje | Cerebro |
| `texto` / `audio_ref` | texto / uuid | contenido | webhook |
| `hash_contenido` | texto | huella del audio o texto | ingesta |
| `recibido_en` | timestamp | hora del proveedor | webhook |
| `procesado_en` | timestamp | hora del Cerebro | Cerebro |

**Regla:** un `mensaje_id` no se procesa dos veces. Si llega repetido, se
devuelve el resultado anterior; no se crea otra solicitud.

---

## 4. Conversación y asunto

- **Conversación:** agrupa mensajes de un mismo remitente en un período corto.
- **Asunto:** es la **solicitud** concreta dentro de la conversación. Un audio
  con tres encargos produce **tres asuntos**.
- Cada asunto tiene su **borrador** y su **versión**. Corregir un asunto **no
  toca** los otros.
- Si un mensaje es ambiguo («no, el otro»), el Cerebro pregunta a qué asunto se
  refiere en vez de adivinar.

**Regla de oro:** la corrección se aplica al **último asunto abierto del mismo
remitente**, salvo que el mensaje nombre otro. Si hay dos asuntos abiertos y la
corrección puede aplicar a ambos, se pregunta.

---

## 5. Interpretación y versiones

| Concepto | Identificador | Regla |
|---|---|---|
| Extracción | `extraccion_id` | una por mensaje/asunto; guarda el sobre con hechos citados |
| Borrador | `borrador_id` + `version` | la corrección crea `version + 1` y marca el anterior `SUPERADO_POR_CORRECCION` |
| Hecho | `clave` dentro del sobre | si el estado es `TENTATIVO`, no decide |
| Corrección | `correccion_id` | fila nueva; nunca reescribe |

**Una confirmación vale solo para la versión que cita.** Si el borrador cambió
después, la confirmación se rechaza y se pide confirmar la versión nueva.

---

## 6. Delegación: tarea y ejecución

### 6.1 Tarea

| Campo | Qué es |
|---|---|
| `tarea_id` | id en `cerebro_tareas_internas` o `gato_recordatorios` |
| `tipo` | `INTERNA` o `WHATSAPP` |
| `origen` | mensaje, extracción y borrador que la originaron |
| `responsable` | rol y, si se sabe, persona |
| `ficha` | tipo, cliente, monto de referencia, pendientes, resultado esperado |
| `prioridad` | `NORMAL` / `URGENTE` |
| `plazo_en` | fecha límite |
| `estado` | NOTIFICADA → RESUELTA / JUSTIFICADA → REGISTRADA |
| `clave_externa` | evita duplicados |

### 6.2 Ejecución (módulo dueño)

El módulo que ejecuta devuelve **siempre** un resultado explícito:

| Campo | Valores |
|---|---|
| `estado` | `OK` \| `RECHAZADO` \| `FALTA_DATO` \| `ERROR_TECNICO` \| `DESCONOCIDO` |
| `mensaje` | texto legible para el humano |
| `datos` | id del objeto creado y estado real |
| `reintentable` | sí/no |

**Prohibido:** cambiar en silencio una hora, un destinatario o un monto. Si no
se puede cumplir como se pidió, se devuelve `RECHAZADO` o `FALTA_DATO`.

---

## 7. Idempotencia y efectos externos

1. **Entrada:** `mensaje_id` y `wa_message_id` únicos.
2. **Tarea:** `clave_externa` = hash de `borrador + acción + versión`.
3. **Confirmación repetida:** devuelve la ejecución existente, no crea otra.
4. **Envío externo con respuesta perdida:** el mensaje queda en estado
   `ENVIANDO` con su `request_id`. Antes de reintentar se consulta el proveedor:
   - si el proveedor dice **enviado**, se marca `ENVIADO` y no se reenvía;
   - si dice **no enviado**, se reintenta;
   - si no se puede saber, queda `DESCONOCIDO` y **se avisa a un humano**; no se
     reintenta a ciegas.
5. **Nunca** se borra una tarea porque el envío falló.

---

## 8. Permisos por riesgo

| Riesgo | Ejemplo | Quién | Confirmación |
|---|---|---|---|
| Bajo | tarea interna, nota | Secretaría | una |
| Medio | recordatorio de WhatsApp a un tercero | Secretaría / Julio | una, con destinatario y hora |
| Alto | crear cliente, cotización | Julio / Secretaría / Vendedor | una, con datos completos |
| Crítico | abono, traslado de caja | Julio / Contadora | **doble** |

Tener el número de Julio **no** autoriza todo: el rol y el riesgo se validan en
el backend, no en el canal.

---

## 9. Consulta de estado («¿qué pasó con lo de ayer?»)

El Cerebro responde con datos reales de las tareas, no con una promesa:

- tareas del período, con estado y minutos;
- qué se avisó, qué se acusó, qué se resolvió y qué quedó sin atender;
- quién es el responsable actual;
- si algo se escaló.

La consulta es **de solo lectura** y usa las mismas vistas que el panel
(`v_cerebro_tareas_internas`).

---

## 10. Correspondencia con lo ya construido

| Contrato | Hoy |
|---|---|
| `mensaje_id`, `wa_message_id` | existen en `chat_mensajes` para salientes; **falta persistir entrantes** |
| `conversacion_id` | existe `chat_conversaciones`; falta enlazar con el Cerebro |
| `extraccion_id`, `borrador_id`, `version` | `cerebro_extracciones`, `cerebro_borradores` |
| `correccion_id` | `cerebro_correcciones` |
| `tarea_id` interna | `cerebro_tareas_internas` |
| `tarea_id` WhatsApp | `gato_recordatorios` |
| `ejecución` | `cerebro_ejecuciones` |
| `acuse / vista / escalada` | `vista_en`, `acusada_en`, `escalada_en` |
| `vocabulario aprendido` | `v_cerebro_vocabulario` + `cerebro_vocabulario_retiros` |

---

## 11. Lo que debe implementar la fase de WhatsApp

1. **Persistir los entrantes** en `chat_mensajes` (hoy no se guardan) con
   `wa_message_id` único y el hash del audio.
2. **Resolver la identidad** del remitente contra `panel_users_acl` y `clients`.
3. **Abrir o reutilizar** la conversación y crear el asunto por mensaje.
4. **Llamar a las mismas operaciones** de interpretar, corregir y confirmar que
   usa el panel.
5. **Responder en lenguaje natural** con el resumen y las preguntas; nunca con
   JSON ni códigos.
6. **Consultar tareas** para responder «¿qué pasó con lo de ayer?».
7. **Probar** los escenarios A, H y J del documento de auditoría, que hoy no se
   pueden cerrar sin este canal.

---

## 12. Invariantes que no se negocian

1. Ningún dato sin cita (salvo una corrección humana explícita).
2. Ninguna escritura de negocio sin confirmación humana.
3. Ningún dinero calculado por la IA ni registrado sin doble confirmación.
4. Ninguna corrección reescribe el pasado: se agrega.
5. Ninguna tarea se duplica por reintento o mensaje repetido.
6. Ningún canal tiene privilegios distintos: la autorización vive en el backend.
7. Si el sistema no sabe, pregunta. Si no puede, lo dice.
