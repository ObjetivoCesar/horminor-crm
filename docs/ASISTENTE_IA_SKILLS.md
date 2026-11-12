# Asistente IA — bibliotecario, skills y manos (v0.2)

> **Documento de inventario para diseñar skills. No hay código.**
> Complementa `docs/ASISTENTE_IA_PROPUESTA.md`. Aquí están los datos reales
> que el bot puede pedir hoy, las dos personas (interna y pública) y el estado
> exacto de cada "mano" del bot público.
>
> Verificado contra el código y la base al 2026-11-12: **34 tablas, 7 vistas,
> 19 migraciones, 30 cuentas contables, 296 tests**.

---

## 0. Las dos personas

| | **Interna** | **Pública** |
|---|---|---|
| Nombre propuesto | `HORMINOR_INTERNO` | `HORMINOR_PUBLICO` |
| Quién | Julio, asesores, secretaria, bodega | Clientes y leads |
| Canal | **Solo CRM / panel** (`WEB_PANEL`). Nunca WhatsApp | WhatsApp y web pública |
| Identidad | Rol del panel (`X-Panel-Role` hoy, login después) | Teléfono registrado (cliente) o número desconocido (lead) |
| Alcance | Todo lo que su rol permita leer | Solo su información y datos públicos de la empresa |
| Escrituras | Propone borradores; ejecuta el Custodio con confirmación (fase posterior) | Solo solicitudes; confirma Secretaría |
| Modelo | DeepSeek | DeepSeek |

**Regla de oro:** es el mismo motor de skills, pero cada persona tiene su
**catálogo permitido**. El bot interno no puede hablar con clientes; el público
no puede ver la operación.

---

## 1. El bibliotecario

### 1.1 ¿Existe un jefe de la base de datos?

Como **persona**, no. `docs/BASE_DE_DATOS.md` §5 lo deja por escrito:

- Dueño del negocio y de los datos: **Julio** (precios, recetas, stock, cupos).
- Mantenimiento técnico del esquema: **César** (migraciones, vistas, backups).
- **DBA / custodio formal de producción: no designado** (pendiente de confirmar).
- **Custodio** en el sistema es otra cosa: es el *Gate* contable, no una persona.

Como **software**, el bibliotecario sí se puede construir y es lo que el bot
necesita. Propongo llamarlo así en el código: **`bibliotecario`** = la única
puerta de lectura de datos de negocio, con un catálogo de consultas nombradas.

### 1.2 Qué es hoy el bibliotecario (sin inventar nada)

| Capa | Qué entrega | Dónde |
|---|---|---|
| 9 `QUERY_INTENTS` del Custodio | Consultas con permisos por rol | `app/custodio/contracts.py` y `gate.py` |
| 7 vistas | Cartera, despachos, inventario, stock proyectado, balance, resultados, chat | `db/migrations/001`, `064`, `070` |
| Endpoints del panel | Cartera, carpeta, cierre, bancos, mercado, simulador, agenda, compras, kardex | `app/web/panel.py`, `m3_secretaria`, `m4_dashboard` |
| Sabueso | Búsqueda de clientes multi-variable | `app/routers/clients_search.py` |
| Configuración | `system_settings`, `empresa.bot_publico`, recetas, flota | `app/superadmin/` |

### 1.3 Contrato de respuesta del bibliotecario

Toda respuesta del bibliotecario debe ser una **ficha de dato**, no texto libre:

```json
{
  "dato": "saldo_pendiente",
  "valor": 55043.60,
  "unidad": "USD",
  "fuente": "v_cliente_saldo",
  "filtro": {"cliente_id": "…"},
  "fecha_consulta": "2026-11-12T17:40:00-05:00",
  "vacio": false,
  "nota": null
}
```

Si no hay dato: `{"vacio": true, "nota": "Cupo no configurado"}`. El bot está
obligado a decir "sin definir" y a indicar dónde se carga. **Nunca rellena.**

### 1.4 Catálogo v1 del bibliotecario por dominio

