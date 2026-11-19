# Decisión técnica: memoria e historial de Gato

> **Estado:** decisión tomada por el responsable técnico, después de auditar las
> propuestas de Astra y Gemini Neon contra el esquema real y el código.
> **No es una implementación.** Es el contrato que debe seguir el implementador.
>
> **Fuentes:** `docs/MAPA_TECNICO_BASES_DATOS.md`,
> `docs/MAPA_TECNICO_BASES_DATOS_DDL.sql`,
> `docs/PROMPT_GATO_CONVERSACIONES_HISTORIAL.md` y el código de
> `services/core-api/app`.

---

## 1. Veredicto de la auditoría

### Astra

La propuesta es sólida en arquitectura:

- Ciclo de vida real de la conversación.
- Separación conversación / borrador / entidad comercial.
- Hechos extraídos más allá de las acciones.
- `client_facts` como conocimiento persistente.
- Resolución de referencias y aclaraciones pendientes.
- Búsqueda empresarial antes de vectores.
- Confirmación idempotente y permisos.

Se adopta casi completa, con correcciones de modelo y de tipos.

### Gemini Neon

Acierta en:

- Buzón de dato huérfano después del refresh.
- `estado_flujo` + `payload_pendiente` + `candidatos_ofrecidos`.
- TTL para no bloquear el flujo.
- Fallback para acciones 501: tarea interna para secretaría.
- Catálogo de etiquetas y origen `CEREBRO`.
- Permisos en servidor y refresh por usuario.

**Pero su SQL no se puede aplicar tal cual.** Tiene errores críticos:

| Error de Gemini | Realidad verificada |
|---|---|
| `gato_conversaciones.id BIGSERIAL`, `actor_id BIGINT`, `cliente_id BIGINT` | Todos los IDs son **UUID**. `gato_turnos.id`, `clients.id`, `cerebro_borradores.id` y `cerebro_tareas_internas.id` son UUID. |
| `ALTER TABLE gato_turnos ADD COLUMN conversacion_id` | **Ya existe** `gato_turnos.conversacion_id uuid NOT NULL` desde la migración 074. Agregarla falla. |
| `ALTER TABLE cerebro_borradores ... BIGINT` | Debe ser `uuid`. |
| `ALTER TABLE cerebro_tareas_internas ... cliente_id BIGINT` | Debe ser `uuid`. |
| `CREATE EXTENSION unaccent` y `pg_trgm` | **No están instaladas**; solo está `plpgsql`. `CREATE EXTENSION` requiere privilegios y `unaccent` no es `IMMUTABLE`, así que el índice GIN directo falla. |
| `cliente_etiquetas.origen = 'cerebro'` | El CHECK actual solo admite `COTIZACION`, `MANUAL`, `COBRANZA`. Hay que migrar el CHECK. |
| `client_facts.categoria = 'ubicacion_obra'` / `'tipo_obra:escuela'` | El CHECK actual solo admite `DATO_CONTACTO`, `REFERENCIA_OBRA`, `ACUERDO_COMERCIAL`, `COMPROMISO_PAGO`, `PREFERENCIA`, `INCIDENTE`, `CONSENTIMIENTO_VOZ`. |
| `gato_conversaciones.cliente_id` como dueño del cliente | Una conversación puede tener **varios clientes y varias operaciones**. El cliente pertenece al borrador/encargo, no a la conversación. |
| `client_facts` para datos huérfanos | `client_facts.cliente_id` es **NOT NULL**. Los datos sin cliente van a una tabla general de hechos, no a `client_facts`. |
| “Generar un recibo” | No existe generación de recibos. `registrar_pago` responde 501. El camino seguro es una tarea interna para secretaría. |

---

## 2. Decisiones cerradas

1. **Conversación con ciclo de vida real.** `gato_conversaciones` con apertura,
   cierre, estado de diálogo y bloqueo optimista.
2. **Refresh = cierre + apertura nueva, en una transacción.** No borra nada.
3. **Al abrir Gato se muestra la última conversación del actor**, desde la base,
   no desde `localStorage`.
4. **Historial solo para Julio desde Superadmin.** Secretaría usa Gato, pero no
   ve el historial completo.
