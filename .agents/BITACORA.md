# BITÁCORA — Orminorth / Centinela

**Registro append-only.** Se añade al final. No se borra ni se reescribe una
entrada anterior. Si una decisión cambió, se escribe una entrada nueva que lo
explique y se referencia la anterior.

Formato de entrada: ver `plantillas/entrada-bitacora.md`.
Convención de fechas: `AAAA-MM-DD`. Una entrada por sesión de trabajo.

---

## 2026-11-08 — Bootstrap: Hitos 1 y 2 (M0, M2, M5)

**Agente:** DeepSeek V4.1 Flash Free (OpenCode) + 1 subagente (M5)
**Duración:** sesión única
**Objetivo:** leer el PDR v4.0, montar el Módulo 0 y dejar funcionando los
Módulos 2 y 5 en local, sin inventar datos de negocio.

### Hecho

1. **Lectura del PDR.** El PDF (`PDR_Orminorth_Arquitectura_Modular_v4.pdf`,
   7 páginas) se extrajo a `pdr_pdf_texto.txt` con PyMuPDF. Contenido idéntico
   al `pdr.txt` original. Conclusión: el PDR **no** trae recetas, lista de
   tablas, precios, flota ni reglas de identidad de WhatsApp.
2. **Módulo 0:** `db/migrations/001_init.sql` con 12 tablas + 3 vistas
   (`v_dispatch_timeline`, `v_cliente_saldo`, `v_inventario`) y trigger
   `trg_dispatch_project` que proyecta el JSONB a columnas planas.
3. **Seeds:** `010_seed_settings.sql` (parámetros maestros), `020_seed_recipes.sql`
   (recetas marcadas `confirmado = false`, materiales con stock `NULL`),
   `030_umbral_termico.sql`.
4. **Módulo 2:** `app/m2_planta/dosificador.py` (Decimal, división de viajes con
   3 políticas, reloj térmico) y `kardex.py` (teórico por viaje, real con
   actualización de stock).
5. **Servicio de órdenes:** `app/services/ordenes.py` crea orden + N viajes +
   kardex teórico en una transacción, y devuelve advertencias en vez de fallar
   cuando la receta está incompleta.
6. **API:** `/health`, `/api/v1/clients`, `/api/v1/orders`, `/api/v1/inventory`,
   `/api/v1/sentinel/daily-audit`.
7. **Módulo 5:** 11 chequeos en paralelo (infra, canales, operación), 401/503
   por clave maestra, degradación a `NO_CONFIGURADO`.
8. **Infra local:** `docker-compose.yml` con PostgreSQL 15, Redis 7 y core-api;
   Dockerfile; `.env.example`; migraciones automáticas al arrancar.

### Evidencia (real, ejecutada)

| Comando | Resultado |
|---|---|
| `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` | **33 passed** |
| `... python scripts/hito1_lock_test.py` | 8/8 verificaciones OK; 40 viajes en 320 m³, 7 en 52 m³ (6×8+4); 47 filas en timeline |
| `... hito1_lock_test.py --provisional` | **80 movimientos de kardex**; 2.400 sacos y 384 L de retardante |
| `GET /api/v1/sentinel/daily-audit` con clave | `WARN`; latencia caliente 20–25 ms; caja de ayer sin cerrar detectada |
| Mismo endpoint sin header | `401` |
| `POST /api/v1/orders` (16 m³ FC-210) | 2 viajes, advertencia de receta provisional, timeline correcto |

Notas de entorno: Docker Desktop no estaba corriendo (`open //./pipe/dockerDesktopLinuxEngine`).
Se inició `Docker Desktop.exe` y se esperó al engine (~40 s).

### Decisiones tomadas

1. **12 tablas, no 10.** El PDR dice "las 10 tablas" sin enumerarlas; se
   implementaron 10 de negocio + `market_benchmarks` y `error_logs`, que el
   propio documento nombra. Documentado en `docs/00_DECISIONES_PENDIENTES.md`.
2. **JSONB autoritativo** y columnas por trigger. Motivo: el contrato del PDR
   es el JSON; las columnas son solo índice.
3. **Kardex por viaje.** Motivo: el JSON de cada viaje debe ser autosuficiente
   para el panel y para el juez binario.
4. **Stock no levantado = `NULL`, no `0`.** Motivo: 0 dispararía alertas falsas
   de merma y sería un dato inventado.
5. **Política `ultimo_parcial` por defecto** (52 m³ → 6×8 + 4). Provisional,
   parametrizada en `system_settings`.
6. **FC-210 con 7,5 sacos/m³ y 1,2 L/m³** derivados del único ejemplo numérico
   del PDR (60 sacos y 9,6 L para 8 m³), marcados `confirmado = false` y con la
   fuente escrita en la fila. Alternativa descartada: dejar la tabla vacía, que
   impedía probar el reparto de viajes.
7. **Umbral `POR_VENCER` = 30 min.** No está en el PDR; se agregó como parámetro
   ajustable (`operacion.umbral_por_vencer_minutos`), marcado como propuesto por
   ingeniería.

### Bloqueos / preguntas al cliente

1. Dosificación real de FC-180/210/280/350 y peso del saco.
2. Flota real de mixers (códigos y capacidades 7 u 8 m³).
3. ¿El reparto del último viaje es parcial, completo o uniforme?
4. Stock inicial, umbrales mínimos y unidades.
5. Precios por m³.
6. **Identidad de WhatsApp:** cómo distinguir bodeguero, chofer, cliente y lead
   en un solo número corporativo.
7. Credenciales de Evolution API y Bunny.net; número de prueba.
8. Alcance de facturación electrónica SRI.

### Próximo paso exacto

Si Julio entrega las recetas: cargarlas con `procesos/04-datos-negocio.md`,
correr `hito1_lock_test.py`, verificar kardex sin advertencia de provisional y
cerrar el Hito 1 en `ESTADO.md`.

Si no: iniciar el Módulo 1 con identificación por número registrado
(`clients.telefono_whatsapp` + `whatsapp.staff`), dejando la regla en base de
datos para no reescribir el bot después.

### Archivos creados

`AGENTS.md`, `.agents/**`, `db/migrations/*.sql`, `docker-compose.yml`,
`.env.example`, `services/core-api/**`, `scripts/*.py`, `docs/*.md`,
`README.md`, `pytest.ini`.

---

## 2026-11-08 (cierre) — Repo GitHub, incidente de git y traspaso

**Agente:** DeepSeek V4.1 Flash Free (OpenCode)

### Hecho

1. Repo creado por César: `https://github.com/CesarReyesJaramillo/horinor`
2. PDR copiado dentro del repo (`docs/PDR_v4.0.pdf` y `docs/PDR_v4.0.txt`) y
   referencias actualizadas en `AGENTS.md`.
3. Creado `.agents/traspaso/2026-11-08_handoff.md`: brief listo para pegar en el
   chat de dirección, con estado, decisiones a ratificar, datos que faltan y
   próximos pasos.
4. `git init` en `orminorth/`, commit inicial de 56 archivos. `.env` y
   `__pycache__` quedaron fuera (verificado).
5. Push **falló**: las credenciales de Windows corresponden a la cuenta
   `ObjetivoCesar`, que no tiene permiso sobre `CesarReyesJaramillo/horinor`
   (HTTP 403). Pendiente autenticarse con la cuenta correcta o un PAT.

### Incidente (documentado para no repetirlo)

- **Qué pasó:** se ejecutó `git reset --hard` en un repositorio **sin commit
  inicial** (HEAD inexistente). Git borró del disco los 55 archivos que estaban
  en el índice; sobrevivieron solo los ignorados (`.env`, `__pycache__`).
- **Recuperación:** los blobs seguían en `.git/objects`. Se listaron 56 objetos
  inalcanzables con `git fsck --unreachable`, se identificaron por contenido y
  se restauraron a su ruta con un script de mapeo. La imagen Docker sirvió como
  segunda fuente de verificación para `app/`, `db/` y `scripts/`.
- **Verificación:** 57 archivos en disco, `33 passed`, commit rehecho con 56
  archivos, `.env` intacto.
- **Regla nueva:** nunca `git reset --hard` en un repo sin HEAD. Para
  desestagear: `git rm -r --cached .` o iniciar de nuevo el repo.

### Evidencia

| Comando | Resultado |
|---|---|
| `git fsck --unreachable --no-reflogs` | 56 blobs recuperables |
| `docker compose run ... pytest /app/tests` | **33 passed** |
| `git ls-files` | 56 archivos versionados |
| `git log --oneline` | `7a67f13` commit inicial |

### Decisión

El repositorio se inicializó en `orminorth/` (no en la carpeta padre) para que
`git clone` + `docker compose up` funcione directo en el VPS. El PDR viaja
copiado en `docs/`.

### Próximo paso exacto

Autenticar git con la cuenta dueña del repo y ejecutar `git push -u origin main`;
luego enviar el contenido de `.agents/traspaso/2026-11-08_handoff.md` al chat de
dirección.

---

## 2026-11-08 (Hito 3) — Módulo 1 WhatsApp: debounce, Jeb y Bunny

**Agente:** DeepSeek V4.1 Flash Free (OpenCode)

### Objetivo

Construir el **Hito 3 (Módulo 1: Central de Comunicaciones WhatsApp)** del PDR
v4.0 e incorporar los dos ajustes ratificados por Dirección, sin tocar los 33
tests originales y sin inventar datos de negocio.

### Hecho

1. **Módulo 1 completo** en `services/core-api/app/m1_whatsapp/`:
   `models`, `identity`, `debounce`, `judges`, `bunny`, `repositorio`,
   `notifications`, `pipeline`, `webhook`, `worker`, `runtime`, `router`.
2. **Debounce de 14 s** (configurable e inyectable a 0.1 s en tests) sobre
   Redis, con degradación a `MemoryBufferStore` si Redis no responde.
3. **Identidad de remitentes**: primaria por número registrado
   (`clients.telefono_whatsapp` + `whatsapp.staff`) y fallback por código
   (`#M1`, `#BODEGA`, `#CAJA`, `#ADMIN`); desconocidos → `LEAD_DESCONOCIDO`.
   Los códigos de operador ganan sobre `#M<n>`.
4. **Juez Binario "Jeb"** detrás de `BooleanJudgeProvider`, con
   `DeterministicRuleMockJudge` y `GeminiFlashBooleanJudge` (JSON forzado,
   `temperature=0`, fallback determinístico ante red o salida inválida).
5. **Cuatro compuertas**: Gate 1 despacho, Gate 2 sello del cliente, Gate 3
   evidencia multimedia vía `BunnyStorageClient` mockeable, Gate 4 lead
   (`clients.estado = 'PROSPECTO'`, sin duplicar).
6. **Ajuste 1:** `permitir_receta_provisional=True` por defecto; el viaje
   declara `"receta_provisional": <bool>` en `tracking_payload`; el Centinela
   avisa con el check `recetas_provisionales`.
7. **Ajuste 2:** dos umbrales sobre 150 min → `ALERTA_TEMPRANA` (60 antes,
   WARN) y `POR_VENCER_CRITICO` (30 antes, CRÍTICO). El check
   `riesgo_termico` reporta las dos bandas.
8. **Migración `040_ratificacion_hito3.sql`**: códigos de operador, umbrales
   térmicos y ventana máxima de debounce.
9. **Centinela con 12 checks** (`construir_fabricas()`), sin alterar el
   resumen operativo de 5 llaves.
10. **Tests nuevos**: `test_hito3_ajustes.py` y `test_m1_whatsapp.py`.
    **134 tests pasan** (los 33 originales siguen intactos).
11. **Candado del Hito 3** (`scripts/hito3_lock_test.py`): tres celulares
    simulados (bodega, chofer, cliente) contra PostgreSQL real.
    **28/28 `[OK]`, 0 `[FALLA]` → CANDADO ABIERTO.**
12. **Candado del Hito 1 re-ejecutado** sin regresión: 8/8 `[OK]`.
13. **Documentación**: README raíz reescrito, `.env.example` ampliado,
    `docs/00_DECISIONES_PENDIENTES.md`, este estado y el handoff de Dirección.

### Evidencia (reproducible)

| Comando | Resultado | Archivo |
|---|---|---|
| `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` | **134 passed in 2.15s** | `.agents/evidencias/hito3_pytest.txt` |
| `docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py` | **28 `[OK]` / 0 `[FALLA]` → CANDADO ABIERTO** | `.agents/evidencias/hito3_lock.txt` |
| `docker compose run --rm --no-deps core-api python scripts/hito1_lock_test.py` | **8 `[OK]` / 0 `[FALLA]`** | `.agents/evidencias/hito1_lock_post_hito3.txt` |
| `python scripts/db_migrate.py` | `+ 040_ratificacion_hito3.sql` | `.agents/evidencias/hito3_migracion.txt` |
| `GET /api/v1/sentinel/daily-audit` | 12 checks, `WARN` global, **77.3 ms** | `.agents/evidencias/hito3_centinela.json` |
| `GET /api/v1/whatsapp/health` | `estado=OK`, `store=redis`, `ventana=14.0`, juez determinístico | `.agents/evidencias/hito3_whatsapp_health.json` |

### Decisiones (con alternativa descartada)

1. **Un check nuevo, no un cambio de contrato.** `recetas_provisionales` se
   suma a los checks pero **no** a `_MAPA_RESUMEN`: así el resumen operativo de
   5 llaves no cambia. Se descartó reemplazar un check existente porque el
   contrato ya está consumido por el CRM.
2. **`evaluar_ventana_termica()` nueva; `estado_termico()` intacta.** El Hito 2
   queda congelado y el código nuevo usa las dos bandas. Se descartó modificar
   la función legada porque habría cambiado su semántica sin necesidad.
3. **`SENTINEL_MASTER_KEY` gana sobre `AGENCY_MASTER_KEY`.** La verificación se
   centraliza en `app/auth.py`. Se descartó duplicar la lógica en cada router.
4. **Si Redis falla, el debounce cae a memoria.** Se descartó devolver 503 en el
   webhook: perder mensajes de WhatsApp es peor que procesarlos en memoria.
5. **Umbrales invertidos se normalizan** (el menor es el crítico). Se descartó
   lanzar excepción: un dato mal cargado no debe tumbar el procesamiento.
6. **Un mixer declarado es pista, no filtro.** Si el viaje tiene
   `mixer_codigo = NULL`, no se descarta; se registra en el payload al
   confirmar salida o evidencia. Se descartó exigir mixer asignado para operar.
7. **Gate 2 con reclamo no sella recepción.** Se marca
   `INCIDENCIA_RECLAMO` y se alerta. Se descartó sellar y alertar a la vez
   porque un sello de conformidad con reclamo es evidencia contradictoria.
8. **Alertas sin webhook/clave quedan en `error_logs` como `NO_CONFIGURADO`.**
   Se descartó simular el envío: falsear telemetría rompe el Centinela.
9. **`#CLIENTE` no es un código válido.** Un cliente se identifica por su número
   registrado; aceptar el código permitiría que cualquiera sellara recepciones.

### Bloqueos

- **Credenciales reales** de Evolution API, Bunny.net y Gemini; sin ellas el
  Módulo 1 corre con juez determinístico y almacenamiento en memoria.
- **Teléfonos reales del personal** para `whatsapp.staff`.
- **`git push` con 403**: las credenciales de Windows son de `ObjetivoCesar`,
  sin permiso sobre `CesarReyesJaramillo/horinor`. El commit local sí se hace.
- Siguen pendientes las recetas reales (Hito 1) y los datos de negocio de §A.

### Próximo paso exacto

1. Hacer `git add` + commit local del Hito 3 (este registro incluido).
2. El usuario corrige credenciales y ejecuta:
   `git credential-manager logout https://github.com`
   `git remote set-url origin https://CesarReyesJaramillo@github.com/CesarReyesJaramillo/horinor.git`
   `git push -u origin main`
3. Cuando la agencia entregue credenciales/teléfonos, cargar `.env` y
   `whatsapp.staff`, repetir `hito3_lock_test.py` con servicios reales y cerrar
   el Hito 3 en `ESTADO.md`.
