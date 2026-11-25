# Continuidad del Cerebro — estado, arquitectura y próximos pasos

> **Para qué sirve.** Que una conversación nueva (o una persona nueva) pueda
> retomar el proyecto sin depender del historial del chat: qué está construido,
> qué se decidió, qué NO se debe hacer todavía y cuál es el siguiente paso.
>
> **Fecha:** 2026-11-16 · **Corte:** Cerebro experimental **cerrado** (fase 0–2,
> corrección de revocación aceptada, `router-1.7` congelado en laboratorio) ·
> **Suites:** 623 pruebas del CRM + 21 del router en verde · **Migraciones:** 085–092.
>
> **Documentos hermanos.**
> - Explicación funcional: `docs/HORMINOR_MANUAL_FUNCIONAL.md`
> - Cierre del router: `docs/ROUTER_CONVERSACIONAL_CIERRE.md`
> - Corrección de revocación: `docs/CORRECCION_REVOCACION_DIAZ_SUR.md`
> - Auditoría de las pruebas manuales: `docs/AUDITORIA_PRUEBAS_MANUALES_2026-11-16.md`
> - Brechas y auditoría: `docs/CEREBRO_MATRIZ_BRECHAS.md`
> - Diseño técnico: `docs/CEREBRO_VOZ_DISENO.md`
> - Contrato de canal: `docs/CONTRATO_WHATSAPP_CEREBRO.md`

---

## 1. Qué está construido (verificado)

| Pieza | Estado | Evidencia |
|---|---|---|
| Voz: ingesta, hash, STT (Groq/Whisper), normalizador es-EC | Funciona en local | `cerebro_joaquin_2026-11-15.txt` |
| Hechos citados con verificación de cita | Funciona | `test_v89_extractor.py` |
| Compilador determinístico (acciones, preguntas, estados) | Funciona | `test_v87_cerebro_compilador.py` |
| Borradores versionados y correcciones con bóveda | Funciona | `test_v90_cerebro_correcciones.py`, cadena v1→v3 en vivo |
| Vocabulario aprendido y retiro de asociaciones | Funciona | migración 087 y 090; en vivo |
| Tareas internas con aviso, vista, acuse, cierre, prioridad, plazo y escalada | Funciona | migración 088 y 090; `cerebro_tareas_internas_2026-11-15.txt` |
| Condiciones conservadas con cita (plazo, entrega contra pago, expediente) | Funciona | migración 091; `cerebro_conservacion_2026-11-16.txt` |
| Recordatorio con mensaje autorizado y envío inmediato confirmado | Funciona | `test_v94_conservacion.py`; guardas 422 |
| Varios encargos en un dictado, con corrección, cancelación y confirmación por separado | Funciona | migración 092; `test_v95_encargos.py`; `cerebro_encargos_2026-11-16.txt` |
| Separación de encargos en lenguaje natural (sin ordinales) | Funciona | prompt v7 + `test_v96_natural.py` |
| Duda acotada al dato («creo» → solo el volumen) | Funciona | `extractor._ajustar_incertidumbre`; `test_v96_natural.py` |
| Cadena de audio real (STT → encargos → acciones) | Funciona con voz sintética | `cerebro_audio_natural_2026-11-16.txt` |
| Guarda de dinero y doble confirmación | Funciona | `cerebro_guarda_dinero_2026-11-15.txt` |
| Revocación completa y negación de instrucción citada | Funciona | `test_v92_adversarial.py`; en vivo |
| Panel: franja persistente, ficha de tarea, etiquetas visibles | Funciona | navegador verificado |
| Laboratorio `/panel/cerebro` | Funciona | captura `cerebro_lab_correccion_2026-11-15.jpeg` |
| Informe semanal de errores | Funciona | `cerebro_informe_errores_2026-11-15.md` |
| Manual Vivo + skill de consulta | Funciona (documento) | `test_v93_manual_funcional.py` |
| Router conversacional (laboratorio aislado) | **Cerrado, `router-1.7`**; no conectado al CRM | 21/21 `tests_core`; `docs/ROUTER_CONVERSACIONAL_CIERRE.md` |

**Actualización local del 2026-11-24.** Gato usa un razonador semántico para
identificar el asunto, la acción y las dudas de cada turno. Los asuntos se
guardan en la conversación del panel con referencia a la revisión vigente del
Cerebro. La selección del asunto y los datos citados se validan antes de
conectar las acciones existentes. El resultado del servicio sostiene el estado
que se muestra en el chat.

**No implementado todavía** (y así debe decirse):