5. **Un dictado nuevo es una operación nueva por defecto.** Solo continúa un
   borrador si responde una pregunta pendiente o si el usuario pide continuar.
6. **La conversación no es dueña del cliente.** El cliente vive en el borrador,
   el encargo y la entidad comercial.
7. **Los hechos se conservan aunque no generen acción.** Se persisten con
   estado, evidencia, sujeto y confianza.
8. **Los hechos huérfanos se congelan y se pregunta por la entidad.** No se
   inventa el cliente ni se reabre la conversación vieja.
9. **Confirmar desde Gato usa el mecanismo existente del Cerebro.** No se crea
   un segundo motor de ejecución.
10. **No hay recibo ni pago automático.** Si la acción no tiene ejecutor, se
    crea una tarea interna para secretaría, ligada al cliente.
11. **No hay base vectorial ni RAG en la primera fase.** PostgreSQL, filtros y
    búsqueda textual primero.
12. **No se crean tablas de contactos u obras en la primera fase.** Se guardan
    como hechos con `sujeto_tipo` y `sujeto_id` nulo hasta resolver la entidad.
    Las entidades independientes se evalúan en una fase posterior.

---

## 3. Modelo de datos final

> Todo UUID. Nada de `BIGSERIAL`/`BIGINT`. No se editan migraciones aplicadas.

### 3.1 `gato_conversaciones` (nueva)

```sql
CREATE TABLE gato_conversaciones (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id            text NOT NULL,          -- misma clave que gato_turnos.actor_id
    perfil_id           uuid NULL REFERENCES panel_users_acl(id),
    rol_actor           text NOT NULL,
    abierta_en          timestamptz NOT NULL DEFAULT now(),
    cerrada_en          timestamptz NULL,
    ultimo_turno_en     timestamptz NOT NULL DEFAULT now(),
    titulo              text NULL,
    resumen             text NULL,
    estado_dialogo_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    lock_version        integer NOT NULL DEFAULT 1,
    CONSTRAINT chk_gato_conv_cierre
        CHECK (cerrada_en IS NULL OR cerrada_en >= abierta_en),
    CONSTRAINT chk_gato_conv_lock CHECK (lock_version >= 1)
);

CREATE UNIQUE INDEX uq_gato_conversacion_abierta_actor
    ON gato_conversaciones (actor_id)
    WHERE cerrada_en IS NULL;
```

**Por qué `actor_id text` y `perfil_id uuid`:** `gato_turnos.actor_id` es texto
y puede ser `"julio"` cuando el panel usa el perfil base; `perfil_id` guarda el
UUID real cuando existe. Así no se rompe el perfil base ni se inventa un UUID.

**Por qué no `cliente_id` en la conversación:** una conversación puede contener
Pastrana y Escuela Miguel Rofrío, o dos operaciones del mismo cliente. El
cliente se guarda en `cerebro_borradores.cliente_id` y en las entidades
comerciales. Para el título se usa `titulo`/`resumen`.

**Estado de diálogo (`estado_dialogo_json`):**

```json
{
  "estado": "LIBRE | ESPERANDO_CLIENTE | ESPERANDO_CONFIRMACION",
  "pendiente": {
    "tipo": "DATO_PARCIAL | ACLARACION",
    "payload": { "campo": "ubicacion", "valor": "junto al parque" },
    "candidatos": [
      { "cliente_id": "uuid", "nombre": "Escuela Miguel Rofrío", "score": 0.82 }
    ],
    "creado_en": "2026-11-19T17:45:00-05:00",
    "expira_en": "2026-11-19T18:15:00-05:00"
  }
}
```

- Solo hay **una aclaración pendiente** a la vez. Si llega otra, se resuelve la
  primera o se pide al usuario que elija.
- El TTL es configurable en `system_settings` como
  `gato.aclaracion_ttl_min`. Default técnico propuesto: **30 minutos**. No es
  una regla de negocio; es una guarda para no bloquear el flujo. Julio puede
  cambiarlo.

### 3.2 Enlaces