4. En paralelo, insistir con Julio por las recetas para cerrar el Hito 1.

---

## 2026-11-08 (Cierre Hito 1 + Superadmin) — Semilla oficial y configuración en caliente

**Agente:** DeepSeek V4.1 Flash Free (OpenCode)
**Duración:** sesión única
**Objetivo:** cerrar el Hito 1 sin esperar los datos manuales de Julio, construir
el Centro de Configuración Superadmin de 7 secciones y hacer que el Módulo 1
lea toda su configuración en vivo desde PostgreSQL.

### Hecho

1. **Migración `050_seed_oficial_superadmin.sql`** (no se editaron migraciones
   aplicadas): 5 recetas confirmadas con dosificación completa, saco de 50 kg,
   precio/m³ sin IVA, IVA editable y uso comercial; stock y costos de Planta
   Central El Coca; flota `MIXER-01/02/03`; política `PARCIAL`; reloj térmico
   `150/90/120`; `empresa.bot_publico`; umbrales por planta; simulador y
   benchmarks.
2. **Columnas comerciales** en `concrete_recipes`: `precio_m3`, `iva_pct`
   (default 15%) y `uso_comercial`. `Receta` las expone y `Receta.from_row` las
   lee.
3. **Centro de Configuración Superadmin** en `app/superadmin/`:
   - `GET /api/v1/superadmin/config`
   - `GET/PUT /api/v1/superadmin/config/{section}` (con alias de sección)
   - CRUD `GET/POST/PUT/DELETE /api/v1/superadmin/recetas`
   - CRUD `GET/POST/PUT/DELETE /api/v1/superadmin/flota`
4. **Sin autenticación** en Superadmin (ratificado): solo el Centinela conserva
   `X-Agency-Master-Key`. La autenticación se desacopla para el final.
5. **Dos backends del mismo contrato**: `PostgresConfigStore` real y
   `MemoryConfigStore` para tests, inyectable por `app.state.config_store`.
6. **Recarga en caliente**: al guardar una sección, el router llama
   `WhatsAppRuntime.recargar_config()`, que ajusta la ventana de debounce y
   invalida la caché de identidad. Sin reiniciar el servidor.
7. **Alias de política de viajes**: `PARCIAL | COMPLETO | UNIFORME` se
   normalizan a `ultimo_parcial | ultimo_completo | distribucion_uniforme`.
8. **Gate #4 con respuesta dinámica**: `RepositorioWhatsApp.recetas_publicas()`
   lee las recetas confirmadas con precio; `componer_respuesta_lead()` arma el
   texto con `empresa.bot_publico` + precios y el notificador lo envía al lead.
   El LLM solo decide SÍ/NO; no calcula precios ni inventa datos.
9. **Ajuste del Centinela**: `check_recetas_provisionales` cruza contra
   `concrete_recipes.confirmado`, para no dejar un `WARN` eterno por viajes
   históricos creados antes de la semilla. El contrato de 12 checks y el
   resumen de 5 llaves no cambió.
10. **Candado Hito 1 adaptado y cerrado**: verifica 5 recetas confirmadas,
    dosificación completa, precio/uso y kardex > 0. Termina en
    `[CANDADO CERRADO]`.
11. **Candado Hito 3 adaptado**: `receta_provisional=false` y una cuarta
    simulación (lead desconocido) que prueba el Gate #4 contra PostgreSQL real.
12. **Tests nuevos** en `tests/test_superadmin_config.py`: 23 casos de las 7
    secciones, CRUD, endpoints abiertos, recarga en vivo y Gate #4 dinámico.
    **157 tests pasan** (los 134 previos siguen intactos).
13. **Documentación**: `README.md`, `AGENTS.md`, `docs/00_DECISIONES_PENDIENTES.md`,
    `ESTADO.md`, skill del candado y nuevo handoff de Dirección.

### Evidencia (reproducible)

| Comando | Resultado | Archivo |
|---|---|---|
| `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` | **157 passed** | `.agents/evidencias/pytest_cierre_hito1.txt` |
| `docker compose run --rm --no-deps core-api python scripts/hito1_lock_test.py` | **17 `[OK]` / 0 `[FALLA]` → `[CANDADO CERRADO]`**, 235 movimientos de kardex | `.agents/evidencias/hito1_lock_cierre.txt` |
| `docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py` | **34 `[OK]` / 0 `[FALLA]` → CANDADO ABIERTO** (solo faltan credenciales/teléfonos) | `.agents/evidencias/hito3_lock_cierre_hito1.txt` |
| `GET /api/v1/superadmin/config` | 7 secciones, 5 recetas, política `PARCIAL`, reloj `150/90/120` | `.agents/evidencias/superadmin_config.txt` |
| `PUT .../whatsapp_evolution_y_cdn` + `GET /whatsapp/health` | debounce `14 → 9 → 14` sin reiniciar | `.agents/evidencias/superadmin_config.txt` |
| `GET /api/v1/sentinel/daily-audit` | 12 checks; `recetas_provisionales=OK` | `.agents/evidencias/centinela_cierre_hito1.json` |

### Decisiones (con alternativa descartada)

1. **Semilla en migración nueva 050, no editar 010/020/040.** Se descartó
   reescribir migraciones aplicadas: rompería la trazabilidad y el runner.
2. **El precio base no incluye IVA; el IVA es una columna editable.** Se
   descartó guardar el precio con impuesto: el PDR y la Dirección hablan de
   precio/m³ sin IVA y el Frontend decide cuándo mostrarlo.
3. **Sin login en Superadmin por ahora.** Se descartó montar JWT antes del
   Frontend: frenaría las pruebas de API. Se deja aislado para el final y se
   documenta el riesgo de no exponerlo a Internet.
4. **La respuesta del bot se arma en código con datos de BD.** Se descartó
   dejar que Gemini redacte precios: un LLM puede inventar cifras. El Juez solo
   decide si el mensaje es una cotización.
5. **Alias de política en el motor, no en el frontend.** Se descartó obligar al
   panel a conocer `ultimo_parcial`; `normalizar_politica()` acepta ambos.
6. **El Centinela mira la receta actual, no solo el payload histórico.** Se
   descartó dejar el WARN: la receta ya está validada y el aviso eterno
   degradaría la señal.
7. **`PostgresConfigStore` y `MemoryConfigStore` comparten contrato.** Se
   descartó mockear SQL en los tests: el store en memoria ejercita la misma
   lógica de secciones y CRUD sin infraestructura.

### Bloqueos

- **Credenciales reales** de Evolution API, Bunny.net y Gemini.
- **Teléfonos reales del personal** para `whatsapp.staff` (ya editables en
  `directorio_roles_whatsapp`).
- **Datos no entregados**: RUC, horario, cuentas bancarias, placas, choferes y
  tope de crédito automático. Quedan `NULL`/vacíos a propósito.
- **`git push` con 403** por credenciales de Windows de `ObjetivoCesar`. El
  commit local sí se hace.

### Próximo paso exacto

1. Hacer `git add` + commit local de este cierre (migración, Superadmin, tests,
   candados y documentación).
2. El usuario corrige credenciales y ejecuta:
   `git credential-manager logout https://github.com`
   `git remote set-url origin https://CesarReyesJaramillo@github.com/CesarReyesJaramillo/horinor.git`
   `git push -u origin main`
3. Entregar a Dirección `.agents/traspaso/2026-11-08_handoff_cierre_hito1_superadmin.md`.
4. Cuando la agencia entregue credenciales/teléfonos, cargarlos desde el
   Superadmin, repetir `hito3_lock_test.py` con servicios reales y cerrar el
   Hito 3 en `ESTADO.md`.

---

## 2026-11-08 (Cierre de sesión) — Commit local del cierre Hito 1

**Agente:** DeepSeek V4.1 Flash Free (OpenCode)

### Hecho

1. **Commit local `16e0456`** con la migración 050, el paquete
   `app/superadmin/`, los tests nuevos, los dos candados adaptados y toda la
   documentación. Árbol de trabajo limpio después del commit.
2. **Verificación final de la base**: 5 recetas `confirmado=t`, precios
   `108/118/126/136/158` con `iva_pct=15.00`; flota `MIXER-01/02/03`
   (`8, 8, 7 m³`). Las entidades de prueba (`FC-999`, `MIXER-TEST`) fueron
   creadas y eliminadas por la API, sin residuos.
3. **Push intentado y rechazado** con la evidencia real:
   `remote: Permission to CesarReyesJaramillo/horinor.git denied to
   ObjetivoCesar.` → `403`.

### Evidencia

| Comando | Resultado |
|---|---|
| `git commit` | `16e0456 Cierre Hito 1: semilla oficial y Centro de Configuracion Superadmin` |
| `git status --short` | sin cambios pendientes |
| `git push -u origin main` | **403**, credenciales de `ObjetivoCesar` |
| `psql` sobre `concrete_recipes` | 5 recetas confirmadas, IVA 15% |
| `psql` sobre `flota.mixers` | `MIXER-01/02/03` activos |

### Bloqueos

- `git push` sigue bloqueado por la cuenta equivocada en el Credential Manager
  de Windows. **No** es un problema del repositorio ni del código.

### Próximo paso exacto

El usuario ejecuta, en `orminorth/`:

```powershell
git credential-manager logout https://github.com
git remote set-url origin https://CesarReyesJaramillo@github.com/CesarReyesJaramillo/horinor.git
git push -u origin main
```

Luego entregar a Dirección
`.agents/traspaso/2026-11-08_handoff_cierre_hito1_superadmin.md`.

---

## 2026-11-08 (Decisión) — Repositorio solo local hasta el VPS

**Agente:** DeepSeek V4.1 Flash Free (OpenCode)

### Objetivo

Cerrar la discusión sobre Git: Dirección decidió que el sistema vivirá en un VPS
y que **no hace falta publicar en GitHub para avanzar**.

### Decisión

1. **El repositorio se queda local.** Los commits en `orminorth/` son la fuente
   de verdad, el historial y la red de seguridad. Se siguen haciendo al cerrar
   cada sesión.
2. **`git push` deja de ser un bloqueo.** No aparece más como pendiente en
   `ESTADO.md` ni en el handoff; cuando exista el VPS se copia/publica el repo
   y ahí entra Git remoto.
3. **Se mantiene el `.git`.** Borrarlo no simplifica nada y quitaría la
   posibilidad de revertir cambios o auditar qué se entregó.
4. **Contrapartida asumida:** al no haber copia remota, todo el proyecto vive en
   un solo disco. Se recomienda respaldar el repo a otra unidad o carpeta en la
   nube hasta que exista el VPS. Queda como riesgo abierto, no como bloqueo.

**Alternativa descartada:** insistir con las credenciales de `ObjetivoCesar` o
abrir otra cuenta. No aporta al producto y consume tiempo de sesión.

### Evidencia

- `.agents/ESTADO.md`: bloqueo #4 eliminado; nueva nota de repositorio local y
  riesgo de disco único.
- `.agents/traspaso/2026-11-08_handoff_cierre_hito1_superadmin.md`: secciones 5
  y 6 reescritas sin `git push`.
- `docs/00_DECISIONES_PENDIENTES.md`: decisión D9 con el porqué y la alternativa
  descartada.

### Bloqueos

- Ninguno por Git. Los bloqueos reales siguen siendo datos y accesos:
  credenciales de Evolution/Bunny/Gemini, teléfonos del personal y datos
  administrativos de Julio.

### Próximo paso exacto

1. Commit local de esta decisión.
2. Pedir a la agencia el paquete de credenciales y teléfonos (ver §5 del handoff)
   para cerrar el Hito 3.
3. Respaldar el repo en otra unidad mientras el VPS no exista.

---

## 2026-11-08 — Cierre Hito 3 en SANDBOX + Módulos 3 y 4

**Agente:** DeepSeek V4.1 Flash Free (OpenCode)
**Objetivo:** Cerrar el Hito 3 sin credenciales externas (modo SANDBOX) y
construir los Módulos 3 (Secretaría + Superadmin) y 4 (Dashboard de Julio y
Ases), con tests, candados y commit local.

### Hecho

1. **Modo SANDBOX conmutable.** `app/sandbox.py` añade `SandboxNotifier`
   (encola en `sandbox_outbox`, no finge un envío), `SandboxBunnyStorageClient`
   (URL determinista bajo `/sandbox/`, sin red) y el fallback
   `DeterministicRuleMockJudge`. `/health` y el Centinela publican
   `modo=SANDBOX` y `judge_mode=DETERMINISTIC_FALLBACK`. Al cargar credenciales
   reales y apagar el switch, los mismos contratos pasan a producción.
2. **Migración 060** (`060_modulos_3_4_sandbox.sql`): `clients.credit_limit_usd`,
   `clients.provincia`, `orders.excede_cupo_credito`, `sandbox_outbox`, semillas
   administrativas/flota/staff, integraciones sandbox, Juez, cupo de crédito,
   parámetros del simulador, benchmarks 2025/2026 y valorización FC-210.
3. **Migración 061** (`061_benchmarks_limpieza.sql`): elimina los benchmarks
   heredados con `anio NULL` de Orellana y Sucumbíos. `/dashboard/benchmarks`
   devuelve exactamente 4 filas.
4. **Módulo 3 (Secretaría + Caja).** `calcular_resumen_caja`,
   `PostgresSecretariaStore` y `MemorySecretariaStore`; endpoints de clientes,
   carpeta forense, opciones del formulario, alta de orden, cierre de caja y
   cierres. El alta de orden marca `excede_cupo_credito` sin bloquear la venta.
5. **Módulo 4 (Dashboard).** Amortización francesa, DSCR, cuota de mercado y
   periodos `12_MESES_MOVILES` / `ANIO_CALENDARIO`; KPIs de caja/cartera,
   operación/riesgo térmico y bodega/autonomía; dossier HTML imprimible
   "Dossier Financiero de Pre-Calificación Bancaria — Orminorth".
6. **Superadmin ampliado.** `GET /simulador/remitentes`,
   `POST /simulador-whatsapp` y `GET /sandbox/outbox`; las 7 secciones se
   editan en caliente.
7. **Panel web** servido por FastAPI en `/panel` (también `/`): selector
   Secretaría / Gerencial / Superadmin, carpeta forense, nueva orden, cierre de
   caja, KPIs, cuota de mercado, simulador, configuración y simulador de
   WhatsApp con outbox. HTML/CSS/JS propios, sin build ni CDN.
8. **Correcciones de esta sesión:**
   - `crear_orden` insertaba `datos.precio_m3` (NULL si no venía explícito).
     Ahora usa el precio de la receta; si la receta tampoco tiene precio, queda
     NULL (nunca se inventa). Los KPIs de fiado/cartera dejaron de salir en 0.
   - El cierre de caja calculaba `diferencia` sin `efectivo_contado`; corregido
     en ambos stores.
   - `_d()` del dashboard acepta valor por defecto (causaba 500 en `/mercado`
     y `/dossier`).
   - `_json_dict()` tolera `metadatos` devuelto como texto por asyncpg.
   - En SANDBOX, los checks Evolution/Bunny del Centinela devuelven `OK` sin
     llamadas externas (antes Bunny hacía `HEAD` al CDN real y daba 403/WARN).
   - `hito3_lock_test.py`: teléfonos de prueba movidos a `0990000011/12/13/14`
     para no chocar con las semillas de `whatsapp.staff` (la identidad por
     teléfono manda sobre el código) y comparación case-insensitive.
   - `hito1_lock_test.py`: verifica que las órdenes sin precio explícito toman
     el de la receta y quedan valoradas.

### Evidencia (real, ejecutada)

