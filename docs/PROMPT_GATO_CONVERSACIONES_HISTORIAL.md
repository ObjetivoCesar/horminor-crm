# Brief para implementar la memoria e historial de Gato

> **Para quién es este documento:** para el modelo de IA que va a implementar la
> funcionalidad. No es documentación para el usuario final ni un resumen
> comercial. Es un contrato de trabajo con contexto, estado real del código,
> decisiones ya tomadas por Julio y criterios de aceptación.
>
> **Regla:** si algo no está aquí, no se inventa. Se pregunta.

---

## Parte I — La visión de Julio, en sus palabras

Yo, Julio, quiero que Gato sea un asistente con **memoria de verdad**, no un
chat que se olvida o que mezcla operaciones.

Lo que quiero es esto:

- Abro Gato y veo **la última conversación** que tenía. Si no la he cerrado,
  sigue ahí, con su historial. No quiero una ventana vacía que me haga creer que
  empecé de cero cuando en realidad el sistema sigue en la conversación
  anterior.
- El botón de **refresh/cerrar** termina la conversación y abre una nueva vacía.
  La anterior queda guardada en el historial.
- Puedo dictar un audio, Gato lo transcribe, me muestra **lo que entendió** y yo
  digo **«confirmado»**. En ese momento se crea el cliente, se registran las
  tareas y **todo queda en la base**, con la conversación, el borrador y el
  cliente relacionados.
- Si sigo en la misma conversación y digo «me acaba de dar el efectivo», Gato
  entiende que hablo de la operación anterior y no me vuelve a preguntar el
  cliente ni el monto.
- Pero si empiezo una **operación nueva** —aunque sea el mismo cliente— no
  quiero que arrastre la operación anterior. Ejemplo real: primero fueron 7 m³
  con 300 USD en efectivo; después fueron 7 m³ con 200 USD por transferencia.
  Son dos operaciones distintas y no se pueden mezclar.
- Si me olvido del proceso y digo «por cierto, ya me cancelaron los 300 dólares,
  regístralo», Gato debe **preguntarme de qué cliente hablo** si no está claro.
  Le contesto «el de la escuela», busca en el historial, extrae los datos de esa
  conversación y **toma contexto** para registrar el pago o avisar a
  secretaría.
- Quiero un **historial de todas las conversaciones de Gato**. Hoy el historial
  está en la base, pero la pantalla no lo muestra; por eso parece que no existe.
  Si empiezo en el celular y luego abro la laptop, debo ver la misma
  conversación. No puede depender del `localStorage` de un navegador.
- Quiero poder pedir «dame viendo lo que te indiqué acerca de la escuela del
  otro día» y que Gato **busque por filtros** —nombre, fecha, ubicación, estado,
  texto— y me diga «tengo 3 conversaciones sobre eso, ¿cuál quieres ver?». La
  gente habla feo; la búsqueda tiene que aguantar errores de voz, nombres
  aproximados y fechas relativas.
- **Solo Julio, desde el Superadmin**, puede ver el historial de conversaciones
  de Gato. Los demás perfiles no.
- Los datos de prueba son ficticios y se pueden borrar. No hay que conservar los
  borradores contaminados.

En resumen: **Gato necesita una conversación con principio y final, historial
persistente en base, relación con el cliente y búsqueda tolerante a errores.**
Eso es lo que quiero construir.

---

## Parte II — Lo que ya existe en código (verificado)

> Esto no es una propuesta: es lo que hay hoy. El implementador debe leerlo
> antes de cambiar nada.

### 2.1 Memoria actual de Gato

- Tabla `gato_turnos` (migración 074):
  - `id`, `conversacion_id`, `actor_id`, `rol_actor`, `pregunta`,
    `respuesta`, `estado`, `created_at`.
- `app/asistente/memoria.py`:
  - `LIMITE_TURNOS = 8`.
  - `cargar(pool, conversacion_id, actor_id)` devuelve los últimos turnos;
    lanza `PermissionError` si la conversación es de otro actor.
  - `guardar(...)` inserta un turno.
- El frontend guarda el `conversacion_id` en
  `localStorage['horminor.gato.conv.<uid>']`.
- **El panel no pinta los turnos guardados.** Al abrir Gato muestra el saludo
  vacío, aunque el backend siga usando la conversación anterior. Esa es la
  causa de la confusión: la pantalla miente.