```sql
CREATE TABLE gato_turno_borradores (
    turno_id    uuid NOT NULL REFERENCES gato_turnos(id) ON DELETE RESTRICT,
    borrador_id uuid NOT NULL REFERENCES cerebro_borradores(id) ON DELETE RESTRICT,
    creado_en   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (turno_id, borrador_id)
);

-- Idempotencia de turno desde el cliente (móvil o web)
ALTER TABLE gato_turnos
    ADD COLUMN client_turn_id text NULL;

CREATE UNIQUE INDEX uq_gato_turnos_conv_client_turn
    ON gato_turnos (conversacion_id, client_turn_id)
    WHERE client_turn_id IS NOT NULL;

ALTER TABLE gato_turnos
    ADD CONSTRAINT fk_gato_turnos_conversacion
    FOREIGN KEY (conversacion_id) REFERENCES gato_conversaciones(id);

ALTER TABLE gato_recordatorios
    ADD CONSTRAINT fk_gato_recordatorios_conversacion
    FOREIGN KEY (conversacion_id) REFERENCES gato_conversaciones(id);

ALTER TABLE cerebro_borradores
    ADD COLUMN conversacion_id uuid NULL REFERENCES gato_conversaciones(id),
    ADD COLUMN cliente_id uuid NULL REFERENCES clients(id);

ALTER TABLE cerebro_extracciones
    ADD COLUMN conversacion_id uuid NULL REFERENCES gato_conversaciones(id);

ALTER TABLE cerebro_tareas_internas
    ADD COLUMN cliente_id uuid NULL REFERENCES clients(id);
```

`cerebro_borradores.cliente_id` es solo un **atajo** cuando el borrador tiene un
cliente inequívoco. Si el borrador mezcla dos clientes, queda `NULL` y la
relación se guarda por hecho/encargo; nunca se asigna el mismo cliente a todos
los encargos.

**No agregar `gato_turnos.borrador_id`.** Un turno puede producir varios
borradores/encargos; la tabla puente lo representa sin forzar uno solo.

**Backfill obligatorio antes de las FK:**

1. **Preflight:** verificar que cada `conversacion_id` de `gato_turnos` tenga
   un solo `actor_id`. Si hay colisión, **detener la migración** y conciliar;
   no asignar un dueño por intuición.
2. Crear una cabecera por cada `conversacion_id` de `gato_turnos`.
3. `abierta_en = min(created_at)`, `ultimo_turno_en = max(created_at)`.
4. Dejar **abierta** solo la conversación más reciente por actor; las demás
   `cerrada_en = max(created_at)`.
5. Crear cabeceras para los `conversacion_id` no nulos de
   `gato_recordatorios` que no existan; marcarlas cerradas.
6. Recién después agregar las FK con `NOT VALID` + `VALIDATE CONSTRAINT`.

### 3.3 Hechos extraídos (nueva tabla general)

Primero el catálogo de categorías, para no dejar `categoria` como texto libre:

```sql
CREATE TABLE cerebro_categorias (
    clave       text PRIMARY KEY,
    nombre      text NOT NULL,
    descripcion text NULL,
    activo      boolean NOT NULL DEFAULT true,
    origen      text NOT NULL DEFAULT 'CEREBRO',
    creado_en   timestamptz NOT NULL DEFAULT now()
);
```

Luego los hechos:

```sql
CREATE TABLE cerebro_hechos (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    extraccion_id     uuid NOT NULL REFERENCES cerebro_extracciones(id) ON DELETE CASCADE,
    conversacion_id   uuid NULL REFERENCES gato_conversaciones(id),
    encargo           integer NOT NULL DEFAULT 1 CHECK (encargo >= 1),
    indice_fuente     integer NOT NULL CHECK (indice_fuente >= 0),
    clave             text NOT NULL,
    categoria         text NULL REFERENCES cerebro_categorias(clave),
    tipo              text NULL,
    valor_original    jsonb NULL,
    valor_normalizado jsonb NULL,
    cita              text NULL,
    evidencia         jsonb NOT NULL DEFAULT '{}'::jsonb,
    estado_extraccion text NOT NULL,
    estado_negocio    text NOT NULL DEFAULT 'REPORTADO',
    sujeto_tipo       text NOT NULL DEFAULT 'OTRO',
    sujeto_id         uuid NULL,
    confianza         numeric(4,3) NULL CHECK (confianza IS NULL OR (confianza >= 0 AND confianza <= 1)),
    motivo_rechazo    text NULL,
    requiere_accion   boolean NOT NULL DEFAULT false,
    fecha_evento      date NULL,
    version_extractor text NULL,
    creado_en         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (extraccion_id, indice_fuente)
);
```

