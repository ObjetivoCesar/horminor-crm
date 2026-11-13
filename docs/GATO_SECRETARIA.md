# Gato Secretaría — sistema de recordatorios por WhatsApp

| Campo | Valor |
|---|---|
| **Versión del documento** | 1.3.0 (adjuntos y ratificación tardía) |
| **Base** | v6.16 · migraciones 075, 076, 077 y 078 |
| **Fecha** | 2026-11-12 |
| **Estado real** | **Ratificación y adjuntos funcionando en local (SANDBOX).** **No desplegado al VPS.** Quedan pendientes de §15. |
| **Evidencia** | `.agents/evidencias/gato_adjuntos_2026-11-12.txt` · `pytest` **374 passed** |
| **Autor** | OpenCode · Dirección: Julio Villavicencio |

> **Cómo leer este documento.** La versión 1.0 afirmaba cosas que la auditoría
> desmintió. La 1.1 documentó los fallos. Esta 1.2 registra los que ya se
> cerraron con código y evidencia, y deja explícito lo que falta. Si algo no
> tiene comando y salida, no se declara hecho.

---

## 0. Qué garantiza y qué no

### 0.1 Garantizado hoy

1. **Nada se agenda sin ratificación.** Gato prepara un `BORRADOR` y espera un
   "sí" explícito. Un "no" lo descarta. Probado.
2. **Si la hora pasa mientras ratificas, se envía igual.** Al confirmar, la
   tarea se reprograma a "ahora" y sale en el siguiente tick.
3. **"Ahora mismo" es una hora válida.** También "ya", "de una", "en este
   momento".
4. **La factura viaja adjunta.** "Pásale la factura" genera un `DOCUMENTO` con
   el PDF del cliente, no un texto que promete un archivo inexistente.
5. **El mensaje sale a la hora.** Programado 19:55:25 → enviado en el tick.
6. **El teléfono del cliente sale del CRM** y se normaliza; si se dicta un
   número, queda marcado como `DICTADO`. Probado.
7. **Si el cliente no tiene número, no se inventa.**
8. **Doble clic no duplica:** clave de idempotencia única. Probado.
9. **Se puede auditar quién pidió qué:** `creado_por`, `conversacion_id`,
   `confirmado_por`.

### 0.2 NO garantizado (está en §15)

1. **Que el texto sea idéntico al dictado.** El modelo todavía agrega
   "Recuérdale que…". La ratificación lo muestra antes de agendar.
2. **Que `ENVIADO` signifique entregado.** Significa "Evolution aceptó el
   envío".
3. **Que nadie más que tú programe mensajes.** Sin login, el rol es una
   cabecera HTTP.
4. **Que el número exista en WhatsApp.** No se consulta antes de crear.

---

## 1. Alcance y fronteras

### 1.1 Dentro

| Capacidad | Estado |
|---|---|
| Crear recordatorio de texto a un cliente con hora | ✅ probado |
| Listar pendientes y cancelar antes de la hora | ✅ probado, con la salvedad de §7.3 |
| Hora por frase ("18:40", "mañana a las 9", "en 30 minutos") o ISO | ⚠️ parcial (§5.3) |
| Normalizar el teléfono a formato Evolution | ✅ probado |
| Reintentar 3 veces y guardar el error | ✅ probado con pool simulado |
| Enviar por Evolution o dejar en outbox (SANDBOX) | ✅ probado |
| Decir qué se enviará y a quién | ✅ |

### 1.2 Fuera

| Capacidad | Motivo |
|---|---|
| Recurrentes ("todos los lunes") | Falta semántica de recurrencia |
| PDF o foto en el recordatorio | `Notifier` solo envía texto |
| Editar una tarea programada | Se cancela y se crea otra |
| Varios destinatarios por tarea | Un destino por fila |
| Acuse de entrega/lectura | No se procesa `MESSAGES_UPDATE` |
| Recordatorios al personal interno | Solo clientes o número dictado |

---

## 2. Arquitectura

```
┌──────────────────────────────────────────────────────────────────────┐
│ /panel · widget Gato                                (navegador)      │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ POST /api/v1/asistente/chat
                                │ X-Panel-Role · X-Panel-User
┌───────────────────────────────▼──────────────────────────────────────┐
│ core-api (FastAPI)                                                   │
│  asistente/router.py ── actor_actual() → rol desde la sesión         │
│         ▼                                                            │
│  asistente/orquestador.py ── responder()                             │
│         ├── proveedores.py (DeepSeek + tool calling)  ← camino IA    │
│         └── planear() + recordatorios.interpretar()   ← sin IA       │
│         ▼                                                            │
│  asistente/recordatorios.py ── crear / listar / cancelar             │
│         ▼                                                            │
│  PostgreSQL · gato_recordatorios                                     │
│         ▲  cada 20 s · FOR UPDATE SKIP LOCKED                        │
│  asistente/despachador.py                                            │
│         ▼                                                            │
│  notificador M1:  SANDBOX → sandbox_outbox · PRODUCCIÓN → Evolution  │
└──────────────────────────────────────────────────────────────────────┘
```

