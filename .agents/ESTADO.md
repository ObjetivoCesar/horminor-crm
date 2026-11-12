# ESTADO DEL PROYECTO

> Foto del presente. Se reescribe en cada sesión. La historia está en `BITACORA.md`.
> Última actualización: **2026-11-12**.
> Base v6.13: Custodio v4.4.0 + HTTP, agenda única `HorminorAgenda`,
> compras/caja chica, perfiles ACL, Superadmin por Action Cards, Carpetas de
> Clientes con buscador Sabueso, bancos con color de marca y **facturas
> internas adjuntas al cliente** (PDF o foto) consultables por Gato.
> 21 migraciones, 36 tablas, 7 vistas, 30 cuentas; **342 tests** y los 2
> candados en verde. Siguiente foco: validación del cliente y login pre-VPS.

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
| 4m | v6.13 - Facturas internas adjuntas al cliente | OK **Cerrado** (2026-11-12) | Migración 073 (`client_invoices`); factura ficticia `PRUEBA-0001` (orden #55, **$43.424,00**) con PDF; pestaña **Facturas** en el expediente; `GET/POST /api/v1/clients/{id}/facturas`; Gato `cliente_facturas` con marca **FICTICIA** y SRI fuera de alcance; `evidencias/facturas_v613_2026-11-12.txt` y `panel_v613_facturas_2026-11-12.jpeg`; pytest (**338 tests**) | Validar formato con Julio; definir numeración y datos fiscales reales |
| 4l | v6.12 - Logos de bancos con color de marca | OK **Cerrado** (2026-11-12) | Tres placas SVG 96x96: Pichincha amarillo `#FFD100`, Guayaquil rosado `#C7007E`, Internacional naranja `#F39200`; isotipos oficiales, símbolo Pichincha a 56/96; `.banco-logo` de 46 px sin caja blanca; evidencias/panel_v612_bancos_dark_2026-11-12.png, _light_ y logos_zoom; pytest (**296 tests**) | Nada bloqueante. Aceptado por Dirección; si pide el lockup completo, placas 92x40 |
| 4k | v6.11 - Banco activo + detalle de cuenta | OK **Cerrado** (2026-11-12) | Migracion 072 (`bank_accounts`, hijas `1102.01-03`, `saldo_informado`); tarjetas seleccionables en amarillo; detalle con saldo contable/informado, prestamos y movimientos; `PUT /api/v1/dashboard/bancos/{slug}`; evidencias/panel_v611_banca_2026-11-12.jpeg; pytest_v611_2026-11-12.txt (**296 tests**) | Cargar cuentas y saldos reales; asignar pagos a la cuenta hija del banco |
| 4j | v6.10 - Fondo de Planta + cabecera de Banca | OK **Cerrado** (2026-11-12) | Foto `planta-agenda.webp` como fondo de la agenda con overlay; cabecera de Banca con tarjetas Pichincha/Guayaquil/Internacional y logos; endpoint `GET /api/v1/dashboard/bancos`; tarea `.agents/tareas/2026-11-12_ABEL.md`; evidencias/panel_v610_*.jpeg; pytest_v610_2026-11-12.txt (**295 tests**) | Confirmar cuentas Guayaquil/Internacional y reemplazar foto con marca Vecteezy |
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
| Panel (M3 + M4 + Superadmin) | http://localhost:8000/panel · Horminor, top header 72 px, sidebar de 6 tabs, dashboard número-primero (mercado, ventas y provincias), obras con SVG locales, agenda y actividad plegables, Poppins local, tema día/noche | http://localhost:8012/panel por túnel SSH; no público hasta tener login |

Datos de demo en local: Ã³rdenes del Ing. Reyes (320 mÂ³ FC-210 y 52 mÂ³ FC-350),
orden del candado del Hito 3 (16 mÂ³) y clientes de fixture con provincia
Orellana/SucumbÃ­os para verificar la cuota de mercado. Se regeneran con los
scripts de candado.

## Evidencia de la Ãºltima sesiÃ³n

- **VPS + Evolution (2026-11-12).** El CRM quedó desplegado en Contabo (`/opt/horminor`), clonado con deploy key read-only desde `ObjetivoCesar/horminor-crm`. `core-api` escucha en `127.0.0.1:8012`; Caddy publica solo `https://horminor.178.238.238.158.sslip.io/health` y el webhook de Evolution. El panel se usa por túnel SSH hasta que exista login. Instancia Evolution `horminor` creada con webhook; estado `connecting`, pendiente escanear QR. Ver `docs/DESPLIEGUE_VPS_HORMINOR.md`.
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

## PrÃ³ximo paso exacto

0. **Escanear el QR de Evolution `horminor`** (estado `connecting`), enviar un
   texto a un teléfono de prueba y confirmar `notifier: evolution`. Luego
   rotar la API key que se compartió por chat.
1. **Probar el panel en local con la secretaria** (cobro/abono, gasto, tasas y
   conteo) y ajustar pantallas/flujos segÃºn lo que pida Julio. El login no
   bloquea esta etapa.
2. **Cargar las tasas financieras** en Superadmin >
   `finanzas.parametros_contables` (`wacc_anual_pct`,
   `crecimiento_anual_pct`, `participacion_trabajadores_pct`,
   `impuesto_renta_pct`, `dscr_minimo_banco`) para activar valoraciÃ³n/DSCR.
3. **Ejecutar el conteo fÃ­sico** de los 5 materiales desde Superadmin; hoy
   siguen `SIN_FECHA_CONTEO`.
4. **Instalar el cron de backup** (`backup_db.sh`) y copiar los dumps fuera del
   VPS; probar una restauraciÃ³n mensual.
5. **Dashboard V2 aprobado por Julio (2026-11-08).** La captura de referencia es
   `.agents/evidencias/panel_horminor_dashboard_v2_dark_2026-11-08.png`; el
   Ã¡ngulo comercial es **372 mÂ³ vendidos de 120,000 mÂ³ (0.31%)** en El Coca.
   Sigue pendiente que Julio entregue la **capacidad operativa de planta**.
6. **ProducciÃ³n del Hito 3:** cargar credenciales reales en
   `PUT /api/v1/superadmin/config/whatsapp_evolution_y_cdn`, poner
   `evolution_sandbox=false` y `bunny_sandbox=false`, y repetir
   `docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py`.
7. **Backlog pre-VPS (no antes):** implementar el login de usuario
   (`panel_users`, hash `scrypt`, cookie `HttpOnly`) y proteger `/panel` y las
   rutas de SecretarÃ­a/Superadmin. DespuÃ©s: VPS, TLS, proxy inverso y cron de
   backups.

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

## Riesgos abiertos

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