**Identidad del hecho:** es la ocurrencia, no la clave. Dos
`contacto.telefono` en el mismo encargo son dos hechos distintos y deben
conservarse. Por eso el único es `(extraccion_id, indice_fuente)` y no
`(extraccion_id, clave, encargo)`. La consolidación semántica se hace después,
sin borrar evidencias.

Catálogos cerrados:

- `estado_extraccion`: `EXTRAIDO`, `TENTATIVO`, `NO_DIJO`,
  `INAUDIBLE_NO_ENTENDI`, `BAJA_CONFIANZA_STT`, `CORREGIDO_POR_HUMANO`,
  `RECHAZADO`.
- `estado_negocio`: `REPORTADO`, `VALIDADO`, `PENDIENTE_IDENTIFICACION`,
  `CONFIRMADO`, `CONTRADICHO`, `SUPERADO`.
- `sujeto_tipo`: `CLIENTE`, `CONTACTO`, `OBRA`, `OPERACION`, `CONVERSACION`,
  `OTRO`.
- `categoria`: catálogo controlado. No se crea una columna por concepto.

**Qué se guarda aquí:** todos los hechos, incluso los que no generan acción,
los tentativos, los rechazados y los que todavía no tienen cliente. `motivo_rechazo`
explica por qué no pasó al borrador. Esto elimina la pérdida actual de las
notas del validador.

### 3.4 `client_facts` (existente) y hechos confirmados

`client_facts` ya existe y **no se recrea**. Se usa para hechos **confirmados y
ligados a un cliente**:

```sql
ALTER TABLE client_facts
    ADD COLUMN hecho_id uuid NULL REFERENCES cerebro_hechos(id);
```

- `cliente_id` sigue siendo NOT NULL.
- `categoria` sigue usando el CHECK existente; se mapea:
  - contacto/teléfono → `DATO_CONTACTO`
  - ubicación/acceso → `REFERENCIA_OBRA`
  - precio/volumen/acuerdo → `ACUERDO_COMERCIAL`
  - promesa de pago → `COMPROMISO_PAGO`
  - preferencia horaria → `PREFERENCIA`
  - problema/restricción → `INCIDENTE`
  - consentimiento de voz → `CONSENTIMIENTO_VOZ`
- `client_fact_supersedes` se usa para correcciones; no se borra el hecho
  anterior.
- Un hecho huérfano **no** entra a `client_facts` hasta que se resuelve el
  cliente; mientras tanto vive en `cerebro_hechos` con
  `estado_negocio = 'PENDIENTE_IDENTIFICACION'`.

### 3.5 Etiquetas

`cliente_etiquetas` ya existe. Se amplía su origen:

```sql
ALTER TABLE cliente_etiquetas
    DROP CONSTRAINT cliente_etiquetas_origen_check;

ALTER TABLE cliente_etiquetas
    ADD CONSTRAINT cliente_etiquetas_origen_check
    CHECK (origen IN ('COTIZACION', 'MANUAL', 'COBRANZA', 'CEREBRO'));
```

Para etiquetas de hechos, no se usa una columna por etiqueta. Se crea un
catálogo y una relación:

```sql
CREATE TABLE cerebro_etiquetas (
    etiqueta    text PRIMARY KEY,
    categoria   text NULL REFERENCES cerebro_categorias(clave),
    descripcion text NULL,
    estado      text NOT NULL DEFAULT 'CANDIDATA'
                CHECK (estado IN ('OFICIAL', 'CANDIDATA', 'RETIRADA')),
    origen      text NOT NULL DEFAULT 'CEREBRO',
    creado_en   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE cerebro_hecho_etiquetas (
    hecho_id uuid NOT NULL REFERENCES cerebro_hechos(id) ON DELETE CASCADE,
    etiqueta text NOT NULL REFERENCES cerebro_etiquetas(etiqueta),
    origen   text NOT NULL DEFAULT 'CEREBRO',
    PRIMARY KEY (hecho_id, etiqueta)
);
```