**Principio:** la decisión (qué, a quién, cuándo) se toma al crear; el envío es
ejecución mecánica. Nada de lo que diga el modelo al enviar se reinterpreta.

---

## 3. Flujo end-to-end (caso real)

> "Gato, escríbele al Cliente Prueba Hito 3 en 1 minuto y recuérdale que la
> cita es en las oficinas de Horminor."

| # | Paso | Artefacto | Resultado real |
|---|---|---|---|
| 1 | El panel envía el mensaje con su rol | `POST /api/v1/asistente/chat` | 200 |
| 2 | `actor_actual()` resuelve el rol en el backend | `Actor(rol="SUPERADMIN")` | OK |
| 3 | Se carga el historial (8 turnos) | `gato_turnos` | OK |
| 4 | DeepSeek elige la herramienta | `recordatorios__recordatorio_crear` | OK |
| 5 | ACL por rol | `pilares.permite()` | SUPERADMIN/SECRETARIA ✅ |
| 6 | Valida mensaje y hora | `parsear_cuando()` | 19:00 local |
| 7 | Resuelve cliente y teléfono | `clients.telefono_whatsapp` | `0990000013` |
| 8 | Normaliza | `formato_whatsapp()` | `593990000013` |
| 9 | Inserta la tarea | `gato_recordatorios` | `BORRADOR` |
| 10 | Lee de vuelta y pide ratificación | texto del chat | "Responde sí o no" |
| 11 | El usuario responde "sí" | `recordatorios.confirmar()` | `PENDIENTE` |
| 12 | Despachador reclama | `UPDATE … RETURNING` | `ENVIANDO` |
| 13 | Relee el estado y envía | notificador + `ENVIADO` | outbox 22 · 19:40:37 |

Punto clave: **entre el 9 y el 11 no se envía nada.** El paso 10 es la
ratificación que exige la regla del prompt.

---

## 4. Modelo de datos

### 4.1 Tabla `gato_recordatorios` (migración 075)

| Columna | Tipo | Regla |
|---|---|---|
| `id` | uuid | PK |
| `creado_por` | text | Usuario real de la sesión (`X-Panel-User` o rol simulado) |
| `rol_actor` | text | Rol al crear |
| `conversacion_id` | uuid | **Ya se guarda**; enlaza con `gato_turnos` |
| `cliente_id` | uuid | FK `clients(id)` `ON DELETE SET NULL` |
| `destinatario_nombre` | text | Nombre resuelto en el CRM, o el dictado |
| `telefono` | text | Normalizado `593…`; nunca vacío |
| `mensaje` | text | Texto que se envía |
| `programado_at` | timestamptz | Instante absoluto |
| `zona` | text | `America/Guayaquil`, solo para mostrar |
| `estado` | text | `BORRADOR · PENDIENTE · ENVIANDO · ENVIADO · FALLIDO · CANCELADO` |
| `origen_destino` | text | `CRM` o `DICTADO` (migración 076) |
| `confirmado_por` | text | Quién ratificó (migración 076) |
| `confirmado_at` | timestamptz | Cuándo ratificó |
| `clave_idempotencia` | text | sha256 único; evita duplicados (migración 076) |
| `media_id` | uuid | FK `media_assets(id)`; adjunto que se envía como documento (077) |
| `intentos` | integer | Se incrementa al reclamar |
| `ultimo_error` | text | Máx. 500 caracteres |
| `enviado_at` | timestamptz | Sello del envío |
| `created_at` / `updated_at` | timestamptz | Auditoría |

### 4.2 Estados