- El botón de refresh (`gatoNuevaConversacion`) borra la clave de
  `localStorage`, limpia el hilo visual y deja que el próximo mensaje cree un
  UUID nuevo. **No cierra ni registra nada en la base.**

### 2.2 Cerebro

- `cerebro_borradores` (migraciones 085, 086, 091, 092):
  - `id`, `extraccion_id`, `borrador_padre_id`, `version`, `estado`,
    `acciones_propuestas_json`, `preguntas_pendientes_json`,
    `condiciones_json`, `encargos_json`, `creado_por`, `creado_en`.
  - **No tiene `conversacion_id` ni `cliente_id`.**
- `cerebro_extracciones`: guarda `texto_directo`, `sobre_json`,
  `usuario_solicitante`, `rol_base_solicitante`, `modelo_llm`,
  `version_prompt`, etc.
  - **No tiene `conversacion_id`.**
- `cerebro_ejecuciones`: guarda la acción confirmada, el `borrador_id`, el
  resultado y la entidad destino. **No tiene `conversacion_id`.**
- `cerebro_tareas_internas` (migración 088):
  - `id`, `clave_externa`, `instruccion`, `asignado_rol`, `asignado_a`,
    `asignado_a_id`, `origen`, `extraccion_id`, `borrador_id`, `cita`,
    `hablante`, `estado`, `prioridad`, `plazo_en`, etc.
  - **No tiene `cliente_id`.** Por eso una tarea interna no se puede buscar
    «por cliente» de forma directa.
- `gato_recordatorios` (migración 075) **sí tiene** `conversacion_id` y
  `cliente_id`. Los recordatorios ya están ligados a cliente y conversación.

### 2.3 El puente Gato → Cerebro

- `app/asistente/cerebro_bridge.py`:
  - `interpretar(...)` envía el dictado a `POST /api/v1/cerebro/interpretar`.
  - `mensaje_de_resumen(...)` arma el resumen markdown que se ve en Gato.
- `app/asistente/router.py`:
  - `_contexto_dictado(historial)` toma los últimos dictados de la conversación
    y los manda como `contexto`.
  - `chat_audio` transcribe y pasa el texto como `dictado:` por defecto.
- `app/cerebro/router.py`:
  - `InterpretarIn` acepta `contexto`.
  - Si hay `contexto`, concatena contexto + texto nuevo y compila.
  - `continuacion_desde` asigna los hechos nuevos al último encargo previo.
- **Problema actual:** como no hay cierre de conversación, `_contexto_dictado`
  toma los últimos 5 dictados **para siempre**. Eso arrastra operaciones viejas
  a dictados nuevos.

### 2.4 Panel

- `app/web/templates/panel.html`:
  - Widget de Gato: `#gato-panel`, `#gato-hilo`, `#gato-input`, `#gato-mic`.
  - `gatoSesion()` arma `X-Panel-User` desde `localStorage` o `#sim-user`.
  - `gatoEnviar()` envía texto a `/api/v1/asistente/chat`.
  - `gatoEnviarAudio()` envía `multipart` a `/api/v1/asistente/audio` con
    `modo=dictado`.
  - `gatoNuevaConversacion()` limpia el hilo y el `localStorage`.
  - `cargarPerfilesUI()` llena «Viendo como» con los perfiles.
- La opción «Julio (base Superadmin)» ya lleva el UUID real de Julio; si una
  pestaña vieja manda solo el rol, el puente usa el perfil base.
- `panel_acl.py` resuelve el perfil por `X-Panel-User`; sin cabecera usa
  `PERFIL_DEFECTO` (Julio, todos los módulos).

### 2.5 Lo que ya funciona y no se debe romper

- Transcripción de audio con Groq (`app/voz`).
- Dictado al Cerebro con `dictado:` y con el micrófono.
- Formato markdown del resumen en Gato (negritas, viñetas, saltos).
- Citas, leads, WhatsApp, tareas internas, recordatorios y el resto del CRM.
- Suite actual: **744 pruebas en verde** y candados del Hito 1/3.
- Migraciones aplicadas: no se editan; se crea una nueva.

---

## Parte III — El problema exacto que hay que resolver

Caso real del 2026-11-19. El borrador `4dfa77e4-cf58-42bd-a2c9-c2714e1b7cee`
compiló **seis dictados concatenados**:

1. Pastrana, 70 m³, 4.000 USD.
2. «Sí, correcto…» (seguimiento de Pastrana).
3. Escuela Miguel Rofrío, 7 m³, 300 USD en efectivo.
4. «Me acaba de dar en efectivo…».
5. «¿Tienes recuerdo de lo que acabamos de conversar?».
6. **Dictado nuevo:** Escuela Miguel Rofrío, 7 m³, mañana 10:00, 200 USD por
   transferencia.

El resultado mostró Pastrana y los 300 USD otra vez, y el dictado nuevo quedó
como «Encargo 4». La causa: la conversación nunca se cerró y el contexto tomó
los últimos cinco dictados.

**Lo que debe pasar en ese caso:** el dictado 6 es una **operación nueva**,
aunque sea el mismo cliente. Debe abrir un borrador nuevo y no heredar Pastrana
ni los 300 USD. El dictado 4 sí debe continuar el borrador 3 porque responde
una pregunta pendiente.

---

## Parte IV — Decisiones ya tomadas por Julio

Estas son decisiones cerradas. No se reinterpretan:

1. **La conversación se cierra solo con el botón de refresh/cerrar.** Si no se
   cierra, al abrir Gato se muestra la última conversación.
2. **Al abrir Gato se muestra la última conversación.** No una ventana vacía.
3. **Solo Julio, desde el Superadmin, puede ver el historial de conversaciones.**
4. **Para continuar una conversación hay que pedirla.** Ejemplo: «por cierto, ya
   me cancelaron los 300 dólares, regístralo». Si no está claro, Gato pregunta
   «¿de qué cliente?». El usuario responde «el de la escuela». Gato busca en el
   historial, extrae los datos de esa conversación y toma contexto para
   registrar el pago o avisar a secretaría.
5. **Los datos actuales son ficticios y se pueden borrar.** No hay que preservar
   los borradores contaminados.

---

## Parte V — Lo que se quiere obtener

### 5.1 Entidad conversación

Crear una entidad real de conversación de Gato, con:

- `id`
- `actor_id` y `rol`
- `abierta_en`
- `cerrada_en` (NULL mientras esté abierta)
- `titulo` o resumen corto
- `ultimo_turno_en`
- `cliente_id` (opcional, cuando se resuelva)

La conversación es la dueña del hilo. `gato_turnos` sigue guardando los
mensajes, pero ahora con una cabecera que dice si está abierta o cerrada.

### 5.2 Al abrir Gato

- Cargar la **última conversación** del actor (la más reciente), esté abierta o
  cerrada.
- Si está abierta, mostrar su historial completo en el panel.
- Si está cerrada, mostrarla como historial y dejar el botón de refresh para
  abrir una nueva. La regla de Julio: «si no se cierra, se muestra la última
  conversación».
- Nunca mostrar una ventana vacía mientras el backend tenga una conversación
  abierta.
- En el celular y en la laptop debe verse la misma conversación: la fuente es
  la base, no `localStorage`.

### 5.3 Refresh / cerrar

- El botón de refresh cierra la conversación actual (`cerrada_en = now()`),
  guarda un resumen/título y abre una nueva vacía.
- La conversación cerrada queda en el historial.
- El refresh no borra datos: solo cierra y empieza otra.
- Si el usuario vuelve a abrir Gato, ve la nueva conversación abierta.

### 5.4 Dictar y confirmar

- El audio se transcribe y se entrega al Cerebro como hoy.
- El borrador creado guarda `conversacion_id` y, cuando se resuelva,
  `cliente_id`.
- El turno de Gato guarda el `borrador_id` para que el historial pueda mostrar
  «mensaje → borrador → acciones».
- Cuando Julio dice «confirmado» en Gato:
  - Se ejecuta la acción pendiente del borrador (crear cliente, tarea,
    recordatorio, etc.).
  - Se registra en `cerebro_ejecuciones`.
  - Se registra el turno en `gato_turnos`.
  - El historial muestra el resultado y deja de mostrar la pregunta pendiente.
- Si la confirmación es ambigua, Gato pregunta antes de ejecutar. No inventa.

### 5.5 Tareas y cliente

- Las tareas que se creen desde una conversación deben quedar ligadas al
  **cliente** y al **borrador**.
- `cerebro_tareas_internas` necesita `cliente_id` (hoy no lo tiene).
- `gato_recordatorios` ya tiene `cliente_id` y `conversacion_id`; se debe
  aprovechar.