- Las etiquetas nuevas nacen `CANDIDATA`; no se usan como oficiales hasta que
  una persona las apruebe.
- `cliente_etiquetas` sigue siendo la etiqueta del cliente; `cerebro_hecho_etiquetas`
  clasifica hechos.
- No hay tabla polimórfica de etiquetas para conversaciones, obras y contactos
  en la primera fase. Las etiquetas de conversación se derivan de sus hechos.

### 3.6 Contactos y obras

En la primera fase **no se crean tablas nuevas** de contactos u obras. Se
representan como hechos:

- `sujeto_tipo = 'CONTACTO'`, `sujeto_id = NULL` hasta resolver la persona.
- `sujeto_tipo = 'OBRA'`, `sujeto_id = NULL` hasta resolver la obra.
- Si el cliente existe, el hecho confirmado se proyecta a `client_facts` con la
  categoría correspondiente.
- La creación de entidades independientes de contactos/obras se evalúa en una
  fase posterior, cuando exista volumen y una consulta que lo justifique.

Esto evita crear dos sistemas de contactos que se contradigan.

---

## 4. Flujos

### 4.1 Abrir Gato

1. El panel llama a `GET /api/v1/gato/conversacion/actual`.
2. El servidor busca la última conversación del actor (abierta o cerrada).
3. Devuelve la conversación, sus turnos y sus borradores/hechos/tareas.
4. El panel pinta el historial.
5. Si no hay ninguna, crea una conversación nueva y devuelve el saludo.

`localStorage` deja de ser la fuente de verdad; solo puede cachear el id
seleccionado.

### 4.2 Enviar un audio o texto

1. El panel captura el `conversacion_id` **al inicio** de la petición.
2. El servidor verifica que la conversación exista, sea del actor y esté
   abierta. Si se cerró mientras el audio se procesaba, responde `409
   CONVERSACION_CERRADA`; la respuesta tardía no se reasigna al hilo nuevo.
3. Transcribe si es audio.
4. Guarda el turno en `gato_turnos`.
5. Decide si es una operación nueva, una continuación o una respuesta a una
   aclaración pendiente.
6. Llama al Cerebro con el contexto **estrictamente necesario**, no con los
   últimos cinco dictados.
7. Guarda el borrador con `conversacion_id` y `cliente_id` si se resolvió.
8. Enlaza turno y borrador en `gato_turno_borradores`.
9. Persiste los hechos en `cerebro_hechos`.
10. Devuelve el resumen y las preguntas.

### 4.3 Refresh

1. El panel llama a `POST /api/v1/gato/conversacion/refresh`.
2. En una transacción: se marca `cerrada_en`, se calcula `titulo`/`resumen`, se
   cierra el estado de diálogo pendiente y se crea la nueva conversación.
3. El servidor devuelve la nueva conversación vacía.
4. El panel limpia el hilo y muestra la nueva.
5. La conversación anterior sigue disponible para el historial de Julio.

### 4.4 Confirmar desde Gato

1. El usuario dice «confirmado» o pulsa confirmar.
2. El servidor identifica el borrador vigente de la conversación.
3. Verifica versión, estado, permisos y acciones ya ejecutadas.
4. Ejecuta las acciones **ejecutables y autorizadas** en orden. Si una requiere
   doble confirmación o le faltan datos, se detiene y pregunta.
5. Registra cada ejecución en `cerebro_ejecuciones`.
6. Guarda el resultado en `gato_turnos` y actualiza el resumen.
7. Una confirmación repetida no duplica: se apoya en la idempotencia existente
   (`borrador_id` + `orden_ejecucion` + `intento_num`).

### 4.5 Dato huérfano después del refresh

Ejemplo: «me olvidé, los de la escuela quedan junto al parque».

1. La conversación nueva no hereda el contexto viejo.
2. El extractor marca el hecho como parcial y sin entidad ancla.
3. El servidor lo guarda en `cerebro_hechos` con
   `estado_negocio = 'PENDIENTE_IDENTIFICACION'`.
