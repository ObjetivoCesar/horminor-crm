# Hitos — orden de trabajo de Horminor

> **Documento obligatorio.** Se lee al abrir cualquier sesión, junto con
> `ESTADO.md` y las últimas 3 entradas de la bitácora. Si cambia el orden, se
> cambia aquí y en la skill `orminorth-documentos`.
>
> **Fecha:** 2026-11-19. **Dueño del orden de trabajo:** este archivo.
>
> **Qué va aquí y qué no:** aquí va el plan, el estado en una línea y los
> enlaces. La narración, los comandos y las decisiones viven en la bitácora;
> la foto del presente y los bloqueos, en `ESTADO.md`. **No se copia la
> bitácora: se enlaza.**

## 0. Regla de la fecha (no se negocia)

Todo módulo que dependa del día debe usar **una sola** fuente:
`app/tiempo.py` (`America/Guayaquil`). Nunca `datetime.now()` sin zona, nunca
una fecha calculada en el navegador para decisiones de negocio.

- `hoy()` → fecha de Ecuador.
- `ahora()` → fecha y hora con zona.
- La API puede exponer `GET /api/v1/sistema/hoy` para que el panel muestre la
  misma fecha, pero la decisión siempre se toma en el servidor.

**Por qué:** ya hubo fallos por variables de fecha faltantes. Un módulo que no
sabe qué día es en Ecuador no puede agendar ni marcar un lead caído.

## 1. Estado al 2026-11-19

**Hecho y en producción:** acceso al panel, WhatsApp con multimedia y chat en
vivo, iconos de cabecera, Cerebro visible y puente con Gato, VPS alineado,
momento cero (cliente + carpeta + manos + paquete), orden de clientes por último
mensaje, chat como primera pestaña, vigilante de WhatsApp.

**Cerrado 2026-11-19:** núcleo comercial (**H1**). Migraciones **096–097**
(`leads`, `lead_eventos`, `lead_reglas_caida`, `citas`, `cita_eventos`),
`app/tiempo.py` y `/api/v1/comercial/*`. Los tres orígenes (panel, Gato y
WhatsApp) entran por el mismo módulo; el origen lo fija el servidor. Evidencia:
`pytest` **727 passed**, `scripts/h1_comercial_check.py` → `[H1 COMERCIAL: OK]` y
candado del Hito 3 en verde.

**Desplegado en el VPS el 2026-11-19:** migración **097** aplicada, imagen
reconstruida y servicio sano. En el servidor: `26 passed` (pruebas H1),
`[H1 COMERCIAL: OK]`, `/api/v1/comercial/hoy` y `/panel` responden. El candado
del Hito 3 se ejecutó en modo producción: **30 verificaciones OK** y la única
diferencia es `modo=PRODUCCION` frente al `SANDBOX` que espera el candado; no es
una regresión.

**Pendiente:** confirmar una cita con datos reales de Julio.

## 2. Hitos

| # | Hito | Alcance | Criterio de cierre | Estado |
|---|---|---|---|---|
| **H1** | **Núcleo comercial: leads + agendamiento independiente** | Módulo propio que funciona sin importar el origen: lead nuevo por WhatsApp, Julio desde Gato o la secretaría desde el panel. La fecha siempre sale de `app/tiempo.py`. | Un lead creado desde los tres orígenes con las mismas reglas; una cita creada desde los tres orígenes y visible en la agenda; tests de fecha y de origen | **cerrado 2026-11-19**: los tres orígenes pasan por el módulo; cita con choque, estados y auditoría; `[H1 COMERCIAL: OK]` |
| **H2** | **Audio por Gato** | Gato recibe una nota de voz y la pasa al **transcriptor existente** (`app/voz`); no se duplica código. | Un audio real termina en el mismo borrador del Cerebro que un texto | **cerrado 2026-11-19**: botón de micrófono en Gato → transcripción → borrador del Cerebro; `732 passed` y audio real verificado |
| **H3** | **Manos de Bunny** | Listar, mover, renombrar y borrar con vista previa, confirmación, **auditoría persistente** y manifiesto con archivos. | Una operación destructiva deja fila de auditoría y el manifiesto lista los archivos movidos | en curso (base hecha) |
| **H4** | **Visual / móvil** | Iterativo con las ideas de Julio: header, clientes, chat, secretaría y tablas en celular. | Las pantallas principales se usan a 390 px sin zoom ni scroll horizontal | pendiente (iterativo) |
| **H5** | **Gato público (WhatsApp)** | Informar, vender y agendar; sin contexto interno; lead con al menos una respuesta. | Un cliente real informa, recibe precio oficial y solicita cita | pendiente (skill lista) |
| **H6** | **Blindaje de entrega** | Login propio, servidor con Evolution aislado y versión estable, backups programados, suite completa en el VPS. | Panel sin basic auth, backup restaurado en prueba, suite en verde en el VPS | pendiente |
| **H7** | **ERP de fondo** | Cotizaciones, contratos, cobranza, inventario. | Según `PENDIENTES.md` (Q, C, F) | pendiente |