```
                 crear
                   │
                   ▼
             ┌───────────┐  "no" / cancelar   ┌───────────┐
             │ BORRADOR  │───────────────────▶│ CANCELADO │
             └─────┬─────┘                    └───────────┘
                   │ "sí" (ratificación)
                   ▼
             ┌───────────┐  cancelar   ┌───────────┐
             │ PENDIENTE │────────────▶│ CANCELADO │
             └─────┬─────┘             └───────────┘
                   │ tick (hora cumplida)
                   ▼
             ┌───────────┐
             │ ENVIANDO  │◀── el despachador relee el estado antes de enviar
             └─────┬─────┘
        éxito      │      fallo (<3)          fallo (=3)
             ┌─────▼─────┐  ┌───────────────┐  ┌──────────┐
             │  ENVIADO  │  │ PENDIENTE +n m│  │ FALLIDO  │
             └───────────┘  └───────────────┘  └──────────┘
                   ▲
   recuperación: ENVIANDO > 5 min → PENDIENTE (puede duplicar, B3)
```

### 4.3 Invariantes

1. `telefono` nunca vacío; siempre normalizado al despachar.
2. Solo se envía lo que está `PENDIENTE` (ratificado) y con `programado_at <= now()`.
3. `intentos` cuenta reclamaciones; sin canal no se consume
   (`GREATEST(intentos - 1, 0)`).
4. Una fila no vuelve de `ENVIADO`, `CANCELADO` ni `FALLIDO`.
5. `cancelar` aplica a `BORRADOR` y `PENDIENTE`; en `ENVIANDO` avisa que ya salió.
6. `clave_idempotencia` única: el mismo mensaje, a la misma hora, del mismo
   usuario no crea dos filas.

---

## 5. Interpretación del lenguaje

### 5.1 Dos caminos

| Camino | Cuándo | Quién extrae los datos |
|---|---|---|
| **IA (DeepSeek)** | `DEEPSEEK_API_KEY` + `GATO_LLM=1` | Tool calling con JSON Schema |
| **Determinista** | Sin clave o si la IA falla | `recordatorios.interpretar()` por reglas |

Ambos terminan en `recordatorios.crear()`, que **vuelve a resolver el cliente**
contra la base. El modelo no puede fijar un teléfono: lo elige el CRM.

### 5.2 Reglas de hora (`parsear_cuando`)

| Frase | Resultado esperado | Resultado real hoy |
|---|---|---|
| `18:40` / `a las 18:40` | hoy 18:40 (o mañana si pasó) | ✅ |
| `a las 6 pm` | 18:00 | ✅ |
| `a las 9` | 09:00 (1–7 sin sufijo → tarde) | ⚠️ ambigua por diseño |
| `a las 7 de la mañana` | 07:00; hoy si aún no pasó | ✅ corregido (B1) |
| `a las 6 de la tarde` | 18:00 | ✅ |
| `mañana a las 9:00` | +1 día 09:00 | ✅ |
| `en 30 minutos` | ahora + 30 min | ✅ |
| `ahora mismo` / `ya` / `de una` | ahora + 30 s | ✅ |
| `2026-11-12T18:40:00` | ese instante | ✅ |
| Dos horas en la frase | la última (la del recordatorio) | ✅ corregido (B1b) |
| Sin hora | pedir la hora | ✅ |

### 5.3 Decisión: la IA interpreta, el backend calcula la hora

El LLM **no convierte a fecha absoluta**. Devuelve la frase tal como la dijo el
usuario (`"en 5 minutos"`, `"a las 18:40"`, `"mañana a las 9"`) y el backend
calcula en `America/Guayaquil`.

Motivo real: con ISO, el modelo mezclaba UTC y hora local y programó un mensaje
5 horas corrido. La frase es determinista y no tiene zona horaria que adivinar.

El camino sin IA (respaldo) aplica las mismas reglas y **pregunta** cuando no
puede leer la hora con certeza.

### 5.4 Límites conocidos

1. Nombres pegados a la hora pueden cortar mal en el camino sin IA.
2. El modelo reformula el mensaje; la confirmación lo muestra (§11.3).
3. Nombres ambiguos: no elige, devuelve la lista.
4. `programa de mantenimiento…` dispara la intención de recordatorio (B6).

---

## 6. Permisos

| Acción | SUPERADMIN | SECRETARIA | CONTADORA | BODEGA |
|---|---|---|---|---|
| Crear | ✅ | ✅ | ❌ | ❌ |
| Listar | ✅ | ✅ | ❌ | ❌ |
| Cancelar | ✅ | ✅ (solo los suyos) | ❌ | ❌ |

Dos salvedades:

- "Solo los suyos" **no funciona** si el panel no manda `X-Panel-User`: todos
  caen en `creado_por = "panel"` (B4).
- `listar` no filtra por creador: Secretaría ve los mensajes de todos.

---

## 7. Despachador (el "cron")

