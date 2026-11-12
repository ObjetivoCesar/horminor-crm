# Asistente IA conversacional — propuesta v0.1 (2026-11-12)

> **Estado: propuesta para iterar con Dirección. No hay código escrito.**
> Este documento responde al pedido de "un bot que converse con el usuario y
> busque las cosas por él en la base de datos" y reconcilia ese pedido con lo
> que el PDR y las decisiones ya registradas exigen.
>
> Lee también: `docs/PDR_v4.0.txt` §3, `.agents/ESTADO.md` (decisión 14),
> `docs/tutoriales/00_INDICE_BOT_TUTOR.md`.

---

## 1. Qué dice el PDR y qué se decidió antes

El PDR es explícito y va en contra de un chatbot abierto:

> "No usamos un chatbot conversacional abierto que pueda inventar respuestas.
> En su lugar, pasamos el texto por compuertas binarias ultrarrápidas."
> — `PDR_v4.0.txt`, §3.2

Y la decisión 14 del estado del proyecto lo refuerza:

> "El bot arma su respuesta con datos de BD; el LLM solo decide SÍ/NO.
> Cero precios o promesas inventadas por el modelo."

Hoy el único "bot" que responde es el de **leads**: `componer_respuesta_lead()`
arma el texto en código con `empresa.bot_publico` + precios de recetas y lo
envía por WhatsApp. El LLM (Gemini 2.5 Flash) solo devuelve
`{cumple: true/false, codigo_accion}` para las 4 compuertas.

**Por eso este pedido es un cambio de alcance, no una mejora del bot actual.**
Necesita una decisión explícita de Dirección y quedar escrita en la bitácora
(regla 7 de `AGENTS.md`: un módulo cerrado no se reabre sin documentar el motivo).

La forma de cumplirlo sin romper la regla de "cero datos inventados" es que el
modelo **no redacte cifras**: que **pida** las cifras a herramientas
determinísticas y solo **componga** la respuesta con lo que recibe.

---

## 2. Lo que ya existe y se puede reutilizar

| Pieza | Qué aporta al asistente |
|---|---|
| `app/custodio/` — 9 `QUERY_INTENTS` | Consultas con permisos por rol: saldo de cliente, cierre de caja, por pagar, inventario, cronología de despachos, P&L, balance, valoración/DSCR |
| `app/routers/clients_search.py` (Sabueso) | Búsqueda de clientes con tildes, b/v, nombre invertido, RUC, #orden |
| `app/m3_secretaria/` | Cartera, movimientos, cierre, carpeta del cliente |
| `app/m4_dashboard/bancos.py` | Detalle de cuenta, saldos, préstamos, movimientos |
| `app/superadmin/secciones.py` | `componer_respuesta_lead()` y lectura de `empresa.bot_publico` |
| `app/m1_whatsapp/` | Identidad por teléfono/código, debounce 14 s, Evolution API, outbox SANDBOX |
| `panel.html` | Widget de chat ya existe por cliente (`chat_*`); sirve de base visual |
| `docs/tutoriales/` (7 archivos) | Base de conocimiento de cómo se usa cada módulo |
| `chat_conversaciones` / `chat_mensajes` (070) | Modelo de historial, idempotencia por `whatsapp_msg_id` |
| `GEMINI_API_KEY` + `integraciones.juez` | Cliente Gemini ya integrado, con fallback determinístico |

Lo que **no** existe: catálogo de herramientas, orquestador de agente, registro
de auditoría del asistente, widget global y permisos por rol para el agente.

---

## 3. Arquitectura recomendada: agente con herramientas, sin SQL libre

```
Usuario (panel o WhatsApp)
        │
        ▼
[Identidad y rol]  ← teléfono registrado / X-Panel-Role
        │
        ▼
[Orquestador]  ← LLM con function calling (máx. N pasos)
        │  pide herramientas, nunca escribe SQL
        ▼
[Catálogo de herramientas]  ← contratos fijos + permisos por rol
        │
        ▼
[Capa de datos]  ← Custodio.consultar(), repositorios, vistas
        │
        ▼
[Guardas]  ← cifras citadas ⊆ cifras devueltas; PII; auditoría
        │
        ▼
Respuesta con origen: módulo + filtro + fecha
```

### 3.1 El modelo no ve SQL, solo herramientas

Cada herramienta es una función con parámetros validados y contrato fijo. El LLM
recibe nombre, descripción y JSON Schema; devuelve qué herramienta llamar y con
qué argumentos. El backend la ejecuta con el rol del usuario y devuelve JSON.
El modelo **compone** la respuesta.

Herramientas mínimas de la Fase 1 (todas de lectura):