| Comando | Resultado |
|---|---|
| `docker compose run ... pytest /app/tests -q` | **180 passed**, exit 0 (`evidencias/hito3_4_pytest_2026-11-08.txt`) |
| `python scripts/hito1_lock_test.py` | exit 0, `[CANDADO CERRADO]`; 320 m³ × $118 = $37.760 y 52 m³ × $158 = $8.216 (`evidencias/hito1_lock_2026-11-08.txt`) |
| `python scripts/hito3_lock_test.py` | exit 0, `[CANDADO CERRADO EN SANDBOX]` (`evidencias/hito3_lock_2026-11-08.txt`) |
| `db_migrate.py` | `+ 060_modulos_3_4_sandbox.sql`, `+ 061_benchmarks_limpieza.sql` |
| `GET /health` | `{"status":"ok","db":"ok"}` |
| `GET /api/v1/whatsapp/health` | `estado=OK modo=SANDBOX judge=DETERMINISTIC_FALLBACK store=redis notifier=sandbox` |
| `GET /api/v1/dashboard/hero-kpis` | `fiado_hoy=47864.0`, `por_cobrar_total=47864.0`, `ordenes_fiado_excedidas=3` |
| `GET /api/v1/dashboard/mercado?periodo=12_MESES_MOVILES&anio=2026` | Orellana 372/120.000 m³ = **0.31%**; Sucumbíos 16/95.000 m³ = **0.02%**; sin provincia 16 m³; precio $118.00 |
| `GET /api/v1/dashboard/benchmarks` | 4 filas: Orellana 2025/2026 = 120.000 m³; Sucumbíos 2025/2026 = 95.000 m³ |
| `GET /api/v1/dashboard/simulador` | Pluma $100k/36m cuota **$3.283,35**, DSCR **2,33x**; Combo $240k/48m cuota **$6.226,26**, DSCR **3,07x**; ambos VERDE |
| `GET /panel` | HTTP 200; contiene las tres vistas y el simulador |
| `POST /api/v1/superadmin/simulador-whatsapp` | `LEAD_DESCONOCIDO` → `GATE_4_LEAD`, `modo=SANDBOX`, respuesta `ENCOLADO` en outbox |
| `GET /api/v1/sentinel/daily-audit` | `WARN` global (caja de ayer, merma sin umbral, 1 error 24 h); **Evolution y Bunny en OK SANDBOX** |

Evidencia live completa: `.agents/evidencias/hito3_4_live_2026-11-08.txt`.

### Decisiones tomadas

1. **SANDBOX por adaptadores inyectables, no por `if` en el pipeline.** Motivo:
   el mismo contrato pasa a producción al cargar credenciales; se descartó
   hardcodear mocks dentro de los módulos.
2. **Outbox persistido en PostgreSQL (`sandbox_outbox`) y en memoria.** Motivo:
   el simulador y el candado deben verse igual en local y en tests; se descartó
   loggear solo en consola.
3. **Inmigración 061 separada.** Motivo: la 060 ya estaba aplicada y no se
   edita una migración aplicada; se descartó borrar filas a mano.
4. **`clients.provincia` para la cuota de mercado.** Motivo: la demanda es
   provincial; las ventas sin provincia se informan en `sin_provincia_m3` y no
   se reparten artificialmente. Se descartó inferir la provincia por nombre de
   cliente.
5. **Panel único HTML sin build ni CDN.** Motivo: funciona en el VPS y en local
   sin toolchain de frontend; se descartó montar React/Vite en esta etapa.
6. **Centinela sin llamadas externas en SANDBOX.** Motivo: un WARN por el CDN
   real confundía el estado del sistema; se descartó dejar que el check de
   Bunny siguiera haciendo `HEAD`.
7. **Precio de orden = precio explícito o precio de receta.** Motivo: las
   ventas deben quedar valoradas sin inventar precios; si no hay precio en
   ninguno de los dos lados, el total queda NULL y pendiente. Se descartó
   bloquear el alta o rellenar con un precio "razonable".
8. **Repositorio solo local hasta el VPS.** Se mantiene la decisión del
   2026-11-08: commits locales, sin `git push`, con respaldo externo pendiente.

### Bloqueos / preguntas al cliente

1. **Credenciales reales** de Evolution API, Bunny.net y Gemini. Ya **no
   bloquean** demos ni cierre lógico: se cargan desde Superadmin y se apaga el
   switch SANDBOX.
2. **Teléfonos reales del personal** y datos administrativos (RUC, horario,
   cuentas bancarias, placas, choferes). Editables en caliente; las semillas
   actuales son de demostración.
3. **Autenticación** de Superadmin/Secretaría: las rutas siguen abiertas; no
   exponerlas a Internet hasta implementarla.
4. **Respaldo externo:** todo el repositorio y la base viven en un solo disco.

### Próximo paso exacto

1. Cargar credenciales reales en `PUT /api/v1/superadmin/config/whatsapp_evolution_y_cdn`,
   poner `evolution_sandbox=false` y `bunny_sandbox=false`.
2. Repetir `docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py`
   contra los servicios reales y guardar la salida en `.agents/evidencias/`.
3. Implementar login antes de publicar `/panel`, `/api/v1/secretaria/*` y
   `/api/v1/superadmin/*` en el VPS.

### Archivos tocados

- `services/core-api/app/sandbox.py` (nuevo)
- `services/core-api/app/m3_secretaria/` (nuevo)
- `services/core-api/app/m4_dashboard/` (nuevo)
- `services/core-api/app/web/` (nuevo)
- `services/core-api/app/main.py`, `settings.py`, `services/ordenes.py`
- `services/core-api/app/superadmin/{router,store}.py`
- `services/core-api/app/m1_whatsapp/{identity,repositorio,runtime}.py`
- `services/core-api/app/m5_sentinel/{audit,checks}.py`
- `services/core-api/app/routers/catalog.py`
- `db/migrations/060_modulos_3_4_sandbox.sql`, `061_benchmarks_limpieza.sql`
- `services/core-api/tests/test_m3_secretaria.py`, `test_m4_dashboard.py`,
  `test_sandbox.py`
- `scripts/hito1_lock_test.py`, `scripts/hito3_lock_test.py`
- `.agents/evidencias/hito3_4_pytest_2026-11-08.txt`,
  `hito3_4_live_2026-11-08.txt`, `hito1_lock_2026-11-08.txt`,
  `hito3_lock_2026-11-08.txt`

---

## 2026-11-08 — Panel con tema "Industrial Titanium" día/noche

**Agente:** DeepSeek V4.1 Flash Free (OpenCode)
**Objetivo:** Aplicar la directriz visual V2 (Industrial Titanium, CAT Amber &
Banking Blue Bento) al panel existente, con Modo Ejecutivo Oscuro por defecto y
Modo Oficina Claro conmutable, sin romper contratos ni tests.

### Hecho

1. **Tokens CSS completos** en `/panel`: base basalto/acero oscuro, neblina
   radial ámbar-azul, superficies Bento con vidrio, coronas de luz ámbar (CAT,
   operación) y azul cobalto (banca, caja/cartera y simulador), cápsulas
   horizontales para clientes y semáforos operativos.
2. **Modo Oficina Claro** (`[data-theme="light"]`): Blanco Hormigón
   Arquitectónico, texto carbón, bordes claros y acentos ámbar/azul. Pensado
   para la secretaria bajo luz solar intensa.
3. **Conmutador día/noche** en la barra superior, con persistencia en
   `localStorage` (`orminorth-theme`), icono sol/luna, `aria-pressed` y
   actualización de `meta[name="theme-color"]`. El tema se aplica en un script
   inline antes del primer pintado para evitar destellos.
4. **Geometría Bento en KPIs**: la tarjeta de caja/cartera ocupa 5/12, la de
   operación 4/12 y la de bodega 3/12 en escritorio; en tablet y móvil colapsan
   a 2 y 1 columna. El simulador usa la corona bancaria azul.
5. **Detalles de interacción**: filas de clientes como cápsulas con hover
   ámbar, botones primarios ámbar CAT, cierre de caja y dossier en azul
   bancario/CTA blanco, foco visible en inputs, transiciones suaves y respeto a
   `prefers-reduced-motion`.
6. **Móvil**: el selector de rol ahora envuelve en varias líneas en lugar de
   recortarse; los tres botones quedan visibles en 484 px.

### Evidencia (real, ejecutada)

| Comando / verificación | Resultado |
|---|---|
| `docker compose run ... pytest /app/tests -q` | **180 passed**, exit 0 |
| `node --check` sobre los dos `<script>` del panel | exit 0, sintaxis válida |
| Navegador → `/panel` (oscuro) | `data-theme=dark`, fondo `rgb(11,15,23)`, texto blanco, **0 errores de consola** |
| Conmutar a claro | `data-theme=light`, fondo `rgb(241,245,249)`, texto `rgb(15,23,42)`, **0 errores** |
| Recargar la página | `localStorage=dark` y `data-theme=dark` (persistencia correcta) |
| KPIs en claro | caja/cartera borde `rgb(37,99,235)`; operación borde `rgb(245,158,11)`; bodega borde `rgb(226,232,240)` |
| KPIs en oscuro | caja/cartera borde `rgba(65,131,251,.55)`; operación borde `rgba(245,158,11,.55)` |
| Selector de rol a 484 px | los 3 botones visibles (`derecha` máx. 455 ≤ 484) |
| Capturas | `.agents/evidencias/panel_tema_oscuro_secretaria.jpeg`, `panel_tema_claro_gerencial.jpeg`, `panel_tema_oscuro_gerencial.jpeg` |

### Decisiones tomadas

1. **Tokens en CSS, no en JS.** El cambio de tema solo alterna
   `data-theme` en `<html>`; todos los colores viven en variables. Se descartó
   re-renderizar componentes o duplicar hojas de estilo.
2. **Oscuro por defecto.** Impacto ejecutivo para Julio; claro disponible para
   turnos largos de Secretaría. Se descartó seguir el `prefers-color-scheme`
   del sistema para que la primera impresión sea la definida por Dirección.
3. **Corona ámbar = operación; corona azul = banca.** La semántica de color
   guía la lectura: CAT para mixers/producción, cobalto para cartera, cuota de
   mercado y simulador. Se descartó usar un solo acento para todo.
4. **Sin build ni CDN.** Todo el sistema visual vive en el `<style>` de
   `panel.html`. Se descartó introducir Tailwind/Vite en esta etapa.

### Bloqueos / preguntas al cliente

- Ninguno para el panel. Las credenciales reales las sube Abel el 2026-11-09;
  mientras tanto el sistema sigue en SANDBOX.
- Validar con Julio si el oscuro debe ser el predeterminado para su equipo o si
  prefiere claro por defecto en oficina.

### Próximo paso exacto

1. Cuando Abel cargue las credenciales, actualizar
   `whatsapp_evolution_y_cdn`, apagar `evolution_sandbox`/`bunny_sandbox` y
   repetir `hito3_lock_test.py`.
2. Revisar el panel en una pantalla ancha real (escritorio) para confirmar la
   composición Bento 5/4/3 y ajustar si Julio pide otra jerarquía.

### Archivos tocados

- `services/core-api/app/web/templates/panel.html` (CSS, toggle y clases Bento)
- `.agents/evidencias/panel_tema_*.jpeg`

---

## 2026-11-08 — Rebranding a Horminor y rediseño del panel (CRM con sidebar)

**Agente:** OpenCode (DeepSeek V4.1 Flash Free)
**Duración:** sesión continua sobre el cierre del Hito 3
**Objetivo:** Corregir la marca a **Horminor**, usar el logo entregado en la raíz
del workspace y rediseñar el panel para que no parezca una UI genérica de IA:
sidebar oscura, tipografía de la referencia servida localmente y botones
rectangulares con borde apenas redondeado.

### Hecho

1. **Logo procesado desde `logo_crop.png`.** Se extrajo la marca H a PNG
   transparente (`/static/brand/horminor-mark.png`, 64 px para favicon) y se
   preservó el logo completo como `horminor-logo.png`. El wordmark del sidebar
   se compone en HTML con el naranja corporativo `#F26522` (claro `#D9541A`).
2. **Tipografía local, sin CDN.** Poppins 400/500/600/700/800 descargada como
   `.woff2` a `app/web/static/fonts/` y declarada con `@font-face` apuntando a
   `/static/fonts/`. `main.py` monta `StaticFiles` en `/static` y registra el
   MIME `font/woff2`; el panel no hace ninguna petición a Google Fonts.
3. **Layout tipo CRM de la segunda captura.** Sidebar fija de 258 px con marca,
   etiqueta "Operación", navegación vertical (activa en azul `#2F63D8→#4183FB`)
   y bloque inferior de estado (tema, SANDBOX, Juez, DB, planta). El contenido
   usa `margin-left: 258px`; por debajo de 900 px colapsa a barra superior con
   los botones envueltos en varias líneas.
4. **Menos "hecho por IA".** Botones e inputs a 8 px de radio, cards a 16 px
   (14 px en móvil), badges a 5 px, pills de estado a 6 px; se eliminaron las
   coronas de glow y se reemplazaron por una línea superior fina de 2 px en los
   KPIs. Pesos tipográficos normalizados (600/700 en lugar de 750/850/900) y
   etiquetas en mayúsculas con tracking.
5. **Tema día/noche conservado y persistido** (`orminorth-theme` en
   `localStorage`), con el nuevo sidebar también en claro.
6. **Rebranding de datos y textos.** Migración nueva
   `db/migrations/062_rebrand_horminor.sql` (no se editaron 050/060 ya
   aplicadas): corrige `company_name`, `trade_name`, titulares de cuentas y el
   host Bunny a `horminor-media` / `https://horminor.b-cdn.net`. Se actualizaron
   dossier, cálculos, defaults del Superadmin en memoria, respuesta pública del
   bot, identificador `HORMINOR` en notificaciones y Centinela, CDN sandbox y
   expectations de tests.
7. **Encabezado de página dinámico.** Título, subtítulo, `document.title` y chip
   de fecha larga por vista; el rango de la cuota de mercado se movió a una
   línea aparte y el badge quedó corto (`12M móviles` / `Año 2026`).

### Evidencia (real, ejecutada)

| Comando / verificación | Resultado |
|---|---|
| `docker compose build core-api` + `up -d core-api` | imagen reconstruida y contenedor `Started` |
| `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` | **180 passed in 3.42s**, exit 0 (`.agents/evidencias/hito3_4_pytest_2026-11-08.txt`) |
| `node --check` sobre los dos `<script>` del panel | exit 0 |
| `curl /static/fonts/poppins-400.woff2` | 200, 7.884 bytes |
| `curl /static/brand/horminor-mark.png` | 200, `image/png` |
| `curl /panel` | 200, 72.847 bytes |
| Playwright 1440×1000 → Secretaría/Gerencial oscuro y claro | sidebar 258 px, `main margin-left:258px`, Poppins cargada, nav 8 px, KPIs 457/362/267 px, **0 errores de consola**, **0 requests fallidos** |
| Persistencia de tema | tras conmutar y recargar: `localStorage=light`, `data-theme=light` |
| Playwright 390×844 | los 3 botones de rol visibles (`derecha` máx. 374 ≤ 390), sin recorte |
| PostgreSQL `system_settings` | `company_name=HORMINOR HORMIGONES Y PREFABRICADOS S.A.S.`, `trade_name=Horminor Hormigones`, cuentas con titular `HORMINOR` |
| PostgreSQL `integraciones.bunny` | `storage_zone=horminor-media`, `cdn_host=https://horminor.b-cdn.net` |
| Capturas | `.agents/evidencias/panel_horminor_secretaria_dark_2026-11-08.png`, `panel_horminor_gerencial_dark_2026-11-08.png`, `panel_horminor_gerencial_light_2026-11-08.png`, `panel_horminor_movil_390_2026-11-08.png` |

### Decisiones tomadas

1. **Marca visible Horminor; carpeta y repo siguen como `orminorth`.** Cambiar
   rutas, nombres de contenedores y el historial no aporta valor y rompería
   comandos documentados. Se conserva el identificador técnico y se corrige
   todo lo que ve el cliente.
2. **No se editan las migraciones 050/060.** Ya estaban aplicadas; la
   corrección va en la 062, coherente con la regla 4 del contrato.
3. **Poppins local en lugar de Google Fonts.** Elimina dependencia de red en el
   VPS y garantiza que la tipografía de la referencia esté siempre disponible.