| Aspecto | Valor |
|---|---|
| Dónde | `app/asistente/despachador.py`, tarea `asyncio` |
| Intervalo | 20 s |
| Lote por tick | 10 |
| Reclamo | `FOR UPDATE SKIP LOCKED` |
| Reintento | `PENDIENTE` con espera de `intentos` minutos |
| Tope | 3 intentos → `FALLIDO` |
| Sin canal | `PENDIENTE` sin gastar intento |
| Recuperación | `ENVIANDO` > 5 min → `PENDIENTE` |
| Arranque | Solo con `asyncpg.Pool` (no en tests) |

```sql
WITH lote AS (
    SELECT id FROM gato_recordatorios
     WHERE estado = 'PENDIENTE' AND programado_at <= now()
     ORDER BY programado_at LIMIT $1
     FOR UPDATE SKIP LOCKED
)
UPDATE gato_recordatorios r
   SET estado = 'ENVIANDO', intentos = r.intentos + 1, updated_at = now()
  FROM lote WHERE r.id = lote.id
RETURNING r.id, r.telefono, r.mensaje, r.intentos, r.destinatario_nombre;
```

### 7.3 Ventanas donde el sistema todavía no es perfecto

| Ventana | Qué pasa | Estado |
|---|---|---|
| Cancelar entre el reclamo y el envío | El despachador relee `estado`; si ya no es `ENVIANDO`, no envía | ✅ reducido |
| Proceso muere tras enviar y antes del `UPDATE` | La recuperación reenvía | ⚠️ B3 abierto |
| Dos clics en el widget | La clave de idempotencia bloquea el duplicado | ✅ |

**Por qué no cron del sistema:** el PDR no trae Celery, el despliegue es un
contenedor y el cron del host no conoce el estado de la API. Es el mismo patrón
del worker de WhatsApp.

---

## 8. Teléfonos

### 8.1 Normalización (`formato_whatsapp`)

| Entrada | Salida | Correcto |
|---|---|---|
| `0990000013` | `593990000013` | ✅ |
| `990000013` | `593990000013` | ✅ |
| `593990000013` | `593990000013` | ✅ |
| `+593 99 000 0013` | `593990000013` | ✅ |
| `00593990000013` | `593990000013` | ✅ |
| `021234567` (fijo) | `59321234567` | ✅ corregido (B7) |
| `+1 305 555 1234` | `13055551234` | ⚠️ se deja pasar sin validar país |
| `12345` | `12345` | ✅ no inventa |
| vacío / `None` | `""` | ✅ |

### 8.2 Tres capas de aplicación

1. **Al crear:** se guarda normalizado.
2. **Al despachar:** cubre filas viejas.
3. **En `EvolutionNotifier.enviar_texto`:** cubre también los avisos de mixer.

`normalizar_telefono()` (la histórica) no se toca: sirve para comparar identidad
y devuelve 9 dígitos sin país.

---

## 9. Canales

### 9.1 SANDBOX

`SandboxNotifier` escribe en `sandbox_outbox` (`WHATSAPP`, `TEXTO`/`DOCUMENTO`,
destino normalizado, texto). Visible en el panel. **No sale a un celular.** Desde
v6.16 Gato lo dice en la ratificación y en la confirmación: *"Modo SANDBOX: en
local el mensaje queda en el outbox del panel; no sale a un teléfono real."*

### 9.2 Producción

`EVOLUTION_URL` + `EVOLUTION_INSTANCE` + `EVOLUTION_API_KEY` en
`system_settings.integraciones.evolution` con `sandbox=false`. Llama
`POST /message/sendText/{instancia}` con `{"number":"593…","text":"…"}`.

### 9.3 Qué significa `ENVIADO`

**"Evolution aceptó el envío"**, no "el cliente lo recibió". Un número
inexistente puede quedar `ENVIADO` y fallar en silencio. No se procesa
`MESSAGES_UPDATE`, así que no hay `ENTREGADO` ni `LEIDO`.

### 9.4 Archivos

Implementado: `Notifier.enviar_documento()` en Evolution (`/message/sendMedia`
con base64) y en SANDBOX (outbox tipo `DOCUMENTO`). El despachador lee
`media_assets`, carga el archivo del sandbox o del CDN y lo envía con el texto
como pie. Si el adjunto no se puede leer, la tarea se marca `FALLIDO` y
reintenta; no se envía un texto que prometa un archivo que no va.

---

## 10. API

Errores: `401` sin sesión · `403` sin permiso · `422` dato faltante · `503` sin base.

### 10.1 Crear

```http
POST /api/v1/asistente/recordatorios
X-Panel-Role: secretaria
X-Panel-User: 7f3c…

{"destinatario":"Cliente Prueba Hito 3","mensaje":"La cita es a las 18:40",
 "cuando":"18:40"}
```