| Herramienta | Devuelve | Fuente | Roles |
|---|---|---|---|
| `buscar_cliente` | id, nombre, RUC, provincia, saldo | Sabueso / `v_cliente_saldo` | todos los internos |
| `saldo_cliente` | fiado, cobrado, saldo, cupo | `GET_CLIENT_BALANCE` | SUPERADMIN, CONTADORA, CAJA_SECRETARIA |
| `estado_orden` | avance viajes, estado, tiempos | `GET_DISPATCH_TIMELINE` | internos |
| `cierre_caja` | efectivo, transferencias, fiado, diferencia | `GET_DAILY_CASH_CLOSURE` | SUPERADMIN, CONTADORA, CAJA_SECRETARIA |
| `inventario_alertas` | stock, mínimo, proyectado | `GET_INVENTORY_AND_ALERTS` | SUPERADMIN, BODEGA_PLANTA, CONTADORA |
| `por_pagar` | proveedores y saldos | `GET_ACCOUNTS_PAYABLE` | SUPERADMIN, CONTADORA |
| `bancos` | cuentas, saldo contable/informado, movimientos | `m4_dashboard/bancos.py` | SUPERADMIN, CONTADORA |
| `mercado` | cuota, m³, brecha | `m4_dashboard` | SUPERADMIN |
| `precios_recetas` | FC y precio sin IVA | `concrete_recipes` | todos los internos |
| `empresa_info` | RUC, horario, cobertura, bancos | `empresa.bot_publico` | todos (incluye público) |
| `manual` | pasos de uso de un módulo | RAG sobre `docs/tutoriales/` | todos |

Cada herramienta devuelve además `fuente`, `filtro`, `fecha_consulta` y
`datos_vacios: true` cuando aplica, para que la respuesta pueda citar el origen
y decir "sin definir" en lugar de inventar.

### 3.2 Alternativas descartadas (y por qué)

1. **Text-to-SQL de solo lectura.** Da flexibilidad total, pero expone el
   esquema, permite inyección desde el texto del usuario y hace muy difícil
   demostrar que una cifra salió de la base. Se puede evaluar como "modo
   experto" interno, nunca para clientes.
2. **RAG puro sobre documentos.** Sirve para "¿cómo cierro caja?", no para
   "¿cuánto debe el Ing. Reyes?". No tiene acceso a números.
3. **Dejar que el LLM redacte con un dump de contexto.** Es lo que el PDR
   prohíbe: el modelo puede mezclar o inventar cifras.

La recomendación es **híbrida**: herramientas para números + RAG para
procedimientos.

---

## 4. Reglas duras del asistente

1. **Cero cifras que no vengan de una herramienta.** Antes de enviar, un
   verificador determinístico extrae los números de la respuesta y comprueba que
   estén en las salidas de las herramientas de ese turno (normalizando moneda y
   separadores). Si falta uno, se regenera una vez; si vuelve a faltar, se
   responde "no tengo ese dato" y se indica dónde cargarlo.
2. **Permisos por rol, no por prompt.** El catálogo se filtra en el backend según
   la identidad; el LLM no puede pedir una herramienta que su rol no tiene.
3. **Un cliente solo ve lo suyo.** El rol `CLIENTE` se identifica por teléfono
   registrado y las herramientas se limitan a sus órdenes, saldo y datos
   públicos. Nunca se puede consultar otro cliente.
4. **Las escrituras no las hace el LLM.** El asistente puede **proponer** una
   acción (cobro, gasto, orden) y arma un borrador; se ejecuta solo con
   confirmación explícita del usuario y pasa por el Custodio (ACL, testigo,
   idempotencia). En la Fase 1 no hay escrituras.
5. **Todo se audita.** Cada turno guarda actor, rol, canal, herramientas
   llamadas, argumentos, hash del resultado y respuesta final. Append-only.
6. **Sin credenciales no se finge.** Sin `GEMINI_API_KEY` el asistente entra en
   modo determinístico: responde un set fijo de preguntas frecuentes y dice que
   la conversación libre no está configurada. Igual que el Juez.
7. **Sin login no se expone.** El asistente hereda el puente `X-Panel-Role`
   mientras el panel siga abierto; no se publica a Internet antes del login.

---

## 5. Canales y personas

| Canal | Quién | Qué puede hacer | Cuándo |
|---|---|---|---|
| Panel (widget) | Julio, asesores, secretaria, bodega | Consultar todo lo que su rol permite; pedir borradores de acciones | Fase 1 |
| WhatsApp interno | Staff identificado por teléfono | Las mismas consultas, en texto corto | Fase 2 |
| WhatsApp cliente | Cliente identificado | Su saldo, estado de su pedido, precios públicos, horario; escalar a Secretaría | Fase 3 |
| WhatsApp lead | Número desconocido | Lo que ya hace el bot actual + precios públicos + agendar contacto | Fase 3 |

El bot de leads actual **no se toca** hasta que la Fase 1 esté cerrada.

