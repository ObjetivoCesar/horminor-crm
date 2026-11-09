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