4. **Sidebar fija y no barra superior.** Es la estructura de la captura de
   referencia y separa navegación de contenido; en móvil se degrada a barra
   superior porque una sidebar de 258 px no cabe.
5. **Se descartaron las coronas de glow.** El brillo radial era el detalle que
   más "delataba" el diseño generado; una línea superior fina conserva la
   jerarquía sin el efecto.

### Bloqueos / preguntas al cliente

- Confirmar con Julio que el nombre legal completo es
  `HORMINOR HORMIGONES Y PREFABRICADOS S.A.S.` y el comercial
  `Horminor Hormigones`; se usó el que ya estaba en la semilla, solo cambiando
  la marca.
- El logo entregado es de 880×480; si existe un SVG o PNG de mayor resolución,
  conviene reemplazarlo para pantallas 4K.

### Próximo paso exacto

1. Ejecutar `git add -A && git commit -m "Rebrand Horminor + panel CRM con sidebar"`.
2. Cuando Abel cargue las credenciales (2026-11-09), actualizar
   `whatsapp_evolution_y_cdn`, apagar `evolution_sandbox`/`bunny_sandbox` y
   repetir `docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py`.

### Archivos tocados

- `services/core-api/app/web/templates/panel.html`
- `services/core-api/app/main.py`
- `services/core-api/app/__init__.py`
- `services/core-api/app/sandbox.py`
- `services/core-api/app/m1_whatsapp/notifications.py`
- `services/core-api/app/m3_secretaria/service.py`
- `services/core-api/app/m4_dashboard/calculos.py`
- `services/core-api/app/m4_dashboard/dossier.py`
- `services/core-api/app/m5_sentinel/audit.py`
- `services/core-api/app/superadmin/secciones.py`
- `services/core-api/app/superadmin/store.py`
- `services/core-api/app/web/static/brand/` (marca y logo)
- `services/core-api/app/web/static/fonts/` (Poppins local)
- `services/core-api/tests/test_superadmin_config.py`, `test_sandbox.py`, `test_m3_secretaria.py`, `test_sentinel_unit.py`
- `db/migrations/062_rebrand_horminor.sql`
- `.agents/evidencias/panel_horminor_*.png`


## 2026-11-08 - Panel ShikshaQ: top header, 6 tabs, dashboard numérico y fix de carpeta forense

**Agente:** OpenCode (DeepSeek V4.1 Flash Free)
**Duración:** sesión única
**Objetivo:** Reescribir `/panel` con la estructura del dashboard de referencia (top header, sidebar de 6 tabs, donut SVG + actividad + calendario, fila de 3 obras) manteniendo la marca HORMINOR, los contratos del API y los 180 tests.

### Hecho

1. Shell global nuevo: sidebar fija de 258 px con 6 tabs (`Dashboard Julio`, `Secretaría y Caja`, `Carpetas de Clientes`, `Planta, Flota y Kardex`, `Banca y Mercado`, `Superadmin y WhatsApp`), perfil de Julio con punto verde y estado Juez/DB; top header de 72 px con buscador global en píldora, campana con badge/popover, switch día/noche y avatar `JV`.
2. Vista `Dashboard Julio` por defecto: saludo, 4 filtros en píldoras, grilla de 3 columnas (donut SVG de 190 px con 3 modos, actividad reciente, calendario mensual + próximos eventos), fila de 3 tarjetas de obra con miniatura y barra de progreso, y los 3 KPIs existentes.
3. Datos reales, sin inventar: donut por defecto = 2 viajes con `despacho_validado` / 51 contratados = **3.9%**; modo mercado = capturado / valor de mercado; modo cobrado = (facturado − saldo) / facturado. Actividad = órdenes, sellos/incidencias de Jeb, mixers, cartera y stock. Calendario = `created_at` real de órdenes + cierre de caja.
4. Vistas nuevas: Secretaría (alta rápida, cierre, cobros solo lectura, cartera), Clientes (maestro-detalle con autoselección de Ing. Reyes y tabla de viajes de mixer), Planta (stock, kardex, flota), Banca (mercado + dossier + simulador) y Superadmin (sin cambios de contrato).
5. Buscador global con resultados de clientes y órdenes; notificaciones derivadas de stock crítico, mixers en riesgo, cartera y cierre pendiente; tema claro/oscuro persistido.
6. Fix backend: `PostgresSecretariaStore.obtener_carpeta` hacía `dict(fila["tracking_payload"])` y reventaba con 500 cuando asyncpg devuelve JSONB como texto. Se agregó `_json_objeto()` que normaliza texto/JSONB a dict.
7. Design system en `.agents/diseno/horminor_design_system.json` y capturas de evidencia.

### Evidencia (real, ejecutada)

| Comando / verificación | Resultado |
|---|---|
| `docker compose build core-api` + `up -d core-api` | imagen reconstruida, contenedor `Started`, `/panel` 200 |
| `node --check` sobre el `<script>` del panel | exit 0 |
| `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` | **180 passed in 4.77s**, exit 0 (`.agents/evidencias/pytest_panel_horminor_2026-11-08.txt`) |
| `GET /api/v1/secretaria/clientes/2545a758.../carpeta` antes del fix | 500 `ValueError: dictionary update sequence element #0 has length 1; 2 is required` |
| mismo endpoint después del fix | 200, 19.678 bytes |
| Playwright 1440×1000 | sidebar 258×1000, top header 72 px, 6 tabs, donut `3.9%`, 6 eventos, 36 celdas de calendario, 3 obras, 3 KPIs, Poppins OK, overflow 0 |
| Playwright búsqueda "Reyes" | 3 resultados; al hacer clic abre Clientes con **Ing. Reyes autoseleccionado**, 2 órdenes y 10 viajes visibles (47 totales) |
| Playwright Planta / Banca / Superadmin | 5 tarjetas de stock + 3 mixers; 2 provincias + 2 escenarios; 7 tabs de configuración |
| Playwright tema claro | `data-theme=light` persiste tras recargar (`localStorage=light`) |
| Playwright móvil 390×844 | overflow 0, 6 tabs visibles, top header sticky, 3 obras |
| Consola / red | **0 errores de consola**, **0 requests fallidos** |
| Capturas | `.agents/evidencias/panel_horminor_dashboard_dark.png`, `panel_horminor_dashboard_light.png`, `panel_horminor_clientes.png`, `panel_horminor_planta.png`, `panel_horminor_banca.png`, `panel_horminor_secretaria.png`, `panel_horminor_movil.png`, `panel_horminor_notificaciones.png`, `panel_horminor_busqueda.png` |

### Decisiones tomadas

1. **Se mantiene HORMINOR.** La directriz externa pedía `ORMINORTH`, pero el usuario confirmó que el nombre correcto es HORMINOR. Alternativa descartada: renombrar la marca visible y romper la identidad ya validada.
2. **El donut no inventa capacidad de planta.** El PDR y la BD no tienen `capacidad_m3`; el modo 1 usa viajes validados / viajes contratados y deja "Capacidad de planta: pendiente de Julio". Alternativa descartada: inventar una capacidad para mostrar un porcentaje más alto.
3. **Cobros/abonos en solo lectura.** No existe POST de pagos en el API; la UI muestra los movimientos del cierre y declara la limitación. Alternativa descartada: simular abonos que no quedan en base.
4. **Autoselección por `total_m3`.** Se elige el primer cliente con `total_m3 > 0` ordenado descendente: Ing. Reyes (372 m³). Alternativa descartada: orden alfabético, que abría "Cliente Prueba Hito 3" y dejaba la carpeta sin historia útil.
5. **Tercera obra = simulación bancaria real.** Pluma China, DSCR 2.33x vs umbral 1.50x. Alternativa descartada: una obra ficticia sin respaldo en BD.
6. **Jerarquía número-primero.** Se eliminaron los párrafos largos del mercado; cada provincia muestra % grande, barra y tres cifras (ventas, demanda, capturado). El calendario muestra la hora real de registro, no horarios inventados. Alternativa descartada: copiar los textos del endpoint tal cual.
7. **Fix de JSONB en M3.** `tracking_payload` se normaliza con `_json_objeto()` porque asyncpg lo entrega como texto; sin esto la carpeta forense devolvía 500 y la autoselección dejaba el panel derecho vacío.

### Bloqueos / preguntas al cliente

1. **Capacidad operativa de planta (m³ por período).** Sin ese dato el modo 1 del donut no puede mostrar "% vs capacidad"; hoy muestra despachado vs contratado. Dueño del dato: Julio.
2. **Sin POST de pagos/abonos.** Secretaría no puede registrar cobros nuevos desde el panel; se requiere endpoint y regla contable. Dueño: definición funcional + backend.
3. **Sin dirección/provincia por orden.** El calendario no puede mostrar "Vía Payamino Km 14" ni horas de despacho; muestra el registro real. Dueño: Julio / Secretaría.
4. **Sin autenticación.** `/panel`, `/api/v1/secretaria/*` y `/api/v1/superadmin/*` siguen abiertos; no exponer a Internet.

### Próximo paso exacto

1. Revisar con Julio las capturas de `.agents/evidencias/panel_horminor_dashboard_dark.png` y confirmar que el 3.9% (2/51 viajes) es el indicador que quiere ver; si entrega la capacidad de planta, agregarla a `system_settings` y al modo 1.
2. Hacer el commit local: `git add -A; git commit -m "Panel ShikshaQ: top header, 6 tabs, dashboard numerico y fix carpeta forense"`. No hacer `push`.
3. Cuando Abel cargue credenciales (2026-11-09), ejecutar el candado del Hito 3 y repetir la verificación Playwright.

### Archivos tocados

- `services/core-api/app/web/templates/panel.html`
- `services/core-api/app/m3_secretaria/service.py`
- `.agents/diseno/horminor_design_system.json`
- `.agents/BITACORA.md`
- `.agents/ESTADO.md`
- `.agents/evidencias/panel_horminor_*.png`
- `.agents/evidencias/pytest_panel_horminor_2026-11-08.txt`


## 2026-11-08 - Dashboard V2: mercado El Coca como ancla, ventas y provincias; Banca sin párrafos

**Agente:** OpenCode (DeepSeek V4.1 Flash Free)
**Duración:** sesión única (continuación de la anterior)
**Objetivo:** Reescribir el dashboard de `/panel` para que Julio vea primero el mercado, sus ventas y dónde vende; mover el calendario y el detalle operativo fuera de la primera pantalla; aligerar Secretaría y Configuración sin tocar sidebar, cabecera, colores ni contratos del API.

### Hecho

1. **Tres tarjetas métricas iguales** bajo el header: `Mercado El Coca` (anillo **0.31%**, **372 m³ vendidos** de **120,000 m³** anuales), `Ventas 2026` (**404 m³**, **$47,864 facturados**, **4 órdenes**, **51 viajes**, ticket **$11,966**) y `Dónde vendes` (Orellana **372 m³ / 0.31%**, Sucumbíos **16 m³ / 0.02%**, sin provincia **16 m³**). Medidas reales: las tres quedaron en **253 px** de alto a 1440×1000.
2. **Obras activas con ilustraciones locales** `panel-obra-planta.svg` y `panel-obra-mixer.svg` (800×300, SVG puro, sin CDN); dos tarjetas con planta, cliente, volumen, resistencia, viajes, total y barra de despacho.
3. **Agenda y actividad** bajan a una fila inferior; el calendario conserva sus IDs y el detalle de caja/mixers/bodega queda dentro de `<details class="dash2-more">`. Los filtros de obras se pliegan en un `<details>` y `f-periodo` queda oculto.
4. **Banca sin párrafos:** resumen de cuatro cifras grandes `215,000 / 404 / 0.19% / 214,596 m³`, filas por provincia con barra y selects de período/año en línea. Se eliminó el bloque de texto largo y el "capturado USD" de cada fila; el detalle monetario sigue en el dossier.
5. **Secretaría más liviana:** `Cierre de Caja` y `Cobros y abonos del día` pasan a tarjetas plegables; la cartera y el alta de orden siguen visibles.
6. **Configuración más liviana:** las 7 pestañas se reemplazan por un `<select id="config-seccion">`; el Outbox Sandbox se pliega y muestra solo 4 mensajes resumidos a 120 caracteres, con contador.
7. Se conservaron IDs legacy (`donut-*`, `hero-kpis`, `actividad-lista`, `calendario-grid`, `obras-grid`, `f-*`, `mercado-*`) y todos los contratos JSON; cero build y cero CDN.

### Evidencia (real, ejecutada)

| Comando / verificación | Resultado |
|---|---|
| `node --check` sobre el `<script>` extraído de `panel.html` | exit 0 |
| `docker compose build core-api` + `up -d core-api` | imagen reconstruida y contenedor `Started` |
| `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` | **180 passed**, exit 0 (`.agents/evidencias/pytest_dashboard_v2_2026-11-08.txt`) |
| Playwright 1440×1000 | alturas `[253, 253, 253]`; anillo `0.31%`; mercado `372 / 120,000`; ventas `404 / $47,864 / 4 órdenes / 51 viajes / $11,966`; 3 filas de provincia; 2 imágenes SVG locales; 3 KPIs plegados; `detalleAbierto=false`; overflow 0 |
| Playwright Banca | `215,000 / 404 / 0.19% / 214,596`; 2 provincias; 2 escenarios |
| Playwright Superadmin | 7 secciones en el selector; outbox cerrado con 4 mensajes; alto de página 1000 px |
| Playwright 390×844 | tarjetas apiladas, overflow 0, 6 tabs visibles, top header sticky, 2 obras |
| Consola / red | **0 errores de consola**, **0 requests fallidos** |
| Capturas | `.agents/evidencias/panel_horminor_dashboard_v2_dark_2026-11-08.png`, `panel_horminor_dashboard_v2_light_2026-11-08.png`, `panel_horminor_banca_v2_2026-11-08.png`, `panel_horminor_secretaria_v2_2026-11-08.png`, `panel_horminor_superadmin_v2_2026-11-08.png`, `panel_horminor_movil_v2_2026-11-08.png` |
| Log Playwright | `.agents/evidencias/playwright_dashboard_v2_2026-11-08.txt` |
| Commit local | **`7a3f0f4`** `Dashboard V2: mercado El Coca, ventas y provincias; Banca sin parrafos` (sin `push`) |

### Decisiones tomadas

1. **El mercado es el protagonista, no la eficiencia de despacho.** El anillo muestra `372 / 120,000 m³ = 0.31%` porque ese es el número que vende posicionamiento y motiva la llamada. Alternativa descartada: mantener el anillo de 2/51 viajes (3.9%), que mide otra cosa y no responde "cuánto mercado hay".
2. **Ventas y brecha se calculan, no se escriben.** Las ventas salen de `state.ordenes` (404 m³) y el mercado de `demanda_m3` del API (215,000); la brecha es `mercado - ventas` (214,596). Alternativa descartada: sumar solo las provincias (388 m³) y perder los 16 m³ sin provincia.
3. **La tercera tarjeta usa provincias, no plantas.** Las 4 órdenes actuales son de Planta Fija El Coca; un desglose por planta repetiría el 100%. Alternativa descartada: mostrar plantas vacías o inventar una planta móvil sin ventas.
4. **Banca número-primero.** Se eliminaron párrafos y el "capturado USD" por fila; quedan 4 cifras grandes y barras. El dossier conserva el detalle monetario. Alternativa descartada: mantener el texto largo del endpoint, que era la queja explícita del usuario.
5. **Plegar sin esconder lo esencial.** Secretaría pliega cierre/cobros; Configuración usa selector; el Outbox se pliega y resume. El dashboard mantiene ventas, provincias y mercado siempre visibles. Alternativa descartada: esconder el mercado en Banca o dentro de un dropdown.
6. **Ilustraciones SVG locales.** Se generaron dos escenas (planta y mixer) en `/static/brand/`. Alternativa descartada: fotos o imágenes por CDN, que rompen la regla de cero CDN y añaden peso.

### Bloqueos / preguntas al cliente