```json
{"estado":"OK",
 "nota":"Recordatorio programado para 12/11/2026 18:40 (America/Guayaquil) a …",
 "datos":{"id":"c55a0882-…","destinatario":"Cliente Prueba Hito 3 (WhatsApp)",
          "telefono":"593990000013","mensaje":"La cita es a las 18:40",
          "programado_local":"12/11/2026 18:40","estado":"PENDIENTE"}}
```

### 10.2 Listar

```http
GET /api/v1/asistente/recordatorios?incluir_historicos=false
```

### 10.3 Cancelar

```http
POST /api/v1/asistente/recordatorios/{id}/cancelar
```

`200` cancelado · `404` no existe, no está `PENDIENTE` o no es del creador.

### 10.4 Chat

`POST /api/v1/asistente/chat` → `respuesta`, `estado`, `conversacion_id`.

**Pendiente de contrato:** `POST /recordatorios` no devuelve `origen_destino`,
porque la columna aún no existe.

---

## 11. Prompt y salvaguardas

### 11.1 Reglas añadidas a `persona.py`

1. Solo preparar si lo piden explícitamente.
2. Faltan tres datos → pedir solo el que falta.
3. Teléfono desde la ficha; nunca inventar ni deducir. Un número dictado se
   acepta y se repite en la confirmación.
4. Mensaje **literal**, sin adornos.
5. **Ratificación obligatoria:** queda en BORRADOR; decir "listo para que lo
   confirmes", nunca "programado" ni "enviado".
6. Repetir destinatario, hora y mensaje.
7. No convertir la hora a fecha absoluta: pasar la frase.
8. Primero el recordatorio, después la consulta.

### 11.2 Verificación real

- Con el Ing. Reyes (sin teléfono), Gato se negó y pidió el número.
- Con un cliente con número, respondió: *"Voy a enviar a … Responde «sí» para
  programarlo o «no» para descartarlo."* Nada se envió hasta el "sí".

### 11.3 Contradicción resuelta

La regla del prompt ("ninguna escritura sin confirmación explícita") ya se
cumple: crear solo produce un `BORRADOR`; el envío requiere `confirmar`. El
"no" lo pasa a `CANCELADO` sin salir a la red.

---

## 12. Observabilidad

| Pregunta | Dónde | Limitación |
|---|---|---|
| ¿Qué se programó? | `gato_recordatorios` | — |
| ¿Se envió? | `estado`, `enviado_at` | `ENVIADO` ≠ entregado |
| ¿Qué salió? | `sandbox_outbox` / log Evolution | — |
| ¿Quién lo pidió? | `creado_por` + `confirmado_por` | Usuario real o rol simulado |
| ¿Con qué palabras? | `conversacion_id` → `gato_turnos` | **Ya se guarda** |
| ¿El despachador vive? | log `despachador de recordatorios activo` | — |

```sql
SELECT id, destinatario_nombre, telefono, mensaje, programado_at,
       estado, intentos, ultimo_error, enviado_at
  FROM gato_recordatorios
 ORDER BY created_at DESC
 LIMIT 20;
```

---

## 13. Pruebas

```
docker compose up -d --build core-api
docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto
```

**374 passed.**

| Grupo | Cubre | No cubre |
|---|---|---|
| `test_recordatorios.py` (24) | horas (incluye "ahora mismo"), ratificación, adjuntos, ACL, idempotencia, despachador | SQL real |
| `test_m1_whatsapp.py` (+9) | `formato_whatsapp` con fijos y países raros | — |
| Resto | sin regresiones M1–M5 | — |

**Deuda de prueba:** el despachador se testea con un pool falso. El SQL real y
el envío de un documento se verificaron a mano; falta un test de integración con
PostgreSQL y `ROLLBACK`.

---

## 14. Operación

### Crear

- Chat: "Gato, escríbele a \<cliente\> a las HH:MM y recuérdale \<texto\>".
- "ahora mismo" se acepta como hora.
- "pásale la factura" adjunta el PDF del cliente (`factura_de` si es de otro).
- Gato responde con el borrador y espera: **"sí"** para programar, **"no"** para
  descartar.
- API: `POST /api/v1/asistente/recordatorios` (crea el borrador; no envía).

### Ratificar o descartar

- Chat: "sí" / "no" en el mismo hilo.
- Si la hora ya pasó mientras ratificabas, Gato pide otra hora y no envía.

### Cancelar

- Chat: pedir el id que Gato devuelve al confirmar.
- API: `POST …/{id}/cancelar`.
- **Antes de la hora**, no en los últimos 20 s.