| Dominio | Pregunta que responde | Fuente | Estado |
|---|---|---|---|
| Cartera | ¿Cuánto debe cada cliente? ¿quién está vencido? | `v_cliente_saldo`, `GET_CLIENT_BALANCE` | ✅ |
| Cliente 360 | Ficha, RUC, provincia, órdenes, último viaje, chat | `clients`, `orders`, `chat_*`, Sabueso | ✅ |
| Caja | Cobros, gastos, efectivo esperado, diferencia | `payments`, `cash_closures`, `GET_DAILY_CASH_CLOSURE` | ✅ |
| Despachos | Avance de viajes, sellos de tiempo, riesgo térmico | `v_dispatch_timeline`, `GET_DISPATCH_TIMELINE` | ✅ |
| Inventario | Stock real, mínimo, proyectado, alertas | `v_inventario`, `v_stock_proyectado`, `GET_INVENTORY_AND_ALERTS` | ✅ |
| Compras | Compras, en tránsito, recepciones, proveedores | `purchases`, `goods_receipts`, `suppliers` | ✅ |
| Contabilidad | Balance, resultados, libro mayor, por pagar | `v_balance_general`, `v_estado_resultados`, `GET_ACCOUNTS_PAYABLE` | ✅ |
| Banca | Cuentas, saldo contable/informado, préstamos, movimientos | `bank_accounts`, `financial_liabilities`, `payments.account_id` | ✅ |
| Mercado | Cuota Orellana/Sucumbíos, brecha, benchmarks | `market_benchmarks`, `/dashboard/mercado` | ✅ |
| Agenda | Entregas programadas, disponibilidad de mixers | `dispatch_schedule`, `app/agenda/service.py` | ✅ |
| Catálogo | Recetas, precios sin IVA, plantas, materiales | `concrete_recipes`, `plants`, `materials` | ✅ |
| Configuración | RUC, horario, cobertura, bancos del bot | `system_settings['empresa.bot_publico']` | ✅ |
| Personas | Perfiles del panel, módulos y roles | `panel_users_acl`, `whatsapp.staff` | ✅ |
| Salud | Centinela, errores, outbox | `error_logs`, `sandbox_outbox`, `/sentinel/daily-audit` | ✅ |

### 1.5 Lo que el bibliotecario **no** puede responder hoy

1. **Historial del saldo informado de bancos**: solo guarda el último valor.
2. **Movimientos por banco**: `payments.account_id` existe, pero el formulario
   de cobro aún no asigna la cuenta hija (`1102.01/02/03`).
3. **Conciliación bancaria** y extractos: no modelado.
4. **Cupo y mora**: el cupo existe (`credit_limit_usd`); la mora se calcula con
   `orders.created_at`, no hay tabla de vencimientos.
5. **Costo por viaje/orden**: hay kardex y COGS por movimiento, no un cierre de
   costo por orden.
6. **Datos del cliente para el bot público**: cédula y dirección de obra están
   `NULL` hasta que Julio los cargue.

---

## 2. Bot interno (`HORMINOR_INTERNO`)

### 2.1 Cómo funciona el prompt y la inferencia

El prompt **no contiene datos**. Contiene la persona, las reglas y el catálogo
de skills. El flujo es:

```
1. El usuario pregunta en el CRM.
2. El prompt + rol + catálogo permitido van al modelo (DeepSeek).
3. El modelo decide qué skills llamar y con qué parámetros.
4. El bibliotecario ejecuta y devuelve fichas de dato.
5. El modelo compone la respuesta citando fuente, filtro y fecha.
6. La guarda verifica que cada cifra exista en las fichas.
```

Así el modelo puede "inferir" (elegir el camino, cruzar dominios, explicar),
pero **no puede inventar un número**: si no lo pidió, no lo tiene.

### 2.2 Skills internas propuestas