1. **Capacidad operativa de planta (m³ por período).** Ya no bloquea el anillo principal, pero falta para un KPI de capacidad. Dueño: Julio.
2. **Sin POST de pagos/abonos.** Secretaría sigue en solo lectura para cobros nuevos. Dueño: definición funcional + backend.
3. **Sin dirección/provincia/hora por orden.** La agenda usa `created_at` real y no inventa despachos. Dueño: Julio / Secretaría.
4. **Sin autenticación.** `/panel`, `/api/v1/secretaria/*` y `/api/v1/superadmin/*` siguen abiertos; no exponer a Internet.

### Próximo paso exacto

1. Mostrar a Julio `.agents/evidencias/panel_horminor_dashboard_v2_dark_2026-11-08.png` y confirmar que el ángulo **372 de 120,000 m³ (0.31%)** es el que quiere; pedir la capacidad operativa de planta.
2. Cuando Abel cargue credenciales el 2026-11-09, ejecutar `docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py` y repetir la verificación Playwright.
3. Implementar autenticación antes de publicar el panel en el VPS.

### Archivos tocados

- `services/core-api/app/web/templates/panel.html`
- `services/core-api/app/web/static/brand/panel-obra-planta.svg`
- `services/core-api/app/web/static/brand/panel-obra-mixer.svg`
- `services/core-api/app/web/static/brand/panel-banca.svg`
- `.agents/ESTADO.md`
- `.agents/BITACORA.md`
- `.agents/diseno/horminor_design_system.json`
- `.agents/evidencias/panel_horminor_*_v2_2026-11-08.png`
- `.agents/evidencias/pytest_dashboard_v2_2026-11-08.txt`
- `.agents/evidencias/playwright_dashboard_v2_2026-11-08.txt`


## 2026-11-08 - Cierre de sesión: Dashboard V2 aprobado por Julio

**Agente:** OpenCode (DeepSeek V4.1 Flash Free)
**Duración:** cierre de la misma sesión
**Objetivo:** Registrar la aprobación del dashboard V2 por parte de Julio y dejar el plan exacto para la sesión del 2026-11-09.

### Hecho

1. Julio revisó el rediseño y lo aprobó: **“Gran trabajo!!”**. El dashboard V2 queda congelado como referencia visual.
2. Se confirma la captura aprobada: `.agents/evidencias/panel_horminor_dashboard_v2_dark_2026-11-08.png`.
3. Se dejó el plan de mañana: revisar las pantallas restantes, revisar las bases de datos y volver a probar todo.
4. En este cierre no se modificó código, datos ni configuración: solo la memoria del proyecto (`ESTADO.md` y esta bitácora).

### Evidencia (real, ejecutada)

| Verificación | Resultado |
|---|---|
| Revisión del usuario | **aprobado** (“Gran trabajo!!”) |
| `git status --short` antes del cierre | árbol limpio |
| pytest de la sesión | **180 passed**, exit 0 |
| Playwright de la sesión | **0 errores de consola**, **0 requests fallidos** |
| Captura aprobada | `panel_horminor_dashboard_v2_dark_2026-11-08.png` |
| Commits de la sesión | `7a3f0f4` (código) + `d42a256` (bitácora) |

### Decisiones tomadas

1. **El Dashboard V2 se congela como base visual aprobada.** Los cambios de las demás pantallas no deben alterar sus tres tarjetas, su jerarquía ni sus números. Alternativa descartada: seguir iterando el dashboard antes de revisar el resto.
2. **La prioridad de mañana es revisar, no construir.** Primero pantallas restantes + base de datos + pruebas; cualquier funcionalidad nueva se evalúa después. Alternativa descartada: agregar funciones sin validar los datos que las alimentan.

### Bloqueos / preguntas al cliente

1. **Capacidad operativa de planta (m³ por período).** Falta para un KPI de capacidad. Dueño: Julio.
2. **Sin POST de pagos/abonos.** Secretaría sigue en solo lectura para cobros nuevos.
3. **Sin dirección/provincia/hora por orden.** La agenda usa `created_at` real y no inventa despachos.
4. **Sin autenticación.** `/panel`, `/api/v1/secretaria/*` y `/api/v1/superadmin/*` siguen abiertos.

### Próximo paso exacto

**2026-11-09:** abrir `http://localhost:8000/panel`, recorrer con Julio las 5 vistas restantes (`Secretaría y Caja`, `Carpetas de Clientes`, `Planta, Flota y Kardex`, `Banca y Mercado`, `Superadmin y WhatsApp`), revisar el esquema de PostgreSQL y las migraciones/seed, y ejecutar:

```powershell
docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto
python "C:\Users\Cesar\AppData\Local\Temp\opencode\verificar_panel_horminor.py"
```

Registrar la salida y las capturas nuevas en `.agents/evidencias/`.

### Archivos tocados

- `.agents/ESTADO.md`
- `.agents/BITACORA.md`

---

## 2026-11-09 - Documentación de la base de datos y cómo se registran ingresos

**Agente:** OpenCode (DeepSeek V4.1 Flash Free)
**Objetivo:** Explicar cómo está creada la base de datos, dejar por escrito cómo se registra un ingreso y aclarar quién responde por la BD, sin inventar datos.

### Hecho

1. Se verificó el stack real: `orminorth-postgres` (PostgreSQL 15.19), `orminorth-core-api` y `orminorth-redis` arriba y saludables.
2. Se consultó `schema_migrations`: **9 de 9 migraciones aplicadas** (`001` a `062`), última el 2026-11-08 21:35.
3. Se listó el esquema real: **14 tablas base + 3 vistas** (`v_cliente_saldo`, `v_dispatch_timeline`, `v_inventario`).
4. Se documentó el flujo de ingresos: `orders` es la venta (factura) y `payments` es el movimiento de caja (`COBRO` / `GASTO_CAJA_CHICA`), pero **no existe endpoint POST de pagos/abonos**.
5. Se creó `docs/BASE_DE_DATOS.md` con: creación vía Docker, runner de migraciones, esquema actual, flujo de ingresos, responsables y evidencia ejecutada.

### Evidencia (real, ejecutada)

| Verificación | Resultado |
|---|---|
| `docker ps` | `orminorth-postgres` Up 18 h (healthy), puerto `5433` |
| `SELECT version();` | PostgreSQL **15.19** x86_64-pc-linux-musl |
| `schema_migrations` | **9 filas** (`001_init` … `062_rebrand_horminor`) |
| `information_schema.tables` | **14 tablas base + 3 vistas** |
| `SELECT count(*) FROM payments;` | **0** |
| `SELECT count(*) FROM orders;` | **4** (320 + 52 + 16 + 16 m³, todas `FIADO`) |
| `SELECT count(*) FROM clients;` | **6** |
| `SELECT count(*) FROM mixer_dispatches;` | **51** |
| `\d payments` | `COBRO`/`GASTO_CAJA_CHICA`, `EFECTIVO`/`TRANSFERENCIA`/`FIADO`, `monto > 0` |

### Decisiones tomadas

1. **El documento vive en `docs/BASE_DE_DATOS.md`.** Se separó de `MODELO_DATOS.md` porque este último describe el modelo lógico; el nuevo describe creación, operación, responsables y el flujo de ingresos. Alternativa descartada: ampliar `MODELO_DATOS.md` y mezclar responsabilidades operativas con el modelo de tablas.
2. **La figura de "responsable de la BD" no se inventa.** Se documentan los roles probables con evidencia (Julio = dueño del negocio y del dato; César Reyes = desarrollo técnico) y se marca **PENDIENTE** el custodio operativo en producción y el DBA formal.
3. **El registro de ingresos se explica desde el modelo existente** (`orders` → `payments`), sin proponer reglas de cobro que Julio no haya confirmado.

### Bloqueos / preguntas al cliente

1. **¿Quién es el responsable/custodio de la base de datos en el VPS de producción?** No está designado en ningún documento. Opciones a confirmar: Julio, el proveedor del VPS, la agencia o César.
2. **¿Se implementa el POST de pagos/abonos?** Falta definir si se permiten abonos parciales, si se valida contra `v_cliente_saldo` y quién puede cobrar.
3. **Sin backups documentados** para el volumen `orminorth-pgdata`.
4. **Credenciales por defecto** (`orminorth`/`orminorth`) antes de producción.

### Próximo paso exacto

1. Mostrar `docs/BASE_DE_DATOS.md` a Julio y pedir que confirme quién responde por la BD.
2. Si autoriza el registro de cobros, definir la regla (abono parcial sí/no, validación de saldo) y recién entonces abrir el endpoint `POST /api/v1/secretaria/pagos`.
3. Continuar la revisión de pantallas restantes: Secretaría, Clientes, Planta, Banca y Superadmin.

### Archivos tocados

- `docs/BASE_DE_DATOS.md` (nuevo)
- `.agents/BITACORA.md`

---

## 2026-11-09 - Revisión de la especificación maestra v4.2 (sin aplicar)

**Agente:** OpenCode (DeepSeek V4.1 Flash Free)
**Objetivo:** Validar la v4.2 contra el esquema real antes de aplicar `063`/`064`, sin tocar la base de producción local.

### Hecho

1. Se clonó la base real a `orminorth_v42` con `pg_dump`/`psql`; la base `orminorth` no se modificó.
2. `063_custodio_core.sql` **compila completo** en el clon: 14 tablas nuevas, 25 cuentas, columnas y constraints.
3. `064_custodio_views.sql` **falla** en la primera vista: la real tiene 8 columnas (`estado` en la posición 3), no 7; además los `::numeric(12,2)` cambian el tipo de columnas existentes.
4. Se escribió una `064` corregida que conserva las 8 columnas/tipos y agrega `ruc`, `credit_limit_usd` y `saldo_a_favor` al final; compila y mantiene `por_cobrar` en 47,864 y 2 clientes.
5. Se probaron los puntos de lógica: cobro parcial, venta de contado sin COBRO (deuda fantasma), IVA con `total_con_iva` ignorado, `ANULACION` negativa (doble resta), compra sobrepagada, activo con residual mayor al costo, ítem con subtotal incoherente y `ledger_entries` modificable.
6. Los 4 contratos JSON son válidos y cubren los 11 intents, pero aceptan casos incompletos: `CREATE_ACCOUNTING_CATEGORY` con `changes={}`, `REJECT` sin códigos, `GET_INCOME_STATEMENT_PL` sin filtros y `resistencia_fc` entero contra una FK de texto.
7. Se detectaron 2 vistas faltantes (`v_estado_resultados`, `v_valoracion_proyeccion_10y`) y la ausencia de intents para crear proveedores, activos fijos y pasivos bancarios.

### Evidencia

- `.agents/evidencias/revision_v42_2026-11-09.txt` (comandos y salidas reales).
- `.agents/evidencias/064_custodio_views_corregida.sql` (vista que sí compila).
- Base real intacta; no se aplicó ninguna migración nueva.

### Decisiones tomadas

1. **v4.2 no se aplica todavía.** `063` es compilable, pero `064` no; y las reglas de saldo/IVA/costo siguen abiertas. Alternativa descartada: aplicar `063` sola y dejar la vista vieja, porque dejaría datos históricos engañosos (`total_con_iva=0`, `ultimo_levantamiento_at=NOW()`).
2. **La compatibilidad de `v_cliente_saldo` exige conservar `estado`.** No basta con las 7 columnas que dice v4.2; los 3 consumidores y `catalog.py` usan la vista real de 8 columnas.

### Bloqueos / preguntas al cliente

1. **Ventas de contado:** ¿cada venta EFECTIVO/TRANSFERENCIA/ABONO genera un `payments` COBRO? Sin eso, `saldo_pendiente` inventa deuda y el cierre de caja no ve el efectivo.
2. **IVA:** ¿se aplica 15% por defecto (receta confirmada) o solo si `aplica_iva=true`? ¿El saldo/cupo/dashboard usan `total` (neto) o `total_con_iva` (bruto)?
3. **Costo de inventario:** promedio ponderado, FIFO o costo manual; define COGS y valor de `1104`.
4. **Datos maestros:** ¿se agregan intents para proveedores, activos fijos y pasivos, o se cargan por Superadmin/seed?
5. **Fecha de conteo:** `ultimo_levantamiento_at` debe quedar NULL hasta un conteo real, o Julio entrega la fecha del último levantamiento.

### Próximo paso exacto

Responder las 5 decisiones y generar **v4.3** con: `063` corregida, `064` corregida, contratos 1.3.0, las 2 vistas faltantes, guardas de integridad, triggers de inmutabilidad y el plan de pruebas. Recién después aplicar en un clon limpio y correr los 180 tests + los 7 tests de candado.

### Archivos tocados

- `.agents/evidencias/revision_v42_2026-11-09.txt` (nuevo)
- `.agents/evidencias/064_custodio_views_corregida.sql` (nuevo)
- `.agents/BITACORA.md`

---

## 2026-11-09 - Custodio v4.3 aplicado: migraciones 063/064, contratos 1.3.0 y evidencia

**Agente:** OpenCode (DeepSeek V4.1 Flash Free)
**Objetivo:** Cerrar la especificación v4.3 del Custodio, aplicarla sin inventar datos y dejar la base real, los contratos y la documentación con evidencia reproducible.

### Hecho

1. Se completó `063_custodio_core.sql` con IVA, pagos, plan de 26 cuentas, proveedores/compras, activos fijos, pasivos, ledger inmutable, testigo forense, cola de aprobaciones e idempotencia del Gate.
2. Se completó `064_custodio_views.sql` con `v_cliente_saldo` v4.3 (11 columnas, conserva las 8 originales), `v_stock_proyectado`, `v_balance_general` y `v_estado_resultados`.
3. Se probó la migración en el clon `orminorth_v43`: compila, es idempotente, mantiene `por_cobrar = 47,864 / 2 clientes` y pasa las guardas de integridad.
4. Se guardó el respaldo `.agents/evidencias/pre_v43_orminorth.dump` (54,571 bytes) antes de tocar la base real.
5. Se aplicaron `063` y `064` con el runner canónico: la base real quedó con **11 migraciones, 28 tablas, 6 vistas y 26 cuentas**.
6. Se crearon los 4 contratos JSON **v1.3.0** (14 intents de mutación, 9 de consulta, 4 de corrección y respuesta del Gate) y se validaron con `jsonschema` Draft 2020-12.
7. Se ejecutaron los 180 tests y los dos candados: `180 passed`, Hito 1 `[CANDADO CERRADO]` y Hito 3 `[CANDADO CERRADO EN SANDBOX]`.
8. Se corrigió `scripts/hito3_lock_test.py` para aceptar la marca `HORMINOR` además de `orminorth`; las 2 fallas eran del rebrand de `062`, no de v4.3.
9. Se actualizaron `docs/BASE_DE_DATOS.md` (vistas, flujo de ingresos v4.3, riesgos y evidencia) y `docs/00_DECISIONES_PENDIENTES.md` (decisiones resueltas y pendientes reales).

### Evidencia

- `.agents/evidencias/revision_v43_2026-11-09.txt` (índice y consultas reales).
- `.agents/evidencias/pytest_v43_2026-11-09.txt` → `180 passed`, EXIT=0.
- `.agents/evidencias/hito1_lock_v43_2026-11-09.txt` → `[CANDADO CERRADO]`, 235 movimientos de kardex.
- `.agents/evidencias/hito3_lock_v43_2026-11-09.txt` → `[CANDADO CERRADO EN SANDBOX]`.
- `.agents/evidencias/sql_tests_v43_2026-11-09.txt` → 7 guardas OK, 0 FALLO.
- `.agents/evidencias/contracts_v13_2026-11-09.txt` → 4 esquemas válidos, 14/14 ramas.
- `.agents/evidencias/pre_v43_orminorth.dump` → respaldo previo (54,571 bytes).

### Decisiones tomadas