### Si un envío falla

1. Revisar `ultimo_error`.
2. Corregir el dato en el CRM.
3. Crear de nuevo: `FALLIDO` no se reintenta solo.

### Checklist antes de usarlo con clientes

- [ ] Desplegar al VPS y aplicar la 075 y la 076 (hoy **no existen allá**).
- [ ] `EVOLUTION_*` cargado y `sandbox=false`.
- [ ] Instancia en `state: open`.
- [ ] Un envío de prueba a un número interno, con ratificación.
- [ ] Verificar que el mensaje llega igual a como se leyó en la ratificación.

---

## 15. Pendientes

### P0 — antes de producción

#### Cerrados en v6.15 (con evidencia)

| # | Tema | Estado |
|---|---|---|
| 1 | **Ratificación antes de agendar** | ✅ Nace `BORRADOR`; "sí" → `PENDIENTE`; "no" → `CANCELADO`. Sin ratificación no se envía nada |
| 3 | **Parser de horas** | ✅ "a las 7 de la mañana" → 07:00; dos horas → la última; fijos correctos |
| 4 | **Trazabilidad** | ✅ `conversacion_id` y `creado_por` reales en las filas nuevas |
| 5 | **Número dictado marcado** | ✅ `origen_destino=DICTADO` y aviso en la ratificación |
| 6 | **Idempotencia y cancelación** | ✅ Clave única; el despachador relee el estado antes de enviar |
| 7 | **Fijos** | ✅ `021234567` → `59321234567` |

#### Abiertos

| # | Tema | Qué es, en simple | Criterio de aceptación |
|---|---|---|---|
| **2** | Tope diario | **Descartado por decisión de Dirección (2026-11-12):** el chat que crea recordatorios es interno (Julio y Secretaría), no un canal público. No se implementa tope mientras el acceso siga cerrado. Si mañana lo usa más gente, se retoma. | — |
| **8** | Cliente activo y número vivo | Hoy `clients.estado` solo tiene `ACTIVO` y `PROSPECTO`, así que no hay "inactivo" que bloquear. Falta consultar `chat/whatsappNumbers` antes de crear. | Número inexistente → 422 con mensaje claro |

### P1 — siguiente iteración

| # | Tema | Criterio |
|---|---|---|
| 9 | UI de recordatorios en el panel | Lista, aprobar, cancelar; sin build ni CDN |
| 10 | ~~`enviar_documento()`~~ | ✅ Hecho: PDF adjunto en outbox 25 |
| 11 | Acuse de entrega | `ENTREGADO` solo con `MESSAGES_UPDATE` real |
| 12 | Aviso al creador si falla | Mensaje al panel o WhatsApp interno |
| 13 | Listar filtrado por creador | Secretaría no ve lo de sus compañeros |

### P2 — evolución

| # | Tema | Nota |
|---|---|---|
| 14 | Recurrencia | Diaria/semanal, sin RRULE completo |
| 15 | Plantillas | Textos aprobados reutilizables |
| 16 | Horario permitido | No enviar de noche salvo excepción explícita |

---

## 16. Decisiones y alternativas descartadas

| # | Decisión | Por qué | Alternativa descartada |
|---|---|---|---|
| 1 | Tabla propia | Una cita no ocupa mixer | Reusar `dispatch_schedule` |
| 2 | Tarea `asyncio` | Sin Celery en el PDR | Cron del host |
| 3 | `FOR UPDATE SKIP LOCKED` | Escala a varias réplicas | Bloqueo en memoria |
| 4 | Teléfono del CRM por defecto | Evita enviar datos a terceros | Solo número libre |
| 5 | Número dictado permitido, marcado | Caso real del maestro/tercero | Prohibirlo y frenar la operación |
| 6 | Normalizar en 3 capas | Cubre filas viejas y avisos de mixer | Normalizar solo al crear |
| 7 | 3 intentos y `FALLIDO` | Error visible y acotado | Reintentos infinitos |
| 8 | Sin archivos todavía | El notificador no los soporta | Prometer PDF sin canal |
| 9 | `ENVIADO` = aceptado por la API | Honestidad de estado | Decir "leído" sin acuse |
| 10 | Respaldo sin IA limitado | El parser adivinaba mal | Dejar que adivine |
| 11 | **Ratificación en BORRADOR** | Un error de lectura no llega al cliente | Enviar directo y "avisar después" |
| 12 | **La IA pasa la frase, no la fecha** | El modelo mezclaba UTC y local (5 h de error) | Convertir ISO en el modelo |
| 13 | **Clave de idempotencia** | Doble clic no duplica | Confiar en la UI |
| 14 | **Sin tope diario** | El canal de creación es interno (Julio/Secretaría) | Bloquear por volumen a dos usuarios |