| ID | Disparador | Qué hace | Datos | Escritura |
|---|---|---|---|---|
| `cartera_hoy` | "¿quién me debe?", "cartera" | Lista clientes con saldo, ordena por riesgo | `v_cliente_saldo` | No |
| `cliente_360` | "dame todo de X", "cómo va X" | Ficha, saldo, órdenes, último viaje, chat | Sabueso + varias | No |
| `estado_orden` | "cómo va la orden #55" | Avance X/Y viajes, tiempos, incidencias | `v_dispatch_timeline` | No |
| `cierre_del_dia` | "cierra el día", "cuánto hay en caja" | Cobros por método, gastos, diferencia | `GET_DAILY_CASH_CLOSURE` | No |
| `cobro_borrador` | "cóbrale 500 a X" | Arma el borrador de cobro y pide confirmación | `payments` | **Sí, Custodio** |
| `gasto_borrador` | "registra 40 de diésel" | Arma el gasto con rubro y pide confirmación | `payments` | **Sí, Custodio** |
| `orden_borrador` | "hazme una orden de 20 m³ FC-210" | Calcula receta, IVA y disponibilidad | `orders`, `agenda` | **Sí, Custodio** |
| `inventario_critico` | "¿qué me falta?" | Stock vs mínimo y proyectado | `v_inventario` | No |
| `kardex_material` | "movimientos del cemento" | Últimos movimientos y costo promedio | `inventory_movements` | No |
| `compras_pendientes` | "¿qué debo pagar?" | En tránsito, por pagar, proveedores | `purchases`, `purchase_items` | No |
| `banco_detalle` | "cómo está el Pichincha" | Saldo contable/informado, préstamos, movimientos | `bank_accounts` | No |
| `mercado_cuota` | "¿cómo vamos en el mercado?" | m³, cuota, brecha por provincia | `market_benchmarks` | No |
| `simulador_bancario` | "¿aguanto la pluma?" | Escenarios y DSCR | `m4_dashboard` | No |
| `explicar_numero` | "¿de dónde sale este 55.043,60?" | Traza: vista, filtros y movimientos | Cualquiera | No |
| `manual_modulo` | "¿cómo cierro caja?" | Pasos del tutorial + ruta del panel | `docs/tutoriales/` | No |
| `salud_sistema` | "¿cómo está el sistema?" | Centinela, errores, outbox | `daily-audit` | No |
| `permisos` | "¿quién puede cobrar?" | Perfiles y módulos | `panel_users_acl` | No |

**Fase 1** implementa las 13 primeras sin escritura (todas menos los tres
borradores). **Fase 4** agrega los borradores con confirmación y Custodio.

### 2.3 Reglas del prompt interno

1. Nunca inventar cifras; citar fuente, filtro y fecha.
2. No responder por un módulo que el rol no puede ver (el catálogo ya lo filtra).
3. Las acciones se proponen, no se ejecutan sin "confirmo".
4. Si el dato está vacío, decir dónde se carga (Superadmin / Banca / etc.).
5. Español de Ecuador, respuestas cortas, números con separador de miles.
6. No salir del CRM: no enviar mensajes a clientes desde este bot.

---

## 3. Bot público (`HORMINOR_PUBLICO`)

### 3.1 Protocolos (reglas duras)

1. **Identificarse**: "Le saluda Horminor Hormigones".
2. **Solo datos públicos**: empresa, cobertura, horario, servicios, precios
   confirmados, cuentas bancarias publicadas.
3. **Nunca** dar saldos, deudas, datos de otros clientes ni información interna.
4. **No prometer** precio, plazo ni disponibilidad: "un asesor confirma".
5. **Toda solicitud queda registrada** con teléfono, intención y hora.
6. **Escalar a Secretaría** si hay queja, volumen > umbral o pide hablar con
   una persona.
7. **No cobrar ni confirmar pagos**: solo comparte datos bancarios.
8. **Límite de mensajes** por número y ventana de tiempo (antiabuso).

### 3.2 Manos: inventario real