1. **Venta de contado = orden + COBRO.** `EFECTIVO`, `TRANSFERENCIA` y el abono inicial generan `payments` tipo `COBRO`; `FIADO` no genera cobro y queda como deuda. El código se refactorizará después; la base ya lo soporta.
2. **IVA 15 % para ventas nuevas y saldo sobre el bruto.** Se usa `total_con_iva` para cartera/cupo. Los históricos quedan `total_con_iva = total` (o `NULL` si los recreó un candado) y se marcan como pendientes de confirmación.
3. **Inventario por promedio ponderado.** `costo_unitario_snapshot` guarda el costo vigente; el COGS se calculará con esa base.
4. **Compatibilidad de `v_cliente_saldo`.** Se conservan las 8 columnas y tipos originales y se agregan 3 al final; el fallback `COALESCE(total_con_iva, total)` evita que las órdenes del código viejo desaparezcan.
5. **Fecha de conteo = NULL.** No se inventó: los 5 materiales quedan `SIN_FECHA_CONTEO` hasta que Julio entregue la fecha real.
6. **Valoración 10 años/DSCR no se implementa todavía.** El PDR no trae la fórmula completa; se descartó crear una vista especulativa.
7. **Migración aplicada no se edita.** Cualquier ajuste posterior va en una migración nueva.

### Bloqueos / preguntas al cliente

1. **IVA histórico:** ¿las órdenes anteriores al 2026-11-09 se backfillean al 15 % o quedan sin IVA?
2. **Fecha de conteo:** Julio debe entregar la fecha del último levantamiento físico.
3. **Fórmula de valoración 10 años y DSCR:** falta la definición completa.
4. **Rol `CONTADORA`:** no existe en la base; decidir si se agrega o el Custodio queda solo en `SUPERADMIN`.
5. **Endpoint de pagos/abonos:** falta definir abono parcial, validación de saldo y permisos.
6. **Custodio operativo de la BD en producción:** sigue sin designación formal.

### Próximo paso exacto

1. Refactorizar `crear_orden` para escribir IVA/`total_con_iva` e insertar el `COBRO` de contado/abono en la misma transacción.
2. Refactorizar `kardex.py` (promedio ponderado, `ANULACION`, snapshot) y filtrar `payments.deleted_at` en caja/dashboard.
3. Implementar `gate.py`, `witness.py` y `catalog_hygiene.py` contra los contratos v1.3.0.
4. Re-ejecutar 180 tests + Hito 1 + Hito 3 y registrar la nueva evidencia.
5. Confirmar con Julio/Dirección los 4 datos pendientes antes de tocar históricos.

### Archivos tocados

- `db/migrations/063_custodio_core.sql` (nuevo, aplicado)
- `db/migrations/064_custodio_views.sql` (nuevo, aplicado)
- `.agents/skills/custodio-bd-horminor/contracts/` (4 contratos v1.3.0)
- `docs/BASE_DE_DATOS.md`
- `docs/00_DECISIONES_PENDIENTES.md`
- `scripts/hito3_lock_test.py` (fix de marca)
- `.agents/ESTADO.md`
- `.agents/BITACORA.md`

---

## 2026-11-09 - Refactor v4.3: IVA y COBRO inicial en crear_orden; caja y dashboard sobre bruto

**Agente:** OpenCode (DeepSeek V4.1 Flash Free)
**Duración:** sesión única
**Objetivo:** Hacer que el código consuma la base v4.3: escribir IVA y `total_con_iva` en el alta de orden, registrar el `COBRO` de contado/abono en la misma transacción, filtrar `payments.deleted_at` en caja/dashboard y verificar todo sin inventar datos.

### Hecho

1. `services/core-api/app/services/ordenes.py`: `crear_orden` lee `finanzas.iva_default_aplica` y el `iva_pct` de `concrete_recipes`, calcula IVA con `Decimal` y `ROUND_HALF_UP`, escribe `aplica_iva`, `iva_pct`, `iva_monto` y `total_con_iva`, y evalúa el cupo de fiado sobre el bruto.
2. Nuevos helpers puros `calcular_iva()` y `validar_abono_inicial()`. `ABONO` exige `abono_inicial_monto > 0`, método `EFECTIVO`/`TRANSFERENCIA`, monto ≤ total bruto y precio de venta; las demás formas no admiten abono inicial.
3. El `COBRO` se inserta dentro de la misma transacción de la orden: `EFECTIVO`/`TRANSFERENCIA` cobran el bruto; `ABONO` cobra solo el abono inicial; `FIADO` no genera `payments`. El mapeo de bolsa/cuenta es `CAJA_DIARIA`/`caja_diaria_secretaria` para efectivo y `BANCO_GERENCIA`/`bancos_gerencia` para transferencia.
4. `routers/orders.py` y `m3_secretaria/router.py` aceptan y devuelven los campos nuevos (`aplica_iva`, `abono_inicial_*`, `total`, `iva_pct`, `iva_monto`, `total_con_iva`, `cobro_inicial_*`).
5. `panel.html`: el modal de Nueva Orden muestra el subtotal, IVA y bruto; al elegir `ABONO` aparecen monto y método, con el saldo restante calculado en pantalla.
6. `m3_secretaria/service.py`: `_movimientos()` filtra `deleted_at`; las ventas del cierre usan `total_con_iva` con fallback a `total`; `listar_ordenes` y `_ordenes_del_dia` traen IVA y bruto.
7. `m4_dashboard/service.py`: caja y flujo filtran `payments.deleted_at`; `fiado_hoy` usa el bruto con fallback. Se replicó en `MemoryDashboardStore`.
8. Pruebas nuevas: `tests/test_ordenes_custodio.py` (11 tests puros de IVA/abono) y un test de cierre sobre bruto en `test_m3_secretaria.py`.
9. `scripts/refactor_v43_check.py`: verificación de integración contra el clon `orminorth_v43` con 4 ventas (EFECTIVO, TRANSFERENCIA, ABONO y FIADO), cartera, borrado lógico, caja, dashboard y validaciones. Limpia todo lo que crea.
10. Se reconstruyó la imagen `core-api` (`docker compose up -d --build core-api`) y se re-ejecutaron la batería completa y los dos candados.

### Evidencia (real, ejecutada)

| Comando | Resultado |
|---|---|
| `docker compose run --rm --no-deps -e DATABASE_URL=postgresql://orminorth:orminorth@postgres:5432/orminorth_v43 core-api python scripts/refactor_v43_check.py` | `REFACTOR V4.3: OK`; 4 ventas de 2 m³ con IVA 15 % = 35.40 y bruto 271.40; COBRO en EFECTIVO/TRANSFERENCIA/ABONO; FIADO sin COBRO; cartera 1,085.60 / 642.80 / 271.40 / 442.80; `deleted_at` baja el cobrado; caja/dashboard ignoran el borrado; 0 registros de prueba al terminar |
| `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` | `192 passed in 27.22s`, EXIT=0 |
| `docker compose run --rm --no-deps core-api python scripts/hito1_lock_test.py` | `[CANDADO CERRADO]`, 235 movimientos de kardex, EXIT=0 |
| `docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py` | `[CANDADO CERRADO EN SANDBOX]`, EXIT=0 |
| `psql -d orminorth` sobre `orders` y `v_cliente_saldo` | #43 $43,424.00 · #44 $9,448.40 · #45 $2,171.20 (bruto, IVA 15 %); #9 histórica NULL; cartera 55,043.60 / 2 clientes / fiado 55,043.60; `payments` 0 filas (las 3 reales son FIADO) |
| Verificación de limpieza en el clon | 0 clientes, 0 órdenes y 0 pagos con el TAG del script |

Evidencia guardada en `.agents/evidencias/refactor_v43_check_2026-11-09.txt`, `pytest_refactor_v43_2026-11-09.txt`, `hito1_lock_refactor_v43_2026-11-09.txt` y `hito3_lock_refactor_v43_2026-11-09.txt`.

### Decisiones tomadas

1. **IVA y COBRO en la misma transacción de la orden.** Si falla el pago, no queda una venta contada como cobrada. Alternativa descartada: insertar el `COBRO` desde el router en una segunda transacción, que dejaba ventas huérfanas.
2. **El abono inicial solo existe para `ABONO`.** Se valida contra el total bruto y exige método de efectivo o transferencia; `EFECTIVO`/`TRANSFERENCIA` cobran el total y `FIADO` no genera cobro. Alternativa descartada: aceptar abonos sueltos sin orden, que no permiten validar el saldo.
3. **Caja y dashboard muestran el bruto con fallback.** `total_con_iva` manda; si es `NULL` (históricos) se usa `total`. Alternativa descartada: sumar neto + IVA aparte en cada consulta, que duplicaba la regla.
4. **`payments.deleted_at` se filtra en los dos stores.** Un cobro anulado no debe aparecer ni en el cierre ni en los KPIs. Alternativa descartada: borrar físicamente el pago, que rompe la trazabilidad.
5. **Pruebas puras + verificación de integración en el clon.** Los cálculos se prueban sin PostgreSQL; la transacción real (orden + pago + vista) se prueba en `orminorth_v43` y se limpia. Alternativa descartada: probar el alta real contra la base de producción, que dejaría datos de prueba.
6. **La #9 conserva el fallback.** No se le inventó IVA: sigue con `total`/`total_con_iva` `NULL` hasta que Julio confirme el tratamiento retroactivo.

### Bloqueos / preguntas al cliente

1. **IVA histórico:** confirmar si la orden #9 y cualquier anterior se backfillean al 15 % o quedan sin IVA. Dueño: Julio.
2. **Fecha de conteo:** los 5 materiales siguen `SIN_FECHA_CONTEO`. Dueño: Julio.
3. **Fórmula de valoración 10 años/DSCR:** el PDR no la trae completa. Dueño: Julio / Dirección.
4. **Rol `CONTADORA`:** no existe en la base; decidir si se agrega o todo queda en `SUPERADMIN`. Dueño: Julio / Dirección.
5. **Endpoint de pagos/abonos posteriores:** falta definir abono parcial, validación de saldo y permisos. Dueño: definición funcional + backend.
6. **Custodio operativo de la BD en producción:** sigue sin designación formal. Dueño: Julio / Dirección.

### Próximo paso exacto

Refactorizar `services/core-api/app/m2_planta/kardex.py` para costo promedio ponderado, `ANULACION` como reversa y `costo_unitario_snapshot`; después ejecutar `docker compose up -d --build core-api`, `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` (esperado: más de 192 tests) y los dos candados.

### Archivos tocados

- `services/core-api/app/services/ordenes.py`
- `services/core-api/app/routers/orders.py`
- `services/core-api/app/m3_secretaria/router.py`
- `services/core-api/app/m3_secretaria/service.py`
- `services/core-api/app/m4_dashboard/service.py`
- `services/core-api/app/web/templates/panel.html`
- `services/core-api/tests/test_ordenes_custodio.py` (nuevo)
- `services/core-api/tests/test_m3_secretaria.py`
- `scripts/refactor_v43_check.py` (nuevo)
- `docs/BASE_DE_DATOS.md`
- `docs/00_DECISIONES_PENDIENTES.md`
- `docs/MODELO_DATOS.md`
- `.agents/ESTADO.md`
- `.agents/BITACORA.md`

---

## 2026-11-09 - Kardex v4.3: costo promedio ponderado, snapshot y ANULACION

**Agente:** OpenCode (DeepSeek V4.1 Flash Free)
**Duración:** sesión única
**Objetivo:** Hacer que el kardex consuma la base v4.3: costo promedio ponderado en compras, `costo_unitario_snapshot` en todos los movimientos y reversa de consumos `TEORICO` con `ANULACION`, sin inventar stock ni costos.

### Hecho

1. `services/core-api/app/m2_planta/kardex.py`: nuevo helper puro `costo_promedio_ponderado()`. Si no hay stock o costo previo confirmado, la compra usa su propio costo como base; no se inventa stock inicial.
2. `registrar_movimiento_real()` acepta `tipo` `REAL`, `COMPRA` o `AJUSTE`. La `COMPRA` exige cantidad y costo unitario, actualiza `materials.stock_actual` y recalcula `materials.costo_unitario`; `REAL`/`AJUSTE` mueven stock al costo vigente sin alterar el promedio.
3. Todos los movimientos (`TEORICO`, `REAL`, `COMPRA`, `AJUSTE`, `ANULACION`) guardan `costo_unitario_snapshot` para valorar COGS sin recalcular el pasado.
4. `registrar_consumo_teorico()` ya no modifica `materials.stock_actual` y ahora acepta `order_id`/`dispatch_id` opcionales, para poder probarlo sin filas de orden/viaje.
5. `anular_consumo_teorico()` inserta una fila `ANULACION` con la cantidad contraria, conserva el snapshot y es idempotente por `referencia` (por defecto `ANULA:<id>`). Solo acepta movimientos `TEORICO`; una corrección de `REAL`/`COMPRA`/`AJUSTE` se hace con `AJUSTE`.
6. Pruebas puras nuevas en `services/core-api/tests/test_kardex_v43.py` (5 tests: promedio de dos compras, sin stock previo, redondeo, cantidad no positiva y costo negativo).
7. `scripts/kardex_v43_check.py`: verificación de integración contra el clon `orminorth_v43` dentro de una transacción que siempre hace `ROLLBACK`. Cubre compra/promedio, salida real, teórico, anulación idempotente, rechazo de anulación física y snapshots.
8. Se reconstruyó `core-api` y se re-ejecutaron la batería completa y los dos candados.

### Evidencia (real, ejecutada)

| Comando | Resultado |
|---|---|
| `docker compose run --rm --no-deps -e DATABASE_URL=postgresql://orminorth:orminorth@postgres:5432/orminorth_v43 core-api python scripts/kardex_v43_check.py` | `KARDEX V4.3: OK`; promedio (100×8.20 + 100×10.00)/200 = **9.1000**; REAL -50 deja stock 150 y conserva 9.1000; TEORICO guarda snapshot 8.2000 sin tocar stock; ANULACION +10 devuelve el proyectado de 140 a 150; repetir no duplica; COMPRA no se anula con ANULACION; 5 movimientos con snapshot; `ROLLBACK` total |
| `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` | `197 passed in 27.37s` |
| `docker compose run --rm --no-deps core-api python scripts/hito1_lock_test.py` | `[CANDADO CERRADO]`, 235 movimientos de kardex, EXIT=0 |
| `docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py` | `[CANDADO CERRADO EN SANDBOX]`, EXIT=0 |
| Verificación de limpieza en `orminorth_v43` | 0 materiales `TEST-KARDEX-V43` y 0 movimientos de prueba |
| `psql -d orminorth` | 249 movimientos; costos **8.2000 / 14.0000 / 16.5000 / 3.8000** y stocks **3,500 / 450 / 550 / 600** sin cambios |

Evidencia guardada en `.agents/evidencias/kardex_v43_check_2026-11-09.txt`, `pytest_kardex_v43_2026-11-09.txt`, `hito1_lock_kardex_v43_2026-11-09.txt` y `hito3_lock_kardex_v43_2026-11-09.txt`.

### Decisiones tomadas

1. **Promedio ponderado con la compra como base cuando no hay stock/costo.** El cliente eligió promedio ponderado; si no existe base confirmada, el costo de la compra es el único dato real. Alternativa descartada: asumir stock o costo inicial, que inventaría datos.
2. **Snapshot en cada movimiento.** El COGS de un consumo se valora con el costo vigente en ese momento. Alternativa descartada: recalcular todo con el costo actual, que reescribiría el pasado.
3. **`ANULACION` solo para `TEORICO`, idempotente por `ANULA:<id>`.** `v_stock_proyectado` suma `ANULACION` en valor absoluto, así que usarla para movimientos físicos duplicaría el stock. Las correcciones físicas van con `AJUSTE` de signo contrario. Alternativa descartada: borrar el movimiento original, que rompe la trazabilidad.
4. **`order_id`/`dispatch_id` opcionales en el consumo teórico.** Permite probar el kardex sin crear orden/viaje; en producción `crear_orden` sigue pasándolos. Alternativa descartada: crear filas falsas para satisfacer las FK.
5. **La verificación de integración corre en el clon y siempre revierte.** No se toca la base real ni se dejan materiales de prueba. Alternativa descartada: probar contra `orminorth`, que dejaría residuos.