---

## 17. Riesgos

1. **Baneo del número.** Canal no oficial + mensajes automáticos. Mitigado en
   parte por la ratificación y porque el creador es personal interno; sigue
   siendo el riesgo más caro.
2. **Sin login.** `X-Panel-Role` es una cabecera; el panel está privado por
   Caddy (403) pero no autenticado.
3. **Fuga de datos.** Un número dictado por error puede recibir información de
   otro cliente. La ratificación muestra el número y advierte si es `DICTADO`.
4. **Consentimiento.** No hay registro de que el cliente acepte recibir
   mensajes (LOPDP).
5. **Zona única.** Todo en `America/Guayaquil`.
6. **`ENVIADO` no es `ENTREGADO`.**
7. **Pruebas sin base real** en el despachador.
8. **No desplegado.** Hoy solo existe en local.

---

## 18. Glosario

| Término | Significado |
|---|---|
| **Recordatorio** | Fila de `gato_recordatorios` |
| **Despachador** | Tarea de fondo que envía lo vencido |
| **Tick** | Una pasada, cada 20 s |
| **Reclamo** | Pasar de `PENDIENTE` a `ENVIANDO` de forma atómica |
| **Camino determinista** | Reglas sin IA; respaldo cuando DeepSeek falla |
| **`BORRADOR`** | Estado propuesto: creado pero no enviable hasta aprobar |
| **`origen_destino`** | Campo propuesto: `CRM` o `DICTADO` |
| **SANDBOX** | Modo sin envíos reales |

---

## 19. Mapa de archivos

```
db/migrations/075_gato_recordatorios.sql     tabla y estados
services/core-api/app/asistente/
├── recordatorios.py       interpretación, validación, CRUD
├── despachador.py         reclamo, envío, reintentos
├── herramientas.py        enrutador de herramientas
├── orquestador.py         plan determinista + paso del actor
├── pilares.py             pilar `recordatorios` y ACL
├── proveedores.py         tools del LLM
├── redactor.py            confirmación y lista
├── persona.py             reglas del prompt
└── router.py              chat + endpoints
services/core-api/app/main.py                arranque/apagado
services/core-api/app/m1_whatsapp/
├── models.py              formato_whatsapp()
├── notifications.py       EvolutionNotifier
└── repositorio.py         outbox SANDBOX
services/core-api/tests/test_recordatorios.py
docs/GATO_RECORDATORIOS.md                   puntero
.agents/evidencias/gato_recordatorios_2026-11-12.txt
```

---

## 20. Anexo — evidencia real

### 20.1 Cliente sin teléfono

> "Jefe, no puedo programar el recordatorio: el cliente Ing. Reyes no tiene
> teléfono/WhatsApp registrado en el CRM (`telefono_whatsapp: null`), y no puedo
> inventar ni deducir un número."

0 filas creadas.

### 20.2 Envío 18:42

```
id 7ccd8870… · telefono 0990000013 (pre-normalización)
programado 18:42:00 · ENVIADO · intentos 1 · enviado_at 18:42:20
sandbox_outbox 19 · "Recuerde que tiene una cita…"
```

### 20.3 Envío 19:00

```
id c55a0882… · telefono 593990000013
programado 19:00:00 · ENVIADO
sandbox_outbox 20 · 19:00:10 · "Recuérdale que la cita es…"
```

### 20.4 Auditoría adversarial (v1.1) y estado actual

| Caso | Resultado en la auditoría | Hoy |
|---|---|---|
| `a las 7 de la mañana` | mañana 19:00 | **hoy 07:00** ✅ |
| Dos horas en la frase | 18:40 | **17:00** (la última) ✅ |
| `021234567` | `593021234567` | **59321234567** ✅ |
| `conversacion_id` | NULL en 2/2 | **guardado** ✅ |
| `creado_por` | `"panel"` en 2/2 | **usuario real o rol simulado** ✅ |
| Cancelar en `ENVIANDO` | el mensaje sale | el despachador relee estado ✅ |
| Doble clic | 2 filas | clave única ✅ |
| `programa de mantenimiento` | pide destinatario | ⚠️ sigue (palabra "programa") |
| `¿qué recordatorios tengo?` | "No entendí" | ⚠️ sigue en modo sin IA |
| VPS: tabla `gato_recordatorios` | `count = 0` | ⚠️ sigue sin desplegar |

