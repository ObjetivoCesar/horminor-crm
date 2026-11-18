# ESTADO DEL PROYECTO

> Foto del presente. Se reescribe en cada sesión. La historia está en `BITACORA.md`.
> Última actualización: **2026-11-18** (espejo v9.8: **chat en vivo por SSE** —
> el hilo se actualiza solo, sin pulsar Sincronizar; multimedia entrante real;
> sesión LID reparada, número de prueba 0967491847, corte de historial y altura
> fija del chat; **674 pruebas**. **Desplegado en el VPS** con parche
> quirúrgico: el endpoint SSE responde y Caddy lo entrega sin buffering
> (38 ms); falta solo la confirmación con un WhatsApp real desde el celular).
> Base v6.17: Custodio v4.4.0 + HTTP, agenda única `HorminorAgenda`,
> compras/caja chica, perfiles ACL, Superadmin por Action Cards, Carpetas de
> Clientes con buscador Sabueso, bancos con color de marca, **facturas
> internas adjuntas al cliente** (PDF o foto) consultables por Gato,
> **recordatorios por WhatsApp con ratificación, adjuntos y redacción propia**
> y **ubicación de la obra en la cotización** (texto, GPS y pin de WhatsApp).
> 37 migraciones, 57 tablas, 11 vistas, 30 cuentas; **586 tests** y los 2
> candados en verde. Siguiente foco: conservar y verificar lo construido; el
> Cerebro sigue como inteligencia interna (sin conectar a Gato).
>
> **Continuidad y arquitectura:** `docs/CONTINUIDAD_CEREBRO.md` — el Cerebro no
> será un módulo visible; Gato será la interfaz; flujo interno y flujo comercial
> externo separados por permisos, herramientas y fuentes. **Manual Vivo:**
> `docs/HORMINOR_MANUAL_FUNCIONAL.md`.

## Hitos