## 3. Reglas del núcleo comercial (H1)

> Contrato de uso: `docs/NUCLEO_COMERCIAL.md` (un solo dueño; los
> consumidores solo piden "dame / notifícame / agenda a...").


1. **Independiente del origen.** El módulo no depende de WhatsApp ni de Gato:
   recibe el mensaje y aplica las mismas reglas. **El origen lo fija el
   servidor** (`PANEL`, `GATO`, `WHATSAPP`), nunca el cuerpo del cliente ni un
   desplegable del panel.
2. **Un teléfono = un lead.** Si vuelve a escribir, se reutiliza.
3. **Lead con al menos una respuesta** de la empresa (ver `docs/LEADS.md`).
4. **Caída por intención**, no por días; los plazos quedan `NULL` hasta que
   Julio los defina.
5. **Cita = solicitud + confirmación.** Gato solicita; la confirmación es humana
   o por la regla que se defina.
6. **Fecha de Ecuador** en toda decisión: `app/tiempo.py`.
7. **Trazabilidad:** cada cambio de estado deja evento en `lead_eventos`.

## 4. Decisiones pendientes de Julio

- ¿La respuesta automática del bot cuenta para crear el lead?
- Días e intentos de recontacto.
- Quién marca `CAIDO`.
- Horario y duración de las citas; quién confirma.
- Precios `OFICIAL` y umbral de merma.

## 5. Registro de avance

> Una línea por hito y por sesión. El detalle está en la bitácora; aquí solo se
> enlaza. Si una fila repite lo que ya dice la bitácora, se borra.