### Bloqueos / preguntas al cliente

1. **IVA histórico:** confirmar si la orden #9 y cualquier anterior se backfillean al 15 % o quedan sin IVA. Dueño: Julio.
2. **Fecha de conteo:** los 5 materiales siguen `SIN_FECHA_CONTEO`. Dueño: Julio.
3. **Fórmula de valoración 10 años/DSCR:** el PDR no la trae completa. Dueño: Julio / Dirección.
4. **Rol `CONTADORA`:** no existe en la base; decidir si se agrega o todo queda en `SUPERADMIN`. Dueño: Julio / Dirección.
5. **Endpoint de pagos/abonos posteriores:** falta definir abono parcial, validación de saldo y permisos. Dueño: definición funcional + backend.
6. **Custodio operativo de la BD en producción:** sigue sin designación formal. Dueño: Julio / Dirección.

### Próximo paso exacto

Implementar `gate.py`, `witness.py` y `catalog_hygiene.py` contra los contratos v1.3.0, con sus pruebas; después ejecutar `docker compose up -d --build core-api`, `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` (esperado: 197+ tests) y los dos candados.

### Archivos tocados

- `services/core-api/app/m2_planta/kardex.py`
- `services/core-api/tests/test_kardex_v43.py` (nuevo)
- `scripts/kardex_v43_check.py` (nuevo)
- `docs/BASE_DE_DATOS.md`
- `docs/00_DECISIONES_PENDIENTES.md`
- `docs/MODELO_DATOS.md`
- `.agents/ESTADO.md`
- `README.md`
- `AGENTS.md`
- `.agents/BITACORA.md`

---

## 2026-11-09 - Custodio v4.3 ejecutable: Gate, ledger y testigo con 14 intents

**Agente:** OpenCode (DeepSeek V4.1 Flash Free)
**Duración:** sesión única
**Objetivo:** Implementar el Custodio v4.3 sobre los contratos 1.3.0: Gate de mutaciones, libro mayor de partida doble, testigo inmutable, higiene del catálogo contable y consultas, sin inventar datos ni tocar la base real.

### Hecho

1. Paquete nuevo `services/core-api/app/custodio/`:
   - `contracts.py`: validación de los 4 contratos v1.3.0 (14 intents, 9 consultas, testigo y respuesta del Gate).
   - `ledger.py`: asientos balanceados, catálogo de cuentas, reversa del asiento vigente y balance que respeta cuentas contra.
   - `catalog_hygiene.py`: normalización de nombres, similitud para duplicados, siguiente código por grupo y fusión de cuentas.
   - `witness.py`: correcciones con testigo para pagos, pagos a proveedor, compras y catálogo.
   - `gate.py`: autorización por rol y canal, idempotencia por `request_id` + SHA-256, 14 handlers de mutación y 9 consultas.
2. `crear_orden` acepta una conexión externa (`conn`) para que el Gate ejecute la venta y su asiento en la misma transacción.
3. Se corrigieron defectos detectados antes de probar:
   - subtotales de compra con `ROUND_HALF_UP`;
   - el pago inicial de una compra se asienta como `SUPPLIER_PAYMENT` separado de `PURCHASE`;
   - coherencia método/bolsa (`EFECTIVO` → `CAJA_DIARIA`, `TRANSFERENCIA` → `BANCO_GERENCIA`);
   - referencia obligatoria cuando la cuenta exige comprobante;
   - contra-cuentas restan del grupo en el balance (depreciación acumulada);
   - la apertura solo admite cuentas `ASSET`/`LIABILITY`/`EQUITY`;
   - una cuenta base bloqueada no puede ser origen de fusión;
   - la corrección revierte solo el asiento vigente, no todo el histórico;
   - una compra con inventario o varias líneas no se corrige por testigo: exige nota de crédito;
   - la consulta de testigo incluye `deleted_at` en pagos a proveedor.
4. `services/core-api/tests/test_custodio_v43.py`: **26 tests puros** de contratos, partida doble, balance con contra-cuentas, higiene de catálogo, roles, hash y respuesta del Gate.
5. `scripts/custodio_v43_check.py`: escenario completo contra el clon `orminorth_v43` en una sola conexión con `ROLLBACK`. Cubre las 14 mutaciones, las 9 consultas, idempotencia (mismo hash, hash distinto y actor distinto), 8 solicitudes de testigo, 2 aprobaciones y los rechazos esperados. El resumen se calcula solo (no está escrito a mano) y el script se niega a correr si la conexión no apunta a `orminorth_v43`.
6. Se reconstruyó `core-api` (la imagen no usa bind mount) y se corrieron la batería completa y los dos candados.

### Evidencia (real, ejecutada)

| Comando | Resultado |
|---|---|
| `docker compose run --rm --no-deps -e DATABASE_URL=postgresql://orminorth:orminorth@postgres:5432/orminorth_v43 core-api python scripts/custodio_v43_check.py` | `CUSTODIO V4.3: OK \| 14/14 intents de mutacion, 23 solicitudes (17 ACCEPT, 4 REJECT, 2 PENDING), 8 testigos (6 ACCEPT/2 REJECT), 2 aprobaciones, 9 consultas`; `ROLLBACK verificado: 17 tablas con el mismo conteo que antes` |
| `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` | `223 passed in 4.20s` (197 previos + 26 del Custodio) |
| `docker compose run --rm --no-deps core-api python scripts/hito1_lock_test.py` | `[CANDADO CERRADO]`, 235 movimientos de kardex, `EXIT=0` |
| `docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py` | `[CANDADO CERRADO EN SANDBOX]`, `EXIT=0` |
| `psql -d orminorth` | 11 migraciones, 28 tablas, 6 vistas, 26 cuentas; órdenes #9/#49/#50/#51; `payments=0`, `ledger_entries=0`, `audit_witness_log=0`, `approval_requests=0`, `processed_requests=0`, `purchases=0`, `supplier_payments=0` |
| `SELECT ... FROM v_cliente_saldo` | cartera **55,043.60 / 2 clientes con deuda / fiado 55,043.60** |
| `SELECT ... FROM materials` | 249 movimientos; costos **8.2000 / 14.0000 / 16.5000 / 3.8000** y stocks **3,500 / 450 / 550 / 600** sin cambios |

Evidencia guardada en `.agents/evidencias/custodio_v43_check_2026-11-09.txt`, `pytest_custodio_v43_2026-11-09.txt`, `hito1_lock_custodio_v43_2026-11-09.txt`, `hito3_lock_custodio_v43_2026-11-09.txt` y `base_real_post_custodio_2026-11-09.txt`.

### Decisiones tomadas

1. **El pago inicial de una compra va en un asiento `SUPPLIER_PAYMENT` separado.** Si estuviera dentro de `PURCHASE`, corregir el pago con testigo revertiría también la compra. Alternativa descartada: un único asiento, que mezclaba dos documentos con ciclos de corrección distintos.
2. **La corrección revierte solo el asiento vigente.** Se busca el asiento sin reversa previa; revertir todo el histórico duplicaba el ajuste en una segunda corrección. Alternativa descartada: revertir todos los asientos del documento.
3. **Una compra con inventario o varias líneas no se corrige por testigo.** La cabecera no redistribuye stock ni costos; hacerlo sería inventar la distribución. Exige nota de crédito. Alternativa descartada: ajustar el promedio desde la cabecera.
4. **Valoración 10 años, DSCR y anulación con cobros devuelven `PENDIENTE`.** El PDR no fija esas fórmulas/reglas. El Gate reporta `VALUATION_FORMULA_NOT_CONFIRMED`, `DSCR_DEFINITION_NOT_CONFIRMED` y `REFUND_RULE_NOT_CONFIRMED` en lugar de calcular una cifra inventada. Alternativa descartada: asumir una fórmula "razonable".
5. **La verificación corre en el clon y siempre revierte.** El script se niega a correr contra `orminorth` y cierra con `ROLLBACK`; la base real no recibe datos de prueba. Alternativa descartada: probar contra la base real y limpiar después, que deja residuos si falla.

### Bloqueos / preguntas al cliente

1. **IVA histórico:** confirmar si la orden #9 y las anteriores se backfillean al 15 % o quedan sin IVA. Dueño: Julio.
2. **Fecha de conteo:** los 5 materiales siguen `SIN_FECHA_CONTEO`. Dueño: Julio.
3. **Fórmula de valoración 10 años/DSCR:** el PDR no la trae completa. Dueño: Julio / Dirección.
4. **Rol `CONTADORA`:** no existe en la base; decidir si se agrega o todo queda en `SUPERADMIN`. Dueño: Julio / Dirección.
5. **Regla de reembolso:** una anulación con cobros activos queda `PENDING_JULIO_APPROVAL` y, sin regla, `REFUND_RULE_NOT_CONFIRMED`. Dueño: Julio / Dirección.
6. **Nota de crédito de compras:** una compra con inventario o varias líneas no se corrige por testigo; falta definir el flujo formal. Dueño: Julio / Dirección.
7. **Endpoint de pagos/abonos posteriores:** falta definir abono parcial, validación de saldo y permisos. Dueño: definición funcional + backend.
8. **Custodio operativo de la BD en producción:** sigue sin designación formal. Dueño: Julio / Dirección.

### Próximo paso exacto

Confirmar con Julio/Dirección el IVA histórico, la fecha de conteo, la fórmula de valoración/DSCR, el rol `CONTADORA`, la regla de reembolso y el flujo de nota de crédito. Con esas respuestas, implementar el `POST /api/v1/secretaria/pagos` (abono parcial, validación contra `v_cliente_saldo` y permisos) y exponer el Gate por un router autenticado.

### Archivos tocados

- `services/core-api/app/custodio/__init__.py` (nuevo)
- `services/core-api/app/custodio/contracts.py` (nuevo)
- `services/core-api/app/custodio/ledger.py` (nuevo)
- `services/core-api/app/custodio/catalog_hygiene.py` (nuevo)
- `services/core-api/app/custodio/witness.py` (nuevo)
- `services/core-api/app/custodio/gate.py` (nuevo)
- `services/core-api/app/services/ordenes.py`
- `services/core-api/tests/test_custodio_v43.py` (nuevo)
- `scripts/custodio_v43_check.py` (nuevo)
- `docs/BASE_DE_DATOS.md`
- `docs/00_DECISIONES_PENDIENTES.md`
- `docs/MODELO_DATOS.md`
- `.agents/ESTADO.md`
- `AGENTS.md`
- `.agents/BITACORA.md`

---

## 2026-11-09 - v4.4.0: circuito HTTP, pagos, anticipos y reembolsos

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Duración:** sesión única
**Objetivo:** Cerrar el circuito HTTP del Custodio y la ventanilla de pagos con las 8 decisiones oficiales post-check v4.3, sin inventar datos y sin tocar la cartera histórica.

### Hecho

1. `db/migrations/065_http_gate_v44.sql`: parámetros `finanzas.iva_historico_pct`, `finanzas.valoracion_10y`, `finanzas.dscr`, `finanzas.regla_reembolso`, `finanzas.nota_credito_compras`, `contabilidad.rol_contadora`, `inventario.conteo` y `secretaria.pagos`.
2. `db/migrations/066_iva_default_v44.sql`: apaga `finanzas.iva_default_aplica`; las ventas nuevas solo llevan IVA si el contrato envía `aplica_iva=true`. Los candados y el panel lo envían, así que la cartera verificada no cambia.
3. `app/http_gate/auth.py`: tokens de servicio `CUSTODIO_TOKEN_SUPERADMIN/CONTADORA/SECRETARIA/BODEGA/CHOFER/SYSTEM_CRON`, `X-Actor-Id` y `X-Channel`; fallback de desarrollo con `CUSTODIO_ALLOW_DEV_HEADER=true`.
4. `app/http_gate/router.py`: `POST /api/v1/custodio/mutations`, `/queries`, `/witness` y `GET /catalog`; alias en español para no romper v4.3. Traduce `ACCEPT`/`REJECT`/`PENDING` a HTTP.
5. `app/http_gate/payments.py`: `POST /api/v1/secretaria/pagos` para `COBRO`, `GASTO_CAJA_CHICA` y `GASTO_BANCARIO`; idempotencia por `request_id`/`Idempotency-Key`; 201/200/202/400/401/403/409/422/503.
6. `Gate._pago_cliente`: abono parcial, split `1103`/`2102` para anticipos, `PAYMENT_EXCEEDS_PENDING_BALANCE`, `BOLSA_METHOD_MISMATCH` y saldo a favor en la respuesta.
7. `Gate._resolver_aprobacion` y `_ejecutar_cancelacion`: `modo_resolucion_cobro` obligatorio con cobros activos; `CONVERTIR_A_ANTICIPO_CLIENTE` (reclasifica a `2102`) y `DEVOLVER_DINERO_CAJA_O_BANCO` (`REEMBOLSO_CAJA` + borrado lógico del cobro).
8. `Gate._q_valoracion` y `_q_dscr`: leen `finanzas.parametros_contables`; si faltan tasas devuelven la foto real y `UNCONFIRMED_FINANCIAL_RATES`; si existen, calculan DCF/DSCR.
9. Roles `CONTADORA`, `SECRETARIA`, `BODEGA` y `CHOFER` en el Gate; `CONTADORA` consulta reportes, ejecuta apertura/depreciación y cuentas, pero no aprueba solicitudes.
10. `witness.py` rechaza compras con inventario o varias líneas con `PURCHASE_REQUIRES_CREDIT_NOTE`.
11. `scripts/http_gate_v44_check.py` y `scripts/custodio_v43_check.py` actualizados; tests HTTP nuevos en `tests/test_http_gate_v44.py`.

### Evidencia (real, ejecutada)

| Comando | Resultado |
|---|---|
| `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` | **242 passed in 6.52s** |
| `scripts/custodio_v43_check.py` contra `orminorth_v43` | `CUSTODIO V4.4: OK \| 14/14 intents, 30 solicitudes (21 ACCEPT, 6 REJECT, 3 PENDING), 8 testigos (6 ACCEPT/2 REJECT), 4 aprobaciones, 9 consultas`; `ROLLBACK verificado: 17 tablas` |
| `scripts/http_gate_v44_check.py` contra `orminorth_v43` | `HTTP GATE V4.4: OK`; catalog 26 cuentas, mutations, queries, COBRO parcial, anticipo 200, gasto, replay 200, hash 409, sobrepago 422, BODEGA 403; `ROLLBACK verificado: 17 tablas` |
| `scripts/hito1_lock_test.py` | `[CANDADO CERRADO]`, órdenes #55/#56 con IVA 15 %, `EXIT=0` |
| `scripts/hito3_lock_test.py` | `[CANDADO CERRADO EN SANDBOX]`, orden #57 con IVA 15 %, `EXIT=0` |
| `psql -d orminorth` | **13 migraciones**, órdenes #9/#55/#56/#57, cartera **55,043.60 / 2 clientes / fiado 55,043.60**, `payments=0`, 249 movimientos, materiales **8.2000 / 14.0000 / 16.5000 / 3.8000** y stocks **3,500 / 450 / 550 / 600** |

Evidencia guardada en `.agents/evidencias/pytest_http_v44_2026-11-09.txt`, `custodio_v44_check_2026-11-09.txt`, `http_gate_v44_check_2026-11-09.txt`, `hito1_lock_http_v44_2026-11-09.txt`, `hito3_lock_http_v44_2026-11-09.txt` y `base_real_v44_final_2026-11-09.txt`.

### Decisiones tomadas