---

## 6. Piezas nuevas propuestas

```
services/core-api/app/asistente/
├── catalogo.py       # registro de herramientas: nombre, schema, roles, handler
├── herramientas.py   # implementaciones (reusan Custodio, repositorios y vistas)
├── agente.py         # bucle mensaje → tool calls → respuesta (máx. N pasos)
├── guardas.py        # verificación de cifras, PII, límites, auditoría
├── proveedores.py    # LLM con function calling (Gemini primero) + fake para tests
├── conocimiento.py   # búsqueda full-text en docs/tutoriales/
└── router.py         # POST /api/v1/asistente/chat (panel) y hook de WhatsApp
```

Migración nueva (073 o la que toque):
- `asistente_sesiones` (actor, rol, canal, inicio, fin)
- `asistente_turnos` (sesión, mensaje, herramientas, respuesta, tokens, latencia)
- `asistente_tool_calls` (turno, herramienta, argumentos JSONB, resultado JSONB, error)
- `asistente_documentos` (título, ruta, contenido, `tsvector`) para el RAG
- Claves en `system_settings`: `asistente.modelo`, `asistente.max_pasos`,
  `asistente.temperatura`, `asistente.canales`, `asistente.presupuesto_diario`

Todo editable desde Superadmin, como el resto de parámetros.

---

## 7. Pruebas y candado

- **Unitarias con LLM falso:** el proveedor de test devuelve tool calls
  guionadas; se verifica que el orquestador no permita herramientas fuera de
  rol, no exceda pasos y no invente cifras.
- **Contrato de herramientas:** cada una se prueba contra el clon con
  `ROLLBACK`, igual que `http_gate_v44_check.py`.
- **Candado del asistente:** `scripts/asistente_lock_test.py` con ~20 preguntas
  canónicas; cada respuesta se contrasta con SQL y se exige que las cifras
  coincidan y que las vacías digan "sin definir".
- **Modo sin red:** apagar `GEMINI_API_KEY` y verificar el fallback determinístico.

---

## 8. Riesgos

| Riesgo | Mitigación |
|---|---|
| Cifra inventada | Verificador de cifras contra tool outputs; temperatura baja; catálogo cerrado |
| Fuga de datos entre clientes | Rol `CLIENTE` con herramientas filtradas por su id; tests de aislamiento |
| Prompt injection desde WhatsApp | Sin SQL, sin acceso a archivos; herramientas con esquema; el texto del usuario nunca cambia el rol |
| Costo descontrolado | Presupuesto diario por rol, máximo de pasos, caché de preguntas frecuentes |
| Latencia en WhatsApp | Respuesta corta; debounce ya agrupa; timeout con mensaje "dame un momento" |
| Dependencia del proveedor | Interfaz `proveedores.py` con Gemini, y alternativas intercambiables |
| El PDR prohíbe chatbot | Decisión explícita de Dirección registrada en bitácora y en este documento |

---

## 9. Fases propuestas

1. **Fase 1 — Asistente interno de lectura (panel).** Catálogo, 8–10
   herramientas, widget, auditoría, verificador de cifras, candado. Sin
   escrituras, sin WhatsApp, sin clientes.
2. **Fase 2 — WhatsApp del staff.** Mismo catálogo por el canal existente;
   respuestas cortas y comandos de seguimiento.
3. **Fase 3 — Cliente y lead.** Persona pública, datos propios, escalamiento a
   Secretaría. Reemplaza gradualmente la respuesta plantilla de leads.
4. **Fase 4 — Acciones con confirmación.** Borradores de cobro/gasto/orden a
   través del Custodio, con testigo y aprobación.
5. **Fase 5 — Conocimiento.** RAG sobre tutoriales y "explícame este número"
   con enlace directo al módulo del panel.

---

## 10. Decisiones que necesito de Dirección

1. **Audiencia inicial:** ¿panel interno primero (recomendado), WhatsApp del
   staff, o también clientes/leads desde el día uno?
2. **Escrituras:** ¿la v1 solo consulta (recomendado) o también ejecuta cobros,
   gastos y órdenes con confirmación?
3. **Proveedor/modelo:** ¿seguimos con Gemini 2.5 Flash (ya integrado) o
   evaluamos otro? ¿Hay presupuesto mensual definido?
4. **Alcance del cambio de PDR:** ¿se aprueba formalmente el asistente
   conversacional con las guardas de §4? (sin esta aprobación no se escribe
   código)
5. **Datos sensibles:** ¿el bot de clientes puede dar precios por m³? ¿Los
   saldos solo al titular del número registrado?
6. **Voz:** ¿solo texto en la v1, o también audio (transcripción) como el PDR
   prevé para WhatsApp?

Con esas seis respuestas se cierra el diseño y se pasa a construir la Fase 1.
