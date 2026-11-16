# Continuidad del Cerebro — estado, arquitectura y próximos pasos

> **Para qué sirve.** Que una conversación nueva (o una persona nueva) pueda
> retomar el proyecto sin depender del historial del chat: qué está construido,
> qué se decidió, qué NO se debe hacer todavía y cuál es el siguiente paso.
>
> **Fecha:** 2026-11-16 · **Corte:** Cerebro fases 0–2 + incremento v2 +
> conservación + encargos independientes + lenguaje natural y audio ·
> **Suites:** 620 pruebas en verde · **Migraciones:** 085–092.
>
> **Documentos hermanos.**
> - Explicación funcional: `docs/HORMINOR_MANUAL_FUNCIONAL.md`
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

**No implementado todavía** (y así debe decirse):

- Conversación por WhatsApp (entrantes no persistidos).
- **Hilos de conversación y asuntos que sobreviven entre mensajes.** El
  laboratorio separa los encargos *dentro de un dictado*; mantener ese hilo
  cuando Julio responde «cancela el segundo» en otro audio exige conversación
  persistida (siguiente fase).
- Confirmación por el mismo chat de WhatsApp: cuando se conecte, Julio enviará un
  audio, leerá el resumen, corregirá y confirmará en el hilo; exige persistir
  entrantes y autorizar por riesgo, no solo por el número de teléfono.
- Ejecución de `crear_cliente` y `crear_cotizacion_borrador` desde el Cerebro (501 a propósito).
- Persistencia de `contacto.*` en la ficha del cliente.
- Aprendizaje de significados y lugares.
- Ayuda contextual dentro del CRM.
- Bóveda de audios (consentimiento y retención LOPDP).
- Conexión Gato ↔ Cerebro.
- Flujo comercial externo de WhatsApp con permisos separados.

---

## 2. Arquitectura decidida (2026-11-15)

### 2.1 El Cerebro no será un módulo visible para el usuario final

- Hoy se desarrolla y prueba por separado, en su **laboratorio** (`/panel/cerebro`). Esa separación se conserva hasta que esté suficientemente probado.
- En la arquitectura final, el Cerebro es la **inteligencia interna del CRM**: interpreta, recuerda, estructura y propone.
- **Gato** será la **interfaz conversacional** por la que Julio y la secretaría usan esas capacidades.
- Gato ya tiene herramientas operativas; **no se duplican dentro del Cerebro**.
- **Decisión explícita:** por ahora **no** se conecta Gato con el Cerebro y **no** se reemplazan funciones existentes. Primero se termina de probar y documentar el comportamiento interno.

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

**Regla:** todo lo de la columna derecha se documenta como futuro. No se presenta
como existente ni se implementa por adelantado.

---

## 4. Prioridades para la próxima conversación

1. **Conservar y verificar** lo construido; este documento y la arquitectura quedan registrados.
2. **Auditar y perfeccionar el Cerebro** de forma independiente (sin conectar Gato).
3. **Documentar la interfaz futura** Cerebro–Gato–módulos, con la separación de permisos internos y públicos.
4. **Preparar el flujo conversacional interno** de Julio por WhatsApp, con identidad y autorización.
5. **Definir por separado** la atención comercial externa y el procedimiento de transferencia a Julio.

La funcionalidad de que **Gato consulte el Manual Vivo** queda registrada como
pendiente, pero **no** es motivo para conectar anticipadamente Gato y Cerebro.

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
7. **El Cerebro no es visible para el usuario final.** El laboratorio es de prueba.
8. **No conectar Gato con el Cerebro** ni duplicar las herramientas de Gato hasta que se decida.
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

---

## 9. Bitácora del documento

| Versión | Fecha | Cambio |
|---|---|---|
| v1 | 2026-11-15 | Documento de continuidad: estado, arquitectura Cerebro/Gato, dos flujos, prioridades y reglas. |
| v1.1 | 2026-11-16 | Conservación de condiciones (migración 091), mensaje autorizado del recordatorio; 601 pruebas. Se registra que la confirmación por el mismo chat de WhatsApp es futura. |
| v1.2 | 2026-11-16 | Encargos independientes (migración 092): corregir, cancelar y confirmar por asunto; 610 pruebas. La conversación por hilos sigue siendo de la siguiente fase. |
| v1.3 | 2026-11-16 | Separación de encargos en lenguaje natural (prompt v7), duda acotada al dato y cadena de audio con STT real; 620 pruebas. Se agrega la secuencia técnica del WhatsApp interno como documento futuro. |