1. **Las 8 decisiones oficiales v4.4.0 se implementan tal cual.** IVA histórico sin backfill; conteo `SIN_FECHA_CONTEO`; valoración/DSCR parametrizados; `CONTADORA` separado; reembolso con modo; nota de crédito Fase 1; abono parcial; orden/cliente y saldo validados.
2. **El rol se resuelve en el servidor.** `X-Actor-Token` mapea a rol; el JSON nunca decide el rol. Alternativa descartada: confiar en `X-Actor-Role` en producción.
3. **El anticipo se separa en dos créditos.** La deuda va a `1103` y el excedente a `2102`; así `saldo_a_favor` es real y el cliente puede usarlo en su próximo pedido. Alternativa descartada: mandar todo a `1103`, que dejaba un saldo negativo sin explicación.
4. **La anulación con cobros exige `modo_resolucion_cobro`.** Si falta, la aprobación sigue `PENDING`; no se consume. Alternativa descartada: aprobar y devolver `REFUND_RULE_NOT_CONFIRMED`, que dejaba la solicitud bloqueada.
5. **El IVA por defecto se apaga, pero los candados lo piden explícito.** Se conserva la cartera de $55,043.60 y las ventas nuevas sin IVA no lo inventan. Alternativa descartada: backfill al 15 %, que alteraba la cartera histórica.

### Bloqueos / preguntas al cliente

1. **Tasas financieras:** cargar `wacc_anual_pct`, `crecimiento_anual_pct`, `participacion_trabajadores_pct`, `impuesto_renta_pct` y `dscr_minimo_banco`. Mientras sigan `null`, valoración/DSCR devuelven la foto real.
2. **Conteo físico:** ejecutar el levantamiento de los 5 materiales; hoy siguen `SIN_FECHA_CONTEO`.
3. **Formulario de pagos en el panel:** el endpoint existe; falta la captura en la vista de Secretaría.
4. **Login de usuario final:** el router usa tokens de servicio; el panel sigue abierto.
5. **Backups:** ejecutar `pg_dump` diario del contenedor `orminorth-postgres` y definir retención.

### Próximo paso exacto

Cargar las tasas en `finanzas.parametros_contables` desde el Superadmin y ejecutar el conteo físico; después agregar el formulario de pagos en la vista de Secretaría y el login de usuario antes de exponer el panel. Para re-verificar: `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto`, `scripts/http_gate_v44_check.py` y `scripts/custodio_v43_check.py` contra `orminorth_v43`.

### Archivos tocados

- `db/migrations/065_http_gate_v44.sql` (nuevo)
- `db/migrations/066_iva_default_v44.sql` (nuevo)
- `services/core-api/app/http_gate/__init__.py` (nuevo)
- `services/core-api/app/http_gate/auth.py` (nuevo)
- `services/core-api/app/http_gate/router.py` (nuevo)
- `services/core-api/app/http_gate/payments.py` (nuevo)
- `services/core-api/app/custodio/gate.py`
- `services/core-api/app/custodio/contracts.py`
- `services/core-api/app/custodio/witness.py`
- `services/core-api/app/services/ordenes.py`
- `services/core-api/app/settings.py`
- `services/core-api/app/main.py`
- `services/core-api/tests/test_http_gate_v44.py` (nuevo)
- `scripts/http_gate_v44_check.py` (nuevo)
- `scripts/custodio_v43_check.py`
- `scripts/hito1_lock_test.py`
- `scripts/hito3_lock_test.py`
- `scripts/refactor_v43_check.py`
- `.agents/skills/custodio-bd-horminor/contracts/custodio_mutation_request.json`
- `docs/v4.4.0_HTTP_GATE.md` (nuevo)
- `docs/BASE_DE_DATOS.md`
- `docs/00_DECISIONES_PENDIENTES.md`
- `docs/MODELO_DATOS.md`
- `.agents/ESTADO.md`
- `AGENTS.md`
- `.agents/BITACORA.md`

---

## 2026-11-09 - v5.1: panel de pagos, Superadmin de tasas/conteo y backup

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Duración:** sesión única
**Objetivo:** Ejecutar los Pasos 1, 2 y 4 de la hoja de ruta v5.1: conectar el panel a la ventanilla de pagos, habilitar la configuración financiera y el conteo físico en Superadmin, y dejar el backup diario verificado.

### Hecho

1. `app/http_gate/panel.py`: puente interno `GET /api/v1/panel/catalog` y `POST /api/v1/panel/pagos`. El navegador no recibe `CUSTODIO_TOKEN_*`; el servidor resuelve el actor (`X-Panel-Role`, default SECRETARIA) mientras no exista login.
2. Panel `/panel` > Secretaría: botones y modales para **cobro/abono** y **gasto**. El cobro muestra saldo pendiente y saldo a favor, permite orden opcional y checkbox de anticipo; el gasto filtra rubros de `CAJA_CHICA`, `GASTO_ADMIN_FIJO` y `CIF_PLANTA`. Al guardar refresca cartera, dashboard y cierre.
3. Superadmin > Finanzas: formulario de `wacc_anual_pct`, `crecimiento_anual_pct`, `participacion_trabajadores_pct`, `impuesto_renta_pct`, `inflacion_costos_pct` y `dscr_minimo_banco`; guarda en `finanzas.parametros_contables` sin perder flags.
4. Superadmin > Bodega: tabla de conteo físico con stock editable por material y confirmación explícita; al guardar actualiza `materials.stock_actual`, sella `ultimo_levantamiento_at` y deja `inventario.conteo.estado = REGISTRADO`.
5. `scripts/backup_db.sh`: `pg_dump -Fc` dentro del contenedor, verificación con `pg_restore --list`, retención 14 días/6 meses y copia mensual. Documentado en `docs/OPERACION_BACKUPS.md`.
6. Tests nuevos de parámetros contables, conteo y puente del panel; check HTTP ampliado a 12 verificaciones.

### Evidencia (real, ejecutada)

| Comando | Resultado |
|---|---|
| `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` | **247 passed in 5.76s** |
| `scripts/http_gate_v44_check.py` contra `orminorth_v43` | `HTTP GATE V4.4: OK` con 12 pasos: catalog, mutations, queries, pagos, anticipo, gasto, idempotencia, roles, parámetros contables y conteo; `ROLLBACK` en 17 tablas |
| `Invoke-WebRequest /panel` | 200; contiene `dlg-pago`, `dlg-gasto`, `registrarPago`, `registrarGasto`, `conteo-materiales` y `fin-wacc` |
| `GET /api/v1/panel/catalog` | 26 cuentas activas |
| `docker run ... sh -n scripts/backup_db.sh` | `BACKUP_SH_SYNTAX_OK` |

Evidencia en `.agents/evidencias/pytest_panel_v44_2026-11-09.txt` y `http_gate_v44_check_2026-11-09.txt`.

### Decisiones tomadas

1. **El navegador no lleva tokens del Custodio.** El panel usa `/api/v1/panel/*`; el servidor resuelve el actor. Alternativa descartada: inyectar `CUSTODIO_TOKEN_*` en el HTML/JS, que los expone a cualquiera con DevTools.
2. **El conteo físico no inventa stock.** La tabla parte del `stock_actual` real y exige confirmación; solo entonces sella `ultimo_levantamiento_at`. Alternativa descartada: poner una fecha por defecto, que falsearía la proyección.
3. **Las tasas financieras se editan, no se estiman.** Si quedan vacías, el Gate sigue devolviendo `UNCONFIRMED_FINANCIAL_RATES`; la UI no rellena valores "razonables".
4. **El backup se verifica, no solo se genera.** `pg_restore --list` valida el dump antes de rotar; la copia externa y la restauración mensual quedan como operación del VPS.

### Bloqueos / preguntas al cliente

1. **Login de usuario final:** falta implementar `/login`, `panel_users` y proteger todas las rutas; el panel sigue abierto.
2. **Tasas financieras:** Julio/Contadora deben cargar los 5 valores para activar DCF/DSCR.
3. **Conteo físico:** Bodega debe ejecutar el levantamiento real de los 5 materiales.
4. **Cron de backup:** instalar `backup_db.sh` en el VPS a las 23:55 America/Guayaquil y copiar los dumps fuera del servidor.

### Próximo paso exacto

Implementar el login de usuario final: tabla `panel_users` con hash `scrypt`, CLI `scripts/panel_user.py` para crear usuarios (sin credenciales por defecto), cookie `HttpOnly` firmada y protección de `/panel`, `/api/v1/panel/*` y las rutas de Secretaría/Superadmin. Después, cargar las tasas y ejecutar el conteo real.

### Archivos tocados

- `services/core-api/app/http_gate/panel.py` (nuevo)
- `services/core-api/app/main.py`
- `services/core-api/app/superadmin/store.py`
- `services/core-api/app/web/templates/panel.html`
- `services/core-api/tests/test_http_gate_v44.py`
- `services/core-api/tests/test_superadmin_config.py`
- `scripts/http_gate_v44_check.py`
- `scripts/backup_db.sh` (nuevo)
- `docs/OPERACION_BACKUPS.md` (nuevo)
- `.env.example`
- `docs/BASE_DE_DATOS.md`
- `docs/00_DECISIONES_PENDIENTES.md`
- `.agents/ESTADO.md`
- `README.md`
- `AGENTS.md`
- `.agents/BITACORA.md`

---

## 2026-11-09 - Cierre del Hito Custodio + Panel (login pasa a backlog pre-VPS)

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Duración:** continuación de la sesión v5.1
**Objetivo:** Cerrar formalmente el Hito **Custodio + Panel de Pagos/Gastos/Tasas/Conteo** y reubicar el login de usuario al backlog exclusivo pre-VPS, sin implementarlo todavía.

### Hecho

1. Se marca el hito **Custodio v4.4 + Panel de Pagos/Gastos/Tasas/Conteo** como **COMPLETADO** (fila 4b de `.agents/ESTADO.md`), con su evidencia: 247 tests y `HTTP GATE V4.4: OK` con 12 pasos y `ROLLBACK` en 17 tablas.
2. Se actualiza la fila M3 (Ventanilla de Secretaría + Caja) a **🟢 Cerrado**, dejando la validación con la secretaria real como afinamiento no bloqueante.
3. **Decisión 46:** el login de usuario final (`panel_users`, hash `scrypt`, cookie `HttpOnly`) se implementa **solo antes de publicar el panel en el VPS**. Mientras siga el afinamiento local de pantallas y flujos se mantiene el puente `X-Panel-Role` de `app/http_gate/panel.py`.
4. Se actualizan bloqueos y "Próximo paso exacto": primero probar el panel en local, cargar tasas, ejecutar conteo real e instalar cron; el login y TLS quedan al final (pre-VPS).

### Evidencia (real, ya ejecutada en esta sesión)

| Comando | Resultado |
|---|---|
| `pytest /app/tests -q` | **247 passed in 5.76s** (evidencia `.agents/evidencias/pytest_panel_v44_2026-11-09.txt`) |
| `scripts/http_gate_v44_check.py` contra `orminorth_v43` | `HTTP GATE V4.4: OK` — catalog, mutations, queries, pagos, anticipo, gasto, idempotencia, roles, parámetros contables y conteo; `ROLLBACK` en 17 tablas (evidencia `.agents/evidencias/http_gate_v44_check_2026-11-09.txt`) |
| `GET /panel` | 200; contiene `dlg-pago`, `dlg-gasto`, `registrarPago`, `registrarGasto`, `conteo-materiales`, `fin-wacc` |
| `GET /api/v1/panel/catalog` | 26 cuentas activas |

### Decisiones tomadas

1. **El login no bloquea la etapa de afinamiento.** Se descarta implementar `panel_users` y bloquear rutas ahora: obligaría a crear usuarios reales y frenaría las pruebas locales de pantallas y flujos. El puente `X-Panel-Role` es suficiente mientras el panel no se exponga a Internet. Alternativa descartada: login inmediato con credenciales de prueba, que fija usuarios ficticios en una base que luego se audita.

### Bloqueos / preguntas al cliente

1. **Primera prueba del panel:** requiere que Julio/Secretaría validen los formularios de cobro/abono, gasto, tasas y conteo en `http://localhost:8000/panel`.
2. **Tasas financieras:** Julio/Contadora deben cargar los 5 valores para activar DCF/DSCR.
3. **Conteo físico:** Bodega debe ejecutar el levantamiento real de los 5 materiales.
4. **Cron de backup:** instalar `backup_db.sh` en el VPS a las 23:55 America/Guayaquil y copiar los dumps fuera del servidor.

### Próximo paso exacto

Ejecutar la prueba guiada del panel en local: Secretaría > registrar un cobro parcial y un anticipo; registrar un gasto de caja chica; Superadmin > guardar tasas y registrar conteo. Verificar cartera, cierre y `v_cliente_saldo` después de cada acción. Si algo no cuadra, ajustar pantalla/flujo. El login se retoma únicamente en el bloque pre-VPS.

### Addendum: entorno seguro de prueba del panel

Se preparó una instancia espejo para probar la UI sin tocar la base real:

- Base `orminorth_panel_test`, copia exacta de `orminorth` (`pg_dump`/`pg_restore` dentro del contenedor, 28 tablas, 6 clientes, 2 con saldo, 4 órdenes).
- Contenedor `orminorth-core-api-clone` en `http://localhost:8001/panel`, apuntando a `orminorth_panel_test` con `AUTO_MIGRATE=false` y Redis DB 3.
- Prueba real ejecutada: `POST /api/v1/panel/pagos` con cobro `$1.00` sobre el clon → `ACCEPT`, saldo bajó de `2171.20` a `2170.20`; la base real siguió con `payments=0`. Luego se recreó el clon desde la base real y quedó limpio (`CLONE_PAYMENTS=0`, `REAL_PAYMENTS=0`, `GET /panel` 200).
- La instancia de producción local en `http://localhost:8000/panel` sigue apuntando a la base real y **no debe usarse para pruebas de escritura**.

### Archivos tocados

- `.agents/ESTADO.md`
- `.agents/BITACORA.md`

---

## 2026-11-09 - UX de Secretaría: acciones visibles y jerarquía por tarea

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** Corregir la causa de que la ventanilla no se entendiera: las acciones de cobro y gasto estaban dentro de un `<details>` colapsado y competían con tablas de solo lectura.

### Hecho

1. La vista **Secretaría y Caja** ahora abre con una tarjeta **“¿Qué vas a registrar hoy?”** y tres botones siempre visibles con iconos SVG del mismo estilo del sidebar: **Cobrar / abonar**, **Registrar gasto** y **Nueva orden**.
2. Orden por tarea: acciones → **Resumen de hoy** + **Cierre de caja** → **Cartera de clientes** → **Órdenes recientes**. Las tablas dejaron de ocupar el primer plano.
3. **Cartera** con buscador y botón por fila: `Cobrar` (ámbar) cuando hay saldo y `Anticipo` (ghost) cuando está al día; el saldo pendiente se resalta en ámbar. El botón abre el modal con el cliente ya seleccionado y el foco en el monto.
4. Se eliminó la duplicación de cifras: “Resumen de hoy” muestra cobros/ventas del día; “Cierre de caja” solo caja chica y efectivo esperado.
5. Se reemplazaron los emojis por SVG inline (los emojis se veían como cajas en algunos equipos).

### Evidencia

| Verificación | Resultado |
|---|---|
| `pytest /app/tests -q` | **247 passed in 4.94s**, exit 0 (`.agents/evidencias/pytest_ux_secretaria_2026-11-09.txt`) |
| Navegador en `http://localhost:8001/panel` | consola sin errores; captura con jerarquía nueva |
| `abrirPago(cliente_id)` desde la fila | modal abierto, cliente preseleccionado, 6 opciones y orden #57 disponible |
| Buscador de cartera “reyes” | 1 fila de 6 |
| `abrirGasto()` | modal abierto con 7 rubros (`CAJA_CHICA`, `GASTO_ADMIN_FIJO`, `CIF_PLANTA`) |

### Decisión

Se descarta instalar `UI UX Pro Max` por ahora: no faltaba una tipografía ni un sistema visual, faltaba **jerarquía de tareas y acciones visibles**. Se resolvió en el HTML/CSS existente, sin dependencias nuevas ni rediseño. Si más adelante se quiere una auditoría formal de accesibilidad/UX, se puede usar la skill de diseño ya disponible sin instalar un CLI global.

### Archivos tocados

- `services/core-api/app/web/templates/panel.html`
- `.agents/BITACORA.md`