| Mano | Qué debe hacer | Estado hoy | Dónde vive / qué falta |
|---|---|---|---|
| Responder info de empresa | RUC, dirección, horario, cobertura | ✅ Existe | `componer_respuesta_lead()` |
| Enviar lista de precios | Resistencias y precio/m³ sin IVA | ✅ Existe | `concrete_recipes` (decidir si es público) |
| Enviar datos bancarios | Banco, tipo, número, titular | ⚠️ Parcial | `empresa.bot_publico.bank_accounts` (texto libre); migrar a `bank_accounts` |
| Capturar lead | Crear prospecto con teléfono y mensaje | ✅ Existe | `_gate_lead()` → `clients` |
| Escalar a Secretaría | Avisar y dejar pendiente | ⚠️ Parcial | Crea el lead, pero no hay bandeja de pendientes ni acuse al cliente |
| **Generar PDF** | Cotización o ficha imprimible | ❌ No existe | Solo hay dossier HTML imprimible (`/dashboard/dossier`); no hay motor PDF (`requirements.txt` sin WeasyPrint/reportlab) |
| **Agendar** | Cita de visita o llamada | ❌ No existe para público | `dispatch_schedule` es logística de entregas con mixers; la lógica de disponibilidad (`app/agenda`) se puede reutilizar, pero falta un tipo "cita comercial" |
| **Confirmación de Secretaría** | Que la secretaria acepte/rechace la solicitud | ❌ No existe | `approval_requests` es del Custodio; falta `solicitudes_publicas` + bandeja + notificación |
| Consultar estado de su pedido | "¿ya salió mi mixer?" | ❌ No existe para público | El dato existe (`v_dispatch_timeline`); falta identificar al titular y exponerlo |
| Enviar ubicación | Mapa de la planta | ❌ No existe | `bot_publico` no tiene coordenadas ni URL de mapa |
| Enviar multimedia | Fotos de planta/obras | ⚠️ Parcial | Bunny y `media_assets` existen para clientes; no hay biblioteca pública |
| Recordatorio | Avisar antes de la cita | ❌ No existe | No hay scheduler de recordatorios |

### 3.3 Manos nuevas: qué implica cada una

| Mano nueva | Pieza mínima | Depende de |
|---|---|---|
| `cotizacion_pdf` | Cálculo determinístico + plantilla + motor PDF + folio y validez | Precios públicos confirmados; decidir motor (WeasyPrint o Chromium headless) |
| `agendar_cita` | Tabla `citas_comerciales` o tipo en `dispatch_schedule` + disponibilidad + confirmación | Agenda y horarios de Secretaría |
| `confirmar_solicitud` | `solicitudes_publicas` + bandeja en el panel + notificación a Secretaría | Panel y notificador |
| `estado_pedido` | Identificación por teléfono + vista filtrada del viaje | Login de cliente o PIN por WhatsApp |
| `ubicacion` | Coordenadas + URL de mapa en `empresa.bot_publico` | Dato de Julio |
| `recordatorio` | Job programado + outbox | Scheduler |
| `biblioteca_publica` | Assets en Bunny con permiso `PUBLICO` | Bunny real |

### 3.4 Flujo de escalamiento propuesto

```
Cliente/lead pregunta
   → el bot responde con datos públicos
   → si pide cotización formal: arma solicitud (volumen, obra, fecha)
   → si pide cita: propone horarios disponibles
   → crea SOLICITUD_PUBLICA (estado PENDIENTE)
   → notifica a Secretaría (panel + WhatsApp interno)
   → Secretaría confirma/rechaza
   → el bot avisa al cliente
   → si se confirma, se puede generar el PDF y/o la orden
```

La solicitud es el punto de auditoría: quién pidió, qué, cuándo y quién
respondió. Sin esa tabla, "pedir confirmación a secretaría" no es verificable.

---

## 4. Modelo: DeepSeek

- **Siempre DeepSeek para atender** (persona y composición).
- Proveedor nuevo en `app/asistente/proveedores.py`, con API compatible OpenAI
  y *function calling*. Configurable, no hardcodeado.