4. Guarda en `estado_dialogo_json` el pendiente y pregunta «¿de qué cliente u
   obra me hablas?».
5. El usuario responde «la escuela que visité».
6. Gato busca en `clients`, `cliente_etiquetas`, `client_facts` y
   conversaciones recientes; devuelve hasta 5 candidatos.
7. El usuario elige. Gato actualiza el hecho con `sujeto_id`, proyecta a
   `client_facts` si corresponde y limpia el pendiente.
8. No se reabre la conversación anterior ni se reutiliza su contexto.

### 4.6 «Ya me cancelaron los 300 dólares»

1. Gato detecta un pago, pero `registrar_pago` no tiene ejecutor (501).
2. No escribe en `payments` por su cuenta.
3. Crea una `cerebro_tareas_internas` ligada al `cliente_id`, asignada a
   secretaría, con la instrucción y el contexto.
4. Responde que la tarea quedó para secretaría.
5. No inventa un recibo ni marca el pago como recibido.

---

## 5. Búsqueda e historial

### 5.1 Endpoints

- `GET /api/v1/gato/conversacion/actual`
- `POST /api/v1/gato/conversacion/refresh`
- `GET /api/v1/gato/conversaciones?q=&cliente_id=&desde=&hasta=&estado=`
- `GET /api/v1/gato/conversaciones/{id}`

El listado y el detalle del historial son **solo para Julio** (rol
`SUPERADMIN` y módulo `superadmin_config`). Secretaría puede usar Gato, pero no
el historial completo.

### 5.2 Búsqueda

Primera fase, sin extensiones nuevas:

- Filtros estructurados: cliente, fecha, estado, monto/volumen cuando aplique.
- Texto: `ILIKE`/`to_tsvector` sobre `gato_turnos`, `cerebro_hechos` y
  `client_facts`.
- Normalización de nombres: reutilizar el buscador de clientes/Sabueso que ya
  existe (`translate` + `regexp_replace`), no crear otro normalizador.
- Desambiguación: si hay varias coincidencias, Gato lista hasta 5 y pregunta.

**No usar `unaccent` ni `pg_trgm` en la migración inicial.** No están
instaladas; `unaccent` no es `IMMUTABLE` y un índice GIN directo falla. Si más
adelante se justifica la búsqueda difusa, se hace una migración separada con
`CREATE EXTENSION pg_trgm` y una función `IMMUTABLE` wrapper, con permiso de
base de datos.

### 5.3 Herramienta de Gato

Gato puede usar una herramienta `buscar_conversaciones` que llama al endpoint
anterior. Responde «tengo 3 conversaciones sobre la escuela, ¿cuál quieres ver?».
No vuelca el historial completo sin que el usuario elija.

---

## 6. Permisos y seguridad

- **Historial:** solo Julio (SUPERADMIN) desde Superadmin.
- **Conversación:** pertenece al actor; otro actor no la lee ni la modifica.
- **Dictado:** requiere Voz y Cerebro; si faltan, aviso claro.
- **Confirmación:** el servidor verifica rol, módulo, versión, estado y
  acciones ya ejecutadas. No confía en el navegador.
- **Perfil simulado:** el panel actual no tiene login real; la selección de
  «Viendo como» es una simulación. La seguridad real llega con H6. Mientras
  tanto, el servidor debe validar el perfil y no aceptar acciones destructivas
  desde un rol no autorizado.
- **Datos:** no inventar clientes, montos, fechas, direcciones ni teléfonos.

---

## 7. Fases de implementación

### Fase 1 — Ciclo de conversación

- Migración `098_gato_conversaciones.sql` con `gato_conversaciones`, backfill y
  FK de `gato_turnos`/`gato_recordatorios`.
- `098b` o `099` para `gato_turno_borradores`, `cerebro_borradores.conversacion_id`,
  `cerebro_borradores.cliente_id`, `cerebro_extracciones.conversacion_id`,
  `cerebro_tareas_internas.cliente_id`.
- API de conversación actual y refresh.
- Panel: cargar historial, refresh real, sin `localStorage` como fuente.
- Reemplazar `_contexto_dictado` por contexto deliberado.
- Pruebas: dos operaciones no se contaminan; refresh cierra y abre; cross-device.