- El historial debe poder responder: «tareas de la escuela Miguel Rofrío»,
  «recordatorios del cliente X», etc.

### 5.6 Historial y búsqueda

- Pantalla o panel de historial de conversaciones, visible solo para Julio
  desde el Superadmin.
- Filtros mínimos:
  - cliente / nombre aproximado,
  - fecha o rango («ayer», «el otro día», «la semana pasada»),
  - ubicación u obra,
  - estado (abierta, cerrada, con borrador, confirmada, con tareas),
  - texto libre.
- Resultados con: fecha, cliente, resumen, monto/volumen si aplica, estado,
  cantidad de tareas/recordatorios y un botón «ver».
- Al elegir una conversación, se carga el hilo y sus borradores/acciones.
- Gato debe poder usar esa búsqueda como herramienta: «tengo 3 conversaciones
  sobre la escuela, ¿cuál quieres ver?».
- La búsqueda debe tolerar errores de voz y nombres aproximados. Reutilizar el
  buscador de clientes/Sabueso que ya existe; no crear otro normalizador si se
  puede evitar.

### 5.7 Continuidad y no contaminación

Regla propuesta, a validar con los casos:

- **Un dictado nuevo abre una operación nueva por defecto.**
- Solo continúa el borrador anterior si:
  - el borrador anterior tiene una pregunta pendiente y el nuevo texto es una
    respuesta corta («sí», «correcto», «me acaba de dar…»), o
  - el usuario pide explícitamente continuar («continúa», «corrige»,
    «agrégale», «es el mismo»).
- Si el dictado nuevo trae cliente, volumen, fecha o monto nuevos, abre un
  borrador nuevo aunque sea el mismo cliente.
- El contexto del borrador caduca cuando se confirma, cancela o ejecuta.
- El botón de refresh cierra también el contexto del Cerebro.

---

## Parte VI — Historias de aceptación

El implementador debe convertir estas historias en pruebas automatizadas y, si
aplica, en pruebas manuales con evidencia.

### Historia A — Abrir Gato

- Julio abre Gato en la laptop.
- Ve la última conversación con sus mensajes y borradores.
- No ve una ventana vacía si hay una conversación abierta.
- Abre Gato en el celular y ve la misma conversación.

### Historia B — Refresh

- Julio pulsa refresh.
- La conversación actual se cierra y queda en el historial.
- La ventana queda vacía y lista para una conversación nueva.
- Al recargar, la conversación nueva sigue abierta y la anterior aparece en el
  historial.

### Historia C — Pastrana

- Julio dicta: cliente Pastrana, 70 m³ de 240, entrega sábado/domingo, 4.000 USD
  por transferencia, recordatorio al 0963410409, dirección Juan José Peña y
  Mercadillo.
- Gato muestra «Lo que entendí».
- Julio dice «confirmado».
- Se crea el cliente Pastrana, se registran las tareas/recordatorios y todo
  queda en el historial de esa conversación.

### Historia D — Continuidad del efectivo

- En la misma conversación, Julio dicta 7 m³ para la escuela, 300 USD en
  efectivo.
- Gato pregunta si los 300 USD ya entraron.
- Julio responde «sí, me acaba de dar en efectivo».
- Gato conserva cliente, volumen y monto; marca el pago como recibido; no vuelve
  a preguntar cliente ni monto.

### Historia E — Operación nueva del mismo cliente

- En la misma conversación, Julio dicta: escuela Miguel Rofrío, 7 m³ de 210,
  entrega mañana 10:00, 200 USD por transferencia, recordatorio al 0963410409.
- Gato **no** arrastra Pastrana, ni los 70 m³, ni los 300 USD.
- Abre un borrador nuevo de 200 USD por transferencia, aunque sea el mismo
  cliente.

### Historia F — «Ya me cancelaron los 300 dólares»

- Julio dice: «por cierto, ya me cancelaron los 300 dólares, regístralo».
- Gato pregunta «¿de qué cliente?» porque no está claro.
- Julio responde «el de la escuela».
- Gato busca en el historial, encuentra la conversación de la escuela, extrae
  los datos, toma contexto y registra el pago o avisa a secretaría.
- El historial muestra la acción y su resultado.

### Historia G — Buscar «la escuela del otro día»

- Julio pide: «dame viendo lo que te indiqué acerca de la escuela del otro día».
- Gato busca por nombre aproximado y rango de fechas.
- Responde: «tengo 3 conversaciones sobre la escuela Miguel Rofrío…».
- Julio elige una y Gato carga el hilo.