- Variables: `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `DEEPSEEK_BASE_URL`,
  `DEEPSEEK_TIMEOUT`.
- Parámetros en `system_settings['asistente']`: modelo, temperatura, máximo de
  pasos, presupuesto diario, canales habilitados.
- **Sin key**: modo determinístico (responde el set fijo de preguntas y avisa
  que la conversación libre no está configurada). Igual que el Juez.
- Gemini queda **solo** para el juez binario actual, salvo que Dirección pida
  migrarlo también. Son dos usos distintos: juez = SÍ/NO; asistente = conversar.

> Nota técnica: DeepSeek expone *tool calling* tipo OpenAI; el contrato de
> skills se escribe una vez y sirve para cualquiera de los dos proveedores.

---

## 5. Formato de skill (manifest)

Cada skill se declara una vez y el catálogo se filtra por persona y rol:

```yaml
id: cartera_hoy
nombre: Cartera del día
persona: INTERNO
descripcion: Devuelve los clientes con saldo pendiente, ordenados por monto.
cuando_usar:
  - El usuario pregunta quién debe o cuánto hay por cobrar.
  - El usuario pide priorizar cobros.
no_usar_cuando:
  - Pide el detalle de un movimiento puntual (usar explicar_numero).
herramientas:
  - bibliotecario.cartera
parametros:
  - nombre: incluir_al_dia
    tipo: boolean
    default: false
permisos:
  roles: [SUPERADMIN, CONTADORA, SECRETARIA]
salida: tabla
guardas:
  - Citar fuente v_cliente_saldo y fecha de consulta.
  - Si no hay clientes con saldo, decir "sin saldo pendiente".
ejemplos:
  - "¿Quién me debe?" → tabla de 2 clientes, total 55.043,60.
estado: propuesto
```

Con este manifiesto se puede **mostrar el diseño de skills** en el chat: un
archivo por skill, agrupados por persona y dominio, con su estado.

---

## 6. Decisiones que faltan (pocas y concretas)

1. **PDF**: ¿qué documentos genera el bot público? (cotización, ficha técnica,
   proforma). ¿Motor WeasyPrint en el contenedor o Chromium headless?
2. **Agenda pública**: ¿citas de visita a obra, llamadas, o ambas? ¿Qué
   horarios y duración?
3. **Precios públicos**: ¿la lista de precios por m³ se mantiene visible o solo
   se cotiza por volumen?
4. **DeepSeek**: confirmar modelo exacto y endpoint; ¿la clave la carga Julio
   en Superadmin o va en `.env`?
5. **Bibliotecario**: ¿se designa formalmente a una persona como custodio de la
   BD en producción (hoy está pendiente en `BASE_DE_DATOS.md` §5)?

---

## 7. Referencias

- `docs/ASISTENTE_IA_PROPUESTA.md` (arquitectura y guardas)
- `docs/BASE_DE_DATOS.md` §3 (tablas/vistas) y §5 (responsable de la BD)
- `docs/00_DECISIONES_PENDIENTES.md` (datos y decisiones vigentes)
- `services/core-api/app/custodio/contracts.py` (9 `QUERY_INTENTS`)
- `services/core-api/app/custodio/gate.py` (permisos por rol)
- `services/core-api/app/m1_whatsapp/pipeline.py` (`_gate_lead`)
- `services/core-api/app/superadmin/secciones.py` (`componer_respuesta_lead`)
- `services/core-api/app/agenda/service.py` (disponibilidad y agenda)
- `services/core-api/app/m4_dashboard/router.py` (bancos, mercado, dossier)

---

## 8. Componente PDF independiente

**Decisión de Dirección (2026-11-12):** el generador de PDF es un componente
aparte, no una función del bot. Lo usan el bot, la secretaria, Julio o
cualquier módulo que lo necesite.

### 8.1 Principio

El componente **recibe datos y devuelve un PDF**. No calcula precios, no lee
tablas de negocio, no decide nada. El que lo llama arma el contenido.

```
Cotizador (bot / panel / secretaria)
        │  JSON con líneas y totales
        ▼