- Conversación por WhatsApp (entrantes no persistidos).
- Confirmación por el mismo chat de WhatsApp: cuando se conecte, Julio enviará un
  audio, leerá el resumen, corregirá y confirmará en el hilo; exige persistir
  entrantes y autorizar por riesgo, no solo por el número de teléfono.
- Envío de `enviar_cotizacion_whatsapp` desde el Cerebro (501 a propósito).
- Persistencia de `contacto.*` en la ficha del cliente.
- Aprendizaje de significados y lugares.
- Ayuda contextual dentro del CRM.
- Bóveda de audios (consentimiento y retención LOPDP).
- Conexión Gato ↔ Cerebro.
- **Router conversacional conectado al CRM**: existe solo en el laboratorio; no
  crea clientes, tareas ni cotizaciones y no envía nada.
- **Memoria entre dictados**: cada dictado es un borrador nuevo.
- **Jev (TypeSafe AI)**: idea de backlog, sin evaluar y sin fecha.
- Flujo comercial externo de WhatsApp con permisos separados.

**Limitaciones conocidas del motor antiguo (no se corrigen ahora).** Quedan
documentadas para retomarlas de forma progresiva con el sistema de correcciones,
no con frentes individuales:

- **Propone crear un cliente que Julio no pidió.** En el audio de Díaz Sur, Julio
  dice «acabo de hacer un contrato», no «créame el cliente»; el motor igual
  propone `crear_cliente`.
- **Confunde nombres.** El vocabulario aprendido convierte «Díaz Sur» en
  «Dualsur», aunque el audio diga otra cosa.
- **No siempre separa los encargos.** La transferencia de 27 000 USD quedó como
  un segundo encargo en lugar de ser un dato del primero.

---

## 2. Arquitectura decidida (2026-11-15)

### 2.1 El Cerebro no será un módulo visible para el usuario final

- Hoy se desarrolla y prueba por separado, en su **laboratorio** (`/panel/cerebro`). Esa separación se conserva hasta que esté suficientemente probado.
- En la arquitectura final, el Cerebro es la **inteligencia interna del CRM**: interpreta, recuerda, estructura y propone.
- **Gato** será la **interfaz conversacional** por la que Julio y la secretaría usan esas capacidades.
- Gato ya tiene herramientas operativas; **no se duplican dentro del Cerebro**.
- En el panel se conecta Gato con el Cerebro mediante el puente que mantiene el borrador asociado al asunto. Las operaciones de negocio conservan sus servicios y comprobantes.

### 2.2 Dos flujos con permisos y conocimientos distintos

**Flujo interno (Julio y secretaría)** — propósito principal del Cerebro:

- interpreta audios e instrucciones, recuerda contexto, aprende expresiones;
- genera tareas, pide aclaraciones, coordina módulos y permite consultar resultados;
- usa información empresarial **según los permisos del usuario autenticado**.

**Flujo externo (clientes por WhatsApp)** — independiente y limitado:

- responde sobre horarios, ubicación, contactos, productos y **precios oficiales autorizados**;
- usa herramientas comerciales específicas y aprobadas;
- **no** consulta el contexto, la memoria, los documentos internos ni las herramientas privilegiadas del Cerebro;
- **no** negocia descuentos, crédito ni condiciones especiales por iniciativa propia;
- cuando hay interés comercial que requiere atención humana, **transfiere** a Julio o al responsable, con un **resumen limitado a la conversación del cliente**, sin información interna.

**La separación se implementa con permisos, herramientas y fuentes de conocimiento distintas, no con instrucciones en el prompt.** Se pueden reutilizar componentes técnicos, pero **nunca** se traslada automáticamente el contexto privado al flujo público.

### 2.3 Responsabilidades

| Pieza | Qué hace | Qué NO hace |
|---|---|---|
| **Cerebro** | interpreta, recuerda, estructura y propone; mide el seguimiento | no es la cara visible; no duplica herramientas de Gato; no ejecuta dinero |
| **Gato** | interfaz conversacional; usa herramientas operativas autorizadas | no interpreta dictados ni arma borradores |
| **Módulos** (clientes, cotizaciones, caja, WhatsApp) | ejecutan y verifican sus operaciones | no interpretan lenguaje |
| **Flujo externo** | atiende consultas comerciales aprobadas y transfiere | no accede al contexto interno |

**Futuro:** Gato podrá usar al Cerebro para instrucciones internas, de forma **controlada** y con permisos propios. El acceso comercial externo tendrá herramientas y conocimientos **deliberadamente limitados**.

---

## 2.4 Decisión 2026-11-18: Cerebro visible y conexión con Gato