### 20.5 Flujo con ratificación (v6.15)

```
1) "Gato escríbele al Cliente Prueba Hito 3 en 3 minutos y recuérdale que la
   cita es en las oficinas de Horminor"

   -> "Lo dejo listo para que lo confirmes… Hora: en 3 minutos — 12/11/2026
       19:40 (hora Ecuador). Responde sí para programarlo o no para descartarlo."

   gato_recordatorios: BORRADOR · origen CRM · creado_por julio · con conversacion

2) "sí"

   -> "Confirmado: a Cliente Prueba Hito 3 le llega «…» el 12/11/2026 19:40."
   gato_recordatorios: PENDIENTE · confirmado_por julio · confirmado_at

3) tick de 20 s

   gato_recordatorios: ENVIADO · intentos 1 · enviado_at 19:40:37
   sandbox_outbox 22 · destino 593990000013

4) "no" sobre otro borrador
   -> "Descartado. No se enviará nada a …" · estado CANCELADO · sin outbox

5) Número dictado ("al maestro al 0990000014")
   -> "… 593990000014 (número dictado, no está registrado en el CRM)"
   origen_destino = DICTADO
```

---

## 21. Paquete para Carbon

Encargo cerrado. Ejecutar en orden; no reinterpretar.

**Restricciones inviolables**

1. No editar la 075. Cambios de esquema = `076_*.sql`, `077_*.sql`.
2. Cero datos de negocio en código: teléfonos, nombres y cifras salen de la base.
3. El rol nunca viaja en el body.
4. La IA no calcula ni redacta cifras.
5. Cada entrega con comando y salida en `.agents/evidencias/`.

### Cerradas en v6.15

C1 (ratificación), C3 (parser), C4 (trazabilidad), C5 (número dictado), C6
(idempotencia y carrera) y C7 (fijos) están implementadas y verificadas. C2
(tope diario) queda **descartada** por decisión de Dirección: el chat es interno.

### C8 — Número vivo (P0-8, abierta)

- `POST /chat/whatsappNumbers/{instancia}` antes de crear, solo si Evolution
  está configurado; `exists=false` → 422 con mensaje claro.
- En SANDBOX se omite y la nota lo dice.
- Prueba: número inventado → 422; número real → borrador.

### C9 — UI de recordatorios (P1)

- Pestaña con borradores, pendientes y enviados; botones Ratificar, Descartar y
  Cancelar.
- Cero build, cero CDN, mismo estilo del panel.

### C10 — Documento por WhatsApp (P1) — ✅ cerrada

Implementado en v6.16: `enviar_documento()` en los tres notificadores,
migración 077 (`media_id`) y 078 (`DOCUMENTO` en el outbox). Evidencia: outbox
25 con `application/pdf`, 132.932 bytes.

### C11 — Acuse de entrega (P1)

- Procesar `MESSAGES_UPDATE` y pasar a `ENTREGADO`/`LEIDO`.
- No marcar `ENTREGADO` sin evento real.

### C12 — Test de integración del despachador (P1)

- PostgreSQL real con `ROLLBACK`: reclamar, enviar, reintentar y recuperar.
- Hoy solo se probó a mano.

**Definition of done:** `pytest` verde (372 + nuevos) · un envío real en el VPS
con ratificación · entrada en `.agents/BITACORA.md` y `.agents/ESTADO.md`.

---

## 22. Registro de cambios

| Versión | Fecha | Cambio |
|---|---|---|
| 1.0.0 | 2026-11-12 | Documento inicial tras la implementación |
| 1.1.0 | 2026-11-12 | Auditoría adversarial: se separan garantías de promesas, se documentan 8 fallos con salida real (B1–B8), se corrige el alcance del número dictado (se mantiene y se marca), se redefine el tope diario como valor configurable pendiente y se reescribe el paquete de Carbon como C1–C7 |
| 1.2.0 | 2026-11-12 | **Ratificación implementada** (migración 076): BORRADOR → "sí"/"no". Parser corregido ("de la mañana", última hora, fijos). Trazabilidad real (`conversacion_id`, `creado_por`). `origen_destino`. Idempotencia y relectura de estado antes de enviar. La IA pasa la frase, no la fecha. Tope diario descartado por decisión de Dirección (chat interno). Tests 372 |
| 1.3.0 | 2026-11-12 | **Adjuntos y ratificación tardía** (077 y 078): `enviar_documento`, `media_id`, outbox `DOCUMENTO`; "ahora mismo" como hora; confirmar después de la hora ya no rechaza; no interrogar por partes; verbos de mensaje ampliados. Tests 374 |