### Historia H — Permisos

- Julio entra al Superadmin y ve el historial.
- Secretaría no ve el historial de Gato.
- Un perfil sin Voz/Cerebro no puede dictar; recibe el aviso claro.

---

## Parte VII — Modelo de datos mínimo propuesto

> El implementador puede ajustar nombres, pero no puede omitir la relación
> conversación ↔ borrador ↔ cliente ↔ tareas.

```sql
CREATE TABLE gato_conversaciones (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id text NOT NULL,
    rol_actor text NOT NULL,
    abierta_en timestamptz NOT NULL DEFAULT now(),
    cerrada_en timestamptz NULL,
    titulo text NULL,
    resumen text NULL,
    ultimo_turno_en timestamptz NOT NULL DEFAULT now(),
    cliente_id uuid NULL REFERENCES clients(id) ON DELETE SET NULL,
    metadatos jsonb NOT NULL DEFAULT '{}'::jsonb
);

ALTER TABLE cerebro_borradores
    ADD COLUMN conversacion_id uuid NULL REFERENCES gato_conversaciones(id),
    ADD COLUMN cliente_id uuid NULL REFERENCES clients(id);

ALTER TABLE cerebro_tareas_internas
    ADD COLUMN cliente_id uuid NULL REFERENCES clients(id);
```

Reglas:

- `gato_turnos.conversacion_id` debe apuntar a `gato_conversaciones.id`.
- `cerebro_borradores.conversacion_id` permite reconstruir el historial.
- `cerebro_borradores.cliente_id` permite buscar por cliente sin depender del
  JSONB.
- `cerebro_tareas_internas.cliente_id` permite «tareas del cliente X».
- `gato_recordatorios` ya tiene `conversacion_id` y `cliente_id`; no duplicar.
- No editar migraciones aplicadas: crear `0NN_...sql`.

---

## Parte VIII — Flujos que debe implementar

### 8.1 Abrir Gato

1. El panel pide la conversación activa del actor.
2. El backend devuelve la última conversación (abierta o cerrada) y sus turnos.
3. El panel pinta el hilo y los borradores/acciones.
4. Si no hay conversación, crea una nueva.

### 8.2 Enviar audio o texto

1. El panel envía el audio/texto con `conversacion_id`.
2. El backend transcribe si es audio.
3. El Cerebro interpreta y guarda el borrador con `conversacion_id`.
4. El turno se guarda en `gato_turnos` con el `borrador_id`.
5. El panel muestra el resumen.

### 8.3 Confirmar

1. Julio dice «confirmado» o pulsa confirmar.
2. El backend identifica el borrador y la acción pendiente.
3. Ejecuta la acción (cliente, tarea, recordatorio).
4. Registra `cerebro_ejecuciones`.
5. Guarda el turno y actualiza el historial.
6. Si falta un dato, pregunta; no ejecuta a ciegas.

### 8.4 Refresh

1. El panel llama a cerrar conversación.
2. El backend marca `cerrada_en` y genera un resumen/título.
3. El panel limpia el hilo y crea una conversación nueva.
4. La anterior queda disponible en el historial.

### 8.5 Buscar historial

1. Julio pide por cliente/fecha/ubicación/texto.
2. Gato usa la herramienta de búsqueda.
3. El backend filtra y devuelve una lista corta.
4. Gato responde «tengo N, ¿cuál?».
5. Al elegir, se carga la conversación y su contexto.

---

## Parte IX — Permisos y límites

- **Historial:** solo Julio desde el Superadmin. El resto de perfiles no lo ve.
- **Dictado:** requiere los módulos Voz y Cerebro. Si no, aviso claro.
- **Conversación:** pertenece al actor que la inició. Otro actor no puede
  leerla.
- **Datos:** no inventar clientes, montos, fechas, direcciones ni teléfonos. Si
  falta un dato, preguntar.
- **Privacidad:** la búsqueda de historial no debe exponer conversaciones de
  otros clientes ni de otros actores.
- **Retención:** definir con Julio cuánto tiempo se guarda el historial. Mientras
  no se defina, no borrar automáticamente.

---

## Parte X — Criterios de aceptación

El trabajo no se considera terminado hasta que:

1. Existe una conversación real en base, con apertura y cierre.
2. Al abrir Gato se ve la última conversación, no una ventana vacía.
3. Refresh cierra la conversación y abre una nueva.
4. La conversación se ve igual desde otro dispositivo.
5. Un dictado nuevo no arrastra operaciones viejas.
6. Una respuesta corta a una pregunta pendiente sí continúa el borrador.
7. «Confirmado» crea el cliente/tareas y lo registra en el historial.
8. Las tareas quedan ligadas al cliente.
9. El historial se puede buscar por cliente, fecha, ubicación y estado.
10. Gato puede responder «tengo N conversaciones sobre X».
11. Solo Julio ve el historial.
12. Las pruebas existentes siguen en verde y hay pruebas nuevas para cada
    historia.
13. Hay migración, documentación, evidencia y bitácora.
14. No hay placeholders, TODOs ni prototipos a medias.

---

## Parte XI — Prompt de trabajo para el modelo implementador

Copia esta instrucción al inicio de tu trabajo:

> Trabaja en loop: planifica, construye, prueba, revisa, corrige y repite.
> No me entregues la primera versión.
> Usa un árbitro que emplee técnicas adversariales para auditar y criticar el
> trabajo hecho hasta un listón de **producción real**: migración aplicada,
> pruebas automatizadas, permisos, historial cross-device, búsqueda tolerante a
> errores, documentación y evidencia. El árbitro debe buscar fallos de lógica,
> casos límite, contaminación entre conversaciones, fugas de datos y regresiones.
> No uses placeholders ni te detengas en un prototipo básico.

Además:

- Antes de escribir código, lee `AGENTS.md`, `docs/HITOS.md`,
  `docs/CONTINUIDAD_CEREBRO.md`, `.agents/ESTADO.md` y las últimas entradas de
  `.agents/BITACORA.md`.
- Revisa el código real antes de proponer: no confíes en este documento para
  nombres de columnas; verifica las migraciones.
- No edites migraciones aplicadas. Crea una nueva.
- No toques módulos fuera de Gato/Cerebro salvo lo mínimo para las relaciones.
- Si una decisión no está aquí, pregunta. No inventes datos de negocio.
- Cada cambio visible debe explicarse en `docs/HORMINOR_MANUAL_FUNCIONAL.md`.
- La bitácora es append-only.
- Entrega evidencia reproducible: comando + salida real.
- Si el árbitro encuentra un fallo, corrígelo y vuelve a probar. No entregues
  hasta que el árbitro apruebe.

---

## Parte XII — Archivos y rutas relevantes

| Ruta | Qué contiene |
|---|---|
| `services/core-api/app/asistente/router.py` | Chat, audio, puentes, contexto |
| `services/core-api/app/asistente/memoria.py` | Carga/guarda `gato_turnos` |
| `services/core-api/app/asistente/cerebro_bridge.py` | Puente Gato → Cerebro |
| `services/core-api/app/asistente/recordatorios.py` | Recordatorios con cliente/conversación |
| `services/core-api/app/cerebro/router.py` | Interpretar, corregir, confirmar |
| `services/core-api/app/cerebro/extractor.py` | Extracción y contexto |
| `services/core-api/app/cerebro/compilador.py` | Borrador, encargos, acciones |
| `services/core-api/app/web/templates/panel.html` | Widget de Gato y perfiles |
| `services/core-api/app/panel_acl.py` | Perfiles y módulos |
| `db/migrations/074_*.sql` | `gato_turnos` |
| `db/migrations/075_*.sql` | `gato_recordatorios` |
| `db/migrations/085_*.sql` | `cerebro_borradores`, extracciones, ejecuciones |
| `db/migrations/088_*.sql` | `cerebro_tareas_internas` |
| `db/migrations/092_*.sql` | `encargos_json` |
| `tests/test_v227_calendario_gato.py` | Memoria, calendario y permisos |
| `tests/test_v225_h1_cierre.py` | Núcleo comercial |
| `docs/HORMINOR_MANUAL_FUNCIONAL.md` | Manual Vivo |
| `.agents/BITACORA.md` | Historia append-only |

---

## Nota final

El problema no es «que Gato no tenga memoria». La memoria existe en
`gato_turnos`; lo que falta es **mostrarla, cerrarla y relacionarla** con los
borradores, el cliente y las tareas. La solución debe ser una conversación con
ciclo de vida, no un contexto infinito.

Si el implementador encuentra una contradicción entre este documento y el
código, gana el código y se pregunta antes de asumir.