| Hito | MÃ³dulo | Estado | Evidencia | QuÃ© falta para cerrar |
|---|---|---|---|---|
| 1 | M0 â€” Datos y configuraciÃ³n | ðŸŸ¢ **Cerrado** con semilla oficial | `evidencias/hito1_lock_2026-11-08.txt`: `[CANDADO CERRADO]`, 235 movimientos de kardex, Ã³rdenes valoradas ($37.760 y $8.216) | Nada bloqueante. Re-verificar si se editan recetas |
| â€” | Superadmin â€” ConfiguraciÃ³n en caliente | ðŸŸ¢ Construido y editable desde el panel | 7 secciones, CRUD de recetas/flota, simulador de WhatsApp y outbox | AutenticaciÃ³n antes de exponerlo a Internet |
| 2 | M2 â€” Motor determinÃ­stico | ðŸŸ¡ Construido, verificado local | `evidencias/pytest_panel_v44_2026-11-09.txt`: **247 tests** + candado Hito 1 | Probar desde el CRM de la agencia en el VPS |
| 2 | M5 â€” Nodo Centinela | ðŸŸ¡ Construido, verificado local | `evidencias/hito3_4_live_2026-11-08.txt`: 12 checks, `modo=SANDBOX`, `judge_mode=DETERMINISTIC_FALLBACK`; Evolution/Bunny en OK | Webhook real del CRM; umbral de merma que defina Julio |
| 3 | M1 â€” WhatsApp (Evolution + Jeb + Bunny) | ðŸŸ¢ **Cerrado en SANDBOX** | `evidencias/hito3_lock_2026-11-08.txt`: `[CANDADO CERRADO EN SANDBOX]`; 4 compuertas, JSONB y outbox | ProducciÃ³n real: cargar credenciales, apagar SANDBOX y repetir el candado |
| 4 | M3 â€” Ventanilla de SecretarÃ­a + Caja | ðŸŸ¢ **Cerrado** y verificado local | `/panel` (tab SecretarÃ­a) con formularios de cobro/abono y gasto; carpeta forense; `POST /api/v1/panel/pagos` probado; tests `test_m3_secretaria.py` | ValidaciÃ³n con la secretaria real (afinamiento, no bloqueante) |
| 4b | Custodio v4.4 + Panel de Pagos/Gastos/Tasas/Conteo | ðŸŸ¢ **Cerrado** (2026-11-09) | `evidencias/pytest_panel_v44_2026-11-09.txt` (**247 tests**); `evidencias/http_gate_v44_check_2026-11-09.txt` (`HTTP GATE V4.4: OK`, 12 pasos, `ROLLBACK` 17 tablas); `/panel` con `dlg-pago`, `dlg-gasto`, `conteo-materiales`, `fin-wacc`; `GET /api/v1/panel/catalog` â†’ 26 cuentas | Nada bloqueante. Cargar tasas, ejecutar conteo real e instalar cron quedan como operaciÃ³n del cliente/VPS |
| 5b | VPS + GitHub + Evolution API | OK **Primera subida** (2026-11-12) | Repo `ObjetivoCesar/horminor-crm` (commit `a94a618`), deploy key read-only, VPS `/opt/horminor`, `core-api` en `127.0.0.1:8012`, Caddy `horminor.178.238.238.158.sslip.io` (solo `/health` y webhook), 21 migraciones, instancia Evolution `horminor` creada y webhook configurado; `docs/DESPLIEGUE_VPS_HORMINOR.md` | Escanear QR, probar texto con teléfono real, rotar API key y cargar backups |
| 4n | v6.13.1 - Memoria de Gato + descarga de factura | OK **Cerrado** (2026-11-12) | Migración 074 (`gato_turnos`); `conversacion_id` en el endpoint y en el widget; historial de 8 turnos al LLM; búsqueda de clientes sin puntuación ("ing reyes" → "Ing. Reyes"); enlace `?download=1` en la factura; pytest (**342 tests**) | Validar el hilo con el uso real de Julio/Secretaría |
| 4o | v6.17 - Gato secretaria: ratificación, adjuntos y redacción | 🟢 **Desplegado y probado en VPS** (2026-11-13) | Migraciones 075–078; envío real de `PRUEBA-0002.pdf` y de un mensaje redactado al 0967491847; candado de cifras (`cifras_de`/`_cifras_permitidas`); 4 clientes ficticios con factura en el VPS; `pytest` **376**. Doc `docs/GATO_SECRETARIA.md` v1.3 | C8 número vivo, C9 UI en el panel, C11 acuse de entrega, C12 test de integración |
| 4p | v8.2 - Ubicación de la obra en la cotización + Sabueso | 🟢 **Cerrado** (2026-11-14) | Migración 084 (`ubicacion_*`, CHECKs, `UBICACION_SOLICITADA/RECIBIDA`); `/pedir-ubicacion`, pin por WhatsApp end-to-end, GPS del navegador, bloque en el PDF; `.card-buscar-clientes` desatasca el Sabueso; `pytest` **423** y Hito 3 en verde. Evidencia `.agents/evidencias/ubicacion_v82_2026-11-14.txt` | Probar en un teléfono real; el residuo de prueba ya se limpió |
| 4q | v8.3 - Cerebro y Voz: de audio a borrador | 🟡 **En curso** (2026-11-15) | Fases 0–2: servicios extraídos, migraciones **085/086**, ingesta, **Groq/Whisper** con palabras y tiempos, mapa de alineación, hechos citados, compilador con invariantes, sobre, extractor y endpoints `/voz` y `/cerebro`; laboratorio en **`/panel/cerebro`** con pestañas texto/audio; caso Joaquín (teléfono en grupos, hora ≠ fecha, identidad preguntada); caso Juan Carlos (tarea de WhatsApp en `gato_recordatorios`, abono suprimido sin comprobante); caso Díaz Sur (dos contactos `contacto.2.*`, resistencia ≠ precio, plazo/descuento/planta móvil, 16 hechos, pregunta a cuál ingeniero); normalizador une guiones y «27 mil»; **popout de tareas + campanita** en `/panel` con `GET /cerebro/tareas/pendientes`; `pytest` **534** y Hito 3 en verde; **correcciones humanas con bóveda** (migración **087**, `cerebro_correcciones` append-only y `v_cerebro_vocabulario`), lectura en voz alta («Lo que entendí») con botón **Corregir** que rehace el borrador como versión nueva (sin borrar la anterior), pista de vocabulario en el prompt, **guarda de dinero** (sin frase en pasado no se registra abono: se pregunta) e **informe semanal de errores** (`scripts/informe_cerebro_errores.py`). **Tareas internas con reloj** (migraciones **088/089**, `cerebro_tareas_internas` + eventos append-only, `v_cerebro_tareas_internas`): una instrucción sin teléfono («que revisen en secretaría…») nace **NOTIFICADA**, se **resuelve o justifica** con nota y se **registra con metadatos**; el panel la muestra con **aviso fijo arriba** (no depende de un popout que se pueda cerrar o minimizar, ni de `localStorage`), campanita y botones; **aviso, vista y acuse** separados, **prioridad y plazo**, **escalada** y **ficha determinística** de la tarea; `TENTATIVO` para dudas («300 y pico») que no se vuelven datos definitivos; **intención antes que teléfono** (delegar ≠ enviar); **retiro** de vocabulario aprendido equivocado; **revocación completa** del dictado y **negación de instrucción citada** (F y L: ni se ejecuta ni se delega); y mide minutos entre eventos. **Manual Vivo** (`docs/HORMINOR_MANUAL_FUNCIONAL.md`) con mapa funcional, índice por término técnico/visible/sinónimo, nombres visibles y skill `orminorth-manual-funcional`; los nombres técnicos no cambian, cambian las etiquetas. Evidencias `cerebro_joaquin_2026-11-15.txt`, `cerebro_juan_carlos_2026-11-15.txt`, `cerebro_diaz_sur_2026-11-15.txt`, `panel_cola_tareas_2026-11-15.jpeg`, `cerebro_guarda_dinero_2026-11-15.txt`, `cerebro_tareas_internas_2026-11-15.txt`, `cerebro_informe_errores_2026-11-15.md` y `cerebro_lab_correccion_2026-11-15.jpeg` | Ejecutar `crear_cliente`/`crear_cotizacion_borrador` al confirmar, persistir `contacto.*` en `client_facts`, fase WhatsApp conversacional (contrato en `docs/CONTRATO_WHATSAPP_CEREBRO.md`), bóveda de audios con consentimiento LOPDP y audio humano real |
| 4m | v6.13 - Facturas internas adjuntas al cliente | OK **Cerrado** (2026-11-12) | Migración 073 (`client_invoices`); factura ficticia `PRUEBA-0001` (orden #55, **$43.424,00**) con PDF; pestaña **Facturas** en el expediente; `GET/POST /api/v1/clients/{id}/facturas`; Gato `cliente_facturas` con marca **FICTICIA** y SRI fuera de alcance; `evidencias/facturas_v613_2026-11-12.txt` y `panel_v613_facturas_2026-11-12.jpeg`; pytest (**338 tests**) | Validar formato con Julio; definir numeración y datos fiscales reales |
| 4l | v6.12 - Logos de bancos con color de marca | OK **Cerrado** (2026-11-12) | Tres placas SVG 96x96: Pichincha amarillo `#FFD100`, Guayaquil rosado `#C7007E`, Internacional naranja `#F39200`; isotipos oficiales, símbolo Pichincha a 56/96; `.banco-logo` de 46 px sin caja blanca; evidencias/panel_v612_bancos_dark_2026-11-12.png, _light_ y logos_zoom; pytest (**296 tests**) | Nada bloqueante. Aceptado por Dirección; si pide el lockup completo, placas 92x40 |
| 4k | v6.11 - Banco activo + detalle de cuenta | OK **Cerrado** (2026-11-12) | Migracion 072 (`bank_accounts`, hijas `1102.01-03`, `saldo_informado`); tarjetas seleccionables en amarillo; detalle con saldo contable/informado, prestamos y movimientos; `PUT /api/v1/dashboard/bancos/{slug}`; evidencias/panel_v611_banca_2026-11-12.jpeg; pytest_v611_2026-11-12.txt (**296 tests**) | Cargar cuentas y saldos reales; asignar pagos a la cuenta hija del banco |
| 4j | v6.10 - Fondo de Planta + cabecera de Banca | OK **Cerrado** (2026-11-12) | Foto `planta-agenda.webp` como fondo de la agenda con overlay; cabecera de Banca con tarjetas Pichincha/Guayaquil/Internacional y logos; endpoint `GET /api/v1/dashboard/bancos`; tarea `.agents/tareas/2026-11-12_ABEL.md`; evidencias/panel_v610_*.jpeg; pytest_v610_2026-11-12.txt (**295 tests**) | Confirmar cuentas Guayaquil/Internacional y reemplazar foto con marca Vecteezy |
| 4r | v9.8 - Espejo de WhatsApp por lista blanca + **chat en vivo** | 🟢 **Funcionando en local y en el VPS con el número 0967491847** (2026-11-18) | Migraciones **093/094/095**; módulo `app/whatsapp_espejo/` (identidad PN/LID/ALT, **aprendizaje del teléfono desde el historial cuando falta `remoteJidAlt`**, backfill paginado idempotente **con corte desde el alta del cliente**, envío con `key.id`); webhook del M1 con hook propio; Chat con **Sincronizar**, altura fija de 520 px. **Multimedia entrante real** (imagen, audio, video). **Chat en vivo:** `BusEventos` + `GET /api/v1/whatsapp/espejo/eventos` (SSE) y `chatEventosConectar()` en el panel: el hilo abierto se refresca en **menos de un segundo**, el sondeo de 15 s queda de respaldo. **Sesión de WhatsApp revincada con QR** (el `SessionError` de Evolution impedía descifrar). Prueba real: mensaje enviado **desde el celular del cliente** aparece en el chat del CRM; entrantes y salientes correctos; `pytest` **674** | Confirmar en el VPS con un WhatsApp real desde el celular (el SSE ya responde y Caddy lo entrega sin buffering); conectar Bunny para la media entrante (W3); evaluar actualizar Evolution v2.3.7 por el fallo LID; commit del código |
| 4i | v6.9 - Chat espejo WhatsApp + multimedia Bunny | OK **Cerrado** (2026-11-11) | Chat con estetica WhatsApp (clip, camara, audio, ubicacion), canal `WHATSAPP` y estado de conexion; migracion 071 (`media_assets`, `clients.cedula`); compresion WebP/video; tokens Bunny; limites y rate limit; `docs/WHATSAPP_Y_MEDIA.md`; evidencias/media_v69_check_2026-11-11.txt (**MEDIA V6.9: OK**) y pytest_v69_2026-11-11.txt (**291 tests**) | Conectar Evolution y persistir entrantes; cargar cedula y credenciales Bunny |
| 4h | v6.8 - CHAT por cliente en PostgreSQL | OK **Cerrado** (2026-11-11) | Migracion 070 (`chat_conversaciones`, `chat_mensajes`, `v_chat_conversacion`); API `routers/chat_clientes.py`; pestana `💬 Chat` con badge, burbujas y compositor; idempotencia `whatsapp_msg_id`; busqueda full-text; docs/BASE_DE_DATOS.md §9; evidencias/chat_v68_check_2026-11-11.txt (**CHAT V6.8: OK**) y pytest_v68_2026-11-11.txt (**283 tests**) | Conectar envio real por WhatsApp (Evolution) |
| 4g | v6.7 - Filtros plegables + fotos reales | OK **Cerrado** (2026-11-11) | Boton `Filtros` con contador y panel desplegable; chips de filtros activos; fix global de `[hidden]`; fotos en `static/brand/fotos/` para Obras; evidencias/pytest_v67_2026-11-11.txt (**277 tests**) | Confirmar foto del mixer (recortada u original) |
| 4f | v6.6 - Carpetas de Clientes + Sabueso | OK **Cerrado** (2026-11-09) | Banner de 4 filtros; buscador multi-variable y fonetico; filtros/paginacion; expediente en 3 pestanas; migracion 069; docs/tutoriales/ (7 archivos); evidencias/pytest_v66_2026-11-09.txt (**277 tests**) | Validar con Julio la busqueda real |
| 4e | v6.4 - UX Superadmin por Action Cards | OK **Cerrado** (2026-11-09) | Banner CENTRO DE CONTROL con 4 action cards; 2 tarjetas resumen (perfiles y WhatsApp/reglas); modales de usuarios/caja/recetas/tasas; cero JSON crudo; selector Viendo como con acceso directo; evidencias/pytest_v64_2026-11-09.txt (**272 tests**) | Validar con Julio los textos y perfiles |
| 4d | v6.2 - Agenda unica, config operativa y ACL | OK **Cerrado** (2026-11-09) | 068 aplicada; HorminorAgenda en Dashboard/Secretaria/Planta; /superadmin/operacion/config; panel_users_acl con 5 perfiles; evidencias/pytest_v62_2026-11-09.txt (**270 tests**) | Validar perfiles reales con Julio |
| 4c | v6.0 - Compras, caja chica y agenda | OK **Cerrado** (2026-11-09) | 067 aplicada; panel con compras/cierre/agenda; recepcion en Planta; `evidencias/pytest_v6_2026-11-09.txt` (**265 tests**); `evidencias/clone_v6_2026-11-09.txt` | Confirmar tope y proveedores reales |
| 5 | M4 â€” Dashboard de Julio + Ases | ðŸŸ¢ Construido y verificado local | *Dashboard Julio* con 3 tarjetas iguales: mercado El Coca **0.31% (372/120,000 mÂ³)**, ventas **404 mÂ³ / $55,043.60 / 51 viajes** (la captura aprobada 2026-11-08 mostraba $47,864 sin IVA), y provincias **Orellana 372 + SucumbÃ­os 16 + sin provincia 16**; Banca **215,000 / 404 / 0.19% / 214,596 mÂ³**; 2 escenarios; tests `test_m4_dashboard.py` | Validar con Julio el Ã¡ngulo de mercado; auth para exponer |
| â€” | Despliegue en VPS | âšª No iniciado | â€” | VPS, dominio, TLS, proxy, backups |

Leyenda: âšª no iniciado Â· ðŸŸ¡ en curso / candado abierto Â· ðŸŸ¢ cerrado y congelado

## DÃ³nde estÃ¡ corriendo

| Componente | Local | VPS |
|---|---|---|
| PostgreSQL 15 | localhost:5433 (contenedor orminorth-postgres) | contenedor orminorth-postgres (sin puerto público) |
| Redis 7 | localhost:6380 (contenedor orminorth-redis) | contenedor orminorth-redis (sin puerto público) |
| Core API | http://localhost:8000 (contenedor orminorth-core-api) | 127.0.0.1:8012 en el VPS; público solo /health y webhook |
| Panel (M3 + M4 + Superadmin) | http://localhost:8000/panel · **SANDBOX: no envía WhatsApp** | http://localhost:8012/panel por túnel SSH (`ssh -i ..\vps-entrada\horminor_vps -N -L 8012:127.0.0.1:8012 root@178.238.238.158`); `envio: evolution`, sí envía |

> **Espejo v9.7 en local (2026-11-17):** cliente `PRUEBA - Alejandra WhatsApp`
> (`a6dfca33…`) con el número autorizado `593986962872` y **5 mensajes
> sincronizados**. Matiz importante: local muestra "WhatsApp: no conectado"
> porque el **bot del M1** sigue en SANDBOX; el **espejo** del número autorizado
> sí envía de verdad con su propio cliente Evolution. Son dos canales distintos.

Datos de demo en local: Ã³rdenes del Ing. Reyes (320 mÂ³ FC-210 y 52 mÂ³ FC-350),
orden del candado del Hito 3 (16 mÂ³) y clientes de fixture con provincia
Orellana/SucumbÃ­os para verificar la cuota de mercado. Se regeneran con los
scripts de candado.

## Evidencia de la última sesión

### 2026-11-18 - Chat en vivo: el espejo avisa al panel en segundos

- **Qué cambió:** el Chat del expediente ya no espera el sondeo de 15 s. El
  espejo publica un aviso (`BusEventos`) cuando importa un mensaje, cuando el
  webhook adelanta su estado y cuando termina una sincronización; el panel lo
  recibe por **SSE** (`GET /api/v1/whatsapp/espejo/eventos`) y refresca el hilo
  abierto en menos de un segundo.
- **Permisos:** `EventSource` no manda cabeceras, así que el perfil simulado va
  por `?usuario=`; el módulo se valida igual y el aviso solo lleva
  identificadores, nunca el texto.
- **Respaldo:** el sondeo de 15 s sigue activo por si la conexión en vivo se
  cae.
- **Bug corregido en la prueba:** `enviado_at` viajaba como `datetime` y
  `json.dumps` cerraba el stream; ahora va en ISO-8601 y `_sse` usa
  `default=str`.
- **Verificado:** `curl` recibe `listo` y luego el `mensaje` del webhook real
  con el número autorizado; en el navegador el hilo pasa de 14 a 15 mensajes
  **sin pulsar Sincronizar** y el texto aparece en **462 ms**; panel sin errores
  de sintaxis (`bloques=3 errores=0`); `674 passed`. Evidencia:
  `.agents/evidencias/sse_chat_vivo_2026-11-18.txt`.
- **VPS (2026-11-18):** desplegado con parche quirúrgico sobre el linaje que
  corre allí (`0cfa9fc`): `BusEventos` en `main.py`, `usuario` opcional en
  `panel_acl.py`, el bloque SSE + sondeo en su `panel.html` y los cuatro
  archivos del espejo desde local. El endpoint responde `listo` y un webhook
  real llega al SSE; Caddy entrega el primer bloque en **38 ms** (sin
  buffering); respaldo de los archivos originales en
  `/root/backup_sse_chat_20261117_214843`. Evidencia:
  `.agents/evidencias/sse_chat_vivo_vps_2026-11-18.txt`.
- **Pendiente:** confirmar en el VPS con un WhatsApp real desde el celular;
  Bunny (W3).

### 2026-11-18 - Multimedia entrante: imagen, audio y video

- **La estructura de WhatsApp se aprovecha completa:** el mensaje ya dice el
  tipo (`imageMessage`, `audioMessage`, `videoMessage`, `documentMessage`) y
  Evolution entrega el binario con `getBase64FromMediaMessage`.
- **Se guarda por cliente** en `clientes/<cliente>_<id>/…` dentro de
  `media_dir`, con fila en `media_assets` y `media_id` en el mensaje.
- **Verificado con envío real** desde el celular: imagen (69 KB), audio (4 KB)
  y video (6 MB) descargados y visibles en el chat del expediente.
- **Un fallo de media no pierde el texto** del mensaje.
- **Pendiente:** enviar multimedia desde el CRM (`sendMedia` de Evolution) y
  conectar Bunny al mismo esquema de carpetas.

### 2026-11-18 - Por qué no llegaba al CRM (y número nuevo de prueba)

- **Causa real:** la sesión de WhatsApp estaba **sin poder descifrar** mensajes
  (`SessionError: No matching sessions found` en chats `@lid`, `stream:error
  503`). Los mensajes no entraban ni a Evolution. Se reparó **revincando el
  dispositivo con QR** (sin tocar el contenedor compartido). Después:
  `state: open` y **0 errores**.
- **Segundo defecto:** WhatsApp omite `remoteJidAlt` en muchos `@lid`; el
  espejo ahora **aprende el teléfono del historial de Evolution** y lo registra
  como alias. Sin dato, el mensaje sigue pendiente (no se inventa identidad).
- **Regla de historial (migración 095):** la sincronización solo copia desde el
  **alta del cliente** (`whatsapp_espejo_numeros.desde`, configurable). Se
  limpió el exceso: Abelito pasó de **1.807 a 1** mensaje.
- **Número de prueba:** **0967491847** autorizado en local y VPS; Alejandra
  desactivada (tenía otra automatización).
- **Interfaz:** el chat de la carpeta tiene **altura fija de 520 px** y solo
  desplaza la lista de mensajes.
- **Prueba real:** un mensaje enviado **desde el celular del cliente** al
  0967491847 aparece en el chat del CRM como saliente, junto con los entrantes.
- **Pruebas:** `660 passed`.
- **Pendiente:** descargar multimedia y subirla a Bunny por cliente (W1–W3).

### 2026-11-17 - Espejo v9.7 desplegado en el VPS (conversación real)

- **Qué se logró:** la pestaña **Chat** del expediente **Alejandra** muestra la
  conversación real de WhatsApp del número autorizado `+593 98 696 2872`
  directamente en el VPS. Historial de 3 mensajes importado una sola vez, en
  orden y con estados reales.
- **Envío real desde el CRM:** el texto sale por Evolution con el cliente propio
  del espejo, sin apagar el switch SANDBOX global ni activar el bot informativo.
  Llegó al teléfono.
- **Webhook en vivo:** `MESSAGES_UPDATE` suscrito; entraron en tiempo real el
  texto "probando" y una imagen, guardados sin duplicar.
- **Correcciones mínimas:** `API_PORT` 8010→8012 (Caddy), `extra_hosts`
  `host.docker.internal:host-gateway`, y normalización del estado de envío
  (`PENDING`→`PENDIENTE`) que causaba un 500 después de enviar.
- **Bloqueo:** el **entrante** desde el teléfono de Alejandra nunca llegó a
  Evolution (ni por PN ni por su LID `153459886145727@lid`). No es un descarte
  del espejo.
- **Pruebas:** `655 passed`; archivo del espejo `32 passed`.
- **Evidencia:** `.agents/evidencias/espejo_v97_vps_2026-11-17.txt`.
- **Alcance añadido por Julio:** recibir **audio, imagen, video y documento**, y
  acumular la media de cada cliente en su **carpeta independiente en Bunny.net**
  (`.agents/tareas/PENDIENTES.md` §6, W1–W6). Aún no implementado.
- **Intacto:** bot informativo, Cerebro, Gato, voz y demás números.

### 2026-11-16 - Corrección de revocación y audio de Díaz Sur

- **Defecto:** `dictado_revocado` comparaba «mejor no» como subcadena y lo
  encontraba dentro de «mejor nos abastecemos». El audio real terminaba en
  `SIN_ACCIONES`.
- **Corrección:** las marcas se leen como palabras completas y la revocación se
  aplica al encargo donde aparece; solo «no hagas nada» corta el dictado
  completo. Sin cambios en dinero, permisos ni confirmación.
- **Pruebas:** 25/25 en `test_v92_adversarial.py` (3 nuevas) y **623/623** en la
  suite del CRM.
- **Audio de 122 s:** transcripción `37deb787-d140-44fb-80e4-078057dc34ca`.
  Antes `SIN_ACCIONES`; ahora `REQUIERE_ACLARACION` con **2 encargos**,
  **1 acción** (`crear_cliente`) y 4 preguntas. Borrador
  `e133755d-db43-4257-9a50-c9dd8b1e325d`.
- **Límite real:** no produce todavía la cotización completa porque falta la
  dirección de la obra y el precio; no se registró dinero ni se envió nada.
- **Documentos:** `docs/CORRECCION_REVOCACION_DIAZ_SUR.md`, Manual Vivo v1.7 y
  Continuidad v1.5.
- **Intacto:** router `router-1.7` congelado, Gato desconectado, sin interfaces
  nuevas.

### 2026-11-16 - Cierre de la fase del router conversacional (laboratorio)

- **Decisión:** la fase se cierra con `router-1.7`; no se amplía la arquitectura
  ni se buscan más soluciones. Los errores se corrigen con la caja de respuesta
  y la traza existentes.
- **Qué es:** prototipo aislado en `experiments/router_horminor/` (puerto 8055).
  Interpreta un dictado, separa encargos, propone responsable, pide aclaraciones,
  recibe correcciones y entrega un plan. **No está conectado al CRM.**
- **Pruebas:** 21/21 del router (`tests_core`) y 620/620 del CRM
  (`pytest /app/tests`). Sin regresiones.
- **Documentos:** `docs/ROUTER_CONVERSACIONAL_CIERRE.md` (componentes, flujo,
  límites), Manual Vivo §3.5 y §4, `docs/CONTINUIDAD_CEREBRO.md` v1.4 y
  `docs/AUDITORIA_PRUEBAS_MANUALES_2026-11-16.md`.
- **Backlog:** evaluar Jev (TypeSafe AI) como clasificador o verificador de
  intenciones. Sin fecha, sin integración y sin cambios de código.
- **Siguiente paso:** autorizar el arreglo de `dictado_revocado` en
  `app/cerebro/compilador.py` (detecta «mejor no» dentro de «mejor nos
  abastecemos») y volver a pasar el audio real de 122 s por el panel.

### 2026-11-16 - Lenguaje natural, duda acotada y audio (v8.6)

- **Caso real auditado (sin ordinales):** «que secretaría revise los despachos…
  hay que llamar al ingeniero Mauricio… y el colegio Central, creo que eran
  treinta metros de hormigón de 240, que me confirmen las medidas». Antes: un
  solo encargo con acciones mezcladas. Ahora: **tres encargos** separados.
- **Segmentación:** el extractor (prompt **cerebro-v7**) numera cada encargo por
  cambio de asunto, destinatario o acción; `asignar` valida y renumera; los
  ordinales quedan como respaldo. Si no separó y hay dos `tarea.mensaje`, el
  compilador pregunta (`encargo.division`) en vez de agrupar.
- **Duda acotada:** `_ajustar_incertidumbre` ata la duda al dato más cercano.
  «Creo que eran 30 m³ de 240» → volumen `TENTATIVO` con pregunta; resistencia
  `EXTRAIDO` sin pregunta redundante. También cubre cliente y fecha.
- **Nombres visibles:** «Acciones ejecutadas» (borrador) frente a «Trabajo
  realizado» (tarea resuelta); la confirmación interna dice que la tarea quedó
  **NOTIFICADA** y que el trabajo no está hecho.
- **Audio:** WAV con voz sintética es-MX (Sabina) → STT real de Groq (18,3 s,
  transcripción correcta) → interpretación con 3 encargos y la duda en el
  volumen. **No es una grabación humana**; queda pendiente medir con voz real y
  ruido de planta.
- **Suite:** **620 passed** (10 nuevas en `test_v96_natural.py`); Hito 3 →
  `[CANDADO CERRADO EN SANDBOX]`.
- **Evidencia:** `.agents/evidencias/cerebro_audio_natural_2026-11-16.txt`
  (+ `.wav`, STT e interpretación en JSON).
- **Manual Vivo v1.5:** término *Duda asociada al dato*; *Encargo* actualizado.
- **WhatsApp interno:** `docs/WHATSAPP_INTERNO_IMPLEMENTACION.md` con la
  secuencia 0–7, dependencias verificadas y compuertas. No implementado.

### 2026-11-16 - Encargos independientes en un dictado (v8.5)

- **Caso real auditado.** Un dictado con tres asuntos (revisar medidas de una
  cotización, recordatorio al ingeniero Mauricio, revisar despachos). El motor
  anterior lo colapsaba en **una** acción, perdía el tercer encargo y convertía
  el recordatorio externo en tarea interna por la palabra «secretaría».
- **Migración 092:** `encargos_json` en el borrador, `encargo` en ejecuciones y
  correcciones, y `cerebro_encargos_decisiones` append-only para cancelaciones.
- **Segmentación determinística** (`app/cerebro/encargos.py`) por ordinales
  («primero, segundo, tercero, por último, finalmente»); el preámbulo no se
  compila. Sin marcas, un solo encargo y el comportamiento anterior.
- **Compilación por encargo:** cada asunto se compila con **su propio texto**;
  un tramo con rol interno y sin hechos se conserva como tarea interna copiando
  el tramo (sin redactar).
- **Operaciones:** corrección dirigida (clave repetida → `ENCARGO_AMBIGUO`),
  cancelación con motivo (`ENCARGO_CANCELADO` al confirmar), cancelación real de
  un recordatorio PENDIENTE y aviso si ya se envió.
- **Cifras:** las cifras dictadas del encargo se pasan como `cifras_autorizadas`
  a la guarda del mensaje: un anticipo citado ya no se pierde, y un número que
  nadie dijo sigue bloqueado.
- **Prueba en vivo:** A corregido a 35 m³ (v2, sin ejecutar), B cancelado (sin
  recordatorio), C confirmado una sola vez (tarea interna); repetir no duplica.
- **Suite:** **610 passed** (9 nuevas en `test_v95_encargos.py`); Hito 3 →
  `[CANDADO CERRADO EN SANDBOX]`.
- **Evidencia:** `.agents/evidencias/cerebro_encargos_2026-11-16.txt`
  (`ENCARGOS: OK — tres asuntos independientes, sin mezcla`).
- **Manual Vivo v1.4:** términos *Encargo* y *Cancelación de un encargo*.

### 2026-11-16 - Conservación de instrucciones (v8.4)

- **Caso real auditado.** Audio espontáneo en `/panel/cerebro`: anticipo de USD
  17.000, 250 m³ FC-240, ingeniero Julio Cartuche, rectificación «la cotización,
  no la cotización, el recordatorio del pago», entrega contra pago, plazo de dos
  meses y encargo al expediente. El borrador guardado perdió el plazo, la
  condición de pago y el expediente: la suite verde no lo detectaba.
- **Migración 091:** `cerebro_borradores.condiciones_json` (append-only,
  protegida por el trigger ampliado). No se editó ninguna migración aplicada.
- **Compilador:** `Condicion` con cita; detección determinística de
  `entrega.plazo`, `entrega.contra_pago` y `expediente.completar`; el encargo al
  expediente crea tarea interna para secretaría. El plazo ya no depende de que
  la cotización se pueda armar.
- **Recordatorio:** se separan `instruccion` (lo dictado) y `mensaje` (lo que se
  envía). Si la frase describe el encargo, `mensaje_por_confirmar` exige el
  texto al confirmar; si no hay hora, `programado_inferido` exige aceptar el
  envío inmediato. Guardas 422 `MENSAJE_POR_CONFIRMAR` y
  `CONFIRMAR_ENVIO_INMEDIATO`.
- **Dinero:** «el pago que tiene que hacernos» ya no se registra como «no
  recibido»: queda `INFERIDO` y el resumen dice «sin ingreso confirmado».
- **Secuencia verificada (G):** el recordatorio se creó en la misma petición de
  confirmación (00:21:46), 19 s después del borrador (00:21:27); no se programó
  antes de aprobar. La confusión era de etiqueta: el borrador seguía en
  `REQUIERE_ACLARACION` y ahora la respuesta lo dice (`confirmado_parcial`).
- **Hallazgo extra:** al recompilar, un texto podía rechazarse por compararse
  contra el texto normalizado («2 meses») en vez de la cita cruda («dos
  meses»). Corregido en `validar_hecho`.
- **Suite:** **601 passed** (15 nuevas en `test_v94_conservacion.py`); Hito 3 →
  `[CANDADO CERRADO EN SANDBOX]`.
- **Evidencia:** `.agents/evidencias/cerebro_conservacion_2026-11-16.txt`
  (matriz 10/10: `CONSERVACION: OK`).
- **Manual Vivo v1.3:** términos *Condición conservada*, *Mensaje autorizado del
  recordatorio* e *Ingreso sin confirmar*.

### 2026-11-16 - Verificación de prioridad 1 (sin tocar código)

- **Contenedores:** `core-api` healthy, `core-api-clone`, `postgres` y `redis`
  arriba. `/health` → `ok`, base en 1,38 ms.
- **Migraciones:** «Sin migraciones pendientes»; **085–090** aplicadas (090 el
  15/11 a las 23:00). La base tiene **37 migraciones, 57 tablas y 11 vistas**,
  igual que esta ficha.
- **Suite:** **586 passed**, 1 warning, **exit 0**.
- **Candados:** Hito 3 → `[CANDADO CERRADO EN SANDBOX]`; Hito 1 →
  `[CANDADO CERRADO]`.
- **Código corriendo = código en disco:** SHA-256 idéntico en `main.py`,
  `compilador.py`, `revision.py`, `panel.html` y `pipeline.py`. `app/` no está
  montado: se copia en el build, así que la imagen vigente salió de este árbol.
- **Panel:** `/panel` 200 y `/panel/cerebro` 200.
- **Centinela:** `WARN`, `SANDBOX`, `DETERMINISTIC_FALLBACK`; 12 chequeos
  (**9 OK / 2 WARN / 1 NO_CONFIGURADO**). WARN: caja del 15/11 sin cierre y un
  `ERROR` en 24 h; NO_CONFIGURADO: umbral de merma de cemento.
- **Hallazgo:** `scripts/hito3_lock_test.py` limpia **al inicio**, no al final:
  deja órdenes demo y un `ERROR` (`M1_WHATSAPP`, reclamo del «Cliente Prueba
  Hito 3») que hace que el Centinela reporte WARN hasta la corrida siguiente. No
  se corrigió: cambiar un candado cerrado exige aprobación y volver a correr la
  suite.
- **Punto de restauración:** se versionó el trabajo acumulado desde el commit
  `7fade4a` (2026-11-13), que no incluía v8.2 ni el Cerebro (084–090), en dos
  commits: **`5c4b460`** (v8.2, migración 084 y servicios compartidos) y
  **`67e18ff`** (v8.3, Cerebro y Voz con 085–090, docs y `.agents`).
- Evidencia: `.agents/evidencias/verificacion_prioridad1_2026-11-16.txt`.

### 2026-11-15 - Caso Joaquín: teléfono, hora y conflicto de identidad

- El tip de Julio quedó implementado: un `09…` de 10 dígitos dictado en grupos
  (`0965 555 555`) se une a `0965555555`. Si el LLM no lo captura, el backend
  lo propone como `INFERIDO` y el compilador pregunta «¿El teléfono del cliente
  es…?». Un hecho inferido nunca resuelve identidad por sí solo.
- «A las 6 de la mañana» ya no produce `fecha_entrega = hoy`: se guarda
  `cotizacion.hora_entrega = 06:00` y la fecha tentativa queda nula. El
  compilador revisa otra vez que la cita sostenga una fecha.
- El caso real reveló que el teléfono ya estaba registrado a nombre de otro
  cliente de prueba (`Palo Velez`): ahora se pregunta «¿Es el mismo cliente?»
  en vez de registrar el abono en la ficha equivocada.
- `pytest` → **497 passed**; Hito 3 → `[CANDADO CERRADO EN SANDBOX]`.
- Evidencia: `.agents/evidencias/cerebro_joaquin_2026-11-15.txt`.

### 2026-11-14 - Laboratorio del Cerebro en el panel (prueba manual)

- `GET /panel/cerebro` sirve una página de pruebas (texto o audio) y el sidebar
  gana **«Cerebro · voz BETA»**, visible solo con el módulo `cerebro`.
- Prueba desde la UI: 12 hechos con cita, 4 acciones, 1 con doble confirmación,
  3.2 s, cero errores de consola; `pytest` **482 passed**.
- Se dejaron `voz.enabled` y `cerebro.enabled` en `true` para la prueba local.
- Evidencia: `.agents/evidencias/lab_cerebro_2026-11-14.txt`.

### 2026-11-14 - Cerebro y Voz: de audio a borrador (Groq + DeepSeek)

- `app/voz/proveedores/groq.py`: Whisper con `verbose_json`, palabras y tiempos;
  confianza por segmento (`exp(avg_logprob)`) como proxy, no calibrada.
- `app/cerebro/sobre.py`, `extractor.py`, `router.py`: texto o transcripción →
  sobre validado → borrador persistido. Migración **086** agrega
  `texto_directo` para el texto pegado.
- Prueba en vivo: audio sintético de 11,8 s → transcripción (el STT confundió la
  cédula) → el LLM intentó completarla → el verificador **la descartó** con nota
  «el numero 1710034065 no coincide con el audio»; el borrador siguió sin
  cédula y con 3 acciones.
- Bug corregido en `httpx` 0.28: `data` como lista de tuplas producía un stream
  síncrono; se usa diccionario con lista en `timestamp_granularities[]`.
- `pytest` → **482 passed** (7 de Groq y 5 del extractor). Evidencia:
  `.agents/evidencias/fase2_audio_groq_2026-11-14.txt` y
  `caso_voz_draft_2026-11-14.json`.

### 2026-11-14 — Cerebro y Voz, Fase 2: hechos citados y compilador

- `app/cerebro/hechos.py`: `HechoCitado` con cita, texto que sostiene, span,
  ventana, hablante, confianza y `checksum_valido`; `validar_hecho` rechaza
  valores que no están en la cita.
- `app/cerebro/compilador.py`: hechos → borrador con invariantes. Caso A:
  4 acciones ordenadas (cliente → cotización → abono → envío); Caso B: abono +
  traslado con dependencia y doble confirmación; Caso C: `SIN_ACCIONES`.
- Reglas probadas: cédula inválida pregunta; precio `PROVISIONAL` bloquea envío
  fuera de SANDBOX; precio de otro rol se ignora; faltantes → máximo 3
  preguntas; saldo de caja insuficiente bloquea el traslado; rol sin caja no
  puede registrar dinero.
- `pytest` → **469 passed** (14 nuevos). Evidencia:
  `.agents/evidencias/fase2_hechos_compilador_2026-11-14.txt`.

### 2026-11-14 — Cerebro y Voz, Fase 2: mapa de alineación

- `normalizar_con_mapa` devuelve cada token con su span en el texto crudo y su
  tipo (`NUMERO`, `UNIDAD`, `MONEDA`, `ALIAS`…).
- `localizar_palabras`, `alinear_con_palabras` y `alinear_secuencias` atan los
  datos a las palabras del STT, su ventana de milisegundos y su confianza.
- Una cédula dictada en dos tramos queda como un solo dato; los conectores
  («que más») no bajan la confianza. Sin palabras del STT, el dato queda sin
  ventana y no se puede confirmar con un clic.
- `normalizar_texto` mantiene su contrato y ahora une los tramos en el texto.
- `pytest` → **455 passed** (10 nuevos); `/health` → 200.
- Evidencia: `.agents/evidencias/fase2_alineacion_2026-11-14.txt`.

### 2026-11-14 — Cerebro y Voz, Fase 1: migración 085 e ingesta de audio

- Migración **085** aplicada: `voz_ingestas`, `voz_ingesta_media_links`,
  `voz_trabajos_stt`, `voz_transcripciones`, `cerebro_extracciones`,
  `cerebro_borradores`, `cerebro_ejecuciones`, `client_facts`,
  `client_fact_supersedes` y `whatsapp_mineria_cursores`; settings
  (`voz.enabled=false`, topes en `null`), módulos ACL `voz`/`cerebro` y
  `fecha/hora_entrega_tentativa` en cotizaciones.
- `app/voz/ingesta.py`: valida MIME/tamaño, hashea, guarda en
  `inbox_voz/<fecha>/`, crea ingesta y trabajo, y **reutiliza** la ingesta si
  el mismo audio se reenvía (nuevo intento, sin duplicar el binario).
- `app/voz/stt.py`: protocolo `ProveedorSTT` con degradación
  `DEGRADADO_SIN_CREDENCIAL`; nunca inventa texto.
- `POST /api/v1/voz/transcribir` y `GET /api/v1/voz/ingestas/{id}` con ACL
  `voz` y feature flag apagado por defecto; `voz`/`cerebro` aparecen en el
  checklist de Superadmin.
- Verificado en vivo: 201 con `DEGRADADO_SIN_CREDENCIAL`, un solo archivo,
  tres intentos auditados; el trigger append-only rechaza el `UPDATE`.
- `pytest` → **445 passed**; Hito 3 → `[CANDADO CERRADO EN SANDBOX]`.
- Evidencia: `.agents/evidencias/fase1_voz_2026-11-14.txt`.

### 2026-11-14 — Cerebro y Voz: diseño canónico, Fase 0 y normalizador es-EC

- `docs/CEREBRO_VOZ_DISENO.md` v1.0: separa `app/voz/` de `app/cerebro/`,
  define 9 tablas, 9 acciones y 4 fases; corrige 16 puntos del diseño externo
  (tipos UUID, inmutabilidad, reintentos, roles reales, `obra_direccion`,
  `resistencia` como código, cuotas no inventadas).
- Decisiones resueltas: fecha tentativa en `cotizaciones` (`date` + `time`),
  precio desde la receta sin autoenvío, minería bloqueada hasta persistir
  entrantes de WhatsApp.
- **Fase 0 cerrada:** `services/cotizaciones.py` y `services/clients.py`
  concentran el alta; el panel y el Cerebro usan el mismo camino. Verificado en
  vivo: alta de cliente con cédula, cotización 6 m³ ($814,20) y PUT a 7 m³
  ($949,90); datos de prueba borrados.
- `app/voz/normalizador_ec.py`: números hablados, cédulas en tramos con
  conector, teléfonos, `m3`, moneda y ciudades. **No corrige dígitos**: marca
  `checksum_valido=false` y el borrador pide corroboración.
- `pytest` → **439 passed** (16 nuevos). Evidencia:
  `.agents/evidencias/voz_normalizador_2026-11-14.txt` y
  `fase0_servicios_2026-11-14.txt`.
- Plan de ejecución: `.agents/tareas/2026-11-14_CEREBRO_VOZ.md`.

### 2026-11-14 — Cotizaciones v8.2: ubicación de la obra y Sabueso sobre las tarjetas

- **Migración 084** aplicada: `ubicacion_texto`, `ubicacion_lat/lng`,
  `ubicacion_origen`, `ubicacion_solicitada_at`, `ubicacion_recibida_at`;
  CHECKs de origen y rango; `cotizacion_eventos` acepta
  `UBICACION_SOLICITADA` y `UBICACION_RECIBIDA`; plantilla
  `cotizaciones.pedir_ubicacion` en `system_settings`.
- **Tres vías**: texto libre (`MANUAL`), **Usar mi ubicación** (`GPS`) y pin del
  cliente por WhatsApp (`WHATSAPP`); enlace de mapa pegado (`MAPA`). Sin dato
  queda `NULL` y el PDF imprime `Pin: PENDIENTE`.
- `POST /api/v1/cotizaciones/{id}/pedir-ubicacion` envía la plantilla al
  teléfono del cliente, sella el pedido y deja `UBICACION_SOLICITADA`; la
  compuerta `_gate_ubicacion` de M1 adjunta el pin a la cotización abierta más
  reciente sin pin, sella `ubicacion_recibida_at` y responde al cliente.
- Un `PUT` parcial no borra el pin (`model_fields_set` + `CASE WHEN`); la
  referencia escrita por el asesor **no** se pisa con el nombre del pin.
- **PDF** con bloque **UBICACION DE LA OBRA** (Dirección, Referencia, Pin con
  origen, Mapa) y recorte a 92 caracteres por línea.
- **Sabueso**: `.card` crea contexto de apilamiento por `backdrop-filter`; la
  tarjeta del buscador lleva `.card-buscar-clientes` (`z-index: 6`) y el
  desplegable se dibuja por encima de la tarjeta siguiente. Ficha con nombre,
  constructora, ciudad, teléfono y RUC; navegación con Enter y flechas.
- `pytest` → **423 passed** (18 del archivo `test_v82_ubicacion.py`); Hito 3 →
  `[CANDADO CERRADO EN SANDBOX]`.
- Evidencia: `.agents/evidencias/ubicacion_v82_2026-11-14.txt`,
  `cotizacion_v82_pdf_2026-11-14.png`, `sabueso_zindex_v82_2026-11-14.png`.
- Manual actualizado: `docs/COTIZACIONES.md` v8.2 (§3.1, §3.7, §8, §12.3).

### 2026-11-13 — Dashboard C0–C3: capacidad declarada, MRP y cobranza única

- `GET /api/v1/dashboard/operacion`: capacidad `min(flota, planta, jornada)`;
  con la semilla actual devuelve `CONFIGURACION_INCONSISTENTE`; cola **404 m³
  sin plan** y **388 m³ sin despachar**.
- `/inventario`: explosión MRP + triple lectura. Cemento 3.500 declarado /
  **288 kardex** / cobertura 8,97 %; arena 243,56 corregida; retardante 73,6 L.
- `/cobranza`: documento único, factura ficticia excluida, total **55.043,60**;
  exigibilidad 1.085,60 confirmado / 2.171,20 con salida / 52.872,40 sin salir.
- Superadmin: `viajes_max_dia`, `planta_asignada`, `capacidad_plantas`,
  `supuestos_capacidad` y `umbrales_ocupacion` persistidos sin migración.
- `pytest` → **393 passed**. Evidencia:
  `.agents/evidencias/dashboard_c0_c3_2026-11-13.txt`.

### 2026-11-13 — Cotizaciones v6.21

- Migración **080** aplicada: `cotizaciones`, `cotizacion_extras`,
  `cotizacion_versiones`, `orden_extras`, `cliente_etiquetas`,
  `concrete_recipes.precio_estado` y settings.
- API: alta, edición (solo `BORRADOR`), detalle, listado, aceptación (etiqueta
  `VENTA`) y conversión a orden con `crear_orden`.
- Vista **Cotizaciones** en la columna izquierda: bandeja, detalle, formulario y
  extras globales.
- Permiso `cotizaciones` en el checklist de Superadmin. Julio lo tiene; los
  demás perfiles lo reciben cuando Julio lo apruebe.
- **Buscador** `GET /api/v1/cotizaciones?q=`: nombre, apellido, fecha, teléfono,
  número de cotización, obra, cédula/RUC o razón social.
- **Respuesta del cliente (migración 081):** compuerta determinística en M1.
  Confirmación explícita → `ACEPTADA` + etiqueta `VENTA` + evento + aviso, sin
  crear orden. Negociación/rechazo/pregunta → evento + aviso, sin cambiar el
  precio. Varias abiertas → pregunta cuál.
- **Alta de cliente y teléfono** desde la cotización (`+ Nuevo cliente`); el
  teléfono es obligatorio para enviar el PDF y actualiza la ficha.
- **Forma de pago fuera de la cotización** (migración 082): se define al
  convertir.
- **Enviar por WhatsApp:** PDF generado, archivado en `media_assets` y enviado
  por Evolution o encolado en SANDBOX. La cotización pasa a `ENVIADA`.
- **Convertir a cliente:** popout con forma de pago, abono y datos de factura;
  crea la orden y guarda `factura_datos` (migración 083).
- `pytest` → **405 passed**. Evidencia:
  `.agents/evidencias/cotizaciones_v621_2026-11-13.txt` y
  `.agents/evidencias/cotizaciones_v622_2026-11-13.txt`.
- Manual actualizado: `docs/MANUAL_DASHBOARD_JULIO.md` §9.

### 2026-11-13 — Meta comercial y punto de equilibrio

- Meta mensual configurable (`comercial.meta_mensual_m3`): cumplimiento,
  diferencia en m³ y días de planta cuando hay capacidad.
- Punto de equilibrio contable (`finanzas.punto_equilibrio`): costos fijos,
  costo variable y precio; `NO_CONFIGURADO` con faltantes si no están.
- Tarjeta “Meta y equilibrio” en Operación y 4 campos en Superadmin > Tasas.
- `pytest` → **394 passed**. Evidencia:
  `.agents/evidencias/dashboard_meta_equilibrio_2026-11-13.txt`.
- Manual actualizado: `docs/MANUAL_DASHBOARD_JULIO.md` §3.1.1.

### 2026-11-13 — Dashboard C5/C6: banner amarillo, 4 ventanas y gráficos SVG

- Banner `sec-ventanilla` primero; ventana activa en amarillo sólido con texto
  oscuro; 4 ventanas (Operación, Inventario vs ventas, Inventario por fechas,
  Cobranza).
- 3 KPI mutables por ventana, 6 gráficos SVG nativos (capacidad, despacho,
  resistencia, cobertura, kardex, aging) y bandeja de documentos.
- Presets de cobranza operativos: Todos, Urgencia 7 días, Mora, Clientes
  grandes, Sin vencimiento, Cupo excedido, Listo para cobrar.
- Agenda encapsulada en `data-sub-view="agenda"`; deja de ser un nodo huérfano.
- `pytest` → **394 passed**; navegador sin errores de consola, overflow 0.
- Evidencia: `.agents/evidencias/dashboard_c5_c6_2026-11-13.txt`.
- Manual en borrador: `docs/MANUAL_DASHBOARD_JULIO.md`.

### 2026-11-13 — Dashboard operativo en tres pestañas

- Se eliminó “Filtros de obras” (planta, resistencia, pago) del panel.
- Tres pestañas con submenú: **Ocupación** (por defecto, ámbar), **Inventario**,
  **Cobranza**; el resumen anual queda comprimido arriba.
- Endpoints nuevos `GET /api/v1/dashboard/inventario` y `/cobranza` con
  `fuente`, `consultado`, `filtros`, `datos` y `vacio`.
- Inventario: CEMENTO, ARENA, RIPIO, RETARDANTE (sin agua), con
  `SIN_FECHA_CONTEO` cuando no hay conteo físico.
- Cobranza: cuatro cubos y saldo real por cobrar separado del total documental.
- `pytest` → **386 passed** (7 tests nuevos).
- Verificado en Chromium: 3 pestañas, 4 tarjetas, 4 cubos, sin errores de consola.
- Evidencia: `.agents/evidencias/dashboard_operativo_2026-11-13.txt`.

### 2026-11-13 — Cotizaciones, contratos y mapa de módulos

- Migración **079** aplicada en local: `fecha_vencimiento` en `orders` y
  `client_invoices` + vista `v_cobranza_documentos`. Commit `c9e3446`.
- `pytest` → **379 passed**.
- Auditoría de skills → **APROBADO (179 verificaciones)** con `python
  scripts/auditar_skills.py`; incluye extra global válido y extra con
  `categoria` rechazado.
- `docs/COTIZACIONES.md` v6.20: rubro único global de extras, validez 15 días,
  envío por WhatsApp con PDF en la carpeta del cliente, etiqueta `VENTA`.
- `docs/CONTRATOS.md` v6.19: suministro por m³ con equipo y bombeo, medición
  pactada, firma exclusiva de Julio.
- `.agents/MAPA_MODULOS.md`, `.agents/tareas/PENDIENTES.md` y
  `docs/DASHBOARD_OPERATIVO.md` creados.
- `pdf-cotizaciones` → v1.3.0 (contrato `solicitud_cotizacion` 1.3.0).
- Evidencia: `.agents/evidencias/dashboard_cobranza_2026-11-13.txt`.

- **v6.17 desplegada y probada en el VPS (2026-11-13).** Seis commits
  (`7850241` … `8c6b301`), migraciones **075–078** aplicadas y `envio:
  evolution`. Envíos reales: `PRUEBA-0002.pdf` y un mensaje redactado, ambos al
  0967491847, con `documentMessage` en Evolution. Gato ahora **redacta** el
  mensaje y el backend rechaza cualquier cifra que no esté en la ficha
  (`cifras_de` / `_cifras_permitidas`). Cuatro clientes ficticios con factura en
  el VPS. Fallos corregidos en el camino: `import base64` ausente (ningún
  documento salía), `modo` decía SANDBOX por Bunny aunque el canal fuera
  Evolution, teléfono duplicado en la ratificación y pregunta innecesaria por el
  cliente de la factura. `pytest` -> **376 passed**. Evidencia:
  `.agents/evidencias/vps_despliegue_recordatorios_2026-11-12.txt`.

- **VPS + Evolution (2026-11-12).** El CRM quedó desplegado en Contabo (`/opt/horminor`), clonado con deploy key read-only desde `ObjetivoCesar/horminor-crm`. `core-api` escucha en `127.0.0.1:8012`; Caddy publica solo `https://horminor.178.238.238.158.sslip.io/health` y el webhook de Evolution. El panel se usa por túnel SSH hasta que exista login. Instancia Evolution `horminor` creada con webhook; estado `connecting`, pendiente escanear QR. Ver `docs/DESPLIEGUE_VPS_HORMINOR.md` y `.agents/evidencias/vps_deploy_evolution_2026-11-12.txt`.
- **v6.13.1 cerrada el 2026-11-12.** Gato ya no pierde el hilo: `gato_turnos` (migración 074) guarda cada turno y el endpoint devuelve `conversacion_id`; el widget lo persiste por usuario. El backend pasa los últimos 8 turnos al LLM, así **"descárgala"** devuelve el PDF de la factura anterior. La búsqueda de clientes ahora normaliza puntuación ("ing reyes" encuentra "Ing. Reyes"). La factura incluye un enlace `?download=1` y el widget lo pinta como **Descargar archivo**. Evidencia: `.agents/evidencias/gato_memoria_v6131_2026-11-12.txt`; `pytest` -> **342 passed**.
- **v6.13 cerrada el 2026-11-12.** El expediente del cliente estrena la pestaña **Facturas**: se adjunta un PDF o foto (`client_invoices`, migración 073) y, si se elige una orden, los montos salen de ella; nunca se inventan. La factura de prueba `PRUEBA-0001` quedó en Ing. Reyes (orden #55, **$43.424,00** con IVA) y está marcada **FICTICIA**. Gato la consulta con `cliente_facturas` y advierte que no es comprobante electrónico del SRI (fuera de alcance). `pytest` -> **338 passed**; `auditar_skills.py` -> **177 verificaciones**. Evidencia: `.agents/evidencias/facturas_v613_2026-11-12.txt`, `factura_prueba_2026-11-12.pdf`, `panel_v613_facturas_2026-11-12.jpeg`.
- **v6.9 cerrada el 2026-11-11.** El chat del expediente es **espejo de WhatsApp** (canal `WHATSAPP`, aviso de conexion, salientes `PENDIENTE` hasta que Evolution este configurado) y tiene estetica WhatsApp: burbujas con cola, ticks, separadores de dia y menu del clip (Galeria, Camara, Documento, Audio, Ubicacion, Contacto). La multimedia se comprime en el backend (imagenes a WebP, videos a H.264 <=720p/180 s, audio intacto), se guarda en Bunny bajo `clientes/<nombre>_<cedula>/` o en el sandbox local, y se indexa en `media_assets` (migracion 071). `scripts/media_v69_check.py` -> **MEDIA V6.9: OK**; `pytest` -> **291 passed**. Evidencia: `.agents/evidencias/media_v69_check_2026-11-11.txt`, `pytest_v69_2026-11-11.txt`, `panel_v69_chat_2026-11-11.jpeg`, `panel_v69_adjunto_2026-11-11.jpeg`. Decisiones en `docs/WHATSAPP_Y_MEDIA.md`.
- **v6.10 cerrada el 2026-11-12.** La agenda de **Planta, Flota y Kardex** usa como fondo la fotografía entregada por Dirección (`static/brand/fotos/planta-agenda.webp`) con overlay para mantener la lectura. **Banca y Mercado** estrena cabecera con tres cuentas (Pichincha, Guayaquil, Internacional) y sus logos; el detalle sale de `GET /api/v1/dashboard/bancos` (configuración de Empresa), sin inventar números ni saldos. `pytest` -> **295 passed**. Evidencia: `.agents/evidencias/pytest_v610_2026-11-12.txt`, `panel_v610_planta_2026-11-12.jpeg`, `panel_v610_banca_2026-11-12.jpeg`.
- **Bancos — traspaso 2026-11-12:** leer **`docs/BANCOS_PENDIENTES.md`**. Resumen: las columnas de tarjeta/detalle están implementadas; **el cierre de caja NO menciona el banco** (agrupa por método y bolsa); las cuentas se configuran hoy solo en **Banca > Editar datos**; `empresa.bot_publico.bank_accounts` está desconectado y no hay Superadmin > Bancos. Siguiente: selector de banco en `dlg-pago`, `bank_account_id` en `payments` y desglose por banco en el cierre.
- **v6.11 cerrada el 2026-11-12.** En **Banca y Mercado** el banco seleccionado se pinta en amarillo y abre un detalle con **saldo contable**, **saldo informado**, entradas, préstamos y movimientos. La migración `072` crea `bank_accounts` y las cuentas hijas `1102.01/02/03`; el saldo informado se edita desde **Editar datos** (ACL de Finanzas). Los datos reales quedan en `NULL`/cero hasta que Gerencia los cargue; el flujo de edición se probó y se limpió. `pytest` -> **296 passed**. Evidencia: `.agents/evidencias/pytest_v611_2026-11-12.txt`, `panel_v611_banca_2026-11-12.jpeg`.
- **Asistente IA — propuesta 2026-11-12:** leer **`docs/ASISTENTE_IA_PROPUESTA.md`** y **`docs/ASISTENTE_IA_SKILLS.md`** (§8–§12: PDF independiente, agendas de obras/visitas, auditoría de precios/costos, bibliotecario). El PDR (§3.2) prohíbe un chatbot abierto y la decisión 14 lo ratifica; la propuesta lo cumple con **function calling sobre un catálogo fijo de herramientas** (sin SQL libre), verificador determinístico de cifras, permisos por rol y auditoría. Dos personas: `INTERNO` (solo CRM, DeepSeek) y `PUBLICO` (info + manos). **Hallazgo:** el precio por m³ es manual y **no** está atado al costo; no existe costeo por receta ni alerta de margen. Skill de operación: `.agents/skills/bibliotecario-datos/SKILL.md`. **No hay código**: faltan las decisiones de §12.
- **Skills v7.0 — pilares 2026-11-12 (v1.2 arbitrada):** leer **`docs/SKILLS_PILARES_HORMINOR.md`** v1.3 y **`docs/CATALOGO_CONSULTAS.json`** v1.1. Estándar de 5 componentes adaptado (SKILL.md ≤ 12.000 caracteres, roles ≤ 70 líneas y una capa por rol, contratos JSON Schema 2020-12), 14 pilares en **6 colas congeladas** y 3 skills completas en `.agents/skills/`: **`pdf-cotizaciones`**, **`banca-mercado`** y **`bibliotecario-datos`**. Catálogo cerrado: **22 consultas implementadas + 5 propuestas**, con `requeridos` por consulta. Contratos del bibliotecario **v1.4**: **12 parámetros**, **23 fuentes reales**, **24 `allOf`** (22 ACL+requeridos + 1 whitelist + 1 bloqueo cruzado), ficha escalar con `ficha_id`/`consulta_id` y DECIMAL negativo. `balance`, `resultados`, `banco_detalle` y `salud_sistema` cerrados a `BODEGA`/`SECRETARIA`. Montos como texto decimal y `precio_ref.ficha_id` 1:1 con la ficha de precio. Paquete para Carbon: **`docs/CARBON_ARRANQUE.md`** v1.3. Auditoría: **`docs/AUDITORIA_SKILLS_CARBON.md`** + `scripts/auditar_skills.py` (177 verificaciones en verde). Siguiente: reconstruir `bibliotecario-datos` con Carbon y auditar la salida.
- **Pilar #1 aprobado (referencia) 2026-11-12:** `bibliotecario-datos` pasa los 10 vectores y el checklist; `scripts/auditar_skills.py` → **177 verificaciones en verde**. Contratos: `consulta.json` v1.4.0 (24 `allOf`), `ficha_dato.json` v1.3.0 y `solicitud_cotizacion.json` v1.2.0. **La entrega de Carbon sigue pendiente.** Punto de retorno: **`docs/CONTINUACION_2026-11-12.md`**.
- **Gato — bot interno v2.1 (2026-11-12):** `services/core-api/app/asistente/` con **10 pilares**, **22 consultas conectadas** (0 `NO_CONECTADA`), **ACL desde el catálogo**, **guarda de cifras** con formato EU/US, negativos, FC-210, cantidades y conteos; estados `OK/VACIO/FALTA_PARAMETRO/ACL/PROPUESTA`; tool calling DeepSeek y **endpoint** `POST /api/v1/asistente/chat` con el rol desde la sesión, nunca del body. **Widget "Gato"** visible en `/panel` con estilo WhatsApp (fondo opaco, burbujas, tablas) y fallback a Julio si no hay perfil en "Viendo como". Base ficticia `orminorth_gato_test` + `db/seeds/gato_ficticio.sql`; loop **39 preguntas / 0 errores con DeepSeek real** (`.agents/evidencias/gato_loop_llm_2026-11-12.txt`); **332 tests**. Docs: **`docs/GATO_PROMPT.md`** y **`docs/GATO_CORPUS.md`**. Siguiente: probar el widget con el perfil de Secretaría y cargar preguntas reales.
- **Tarea para Abel (2026-11-12):** `.agents/tareas/2026-11-12_ABEL.md` — conectar Evolution, activar Bunny con token, persistir entrantes, enviar multimedia y cargar cédula/cuentas. Incluye criterios de aceptación y comandos.
- **v6.8 cerrada el 2026-11-11.** El expediente del cliente estrena la pestana `💬 Chat`: historial en PostgreSQL (`chat_conversaciones` + `chat_mensajes`, migracion 070), API para leer/escribir/marcar leido y buscar, badge de no leidos, burbujas y compositor. La ingesta de WhatsApp es idempotente por `whatsapp_msg_id`. La base real queda con **0 mensajes** (los de prueba se borraron). `scripts/chat_v68_check.py` -> **CHAT V6.8: OK**; `pytest /app/tests` -> **283 passed**. Evidencia: `.agents/evidencias/chat_v68_check_2026-11-11.txt`, `pytest_v68_2026-11-11.txt`, `panel_v68_chat_2026-11-11.jpeg`. Mapa de la base en `docs/BASE_DE_DATOS.md` §9.
- **v6.7 cerrada el 2026-11-11.** Carpetas de Clientes estrena boton `Filtros` con contador, panel desplegable y chips de filtros activos; se corrigio el `[hidden]` global que mantenia visibles los campos de fecha. Obras activas usa dos fotografias reales en `static/brand/fotos/` (`mixers-en-planta.jpg` y `mixer-en-descarga-sin-marca.jpg`). `pytest /app/tests` -> **277 passed**. Evidencia: `.agents/evidencias/pytest_v67_2026-11-11.txt`, `panel_v67_filtros_2026-11-11.jpeg`, `panel_v67_fotos_2026-11-11.jpeg`.
- **v6.6 cerrada el 2026-11-09.** Carpetas de Clientes con banner de 4 filtros, buscador Sabueso (tildes, b/v, z/s/c, ll/y, nombre invertido, 7m3, FC-210, #orden, obra/ciudad), filtros combinables, paginacion de 12 y expediente en 3 pestanas. Migracion 069 agrega ciudad/obra frecuente. `docs/tutoriales/` con 7 archivos para el futuro bot. `pytest /app/tests` -> **277 passed**. Evidencia: `.agents/evidencias/pytest_v66_2026-11-09.txt`, `panel_v66_2026-11-09.txt`.`n- **v6.4 cerrada el 2026-11-09.** Superadmin rediseñado con 4 action cards (`Usuarios y accesos`, `Caja chica y horarios`, `Recetas, flota y precios`, `Tasas y conteo de silos`), 2 tarjetas resumen, modales independientes y selector `Viendo como` con opción directa de gestión. Se eliminaron los textareas de JSON y los placeholders `null`. `pytest /app/tests` -> **272 passed**. Evidencia: `.agents/evidencias/pytest_v64_2026-11-09.txt`, `panel_v64_2026-11-09.txt`.`n- **v6.2 cerrada el 2026-11-09.** Componente unico `HorminorAgenda` montado en Dashboard, Secretaria y Planta; se elimino el calendario que leia `orders.created_at`; Superadmin edita topes de caja/compra, fondo base y horarios de planta; `panel_users_acl` trae 5 perfiles con checklist y el selector "Viendo como" aplica modulos y solo-lectura. `pytest /app/tests` -> **270 passed**. Evidencia: `.agents/evidencias/pytest_v62_2026-11-09.txt`, `panel_v62_2026-11-09.txt`, `v62_clone_2026-11-09.txt`.`n- **v6.0 cerrada el 2026-11-09.** Migración 067 aplicada a la base real: ventanilla curada (5401/5301/5201 + 1106), tope de caja chica configurable, compras con proveedores y recepción, cierre que resta compras en efectivo y agenda real de entregas/mixers. pytest /app/tests -> **265 passed**. Evidencia: .agents/evidencias/pytest_v6_2026-11-09.txt, clone_v6_2026-11-09.txt, panel_v6_2026-11-09.txt.
- **UX de SecretarÃ­a ajustada el 2026-11-09.** La vista abre con acciones
  visibles (cobrar/abonar, gasto, nueva orden) y el orden por tarea: acciones â†’
  resumen + cierre â†’ cartera â†’ Ã³rdenes. Cartera con buscador y cobro por fila.
  `pytest /app/tests` â†’ **247 passed**, consola del navegador sin errores.
  Evidencia: `.agents/evidencias/pytest_ux_secretaria_2026-11-09.txt`.
- **v5.1: panel, Superadmin y backup el 2026-11-09.** El panel de SecretarÃ­a
  registra cobros/abonos y gastos contra `/api/v1/panel/pagos`; Superadmin
  edita `finanzas.parametros_contables` y registra el conteo fÃ­sico; el backup
  diario `scripts/backup_db.sh` verifica el dump con `pg_restore --list`.
  `pytest /app/tests` â†’ **247 passed**; `http_gate_v44_check.py` â†’ **OK** con
  12 verificaciones y `ROLLBACK` en 17 tablas.
- **Custodio v4.4.0 con HTTP cerrado el 2026-11-09.** `app/http_gate/` expone
  `POST /api/v1/custodio/mutations`, `/queries`, `/witness` y
  `GET /catalog` con tokens de servicio; `POST /api/v1/secretaria/pagos`
  registra `COBRO`, `GASTO_CAJA_CHICA` y `GASTO_BANCARIO`, valida saldo,
  separa abono/anticipo y es idempotente. `scripts/http_gate_v44_check.py`
  contra `orminorth_v43` â†’ **HTTP GATE V4.4: OK** con 10 verificaciones y
  `ROLLBACK` en 17 tablas. Evidencia:
  `.agents/evidencias/http_gate_v44_check_2026-11-09.txt`.
- `scripts/custodio_v43_check.py` â†’ **CUSTODIO V4.4: OK** con 30 solicitudes
  (21 ACCEPT, 6 REJECT, 3 PENDING), 8 testigos, 4 aprobaciones y 9 consultas;
  incluye anulaciÃ³n con `CONVERTIR_A_ANTICIPO_CLIENTE`,
  `DEVOLVER_DINERO_CAJA_O_BANCO` y anticipo 1103/2102. Evidencia:
  `.agents/evidencias/custodio_v44_check_2026-11-09.txt`.
- `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` â†’ **242 passed**, exit 0 (`.agents/evidencias/pytest_http_v44_2026-11-09.txt`).
- Hito 1 â†’ `[CANDADO CERRADO]` y Hito 3 â†’ `[CANDADO CERRADO EN SANDBOX]`
  (`.agents/evidencias/hito1_lock_http_v44_2026-11-09.txt`,
  `hito3_lock_http_v44_2026-11-09.txt`).
- Base real: 13 migraciones, Ã³rdenes #9/#55/#56/#57, cartera
  **55,043.60 / 2 clientes / fiado 55,043.60**, `payments=0`, 249 movimientos
  y materiales intactos. Evidencia:
  `.agents/evidencias/base_real_v44_final_2026-11-09.txt`.
- **Custodio v4.3 implementado y verificado el 2026-11-09.** `app/custodio/`
  (`contracts.py`, `ledger.py`, `catalog_hygiene.py`, `witness.py`, `gate.py`)
  cubre **14/14 intents de mutaciÃ³n, 9 consultas, 8 solicitudes de testigo y
  2 aprobaciones**. `scripts/custodio_v43_check.py` contra `orminorth_v43` â†’
  **CUSTODIO V4.3: OK** con 23 solicitudes (17 ACCEPT, 4 REJECT, 2 PENDING),
  asientos balanceados, cartera, compras, depreciaciÃ³n, prÃ©stamo, anulaciÃ³n y
  catÃ¡logo contable; **ROLLBACK verificado en 17 tablas**. Evidencia:
  `.agents/evidencias/custodio_v43_check_2026-11-09.txt`.
- `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` â†’ **223 passed**, exit 0 (`.agents/evidencias/pytest_custodio_v43_2026-11-09.txt`), incluidos 26 tests puros del Custodio.
- Hito 1 â†’ `[CANDADO CERRADO]` y Hito 3 â†’ `[CANDADO CERRADO EN SANDBOX]`
  (`.agents/evidencias/hito1_lock_custodio_v43_2026-11-09.txt`,
  `hito3_lock_custodio_v43_2026-11-09.txt`).
- Base real sin residuos del Custodio: `ledger_entries`, `audit_witness_log`,
  `approval_requests`, `processed_requests`, `purchases` y `supplier_payments`
  en **0**; 249 movimientos de kardex y los 5 materiales con sus costos y
  stocks intactos. Cartera **55,043.60 / 2 clientes / fiado 55,043.60**.
  Evidencia: `.agents/evidencias/base_real_post_custodio_2026-11-09.txt`.
- **Kardex v4.3 aplicado y verificado el 2026-11-09.** `kardex.py` calcula
  costo promedio ponderado en `COMPRA`, guarda `costo_unitario_snapshot` en
  todos los movimientos y revierte consumos `TEORICO` con una fila `ANULACION`
  idempotente por `ANULA:<id>`; las correcciones fÃ­sicas usan `AJUSTE`.
  `scripts/kardex_v43_check.py` contra `orminorth_v43` â†’
  **KARDEX V4.3: OK** (promedio 9.1000, snapshot, reversa de 140 a 150,
  rechazo de anulaciÃ³n fÃ­sica y `ROLLBACK` total).
- `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` â†’ **197 passed**, exit 0 (`.agents/evidencias/pytest_kardex_v43_2026-11-09.txt`).
- Hito 1 â†’ `[CANDADO CERRADO]`, 235 movimientos de kardex (`.agents/evidencias/hito1_lock_kardex_v43_2026-11-09.txt`).
- Hito 3 â†’ `[CANDADO CERRADO EN SANDBOX]` (`.agents/evidencias/hito3_lock_kardex_v43_2026-11-09.txt`).
- **Refactor v4.3 aplicado y verificado el 2026-11-09.** `crear_orden` lee
  `finanzas.iva_default_aplica` y el `iva_pct` de la receta, escribe
  `aplica_iva`/`iva_pct`/`iva_monto`/`total_con_iva` e inserta el `COBRO` de
  contado o abono en la misma transacciÃ³n; `FIADO` no genera `COBRO`.
  `scripts/refactor_v43_check.py` contra `orminorth_v43` â†’
  **REFACTOR V4.3: OK** (4 ventas, cartera, `deleted_at`, caja y dashboard;
  0 registros de prueba al terminar). Evidencia:
  `.agents/evidencias/refactor_v43_check_2026-11-09.txt`.
- Ã“rdenes reales #55/#56/#57 con IVA 15 % y bruto **$43,424.00 / $9,448.40 /
  $2,171.20** (los candados las recrean con el cÃ³digo nuevo); cartera real
  **55,043.60 / 2 clientes / fiado 55,043.60**; `payments` sigue en 0 porque las
  tres son FIADO. La #9 histÃ³rica conserva `total`/`total_con_iva` `NULL`.
  Los costos de materiales siguen en **8.2000 / 14.0000 / 16.5000 / 3.8000** y
  el stock en **3,500 / 450 / 550 / 600**; el kardex no tocÃ³ datos reales.
- **Custodio v4.3 aplicado el 2026-11-09.** `.agents/evidencias/revision_v43_2026-11-09.txt`: 11 migraciones, 28 tablas, 6 vistas, 26 cuentas, `por_cobrar 47,864 / 2 clientes / fiado 47,864` (foto previa al refactor); respaldo previo `pre_v43_orminorth.dump`.
- `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` (pre-refactor) â†’ **180 passed**, exit 0 (`.agents/evidencias/pytest_v43_2026-11-09.txt`).
- Hito 1 â†’ `[CANDADO CERRADO]`, 235 movimientos de kardex (`.agents/evidencias/hito1_lock_v43_2026-11-09.txt`).
- Hito 3 â†’ `[CANDADO CERRADO EN SANDBOX]` (`.agents/evidencias/hito3_lock_v43_2026-11-09.txt`).
- Pruebas SQL en `orminorth_v43` â†’ 7 guardas OK, 0 FALLO (`.agents/evidencias/sql_tests_v43_2026-11-09.txt`).
- Contratos v1.3.0 â†’ 4 esquemas vÃ¡lidos, 14/14 ramas (`.agents/evidencias/contracts_v13_2026-11-09.txt`).
- `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` (sesiÃ³n previa) â†’ **180 passed**, exit 0 (`.agents/evidencias/pytest_panel_horminor_2026-11-08.txt`).
- Playwright 1440Ã—1000 â†’ 3 tarjetas de **253 px** cada una, anillo **0.31%**, **372 / 120,000 mÂ³**, ventas **404 mÂ³ / $47,864 / 4 Ã³rdenes / 51 viajes**, provincias Orellana/SucumbÃ­os/sin provincia, 2 obras con SVG locales, **3 KPIs plegados**, Poppins OK, overflow 0, **0 errores de consola**, **0 requests fallidos**.
- Playwright Banca â†’ **mercado 215,000 mÂ³ Â· ventas 404 mÂ³ Â· 0.19% Â· brecha 214,596 mÂ³**, 2 provincias, 2 escenarios.
- Playwright 390Ã—844 â†’ las 3 tarjetas se apilan, overflow 0, 6 tabs visibles, top header sticky, 2 obras.
- Capturas: `.agents/evidencias/panel_horminor_dashboard_dark.png`, `panel_horminor_dashboard_light.png`, `panel_horminor_banca.png`, `panel_horminor_secretaria.png`, `panel_horminor_superadmin.png`, `panel_horminor_movil.png`, `panel_horminor_clientes.png`, `panel_horminor_planta.png`, `panel_horminor_notificaciones.png`, `panel_horminor_busqueda.png`.
- Design system: `.agents/diseno/horminor_design_system.json`.

## Limitaciones del Cerebro experimental (no se corrigen ahora)

Documentadas al cerrar la fase. Se retomarán de forma progresiva con el sistema
de correcciones; no se abren frentes individuales.

- **Cliente no solicitado:** en el audio de Díaz Sur, Julio dice «acabo de hacer
  un contrato», no «créame el cliente»; el motor igual propone `crear_cliente`.
- **Nombres mal interpretados:** el vocabulario aprendido convierte «Díaz Sur»
  en «Dualsur».
- **Encargos no identificados:** la transferencia de 27 000 USD quedó como un
  segundo encargo en lugar de ser un dato del primero.

## Bloqueos actuales (ordenados por impacto)

1. **Credenciales reales de Evolution API, Bunny.net y Gemini.** Ya **no
   bloquean** demos ni el cierre lÃ³gico: en SANDBOX el WhatsApp se encola en
   `sandbox_outbox`, Bunny devuelve URLs simuladas y el Juez es determinÃ­stico.
   Abel las sube el **2026-11-09**; se cargan desde el Superadmin
   (`whatsapp_evolution_y_cdn`) y se apaga el switch para pasar a producciÃ³n.
2. **TelÃ©fonos reales del personal.** La identidad ya estÃ¡ implementada
   (nÃºmero registrado + cÃ³digos `#BODEGA`, `#CAJA`, `#ADMIN`, `#M<n>`);
   `whatsapp.staff` tiene semillas de demostraciÃ³n editables en
   `directorio_roles_whatsapp`.
3. **Datos que Julio todavÃ­a no entregÃ³:** RUC, horario, cuentas bancarias,
   placas, choferes, precio de mercado por provincia y umbral de merma. Quedan
   `NULL`/vacÃ­os o como semilla marcada; no se inventaron.
4. **Capacidad operativa de planta (mÂ³ por perÃ­odo) sin definir.** El dashboard
   ya no la usa para el anillo principal (muestra el mercado real de El Coca);
   sigue faltando para un KPI de capacidad operativa. DueÃ±o del dato: Julio.
5. **Formulario de pagos implementado.** `/panel` ya registra cobros, abonos y
   gastos contra `/api/v1/panel/pagos`; falta validarlo con la secretaria real.
6. **Login de usuario final â€” backlog exclusivo pre-VPS (decisiÃ³n 2026-11-09).**
   El panel sigue afinÃ¡ndose en local con el puente `X-Panel-Role`; el login
   (`panel_users`, hash, cookie `HttpOnly`) se implementa **solo antes de
   publicar en el VPS**. Mientras tanto, `/panel`, `/api/v1/panel/*` y
   `/api/v1/secretaria/*` no se exponen a Internet.
7. **Backup diario listo, cron pendiente.** `scripts/backup_db.sh` genera,
   verifica y retiene 14 dÃ­as/6 meses; falta instalarlo en el VPS y copiar los
   dumps fuera de la mÃ¡quina.
8. **Respaldo externo.** Todo el proyecto y la base viven en un solo disco. Hay
   un respaldo manual previo a v4.3, pero no polÃ­tica automÃ¡tica.
9. **Circuito HTTP cerrado.** El Custodio, el router, la ventanilla de pagos y
   el panel estÃ¡n implementados; solo falta el login de usuario.
10. **Decisiones de negocio cerradas; quedan datos operativos.** IVA histÃ³rico,
    fecha de conteo, valoraciÃ³n/DSCR, rol `CONTADORA`, reembolso y nota de
    crÃ©dito ya tienen decisiÃ³n. Falta que Julio/Contadora carguen las tasas,
    que Bodega ejecute el conteo fÃ­sico y que se validen con la operaciÃ³n real.

> **Repositorio: solo local (ratificado 2026-11-08).** El cÃ³digo vivirÃ¡ en el
> VPS; GitHub no es requisito para avanzar. Los commits locales en `orminorth/`
> son la fuente de verdad y el respaldo. `git push` deja de ser un bloqueo y
> pasa a ser una tarea opcional del despliegue (clonar el repo en el VPS).

## Próximo paso exacto

El Cerebro experimental queda **cerrado** (router `router-1.7` congelado, Gato
desconectado, Jev en backlog). El siguiente trabajo es el resto del ERP:

1. **C4:** capturar `fecha_vencimiento` en los formularios de orden y factura;
   hoy todo cae en `SIN_VENCIMIENTO`.
2. **Ubicación v8.2:** probar en un teléfono real el botón **Usar mi ubicación**
   y el pin enviado por WhatsApp. El residuo de prueba ya se limpió.
3. **Factura con extras:** conectar la factura/cartera a `v_orden_total` para
   que sume `orden_extras`.
4. **Contratos de obra cierta y horas extra** (siguiente migración libre) y
   **C9: UI de recordatorios en el panel**.
5. **Cotizaciones Q5 (Gato):** crear borrador, consultar y enviar con “sí”.
6. **Validar el dashboard C5/C6 y Cotizaciones con Julio**: 4 ventanas, presets
   de cobranza, meta/equilibrio y manual.

## Decisiones de arquitectura vigentes

| # | DecisiÃ³n | PorquÃ© |
|---|---|---|
| 1 | 12 tablas (el PDR dice 10 sin enumerarlas) | Cubre todo lo que el propio PDR nombra |
| 2 | `tracking_payload` JSONB es autoritativo | Contrato entre M1 y M3 sin acoplamiento |
| 3 | Kardex teÃ³rico por viaje, no por orden | Cada JSON de viaje es autosuficiente |
| 4 | `materials.stock_actual` = stock real | Evita mezclar teÃ³rico con fÃ­sico |
| 5 | Receta provisional **no** bloquea la venta | El viaje marca `receta_provisional` y el Centinela avisa; detener la venta cuesta mÃ¡s |
| 6 | Migraciones SQL planas + advisory lock | Sin ORM: el contrato es SQL |
| 7 | `timestamptz` en UTC, zona operativa en BD | El offset no se escribe en el cÃ³digo |
| 8 | Identidad WhatsApp: nÃºmero registrado > cÃ³digo de operador > lead | Una sola regla, en base de datos, sin reescribir el bot |
| 9 | Debounce de 14 s sobre Redis, con degradaciÃ³n a memoria | El webhook responde de inmediato y la API sigue arriba si Redis falla |
| 10 | Dos umbrales tÃ©rmicos (60 y 30 min antes) | Aviso temprano para reaccionar y crÃ­tico para escalar |
| 11 | Alertas sin webhook quedan como `NO_CONFIGURADO` en `error_logs` | No se finge un envÃ­o que no ocurriÃ³ |
| 12 | **Todo parÃ¡metro de negocio es dinÃ¡mico** (semilla 050 + Superadmin) | Julio no bloquea el avance; el frontend edita sin tocar cÃ³digo |
| 13 | **Sin login en Superadmin/SecretarÃ­a por ahora** | No frenar pruebas de API ni integraciÃ³n del Frontend; se desacopla al final |
| 14 | El bot arma su respuesta con datos de BD; el LLM solo decide SÃ/NO | Cero precios o promesas inventadas por el modelo |
| 15 | **SANDBOX por adaptadores inyectables** | El mismo contrato pasa a producciÃ³n al cargar credenciales; sin `if` de sandbox en el pipeline |
| 16 | **Outbox persistido** en `sandbox_outbox` + memoria | El simulador y los tests ven lo mismo; no se finge un envÃ­o real |
| 17 | **Cupo de crÃ©dito alerta, no bloquea** | La venta se registra con `excede_cupo_credito=true`; bloquear cuesta mÃ¡s que cobrar |
| 18 | **Precio de orden = explÃ­cito o precio de receta** | La venta queda valorada; si no hay precio en ninguno, el total queda NULL y pendiente |
| 19 | **`clients.provincia` para cuota de mercado** | La demanda es provincial; las ventas sin provincia se informan aparte, no se reparten |
| 20 | **Panel Ãºnico HTML sin build ni CDN** | Funciona en local y VPS sin toolchain de frontend; se puede migrar despuÃ©s |
| 21 | **Centinela sin llamadas externas en SANDBOX** | Un WARN por el CDN real confundÃ­a la salud del sistema |
| 22 | **MigraciÃ³n 061 separada** | La 060 ya estaba aplicada; no se edita una migraciÃ³n aplicada |
| 23 | **Tema visual V2 en tokens CSS** (`data-theme` + `localStorage`) | Oscuro ejecutivo por defecto para Julio; claro de oficina conmutable para SecretarÃ­a; sin build ni CDN y sin tocar contratos ni tests |
| 24 | **Marca visible Horminor; carpeta/repo siguen como `orminorth`** | Es lo que ve el cliente; renombrar rutas, contenedores e historial romperÃ­a comandos sin aportar valor |
| 25 | **Poppins local y sidebar CRM de 258 px** | La tipografÃ­a de la referencia queda servida desde `/static` (sin Google Fonts); la sidebar reproduce la captura y colapsa a barra superior en <900 px |
| 26 | **CorrecciÃ³n de marca en migraciÃ³n 062** | Las migraciones 050/060 ya estaban aplicadas; se corrige el ADN pÃºblico y Bunny sin editar el pasado |
| 27 | **Panel con shell ShikshaQ y jerarquÃ­a nÃºmero-primero** | Top header fijo, sidebar de 6 tabs, donut/actividad/calendario y 3 obras; los pÃ¡rrafos se reemplazan por cifras grandes y barras. Se conservan IDs, `data-*`, rutas y contratos; cero build y cero CDN. Alternativa descartada: copiar los textos largos del API, que cansan la lectura |
| 28 | **`_json_objeto()` normaliza JSONB en M3** | `obtener_carpeta` hacÃ­a `dict(tracking_payload)` y devolvÃ­a 500 cuando asyncpg entrega JSONB como texto. El helper acepta texto o mapping y devuelve `{}` si no se puede parsear; la carpeta forense volviÃ³ a 200 sin tocar el contrato |
| 29 | **Dashboard V2 nÃºmero-primero con el mercado como ancla comercial** | Tres tarjetas iguales (Mercado El Coca, Ventas 2026, DÃ³nde vendes) que responden quÃ© necesita Julio; agenda y actividad bajan a una fila inferior; caja/mixers/bodega quedan en `<details>`. La tarjeta de mercado muestra **0.31% / 372 mÂ³ / 120,000 mÂ³** y la de Banca **215,000 / 404 / 0.19% / 214,596 mÂ³** sin pÃ¡rrafos. Se conservan IDs, `data-*`, rutas API y los tests existentes; ilustraciones SVG locales sin build ni CDN. Alternativa descartada: seguir mostrando el anillo de eficiencia (2/51 viajes) como protagonista, que no vende posicionamiento |
| 30 | **`v_cliente_saldo` conserva las 8 columnas originales** | Los 3 consumidores y `catalog.py` dependen de `id, nombre, estado, total_m3, total_facturado, total_cobrado, total_fiado, saldo_pendiente`; v4.3 agrega `ruc`, `credit_limit_usd` y `saldo_a_favor` al final. Alternativa descartada: reordenar o cambiar tipos, que rompÃ­a consumidores |
| 31 | **Fallback `COALESCE(total_con_iva, total)` en la vista** | Mantiene visibles las Ã³rdenes histÃ³ricas sin bruto (la #9) sin inventarles IVA. Las ventas nuevas ya escriben `total_con_iva`; el fallback queda permanentemente para histÃ³ricos |
| 32 | **IVA 15 % solo para ventas nuevas; histÃ³ricos sin IVA** | La decisiÃ³n de Julio fue default 15 % en ventas nuevas; la #9 anterior queda con `total_con_iva = total`/`NULL` y `finanzas.iva_historico_confirmado=false` hasta confirmaciÃ³n retroactiva |
| 33 | **Inventario por promedio ponderado** | Confirmado el 2026-11-09; `inventory_movements.costo_unitario_snapshot` guarda el costo vigente y el kardex calcula COGS con esa base |
| 34 | **Gate idempotente + ledger/testigo inmutables** | `processed_requests` guarda `request_id` + hash; `ledger_entries` y `audit_witness_log` solo permiten INSERT y las correcciones se hacen con reversa/testigo. Alternativa descartada: `UPDATE` directo, que borra la trazabilidad |
| 35 | **IVA y COBRO inicial en la transacciÃ³n de la orden** | `crear_orden` valida el abono contra el bruto y escribe orden + `payments` juntos: si falla el pago, no queda una venta contada como cobrada. El router no inserta pagos por su cuenta. Alternativa descartada: un segundo `INSERT` desde el endpoint, que dejaba ventas huÃ©rfanas si fallaba |
| 36 | **El pago inicial de una compra va en un asiento `SUPPLIER_PAYMENT` separado** | Si el pago se asentara dentro de `PURCHASE`, corregir el pago con testigo revertirÃ­a tambiÃ©n la compra. Separado, cada documento tiene su propia reversa y su propio testigo |
| 37 | **CorrecciÃ³n con testigo limitada al asiento vigente y a compras de servicio de una lÃ­nea** | Solo se revierte el asiento sin reversa previa (evita duplicar el ajuste) y una compra con inventario o varias lÃ­neas exige nota de crÃ©dito: redistribuir stock o costos desde una cabecera serÃ­a inventar datos |
| 38 | **ValoraciÃ³n/DSCR parametrizados y anulaciÃ³n con modos** | Si faltan tasas en `finanzas.parametros_contables`, el Gate devuelve la foto real y `UNCONFIRMED_FINANCIAL_RATES`; si existen, calcula DCF/DSCR. La anulaciÃ³n con cobros exige `modo_resolucion_cobro` y no consume la aprobaciÃ³n si falta |
| 39 | **Router HTTP con tokens de servicio y roles oficiales** | `CUSTODIO_TOKEN_SUPERADMIN/CONTADORA/SECRETARIA/BODEGA/CHOFER` + `X-Actor-Id` + `X-Channel`; el rol nunca viaja en el JSON. `SECRETARIA` y `CONTADORA` cobran; `BODEGA` y `CHOFER` no |
| 40 | **Pagos con split 1103/2102** | Abono parcial permitido. Si `monto > saldo` y `es_anticipo=false` â†’ `PAYMENT_EXCEEDS_PENDING_BALANCE`; si `es_anticipo=true`, la deuda va a `1103` y el excedente a `2102`, con `saldo_a_favor` |
| 41 | **Reembolso con `modo_resolucion_cobro`** | `CONVERTIR_A_ANTICIPO_CLIENTE` reclasifica a `2102`; `DEVOLVER_DINERO_CAJA_O_BANCO` inserta `REEMBOLSO_CAJA` y borra lÃ³gicamente el cobro original |
| 42 | **IVA por defecto apagado** | `066` deja `finanzas.iva_default_aplica=false`. Las ventas nuevas solo llevan IVA si el contrato envÃ­a `aplica_iva=true`; el panel y los candados lo envÃ­an, asÃ­ que la cartera verificada de $55,043.60 no cambia |
| 43 | **El navegador no recibe tokens del Custodio** | El panel llama a `/api/v1/panel/pagos` y `/api/v1/panel/catalog`; el servidor resuelve el actor (`X-Panel-Role` mientras no haya login). Los `CUSTODIO_TOKEN_*` quedan solo en el backend |
| 44 | **Superadmin edita tasas y conteo, no valores inventados** | `finanzas.parametros_contables` se edita con inputs; el conteo fÃ­sico se registra con stock real y sella `ultimo_levantamiento_at`. Los valores siguen siendo de Julio/Bodega |
| 45 | **Backup diario verificable, no solo un dump** | `backup_db.sh` valida con `pg_restore --list`, retiene 14 dÃ­as y 6 meses, y se complementa con copia externa y restauraciÃ³n mensual |
| 46 | **Login desacoplado al backlog pre-VPS** | Se sigue afinando `/panel` con el puente `X-Panel-Role` (sin credenciales ni bloqueo de rutas) para no perder agilidad en pantallas y flujos. El login (`panel_users`, hash, cookie `HttpOnly`) se implementa Ãºnicamente antes de exponer el panel a Internet. Alternativa descartada: bloquear rutas ahora, que obliga a crear usuarios y frena las pruebas locales |
| 47 | **Un contrato activo no se edita, se adenda** | El impreso firmado y la base no pueden divergir |
| 48 | **Extras: un solo rubro global con descripcion libre** | Julio cobra o absorbe cualquier cosa ajena a Horminor sin taxonomias que se queden cortas |
| 49 | **La cotizacion no crea orden** | Una venta aceptada que no se despacha no debe producir una orden fantasma |
| 50 | **Cada modulo tiene diseno, skill y tareas** | Sin las tres piezas se redisenya lo ya decidido |
| 51 | **La ubicacion no se estima: NULL y `PENDIENTE`** | El mixer necesita el punto real. Guardar texto, GPS o pin de WhatsApp con `ubicacion_origen`; sin coordenadas el PDF dice `PENDIENTE` en vez de inventar una posicion |
| 52 | **La referencia escrita manda sobre el nombre del pin** | El asesor escribe «junto al tanque»; el nombre del pin suele ser generico. El pin solo rellena cuando no hay texto, y un `PUT` parcial no borra lo recibido por WhatsApp |
| 53 | **La tarjeta que aloja un desplegable sube su `z-index`** | `backdrop-filter` crea contexto de apilamiento y el `z-index` del hijo no puede salir de la tarjeta; se corrige en el contenedor (`.card-buscar-clientes`), no subiendo el hijo |

## Riesgos abiertos

- **El VPS tiene datos ficticios.** Cuatro clientes `(PRUEBA)` con facturas
  ficticias y un lead real del bot. No usar esa base para operar ni emitir
  cobros; limpiar antes de cargar clientes reales.
- **El panel del VPS se usa por túnel SSH.** Si el túnel se cae, el link
  `localhost:8012` deja de responder; no hay acceso público por diseño.
- **El número de WhatsApp es no oficial (Baileys).** Un uso masivo o sin
  consentimiento puede bloquear la línea y con ella todo el bot.
- **`ENVIADO` no es `ENTREGADO`.** No se procesa `MESSAGES_UPDATE`; un número
  inexistente puede quedar como enviado.
- Sin backups de PostgreSQL definidos (se van a generar carpetas bancarias).
- Sin proxy inverso ni TLS: no se puede exponer el webhook de Evolution.
- `.env` con clave de desarrollo: **no usar en producciÃ³n** (rotar antes del VPS).
- **Todo el proyecto vive en un solo disco.** Al no usar repositorio remoto, no
  hay copia fuera de la mÃ¡quina: hacer respaldo periÃ³dico del repo (otra unidad,
  disco externo o carpeta en la nube). Esta es la Ãºnica deuda real de "solo
  local".
- Las rutas del panel, SecretarÃ­a y Superadmin estÃ¡n abiertas: **no exponerlas
  a Internet** hasta que exista autenticaciÃ³n.
- Las semillas de staff, flota, bancos y benchmarks son de **demostraciÃ³n**;
  reemplazarlas por datos reales antes de operar.
- La primera llamada al Centinela puede tardar mÃ¡s por apertura del pool; en
  caliente medimos ~100 ms con 12 checks (el PDR exige <200 ms).
