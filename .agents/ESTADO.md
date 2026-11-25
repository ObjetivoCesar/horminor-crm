# ESTADO DEL PROYECTO

> **Skills operativas de Gato implementadas (local, 2026-11-24).** Razonador enriquecido con historial determinístico, skill de cotizaciones con envio inmediato o programado y huella de confirmacion, skill de agenda, politica de permisos por rol, avisos de dinero para Secretaria. El caso «enviale la cotizacion al encargado a las 18:50» queda resuelto: telefono indicado, PDF de la version vigente, hora en gato_recordatorios. 781 pruebas pasan, cero regresiones. Pendiente: prueba real con Julio en telefono fisico.

> **Agenda confirmada publicada en el VPS el 2026-11-24.** La confirmaciÃ³n en Gato agenda visitas y recordatorios internos, o reserva mixers cuando hay cupo. SecretarÃ­a recibe tareas de revisiÃ³n. MigraciÃ³n 100 aplicada, 49 pruebas focalizadas y verificaciÃ³n temporal en PostgreSQL. Contexto limitado a doce asuntos por turno. Pendiente aceptaciÃ³n en el panel con ambos perfiles.

> **Gato publicado en el VPS el 2026-11-24.** Razonamiento semÃ¡ntico y asuntos separados de cotizaciÃ³n, recordatorio y visita. Core API saludable. 15 pruebas focalizadas, persistencia comprobada en PostgreSQL con tabla temporal y siete casos aprobados con el proveedor real. Pendiente aceptaciÃ³n por texto en el panel.

> **Cambio local del 2026-11-24.** Gato prepara reservas de mixers desde el pedido dictado y comprueba cupo por franja. Pytest local con 772 pruebas aprobadas y dos fallos documentales conocidos. Pendiente verificar PostgreSQL y aceptar el recorrido desde el telÃ©fono.

> **H4 en el VPS al 2026-11-24.** Inicio mÃ³vil con cabeceras fotogrÃ¡ficas, accesos cuadrados, prÃ³ximo evento y enlace al registro creado desde Gato. Panel, fotos y API verificados en el VPS. Pendiente la aceptaciÃ³n de Julio y SecretarÃ­a en telÃ©fono fÃ­sico.

> **ActualizaciÃ³n 2026-11-24.** VPS saludable con Gato y Agenda mÃ³vil de la revisiÃ³n local **53c644f**. Verificadas una visita solicitada y una reserva de mixer mediante audio sintÃ©tico con ROLLBACK, 122 pruebas focalizadas y componentes a 390 px. H4 en curso. Quedan la prueba en el telÃ©fono de Julio y el resto de las pantallas. Evidencia: `.agents/evidencias/vps_dictado_movil_2026-11-24.md`.

> Foto del presente. Se reescribe en cada sesiÃ³n. La historia estÃ¡ en `BITACORA.md`.
> Ãšltima actualizaciÃ³n: **2026-11-20** (el recordatorio dictado se programa de
> verdad: Â«a las 15 y 27Â» se lee como hora, un dictado nuevo ya no se toma como
> confirmaciÃ³n del borrador anterior y el chat puede completar la hora al
> confirmar; **la cotizaciÃ³n del borrador se confirma en `/panel/cerebro`** y
> crea el documento en `BORRADOR` con IVA en `Decimal`; **766 pruebas**; local y
> VPS alineados).
> Antes: 2026-11-19 (cierre de **H1**: nÃºcleo comercial con
> leads y citas independientes del canal; panel, Gato y WhatsApp entran por el
> mismo mÃ³dulo; migraciÃ³n **097**; **desplegado y verificado en el VPS**.
> **Gato ya dicta por audio** y una instrucciÃ³n con dos destinatarios deja un
> solo encargo; el resumen se pinta con **negritas y viÃ±etas**; **744 pruebas**).
> Antes: 2026-11-18 (espejo v9.8: **chat en vivo por SSE** â€”
> el hilo se actualiza solo, sin pulsar Sincronizar; multimedia entrante real;
> sesiÃ³n LID reparada, nÃºmero de prueba 0967491847, corte de historial y altura
> fija del chat; **674 pruebas**. **Desplegado en el VPS** con parche
> quirÃºrgico: el endpoint SSE responde y Caddy lo entrega sin buffering
> (38 ms); falta solo la confirmaciÃ³n con un WhatsApp real desde el celular).
> Base v6.17: Custodio v4.4.0 + HTTP, agenda Ãºnica `HorminorAgenda`,
> compras/caja chica, perfiles ACL, Superadmin por Action Cards, Carpetas de
> Clientes con buscador Sabueso, bancos con color de marca, **facturas
> internas adjuntas al cliente** (PDF o foto) consultables por Gato,
> **recordatorios por WhatsApp con ratificaciÃ³n, adjuntos y redacciÃ³n propia**
> y **ubicaciÃ³n de la obra en la cotizaciÃ³n** (texto, GPS y pin de WhatsApp).
> 37 migraciones, 57 tablas, 11 vistas, 30 cuentas; **586 tests** y los 2
> candados en verde. Siguiente foco: conservar y verificar lo construido; el
> Cerebro sigue como inteligencia interna (sin conectar a Gato).
>
> **Continuidad y arquitectura:** `docs/CONTINUIDAD_CEREBRO.md` â€” el Cerebro no
> serÃ¡ un mÃ³dulo visible; Gato serÃ¡ la interfaz; flujo interno y flujo comercial
> externo separados por permisos, herramientas y fuentes. **Manual Vivo:**
> `docs/HORMINOR_MANUAL_FUNCIONAL.md`.

## Hitos