> **Pedido explícito de Julio.** Cambia dos reglas anteriores de este documento
> (2.1 y el invariante 8). Se registra aquí el porqué y el alcance.

- **Cerebro visible.** Se deja visible en el panel aunque todavía no entregue
  producción completa, para probarlo con casos reales. Sigue marcado **BETA**.
- **Conectar Cerebro con Gato.** Gato será la única interfaz conversacional.
  La conexión es **controlada**: solo perfiles internos con el módulo `cerebro`
  habilitado, sin exponer el contexto interno al flujo comercial externo.
- **Qué NO cambia.** El Cerebro no ejecuta dinero, no escribe negocio sin
  confirmación humana y no reemplaza las herramientas de Gato. El flujo externo
  de clientes sigue sin acceso.
- **Requisito de entorno.** El VPS corre un linaje anterior sin `app/cerebro`,
  sin `app/voz` y sin las migraciones 079–092. Para verlo en producción hay que
  alinear el servidor con la versión local, en una ventana con respaldo.

## 2.5 Modelo Gato / Miau (2026-11-18, iteración de Julio)

> Nombres definitivos: **Gato** es la cara pública en WhatsApp; **Miau** es el
> Cerebro interno. El asistente del panel se llamaba "Gato" por historia; debe
> renombrarse a **Miau**.

| Pieza | Quién le habla | Qué sabe | Qué NO hace |
|---|---|---|---|
| **Gato** (público) | Clientes por WhatsApp | Empresa, productos, precios oficiales, horarios, agenda disponible | No ve contexto interno, cartera, tareas ni memoria del Cerebro |
| **Miau** (Cerebro interno) | Julio, secretaría, planta | Todo lo de la empresa según permisos; aprende cómo habla Julio; organiza tareas; análisis financiero (futuro) | No conversa con clientes ni envía mensajes comerciales |
| **Agendamiento** (componente compartido) | Miau, Julio, secretaría y Gato (cliente) | Disponibilidad, citas, entregas y avisos | No decide precios ni crédito |

### El momento cero (Julio como input del cliente)

1. Julio envía audios, videos y documentos y pide: "registra esto en el cliente X".
2. Miau interpreta, separa los archivos y propone un **paquete de alta**:
   cliente en el CRM, carpeta del cliente, carpeta en Bunny y clasificación de
   cada archivo.
3. **El pasito:** Julio ratifica el paquete. Sin ratificación no se escribe nada.
4. Al confirmar, Miau ejecuta: crea/reutiliza el cliente, crea la carpeta en
   Bunny, mueve la multimedia y deja la auditoría en `cerebro_ejecuciones`.

### Manos y contingencias

- Miau debe poder **mover, renombrar y retirar** archivos de Bunny, siempre con
  vista previa (dry-run), confirmación humana y registro.
- Si una operación falla o es riesgosa, Miau **abre los enlaces** exactos para
  que la secretaría lo haga a mano. Prever el contratiempo es parte del diseño.
- Toda corrección se agrega; nunca se reescribe el historial.

### Fronteras que no se cruzan

- Gato no recibe el contexto interno; Miau no atiende clientes.
- El aviso al cliente sale por Gato, aunque el agendamiento lo haya creado Miau.
- La separación es por permisos, herramientas y fuentes, no por prompt.

### Brecha actual (verificada en código)

- `dispatch_schedule` agenda **entregas/mixers**, no citas comerciales: el
  agendamiento de citas es nuevo.
- `crear_cliente` y `crear_cotizacion_borrador` ya tienen ejecutor y se confirman
  en `/panel/cerebro`; `enviar_cotizacion_whatsapp` sigue respondiendo **501**.
- El cliente de Bunny solo tiene `subir`; no hay listar, mover, renombrar ni
  borrar.
- El flujo público de WhatsApp (Gato) no existe.

## 3. Qué está implementado y qué es arquitectura futura

| Tema | Implementado hoy | Arquitectura futura |
|---|---|---|
| Cerebro como módulo visible | Laboratorio `/panel/cerebro` (pruebas) | Inteligencia interna, sin módulo visible |
| Interfaz para Julio/secretaría | Panel + laboratorio | Gato |
| Conexión Gato ↔ Cerebro | **No existe** | Controlada, con permisos |
| Flujo externo de WhatsApp | **No existe** (M1 en SANDBOX) | Limitado a información comercial aprobada |
| Transferencia a humano | **No existe** | Resumen de la conversación del cliente |
| Ayuda contextual del manual | **No existe** | Gato consulta el Manual Vivo |
| Permisos por flujo | Roles del panel (`panel_users_acl`) | Permisos, herramientas y fuentes separadas por flujo |
| Router conversacional | Laboratorio `:8055`, versión `router-1.7`, cerrado | Decidir si reemplaza al motor del panel, solo con pedido explícito |