[pdf_engine]  → valida aritmética → renderiza plantilla → guarda folio
        │
        ▼
{ folio, pdf_url, emitido_at }
```

### 8.2 Contrato propuesto

```json
POST /api/v1/pdf/cotizaciones
{
  "plantilla": "cotizacion_v1",
  "cliente": {"nombre": "…", "ruc": "…", "telefono": "…", "obra": "…"},
  "lineas": [
    {"descripcion": "Hormigón FC-210", "cantidad_m3": 20, "precio_m3": 118.00}
  ],
  "iva_pct": 15,
  "validez_dias": 7,
  "condiciones": "Precio sujeto a confirmación de volumen y fecha.",
  "creado_por": {"actor_id": "…", "rol": "SECRETARIA", "canal": "WEB_PANEL"},
  "solicitud_id": null
}
→ 201 {"folio": "COT-2026-000123", "pdf_url": "/api/v1/pdf/cotizaciones/COT-2026-000123.pdf"}
```

El componente valida con `Decimal` que `subtotal = cantidad × precio`,
`iva = subtotal × iva_pct` y `total = subtotal + iva`. Si no cuadra, rechaza.

### 8.3 Piezas

| Pieza | Contenido |
|---|---|
| Tabla `cotizaciones` | folio, cliente, subtotal, iva, total, validez, estado, `pdf_url`, `creado_por`, `created_at` |
| Tabla `cotizacion_items` | descripción, cantidad, precio unitario, subtotal (snapshot del precio al emitir) |
| Plantillas | `cotizacion_v1`, `ficha_cliente_v1`, `dossier_bancario_v1` |
| Branding | `empresa.bot_publico` + logos de `static/brand/` |
| Almacenamiento | Bunny (`cotizaciones/<folio>.pdf`) o volumen local; `pdf_url` en la tabla |
| Estados | `BORRADOR`, `PRELIMINAR`, `EMITIDA`, `ACEPTADA`, `ANULADA` |

### 8.4 Reglas

1. **Una cotización no es una factura.** Se rotula "COTIZACIÓN" y no lleva
   datos de SRI (fuera de alcance).
2. **Precio congelado al emitir.** El ítem guarda el precio usado; si luego
   cambia la receta, la cotización no se mueve.
3. **Validez explícita.** Sin fecha de validez, el PDF no se emite.
4. **Preliminar.** Si nace del bot público y la secretaria no confirmó, lleva
   marca "PRELIMINAR" y no genera compromiso.
5. **Mismo PDF para todos los canales.** Bot, panel y secretaría llaman al
   mismo endpoint; no hay tres generadores.

### 8.5 Motor

- **WeasyPrint** (HTML/CSS → PDF): encaja con el panel actual, plantillas en
  HTML, dependencias Python. Requiere fuentes en la imagen Docker.
- **Chromium headless**: ya se usa para capturas, pero es más pesado en el VPS.
- Recomendación: **WeasyPrint**; el contrato no cambia si mañana se cambia el
  motor.

---

## 9. Agenda: obras y visitas

Hoy existe **una sola agenda**: `dispatch_schedule` (entregas de hormigón con
mixers, disponibilidad por mixer y ventana térmica). No sirve para citas
comerciales.

### 9.1 Dos agendas

| Agenda | Para qué | Tabla | Quién la usa |
|---|---|---|---|
| **Obras / entregas** | Programar viajes de mixer a una obra | `dispatch_schedule` (existe) | Secretaría, Planta |
| **Visitas / cotización** | Agendar una visita para medir o cotizar | `citas_comerciales` (nueva) | Bot público, Secretaría, asesores |

### 9.2 `citas_comerciales` (propuesta)

| Campo | Uso |
|---|---|
| `tipo` | `PLANTA`, `OBRA`, `VIRTUAL` |
| `motivo` | `COTIZACION`, `MEDICION`, `SEGUIMIENTO` |
| `cliente_id` / `prospecto` | Cliente registrado o lead con teléfono |
| `obra_direccion`, `obra_referencia` | Dónde es la visita |
| `volumen_estimado_m3` | Para priorizar y preparar la cotización |
| `asesor_id` | Quién atiende |
| `fecha`, `hora`, `duracion_min` | Cita |
| `estado` | `PENDIENTE_CONFIRMACION`, `CONFIRMADA`, `REALIZADA`, `CANCELADA`, `REAGENDADA` |
| `creado_por` | `BOT_PUBLICO`, `SECRETARIA`, `SUPERADMIN` |
| `solicitud_id` | Vínculo con `solicitudes_publicas` |
| `notas` | Contexto |

**"Visitar la obra" es un subtipo**, no el default: `tipo=OBRA, motivo=COTIZACION`.
La cita en planta es `tipo=PLANTA`.

### 9.3 Disponibilidad

- Se calcula con horario de atención (`empresa.bot_publico.business_hours`) y
  la agenda del asesor.
- **No** usa la ocupación de mixers: esa es la agenda de obras.
- El bot público solo propone horarios libres; nunca confirma solo.

---

## 10. Precios y costos: auditoría (hallazgo importante)

### 10.1 Lo que existe

| Pieza | Dónde | Qué hace |
|---|---|---|
| Precio por m³ | `concrete_recipes.precio_m3` | Precio de venta **sin IVA**, manual |
| Editor de precios | Superadmin > Recetas, flota y precios | CRUD por resistencia ("El precio es por m³ sin IVA") |
| Precio por orden | `orders.precio_m3` + override en el panel | Permite un precio distinto por venta |
| Costo de materiales | `materials.costo_unitario` | Costo vigente; el kardex lo actualiza por promedio ponderado |
| Costo en movimientos | `inventory_movements.costo_unitario_snapshot` | COGS con el costo del momento |
| Margen del simulador | `finanzas.simulador_bancario.margen_neto_m3 = 42.50` | Parámetro plano solo para el simulador bancario y el dossier |

### 10.2 Lo que **no** existe

1. **No hay cálculo de costo por receta.** Nada multiplica la dosificación por
   el costo de los materiales.
2. **No hay margen por resistencia.** El precio es un número manual; el sistema
   no avisa si queda por debajo del costo.
3. **No hay módulo de "precio unitario" derivado de costos.** El editor existe,
   pero es una tabla de precios, no un costeador.
4. **Hay dos nociones de margen** que no se tocan: el margen de materiales
   (calculable, hoy no calculado) y el `margen_neto_m3` plano del simulador.
5. **El agua no tiene costo** (`materials.costo_unitario` de `AGUA` sigue
   `NULL`), así que cualquier costeo la tomaría como cero.

### 10.3 Números con la semilla actual (solo materiales)

Costo directo = Σ (dosificación × `materials.costo_unitario`). **No incluye**
agua, mano de obra, energía, CIF, transporte ni merma.

| Resistencia | Costo materiales/m³ | Precio/m³ | Margen bruto/m³ | % |
|---|---:|---:|---:|---:|
| FC-180 | 76.16 | 108.00 | 31.84 | 29.5 % |
| FC-210 | 84.56 | 118.00 | 33.44 | 28.3 % |
| FC-240 | 92.91 | 126.00 | 33.09 | 26.3 % |
| FC-280 | 101.43 | 136.00 | 34.57 | 25.4 % |
| FC-350 | 114.33 | 158.00 | 43.67 | 27.6 % |

**Consecuencia:** si el cemento sube de $8.20 a $9.00 (+9.8 %), el costo de
FC-210 sube $6.00/m³ y el margen cae ~6 puntos **sin que nadie se entere**,
porque el precio no está atado al costo.

### 10.4 Propuesta

1. **`app/costos/` + vista `v_receta_costo`**: costo de materiales por receta
   usando el costo vigente (o un snapshot por fecha).
2. **Parámetros nuevos** en `system_settings['costos']`:
   `agua_costo`, `mano_obra_m3`, `energia_m3`, `cif_m3`, `transporte_m3`,
   `merma_pct`, `margen_objetivo_pct` (global o por resistencia).
3. **Superadmin > Recetas** muestra costo, precio y margen; alerta si
   `precio < costo` o `margen < objetivo`.
4. **El precio publicado sigue siendo decisión de Julio**, pero con el margen
   visible y auditado. No se autoajusta sin aprobación.
5. **Reconciliar** `margen_neto_m3`: o se calcula desde las recetas (y se
   documenta qué incluye) o se renombra a "margen de caja" y se explica.
6. **El bot público nunca ve costos ni márgenes**: solo `precio_m3` publicado.
7. **El bibliotecario** expone `costo_receta` y `margen_receta` solo a
   `SUPERADMIN` y `CONTADORA`.

> Estado: **hallazgo confirmado**. No es que los números estén mal; es que el
> precio no está anclado al costo y el sistema no lo advierte.

---

## 11. El bibliotecario como skill

Se adopta el patrón de skill con front matter (nombre, descripción con
disparadores, principio inviolable, sub-niveles, SOPs y checklist), como el
ejemplo `hefesto-tecnologia`.

- Skill de operación: **`.agents/skills/bibliotecario-datos/SKILL.md`**.
- Catálogo de consultas del producto: este documento §1.4.
- El bot **no** ejecuta la skill: el bot pide fichas de dato al bibliotecario
  de software, que implementa este catálogo.

Sub-niveles propuestos:

1. **Catálogo de datos** — inventario de tablas, vistas y consultas canónicas.
2. **Guardián de integridad** — procedencia, vacíos, cifras, no invención.
3. **Migraciones** — runner, numeración, no editar aplicadas.
4. **Privacidad y roles** — PII, permisos, aislamiento entre clientes.
5. **Observabilidad** — consultas lentas, errores, auditoría.

---

## 12. Decisiones actualizadas

1. **PDF:** componente independiente; cotización con folio, validez y snapshot
   de precio. Motor recomendado: WeasyPrint. (Confirmado por Dirección.)
2. **Agenda:** dos agendas, obras y visitas; `citas_comerciales` nueva.
3. **Precios:** hay editor manual, **no** un costeador. Se propone costeo por
   receta y margen visible (hallazgo §10).
4. **DeepSeek:** siempre, con API key en `.env`.
5. **Bibliotecario:** skill de datos con sub-niveles; pendiente designar al
   custodio humano de la BD en producción.

---

## 13. Handoff a Carbon y skills de pilares (2026-11-12)

Se adoptó el **estándar de skills v7.0** (5 componentes, frontmatter, router por
capas, roles de 40–70 líneas, contratos JSON Schema 2020-12 y registro de
errores) y se adaptó a Horminor:

- Colas: `q_gobierno`, `q_datos`, `q_finanzas`, `q_operacion`, `q_documentos`,
  `q_publico`.
- `parent_skill`: `asistente-horminor` / `asistente-publico`.
- Límite: `SKILL.md` ≤ 12.000 caracteres; `roles/*.md` ≤ 70 líneas.
- Capas: 0 determinista, 1 DeepSeek Flash, 2 DeepSeek Chat, 3 DeepSeek
  Reasoner + humano.

**Documento de handoff:** `docs/SKILLS_PILARES_HORMINOR.md` (mapa de 14 pilares,
dos ejemplos completos, encargo y checklist para Carbon).

**Skills creadas en el repo:**

| Skill | Componentes | Estado |
|---|---|---|
| `.agents/skills/pdf-cotizaciones/` | SKILL, router, errores, 3 roles, 2 contratos | Completa |
| `.agents/skills/banca-mercado/` | SKILL, router, errores, 3 roles, 2 contratos | Completa |
| `.agents/skills/bibliotecario-datos/` | SKILL, router, errores, 4 roles, 2 contratos propios + contratos del Gate | Completa |

Validación ejecutada: los 5 componentes existen en las tres; todos los JSON
parsean; los roles no exceden 70 líneas; los `SKILL.md` están entre 3.110 y
4.455 caracteres.