| Hito | MÃƒÂ³dulo | Estado | Evidencia | QuÃƒÂ© falta para cerrar |
|---|---|---|---|---|
| 1 | M0 Ã¢â‚¬â€ Datos y configuraciÃƒÂ³n | Ã°Å¸Å¸Â¢ **Cerrado** con semilla oficial | `evidencias/hito1_lock_2026-11-08.txt`: `[CANDADO CERRADO]`, 235 movimientos de kardex, ÃƒÂ³rdenes valoradas ($37.760 y $8.216) | Nada bloqueante. Re-verificar si se editan recetas |
| Ã¢â‚¬â€ | Superadmin Ã¢â‚¬â€ ConfiguraciÃƒÂ³n en caliente | Ã°Å¸Å¸Â¢ Construido y editable desde el panel | 7 secciones, CRUD de recetas/flota, simulador de WhatsApp y outbox | AutenticaciÃƒÂ³n antes de exponerlo a Internet |
| 2 | M2 Ã¢â‚¬â€ Motor determinÃƒÂ­stico | Ã°Å¸Å¸Â¡ Construido, verificado local | `evidencias/pytest_panel_v44_2026-11-09.txt`: **247 tests** + candado Hito 1 | Probar desde el CRM de la agencia en el VPS |
| 2 | M5 Ã¢â‚¬â€ Nodo Centinela | Ã°Å¸Å¸Â¡ Construido, verificado local | `evidencias/hito3_4_live_2026-11-08.txt`: 12 checks, `modo=SANDBOX`, `judge_mode=DETERMINISTIC_FALLBACK`; Evolution/Bunny en OK | Webhook real del CRM; umbral de merma que defina Julio |
| 3 | M1 Ã¢â‚¬â€ WhatsApp (Evolution + Jeb + Bunny) | Ã°Å¸Å¸Â¢ **Cerrado en SANDBOX** | `evidencias/hito3_lock_2026-11-08.txt`: `[CANDADO CERRADO EN SANDBOX]`; 4 compuertas, JSONB y outbox | ProducciÃƒÂ³n real: cargar credenciales, apagar SANDBOX y repetir el candado |
| 4 | M3 Ã¢â‚¬â€ Ventanilla de SecretarÃƒÂ­a + Caja | Ã°Å¸Å¸Â¢ **Cerrado** y verificado local | `/panel` (tab SecretarÃƒÂ­a) con formularios de cobro/abono y gasto; carpeta forense; `POST /api/v1/panel/pagos` probado; tests `test_m3_secretaria.py` | ValidaciÃƒÂ³n con la secretaria real (afinamiento, no bloqueante) |
| 4b | Custodio v4.4 + Panel de Pagos/Gastos/Tasas/Conteo | Ã°Å¸Å¸Â¢ **Cerrado** (2026-11-09) | `evidencias/pytest_panel_v44_2026-11-09.txt` (**247 tests**); `evidencias/http_gate_v44_check_2026-11-09.txt` (`HTTP GATE V4.4: OK`, 12 pasos, `ROLLBACK` 17 tablas); `/panel` con `dlg-pago`, `dlg-gasto`, `conteo-materiales`, `fin-wacc`; `GET /api/v1/panel/catalog` Ã¢â€ â€™ 26 cuentas | Nada bloqueante. Cargar tasas, ejecutar conteo real e instalar cron quedan como operaciÃƒÂ³n del cliente/VPS |
| 5b | VPS + GitHub + Evolution API | OK **Primera subida** (2026-11-12) | Repo `ObjetivoCesar/horminor-crm` (commit `a94a618`), deploy key read-only, VPS `/opt/horminor`, `core-api` en `127.0.0.1:8012`, Caddy `horminor.178.238.238.158.sslip.io` (solo `/health` y webhook), 21 migraciones, instancia Evolution `horminor` creada y webhook configurado; `docs/DESPLIEGUE_VPS_HORMINOR.md` | Escanear QR, probar texto con telÃ©fono real, rotar API key y cargar backups |
| 4n | v6.13.1 - Memoria de Gato + descarga de factura | OK **Cerrado** (2026-11-12) | MigraciÃ³n 074 (`gato_turnos`); `conversacion_id` en el endpoint y en el widget; historial de 8 turnos al LLM; bÃºsqueda de clientes sin puntuaciÃ³n ("ing reyes" â†’ "Ing. Reyes"); enlace `?download=1` en la factura; pytest (**342 tests**) | Validar el hilo con el uso real de Julio/SecretarÃ­a |
| 4o | v6.17 - Gato secretaria: ratificaciÃ³n, adjuntos y redacciÃ³n | ðŸŸ¢ **Desplegado y probado en VPS** (2026-11-13) | Migraciones 075â€“078; envÃ­o real de `PRUEBA-0002.pdf` y de un mensaje redactado al 0967491847; candado de cifras (`cifras_de`/`_cifras_permitidas`); 4 clientes ficticios con factura en el VPS; `pytest` **376**. Doc `docs/GATO_SECRETARIA.md` v1.3 | C8 nÃºmero vivo, C9 UI en el panel, C11 acuse de entrega, C12 test de integraciÃ³n |
| 4p | v8.2 - UbicaciÃ³n de la obra en la cotizaciÃ³n + Sabueso | ðŸŸ¢ **Cerrado** (2026-11-14) | MigraciÃ³n 084 (`ubicacion_*`, CHECKs, `UBICACION_SOLICITADA/RECIBIDA`); `/pedir-ubicacion`, pin por WhatsApp end-to-end, GPS del navegador, bloque en el PDF; `.card-buscar-clientes` desatasca el Sabueso; `pytest` **423** y Hito 3 en verde. Evidencia `.agents/evidencias/ubicacion_v82_2026-11-14.txt` | Probar en un telÃ©fono real; el residuo de prueba ya se limpiÃ³ |
| 4q | v8.3 - Cerebro y Voz: de audio a borrador | ðŸŸ¡ **En curso** (2026-11-15) | Fases 0â€“2: servicios extraÃ­dos, migraciones **085/086**, ingesta, **Groq/Whisper** con palabras y tiempos, mapa de alineaciÃ³n, hechos citados, compilador con invariantes, sobre, extractor y endpoints `/voz` y `/cerebro`; laboratorio en **`/panel/cerebro`** con pestaÃ±as texto/audio; caso JoaquÃ­n (telÃ©fono en grupos, hora â‰  fecha, identidad preguntada); caso Juan Carlos (tarea de WhatsApp en `gato_recordatorios`, abono suprimido sin comprobante); caso DÃ­az Sur (dos contactos `contacto.2.*`, resistencia â‰  precio, plazo/descuento/planta mÃ³vil, 16 hechos, pregunta a cuÃ¡l ingeniero); normalizador une guiones y Â«27 milÂ»; **popout de tareas + campanita** en `/panel` con `GET /cerebro/tareas/pendientes`; `pytest` **534** y Hito 3 en verde; **correcciones humanas con bÃ³veda** (migraciÃ³n **087**, `cerebro_correcciones` append-only y `v_cerebro_vocabulario`), lectura en voz alta (Â«Lo que entendÃ­Â») con botÃ³n **Corregir** que rehace el borrador como versiÃ³n nueva (sin borrar la anterior), pista de vocabulario en el prompt, **guarda de dinero** (sin frase en pasado no se registra abono: se pregunta) e **informe semanal de errores** (`scripts/informe_cerebro_errores.py`). **Tareas internas con reloj** (migraciones **088/089**, `cerebro_tareas_internas` + eventos append-only, `v_cerebro_tareas_internas`): una instrucciÃ³n sin telÃ©fono (Â«que revisen en secretarÃ­aâ€¦Â») nace **NOTIFICADA**, se **resuelve o justifica** con nota y se **registra con metadatos**; el panel la muestra con **aviso fijo arriba** (no depende de un popout que se pueda cerrar o minimizar, ni de `localStorage`), campanita y botones; **aviso, vista y acuse** separados, **prioridad y plazo**, **escalada** y **ficha determinÃ­stica** de la tarea; `TENTATIVO` para dudas (Â«300 y picoÂ») que no se vuelven datos definitivos; **intenciÃ³n antes que telÃ©fono** (delegar â‰  enviar); **retiro** de vocabulario aprendido equivocado; **revocaciÃ³n completa** del dictado y **negaciÃ³n de instrucciÃ³n citada** (F y L: ni se ejecuta ni se delega); y mide minutos entre eventos. **Manual Vivo** (`docs/HORMINOR_MANUAL_FUNCIONAL.md`) con mapa funcional, Ã­ndice por tÃ©rmino tÃ©cnico/visible/sinÃ³nimo, nombres visibles y skill `orminorth-manual-funcional`; los nombres tÃ©cnicos no cambian, cambian las etiquetas. Evidencias `cerebro_joaquin_2026-11-15.txt`, `cerebro_juan_carlos_2026-11-15.txt`, `cerebro_diaz_sur_2026-11-15.txt`, `panel_cola_tareas_2026-11-15.jpeg`, `cerebro_guarda_dinero_2026-11-15.txt`, `cerebro_tareas_internas_2026-11-15.txt`, `cerebro_informe_errores_2026-11-15.md` y `cerebro_lab_correccion_2026-11-15.jpeg` | Ejecutar `crear_cliente`/`crear_cotizacion_borrador` al confirmar, persistir `contacto.*` en `client_facts`, fase WhatsApp conversacional (contrato en `docs/CONTRATO_WHATSAPP_CEREBRO.md`), bÃ³veda de audios con consentimiento LOPDP y audio humano real |
| 4m | v6.13 - Facturas internas adjuntas al cliente | OK **Cerrado** (2026-11-12) | MigraciÃ³n 073 (`client_invoices`); factura ficticia `PRUEBA-0001` (orden #55, **$43.424,00**) con PDF; pestaÃ±a **Facturas** en el expediente; `GET/POST /api/v1/clients/{id}/facturas`; Gato `cliente_facturas` con marca **FICTICIA** y SRI fuera de alcance; `evidencias/facturas_v613_2026-11-12.txt` y `panel_v613_facturas_2026-11-12.jpeg`; pytest (**338 tests**) | Validar formato con Julio; definir numeraciÃ³n y datos fiscales reales |
| 4l | v6.12 - Logos de bancos con color de marca | OK **Cerrado** (2026-11-12) | Tres placas SVG 96x96: Pichincha amarillo `#FFD100`, Guayaquil rosado `#C7007E`, Internacional naranja `#F39200`; isotipos oficiales, sÃ­mbolo Pichincha a 56/96; `.banco-logo` de 46 px sin caja blanca; evidencias/panel_v612_bancos_dark_2026-11-12.png, _light_ y logos_zoom; pytest (**296 tests**) | Nada bloqueante. Aceptado por DirecciÃ³n; si pide el lockup completo, placas 92x40 |
| 4k | v6.11 - Banco activo + detalle de cuenta | OK **Cerrado** (2026-11-12) | Migracion 072 (`bank_accounts`, hijas `1102.01-03`, `saldo_informado`); tarjetas seleccionables en amarillo; detalle con saldo contable/informado, prestamos y movimientos; `PUT /api/v1/dashboard/bancos/{slug}`; evidencias/panel_v611_banca_2026-11-12.jpeg; pytest_v611_2026-11-12.txt (**296 tests**) | Cargar cuentas y saldos reales; asignar pagos a la cuenta hija del banco |
| 4j | v6.10 - Fondo de Planta + cabecera de Banca | OK **Cerrado** (2026-11-12) | Foto `planta-agenda.webp` como fondo de la agenda con overlay; cabecera de Banca con tarjetas Pichincha/Guayaquil/Internacional y logos; endpoint `GET /api/v1/dashboard/bancos`; tarea `.agents/tareas/2026-11-12_ABEL.md`; evidencias/panel_v610_*.jpeg; pytest_v610_2026-11-12.txt (**295 tests**) | Confirmar cuentas Guayaquil/Internacional y reemplazar foto con marca Vecteezy |
| 4r | v9.8 - Espejo de WhatsApp por lista blanca + **chat en vivo** | ðŸŸ¢ **Funcionando en local y en el VPS con el nÃºmero 0967491847** (2026-11-18) | Migraciones **093/094/095**; mÃ³dulo `app/whatsapp_espejo/` (identidad PN/LID/ALT, **aprendizaje del telÃ©fono desde el historial cuando falta `remoteJidAlt`**, backfill paginado idempotente **con corte desde el alta del cliente**, envÃ­o con `key.id`); webhook del M1 con hook propio; Chat con **Sincronizar**, altura fija de 520 px. **Multimedia entrante real** (imagen, audio, video). **Chat en vivo:** `BusEventos` + `GET /api/v1/whatsapp/espejo/eventos` (SSE) y `chatEventosConectar()` en el panel: el hilo abierto se refresca en **menos de un segundo**, el sondeo de 15 s queda de respaldo. **SesiÃ³n de WhatsApp revincada con QR** (el `SessionError` de Evolution impedÃ­a descifrar). Prueba real: mensaje enviado **desde el celular del cliente** aparece en el chat del CRM; entrantes y salientes correctos; `pytest` **674** | Confirmar en el VPS con un WhatsApp real desde el celular (el SSE ya responde y Caddy lo entrega sin buffering); conectar Bunny para la media entrante (W3); evaluar actualizar Evolution v2.3.7 por el fallo LID; commit del cÃ³digo |
| 4i | v6.9 - Chat espejo WhatsApp + multimedia Bunny | OK **Cerrado** (2026-11-11) | Chat con estetica WhatsApp (clip, camara, audio, ubicacion), canal `WHATSAPP` y estado de conexion; migracion 071 (`media_assets`, `clients.cedula`); compresion WebP/video; tokens Bunny; limites y rate limit; `docs/WHATSAPP_Y_MEDIA.md`; evidencias/media_v69_check_2026-11-11.txt (**MEDIA V6.9: OK**) y pytest_v69_2026-11-11.txt (**291 tests**) | Conectar Evolution y persistir entrantes; cargar cedula y credenciales Bunny |
| 4h | v6.8 - CHAT por cliente en PostgreSQL | OK **Cerrado** (2026-11-11) | Migracion 070 (`chat_conversaciones`, `chat_mensajes`, `v_chat_conversacion`); API `routers/chat_clientes.py`; pestana `ðŸ’¬ Chat` con badge, burbujas y compositor; idempotencia `whatsapp_msg_id`; busqueda full-text; docs/BASE_DE_DATOS.md Â§9; evidencias/chat_v68_check_2026-11-11.txt (**CHAT V6.8: OK**) y pytest_v68_2026-11-11.txt (**283 tests**) | Conectar envio real por WhatsApp (Evolution) |
| 4g | v6.7 - Filtros plegables + fotos reales | OK **Cerrado** (2026-11-11) | Boton `Filtros` con contador y panel desplegable; chips de filtros activos; fix global de `[hidden]`; fotos en `static/brand/fotos/` para Obras; evidencias/pytest_v67_2026-11-11.txt (**277 tests**) | Confirmar foto del mixer (recortada u original) |
| 4f | v6.6 - Carpetas de Clientes + Sabueso | OK **Cerrado** (2026-11-09) | Banner de 4 filtros; buscador multi-variable y fonetico; filtros/paginacion; expediente en 3 pestanas; migracion 069; docs/tutoriales/ (7 archivos); evidencias/pytest_v66_2026-11-09.txt (**277 tests**) | Validar con Julio la busqueda real |
| 4e | v6.4 - UX Superadmin por Action Cards | OK **Cerrado** (2026-11-09) | Banner CENTRO DE CONTROL con 4 action cards; 2 tarjetas resumen (perfiles y WhatsApp/reglas); modales de usuarios/caja/recetas/tasas; cero JSON crudo; selector Viendo como con acceso directo; evidencias/pytest_v64_2026-11-09.txt (**272 tests**) | Validar con Julio los textos y perfiles |
| 4d | v6.2 - Agenda unica, config operativa y ACL | OK **Cerrado** (2026-11-09) | 068 aplicada; HorminorAgenda en Dashboard/Secretaria/Planta; /superadmin/operacion/config; panel_users_acl con 5 perfiles; evidencias/pytest_v62_2026-11-09.txt (**270 tests**) | Validar perfiles reales con Julio |
| 4c | v6.0 - Compras, caja chica y agenda | OK **Cerrado** (2026-11-09) | 067 aplicada; panel con compras/cierre/agenda; recepcion en Planta; `evidencias/pytest_v6_2026-11-09.txt` (**265 tests**); `evidencias/clone_v6_2026-11-09.txt` | Confirmar tope y proveedores reales |
| 5 | M4 Ã¢â‚¬â€ Dashboard de Julio + Ases | Ã°Å¸Å¸Â¢ Construido y verificado local | *Dashboard Julio* con 3 tarjetas iguales: mercado El Coca **0.31% (372/120,000 mÃ‚Â³)**, ventas **404 mÃ‚Â³ / $55,043.60 / 51 viajes** (la captura aprobada 2026-11-08 mostraba $47,864 sin IVA), y provincias **Orellana 372 + SucumbÃƒÂ­os 16 + sin provincia 16**; Banca **215,000 / 404 / 0.19% / 214,596 mÃ‚Â³**; 2 escenarios; tests `test_m4_dashboard.py` | Validar con Julio el ÃƒÂ¡ngulo de mercado; auth para exponer |
| Ã¢â‚¬â€ | Despliegue en VPS | Ã¢Å¡Âª No iniciado | Ã¢â‚¬â€ | VPS, dominio, TLS, proxy, backups |

Leyenda: Ã¢Å¡Âª no iniciado Ã‚Â· Ã°Å¸Å¸Â¡ en curso / candado abierto Ã‚Â· Ã°Å¸Å¸Â¢ cerrado y congelado

## DÃƒÂ³nde estÃƒÂ¡ corriendo

| Componente | Local | VPS |
|---|---|---|
| PostgreSQL 15 | localhost:5433 (contenedor orminorth-postgres) | contenedor orminorth-postgres (sin puerto pÃºblico) |
| Redis 7 | localhost:6380 (contenedor orminorth-redis) | contenedor orminorth-redis (sin puerto pÃºblico) |
| Core API | http://localhost:8000 (contenedor orminorth-core-api) | 127.0.0.1:8012 en el VPS; pÃºblico solo /health y webhook |
| Panel (M3 + M4 + Superadmin) | http://localhost:8000/panel Â· **SANDBOX: no envÃ­a WhatsApp** | http://localhost:8012/panel por tÃºnel SSH (`ssh -i ..\vps-entrada\horminor_vps -N -L 8012:127.0.0.1:8012 root@178.238.238.158`); `envio: evolution`, sÃ­ envÃ­a |

> **Espejo v9.7 en local (2026-11-17):** cliente `PRUEBA - Alejandra WhatsApp`
> (`a6dfca33â€¦`) con el nÃºmero autorizado `593986962872` y **5 mensajes
> sincronizados**. Matiz importante: local muestra "WhatsApp: no conectado"
> porque el **bot del M1** sigue en SANDBOX; el **espejo** del nÃºmero autorizado
> sÃ­ envÃ­a de verdad con su propio cliente Evolution. Son dos canales distintos.

Datos de demo en local: ÃƒÂ³rdenes del Ing. Reyes (320 mÃ‚Â³ FC-210 y 52 mÃ‚Â³ FC-350),
orden del candado del Hito 3 (16 mÃ‚Â³) y clientes de fixture con provincia
Orellana/SucumbÃƒÂ­os para verificar la cuota de mercado. Se regeneran con los
scripts de candado.

## Evidencia de la Ãºltima sesiÃ³n

### 2026-11-19 - Fase 1: conversaciones reales de Gato

- **QuÃ© cambiÃ³:** `gato_conversaciones` con apertura/cierre; una sola abierta
  por actor; refresh atÃ³mico; el panel carga el hilo desde PostgreSQL, no desde
  `localStorage`.
- **Contexto deliberado:** se eliminÃ³ el arrastre de los Ãºltimos cinco dictados.
  Solo se incluye el dictado anterior si el mensaje es una respuesta corta a una
  pregunta pendiente o pide corregir/agregar. **Si el borrador quedÃ³ esperando
  aclaraciÃ³n o confirmaciÃ³n, el siguiente dictado usa el texto completo del
  borrador, aunque sea largo**; asÃ­ una correcciÃ³n no vuelve a preguntar cliente,
  volumen o direcciÃ³n.
- **Enlaces:** `cerebro_borradores.conversacion_id`, `cerebro_extracciones.conversacion_id`,
  `cerebro_tareas_internas.cliente_id` y puente `gato_turno_borradores`.
- **Idempotencia:** `gato_turnos.client_turn_id`; dos envÃ­os del mismo turno
  dejan una sola fila.
- **Comprobado:** dos dictados seguidos no se contaminan (Pastrana y Escuela
  Miguel RofrÃ­o quedan en extracciones separadas); Â«sÃ­, me acaba de dar 200 en
  efectivoÂ» conserva el segundo dictado y marca el pago. El panel carga el hilo,
  refresh lo cierra y al recargar aparece la conversaciÃ³n nueva.
- **Pruebas:** **744 passed**, 2 warnings; panel con 3 bloques `<script>` OK.
- **Evidencia:** `.agents/evidencias/gato_conversaciones_fase1_2026-11-19.txt`.
- **VPS (2026-11-19):** migraciÃ³n **098** aplicada y cÃ³digo desplegado;
  **18** conversaciones, **3** abiertas; **24 passed**; `GET actual` y
  `POST refresh` responden. Respaldo en `/root/backup_gato_fase1_20261119`.
- **Limpieza VPS (2026-11-19):** **0 turnos** visibles, **17 borradores**
  borrados y conversaciones nuevas vacÃ­as para Julio y SecretarÃ­a. Se
  conservaron **2 ejecuciones de auditorÃ­a** y sus extracciones/transcripciones
  porque son append-only; no se ven en el hilo. No se tocaron clientes, pagos ni
  Ã³rdenes.
- **Seguimiento (2026-11-19):** el contexto se perdÃ­a en respuestas largas. Se
  persistiÃ³ el estado de aclaraciÃ³n/confirmaciÃ³n y ahora el siguiente dictado
  usa el texto completo del borrador; el tercer mensaje conserva cliente, 5 mÂ³,
  180 y direcciÃ³n. **745 passed**; VPS **11 passed**. Nueva conversaciÃ³n de
  Julio: `fc29cf49-...`.
- **ConfirmaciÃ³n desde Gato (2026-11-20):** Â«crÃ©alo/confirmadoÂ» ejecuta
  `crear_cliente` con el ejecutor del Cerebro. En el VPS se creÃ³ **Ingeniero
  Pablo Ayala** (`5c20148e-...`) con el telÃ©fono `0963410409`. **746 passed**;
  la cotizaciÃ³n y el abono siguen en 501.
- **Agenda visual (2026-11-20):** `GET /api/v1/agenda/eventos` y la vista
  Â«AgendaÂ» del panel con pestaÃ±as **Mixers**, **Recordatorios**, **Julio** y
  **Equipo**. El chat ahora confirma tambiÃ©n `crear_tarea_recordatorio` y
  `crear_tarea_interna`; el dinero sigue fuera. **16 passed** (v227 + v228).
- **Una sola agenda (2026-11-20):** se retiraron los calendarios duplicados de
  SecretarÃ­a, Planta y Dashboard; crear/editar mixer se hace desde **Agenda**.
  Gato registra Â«mi agendaÂ» sin lead como cita de Julio. **18 passed**.
- **CorrecciÃ³n de citas (2026-11-20):** Â«rectificoÂ», Â«muÃ©velaÂ» y Â«cancela la
  citaÂ» funcionan desde el chat; sin pasado, sin solapes, con auditorÃ­a en
  `cita_eventos`. MigraciÃ³n 099. **758 passed**.
- **Agenda operativa (2026-11-20):** las cuatro pestaÃ±as se manejan desde Gato:
  crear, mover y cancelar mixers, recordatorios y tareas. El monto dictado se
  autoriza como instrucciÃ³n. **760 passed**.
- **VPS (2026-11-20):** agenda desplegada y migraciÃ³n 099 aplicada. Se borraron
  los turnos de Gato en local y VPS; cada perfil tiene una conversaciÃ³n nueva
  vacÃ­a. **45 tests de agenda** en el VPS.
- **Pendiente:** historial completo y bÃºsqueda (Fase 4); autenticaciÃ³n real
  (H6).

### 2026-11-19 - Gato: aviso claro cuando el perfil no tiene Voz

- **QuÃ© pasÃ³:** el audio fallÃ³ con `MODULE_NOT_ALLOWED` porque el panel estaba
  en **Secretaria Ventanilla**, que no tiene Voz ni Cerebro. Julio sÃ­ los tiene.
- **Corregido:** el endpoint devuelve un mensaje accionable (Â«Secretaria
  Ventanilla no tiene el mÃ³dulo Voz. Cambia a Julioâ€¦Â») y el panel lo muestra
  limpio, sin JSON crudo.
- **Perfil base:** la opciÃ³n Â«Julio (base Superadmin)Â» ahora lleva su UUID. Si
  una pestaÃ±a vieja manda solo el rol, el Cerebro usa el perfil base y no
  escala a otros roles.
- **Verificado:** con Julio el mismo audio responde `HTTP 200` y `estado=OK`;
  con SecretarÃ­a, `403` con el aviso. No se cambiaron permisos.
- **Pruebas:** **744 passed**, 2 warnings; panel con 3 bloques `<script>` OK.
- **Evidencia:** `.agents/evidencias/gato_audio_permiso_2026-11-19.txt`.
- **VPS (2026-11-19):** desplegado con respaldo en
  `/root/backup_gato_permiso_20261119`.

### 2026-11-19 - Gato recupera la memoria entre dictados

- **QuÃ© pasÃ³:** cada audio se entregaba al Cerebro como un dictado aislado. El
  segundo audio (Â«me acaba de dar en efectivoÂ») creaba otro borrador y volvÃ­a a
  preguntar cliente y monto; el tercero empezaba de cero. La memoria de Gato
  (`gato_turnos`) existÃ­a, pero no se pasaba al Cerebro.
- **Corregido:** el puente envÃ­a los **dictados previos de la misma
  conversaciÃ³n** como contexto; los hechos nuevos se asignan al Ãºltimo encargo
  previo; Â«me acaba de dar en efectivoÂ» marca `pago.recibido=true`.
- **Comprobado local y VPS:** el segundo dictado conserva Escuela Miguel RofrÃ­o,
  7 m3 de 210, la direcciÃ³n y el pago de 300 USD **Â«que ya entrÃ³Â»**, sin volver
  a preguntar cliente ni monto. El tercero conserva todo.
- **Pruebas:** **744 passed**, 2 warnings (10 en `test_v227_calendario_gato.py`);
  en el VPS **10 passed**.
- **Evidencia:** `.agents/evidencias/gato_memoria_dictados_2026-11-19.txt` y los
  JSON de los pasos 1â€“3 (local y VPS).
- **VPS (2026-11-19):** desplegado con respaldo en
  `/root/backup_gato_memoria_20261119`.

### 2026-11-19 - Gato: calendario y precedencia del dictado

- **QuÃ© pasÃ³:** el audio con Â«agendarÂ» lo capturÃ³ el atajo comercial antes que
  el Cerebro, y el seguimiento Â«este sÃ¡bado y domingoÂ» fallÃ³ porque la
  herramienta de disponibilidad recibiÃ³ la fecha como texto (`'2026-11-21'`)
  donde la base exige `date`. El LLM cayÃ³ al modo determinista y respondiÃ³
  Â«No entendÃ­Â».
- **Corregido:** el prefijo `dictado:` ahora se evalÃºa primero;
  `disponibilidad_agenda` convierte ISO a `date`; `parse_cita` entiende Â«este
  sÃ¡badoÂ», Â«domingoÂ», Â«lunesÂ»â€¦; el prompt de Gato dice **Ecuador
  (America/Guayaquil) | Hoy: YYYY-MM-DD**.
- **Guarda de cifras:** Gato puede repetir una cifra que el usuario dictÃ³
  (70 mÂ³, 4 mil dÃ³lares) sin tratarla como inventada; una cifra sin fuente sigue
  bloqueada.
- **Comprobado:** el seguimiento ya responde Â«sÃ¡bado 2026-11-21 y domingo
  2026-11-22Â», sin Â«No entendÃ­Â» ni error de cifras, en local y en el VPS.
- **Pruebas:** **741 passed**, 2 warnings (7 nuevas en
  `test_v227_calendario_gato.py`); en el VPS **7 passed**.
- **Evidencia:** `.agents/evidencias/gato_calendario_2026-11-19.txt`,
  `gato_calendario_dictado_2026-11-19.json`,
  `gato_calendario_seguimiento_2026-11-19.json` y los JSON del VPS.
- **VPS (2026-11-19):** desplegado con respaldo en
  `/root/backup_gato_calendario_20261119` y `/root/backup_gato_guardas_20261119`;
  el mismo hilo devuelve `SEGUIMIENTO_ESTADO=OK`.

### 2026-11-19 - Gato: resumen con formato y comprobaciÃ³n de la orden de Pastrana

- **Formato:** el resumen de Gato usa markdown real (negritas, viÃ±etas, saltos,
  cÃ³digo y enlace al borrador). Las citas largas se recortan; una instrucciÃ³n de
  mÃ¡s de 300 caracteres se resume como Â«instrucciÃ³n larga; revÃ­sala en el
  borradorÂ».
- **Orden de Pastrana comprobada:** produce **3 encargos y 4 acciones**
  (`crear_cliente`, dos tareas internas y un recordatorio al 0963410409) y **3
  preguntas** (direcciÃ³n, resistencia, precio). **No crea una entrega ni reserva
  mixes** en la agenda operativa: hoy el Cerebro no tiene ese ejecutor.
- **Pruebas:** **734 passed**, 2 warnings; los 3 bloques `<script>` del panel
  en OK.
- **Evidencia:** `.agents/evidencias/gato_formato_pastrana_2026-11-19.txt` y
  `gato_pastrana_2026-11-19.json`.
- **VPS (2026-11-19):** desplegado con respaldo en
  `/root/backup_gato_formato_20261119`; `11 passed` y render con viÃ±etas
  verificado en el servidor. Evidencia:
  `.agents/evidencias/gato_formato_vps_2026-11-19.txt` y
  `gato_formato_render_2026-11-19.txt`.

### 2026-11-19 - Dictado por audio desde Gato y una instrucciÃ³n = un encargo

- **Gato ya tiene micrÃ³fono:** el compositor muestra un botÃ³n para grabar una
  nota de voz. El audio se transcribe con `app/voz` (Groq), **la transcripciÃ³n
  se pinta en el hilo** y el texto se entrega al Cerebro con `modo=dictado`.
  Escribir en Gato sigue siendo una consulta normal.
- **Caso Jack Sparrow corregido:** Â«Dame preparando una entrega de 25 m3 â€¦
  confÃ­rmame con el chofer y con JulioÂ» pasÃ³ de **3 encargos, 0 acciones y 7
  preguntas** a **1 encargo, 1 tarea interna y 3 preguntas**. La tarea queda
  asignada a **Â«chofer y JulioÂ»** y la instrucciÃ³n conserva la frase completa.
- **Por quÃ© pasaba:** el extractor contaba cada destinatario de una misma frase
  como un encargo distinto. Ahora una frase que solo confirma o coordina se une
  al encargo anterior; el compilador conserva los dos destinatarios.
- **Pruebas:** **732 passed**, 2 warnings (5 nuevas en
  `test_v226_gato_audio_encargos.py`); sintaxis de los 3 bloques `<script>` del
  panel en OK.
- **Evidencia:** `.agents/evidencias/gato_audio_2026-11-19.txt`,
  `gato_audio_dictado_2026-11-19.json`, `gato_jack_sparrow_2026-11-19.json`,
  `pytest_gato_audio_2026-11-19.txt`.
- **VPS (2026-11-19):** desplegado con respaldo en
  `/root/backup_gato_audio_20261119`; `19 passed` en el servidor y audio real
  `HTTP 200` con `estado=OK`. Evidencia:
  `.agents/evidencias/gato_audio_vps_2026-11-19.txt`.

### 2026-11-19 - H1 cerrado: nÃºcleo comercial completo con los tres orÃ­genes

- **QuÃ© cambiÃ³:** el mÃ³dulo comercial ya no depende del canal. Panel, Gato
  interno y el webhook de WhatsApp entran por `/api/v1/comercial/*`; **el origen
  lo fija el servidor** y el cuerpo no lo acepta (422 si se intenta).
- **Dos hechos separados:** `POST /leads/{id}/respuesta` (la empresa respondiÃ³,
  nace el `LEAD`) y `POST /leads/{id}/mensaje` (el lead escribiÃ³, aplica
  intenciÃ³n). Un `CAIDO`/`EN_ESPERA` **revive a `LEAD`** con evento y sin
  borrar el historial.
- **Citas:** choque del mismo lead/cliente, mÃ¡quina de estados
  (`SOLICITADA â†’ CONFIRMADA â†’ REALIZADA`, con `CANCELADA`/`REAGENDADA`) y
  auditorÃ­a append-only en `cita_eventos` (migraciÃ³n **097**, aplicada).
- **Panel:** se quitÃ³ el selector de origen y el envÃ­o de `origen`; la agenda
  dejÃ³ de usar `date.today()` y usa `app/tiempo.py`.
- **WhatsApp:** `ComercialWhatsApp` registra el entrante y solicita citas; el
  webhook ya no crea leads ni citas por su cuenta. El parser de citas es Ãºnico
  (`app/comercial/intencion.py`) para Gato y WhatsApp.
- **Verificado:** `pytest` **727 passed** (14 nuevas en
  `test_v225_h1_cierre.py`); `scripts/h1_comercial_check.py` â†’
  `[H1 COMERCIAL: OK]` con las tres orÃ­genes, revivir, choque y auditorÃ­a;
  candado del Hito 3 â†’ `[CANDADO CERRADO EN SANDBOX]`.
- **Evidencia:** `.agents/evidencias/pytest_h1_cierre_2026-11-19.txt`,
  `h1_comercial_check_2026-11-19.txt`, `hito3_lock_2026-11-19.txt`.
- **VPS (2026-11-19):** respaldo en `/root/backup_h1_20261119` y
  `/root/backups/horminor_pre_h1_20261119.sql.gz`; migraciÃ³n **097** aplicada;
  imagen reconstruida y servicio sano. Verificado allÃ­: **26 passed** (pruebas
  H1), `[H1 COMERCIAL: OK]`, `/api/v1/comercial/hoy` y `/panel` 200. El candado
  del Hito 3 corriÃ³ en modo producciÃ³n: 30 verificaciones OK y solo difiere en
  `modo=PRODUCCION` frente al SANDBOX esperado. Se limpiÃ³ el residuo de prueba
  del candado. Evidencia: `.agents/evidencias/h1_vps_2026-11-19.txt`.
- **Bloqueo:** nada tÃ©cnico. Falta confirmar una cita con datos reales de Julio.
- **DecisiÃ³n abierta:** `EN_ESPERA(PRECIO)` sin fecha de recontacto mientras
  `leads.recontacto_dias` sea `NULL`; no se inventÃ³ plazo.

### 2026-11-18 - Chat en vivo: el espejo avisa al panel en segundos

- **QuÃ© cambiÃ³:** el Chat del expediente ya no espera el sondeo de 15 s. El
  espejo publica un aviso (`BusEventos`) cuando importa un mensaje, cuando el
  webhook adelanta su estado y cuando termina una sincronizaciÃ³n; el panel lo
  recibe por **SSE** (`GET /api/v1/whatsapp/espejo/eventos`) y refresca el hilo
  abierto en menos de un segundo.
- **Permisos:** `EventSource` no manda cabeceras, asÃ­ que el perfil simulado va
  por `?usuario=`; el mÃ³dulo se valida igual y el aviso solo lleva
  identificadores, nunca el texto.
- **Respaldo:** el sondeo de 15 s sigue activo por si la conexiÃ³n en vivo se
  cae.
- **Bug corregido en la prueba:** `enviado_at` viajaba como `datetime` y
  `json.dumps` cerraba el stream; ahora va en ISO-8601 y `_sse` usa
  `default=str`.
- **Verificado:** `curl` recibe `listo` y luego el `mensaje` del webhook real
  con el nÃºmero autorizado; en el navegador el hilo pasa de 14 a 15 mensajes
  **sin pulsar Sincronizar** y el texto aparece en **462 ms**; panel sin errores
  de sintaxis (`bloques=3 errores=0`); `674 passed`. Evidencia:
  `.agents/evidencias/sse_chat_vivo_2026-11-18.txt`.
- **VPS (2026-11-18):** desplegado con parche quirÃºrgico sobre el linaje que
  corre allÃ­ (`0cfa9fc`): `BusEventos` en `main.py`, `usuario` opcional en
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
- **Se guarda por cliente** en `clientes/<cliente>_<id>/â€¦` dentro de
  `media_dir`, con fila en `media_assets` y `media_id` en el mensaje.
- **Verificado con envÃ­o real** desde el celular: imagen (69 KB), audio (4 KB)
  y video (6 MB) descargados y visibles en el chat del expediente.
- **Un fallo de media no pierde el texto** del mensaje.
- **Pendiente:** enviar multimedia desde el CRM (`sendMedia` de Evolution) y
  conectar Bunny al mismo esquema de carpetas.

### 2026-11-18 - Por quÃ© no llegaba al CRM (y nÃºmero nuevo de prueba)

- **Causa real:** la sesiÃ³n de WhatsApp estaba **sin poder descifrar** mensajes
  (`SessionError: No matching sessions found` en chats `@lid`, `stream:error
  503`). Los mensajes no entraban ni a Evolution. Se reparÃ³ **revincando el
  dispositivo con QR** (sin tocar el contenedor compartido). DespuÃ©s:
  `state: open` y **0 errores**.
- **Segundo defecto:** WhatsApp omite `remoteJidAlt` en muchos `@lid`; el
  espejo ahora **aprende el telÃ©fono del historial de Evolution** y lo registra
  como alias. Sin dato, el mensaje sigue pendiente (no se inventa identidad).
- **Regla de historial (migraciÃ³n 095):** la sincronizaciÃ³n solo copia desde el
  **alta del cliente** (`whatsapp_espejo_numeros.desde`, configurable). Se
  limpiÃ³ el exceso: Abelito pasÃ³ de **1.807 a 1** mensaje.
- **NÃºmero de prueba:** **0967491847** autorizado en local y VPS; Alejandra
  desactivada (tenÃ­a otra automatizaciÃ³n).
- **Interfaz:** el chat de la carpeta tiene **altura fija de 520 px** y solo
  desplaza la lista de mensajes.
- **Prueba real:** un mensaje enviado **desde el celular del cliente** al
  0967491847 aparece en el chat del CRM como saliente, junto con los entrantes.
- **Pruebas:** `660 passed`.
- **Pendiente:** descargar multimedia y subirla a Bunny por cliente (W1â€“W3).

### 2026-11-17 - Espejo v9.7 desplegado en el VPS (conversaciÃ³n real)

- **QuÃ© se logrÃ³:** la pestaÃ±a **Chat** del expediente **Alejandra** muestra la
  conversaciÃ³n real de WhatsApp del nÃºmero autorizado `+593 98 696 2872`
  directamente en el VPS. Historial de 3 mensajes importado una sola vez, en
  orden y con estados reales.
- **EnvÃ­o real desde el CRM:** el texto sale por Evolution con el cliente propio
  del espejo, sin apagar el switch SANDBOX global ni activar el bot informativo.
  LlegÃ³ al telÃ©fono.
- **Webhook en vivo:** `MESSAGES_UPDATE` suscrito; entraron en tiempo real el
  texto "probando" y una imagen, guardados sin duplicar.
- **Correcciones mÃ­nimas:** `API_PORT` 8010â†’8012 (Caddy), `extra_hosts`
  `host.docker.internal:host-gateway`, y normalizaciÃ³n del estado de envÃ­o
  (`PENDING`â†’`PENDIENTE`) que causaba un 500 despuÃ©s de enviar.
- **Bloqueo:** el **entrante** desde el telÃ©fono de Alejandra nunca llegÃ³ a
  Evolution (ni por PN ni por su LID `153459886145727@lid`). No es un descarte
  del espejo.
- **Pruebas:** `655 passed`; archivo del espejo `32 passed`.
- **Evidencia:** `.agents/evidencias/espejo_v97_vps_2026-11-17.txt`.
- **Alcance aÃ±adido por Julio:** recibir **audio, imagen, video y documento**, y
  acumular la media de cada cliente en su **carpeta independiente en Bunny.net**
  (`.agents/tareas/PENDIENTES.md` Â§6, W1â€“W6). AÃºn no implementado.
- **Intacto:** bot informativo, Cerebro, Gato, voz y demÃ¡s nÃºmeros.

### 2026-11-16 - CorrecciÃ³n de revocaciÃ³n y audio de DÃ­az Sur

- **Defecto:** `dictado_revocado` comparaba Â«mejor noÂ» como subcadena y lo
  encontraba dentro de Â«mejor nos abastecemosÂ». El audio real terminaba en
  `SIN_ACCIONES`.
- **CorrecciÃ³n:** las marcas se leen como palabras completas y la revocaciÃ³n se
  aplica al encargo donde aparece; solo Â«no hagas nadaÂ» corta el dictado
  completo. Sin cambios en dinero, permisos ni confirmaciÃ³n.
- **Pruebas:** 25/25 en `test_v92_adversarial.py` (3 nuevas) y **623/623** en la
  suite del CRM.
- **Audio de 122 s:** transcripciÃ³n `37deb787-d140-44fb-80e4-078057dc34ca`.
  Antes `SIN_ACCIONES`; ahora `REQUIERE_ACLARACION` con **2 encargos**,
  **1 acciÃ³n** (`crear_cliente`) y 4 preguntas. Borrador
  `e133755d-db43-4257-9a50-c9dd8b1e325d`.
- **LÃ­mite real:** no produce todavÃ­a la cotizaciÃ³n completa porque falta la
  direcciÃ³n de la obra y el precio; no se registrÃ³ dinero ni se enviÃ³ nada.
- **Documentos:** `docs/CORRECCION_REVOCACION_DIAZ_SUR.md`, Manual Vivo v1.7 y
  Continuidad v1.5.
- **Intacto:** router `router-1.7` congelado, Gato desconectado, sin interfaces
  nuevas.

### 2026-11-16 - Cierre de la fase del router conversacional (laboratorio)

- **DecisiÃ³n:** la fase se cierra con `router-1.7`; no se amplÃ­a la arquitectura
  ni se buscan mÃ¡s soluciones. Los errores se corrigen con la caja de respuesta
  y la traza existentes.
- **QuÃ© es:** prototipo aislado en `experiments/router_horminor/` (puerto 8055).
  Interpreta un dictado, separa encargos, propone responsable, pide aclaraciones,
  recibe correcciones y entrega un plan. **No estÃ¡ conectado al CRM.**
- **Pruebas:** 21/21 del router (`tests_core`) y 620/620 del CRM
  (`pytest /app/tests`). Sin regresiones.
- **Documentos:** `docs/ROUTER_CONVERSACIONAL_CIERRE.md` (componentes, flujo,
  lÃ­mites), Manual Vivo Â§3.5 y Â§4, `docs/CONTINUIDAD_CEREBRO.md` v1.4 y
  `docs/AUDITORIA_PRUEBAS_MANUALES_2026-11-16.md`.
- **Backlog:** evaluar Jev (TypeSafe AI) como clasificador o verificador de
  intenciones. Sin fecha, sin integraciÃ³n y sin cambios de cÃ³digo.
- **Siguiente paso:** autorizar el arreglo de `dictado_revocado` en
  `app/cerebro/compilador.py` (detecta Â«mejor noÂ» dentro de Â«mejor nos
  abastecemosÂ») y volver a pasar el audio real de 122 s por el panel.

### 2026-11-16 - Lenguaje natural, duda acotada y audio (v8.6)

- **Caso real auditado (sin ordinales):** Â«que secretarÃ­a revise los despachosâ€¦
  hay que llamar al ingeniero Mauricioâ€¦ y el colegio Central, creo que eran
  treinta metros de hormigÃ³n de 240, que me confirmen las medidasÂ». Antes: un
  solo encargo con acciones mezcladas. Ahora: **tres encargos** separados.
- **SegmentaciÃ³n:** el extractor (prompt **cerebro-v7**) numera cada encargo por
  cambio de asunto, destinatario o acciÃ³n; `asignar` valida y renumera; los
  ordinales quedan como respaldo. Si no separÃ³ y hay dos `tarea.mensaje`, el
  compilador pregunta (`encargo.division`) en vez de agrupar.
- **Duda acotada:** `_ajustar_incertidumbre` ata la duda al dato mÃ¡s cercano.
  Â«Creo que eran 30 mÂ³ de 240Â» â†’ volumen `TENTATIVO` con pregunta; resistencia
  `EXTRAIDO` sin pregunta redundante. TambiÃ©n cubre cliente y fecha.
- **Nombres visibles:** Â«Acciones ejecutadasÂ» (borrador) frente a Â«Trabajo
  realizadoÂ» (tarea resuelta); la confirmaciÃ³n interna dice que la tarea quedÃ³
  **NOTIFICADA** y que el trabajo no estÃ¡ hecho.
- **Audio:** WAV con voz sintÃ©tica es-MX (Sabina) â†’ STT real de Groq (18,3 s,
  transcripciÃ³n correcta) â†’ interpretaciÃ³n con 3 encargos y la duda en el
  volumen. **No es una grabaciÃ³n humana**; queda pendiente medir con voz real y
  ruido de planta.
- **Suite:** **620 passed** (10 nuevas en `test_v96_natural.py`); Hito 3 â†’
  `[CANDADO CERRADO EN SANDBOX]`.
- **Evidencia:** `.agents/evidencias/cerebro_audio_natural_2026-11-16.txt`
  (+ `.wav`, STT e interpretaciÃ³n en JSON).
- **Manual Vivo v1.5:** tÃ©rmino *Duda asociada al dato*; *Encargo* actualizado.
- **WhatsApp interno:** `docs/WHATSAPP_INTERNO_IMPLEMENTACION.md` con la
  secuencia 0â€“7, dependencias verificadas y compuertas. No implementado.

### 2026-11-16 - Encargos independientes en un dictado (v8.5)

- **Caso real auditado.** Un dictado con tres asuntos (revisar medidas de una
  cotizaciÃ³n, recordatorio al ingeniero Mauricio, revisar despachos). El motor
  anterior lo colapsaba en **una** acciÃ³n, perdÃ­a el tercer encargo y convertÃ­a
  el recordatorio externo en tarea interna por la palabra Â«secretarÃ­aÂ».
- **MigraciÃ³n 092:** `encargos_json` en el borrador, `encargo` en ejecuciones y
  correcciones, y `cerebro_encargos_decisiones` append-only para cancelaciones.
- **SegmentaciÃ³n determinÃ­stica** (`app/cerebro/encargos.py`) por ordinales
  (Â«primero, segundo, tercero, por Ãºltimo, finalmenteÂ»); el preÃ¡mbulo no se
  compila. Sin marcas, un solo encargo y el comportamiento anterior.
- **CompilaciÃ³n por encargo:** cada asunto se compila con **su propio texto**;
  un tramo con rol interno y sin hechos se conserva como tarea interna copiando
  el tramo (sin redactar).
- **Operaciones:** correcciÃ³n dirigida (clave repetida â†’ `ENCARGO_AMBIGUO`),
  cancelaciÃ³n con motivo (`ENCARGO_CANCELADO` al confirmar), cancelaciÃ³n real de
  un recordatorio PENDIENTE y aviso si ya se enviÃ³.
- **Cifras:** las cifras dictadas del encargo se pasan como `cifras_autorizadas`
  a la guarda del mensaje: un anticipo citado ya no se pierde, y un nÃºmero que
  nadie dijo sigue bloqueado.
- **Prueba en vivo:** A corregido a 35 mÂ³ (v2, sin ejecutar), B cancelado (sin
  recordatorio), C confirmado una sola vez (tarea interna); repetir no duplica.
- **Suite:** **610 passed** (9 nuevas en `test_v95_encargos.py`); Hito 3 â†’
  `[CANDADO CERRADO EN SANDBOX]`.
- **Evidencia:** `.agents/evidencias/cerebro_encargos_2026-11-16.txt`
  (`ENCARGOS: OK â€” tres asuntos independientes, sin mezcla`).
- **Manual Vivo v1.4:** tÃ©rminos *Encargo* y *CancelaciÃ³n de un encargo*.

### 2026-11-16 - ConservaciÃ³n de instrucciones (v8.4)

- **Caso real auditado.** Audio espontÃ¡neo en `/panel/cerebro`: anticipo de USD
  17.000, 250 mÂ³ FC-240, ingeniero Julio Cartuche, rectificaciÃ³n Â«la cotizaciÃ³n,
  no la cotizaciÃ³n, el recordatorio del pagoÂ», entrega contra pago, plazo de dos
  meses y encargo al expediente. El borrador guardado perdiÃ³ el plazo, la
  condiciÃ³n de pago y el expediente: la suite verde no lo detectaba.
- **MigraciÃ³n 091:** `cerebro_borradores.condiciones_json` (append-only,
  protegida por el trigger ampliado). No se editÃ³ ninguna migraciÃ³n aplicada.
- **Compilador:** `Condicion` con cita; detecciÃ³n determinÃ­stica de
  `entrega.plazo`, `entrega.contra_pago` y `expediente.completar`; el encargo al
  expediente crea tarea interna para secretarÃ­a. El plazo ya no depende de que
  la cotizaciÃ³n se pueda armar.
- **Recordatorio:** se separan `instruccion` (lo dictado) y `mensaje` (lo que se
  envÃ­a). Si la frase describe el encargo, `mensaje_por_confirmar` exige el
  texto al confirmar; si no hay hora, `programado_inferido` exige aceptar el
  envÃ­o inmediato. Guardas 422 `MENSAJE_POR_CONFIRMAR` y
  `CONFIRMAR_ENVIO_INMEDIATO`.
- **Dinero:** Â«el pago que tiene que hacernosÂ» ya no se registra como Â«no
  recibidoÂ»: queda `INFERIDO` y el resumen dice Â«sin ingreso confirmadoÂ».
- **Secuencia verificada (G):** el recordatorio se creÃ³ en la misma peticiÃ³n de
  confirmaciÃ³n (00:21:46), 19 s despuÃ©s del borrador (00:21:27); no se programÃ³
  antes de aprobar. La confusiÃ³n era de etiqueta: el borrador seguÃ­a en
  `REQUIERE_ACLARACION` y ahora la respuesta lo dice (`confirmado_parcial`).
- **Hallazgo extra:** al recompilar, un texto podÃ­a rechazarse por compararse
  contra el texto normalizado (Â«2 mesesÂ») en vez de la cita cruda (Â«dos
  mesesÂ»). Corregido en `validar_hecho`.
- **Suite:** **601 passed** (15 nuevas en `test_v94_conservacion.py`); Hito 3 â†’
  `[CANDADO CERRADO EN SANDBOX]`.
- **Evidencia:** `.agents/evidencias/cerebro_conservacion_2026-11-16.txt`
  (matriz 10/10: `CONSERVACION: OK`).
- **Manual Vivo v1.3:** tÃ©rminos *CondiciÃ³n conservada*, *Mensaje autorizado del
  recordatorio* e *Ingreso sin confirmar*.

### 2026-11-16 - VerificaciÃ³n de prioridad 1 (sin tocar cÃ³digo)

- **Contenedores:** `core-api` healthy, `core-api-clone`, `postgres` y `redis`
  arriba. `/health` â†’ `ok`, base en 1,38 ms.
- **Migraciones:** Â«Sin migraciones pendientesÂ»; **085â€“090** aplicadas (090 el
  15/11 a las 23:00). La base tiene **37 migraciones, 57 tablas y 11 vistas**,
  igual que esta ficha.
- **Suite:** **586 passed**, 1 warning, **exit 0**.
- **Candados:** Hito 3 â†’ `[CANDADO CERRADO EN SANDBOX]`; Hito 1 â†’
  `[CANDADO CERRADO]`.
- **CÃ³digo corriendo = cÃ³digo en disco:** SHA-256 idÃ©ntico en `main.py`,
  `compilador.py`, `revision.py`, `panel.html` y `pipeline.py`. `app/` no estÃ¡
  montado: se copia en el build, asÃ­ que la imagen vigente saliÃ³ de este Ã¡rbol.
- **Panel:** `/panel` 200 y `/panel/cerebro` 200.
- **Centinela:** `WARN`, `SANDBOX`, `DETERMINISTIC_FALLBACK`; 12 chequeos
  (**9 OK / 2 WARN / 1 NO_CONFIGURADO**). WARN: caja del 15/11 sin cierre y un
  `ERROR` en 24 h; NO_CONFIGURADO: umbral de merma de cemento.
- **Hallazgo:** `scripts/hito3_lock_test.py` limpia **al inicio**, no al final:
  deja Ã³rdenes demo y un `ERROR` (`M1_WHATSAPP`, reclamo del Â«Cliente Prueba
  Hito 3Â») que hace que el Centinela reporte WARN hasta la corrida siguiente. No
  se corrigiÃ³: cambiar un candado cerrado exige aprobaciÃ³n y volver a correr la
  suite.
- **Punto de restauraciÃ³n:** se versionÃ³ el trabajo acumulado desde el commit
  `7fade4a` (2026-11-13), que no incluÃ­a v8.2 ni el Cerebro (084â€“090), en dos
  commits: **`5c4b460`** (v8.2, migraciÃ³n 084 y servicios compartidos) y
  **`67e18ff`** (v8.3, Cerebro y Voz con 085â€“090, docs y `.agents`).
- Evidencia: `.agents/evidencias/verificacion_prioridad1_2026-11-16.txt`.

### 2026-11-15 - Caso JoaquÃ­n: telÃ©fono, hora y conflicto de identidad

- El tip de Julio quedÃ³ implementado: un `09â€¦` de 10 dÃ­gitos dictado en grupos
  (`0965 555 555`) se une a `0965555555`. Si el LLM no lo captura, el backend
  lo propone como `INFERIDO` y el compilador pregunta Â«Â¿El telÃ©fono del cliente
  esâ€¦?Â». Un hecho inferido nunca resuelve identidad por sÃ­ solo.
- Â«A las 6 de la maÃ±anaÂ» ya no produce `fecha_entrega = hoy`: se guarda
  `cotizacion.hora_entrega = 06:00` y la fecha tentativa queda nula. El
  compilador revisa otra vez que la cita sostenga una fecha.
- El caso real revelÃ³ que el telÃ©fono ya estaba registrado a nombre de otro
  cliente de prueba (`Palo Velez`): ahora se pregunta Â«Â¿Es el mismo cliente?Â»
  en vez de registrar el abono en la ficha equivocada.
- `pytest` â†’ **497 passed**; Hito 3 â†’ `[CANDADO CERRADO EN SANDBOX]`.
- Evidencia: `.agents/evidencias/cerebro_joaquin_2026-11-15.txt`.

### 2026-11-14 - Laboratorio del Cerebro en el panel (prueba manual)

- `GET /panel/cerebro` sirve una pÃ¡gina de pruebas (texto o audio) y el sidebar
  gana **Â«Cerebro Â· voz BETAÂ»**, visible solo con el mÃ³dulo `cerebro`.
- Prueba desde la UI: 12 hechos con cita, 4 acciones, 1 con doble confirmaciÃ³n,
  3.2 s, cero errores de consola; `pytest` **482 passed**.
- Se dejaron `voz.enabled` y `cerebro.enabled` en `true` para la prueba local.
- Evidencia: `.agents/evidencias/lab_cerebro_2026-11-14.txt`.

### 2026-11-14 - Cerebro y Voz: de audio a borrador (Groq + DeepSeek)

- `app/voz/proveedores/groq.py`: Whisper con `verbose_json`, palabras y tiempos;
  confianza por segmento (`exp(avg_logprob)`) como proxy, no calibrada.
- `app/cerebro/sobre.py`, `extractor.py`, `router.py`: texto o transcripciÃ³n â†’
  sobre validado â†’ borrador persistido. MigraciÃ³n **086** agrega
  `texto_directo` para el texto pegado.
- Prueba en vivo: audio sintÃ©tico de 11,8 s â†’ transcripciÃ³n (el STT confundiÃ³ la
  cÃ©dula) â†’ el LLM intentÃ³ completarla â†’ el verificador **la descartÃ³** con nota
  Â«el numero 1710034065 no coincide con el audioÂ»; el borrador siguiÃ³ sin
  cÃ©dula y con 3 acciones.
- Bug corregido en `httpx` 0.28: `data` como lista de tuplas producÃ­a un stream
  sÃ­ncrono; se usa diccionario con lista en `timestamp_granularities[]`.
- `pytest` â†’ **482 passed** (7 de Groq y 5 del extractor). Evidencia:
  `.agents/evidencias/fase2_audio_groq_2026-11-14.txt` y
  `caso_voz_draft_2026-11-14.json`.

### 2026-11-14 â€” Cerebro y Voz, Fase 2: hechos citados y compilador

- `app/cerebro/hechos.py`: `HechoCitado` con cita, texto que sostiene, span,
  ventana, hablante, confianza y `checksum_valido`; `validar_hecho` rechaza
  valores que no estÃ¡n en la cita.
- `app/cerebro/compilador.py`: hechos â†’ borrador con invariantes. Caso A:
  4 acciones ordenadas (cliente â†’ cotizaciÃ³n â†’ abono â†’ envÃ­o); Caso B: abono +
  traslado con dependencia y doble confirmaciÃ³n; Caso C: `SIN_ACCIONES`.
- Reglas probadas: cÃ©dula invÃ¡lida pregunta; precio `PROVISIONAL` bloquea envÃ­o
  fuera de SANDBOX; precio de otro rol se ignora; faltantes â†’ mÃ¡ximo 3
  preguntas; saldo de caja insuficiente bloquea el traslado; rol sin caja no
  puede registrar dinero.
- `pytest` â†’ **469 passed** (14 nuevos). Evidencia:
  `.agents/evidencias/fase2_hechos_compilador_2026-11-14.txt`.

### 2026-11-14 â€” Cerebro y Voz, Fase 2: mapa de alineaciÃ³n

- `normalizar_con_mapa` devuelve cada token con su span en el texto crudo y su
  tipo (`NUMERO`, `UNIDAD`, `MONEDA`, `ALIAS`â€¦).
- `localizar_palabras`, `alinear_con_palabras` y `alinear_secuencias` atan los
  datos a las palabras del STT, su ventana de milisegundos y su confianza.
- Una cÃ©dula dictada en dos tramos queda como un solo dato; los conectores
  (Â«que mÃ¡sÂ») no bajan la confianza. Sin palabras del STT, el dato queda sin
  ventana y no se puede confirmar con un clic.
- `normalizar_texto` mantiene su contrato y ahora une los tramos en el texto.
- `pytest` â†’ **455 passed** (10 nuevos); `/health` â†’ 200.
- Evidencia: `.agents/evidencias/fase2_alineacion_2026-11-14.txt`.

### 2026-11-14 â€” Cerebro y Voz, Fase 1: migraciÃ³n 085 e ingesta de audio

- MigraciÃ³n **085** aplicada: `voz_ingestas`, `voz_ingesta_media_links`,
  `voz_trabajos_stt`, `voz_transcripciones`, `cerebro_extracciones`,
  `cerebro_borradores`, `cerebro_ejecuciones`, `client_facts`,
  `client_fact_supersedes` y `whatsapp_mineria_cursores`; settings
  (`voz.enabled=false`, topes en `null`), mÃ³dulos ACL `voz`/`cerebro` y
  `fecha/hora_entrega_tentativa` en cotizaciones.
- `app/voz/ingesta.py`: valida MIME/tamaÃ±o, hashea, guarda en
  `inbox_voz/<fecha>/`, crea ingesta y trabajo, y **reutiliza** la ingesta si
  el mismo audio se reenvÃ­a (nuevo intento, sin duplicar el binario).
- `app/voz/stt.py`: protocolo `ProveedorSTT` con degradaciÃ³n
  `DEGRADADO_SIN_CREDENCIAL`; nunca inventa texto.
- `POST /api/v1/voz/transcribir` y `GET /api/v1/voz/ingestas/{id}` con ACL
  `voz` y feature flag apagado por defecto; `voz`/`cerebro` aparecen en el
  checklist de Superadmin.
- Verificado en vivo: 201 con `DEGRADADO_SIN_CREDENCIAL`, un solo archivo,
  tres intentos auditados; el trigger append-only rechaza el `UPDATE`.
- `pytest` â†’ **445 passed**; Hito 3 â†’ `[CANDADO CERRADO EN SANDBOX]`.
- Evidencia: `.agents/evidencias/fase1_voz_2026-11-14.txt`.

### 2026-11-14 â€” Cerebro y Voz: diseÃ±o canÃ³nico, Fase 0 y normalizador es-EC

- `docs/CEREBRO_VOZ_DISENO.md` v1.0: separa `app/voz/` de `app/cerebro/`,
  define 9 tablas, 9 acciones y 4 fases; corrige 16 puntos del diseÃ±o externo
  (tipos UUID, inmutabilidad, reintentos, roles reales, `obra_direccion`,
  `resistencia` como cÃ³digo, cuotas no inventadas).
- Decisiones resueltas: fecha tentativa en `cotizaciones` (`date` + `time`),
  precio desde la receta sin autoenvÃ­o, minerÃ­a bloqueada hasta persistir
  entrantes de WhatsApp.
- **Fase 0 cerrada:** `services/cotizaciones.py` y `services/clients.py`
  concentran el alta; el panel y el Cerebro usan el mismo camino. Verificado en
  vivo: alta de cliente con cÃ©dula, cotizaciÃ³n 6 mÂ³ ($814,20) y PUT a 7 mÂ³
  ($949,90); datos de prueba borrados.
- `app/voz/normalizador_ec.py`: nÃºmeros hablados, cÃ©dulas en tramos con
  conector, telÃ©fonos, `m3`, moneda y ciudades. **No corrige dÃ­gitos**: marca
  `checksum_valido=false` y el borrador pide corroboraciÃ³n.
- `pytest` â†’ **439 passed** (16 nuevos). Evidencia:
  `.agents/evidencias/voz_normalizador_2026-11-14.txt` y
  `fase0_servicios_2026-11-14.txt`.
- Plan de ejecuciÃ³n: `.agents/tareas/2026-11-14_CEREBRO_VOZ.md`.

### 2026-11-14 â€” Cotizaciones v8.2: ubicaciÃ³n de la obra y Sabueso sobre las tarjetas

- **MigraciÃ³n 084** aplicada: `ubicacion_texto`, `ubicacion_lat/lng`,
  `ubicacion_origen`, `ubicacion_solicitada_at`, `ubicacion_recibida_at`;
  CHECKs de origen y rango; `cotizacion_eventos` acepta
  `UBICACION_SOLICITADA` y `UBICACION_RECIBIDA`; plantilla
  `cotizaciones.pedir_ubicacion` en `system_settings`.
- **Tres vÃ­as**: texto libre (`MANUAL`), **Usar mi ubicaciÃ³n** (`GPS`) y pin del
  cliente por WhatsApp (`WHATSAPP`); enlace de mapa pegado (`MAPA`). Sin dato
  queda `NULL` y el PDF imprime `Pin: PENDIENTE`.
- `POST /api/v1/cotizaciones/{id}/pedir-ubicacion` envÃ­a la plantilla al
  telÃ©fono del cliente, sella el pedido y deja `UBICACION_SOLICITADA`; la
  compuerta `_gate_ubicacion` de M1 adjunta el pin a la cotizaciÃ³n abierta mÃ¡s
  reciente sin pin, sella `ubicacion_recibida_at` y responde al cliente.
- Un `PUT` parcial no borra el pin (`model_fields_set` + `CASE WHEN`); la
  referencia escrita por el asesor **no** se pisa con el nombre del pin.
- **PDF** con bloque **UBICACION DE LA OBRA** (DirecciÃ³n, Referencia, Pin con
  origen, Mapa) y recorte a 92 caracteres por lÃ­nea.
- **Sabueso**: `.card` crea contexto de apilamiento por `backdrop-filter`; la
  tarjeta del buscador lleva `.card-buscar-clientes` (`z-index: 6`) y el
  desplegable se dibuja por encima de la tarjeta siguiente. Ficha con nombre,
  constructora, ciudad, telÃ©fono y RUC; navegaciÃ³n con Enter y flechas.
- `pytest` â†’ **423 passed** (18 del archivo `test_v82_ubicacion.py`); Hito 3 â†’
  `[CANDADO CERRADO EN SANDBOX]`.
- Evidencia: `.agents/evidencias/ubicacion_v82_2026-11-14.txt`,
  `cotizacion_v82_pdf_2026-11-14.png`, `sabueso_zindex_v82_2026-11-14.png`.
- Manual actualizado: `docs/COTIZACIONES.md` v8.2 (Â§3.1, Â§3.7, Â§8, Â§12.3).

### 2026-11-13 â€” Dashboard C0â€“C3: capacidad declarada, MRP y cobranza Ãºnica

- `GET /api/v1/dashboard/operacion`: capacidad `min(flota, planta, jornada)`;
  con la semilla actual devuelve `CONFIGURACION_INCONSISTENTE`; cola **404 mÂ³
  sin plan** y **388 mÂ³ sin despachar**.
- `/inventario`: explosiÃ³n MRP + triple lectura. Cemento 3.500 declarado /
  **288 kardex** / cobertura 8,97 %; arena 243,56 corregida; retardante 73,6 L.
- `/cobranza`: documento Ãºnico, factura ficticia excluida, total **55.043,60**;
  exigibilidad 1.085,60 confirmado / 2.171,20 con salida / 52.872,40 sin salir.
- Superadmin: `viajes_max_dia`, `planta_asignada`, `capacidad_plantas`,
  `supuestos_capacidad` y `umbrales_ocupacion` persistidos sin migraciÃ³n.
- `pytest` â†’ **393 passed**. Evidencia:
  `.agents/evidencias/dashboard_c0_c3_2026-11-13.txt`.

### 2026-11-13 â€” Cotizaciones v6.21

- MigraciÃ³n **080** aplicada: `cotizaciones`, `cotizacion_extras`,
  `cotizacion_versiones`, `orden_extras`, `cliente_etiquetas`,
  `concrete_recipes.precio_estado` y settings.
- API: alta, ediciÃ³n (solo `BORRADOR`), detalle, listado, aceptaciÃ³n (etiqueta
  `VENTA`) y conversiÃ³n a orden con `crear_orden`.
- Vista **Cotizaciones** en la columna izquierda: bandeja, detalle, formulario y
  extras globales.
- Permiso `cotizaciones` en el checklist de Superadmin. Julio lo tiene; los
  demÃ¡s perfiles lo reciben cuando Julio lo apruebe.
- **Buscador** `GET /api/v1/cotizaciones?q=`: nombre, apellido, fecha, telÃ©fono,
  nÃºmero de cotizaciÃ³n, obra, cÃ©dula/RUC o razÃ³n social.
- **Respuesta del cliente (migraciÃ³n 081):** compuerta determinÃ­stica en M1.
  ConfirmaciÃ³n explÃ­cita â†’ `ACEPTADA` + etiqueta `VENTA` + evento + aviso, sin
  crear orden. NegociaciÃ³n/rechazo/pregunta â†’ evento + aviso, sin cambiar el
  precio. Varias abiertas â†’ pregunta cuÃ¡l.
- **Alta de cliente y telÃ©fono** desde la cotizaciÃ³n (`+ Nuevo cliente`); el
  telÃ©fono es obligatorio para enviar el PDF y actualiza la ficha.
- **Forma de pago fuera de la cotizaciÃ³n** (migraciÃ³n 082): se define al
  convertir.
- **Enviar por WhatsApp:** PDF generado, archivado en `media_assets` y enviado
  por Evolution o encolado en SANDBOX. La cotizaciÃ³n pasa a `ENVIADA`.
- **Convertir a cliente:** popout con forma de pago, abono y datos de factura;
  crea la orden y guarda `factura_datos` (migraciÃ³n 083).
- `pytest` â†’ **405 passed**. Evidencia:
  `.agents/evidencias/cotizaciones_v621_2026-11-13.txt` y
  `.agents/evidencias/cotizaciones_v622_2026-11-13.txt`.
- Manual actualizado: `docs/MANUAL_DASHBOARD_JULIO.md` Â§9.

### 2026-11-13 â€” Meta comercial y punto de equilibrio

- Meta mensual configurable (`comercial.meta_mensual_m3`): cumplimiento,
  diferencia en mÂ³ y dÃ­as de planta cuando hay capacidad.
- Punto de equilibrio contable (`finanzas.punto_equilibrio`): costos fijos,
  costo variable y precio; `NO_CONFIGURADO` con faltantes si no estÃ¡n.
- Tarjeta â€œMeta y equilibrioâ€ en OperaciÃ³n y 4 campos en Superadmin > Tasas.
- `pytest` â†’ **394 passed**. Evidencia:
  `.agents/evidencias/dashboard_meta_equilibrio_2026-11-13.txt`.
- Manual actualizado: `docs/MANUAL_DASHBOARD_JULIO.md` Â§3.1.1.

### 2026-11-13 â€” Dashboard C5/C6: banner amarillo, 4 ventanas y grÃ¡ficos SVG

- Banner `sec-ventanilla` primero; ventana activa en amarillo sÃ³lido con texto
  oscuro; 4 ventanas (OperaciÃ³n, Inventario vs ventas, Inventario por fechas,
  Cobranza).
- 3 KPI mutables por ventana, 6 grÃ¡ficos SVG nativos (capacidad, despacho,
  resistencia, cobertura, kardex, aging) y bandeja de documentos.
- Presets de cobranza operativos: Todos, Urgencia 7 dÃ­as, Mora, Clientes
  grandes, Sin vencimiento, Cupo excedido, Listo para cobrar.
- Agenda encapsulada en `data-sub-view="agenda"`; deja de ser un nodo huÃ©rfano.
- `pytest` â†’ **394 passed**; navegador sin errores de consola, overflow 0.
- Evidencia: `.agents/evidencias/dashboard_c5_c6_2026-11-13.txt`.
- Manual en borrador: `docs/MANUAL_DASHBOARD_JULIO.md`.

### 2026-11-13 â€” Dashboard operativo en tres pestaÃ±as

- Se eliminÃ³ â€œFiltros de obrasâ€ (planta, resistencia, pago) del panel.
- Tres pestaÃ±as con submenÃº: **OcupaciÃ³n** (por defecto, Ã¡mbar), **Inventario**,
  **Cobranza**; el resumen anual queda comprimido arriba.
- Endpoints nuevos `GET /api/v1/dashboard/inventario` y `/cobranza` con
  `fuente`, `consultado`, `filtros`, `datos` y `vacio`.
- Inventario: CEMENTO, ARENA, RIPIO, RETARDANTE (sin agua), con
  `SIN_FECHA_CONTEO` cuando no hay conteo fÃ­sico.
- Cobranza: cuatro cubos y saldo real por cobrar separado del total documental.
- `pytest` â†’ **386 passed** (7 tests nuevos).
- Verificado en Chromium: 3 pestaÃ±as, 4 tarjetas, 4 cubos, sin errores de consola.
- Evidencia: `.agents/evidencias/dashboard_operativo_2026-11-13.txt`.

### 2026-11-13 â€” Cotizaciones, contratos y mapa de mÃ³dulos

- MigraciÃ³n **079** aplicada en local: `fecha_vencimiento` en `orders` y
  `client_invoices` + vista `v_cobranza_documentos`. Commit `c9e3446`.
- `pytest` â†’ **379 passed**.
- AuditorÃ­a de skills â†’ **APROBADO (179 verificaciones)** con `python
  scripts/auditar_skills.py`; incluye extra global vÃ¡lido y extra con
  `categoria` rechazado.
- `docs/COTIZACIONES.md` v6.20: rubro Ãºnico global de extras, validez 15 dÃ­as,
  envÃ­o por WhatsApp con PDF en la carpeta del cliente, etiqueta `VENTA`.
- `docs/CONTRATOS.md` v6.19: suministro por mÂ³ con equipo y bombeo, mediciÃ³n
  pactada, firma exclusiva de Julio.
- `.agents/MAPA_MODULOS.md`, `.agents/tareas/PENDIENTES.md` y
  `docs/DASHBOARD_OPERATIVO.md` creados.
- `pdf-cotizaciones` â†’ v1.3.0 (contrato `solicitud_cotizacion` 1.3.0).
- Evidencia: `.agents/evidencias/dashboard_cobranza_2026-11-13.txt`.

- **v6.17 desplegada y probada en el VPS (2026-11-13).** Seis commits
  (`7850241` â€¦ `8c6b301`), migraciones **075â€“078** aplicadas y `envio:
  evolution`. EnvÃ­os reales: `PRUEBA-0002.pdf` y un mensaje redactado, ambos al
  0967491847, con `documentMessage` en Evolution. Gato ahora **redacta** el
  mensaje y el backend rechaza cualquier cifra que no estÃ© en la ficha
  (`cifras_de` / `_cifras_permitidas`). Cuatro clientes ficticios con factura en
  el VPS. Fallos corregidos en el camino: `import base64` ausente (ningÃºn
  documento salÃ­a), `modo` decÃ­a SANDBOX por Bunny aunque el canal fuera
  Evolution, telÃ©fono duplicado en la ratificaciÃ³n y pregunta innecesaria por el
  cliente de la factura. `pytest` -> **376 passed**. Evidencia:
  `.agents/evidencias/vps_despliegue_recordatorios_2026-11-12.txt`.

- **VPS + Evolution (2026-11-12).** El CRM quedÃ³ desplegado en Contabo (`/opt/horminor`), clonado con deploy key read-only desde `ObjetivoCesar/horminor-crm`. `core-api` escucha en `127.0.0.1:8012`; Caddy publica solo `https://horminor.178.238.238.158.sslip.io/health` y el webhook de Evolution. El panel se usa por tÃºnel SSH hasta que exista login. Instancia Evolution `horminor` creada con webhook; estado `connecting`, pendiente escanear QR. Ver `docs/DESPLIEGUE_VPS_HORMINOR.md` y `.agents/evidencias/vps_deploy_evolution_2026-11-12.txt`.
- **v6.13.1 cerrada el 2026-11-12.** Gato ya no pierde el hilo: `gato_turnos` (migraciÃ³n 074) guarda cada turno y el endpoint devuelve `conversacion_id`; el widget lo persiste por usuario. El backend pasa los Ãºltimos 8 turnos al LLM, asÃ­ **"descÃ¡rgala"** devuelve el PDF de la factura anterior. La bÃºsqueda de clientes ahora normaliza puntuaciÃ³n ("ing reyes" encuentra "Ing. Reyes"). La factura incluye un enlace `?download=1` y el widget lo pinta como **Descargar archivo**. Evidencia: `.agents/evidencias/gato_memoria_v6131_2026-11-12.txt`; `pytest` -> **342 passed**.
- **v6.13 cerrada el 2026-11-12.** El expediente del cliente estrena la pestaÃ±a **Facturas**: se adjunta un PDF o foto (`client_invoices`, migraciÃ³n 073) y, si se elige una orden, los montos salen de ella; nunca se inventan. La factura de prueba `PRUEBA-0001` quedÃ³ en Ing. Reyes (orden #55, **$43.424,00** con IVA) y estÃ¡ marcada **FICTICIA**. Gato la consulta con `cliente_facturas` y advierte que no es comprobante electrÃ³nico del SRI (fuera de alcance). `pytest` -> **338 passed**; `auditar_skills.py` -> **177 verificaciones**. Evidencia: `.agents/evidencias/facturas_v613_2026-11-12.txt`, `factura_prueba_2026-11-12.pdf`, `panel_v613_facturas_2026-11-12.jpeg`.
- **v6.9 cerrada el 2026-11-11.** El chat del expediente es **espejo de WhatsApp** (canal `WHATSAPP`, aviso de conexion, salientes `PENDIENTE` hasta que Evolution este configurado) y tiene estetica WhatsApp: burbujas con cola, ticks, separadores de dia y menu del clip (Galeria, Camara, Documento, Audio, Ubicacion, Contacto). La multimedia se comprime en el backend (imagenes a WebP, videos a H.264 <=720p/180 s, audio intacto), se guarda en Bunny bajo `clientes/<nombre>_<cedula>/` o en el sandbox local, y se indexa en `media_assets` (migracion 071). `scripts/media_v69_check.py` -> **MEDIA V6.9: OK**; `pytest` -> **291 passed**. Evidencia: `.agents/evidencias/media_v69_check_2026-11-11.txt`, `pytest_v69_2026-11-11.txt`, `panel_v69_chat_2026-11-11.jpeg`, `panel_v69_adjunto_2026-11-11.jpeg`. Decisiones en `docs/WHATSAPP_Y_MEDIA.md`.
- **v6.10 cerrada el 2026-11-12.** La agenda de **Planta, Flota y Kardex** usa como fondo la fotografÃ­a entregada por DirecciÃ³n (`static/brand/fotos/planta-agenda.webp`) con overlay para mantener la lectura. **Banca y Mercado** estrena cabecera con tres cuentas (Pichincha, Guayaquil, Internacional) y sus logos; el detalle sale de `GET /api/v1/dashboard/bancos` (configuraciÃ³n de Empresa), sin inventar nÃºmeros ni saldos. `pytest` -> **295 passed**. Evidencia: `.agents/evidencias/pytest_v610_2026-11-12.txt`, `panel_v610_planta_2026-11-12.jpeg`, `panel_v610_banca_2026-11-12.jpeg`.
- **Bancos â€” traspaso 2026-11-12:** leer **`docs/BANCOS_PENDIENTES.md`**. Resumen: las columnas de tarjeta/detalle estÃ¡n implementadas; **el cierre de caja NO menciona el banco** (agrupa por mÃ©todo y bolsa); las cuentas se configuran hoy solo en **Banca > Editar datos**; `empresa.bot_publico.bank_accounts` estÃ¡ desconectado y no hay Superadmin > Bancos. Siguiente: selector de banco en `dlg-pago`, `bank_account_id` en `payments` y desglose por banco en el cierre.
- **v6.11 cerrada el 2026-11-12.** En **Banca y Mercado** el banco seleccionado se pinta en amarillo y abre un detalle con **saldo contable**, **saldo informado**, entradas, prÃ©stamos y movimientos. La migraciÃ³n `072` crea `bank_accounts` y las cuentas hijas `1102.01/02/03`; el saldo informado se edita desde **Editar datos** (ACL de Finanzas). Los datos reales quedan en `NULL`/cero hasta que Gerencia los cargue; el flujo de ediciÃ³n se probÃ³ y se limpiÃ³. `pytest` -> **296 passed**. Evidencia: `.agents/evidencias/pytest_v611_2026-11-12.txt`, `panel_v611_banca_2026-11-12.jpeg`.
- **Asistente IA â€” propuesta 2026-11-12:** leer **`docs/ASISTENTE_IA_PROPUESTA.md`** y **`docs/ASISTENTE_IA_SKILLS.md`** (Â§8â€“Â§12: PDF independiente, agendas de obras/visitas, auditorÃ­a de precios/costos, bibliotecario). El PDR (Â§3.2) prohÃ­be un chatbot abierto y la decisiÃ³n 14 lo ratifica; la propuesta lo cumple con **function calling sobre un catÃ¡logo fijo de herramientas** (sin SQL libre), verificador determinÃ­stico de cifras, permisos por rol y auditorÃ­a. Dos personas: `INTERNO` (solo CRM, DeepSeek) y `PUBLICO` (info + manos). **Hallazgo:** el precio por mÂ³ es manual y **no** estÃ¡ atado al costo; no existe costeo por receta ni alerta de margen. Skill de operaciÃ³n: `.agents/skills/bibliotecario-datos/SKILL.md`. **No hay cÃ³digo**: faltan las decisiones de Â§12.
- **Skills v7.0 â€” pilares 2026-11-12 (v1.2 arbitrada):** leer **`docs/SKILLS_PILARES_HORMINOR.md`** v1.3 y **`docs/CATALOGO_CONSULTAS.json`** v1.1. EstÃ¡ndar de 5 componentes adaptado (SKILL.md â‰¤ 12.000 caracteres, roles â‰¤ 70 lÃ­neas y una capa por rol, contratos JSON Schema 2020-12), 14 pilares en **6 colas congeladas** y 3 skills completas en `.agents/skills/`: **`pdf-cotizaciones`**, **`banca-mercado`** y **`bibliotecario-datos`**. CatÃ¡logo cerrado: **22 consultas implementadas + 5 propuestas**, con `requeridos` por consulta. Contratos del bibliotecario **v1.4**: **12 parÃ¡metros**, **23 fuentes reales**, **24 `allOf`** (22 ACL+requeridos + 1 whitelist + 1 bloqueo cruzado), ficha escalar con `ficha_id`/`consulta_id` y DECIMAL negativo. `balance`, `resultados`, `banco_detalle` y `salud_sistema` cerrados a `BODEGA`/`SECRETARIA`. Montos como texto decimal y `precio_ref.ficha_id` 1:1 con la ficha de precio. Paquete para Carbon: **`docs/CARBON_ARRANQUE.md`** v1.3. AuditorÃ­a: **`docs/AUDITORIA_SKILLS_CARBON.md`** + `scripts/auditar_skills.py` (177 verificaciones en verde). Siguiente: reconstruir `bibliotecario-datos` con Carbon y auditar la salida.
- **Pilar #1 aprobado (referencia) 2026-11-12:** `bibliotecario-datos` pasa los 10 vectores y el checklist; `scripts/auditar_skills.py` â†’ **177 verificaciones en verde**. Contratos: `consulta.json` v1.4.0 (24 `allOf`), `ficha_dato.json` v1.3.0 y `solicitud_cotizacion.json` v1.2.0. **La entrega de Carbon sigue pendiente.** Punto de retorno: **`docs/CONTINUACION_2026-11-12.md`**.
- **Gato â€” bot interno v2.1 (2026-11-12):** `services/core-api/app/asistente/` con **10 pilares**, **22 consultas conectadas** (0 `NO_CONECTADA`), **ACL desde el catÃ¡logo**, **guarda de cifras** con formato EU/US, negativos, FC-210, cantidades y conteos; estados `OK/VACIO/FALTA_PARAMETRO/ACL/PROPUESTA`; tool calling DeepSeek y **endpoint** `POST /api/v1/asistente/chat` con el rol desde la sesiÃ³n, nunca del body. **Widget "Gato"** visible en `/panel` con estilo WhatsApp (fondo opaco, burbujas, tablas) y fallback a Julio si no hay perfil en "Viendo como". Base ficticia `orminorth_gato_test` + `db/seeds/gato_ficticio.sql`; loop **39 preguntas / 0 errores con DeepSeek real** (`.agents/evidencias/gato_loop_llm_2026-11-12.txt`); **332 tests**. Docs: **`docs/GATO_PROMPT.md`** y **`docs/GATO_CORPUS.md`**. Siguiente: probar el widget con el perfil de SecretarÃ­a y cargar preguntas reales.
- **Tarea para Abel (2026-11-12):** `.agents/tareas/2026-11-12_ABEL.md` â€” conectar Evolution, activar Bunny con token, persistir entrantes, enviar multimedia y cargar cÃ©dula/cuentas. Incluye criterios de aceptaciÃ³n y comandos.
- **v6.8 cerrada el 2026-11-11.** El expediente del cliente estrena la pestana `ðŸ’¬ Chat`: historial en PostgreSQL (`chat_conversaciones` + `chat_mensajes`, migracion 070), API para leer/escribir/marcar leido y buscar, badge de no leidos, burbujas y compositor. La ingesta de WhatsApp es idempotente por `whatsapp_msg_id`. La base real queda con **0 mensajes** (los de prueba se borraron). `scripts/chat_v68_check.py` -> **CHAT V6.8: OK**; `pytest /app/tests` -> **283 passed**. Evidencia: `.agents/evidencias/chat_v68_check_2026-11-11.txt`, `pytest_v68_2026-11-11.txt`, `panel_v68_chat_2026-11-11.jpeg`. Mapa de la base en `docs/BASE_DE_DATOS.md` Â§9.
- **v6.7 cerrada el 2026-11-11.** Carpetas de Clientes estrena boton `Filtros` con contador, panel desplegable y chips de filtros activos; se corrigio el `[hidden]` global que mantenia visibles los campos de fecha. Obras activas usa dos fotografias reales en `static/brand/fotos/` (`mixers-en-planta.jpg` y `mixer-en-descarga-sin-marca.jpg`). `pytest /app/tests` -> **277 passed**. Evidencia: `.agents/evidencias/pytest_v67_2026-11-11.txt`, `panel_v67_filtros_2026-11-11.jpeg`, `panel_v67_fotos_2026-11-11.jpeg`.
- **v6.6 cerrada el 2026-11-09.** Carpetas de Clientes con banner de 4 filtros, buscador Sabueso (tildes, b/v, z/s/c, ll/y, nombre invertido, 7m3, FC-210, #orden, obra/ciudad), filtros combinables, paginacion de 12 y expediente en 3 pestanas. Migracion 069 agrega ciudad/obra frecuente. `docs/tutoriales/` con 7 archivos para el futuro bot. `pytest /app/tests` -> **277 passed**. Evidencia: `.agents/evidencias/pytest_v66_2026-11-09.txt`, `panel_v66_2026-11-09.txt`.`n- **v6.4 cerrada el 2026-11-09.** Superadmin rediseÃ±ado con 4 action cards (`Usuarios y accesos`, `Caja chica y horarios`, `Recetas, flota y precios`, `Tasas y conteo de silos`), 2 tarjetas resumen, modales independientes y selector `Viendo como` con opciÃ³n directa de gestiÃ³n. Se eliminaron los textareas de JSON y los placeholders `null`. `pytest /app/tests` -> **272 passed**. Evidencia: `.agents/evidencias/pytest_v64_2026-11-09.txt`, `panel_v64_2026-11-09.txt`.`n- **v6.2 cerrada el 2026-11-09.** Componente unico `HorminorAgenda` montado en Dashboard, Secretaria y Planta; se elimino el calendario que leia `orders.created_at`; Superadmin edita topes de caja/compra, fondo base y horarios de planta; `panel_users_acl` trae 5 perfiles con checklist y el selector "Viendo como" aplica modulos y solo-lectura. `pytest /app/tests` -> **270 passed**. Evidencia: `.agents/evidencias/pytest_v62_2026-11-09.txt`, `panel_v62_2026-11-09.txt`, `v62_clone_2026-11-09.txt`.`n- **v6.0 cerrada el 2026-11-09.** MigraciÃ³n 067 aplicada a la base real: ventanilla curada (5401/5301/5201 + 1106), tope de caja chica configurable, compras con proveedores y recepciÃ³n, cierre que resta compras en efectivo y agenda real de entregas/mixers. pytest /app/tests -> **265 passed**. Evidencia: .agents/evidencias/pytest_v6_2026-11-09.txt, clone_v6_2026-11-09.txt, panel_v6_2026-11-09.txt.
- **UX de SecretarÃƒÂ­a ajustada el 2026-11-09.** La vista abre con acciones
  visibles (cobrar/abonar, gasto, nueva orden) y el orden por tarea: acciones Ã¢â€ â€™
  resumen + cierre Ã¢â€ â€™ cartera Ã¢â€ â€™ ÃƒÂ³rdenes. Cartera con buscador y cobro por fila.
  `pytest /app/tests` Ã¢â€ â€™ **247 passed**, consola del navegador sin errores.
  Evidencia: `.agents/evidencias/pytest_ux_secretaria_2026-11-09.txt`.
- **v5.1: panel, Superadmin y backup el 2026-11-09.** El panel de SecretarÃƒÂ­a
  registra cobros/abonos y gastos contra `/api/v1/panel/pagos`; Superadmin
  edita `finanzas.parametros_contables` y registra el conteo fÃƒÂ­sico; el backup
  diario `scripts/backup_db.sh` verifica el dump con `pg_restore --list`.
  `pytest /app/tests` Ã¢â€ â€™ **247 passed**; `http_gate_v44_check.py` Ã¢â€ â€™ **OK** con
  12 verificaciones y `ROLLBACK` en 17 tablas.
- **Custodio v4.4.0 con HTTP cerrado el 2026-11-09.** `app/http_gate/` expone
  `POST /api/v1/custodio/mutations`, `/queries`, `/witness` y
  `GET /catalog` con tokens de servicio; `POST /api/v1/secretaria/pagos`
  registra `COBRO`, `GASTO_CAJA_CHICA` y `GASTO_BANCARIO`, valida saldo,
  separa abono/anticipo y es idempotente. `scripts/http_gate_v44_check.py`
  contra `orminorth_v43` Ã¢â€ â€™ **HTTP GATE V4.4: OK** con 10 verificaciones y
  `ROLLBACK` en 17 tablas. Evidencia:
  `.agents/evidencias/http_gate_v44_check_2026-11-09.txt`.
- `scripts/custodio_v43_check.py` Ã¢â€ â€™ **CUSTODIO V4.4: OK** con 30 solicitudes
  (21 ACCEPT, 6 REJECT, 3 PENDING), 8 testigos, 4 aprobaciones y 9 consultas;
  incluye anulaciÃƒÂ³n con `CONVERTIR_A_ANTICIPO_CLIENTE`,
  `DEVOLVER_DINERO_CAJA_O_BANCO` y anticipo 1103/2102. Evidencia:
  `.agents/evidencias/custodio_v44_check_2026-11-09.txt`.
- `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` Ã¢â€ â€™ **242 passed**, exit 0 (`.agents/evidencias/pytest_http_v44_2026-11-09.txt`).
- Hito 1 Ã¢â€ â€™ `[CANDADO CERRADO]` y Hito 3 Ã¢â€ â€™ `[CANDADO CERRADO EN SANDBOX]`
  (`.agents/evidencias/hito1_lock_http_v44_2026-11-09.txt`,
  `hito3_lock_http_v44_2026-11-09.txt`).
- Base real: 13 migraciones, ÃƒÂ³rdenes #9/#55/#56/#57, cartera
  **55,043.60 / 2 clientes / fiado 55,043.60**, `payments=0`, 249 movimientos
  y materiales intactos. Evidencia:
  `.agents/evidencias/base_real_v44_final_2026-11-09.txt`.
- **Custodio v4.3 implementado y verificado el 2026-11-09.** `app/custodio/`
  (`contracts.py`, `ledger.py`, `catalog_hygiene.py`, `witness.py`, `gate.py`)
  cubre **14/14 intents de mutaciÃƒÂ³n, 9 consultas, 8 solicitudes de testigo y
  2 aprobaciones**. `scripts/custodio_v43_check.py` contra `orminorth_v43` Ã¢â€ â€™
  **CUSTODIO V4.3: OK** con 23 solicitudes (17 ACCEPT, 4 REJECT, 2 PENDING),
  asientos balanceados, cartera, compras, depreciaciÃƒÂ³n, prÃƒÂ©stamo, anulaciÃƒÂ³n y
  catÃƒÂ¡logo contable; **ROLLBACK verificado en 17 tablas**. Evidencia:
  `.agents/evidencias/custodio_v43_check_2026-11-09.txt`.
- `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` Ã¢â€ â€™ **223 passed**, exit 0 (`.agents/evidencias/pytest_custodio_v43_2026-11-09.txt`), incluidos 26 tests puros del Custodio.
- Hito 1 Ã¢â€ â€™ `[CANDADO CERRADO]` y Hito 3 Ã¢â€ â€™ `[CANDADO CERRADO EN SANDBOX]`
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
  idempotente por `ANULA:<id>`; las correcciones fÃƒÂ­sicas usan `AJUSTE`.
  `scripts/kardex_v43_check.py` contra `orminorth_v43` Ã¢â€ â€™
  **KARDEX V4.3: OK** (promedio 9.1000, snapshot, reversa de 140 a 150,
  rechazo de anulaciÃƒÂ³n fÃƒÂ­sica y `ROLLBACK` total).
- `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` Ã¢â€ â€™ **197 passed**, exit 0 (`.agents/evidencias/pytest_kardex_v43_2026-11-09.txt`).
- Hito 1 Ã¢â€ â€™ `[CANDADO CERRADO]`, 235 movimientos de kardex (`.agents/evidencias/hito1_lock_kardex_v43_2026-11-09.txt`).
- Hito 3 Ã¢â€ â€™ `[CANDADO CERRADO EN SANDBOX]` (`.agents/evidencias/hito3_lock_kardex_v43_2026-11-09.txt`).
- **Refactor v4.3 aplicado y verificado el 2026-11-09.** `crear_orden` lee
  `finanzas.iva_default_aplica` y el `iva_pct` de la receta, escribe
  `aplica_iva`/`iva_pct`/`iva_monto`/`total_con_iva` e inserta el `COBRO` de
  contado o abono en la misma transacciÃƒÂ³n; `FIADO` no genera `COBRO`.
  `scripts/refactor_v43_check.py` contra `orminorth_v43` Ã¢â€ â€™
  **REFACTOR V4.3: OK** (4 ventas, cartera, `deleted_at`, caja y dashboard;
  0 registros de prueba al terminar). Evidencia:
  `.agents/evidencias/refactor_v43_check_2026-11-09.txt`.
- Ãƒâ€œrdenes reales #55/#56/#57 con IVA 15 % y bruto **$43,424.00 / $9,448.40 /
  $2,171.20** (los candados las recrean con el cÃƒÂ³digo nuevo); cartera real
  **55,043.60 / 2 clientes / fiado 55,043.60**; `payments` sigue en 0 porque las
  tres son FIADO. La #9 histÃƒÂ³rica conserva `total`/`total_con_iva` `NULL`.
  Los costos de materiales siguen en **8.2000 / 14.0000 / 16.5000 / 3.8000** y
  el stock en **3,500 / 450 / 550 / 600**; el kardex no tocÃƒÂ³ datos reales.
- **Custodio v4.3 aplicado el 2026-11-09.** `.agents/evidencias/revision_v43_2026-11-09.txt`: 11 migraciones, 28 tablas, 6 vistas, 26 cuentas, `por_cobrar 47,864 / 2 clientes / fiado 47,864` (foto previa al refactor); respaldo previo `pre_v43_orminorth.dump`.
- `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` (pre-refactor) Ã¢â€ â€™ **180 passed**, exit 0 (`.agents/evidencias/pytest_v43_2026-11-09.txt`).
- Hito 1 Ã¢â€ â€™ `[CANDADO CERRADO]`, 235 movimientos de kardex (`.agents/evidencias/hito1_lock_v43_2026-11-09.txt`).
- Hito 3 Ã¢â€ â€™ `[CANDADO CERRADO EN SANDBOX]` (`.agents/evidencias/hito3_lock_v43_2026-11-09.txt`).
- Pruebas SQL en `orminorth_v43` Ã¢â€ â€™ 7 guardas OK, 0 FALLO (`.agents/evidencias/sql_tests_v43_2026-11-09.txt`).
- Contratos v1.3.0 Ã¢â€ â€™ 4 esquemas vÃƒÂ¡lidos, 14/14 ramas (`.agents/evidencias/contracts_v13_2026-11-09.txt`).
- `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` (sesiÃƒÂ³n previa) Ã¢â€ â€™ **180 passed**, exit 0 (`.agents/evidencias/pytest_panel_horminor_2026-11-08.txt`).
- Playwright 1440Ãƒâ€”1000 Ã¢â€ â€™ 3 tarjetas de **253 px** cada una, anillo **0.31%**, **372 / 120,000 mÃ‚Â³**, ventas **404 mÃ‚Â³ / $47,864 / 4 ÃƒÂ³rdenes / 51 viajes**, provincias Orellana/SucumbÃƒÂ­os/sin provincia, 2 obras con SVG locales, **3 KPIs plegados**, Poppins OK, overflow 0, **0 errores de consola**, **0 requests fallidos**.
- Playwright Banca Ã¢â€ â€™ **mercado 215,000 mÃ‚Â³ Ã‚Â· ventas 404 mÃ‚Â³ Ã‚Â· 0.19% Ã‚Â· brecha 214,596 mÃ‚Â³**, 2 provincias, 2 escenarios.
- Playwright 390Ãƒâ€”844 Ã¢â€ â€™ las 3 tarjetas se apilan, overflow 0, 6 tabs visibles, top header sticky, 2 obras.
- Capturas: `.agents/evidencias/panel_horminor_dashboard_dark.png`, `panel_horminor_dashboard_light.png`, `panel_horminor_banca.png`, `panel_horminor_secretaria.png`, `panel_horminor_superadmin.png`, `panel_horminor_movil.png`, `panel_horminor_clientes.png`, `panel_horminor_planta.png`, `panel_horminor_notificaciones.png`, `panel_horminor_busqueda.png`.
- Design system: `.agents/diseno/horminor_design_system.json`.

## Limitaciones del Cerebro experimental (no se corrigen ahora)

Documentadas al cerrar la fase. Se retomarÃ¡n de forma progresiva con el sistema
de correcciones; no se abren frentes individuales.

- **Cliente no solicitado:** en el audio de DÃ­az Sur, Julio dice Â«acabo de hacer
  un contratoÂ», no Â«crÃ©ame el clienteÂ»; el motor igual propone `crear_cliente`.
- **Nombres mal interpretados:** el vocabulario aprendido convierte Â«DÃ­az SurÂ»
  en Â«DualsurÂ».
- **Encargos no identificados:** la transferencia de 27 000 USD quedÃ³ como un
  segundo encargo en lugar de ser un dato del primero.

## Bloqueos actuales (ordenados por impacto)

1. **Credenciales reales de Evolution API, Bunny.net y Gemini.** Ya **no
   bloquean** demos ni el cierre lÃƒÂ³gico: en SANDBOX el WhatsApp se encola en
   `sandbox_outbox`, Bunny devuelve URLs simuladas y el Juez es determinÃƒÂ­stico.
   Abel las sube el **2026-11-09**; se cargan desde el Superadmin
   (`whatsapp_evolution_y_cdn`) y se apaga el switch para pasar a producciÃƒÂ³n.
2. **TelÃƒÂ©fonos reales del personal.** La identidad ya estÃƒÂ¡ implementada
   (nÃƒÂºmero registrado + cÃƒÂ³digos `#BODEGA`, `#CAJA`, `#ADMIN`, `#M<n>`);
   `whatsapp.staff` tiene semillas de demostraciÃƒÂ³n editables en
   `directorio_roles_whatsapp`.
3. **Datos que Julio todavÃƒÂ­a no entregÃƒÂ³:** RUC, horario, cuentas bancarias,
   placas, choferes, precio de mercado por provincia y umbral de merma. Quedan
   `NULL`/vacÃƒÂ­os o como semilla marcada; no se inventaron.
4. **Capacidad operativa de planta (mÃ‚Â³ por perÃƒÂ­odo) sin definir.** El dashboard
   ya no la usa para el anillo principal (muestra el mercado real de El Coca);
   sigue faltando para un KPI de capacidad operativa. DueÃƒÂ±o del dato: Julio.
5. **Formulario de pagos implementado.** `/panel` ya registra cobros, abonos y
   gastos contra `/api/v1/panel/pagos`; falta validarlo con la secretaria real.
6. **Login de usuario final Ã¢â‚¬â€ backlog exclusivo pre-VPS (decisiÃƒÂ³n 2026-11-09).**
   El panel sigue afinÃƒÂ¡ndose en local con el puente `X-Panel-Role`; el login
   (`panel_users`, hash, cookie `HttpOnly`) se implementa **solo antes de
   publicar en el VPS**. Mientras tanto, `/panel`, `/api/v1/panel/*` y
   `/api/v1/secretaria/*` no se exponen a Internet.
7. **Backup diario listo, cron pendiente.** `scripts/backup_db.sh` genera,
   verifica y retiene 14 dÃƒÂ­as/6 meses; falta instalarlo en el VPS y copiar los
   dumps fuera de la mÃƒÂ¡quina.
8. **Respaldo externo.** Todo el proyecto y la base viven en un solo disco. Hay
   un respaldo manual previo a v4.3, pero no polÃƒÂ­tica automÃƒÂ¡tica.
9. **Circuito HTTP cerrado.** El Custodio, el router, la ventanilla de pagos y
   el panel estÃƒÂ¡n implementados; solo falta el login de usuario.
10. **Decisiones de negocio cerradas; quedan datos operativos.** IVA histÃƒÂ³rico,
    fecha de conteo, valoraciÃƒÂ³n/DSCR, rol `CONTADORA`, reembolso y nota de
    crÃƒÂ©dito ya tienen decisiÃƒÂ³n. Falta que Julio/Contadora carguen las tasas,
    que Bodega ejecute el conteo fÃƒÂ­sico y que se validen con la operaciÃƒÂ³n real.

> **Repositorio: solo local (ratificado 2026-11-08).** El cÃƒÂ³digo vivirÃƒÂ¡ en el
> VPS; GitHub no es requisito para avanzar. Los commits locales en `orminorth/`
> son la fuente de verdad y el respaldo. `git push` deja de ser un bloqueo y
> pasa a ser una tarea opcional del despliegue (clonar el repo en el VPS).

## PrÃ³ximo paso exacto

El Cerebro experimental queda **cerrado** (router `router-1.7` congelado, Gato
desconectado, Jev en backlog). El siguiente trabajo es el resto del ERP:

1. **C4:** capturar `fecha_vencimiento` en los formularios de orden y factura;
   hoy todo cae en `SIN_VENCIMIENTO`.
2. **UbicaciÃ³n v8.2:** probar en un telÃ©fono real el botÃ³n **Usar mi ubicaciÃ³n**
   y el pin enviado por WhatsApp. El residuo de prueba ya se limpiÃ³.
3. **Factura con extras:** conectar la factura/cartera a `v_orden_total` para
   que sume `orden_extras`.
4. **Contratos de obra cierta y horas extra** (siguiente migraciÃ³n libre) y
   **C9: UI de recordatorios en el panel**.
5. **Cotizaciones Q5 (Gato):** crear borrador, consultar y enviar con â€œsÃ­â€.
6. **Validar el dashboard C5/C6 y Cotizaciones con Julio**: 4 ventanas, presets
   de cobranza, meta/equilibrio y manual.

## Decisiones de arquitectura vigentes

| # | DecisiÃƒÂ³n | PorquÃƒÂ© |
|---|---|---|
| 1 | 12 tablas (el PDR dice 10 sin enumerarlas) | Cubre todo lo que el propio PDR nombra |
| 2 | `tracking_payload` JSONB es autoritativo | Contrato entre M1 y M3 sin acoplamiento |
| 3 | Kardex teÃƒÂ³rico por viaje, no por orden | Cada JSON de viaje es autosuficiente |
| 4 | `materials.stock_actual` = stock real | Evita mezclar teÃƒÂ³rico con fÃƒÂ­sico |
| 5 | Receta provisional **no** bloquea la venta | El viaje marca `receta_provisional` y el Centinela avisa; detener la venta cuesta mÃƒÂ¡s |
| 6 | Migraciones SQL planas + advisory lock | Sin ORM: el contrato es SQL |
| 7 | `timestamptz` en UTC, zona operativa en BD | El offset no se escribe en el cÃƒÂ³digo |
| 8 | Identidad WhatsApp: nÃƒÂºmero registrado > cÃƒÂ³digo de operador > lead | Una sola regla, en base de datos, sin reescribir el bot |
| 9 | Debounce de 14 s sobre Redis, con degradaciÃƒÂ³n a memoria | El webhook responde de inmediato y la API sigue arriba si Redis falla |
| 10 | Dos umbrales tÃƒÂ©rmicos (60 y 30 min antes) | Aviso temprano para reaccionar y crÃƒÂ­tico para escalar |
| 11 | Alertas sin webhook quedan como `NO_CONFIGURADO` en `error_logs` | No se finge un envÃƒÂ­o que no ocurriÃƒÂ³ |
| 12 | **Todo parÃƒÂ¡metro de negocio es dinÃƒÂ¡mico** (semilla 050 + Superadmin) | Julio no bloquea el avance; el frontend edita sin tocar cÃƒÂ³digo |
| 13 | **Sin login en Superadmin/SecretarÃƒÂ­a por ahora** | No frenar pruebas de API ni integraciÃƒÂ³n del Frontend; se desacopla al final |
| 14 | El bot arma su respuesta con datos de BD; el LLM solo decide SÃƒÂ/NO | Cero precios o promesas inventadas por el modelo |
| 15 | **SANDBOX por adaptadores inyectables** | El mismo contrato pasa a producciÃƒÂ³n al cargar credenciales; sin `if` de sandbox en el pipeline |
| 16 | **Outbox persistido** en `sandbox_outbox` + memoria | El simulador y los tests ven lo mismo; no se finge un envÃƒÂ­o real |
| 17 | **Cupo de crÃƒÂ©dito alerta, no bloquea** | La venta se registra con `excede_cupo_credito=true`; bloquear cuesta mÃƒÂ¡s que cobrar |
| 18 | **Precio de orden = explÃƒÂ­cito o precio de receta** | La venta queda valorada; si no hay precio en ninguno, el total queda NULL y pendiente |
| 19 | **`clients.provincia` para cuota de mercado** | La demanda es provincial; las ventas sin provincia se informan aparte, no se reparten |
| 20 | **Panel ÃƒÂºnico HTML sin build ni CDN** | Funciona en local y VPS sin toolchain de frontend; se puede migrar despuÃƒÂ©s |
| 21 | **Centinela sin llamadas externas en SANDBOX** | Un WARN por el CDN real confundÃƒÂ­a la salud del sistema |
| 22 | **MigraciÃƒÂ³n 061 separada** | La 060 ya estaba aplicada; no se edita una migraciÃƒÂ³n aplicada |
| 23 | **Tema visual V2 en tokens CSS** (`data-theme` + `localStorage`) | Oscuro ejecutivo por defecto para Julio; claro de oficina conmutable para SecretarÃƒÂ­a; sin build ni CDN y sin tocar contratos ni tests |
| 24 | **Marca visible Horminor; carpeta/repo siguen como `orminorth`** | Es lo que ve el cliente; renombrar rutas, contenedores e historial romperÃƒÂ­a comandos sin aportar valor |
| 25 | **Poppins local y sidebar CRM de 258 px** | La tipografÃƒÂ­a de la referencia queda servida desde `/static` (sin Google Fonts); la sidebar reproduce la captura y colapsa a barra superior en <900 px |
| 26 | **CorrecciÃƒÂ³n de marca en migraciÃƒÂ³n 062** | Las migraciones 050/060 ya estaban aplicadas; se corrige el ADN pÃƒÂºblico y Bunny sin editar el pasado |
| 27 | **Panel con shell ShikshaQ y jerarquÃƒÂ­a nÃƒÂºmero-primero** | Top header fijo, sidebar de 6 tabs, donut/actividad/calendario y 3 obras; los pÃƒÂ¡rrafos se reemplazan por cifras grandes y barras. Se conservan IDs, `data-*`, rutas y contratos; cero build y cero CDN. Alternativa descartada: copiar los textos largos del API, que cansan la lectura |
| 28 | **`_json_objeto()` normaliza JSONB en M3** | `obtener_carpeta` hacÃƒÂ­a `dict(tracking_payload)` y devolvÃƒÂ­a 500 cuando asyncpg entrega JSONB como texto. El helper acepta texto o mapping y devuelve `{}` si no se puede parsear; la carpeta forense volviÃƒÂ³ a 200 sin tocar el contrato |
| 29 | **Dashboard V2 nÃƒÂºmero-primero con el mercado como ancla comercial** | Tres tarjetas iguales (Mercado El Coca, Ventas 2026, DÃƒÂ³nde vendes) que responden quÃƒÂ© necesita Julio; agenda y actividad bajan a una fila inferior; caja/mixers/bodega quedan en `<details>`. La tarjeta de mercado muestra **0.31% / 372 mÃ‚Â³ / 120,000 mÃ‚Â³** y la de Banca **215,000 / 404 / 0.19% / 214,596 mÃ‚Â³** sin pÃƒÂ¡rrafos. Se conservan IDs, `data-*`, rutas API y los tests existentes; ilustraciones SVG locales sin build ni CDN. Alternativa descartada: seguir mostrando el anillo de eficiencia (2/51 viajes) como protagonista, que no vende posicionamiento |
| 30 | **`v_cliente_saldo` conserva las 8 columnas originales** | Los 3 consumidores y `catalog.py` dependen de `id, nombre, estado, total_m3, total_facturado, total_cobrado, total_fiado, saldo_pendiente`; v4.3 agrega `ruc`, `credit_limit_usd` y `saldo_a_favor` al final. Alternativa descartada: reordenar o cambiar tipos, que rompÃƒÂ­a consumidores |
| 31 | **Fallback `COALESCE(total_con_iva, total)` en la vista** | Mantiene visibles las ÃƒÂ³rdenes histÃƒÂ³ricas sin bruto (la #9) sin inventarles IVA. Las ventas nuevas ya escriben `total_con_iva`; el fallback queda permanentemente para histÃƒÂ³ricos |
| 32 | **IVA 15 % solo para ventas nuevas; histÃƒÂ³ricos sin IVA** | La decisiÃƒÂ³n de Julio fue default 15 % en ventas nuevas; la #9 anterior queda con `total_con_iva = total`/`NULL` y `finanzas.iva_historico_confirmado=false` hasta confirmaciÃƒÂ³n retroactiva |
| 33 | **Inventario por promedio ponderado** | Confirmado el 2026-11-09; `inventory_movements.costo_unitario_snapshot` guarda el costo vigente y el kardex calcula COGS con esa base |
| 34 | **Gate idempotente + ledger/testigo inmutables** | `processed_requests` guarda `request_id` + hash; `ledger_entries` y `audit_witness_log` solo permiten INSERT y las correcciones se hacen con reversa/testigo. Alternativa descartada: `UPDATE` directo, que borra la trazabilidad |
| 35 | **IVA y COBRO inicial en la transacciÃƒÂ³n de la orden** | `crear_orden` valida el abono contra el bruto y escribe orden + `payments` juntos: si falla el pago, no queda una venta contada como cobrada. El router no inserta pagos por su cuenta. Alternativa descartada: un segundo `INSERT` desde el endpoint, que dejaba ventas huÃƒÂ©rfanas si fallaba |
| 36 | **El pago inicial de una compra va en un asiento `SUPPLIER_PAYMENT` separado** | Si el pago se asentara dentro de `PURCHASE`, corregir el pago con testigo revertirÃƒÂ­a tambiÃƒÂ©n la compra. Separado, cada documento tiene su propia reversa y su propio testigo |
| 37 | **CorrecciÃƒÂ³n con testigo limitada al asiento vigente y a compras de servicio de una lÃƒÂ­nea** | Solo se revierte el asiento sin reversa previa (evita duplicar el ajuste) y una compra con inventario o varias lÃƒÂ­neas exige nota de crÃƒÂ©dito: redistribuir stock o costos desde una cabecera serÃƒÂ­a inventar datos |
| 38 | **ValoraciÃƒÂ³n/DSCR parametrizados y anulaciÃƒÂ³n con modos** | Si faltan tasas en `finanzas.parametros_contables`, el Gate devuelve la foto real y `UNCONFIRMED_FINANCIAL_RATES`; si existen, calcula DCF/DSCR. La anulaciÃƒÂ³n con cobros exige `modo_resolucion_cobro` y no consume la aprobaciÃƒÂ³n si falta |
| 39 | **Router HTTP con tokens de servicio y roles oficiales** | `CUSTODIO_TOKEN_SUPERADMIN/CONTADORA/SECRETARIA/BODEGA/CHOFER` + `X-Actor-Id` + `X-Channel`; el rol nunca viaja en el JSON. `SECRETARIA` y `CONTADORA` cobran; `BODEGA` y `CHOFER` no |
| 40 | **Pagos con split 1103/2102** | Abono parcial permitido. Si `monto > saldo` y `es_anticipo=false` Ã¢â€ â€™ `PAYMENT_EXCEEDS_PENDING_BALANCE`; si `es_anticipo=true`, la deuda va a `1103` y el excedente a `2102`, con `saldo_a_favor` |
| 41 | **Reembolso con `modo_resolucion_cobro`** | `CONVERTIR_A_ANTICIPO_CLIENTE` reclasifica a `2102`; `DEVOLVER_DINERO_CAJA_O_BANCO` inserta `REEMBOLSO_CAJA` y borra lÃƒÂ³gicamente el cobro original |
| 42 | **IVA por defecto apagado** | `066` deja `finanzas.iva_default_aplica=false`. Las ventas nuevas solo llevan IVA si el contrato envÃƒÂ­a `aplica_iva=true`; el panel y los candados lo envÃƒÂ­an, asÃƒÂ­ que la cartera verificada de $55,043.60 no cambia |
| 43 | **El navegador no recibe tokens del Custodio** | El panel llama a `/api/v1/panel/pagos` y `/api/v1/panel/catalog`; el servidor resuelve el actor (`X-Panel-Role` mientras no haya login). Los `CUSTODIO_TOKEN_*` quedan solo en el backend |
| 44 | **Superadmin edita tasas y conteo, no valores inventados** | `finanzas.parametros_contables` se edita con inputs; el conteo fÃƒÂ­sico se registra con stock real y sella `ultimo_levantamiento_at`. Los valores siguen siendo de Julio/Bodega |
| 45 | **Backup diario verificable, no solo un dump** | `backup_db.sh` valida con `pg_restore --list`, retiene 14 dÃƒÂ­as y 6 meses, y se complementa con copia externa y restauraciÃƒÂ³n mensual |
| 46 | **Login desacoplado al backlog pre-VPS** | Se sigue afinando `/panel` con el puente `X-Panel-Role` (sin credenciales ni bloqueo de rutas) para no perder agilidad en pantallas y flujos. El login (`panel_users`, hash, cookie `HttpOnly`) se implementa ÃƒÂºnicamente antes de exponer el panel a Internet. Alternativa descartada: bloquear rutas ahora, que obliga a crear usuarios y frena las pruebas locales |
| 47 | **Un contrato activo no se edita, se adenda** | El impreso firmado y la base no pueden divergir |
| 48 | **Extras: un solo rubro global con descripcion libre** | Julio cobra o absorbe cualquier cosa ajena a Horminor sin taxonomias que se queden cortas |
| 49 | **La cotizacion no crea orden** | Una venta aceptada que no se despacha no debe producir una orden fantasma |
| 50 | **Cada modulo tiene diseno, skill y tareas** | Sin las tres piezas se redisenya lo ya decidido |
| 51 | **La ubicacion no se estima: NULL y `PENDIENTE`** | El mixer necesita el punto real. Guardar texto, GPS o pin de WhatsApp con `ubicacion_origen`; sin coordenadas el PDF dice `PENDIENTE` en vez de inventar una posicion |
| 52 | **La referencia escrita manda sobre el nombre del pin** | El asesor escribe Â«junto al tanqueÂ»; el nombre del pin suele ser generico. El pin solo rellena cuando no hay texto, y un `PUT` parcial no borra lo recibido por WhatsApp |
| 53 | **La tarjeta que aloja un desplegable sube su `z-index`** | `backdrop-filter` crea contexto de apilamiento y el `z-index` del hijo no puede salir de la tarjeta; se corrige en el contenedor (`.card-buscar-clientes`), no subiendo el hijo |

## Riesgos abiertos

- **El VPS tiene datos ficticios.** Cuatro clientes `(PRUEBA)` con facturas
  ficticias y un lead real del bot. No usar esa base para operar ni emitir
  cobros; limpiar antes de cargar clientes reales.
- **El panel del VPS se usa por tÃºnel SSH.** Si el tÃºnel se cae, el link
  `localhost:8012` deja de responder; no hay acceso pÃºblico por diseÃ±o.
- **El nÃºmero de WhatsApp es no oficial (Baileys).** Un uso masivo o sin
  consentimiento puede bloquear la lÃ­nea y con ella todo el bot.
- **`ENVIADO` no es `ENTREGADO`.** No se procesa `MESSAGES_UPDATE`; un nÃºmero
  inexistente puede quedar como enviado.
- Sin backups de PostgreSQL definidos (se van a generar carpetas bancarias).
- Sin proxy inverso ni TLS: no se puede exponer el webhook de Evolution.
- `.env` con clave de desarrollo: **no usar en producciÃƒÂ³n** (rotar antes del VPS).
- **Todo el proyecto vive en un solo disco.** Al no usar repositorio remoto, no
  hay copia fuera de la mÃƒÂ¡quina: hacer respaldo periÃƒÂ³dico del repo (otra unidad,
  disco externo o carpeta en la nube). Esta es la ÃƒÂºnica deuda real de "solo
  local".
- Las rutas del panel, SecretarÃƒÂ­a y Superadmin estÃƒÂ¡n abiertas: **no exponerlas
  a Internet** hasta que exista autenticaciÃƒÂ³n.
- Las semillas de staff, flota, bancos y benchmarks son de **demostraciÃƒÂ³n**;
  reemplazarlas por datos reales antes de operar.
- La primera llamada al Centinela puede tardar mÃƒÂ¡s por apertura del pool; en
  caliente medimos ~100 ms con 12 checks (el PDR exige <200 ms).

## Actualizacion 2026-11-18 (tarde)

> Esta seccion reemplaza lo que digan arriba los puntos sobre "tunel SSH" y
> "panel no expuesto": el panel ya esta publicado.

- **Panel publico con basic auth.** `https://horminor.178.238.238.158.sslip.io/panel`
  responde 200 con el usuario `julio` y la clave nueva; sin credenciales da 401.
  El hash vive en `/etc/caddy/Caddyfile`. La clave esta en
  `vps-entrada/HORMINOR_PANEL_ACCESO.txt` (fuera de git). Sigue pendiente el
  login propio del CRM.
- **WhatsApp revinculado el 18-N.** La instancia `horminor` habia dejado de
  recibir entrantes por sesiones rotas (`Bad MAC`); se revinculo con QR desde el
  `0963410409` y volvio a recibir. Es un parche: el defecto puede repetirse.
- **Espejo probado con contactos reales.** Paola (`0968278401`) autorizada y con
  cliente creado; Alejandra (`593986962872`) reactivada. Imagen, video y audio
  entrantes llegan en vivo y se guardan en Bunny dentro de
  `horminor/clientes/<cliente>/`.
- **Notas de video y compresion.** `ptvMessage` ahora se copia como VIDEO y los
  videos entrantes se recomprimen a H.264 720p antes de subirse (con fallback al
  original). `pytest test_v97_espejo_whatsapp.py` -> **53 passed**.
- **Pendiente de probar:** PDF y enlace entrantes; y responder/citar mensajes
  como en WhatsApp (no existe todavia).

## Actualizacion 2026-11-18 (noche)

- **El VPS quedo alineado con la version local.** Se respaldo la base
  (`/root/alineacion_20261118_152413/db.sql.gz`) y el codigo anterior
  (`codigo_anterior.tgz`); se aplicaron las migraciones **079-092** y se
  reconstruyo `core-api`. `/health` ok y `/panel/cerebro` responde **200**.
- **Cerebro visible (BETA).** El modulo `cerebro` y `voz` quedaron habilitados
  para Julio y `cerebro.enabled=true`. El dictado de prueba genero un borrador
  con tarea, destinatario y fecha en 1,5 s.
- **Puente Gato -> Cerebro.** Un mensaje que empieza con `cerebro:` o `dictado:`
  se entrega al Cerebro y Gato devuelve el resumen + preguntas + ruta del
  laboratorio. Probado en el VPS: devolvio dos encargos y dos preguntas.
- **Sigue pendiente:** audio por Gato, confirmar/ejecutar desde Gato, aviso
  sonoro, Gmail y responder/citar.



## Actualizacion 2026-11-20 (noche) - Recordatorio y cotizacion desde el Cerebro

- **El error `CONFIRMAR_ENVIO_INMEDIATO` tenia dos causas.** (1) Con un borrador
  pendiente, el dictado nuevo se tomaba como confirmacion del anterior: la
  frase Â«enviarle un recordatorio...Â» coincidia con Â«enviaÂ» y se ejecutaba la
  accion vieja, que no tenia hora. (2) Â«a las 15 y 27Â» no se leia como hora.
  Ahora un dictado nunca confirma (prefijo `dictado:` o mas de 10 palabras) y
  las dos formas habladas se leen como 15:27 y 15:30.
- **El chat puede completar la hora.** `ConfirmarIn` acepta `cuando`; el puente
  envia `enviar_ahora` y `cuando`; Â«a las 15 y 27Â» o Â«mandalo ahoraÂ» cierran la
  confirmacion. Los guardas ya no se muestran como JSON crudo.
- **Cotizacion conectada.** `crear_cotizacion_borrador` esta en
  `ACCIONES_CONECTADAS`: el panel confirma y el servicio compartido crea el
  documento en `BORRADOR` con subtotal, IVA y version 1. No se ejecuta desde el
  chat; `enviar_cotizacion_whatsapp` sigue en 501.
- **Evidencia:** 766 tests en local; 101 focalizados en el VPS; recordatorio a
  las 15:27 creado y borrado en ambos; cotizacion de prueba 1180 + 177 = 1357
  creada y borrada; `/health` ok. Ver
  `.agents/evidencias/recordatorio_cotizacion_2026-11-20.txt`.
- **Pendiente:** que Julio repita el dictado desde la web; el borrador viejo
  `ef637a32` sigue esperando y ahora pide la hora en vez de fallar.

**AceptaciÃ³n de continuidad de Gato, 2026-11-24.** El seguimiento de una cotizaciÃ³n llegÃ³ a tres encargos y quedÃ³ en REQUIERE_ACLARACION. Reproducir la aclaraciÃ³n de destinatario y hora de envÃ­o, preservando volumen, obra y horario de entrega. Evidencia en la entrada de bitÃ¡cora Â«DiagnÃ³stico de la cotizaciÃ³n en tres encargosÂ».