**Regla:** todo lo de la columna derecha se documenta como futuro. No se presenta
como existente ni se implementa por adelantado.

---

## 4. Prioridades para la próxima conversación

**La fase del router conversacional está cerrada.** La versión `router-1.7` se
conserva tal como está; no se amplía la arquitectura. Los errores que aparezcan
se corrigen con la caja de respuesta y la traza existentes.

Las prioridades, en orden:

1. ~~Arreglar el defecto de producción de `dictado_revocado`.~~ **Hecho:** las
   marcas se comparan como palabras completas y la revocación se aplica por
   encargo (`docs/CORRECCION_REVOCACION_DIAZ_SUR.md`).
2. ~~Volver a pasar el audio real de 122 s.~~ **Hecho:** ya no termina en
   `SIN_ACCIONES`; propone 2 encargos y pide los datos que faltan. Detalle y
   límites en el documento de la corrección.
3. **Decidir, solo con pedido explícito**, si el router reemplaza al motor del
   panel. No se hace por iniciativa técnica.

Lo demás sigue como estaba: sin conectar Gato, sin mensajes externos, sin
operaciones financieras y sin despachos automáticos. El siguiente trabajo es el
resto del ERP de Horminor.

---

## 5. Cómo verificar el estado (comandos)

Desde `orminorth/`:

```powershell
# contenedores
docker ps --filter name=orminorth --format "{{.Names}}  {{.Status}}"

# migraciones (deben estar 085 a 090 aplicadas)
docker compose run --rm --no-deps core-api python scripts/db_migrate.py

# suite completa (hoy 620)
docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto

# candado del Hito 3
docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py

# conservación de instrucciones sobre el dictado real (sin LLM)
docker compose run --rm --no-deps core-api python scripts/evidencia_conservacion.py

# tres encargos independientes (sin LLM)
docker compose run --rm --no-deps core-api python scripts/evidencia_encargos.py

# evidencia del ciclo de tareas internas
docker compose run --rm --no-deps core-api python scripts/evidencia_tareas_internas.py

# informe semanal de errores
docker compose run --rm --no-deps core-api python scripts/informe_cerebro_errores.py --dias 7
```

**Nota de entorno:** `docs/`, `.agents/` y `AGENTS.md` están montados en solo
lectura dentro de `core-api` para que la suite pueda verificar el manual y la
skill (`docker-compose.yml`). Los cambios de `app/` requieren
`docker compose build core-api` + `up -d --no-deps core-api`.

---

## 6. Mapa de archivos clave

| Ruta | Qué es |
|---|---|
| `services/core-api/app/voz/` | ingesta, STT y normalizador |
| `services/core-api/app/cerebro/hechos.py` | hechos citados, estados (incluido `TENTATIVO`) |
| `services/core-api/app/cerebro/compilador.py` | reglas, ficha, guardas (negación, revocación, dinero) |
| `services/core-api/app/cerebro/internas.py` | tareas internas, aviso/vista/acuse, prioridad, escalada, retiro |
| `services/core-api/app/cerebro/revision.py` | correcciones versionadas y resumen «Lo que entendí» |
| `services/core-api/app/cerebro/router.py` | endpoints de interpretar, corregir, confirmar y tareas |
| `services/core-api/app/web/templates/cerebro_lab.html` | laboratorio (uso interno de prueba) |
| `services/core-api/app/web/templates/panel.html` | franja, campanita, tareas y etiquetas visibles |
| `db/migrations/085…092` | esquema de voz, cerebro, correcciones, tareas, acuse, condiciones y encargos |
| `services/core-api/tests/` | 620 pruebas; `test_v92` adversarial, `test_v93` manual, `test_v94` conservación, `test_v95` encargos y `test_v96` lenguaje natural |
| `services/core-api/app/cerebro/encargos.py` | segmentación del dictado en asuntos independientes |
| `docs/WHATSAPP_INTERNO_IMPLEMENTACION.md` | secuencia técnica del WhatsApp interno (futuro, no implementado) |
| `scripts/evidencia_*.py` | evidencia reproducible |
| `experiments/router_horminor/` | router conversacional cerrado (`router-1.7`); laboratorio, no CRM |
| `docs/ROUTER_CONVERSACIONAL_CIERRE.md` | qué es, componentes, correcciones, límites y backlog |
| `docs/HORMINOR_MANUAL_FUNCIONAL.md` | **Manual Vivo** (fuente única de definiciones) |
| `docs/CEREBRO_MATRIZ_BRECHAS.md` | brechas y estado real por requisito |
| `docs/CONTRATO_WHATSAPP_CEREBRO.md` | contrato del canal futuro |