| Fecha | Hito | Qué se hizo (resumen) | Piezas / archivos | Bitácora |
|---|---|---|---|---|
| 2026-11-18 | H6 | Acceso al panel: reset de la clave del basic auth de Caddy | `/etc/caddy/Caddyfile`, `vps-entrada/HORMINOR_PANEL_ACCESO.txt` | 2026-11-18 (tarde) |
| 2026-11-18 | H5 | WhatsApp revinculado; multimedia (imagen, audio, video, PDF) al chat y a Bunny; notas de video | `app/whatsapp_espejo/`, `app/services/media.py`, `templates/panel.html` | 2026-11-18 (tarde) |
| 2026-11-18 | H1 | VPS alineado con la versión local (migraciones 079-092) | `services/core-api/app`, `db/migrations`, `docker-compose.vps.yml` | 2026-11-18 (noche) |
| 2026-11-18 | H1 | Cerebro visible (BETA) y puente Gato→Cerebro con prefijo | `app/cerebro/`, `app/asistente/cerebro_bridge.py` | 2026-11-18 (noche) |
| 2026-11-18 | H3 | Momento cero: ejecutor `crear_cliente`, carpeta en Bunny, manos (listar/mover/renombrar/borrar) | `app/cerebro/ejecutores.py`, `app/cerebro/router.py`, `app/m1_whatsapp/bunny.py` | 2026-11-18 (noche II–III) |
| 2026-11-18 | H3 | Paquete de alta: API y botón en `/panel/cerebro` | `app/cerebro/router.py`, `templates/cerebro_lab.html` | 2026-11-18 (noche IV–V) |
| 2026-11-18 | H4 | Chat como primera pestaña y clientes por último mensaje | `templates/panel.html`, `app/routers/clients_search.py` | 2026-11-18 (noche VI–VII) |
| 2026-11-18 | H6 | Vigilante de WhatsApp (cron, reinicio, estado) | `scripts/vigilante_whatsapp.py` | 2026-11-18 (noche VIII) |
| 2026-11-19 | — | Documento de hitos y lectura obligatoria | `docs/HITOS.md`, `AGENTS.md`, `.agents/README.md`, skill `orminorth-documentos` | 2026-11-19 |
| 2026-11-19 | H1 | Fecha de Ecuador en una sola fuente | `app/tiempo.py`, `tests/test_v222_tiempo.py` | 2026-11-19 |
| 2026-11-19 | H1 | Esquema de leads y citas (migración 096) | `db/migrations/096_nucleo_comercial_leads_citas.sql` | 2026-11-19 |
| 2026-11-19 | H1 | API comercial: leads, respuestas por intención, citas | `app/comercial/leads.py`, `app/comercial/citas.py`, `app/comercial/router.py` | 2026-11-19 |
| 2026-11-19 | H1 | Contrato de un solo dueño y UI en Secretaría | `docs/NUCLEO_COMERCIAL.md`, `templates/panel.html` | 2026-11-19 (II) |
| 2026-11-19 | H1 | Gato interno al módulo comercial: leads caídos y agendar | `app/asistente/comercial_bridge.py`, `app/asistente/router.py`, `app/comercial/leads.py` | 2026-11-19 (IV) |
| 2026-11-19 | H2 | Audio por Gato reutilizando `app/voz` | `app/asistente/router.py` (POST `/api/v1/asistente/audio`) | 2026-11-19 (IV) |
| 2026-11-19 | H2 | Cascada de claves Groq y `.env` del VPS | `app/voz/stt.py`, `app/voz/proveedores/groq.py`, `.env` del VPS | 2026-11-19 (VI) |
| 2026-11-19 | H1 | Cierre: respuesta de empresa vs mensaje del lead, revivir y origen forzado por servidor | `app/comercial/leads.py`, `app/comercial/router.py` | 2026-11-19 (VII) |
| 2026-11-19 | H1 | Citas: choque del mismo lead/cliente, máquina de estados y auditoría (`cita_eventos`) | `app/comercial/citas.py`, `db/migrations/097_cita_eventos.sql` | 2026-11-19 (VII) |
| 2026-11-19 | H1 | WhatsApp conectado al módulo (webhook pide, no crea) y parser de citas compartido | `app/comercial/whatsapp.py`, `app/comercial/intencion.py`, `app/m1_whatsapp/pipeline.py`, `app/m1_whatsapp/runtime.py` | 2026-11-19 (VII) |
| 2026-11-19 | H1 | **H1 cerrado**: `pytest` **727 passed**, `[H1 COMERCIAL: OK]`, candado Hito 3 en verde | `.agents/evidencias/pytest_h1_cierre_2026-11-19.txt`, `h1_comercial_check_2026-11-19.txt`, `hito3_lock_2026-11-19.txt` | 2026-11-19 (VII) |
| 2026-11-19 | H1 | **Desplegado en el VPS**: respaldo, 097 aplicada, imagen reconstruida, `26 passed`, `[H1 COMERCIAL: OK]`, `/panel` 200 | `.agents/evidencias/h1_vps_2026-11-19.txt`, `/root/backup_h1_20261119`, `/root/backups/horminor_pre_h1_20261119.sql.gz` | 2026-11-19 (VIII) |
| 2026-11-19 | H2 | **Dictado por audio desde Gato**: botón de micrófono, transcripción visible y entrega al Cerebro (`modo=dictado`) | `app/asistente/router.py`, `app/web/templates/panel.html`, `.agents/evidencias/gato_audio_2026-11-19.txt` | 2026-11-19 (IX) |
| 2026-11-19 | H2 | **Una instrucción con dos destinatarios = un encargo**: fusión determinística de frases de coordinación y tarea interna «chofer y Julio»; de 3 encargos/7 preguntas a 1/3 | `app/cerebro/encargos.py`, `app/cerebro/compilador.py`, `app/cerebro/internas.py`, `tests/test_v226_gato_audio_encargos.py` | 2026-11-19 (IX) |
| 2026-11-19 | H2 | **Audio de Gato desplegado en el VPS**: imagen reconstruida, `19 passed`, audio real `HTTP 200` con `estado=OK` | `.agents/evidencias/gato_audio_vps_2026-11-19.txt`, `/root/backup_gato_audio_20261119` | 2026-11-19 (X) |
| 2026-11-19 | H2 | **Formato del resumen de Gato**: negritas, viñetas y saltos; citas largas recortadas. Comprobado que la orden de Pastrana **no agenda**, solo deja borrador y tareas | `app/asistente/cerebro_bridge.py`, `app/cerebro/revision.py`, `templates/panel.html`, `.agents/evidencias/gato_formato_pastrana_2026-11-19.txt` | 2026-11-19 (XI) |
| 2026-11-19 | H2 | **Formato desplegado en el VPS**: respaldo, imagen reconstruida, `11 passed` y render con viñetas verificado en el servidor | `.agents/evidencias/gato_formato_vps_2026-11-19.txt`, `gato_formato_render_2026-11-19.txt`, `/root/backup_gato_formato_20261119` | 2026-11-19 (XII) |
| 2026-11-19 | H2 | **Calendario de Gato**: el prefijo `dictado:` gana al atajo comercial; `disponibilidad` acepta ISO; «este sábado/domingo» se calcula con `app/tiempo`; prompt con país y hoy | `app/asistente/router.py`, `bibliotecario.py`, `persona.py`, `app/comercial/intencion.py`, `.agents/evidencias/gato_calendario_2026-11-19.txt` | 2026-11-19 (XIII) |
| 2026-11-19 | H2 | **Cifras dictadas y despliegue**: la guarda acepta cifras de un `dictado:` y sigue bloqueando las inventadas; VPS con `7 passed` y seguimiento `OK` (sábado 21 / domingo 22) | `app/asistente/guardas.py`, `proveedores.py`, `.agents/evidencias/gato_calendario_vps_seguimiento_2026-11-19.json` | 2026-11-19 (XIV) |
| 2026-11-19 | H2 | **Memoria entre dictados**: el Cerebro recibe los dictados previos de la misma conversación; el seguimiento conserva cliente/volumen/pago y «me acaba de dar en efectivo» marca el ingreso | `app/asistente/router.py`, `cerebro_bridge.py`, `app/cerebro/router.py`, `extractor.py`, `dinero.py`, `.agents/evidencias/gato_memoria_dictados_2026-11-19.txt` | 2026-11-19 (XV) |
| 2026-11-19 | H2 | **Aviso de permiso de Voz**: el audio con un perfil sin Voz devuelve un mensaje claro con el perfil y la salida (cambiar a Julio); Julio verificado con audio `HTTP 200` | `app/asistente/router.py`, `templates/panel.html`, `.agents/evidencias/gato_audio_permiso_2026-11-19.txt` | 2026-11-19 (XVI) |
| 2026-11-19 | H2 | **Perfil base «Julio» sin UUID**: la opción base lleva su UUID; si una pestaña vieja manda solo el rol `SUPERADMIN`, el Cerebro usa el perfil base. Audio y dictado `HTTP 200` | `templates/panel.html`, `app/asistente/cerebro_bridge.py`, `.agents/evidencias/gato_audio_permiso_2026-11-19.txt` | 2026-11-19 (XVII) |
| 2026-11-19 | H2 | **Fase 1 de conversaciones**: migración 098, `gato_conversaciones`, refresh atómico, carga del hilo, `client_turn_id`, contexto deliberado y enlaces a borradores/extracciones | `db/migrations/098_gato_conversaciones.sql`, `app/asistente/conversaciones.py`, `router.py`, `cerebro/router.py`, `templates/panel.html`; `.agents/evidencias/gato_conversaciones_fase1_2026-11-19.txt` | 2026-11-19 (XVIII) |

## 6. Cómo se actualiza

1. Al cerrar una sesión: añadir **una fila** al registro de avance y mover el
   estado del hito.
2. La narrativa, los comandos y las decisiones van **solo** a la bitácora.
3. `ESTADO.md` se actualiza solo si cambió la foto del presente (dónde corre,
   qué está roto).
4. Si dos documentos repiten lo mismo, se borra uno. La regla está en
   `.agents/skills/orminorth-documentos/SKILL.md`.