### Fase 2 — Confirmación y enlaces

- Confirmación desde Gato.
- Enlace turno ↔ borrador ↔ ejecución.
- Idempotencia y versiones.
- Pruebas de confirmación duplicada y de dos dispositivos.

### Fase 3 — Hechos y etiquetas

- `cerebro_hechos`, catálogo de etiquetas y relación.
- Persistir hechos aceptados, tentativos y rechazados.
- `client_facts` como proyección confirmada; `hecho_id`.
- Ampliar `cliente_etiquetas.origen` con `CEREBRO`.
- Pruebas de no duplicación y de correcciones.

### Fase 4 — Resolución de identidades y búsqueda

- Buzón de aclaración pendiente, candidatos y TTL.
- Búsqueda por cliente, fecha, ubicación, estado y texto.
- Historial solo Julio.
- Pruebas de ambigüedad y de «la escuela del otro día».

### Fase 5 — Contactos y obras (solo si se justifica)

- Evaluar entidades independientes después de auditar el uso real.
- No crear tablas nuevas antes de demostrar que los hechos no alcanzan.

---

## 8. Criterios de aceptación

1. Refresh cierra en PostgreSQL y abre una conversación nueva.
2. Al abrir Gato aparece la última conversación, no una ventana vacía.
3. Celular y laptop muestran la misma conversación.
4. Un dictado nuevo no arrastra operaciones anteriores.
5. Una respuesta corta a una pregunta pendiente sí continúa el borrador.
6. «Confirmado» ejecuta lo autorizado y registra la ejecución.
7. Una confirmación repetida no duplica.
8. Las tareas quedan ligadas al cliente.
9. Los hechos sin acción se conservan en `cerebro_hechos`.
10. Los hechos rechazados conservan motivo y evidencia.
11. Un dato huérfano pregunta por el cliente y no reabre la conversación vieja.
12. «Ya me cancelaron 300» no escribe en `payments`; crea tarea para secretaría.
13. El historial solo lo ve Julio.
14. La búsqueda encuentra por cliente, fecha, estado y texto.
15. No se instalan extensiones ni se crean columnas duplicadas.
16. No hay regresiones en los 744 tests existentes.

---

## 9. Decisiones que quedan para Julio

Solo estas, porque son de negocio:

1. **TTL de una aclaración pendiente.** Propuesta técnica: 30 minutos,
   configurable. ¿Lo acepta o prefiere otro plazo?
2. **Alcance de «confirmado».** Propuesta: ejecutar todas las acciones
   ejecutables y autorizadas del borrador, en orden, deteniéndose si una exige
   doble confirmación o faltan datos. ¿O prefiere confirmar una por una?
3. **Contactos y obras como entidades.** Propuesta: primera fase como hechos;
   entidades independientes solo si el uso lo exige.

No hay otras decisiones de negocio pendientes para arrancar la Fase 1.

---

## 10. Instrucción para Astra y Neo

Implementen **este documento**, no las propuestas literales.

- No usen `BIGSERIAL` ni `BIGINT`: todo es UUID.
- No agreguen `gato_turnos.conversacion_id`: ya existe.
- No agreguen `conversacion_id`/`cliente_id` a `gato_recordatorios`: ya existen.
- No creen `cliente_etiquetas` ni `client_facts`: ya existen; solo amplíen lo
  necesario.
- No usen `unaccent`/`pg_trgm` en la migración inicial.
- No pongan `cliente_id` en `gato_conversaciones` como dueño del cliente.
- No inventen recibos ni pagos.
- No dupliquen hechos entre `cerebro_hechos` y `client_facts`: usen
  `client_facts` solo para hechos confirmados de cliente y enlacen con
  `hecho_id`.
- Cada migración debe ser reversible, probada y con backfill.
- Cada cambio visible debe actualizar el Manual Vivo y la bitácora.
- Si algo del documento contradice el código real, gana el código y se
  pregunta; no se asume.

El listón es producción real: migración aplicada, pruebas, permisos, historial
cross-device, búsqueda, documentación y evidencia. No se acepta un prototipo ni
placeholders.