---

## 7. Invariantes que no se negocian

1. Ningún dato de negocio sin cita (salvo corrección humana explícita).
2. Ninguna escritura de negocio sin confirmación humana.
3. Ningún dinero calculado por la IA ni registrado sin doble confirmación.
4. Ninguna corrección reescribe el pasado: se agrega.
5. Ninguna tarea se duplica por reintento o mensaje repetido.
6. Un dictado revocado no genera trabajo para nadie.
7. **El Cerebro se ve como laboratorio BETA.** Desde el 2026-11-18 Julio pidió
   dejarlo visible en el panel; sigue marcado BETA y no ejecuta producción.
8. **Gato puede invocar al Cerebro solo de forma explícita y controlada.**
   Desde el 2026-11-18 existe un puente con prefijo (`cerebro:`, `dictado:`);
   no duplica herramientas de Gato y exige el módulo `cerebro`.
9. **El flujo externo no accede al contexto interno**, y la separación es por permisos y herramientas, no por prompt.
10. Si el sistema no sabe, pregunta. Si no puede, lo dice.

---

## 8. Decisiones abiertas (no bloquean esta etapa)

- Persistencia de mensajes entrantes de WhatsApp (hoy no se guardan).
- Identidad y autorización del remitente por riesgo de la acción.
- Retención y consentimiento de audio (LOPDP).
- Cómo se transfiere una conversación externa y qué resumen exacto se entrega.
- Cuándo y cómo Gato consultará el Manual Vivo (sin conectar el Cerebro).
- Si el retiro de vocabulario tendrá botón en el panel.
- **Jev (TypeSafe AI)** como posible clasificador o verificador de intenciones,
  responsables, órdenes nuevas y malentendidos. Idea de backlog: sin fecha, sin
  compromiso de integración y sin cambios de código. Se retoma solo si las
  conversaciones reales muestran una necesidad que justifique incorporarlo.

---

## 9. Bitácora del documento

| Versión | Fecha | Cambio |
|---|---|---|
| v1 | 2026-11-15 | Documento de continuidad: estado, arquitectura Cerebro/Gato, dos flujos, prioridades y reglas. |
| v1.1 | 2026-11-16 | Conservación de condiciones (migración 091), mensaje autorizado del recordatorio; 601 pruebas. Se registra que la confirmación por el mismo chat de WhatsApp es futura. |
| v1.2 | 2026-11-16 | Encargos independientes (migración 092): corregir, cancelar y confirmar por asunto; 610 pruebas. La conversación por hilos sigue siendo de la siguiente fase. |
| v1.3 | 2026-11-16 | Separación de encargos en lenguaje natural (prompt v7), duda acotada al dato y cadena de audio con STT real; 620 pruebas. Se agrega la secuencia técnica del WhatsApp interno como documento futuro. |
| v1.4 | 2026-11-16 | Cierre de la fase del router conversacional (`router-1.7`, laboratorio): estado, límites, correcciones, backlog de Jev y siguiente paso (defecto de producción y audio real). 620 + 21 pruebas en verde. |
| v1.5 | 2026-11-16 | Corrección de `dictado_revocado`: expresiones completas y revocación por encargo. Audio de Díaz Sur verificado (2 encargos, 1 acción, preguntas pendientes). 623 pruebas. |
| v1.6 | 2026-11-16 | Cierre aceptado del Cerebro experimental (commit `c43c5c7`). Limitaciones del motor antiguo documentadas: cliente no pedido, nombres confundidos y encargos no separados. El siguiente trabajo es el resto del ERP. |
| v1.7 | 2026-11-18 | Decision de Julio: Cerebro visible en el panel (BETA) y conexion controlada con Gato. Se documenta que el VPS aun no tiene el modulo y que la alineacion del servidor es requisito previo. |
| v1.8 | 2026-11-18 | VPS alineado con la version local (migraciones 079-092). Cerebro visible como BETA para Julio y puente controlado Gato -> Cerebro con prefijo explicito. |
| v1.9 | 2026-11-18 | Modelo Gato/Miau: Gato duena del WhatsApp publico, Miau cerebro interno; agendamiento compartido; momento cero con ratificacion; manos en Bunny con contingencias. |
