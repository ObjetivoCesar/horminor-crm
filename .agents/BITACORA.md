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

---

## 2026-11-09 - v6.0: compras, tope de caja chica, cierre y agenda real

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** Cerrar la operación diaria de la ventanilla: separar gasto de compra de material, poner tope a la caja chica, descontar compras del cierre y reemplazar el calendario decorativo por un motor real de entregas y ocupación de mixers.

### Hecho

1. **Migración 067** (`db/migrations/067_operacion_compras_y_agenda.sql`): columna `accounting_accounts.visible_en_ventanilla`, cuenta `1106_anticipos_sueldo_personal`, tope `secretaria.pagos.caja_chica_max_monto_usd = 100.00`, proveedor comodín `PROVEEDOR GENERAL (POR CLASIFICAR)` sin RUC y tabla `dispatch_schedule` con índices de fecha/mixer.
2. **Ventanilla curada:** el catálogo de gastos devuelve solo `5401`, `5301`, `5201` y `1106`; no se borró ninguna cuenta. El orden pone primero viáticos/caja chica y deja el anticipo al final. El modal de gasto muestra el tope, exige comprobante cuando la cuenta lo pide y ofrece autorización explícita de exceso.
3. **Compras separadas del gasto:** botón propio en Secretaría y en Planta. `POST /api/v1/panel/purchases` arma `REGISTER_PURCHASE` y debita `1104 Inventario de insumos`; soporta contado efectivo/transferencia, crédito y mixto, recepción inmediata o en tránsito. Se agregó alta de proveedor desde el mismo modal y recepción de compras en tránsito desde Planta.
4. **Tope de caja chica:** `POST /api/v1/panel/pagos` rechaza con `CAJA_CHICA_LIMIT_EXCEEDED` un gasto en efectivo que supere el tope. `autorizado_exceso_caja=true` lo permite y queda registrado en el pago.
5. **Cierre de caja popout:** el resumen muestra cobros, gastos, compras pagadas en efectivo y efectivo esperado; `calcular_resumen_caja` ahora recibe `supplier_payments` y resta `compras_efectivo`.
6. **Agenda real:** `app/m3_secretaria/agenda.py` calcula disponibilidad, próxima hora libre y choques por mixer con la regla `inicio_a < fin_b && inicio_b < fin_a`. `dispatch_schedule` guarda cliente, orden, planta, mixer, chofer, receta, volumen, duración, dirección, estado y motivo de reagendamiento. Endpoints GET/POST/PATCH/DELETE y `GET /agenda/disponibilidad`; el panel permite agendar, reagendar y cancelar, y muestra el calendario y las próximas entregas.
7. **Correcciones encontradas en la verificación:** se registró `NON_MONETARY_ACCOUNT_IN_PAYMENT` en el contrato; `_leer_setting` dejó de convertir arreglos JSON (flota de mixers) en `{}`; `hoy()` del panel usa fecha local y no UTC; el resumen de cierre y el calendario se actualizan tras guardar.

### Evidencia

| Verificación | Resultado |
|---|---|
| `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` | **265 passed in 4.96s** (`.agents/evidencias/pytest_v6_2026-11-09.txt`) |
| Migración en base real | `+ 067_operacion_compras_y_agenda.sql`; `schema_migrations` la reporta como última |
| `GET http://localhost:8000/panel` | HTTP 200; contiene `dlg-gasto`, `dlg-compra`, `dlg-cierre`, `dlg-agenda`, `recibirCompra` (`.agents/evidencias/panel_v6_2026-11-09.txt`) |
| Catálogo real | 4 cuentas: 5401, 5301, 5201, 1106; tope `100.00` |
| Pruebas en clon `orminorth_panel_test` | agenda creada 08:00-09:30; segundo POST 409 `MIXER_SCHEDULE_CONFLICT`; disponibilidad con 3 mixers; gasto de 150 bloqueado 422; cuenta `merma_ajuste_inventario` bloqueada `NON_MONETARY_ACCOUNT_IN_PAYMENT`; compra en efectivo 41.00 y cierre con `compras_efectivo=41.0` (`.agents/evidencias/clone_v6_2026-11-09.txt`) |
| Navegador en `http://localhost:8001/panel` | consola sin errores; compra UI, agenda UI, cierre y recepción en Planta verificados; calendario muestra la entrega agendada |
| Base real después de la migración | `payments=0`, `purchases=0`, `dispatch=0`; sin datos de prueba |
| Respaldo previo | `.agents/evidencias/orminorth_pre_067_2026-11-09.dump` |

### Decisiones

1. **No se borran cuentas:** la ventanilla se cura con `visible_en_ventanilla`; las 26 cuentas históricas siguen disponibles para contabilidad y reportes.
2. **El anticipo de sueldo es un activo, no un gasto:** se creó `1106` (1105 ya es IVA crédito) y el Gate lo acepta como movimiento de ventanilla sin relajar la regla de tipo `EXPENSE`.
3. **Secretaría puede registrar compras:** se amplió `REGISTER_PURCHASE` y `CREATE_SUPPLIER` a `SECRETARIA`/`CAJA_SECRETARIA` porque la compra se captura en la ventanilla; la recepción física sigue reservada a `BODEGA`/`BODEGA_PLANTA`.
4. **El tope es parámetro, no código:** vive en `system_settings` para que Superadmin lo ajuste sin despliegue. El valor 100.00 es el del plan y queda pendiente de confirmación de Julio.
5. **Comodín sin RUC:** el proveedor genérico se crea con `identificacion NULL`; no se inventó un RUC. Se reemplaza cuando Julio entregue la lista real.
6. **Agenda en tabla propia:** `dispatch_schedule` separa la programación de la orden; un bloque sin mixer no reserva una máquina concreta hasta que Secretaría asigne una.

### Bloqueos / preguntas al cliente

1. Julio debe entregar la lista real de proveedores (RUC, teléfono) para reemplazar el comodín.
2. Confirmar el tope de caja chica (`$100.00`) y si las compras en efectivo deben tener el mismo límite o uno propio.
3. Confirmar horario de planta, duración estándar de entrega y reglas de disponibilidad (hoy son parámetros editables; 90 min por defecto).
4. El calendario del Dashboard sigue leyendo `orders.created_at`; la agenda operativa ya es real en Secretaría. Conectar el Dashboard a `state.agenda` queda como siguiente afinamiento visual.

### Próximo paso exacto

Abrir `http://localhost:8000/panel` en Secretaría y registrar una compra de cemento con el proveedor comodín: verificar que el stock suba, que el cierre reste la compra en efectivo y que el agendamiento de una entrega bloquee el mixer. Después cargar los proveedores reales desde el Superadmin o el modal de compra.

### Archivos tocados

- `db/migrations/067_operacion_compras_y_agenda.sql`
- `services/core-api/app/m3_secretaria/agenda.py`
- `services/core-api/app/m3_secretaria/service.py`
- `services/core-api/app/custodio/contracts.py`
- `services/core-api/app/custodio/gate.py`
- `services/core-api/app/http_gate/panel.py`
- `services/core-api/app/http_gate/payments.py`
- `services/core-api/app/web/templates/panel.html`
- `services/core-api/tests/test_agenda_v6.py`
- `services/core-api/tests/test_panel_v6.py`
- `services/core-api/tests/test_m3_secretaria.py`
- `.agents/ESTADO.md`
- `.agents/BITACORA.md`
- `.agents/evidencias/`

---

## 2026-11-09 - v6.2: HorminorAgenda unica, configuracion operativa y perfiles ACL

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** Unificar el calendario real de entregas en un componente, mover caja/horarios a Superadmin y agregar perfiles con checklist de modulos y simulador de vista.

### Hecho

1. **Componente unico `HorminorAgenda`** (`app/web/static/horminor-agenda.js`): calendario + lista + cola de planta, montado con `HorminorAgenda.mount(selector, config)` en Dashboard (`JULIO`), Secretaria (`SECRETARIA`) y Planta (`PLANTA_CHOFER`). Cualquier alta/edicion/cancelacion dispara `horminor:agenda-updated` y refresca las tres vistas. El Dashboard ya no usa `orders.created_at` ni el calendario decorativo.
2. **Servicio backend unico** (`app/agenda/`): `evaluar_disponibilidad`, `conflicto_mixer`, `validar_ventana`, `mixers_activos` y `PostgresAgendaStore`. `app/m3_secretaria/agenda.py` queda como fachada de compatibilidad. Toda la agenda lee `dispatch_schedule` y `system_settings['agenda.parametros']`.
3. **Superadmin operativo en caliente:** endpoints `GET/PUT /api/v1/superadmin/operacion/config` y tarjetas en la UI para `caja_chica_max_monto_usd`, `compras_efectivo_max_monto_usd`, `fondo_base_caja_chica_usd`, `hora_apertura`, `hora_cierre`, `duracion_entrega_default_min`, `intervalo_slot_min` y `dias_laborables`.
4. **Tope de compra en efectivo:** `POST /api/v1/panel/purchases` rechaza con `PURCHASE_CASH_LIMIT_EXCEEDED` cuando el pago desde `CAJA_DIARIA` supera el parametro.
5. **Perfiles ACL:** migracion 068 crea `panel_users_acl` con 5 perfiles semilla (Julio, Secretaria, Auditor Externo, Vendedor, Bodega). CRUD en `/api/v1/superadmin/usuarios`, checklist de 10 modulos y `EMPTY_MODULE_CHECKLIST` cuando no se marca ninguno.
6. **Simulador de vista:** selector `Viendo como` en `/panel`; guarda `X-Panel-User` en `localStorage` y lo envia en cada peticion. El panel oculta pestañas/acciones por modulo y el backend devuelve `403 READ_ONLY_PROFILE` o `403 MODULE_NOT_ALLOWED` segun el perfil.
7. **Pruebas nuevas:** `test_v62_agenda_config_acl.py` cubre componente unico, configuracion en caliente, disponibilidad con nuevo horario, checklist vacio, auditor solo lectura y vendedor con modulos limitados.

### Evidencia

| Verificacion | Resultado |
|---|---|
| `pytest /app/tests -q` | **270 passed in 5.67s** (`.agents/evidencias/pytest_v62_2026-11-09.txt`) |
| Migracion real | `068_agenda_config_y_usuarios_acl.sql` aplicada; `schema_migrations` la reporta como ultima |
| `GET /panel` real | HTTP 200; contiene `horminor-agenda.js`, `agenda-mount-dashboard`, `agenda-mount-secretaria`, `agenda-mount-planta`; sin `calendario-grid` ni `eventosCalendario` (`.agents/evidencias/panel_v62_2026-11-09.txt`) |
| Config real | caja 100/300/200; agenda 07:00-18:00, 90 min, slot 30, LUN-SAB |
| Perfiles reales | 5 semillas: Julio (10 modulos), Secretaria (6), Auditor (4, SOLO_LECTURA), Vendedor (3), Bodega (3) |
| Pruebas en clon | config 150/450 y 06:30-19:00 aplicada en vivo; disponibilidad 06:30 libre; agenda creada 08:00-09:30; segundo POST 409 `MIXER_SCHEDULE_CONFLICT`; auditor POST 403 `READ_ONLY_PROFILE`; checklist vacio 422 `EMPTY_MODULE_CHECKLIST` (`.agents/evidencias/v62_clone_2026-11-09.txt`) |
| Navegador `http://localhost:8001/panel` | sin errores de consola; calendario Dashboard/Secretaria/Planta sincronizado; selector Vendedor muestra solo Secretaria/Clientes y Nueva Orden; Auditor en solo-lectura sin acciones |
| Base real | `payments=0`, `purchases=0`, `dispatch=0`; sin datos de prueba |
| Respaldo previo | `.agents/evidencias/orminorth_pre_068_2026-11-09.dump` |

### Decisiones

1. **Un solo backend de agenda:** la logica se movio a `app/agenda/` y `m3_secretaria/agenda.py` solo reexporta. Alternativa descartada: mantener dos copias para Dashboard y Secretaria, que garantiza divergencia.
2. **El contrato de perfiles no bloquea el login:** el selector simula usuarios con `X-Panel-User`. Sin header se conserva el comportamiento historico (Superadmin con todos los modulos) para no romper scripts ni tests. El login real sigue en el backlog pre-VPS.
3. **Los permisos se validan dos veces:** la UI oculta modulos/acciones y el backend rechaza mutaciones (`READ_ONLY_PROFILE`) y modulos no permitidos (`MODULE_NOT_ALLOWED`). Ocultar en HTML no es seguridad.
4. **El tope de compra en efectivo es independiente del tope de gasto:** el plan fija 300.00 para compras y 100.00 para gastos; ambos viven en `secretaria.pagos` y se editan en la misma tarjeta.
5. **Los seeds de perfiles son provisionales:** nombres y checklist son puntos de partida editables; no se crean usuarios con contrasena ni se activa autenticacion.

### Bloqueos / preguntas al cliente

1. Julio debe confirmar los 5 perfiles semilla y el checklist real de cada rol (especialmente Auditor Externo y Vendedor).
2. Confirmar topes definitivos: gasto en efectivo, compra en efectivo y fondo base de caja chica.
3. Confirmar horario real de planta, duracion estandar y dias laborables; hoy quedan 07:00-18:00, 90 min y LUN-SAB.
4. El login real y el despliegue VPS siguen fuera de esta entrega.

### Proximo paso exacto

Entrar a `http://localhost:8000/panel` > Superadmin > Usuarios y Permisos de Modulos, ajustar el checklist de Secretaria/Vendedor/Auditor y probar cada uno con el selector "Viendo como". Luego registrar una reserva desde el Dashboard y verificar que aparece en Secretaria y en la cola de Planta filtrada por mixer.

### Archivos tocados

- `db/migrations/068_agenda_config_y_usuarios_acl.sql`
- `services/core-api/app/agenda/` (nuevo paquete)
- `services/core-api/app/panel_acl.py`
- `services/core-api/app/superadmin/operacion.py`
- `services/core-api/app/superadmin/usuarios.py`
- `services/core-api/app/http_gate/panel.py`
- `services/core-api/app/http_gate/payments.py`
- `services/core-api/app/m3_secretaria/agenda.py`
- `services/core-api/app/m3_secretaria/router.py`
- `services/core-api/app/routers/catalog.py`
- `services/core-api/app/routers/orders.py`
- `services/core-api/app/main.py`
- `services/core-api/app/web/templates/panel.html`
- `services/core-api/app/web/static/horminor-agenda.js`
- `services/core-api/tests/test_v62_agenda_config_acl.py`
- `.agents/ESTADO.md`
- `.agents/BITACORA.md`
- `.agents/evidencias/`

---

## 2026-11-09 - v6.4: rediseño UX de Superadmin por Action Cards

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** Llevar a Superadmin la misma jerarquía visual de Secretaría: acciones visibles, formularios bajo demanda y acceso directo a usuarios, sin JSON crudo ni textos `null`.

### Hecho

1. **Banner `CENTRO DE CONTROL`** con el mismo componente visual de Secretaría (`sec-ventanilla`, `sec-acciones`, `sec-accion primary`). Cuatro Action Cards:
   - `Usuarios y accesos` (destacada) -> modal de perfiles con checklist de 10 módulos.
   - `Caja chica y horarios` -> modal de topes, fondo base, horario, duración, intervalo y días laborables.
   - `Recetas, flota y precios` -> modal con tablas humanas: cada receta y cada mixer se edita con inputs; el precio por m³ y el IVA están en la misma fila.
   - `Tasas y conteo de silos` -> modal de parámetros contables y levantamiento físico.
2. **Dos tarjetas resumen debajo del banner**:
   - `Perfiles y Accesos`: filas de los usuarios con avatar, módulos activos, badge `EDICIÓN`/`SOLO LECTURA`, botones `Probar vista` y `Editar permisos`, y `+ Crear usuario`.
   - `Canal WhatsApp y reglas vigentes`: simulador, outbox y resumen compacto de tope de gasto, tope de compra, horario de planta y estado del conteo de silos.
3. **Selector `Viendo como:`** convertido en pill clicable en la barra superior, con todos los perfiles y la opción directa `+ Crear / gestionar usuarios…`.
4. **Cero JSON crudo y cero `null` visible**:
   - Se retiró la tarjeta genérica de configuración en caliente y sus textareas JSON.
   - Los parámetros contables vacíos muestran `placeholder="Sin definir (ej. 12.5%)"` y `value=""`.
   - Recetas y flota usan inputs numéricos/texto por celda; no hay textarea de configuración.
   - El simulador ya no muestra el bloque de JSON del pipeline.
5. **Pruebas nuevas:** `test_v64_superadmin_ux.py` verifica las 4 Action Cards, los 4 modales, las tarjetas resumen, el selector con acceso directo y la ausencia de `data-json`, `placeholder="null"` y textos JSON de recetas/flota.

### Evidencia

| Verificacion | Resultado |
|---|---|
| `pytest /app/tests -q` | **272 passed in 5.86s** (`.agents/evidencias/pytest_v64_2026-11-09.txt`) |
| `GET /panel` real | HTTP 200; 4 action cards, 4 modales, perfiles y reglas presentes (`.agents/evidencias/panel_v64_2026-11-09.txt`) |
| Consola del navegador | sin errores; cambio a Auditor aplica solo lectura y oculta la agenda del Dashboard |
| Modal Usuarios | 5 perfiles, 10 checkboxes, boton `+ Crear nuevo usuario` |
| Modal Caja | 100/300/200 y horario 07:00-18:00 con 6 dias marcados |
| Modal Recetas | 5 recetas y 3 mixers editables, 0 textareas |
| Modal Tasas | WACC vacio con placeholder humano, 0 inputs con `null`, 5 materiales para conteo |
| Guardado real en clon | 5 recetas y 3 mixers guardados; caja 120/350 reflejada en reglas al instante |
| Base real | `payments=0`, `purchases=0`, `dispatch=0`; sin datos de prueba |

### Decisiones

1. **La tarjeta genérica de configuración en caliente sale de la vista principal.** Las secciones tecnicas (WhatsApp/Evolution, empresa/bot, directorio y umbrales de bodega) siguen disponibles por sus endpoints de Superadmin, pero ya no se muestran como textareas JSON. Si Julio necesita editarlas desde el panel, el siguiente paso es un modal `Avanzado` con formularios humanos, no volver al JSON.
2. **Las tablas de recetas y flota usan los endpoints existentes de upsert.** No se creo un endpoint nuevo ni se duplico la logica de `_normalizar_receta`/`_normalizar_mixer`.
3. **El selector superior es la unica fuente de simulacion.** La opcion `+ Crear / gestionar usuarios…` abre el mismo modal que la Action Card 1; no hay rutas paralelas.
4. **El resumen de reglas es de solo lectura.** Los cambios se hacen en los modales de caja/horarios o en la configuracion de conteo, no en la tarjeta resumen.

### Bloqueos / preguntas al cliente

1. Validar con Julio los textos y el orden de las 4 Action Cards.
2. Confirmar si las secciones tecnicas (WhatsApp, empresa, directorio, umbrales de bodega) deben volver a la UI como un modal `Avanzado` humano o quedarse por API.
3. Los topes y horarios siguen siendo parametros provisionales hasta la confirmacion del cliente.

### Proximo paso exacto

Abrir `http://localhost:8000/panel` > Superadmin, probar las 4 tarjetas y el selector `Viendo como`; luego crear un usuario desde la Action Card 1 y verificar que `Probar vista` aplica el checklist sin recargar la pagina.

### Archivos tocados

- `services/core-api/app/web/templates/panel.html`
- `services/core-api/tests/test_v64_superadmin_ux.py`
- `.agents/ESTADO.md`
- `.agents/BITACORA.md`
- `.agents/evidencias/`

---

## 2026-11-09 - v6.6: Carpetas de Clientes, buscador Sabueso y tutoriales

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** Rediseñar Carpetas de Clientes para cientos de clientes, con filtros rápidos, búsqueda multi-variable y expediente ordenado; dejar la base de tutoriales para el futuro bot.

### Hecho

1. **Banner `CARTERA Y EXPEDIENTES`** con 4 Action Cards y contadores en vivo:
   - `Con deuda / Fiado`: clientes con saldo y monto total por cobrar.
   - `En obra / Entregas activas`: órdenes recientes o agenda vigente.
   - `Pagos y Transferencias`: cobros registrados o saldo a favor.
   - `Todos y Prospectos`: padrón completo y leads; segundo clic abre `+ Nuevo cliente`.
2. **Buscador Sabueso** (`GET /api/v1/clients/search`):
   - Normalización de tildes y equivalencias b/v, z/s/c, ll/y.
   - Tokens en cualquier orden (`reyes ing`, `ing reyes`).
   - Patrones `7m3`, `7 m3`, `16m3`, `FC-210`, `FC 210`, `#56`.
   - Cruce con nombre, constructora, ciudad, obra frecuente, notas, órdenes, agenda y pagos.
   - `match_hint` con la orden/entrega/pago que explica la coincidencia.
   - Autocompletado a partir de 2 caracteres.
3. **Filtros combinables y paginación:** ciudad/sector, forma de pago, fecha (hoy/semana/mes/rango), resistencia, rango de m³ y orden (deuda/actividad/volumen/nombre). Lista paginada de 12 con `« Anterior | Pág X de Y | Siguiente »`.
4. **Expediente derecho en 3 pestañas:** `Órdenes y Viajes` con viajes desplegables solo de la orden elegida, `Pagos y Estado de Cuenta` con cobros/abonos/anticipos, y `Ficha y Datos` editable (ciudad, obra frecuente, cupo, notas).
5. **Migración 069** (`069_clientes_sabueso.sql`): columnas `ciudad` y `direccion_obra`, índices de ciudad/obra y prefijo normalizado para el buscador.
6. **Backend de expediente:** `obtener_carpeta` ahora devuelve `pagos` y los campos de ciudad/obra; `GET /api/v1/secretaria/clientes` incorpora total cobrado, fiado, saldo a favor y ciudad.
7. **Base de tutoriales:** `docs/tutoriales/` con los 7 Markdown (`00_INDICE_BOT_TUTOR` a `06_superadmin_y_permisos`), placeholders de capturas, preguntas frecuentes y auditoría en 60 segundos. Sin botones ni login nuevos.

### Evidencia

| Verificación | Resultado |
|---|---|
| `pytest /app/tests -q` | **277 passed in 6.24s** (`.agents/evidencias/pytest_v66_2026-11-09.txt`) |
| Migración real | `069_clientes_sabueso.sql` aplicada; `schema_migrations` la reporta como última |
| `GET /panel` real | HTTP 200; banner, buscador, filtros, paginación y pestañas presentes (`.agents/evidencias/panel_v66_2026-11-09.txt`) |
| Resumen real | 6 clientes; deuda 2 / `$55,043.60`; obra 3; pagos 0; prospectos 3 |
| Buscador real | `16m3` y `16 m3` -> 2 clientes con `match_hint` de Orden #57 y #9; `FC 210` -> 3; `#56` -> 1; `reyes` -> 1 |
| Filtros reales | deuda 2; obra 3; ciudad Orellana 1; fiado 3; FC-350 1; rango 10-60 m³ 3 |
| Navegador | sin errores; filtros y búsqueda actualizan la lista; ficha guarda ciudad/obra/cupo; pagos vacío se muestra correctamente |
| Base real | `payments=0`, `purchases=0`, `dispatch_schedule=0`; sin datos de prueba |
| Respaldo previo | `.agents/evidencias/orminorth_pre_069_2026-11-09.dump` |

### Decisiones

1. **Se creó un endpoint nuevo `/api/v1/clients/search`** en lugar de sobrecargar `/api/v1/secretaria/clientes`: el antiguo sigue sirviendo para selectores y cartera, y el nuevo concentra filtros, resumen y paginación.
2. **La normalización fonética es deliberadamente simple** (b/v, z/s/c, ll/y). Evita dependencias externas y es predecible; si aparecen casos raros se ajusta en una función única.
3. **El hint se calcula solo para la página actual** (12 clientes) con tres consultas agregadas, no una por cliente. La búsqueda principal sigue siendo SQL y paginada.
4. **La ficha usa `PUT /api/v1/clients/{id}`** con checklist ACL y bloqueo de solo lectura; no se borra ningún cliente.
5. **Los tutoriales son documentación pura.** No se agregaron botones de tutorial ni login al HTML, tal como pidió la fase.

### Bloqueos / preguntas al cliente

1. Validar con Julio los textos y el orden de las 4 tarjetas de cartera.
2. Confirmar si los prospectos deben ser solo `estado='PROSPECTO'` o también leads sin orden con otro criterio.
3. Confirmar si “En obra activa” debe mirar 90 días de órdenes y ±30 días de agenda, o una ventana distinta.
4. Cargar ciudad/obra frecuente en los clientes reales para que los filtros por zona sean útiles.

### Próximo paso exacto

Abrir `http://localhost:8000/panel` > Carpetas de Clientes, buscar `16m3`, `FC-210` y `#56`, filtrar por ciudad/deuda y abrir la ficha de un cliente para completar ciudad, obra frecuente y cupo.

### Archivos tocados

- `db/migrations/069_clientes_sabueso.sql`
- `services/core-api/app/routers/clients_search.py`
- `services/core-api/app/routers/catalog.py`
- `services/core-api/app/main.py`
- `services/core-api/app/m3_secretaria/service.py`
- `services/core-api/app/web/templates/panel.html`
- `services/core-api/tests/test_v66_clientes_sabueso.py`
- `docs/tutoriales/00_INDICE_BOT_TUTOR.md`
- `docs/tutoriales/01_dashboard_julio.md`
- `docs/tutoriales/02_secretaria_y_caja.md`
- `docs/tutoriales/03_carpetas_clientes.md`
- `docs/tutoriales/04_planta_flota_kardex.md`
- `docs/tutoriales/05_banca_y_mercado.md`
- `docs/tutoriales/06_superadmin_y_permisos.md`
- `.agents/ESTADO.md`
- `.agents/BITACORA.md`
- `.agents/evidencias/`

---

## 2026-11-09 - Cierre de sesión (v6.6)

**Agente:** OpenCode (DeepSeek V4.1 Flash)

**Estado al cerrar:** v6.6 commiteada en `6c345e5`, con **277 tests** en verde y la migración `069_clientes_sabueso.sql` aplicada a la base real. Carpetas de Clientes quedó con banner de 4 filtros, buscador Sabueso, filtros combinables, paginación y expediente en 3 pestañas. `docs/tutoriales/` quedó listo para el futuro bot. La base real sigue sin datos de prueba (`payments=0`, `purchases=0`, `dispatch_schedule=0`) y el clon `orminorth_panel_test` quedó limpio.

**Pendiente para la próxima sesión:**
1. Validar con Julio los textos/orden de las 4 tarjetas y la definición de “prospecto”.
2. Confirmar la ventana de “En obra activa” (hoy: 90 días de órdenes y ±30 días de agenda).
3. Cargar ciudad/obra frecuente en los clientes reales para activar filtros por zona.
4. Retomar login y despliegue VPS cuando el cliente confirme.

**Próximo paso exacto:** abrir `http://localhost:8000/panel` > Carpetas de Clientes y probar `16m3`, `FC-210`, `#56`, filtro por deuda/ciudad y la ficha editable.

---

## 2026-11-11 - v6.7: filtros plegables en Carpetas y fotos reales en Obras

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** Reducir la barra de filtros de Carpetas de Clientes a un botón desplegable y sustituir las dos ilustraciones SVG de "Mixers en calle" por fotografías reales.

### Hecho

1. **Barra compacta en Carpetas de Clientes.** El buscador Sabueso queda visible; a su lado viven `Filtros` (con contador de filtros activos) y `Limpiar`. Los 7 filtros + el rango de fechas se abren bajo demanda en `#panel-filtros-clientes`, con `aria-expanded` y `aria-controls`.
2. **Resumen de filtros activos.** Chips `Ciudad: Orellana ×` sobre la lista; cada chip quita su filtro y vuelve a buscar. `actualizarFiltrosClientes()` alimenta el contador y los chips después de cada búsqueda.
3. **Corrección de `[hidden]`.** Varias clases fijaban `display:flex/grid` y pisaban el atributo `hidden`; por eso los campos `dd/mm/aaaa` se veían siempre. Se agregó `[hidden] { display: none !important; }` como regla global.
4. **Fotos reales en Obras.** `renderObras()` usa `/static/brand/fotos/mixers-en-planta.jpg` y `/static/brand/fotos/mixer-en-descarga-sin-marca.jpg`. Se conserva `mixer-en-descarga.jpg` completo, con la marca de agua original.

### Evidencia

| Verificación | Resultado |
|---|---|
| `pytest /app/tests -q` | **277 passed**, exit 0 (`.agents/evidencias/pytest_v67_2026-11-11.txt`) |
| Navegador 1296 px | Filtros cerrados por defecto, contador oculto, fechas ocultas; al elegir `FIADO` el badge muestra `1`, aparece el chip y la lista baja a 3 clientes; el chip `×` restaura 6 (`panel_v67_filtros_2026-11-11.jpeg`) |
| Consola | 0 errores en las 6 vistas |
| Imágenes | Ambas cargan con `naturalWidth > 0` (633×315 y 730×268); dashboard con fotos (`panel_v67_fotos_2026-11-11.jpeg`) |

### Decisiones

1. **Los IDs de los filtros no cambian.** El panel solo los envuelve; `buscarClientes()` y el backend siguen leyendo `#filtro-ciudad`, `#filtro-fecha`, etc. Alternativa descartada: renombrar campos y tocar el endpoint.
2. **El panel de filtros arranca cerrado.** El caso normal es buscar por nombre; los filtros son secundarios. Alternativa descartada: dejarlo abierto y ocupar media pantalla.
3. **La foto del mixer se recortó al 46 % superior para quitar la marca de agua "ISUZU VEHICLES".** El original completo queda en la misma carpeta por si Dirección prefiere usarlo.
4. **Los recursos viven en `static/brand/fotos/`** (servidos como `/static/...`), no en `web/` ni en un CDN. Alternativa descartada: subirlos a Bunny antes de tener credenciales.

### Bloqueos / preguntas al cliente

1. Confirmar si se usa la foto recortada o la original con marca de agua; o si Julio entrega una foto propia de su flota.
2. El buscador global del header sigue comprimido a 149 px en 1296 px de ancho; pendiente de arreglo de layout.
3. El saludo "Buenos días" es estático y se muestra de noche; pendiente de hacerlo horario.

### Próximo paso exacto

Abrir `http://localhost:8000/panel` > Carpetas de Clientes, pulsar `Filtros`, combinar ciudad + pago y verificar que el contador y los chips reflejan los filtros; luego revisar el Dashboard con las fotos nuevas.

### Archivos tocados

- `services/core-api/app/web/templates/panel.html`
- `services/core-api/app/web/static/brand/fotos/` (nuevo)
- `.agents/evidencias/pytest_v67_2026-11-11.txt`
- `.agents/evidencias/panel_v67_filtros_2026-11-11.jpeg`
- `.agents/evidencias/panel_v67_fotos_2026-11-11.jpeg`
- `.agents/BITACORA.md`
- `.agents/ESTADO.md`

---

## 2026-11-11 - v6.8: pestaña CHAT con historial en PostgreSQL

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** Agregar una cuarta pestaña `💬 Chat` al expediente del cliente que guarde el historial de conversaciones en la base de datos, no en el navegador, para que un bot pueda leerlo después.

### Hecho

1. **Migración `070_chat_clientes.sql`.** Crea `chat_conversaciones` (un hilo por `cliente_id` + `canal`, único), `chat_mensajes` (append-only: dirección, autor, cuerpo, adjuntos JSONB, `whatsapp_msg_id` único parcial, estado de entrega, `leido_panel_at`, `tsvector` en español) y la vista `v_chat_conversacion` (total, no leídos, último mensaje y preview). Índices para hilo, pendientes, búsqueda GIN y cliente. Trigger que actualiza el preview del hilo.
2. **API `app/routers/chat_clientes.py`.** `GET /api/v1/clients/{id}/chat`, `POST .../chat/mensajes`, `POST .../chat/leido` y `GET /api/v1/chat/buscar`. Exige el módulo `clientes_cartera` (mutación para escribir). La ingesta de WhatsApp es idempotente por `whatsapp_msg_id`.
3. **Pestaña `💬 Chat` en el panel.** Badge de no leídos, burbujas entrantes/salientes, `Enter` envía, `Shift+Enter` salta de línea, contador de mensajes, aviso de que el historial vive en la base. El hilo se precarga al abrir la carpeta y se marca leído al entrar.
4. **Mapa de la base actualizado.** `docs/BASE_DE_DATOS.md` §9 documenta dónde está el chat, sus columnas, índices, vista, endpoints, cómo lo lee el bot y lo que todavía no hace. También se actualizaron las tablas/vistas y las migraciones 067-070; `docs/MODELO_DATOS.md` y el tutorial de Carpetas suman el chat.

### Evidencia

| Verificación | Resultado |
|---|---|
| `python scripts/chat_v68_check.py` | **CHAT V6.8: OK** (19 checks, 0 fallos; limpieza deja 0 mensajes) — `.agents/evidencias/chat_v68_check_2026-11-11.txt` |
| `pytest /app/tests -q` | **283 passed**, exit 0 — `.agents/evidencias/pytest_v68_2026-11-11.txt` |
| Persistencia real | Mensaje enviado desde el panel, entrante insertado por API, recarga completa y el hilo sigue; badge `1`, al abrir chat pasa a 0 y `no_leidos=0` |
| Idempotencia | Reintento del mismo `whatsapp_msg_id` devuelve `duplicado=true` y no suma mensajes |
| Búsqueda | `GET /chat/buscar?q=chatv68prueba` encuentra los 2 mensajes y resalta el término |
| UI | Pestaña Chat + 4 mensajes, contador `4 mensaje(s)`, 0 errores de consola — `.agents/evidencias/panel_v68_chat_2026-11-11.jpeg` |
| Base al cerrar | `chat_conversaciones=0`, `chat_mensajes=0`, `schema_migrations=17`, 32 tablas y 7 vistas |

### Decisiones

1. **PostgreSQL, no `localStorage`.** El historial es un documento del cliente; tiene que sobrevivir al navegador y ser consultable por el bot. Alternativa descartada: guardar en el navegador y sincronizar después.
2. **Un hilo continuo por cliente y canal** (`UNIQUE (cliente_id, canal)`). Refleja “una carpeta con un documento que muestra la conversación”. Si se necesitan varios hilos, se abre una migración nueva; la API no depende de la restricción.
3. **Sin contadores desnormalizados.** Los no leídos se calculan con un índice parcial sobre entrantes sin `leido_panel_at`; el trigger solo mantiene preview y fecha del último mensaje. Alternativa descartada: columnas contador que se desincronizan.
4. **Append-only.** No hay endpoint de edición ni borrado; una corrección será un mensaje nuevo o una migración explícita. Es coherente con el ledger y el testigo del Custodio.
5. **Adjuntos como JSONB de referencias**, no binarios en la base. El panel todavía no tiene selector de archivos; cuando se conecte Bunny se guardan URL/ID.
6. **Los mensajes de la prueba manual se borraron** al terminar. La conversación funcional se verificó, pero la base real queda sin datos inventados; el script `chat_v68_check.py` crea y elimina los suyos.

### Bloqueos / preguntas al cliente

1. El envío real por WhatsApp sigue pendiente de Evolution API: hoy el chat solo guarda. Cuando se conecte, el mismo endpoint recibe el `whatsapp_msg_id` y el índice único evita duplicados.
2. Falta definir si el bot responderá automáticamente o solo leerá el historial; el modelo soporta ambos (`autor_tipo = BOT`).
3. Siguen abiertas las dos decisiones de v6.7: foto del mixer recortada u original, y si se commitea ya.

### Próximo paso exacto

Abrir `http://localhost:8000/panel` > Carpetas de Clientes > cualquier cliente > pestaña `💬 Chat`, escribir un mensaje, recargar la página y confirmar que el mensaje sigue ahí; luego consultar `GET /api/v1/clients/{id}/chat` para ver el mismo historial que leería el bot.

### Archivos tocados

- `db/migrations/070_chat_clientes.sql` (nuevo)
- `services/core-api/app/routers/chat_clientes.py` (nuevo)
- `services/core-api/app/main.py`
- `services/core-api/app/web/templates/panel.html`
- `services/core-api/tests/test_v68_chat_clientes.py` (nuevo)
- `scripts/chat_v68_check.py` (nuevo)
- `docs/BASE_DE_DATOS.md`
- `docs/MODELO_DATOS.md`
- `docs/tutoriales/03_carpetas_clientes.md`
- `.agents/evidencias/chat_v68_check_2026-11-11.txt`
- `.agents/evidencias/pytest_v68_2026-11-11.txt`
- `.agents/evidencias/panel_v68_chat_2026-11-11.jpeg`
- `.agents/BITACORA.md`
- `.agents/ESTADO.md`

---

## 2026-11-11 - v6.9: chat espejo de WhatsApp y multimedia en Bunny

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** Corregir el rumbo del chat: el canal oficial es WhatsApp (Evolution) y el panel pasa a ser un espejo. Sumar fotos, videos, audios y documentos con carpetas por cliente en Bunny, compresión y límites.

### Hecho

1. **Chat espejo de WhatsApp.** El canal por defecto es `WHATSAPP`; la cabecera muestra el estado de Evolution y un aviso cuando no está conectado. Los salientes quedan `PENDIENTE` y se marcan con reloj; si Evolution está conectado, el texto sale por `sendText` y queda `ENVIADO`/`FALLIDO`. Ya no se presenta como un chat interno del ERP.
2. **Estética WhatsApp.** Burbujas con cola, separadores Hoy/Ayer, ticks ✓/✓✓/azul, avatar con iniciales, fondo punteado y compositor con emoji, clip, cámara y micrófono. El clip abre una hoja con Galería, Cámara, Documento, Audio, Ubicación y Contacto; el botón cambia entre micrófono y enviar según el texto.
3. **Multimedia real.** `POST /api/v1/clients/{id}/chat/adjuntos` valida tipo y tamaño, comprime imágenes a WebP (máx. 1920 px, sin EXIF), recomprime videos a H.264/AAC (1280×720, CRF 28, ≤180 s), deja el audio tal cual y limita documentos. Los archivos van a Bunny (`clientes/<nombre>_<cédula>/`) o al sandbox local; `media_assets` guarda ruta, mime, tamaño, hash y etiquetas. `GET /api/v1/media/{id}` firma la URL con `BUNNY_TOKEN_KEY`; `/archivo` sirve el sandbox.
4. **Igualdad de columnas.** La lista de clientes y la carpeta del cliente comparten altura (medido 712/712 px en 1296 px); el chat crece con el panel.
5. **Defensas.** Lista blanca de extensiones, topes por tipo, límite de píxeles, rechazo de path traversal, límite en memoria de 30 subidas/h y 180 mensajes/h por IP.
6. **Cédula en la ficha.** `clients.cedula` se agregó a la migración 071, al `PUT /api/v1/clients/{id}`, a la carpeta y al formulario **Ficha y Datos** (con placeholder para Bunny). Nace `NULL`; no se inventa.
7. **Documentación.** `docs/WHATSAPP_Y_MEDIA.md` explica la decisión, la carpeta por cliente (cédula → RUC → id), las etiquetas en base, el token de Bunny y las fases. Se actualizaron `BASE_DE_DATOS.md` (§9.6), `MODELO_DATOS.md`, el tutorial de Carpetas y `00_DECISIONES_PENDIENTES.md` (P7 cédula, P8 credenciales).

### Evidencia

| Verificación | Resultado |
|---|---|
| `python scripts/media_v69_check.py` | **MEDIA V6.9: OK**: PNG 3200×1800 → WebP ≤1920, WAV passthrough, MP4 recomprimido ≤180 s, 3 filas en `media_assets`, rutas `clientes/...`, SHA-256; limpieza deja 0 archivos |
| `python scripts/chat_v68_check.py` | **CHAT V6.8: OK**: GET/POST, idempotencia por `whatsapp_msg_id`, orden, búsqueda, leído y limpieza |
| `pytest /app/tests -q` | **291 passed**, exit 0 (`.agents/evidencias/pytest_v69_2026-11-11.txt`) |
| Navegador 1296 px | Cliente 712 px = carpeta 712 px; clip con 6 opciones; subida real de una imagen de prueba (900×600) y render en burbuja; 0 errores de consola (`panel_v69_chat_2026-11-11.jpeg`, `panel_v69_adjunto_2026-11-11.jpeg`) |
| Base al cerrar | `media_assets=0`, `chat_mensajes=1` (el “Hola” de prueba del usuario, migrado de PANEL a WHATSAPP y marcado PENDIENTE), `chat_conversaciones=1`, `schema_migrations=18` |

### Decisiones

1. **WhatsApp manda; el panel es espejo.** Se descartó el chat interno como canal. El panel lee el mismo hilo y responde por Evolution cuando esté conectado. Alternativa descartada: mantener dos historiales separados.
2. **Carpeta por cliente, no por obra.** `clientes/<nombre>_<cédula>/`; obra, orden y viaje son etiquetas JSONB. Evita carpetas que cambian de nombre y permite filtrar sin mover archivos. Si falta cédula se usa RUC y luego el id.
3. **Token authentication en Bunny.** Se implementó la firma `?token=&expires=`; sin clave la URL sale pública (solo local). Alternativa descartada: URLs públicas permanentes para fotos de obras.
4. **Compresión en el backend.** El navegador no es confiable para bajar peso; WebP y H.264 se hacen en el servidor. El video exige `ffmpeg` en la imagen (agregado al Dockerfile).
5. **Sandbox local solo para desarrollo.** Volumen `orminorth-media`; producción usa Bunny y no deja binarios en el VPS, como exige el PDR.

### Bloqueos / preguntas al cliente

1. **Evolution:** falta conectar el número y persistir los mensajes entrantes del webhook en `chat_mensajes` (hoy el pipeline actualiza el viaje). El envío de texto desde el panel ya está listo; el de multimedia espera el endpoint de Evolution.
2. **Cédula:** `clients.cedula` nace NULL; mientras no se cargue, la carpeta usa RUC o id.
3. **Bunny:** cargar Storage Zone/API key/CDN y `BUNNY_TOKEN_KEY`, apagar `sandbox` en `integraciones.bunny` y activar Token Authentication en el Pull Zone.
4. **Retención y cuota:** definir cuánto tiempo se guardan videos y si hay tope por cliente. Antivirus de documentos queda pendiente.

### Próximo paso exacto

Conectar Evolution en Superadmin, verificar `GET /api/v1/whatsapp/health` → `notifier: evolution`, enviar un mensaje desde el chat del panel y confirmar que llega al teléfono y queda `ENVIADO` en el hilo; después conectar Bunny con token y repetir con una foto.

### Archivos tocados

- `db/migrations/071_media_clientes.sql` (nuevo)
- `services/core-api/app/services/media.py` (nuevo)
- `services/core-api/app/routers/chat_clientes.py`
- `services/core-api/app/web/templates/panel.html`
- `services/core-api/app/settings.py`
- `services/core-api/app/main.py`
- `services/core-api/Dockerfile`
- `services/core-api/requirements.txt`
- `services/core-api/tests/test_v69_media_clientes.py` (nuevo)
- `scripts/media_v69_check.py` (nuevo)
- `scripts/chat_v68_check.py`
- `docker-compose.yml`
- `.env.example`
- `docs/WHATSAPP_Y_MEDIA.md` (nuevo)
- `docs/BASE_DE_DATOS.md`
- `docs/MODELO_DATOS.md`
- `docs/tutoriales/03_carpetas_clientes.md`
- `docs/00_DECISIONES_PENDIENTES.md`
- `.agents/evidencias/media_v69_check_2026-11-11.txt`
- `.agents/evidencias/chat_v69_check_2026-11-11.txt`
- `.agents/evidencias/pytest_v69_2026-11-11.txt`
- `.agents/evidencias/panel_v69_chat_2026-11-11.jpeg`
- `.agents/evidencias/panel_v69_adjunto_2026-11-11.jpeg`
- `.agents/BITACORA.md`
- `.agents/ESTADO.md`

---

## 2026-11-12 - v6.10: fondo de Planta, cabecera de Banca y tarea para Abel

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** Poner la fotografía de obra como fondo de la agenda de Planta, agregar la cabecera de cuentas bancarias en Banca y Mercado, y dejar por escrito la tarea de integración para Abel.

### Hecho

1. **Fondo en Planta, Flota y Kardex.** La tarjeta “Agenda de planta” usa `static/brand/fotos/planta-agenda.webp` con un degradado oscuro (y su variante clara) para que el calendario siga legible. La foto es la que entregó Dirección; conserva la marca de agua de Vecteezy y queda anotada para reemplazo.
2. **Cabecera de Banca y Mercado.** Se agregó un bloque estilo *Carpetas de Clientes* con tres tarjetas de bancos: **Pichincha, Guayaquil e Internacional**, cada una con su logo en `static/brand/bancos/`, el detalle de la cuenta y un estado (`Provisional`, `Pendiente`). Pichincha se llena desde `empresa.bot_publico.bank_accounts`; Guayaquil e Internacional muestran “Cuenta por confirmar” porque todavía no están en la configuración. **No se inventó ningún número ni saldo.**
3. **Endpoint `GET /api/v1/dashboard/bancos`.** Lee `empresa_bot_publico` y devuelve las cuentas declaradas y `dato_provisional`; la UI pinta el detalle sin hardcodear datos de negocio.
4. **Tarea para Abel.** Se creó `.agents/tareas/2026-11-12_ABEL.md` con los bloques: Evolution API, Bunny.net + token, persistencia de entrantes, envío de multimedia, cédula/cuentas y límites. Incluye criterios de aceptación, comandos y checklist de cierre.
5. **Formatos documentados.** `docs/WHATSAPP_Y_MEDIA.md` lista qué imágenes (JPG, PNG, WebP, GIF, BMP, TIFF, HEIC), videos, audios y documentos se aceptan; todas las imágenes se convierten a WebP sin importar el formato de origen.

### Evidencia

| Verificación | Resultado |
|---|---|
| Navegador, Planta | `background-image` contiene `planta-agenda.webp`; la tarjeta mide 256 px y el calendario queda legible; 0 errores (`panel_v610_planta_2026-11-12.jpeg`) |
| Navegador, Banca | 3 tarjetas de 84 px; logos cargan (`naturalWidth > 0`); Pichincha → “Cuenta Corriente #2100XXXXXX / Provisional”; Guayaquil e Internacional → “Cuenta por confirmar / Pendiente”; 0 errores (`panel_v610_banca_2026-11-12.jpeg`) |
| API | `GET /api/v1/dashboard/bancos` devuelve las 2 cuentas declaradas y `dato_provisional: true` |
| `pytest /app/tests -q` | **295 passed**, exit 0 (`.agents/evidencias/pytest_v610_2026-11-12.txt`) |

### Decisiones

1. **Las cuentas salen de la configuración, no del código.** Pichincha se lee de `empresa.bot_publico`; si Dirección carga Guayaquil e Internacional, las tarjetas se llenan solas. Alternativa descartada: escribir números de cuenta en el HTML.
2. **Estado visible en vez de saldo inventado.** Con `ledger_entries` vacío no hay saldo por banco; se muestra `Provisional` o `Pendiente` antes que un `$0.00` que parezca real.
3. **Logos desde Wikimedia Commons.** Se guardaron en `static/brand/bancos/` con un `README.md` que cita el origen; son marcas de sus titulares y se usan solo para identificar. Si Dirección entrega los oficiales, se reemplazan sin tocar código.
4. **La foto de fondo es la entregada por Dirección.** Tiene marca de agua de Vecteezy; se usa tal cual con overlay. Pendiente reemplazarla por una foto propia o licenciada.

### Bloqueos / preguntas al cliente

1. Confirmar si las cuentas de **Guayaquil** e **Internacional** existen y cargarlas en Superadmin > Empresa; hoy solo Pichincha y BanEcuador están en la configuración.
2. Reemplazar `planta-agenda.webp` por una foto sin marca de agua cuando esté disponible.
3. Abel debe ejecutar `.agents/tareas/2026-11-12_ABEL.md` (Evolution, Bunny + token, entrantes y multimedia).

### Próximo paso exacto

Abrir `http://localhost:8000/panel` > **Banca y Mercado** y confirmar la cabecera con los tres bancos; luego cargar las cuentas faltantes en Superadmin > Empresa. En paralelo, Abel sigue la tarea del 12/11.

### Archivos tocados

- `services/core-api/app/web/templates/panel.html`
- `services/core-api/app/m4_dashboard/router.py`
- `services/core-api/app/web/static/brand/fotos/planta-agenda.webp` (nuevo)
- `services/core-api/app/web/static/brand/bancos/` (nuevo: 3 logos + README)
- `services/core-api/tests/test_v70_banca_planta.py` (nuevo)
- `.agents/tareas/2026-11-12_ABEL.md` (nuevo)
- `docs/WHATSAPP_Y_MEDIA.md`
- `.agents/evidencias/pytest_v610_2026-11-12.txt`
- `.agents/evidencias/panel_v610_planta_2026-11-12.jpeg`
- `.agents/evidencias/panel_v610_banca_2026-11-12.jpeg`
- `.agents/BITACORA.md`
- `.agents/ESTADO.md`

---

## 2026-11-12 - v6.11: banco activo y detalle de cuenta

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** Convertir la cabecera de Banca en una consola real: un banco activo en amarillo y, al hacer clic, ver saldo, préstamos y movimientos.

### Hecho

1. **Tarjetas seleccionables.** Pichincha, Guayaquil e Internacional son botones; el activo se pinta con el amarillo de las action cards (`#F59E0B`) y texto oscuro. Al entrar a Banca queda activo Pichincha y el detalle se abre debajo.
2. **Migración `072_bancos_detalle.sql`.** Crea `bank_accounts` (tipo, número enmascarado, titular, moneda, estado, saldo informado) y siembra los tres bancos. Agrega las cuentas contables hijas `1102.01`, `1102.02` y `1102.03` y enlaza cada banco. Copia el número `2100XXXXXX` de `empresa.bot_publico` si existe. Añade `financial_liabilities.bank_account_id`.
3. **API `m4_dashboard/bancos.py`.** `GET /bancos` y `GET /bancos/{slug}` devuelven saldo contable, saldo informado, entradas/salidas, préstamos y últimos movimientos. `PUT /bancos/{slug}` permite cargar número, tipo, estado, titular, notas y saldo informado (con ACL de Finanzas y mutación).
4. **Panel de detalle.** KPIs de saldo contable, saldo informado, entradas y préstamos; tablas de préstamos y movimientos con estados vacíos honestos; botón **Editar datos** con diálogo para completar la cuenta y el saldo.
5. **Tarea de Abel actualizada:** cargar cuentas/saldos desde Banca y, en desarrollo, asignar los pagos a la cuenta hija del banco (`1102.01/02/03`) para que los movimientos aparezcan.

### Evidencia

| Verificación | Resultado |
|---|---|
| Navegador, Banca | Pichincha activo con `background-color: rgb(245, 158, 11)`; detalle visible con “Cuenta corriente · #2100XXXXXX”, saldo contable `$0.00`, saldo informado `—`, 0 préstamos/movimientos; 0 errores (`panel_v611_banca_2026-11-12.jpeg`) |
| Cambio de banco | Clic en Guayaquil cambia el activo y el detalle a “Banco Guayaquil / Cuenta por confirmar” |
| Edición real | Se guardó `saldo informado = 1000` y titular `HORMINOR` desde el diálogo; el detalle mostró `$1,000.00` y “Actualizado 12/11/2026”; luego se limpió a `—` para no dejar datos inventados |
| API | `GET /bancos` devuelve 3 bancos; `PUT /bancos/pichincha` actualiza y `saldo_informado: null` limpia |
| Base | 34 tablas, 7 vistas, 19 migraciones, 30 cuentas contables, 3 bancos |
| `pytest /app/tests -q` | **296 passed**, exit 0 (`.agents/evidencias/pytest_v611_2026-11-12.txt`) |

### Decisiones

1. **Saldo contable ≠ saldo informado.** El primero sale del libro mayor; el segundo es la foto que carga Gerencia. No se reemplaza el libro ni se inventa un saldo cuando no hay datos.
2. **Una cuenta contable hija por banco.** `1102.01`, `1102.02` y `1102.03` permiten que los movimientos y el balance se separen sin mezclar bancos. Alternativa descartada: usar solo `1102` y repartir a ojo.
3. **Préstamos por `bank_account_id` o por nombre de entidad.** Las filas históricas sin vínculo se muestran si `entidad_financiera` coincide con el banco; no se duplican.
4. **Movimientos desde `payments`.** Para que un cobro/gasto aparezca en el banco, debe registrarse contra la cuenta hija. El formulario de pagos aún usa `1102`; queda como tarea de integración.
5. **Edición con ACL de Finanzas.** El saldo informado es una decisión de Gerencia/Contadora, no de cualquier perfil.

### Bloqueos / preguntas al cliente

1. Confirmar las cuentas de **Guayaquil** e **Internacional** y cargarlas en Banca > Editar datos.
2. Asignar los pagos a la cuenta hija del banco para poblar movimientos (desarrollo).
3. Cargar los préstamos reales en `financial_liabilities` para verlos en el detalle.

### Próximo paso exacto

Abrir `http://localhost:8000/panel` > **Banca y Mercado**, hacer clic en cada banco y usar **Editar datos** para cargar número, titular y saldo informado. Luego registrar un cobro contra `1102.01` y verlo aparecer en Movimientos.

### Archivos tocados

- `db/migrations/072_bancos_detalle.sql` (nuevo)
- `services/core-api/app/m4_dashboard/bancos.py` (nuevo)
- `services/core-api/app/m4_dashboard/router.py`
- `services/core-api/app/web/templates/panel.html`
- `services/core-api/tests/test_v70_banca_planta.py`
- `.agents/tareas/2026-11-12_ABEL.md`
- `docs/BASE_DE_DATOS.md`
- `docs/MODELO_DATOS.md`
- `.agents/evidencias/pytest_v611_2026-11-12.txt`
- `.agents/evidencias/panel_v611_banca_2026-11-12.jpeg`
- `.agents/BITACORA.md`
- `.agents/ESTADO.md`

---

## 2026-11-12 - Traspaso de bancos: qué hay, qué falta y qué decidir

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Motivo:** dejar el tema de bancos documentado para abrir una conversación nueva con menos contexto.

**Documento de arranque:** `docs/BANCOS_PENDIENTES.md` (leerlo primero).

### Respuestas cortas

1. **¿Están previstas las columnas?** La tarjeta muestra logo, banco, tipo/número y estado. El detalle muestra saldo contable, saldo informado, entradas, salidas, préstamos y movimientos. La tabla `bank_accounts` tiene las columnas de §2.3 del documento. **No** están implementados: selector de banco en pagos, cierre por banco, transferencias internas, conciliación, historial de saldo informado ni sección de bancos en Superadmin.
2. **¿El cierre de caja menciona el banco?** **No.** `cash_closures` no tiene banco. `calcular_resumen_caja()` agrupa por método (`EFECTIVO`/`TRANSFERENCIA`/`FIADO`) y bolsa (`CAJA_DIARIA`/`BANCO_GERENCIA`); `_movimientos()` ni siquiera selecciona `account_id`. Un cobro por transferencia al Pichincha y otro al Guayaquil se suman juntos.
3. **¿Existe dónde configurar las cuentas?** Solo **Banca > Editar datos** (tabla `bank_accounts`, ACL de Finanzas). `empresa.bot_publico.bank_accounts` es una lista de texto para el bot, **desconectada**: la migración copió el número una vez y no se sincroniza. No hay pantalla Superadmin > Bancos.

### Estado del código

- `072_bancos_detalle.sql` aplicada; 3 bancos, cuentas hijas `1102.01/02/03`, `saldo_informado`, `financial_liabilities.bank_account_id`.
- `GET/PUT /api/v1/dashboard/bancos[/{slug}]` funcionando.
- UI con tarjeta activa amarilla, detalle y diálogo de edición.
- Se probó guardar `$1,000` y limpiar; la base real queda **sin saldos ni préstamos inventados**.
- `pytest` 296; evidencia en `pytest_v611_2026-11-12.txt` y `panel_v611_banca_2026-11-12.jpeg`.

### Decisiones que faltan

1. Saldo oficial: libro mayor vs. saldo informado.
2. Elegir banco en cada cobro (mínimo para transferencias).
3. Cierre diario con desglose por banco en el `snapshot`.
4. Fuente única de cuentas: `bank_accounts` vs. `empresa.bot_publico` (recomendado: `bank_accounts` y generar el texto del bot desde ahí).
5. Transferencias internas, conciliación y permisos de edición.
6. Número completo vs. enmascarado para conciliación.

### Próximo paso exacto

Agregar el selector de banco en `dlg-pago`, guardar `bank_account_id`/`account_id` en `payments`, extender `_movimientos()` y `calcular_resumen_caja()` con `cobros_por_banco`, y probar en el clon con un cobro de transferencia al Pichincha y otro al Guayaquil.

### Archivos de referencia

- `docs/BANCOS_PENDIENTES.md`
- `db/migrations/072_bancos_detalle.sql`
- `services/core-api/app/m4_dashboard/bancos.py`
- `services/core-api/app/m3_secretaria/service.py` (`calcular_resumen_caja`, `_movimientos`, `cerrar_caja`)
- `services/core-api/app/web/templates/panel.html` (`dlg-pago`, `dlg-banco`, `banco-detalle`)
- `.agents/tareas/2026-11-12_ABEL.md`

---

## 2026-11-12 - v6.12: logos de bancos con color de marca

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** que las tarjetas de Banca muestren el logo de cada banco con su color de marca (amarillo Pichincha, rosado Guayaquil, naranja Internacional) y no un cuadrito blanco con un logo ilegible.

### Hecho

1. **Tres placas de 96x96 nuevas** en `static/brand/bancos/`:
   - `pichincha.svg`: fondo amarillo `#FFD100` con el símbolo oficial en azul `#1B2D54` y la flecha calada en amarillo.
   - `guayaquil.svg`: fondo rosado `#C7007E` con el isotipo oficial (anillo) en blanco. El isotipo se tomó del PNG oficial transparente y se recoloreó a blanco conservando el alfa; va embebido como `data:image/png;base64` para que sea un archivo autocontenido.
   - `internacional.svg`: fondo naranja `#F39200` con las barras oficiales en blanco. La geometría (3 barras verticales y 3 dashes horizontales por lado) se midió pixel a pixel del `internacional.png` original.
2. **Panel:** `.banco-logo` pasa de caja blanca de 44 px con `padding` a placa de 46 px sin fondo propio, `object-fit: cover` y sombra; la tarjeta activa ya no fuerza fondo blanco. `internacional.png` se cambia por `internacional.svg`.
3. **README de logos** actualizado con el color y el origen de cada isotipo.
4. **Test actualizado:** `test_v70_banca_planta.py` ahora espera `internacional.svg` y verifica que cada SVG contenga su color de marca (`#FFD100`, `#C7007E`, `#F39200`).

### Evidencia (real, ejecutada)

| Comando / verificación | Resultado |
|---|---|
| `docker compose up -d --build core-api` | Imagen reconstruida y contenedor recreado (el codigo va horneado, no montado) |
| `GET /static/brand/bancos/pichincha.svg` / `guayaquil.svg` / `internacional.svg` | 200 `image/svg+xml` (447 / 13,283 / 727 bytes) |
| Chrome headless 1460x800 sobre `/panel` (Banca, tema noche) | Tres placas con su color; Pichincha amarillo activo, Guayaquil rosado, Internacional naranja (`panel_v612_bancos_dark_2026-11-12.png`) |
| Chrome headless (Banca, tema dia) | Placas legibles sobre fondo claro (`panel_v612_bancos_light_2026-11-12.png`) |
| Cambio de banco activo | Clic en Guayaquil pinta la tarjeta en ambar y el detalle muestra "Banco Guayaquil" |
| `pytest /app/tests -q` | **296 passed** en 8.51 s (`pytest_v612_2026-11-12.txt`) |

### Decisiones tomadas

1. **El logo es una placa con el color de marca, no una caja blanca.** A 46 px el lockup completo (isotipo + palabra) era ilegible; el isotipo sobre el color del banco identifica mejor y da el "cache" que pidio Direccion. Alternativa descartada: dejar el lockup completo en la caja blanca (estado anterior).
2. **Isotipos, no marcas recreadas a mano.** Pichincha usa los paths vectoriales oficiales que ya estaban en el repo; Guayaquil usa el isotipo oficial raster recoloreado a blanco; Internacional replica la geometria medida del PNG oficial. Alternativa descartada: dibujar un aproximado "de memoria".
3. **Placas autocontenidas de 96x96.** El color viaja dentro del SVG, asi el mismo archivo se ve igual en cualquier fondo y tema. Alternativa descartada: color por CSS en cada tarjeta, que acopla el logo al layout.

### Bloqueos / preguntas al cliente

1. Si Direccion quiere el **lockup completo con la palabra** ("BANCO PICHINCHA", etc.) en vez del isotipo, se hacen placas anchas (por ejemplo 92x40) y se ajusta la tarjeta.
2. `internacional.png` se conserva como fuente original; se puede borrar cuando Direccion confirme los SVG.

### Proximo paso exacto

Abrir `http://localhost:8000/panel` > **Banca y Mercado** y confirmar los tres logos con Direccion; si pide el lockup completo, reemplazar las placas por versiones 92x40 y ajustar `.banco-logo` en `panel.html`.

### Archivos tocados

- `services/core-api/app/web/static/brand/bancos/pichincha.svg` (rehecho)
- `services/core-api/app/web/static/brand/bancos/guayaquil.svg` (rehecho)
- `services/core-api/app/web/static/brand/bancos/internacional.svg` (nuevo)
- `services/core-api/app/web/static/brand/bancos/internacional.png` (se conserva como fuente)
- `services/core-api/app/web/static/brand/bancos/README.md`
- `services/core-api/app/web/templates/panel.html` (`.banco-logo`, estado activo, `src` de Internacional)
- `services/core-api/tests/test_v70_banca_planta.py`
- `.agents/evidencias/pytest_v612_2026-11-12.txt`
- `.agents/evidencias/panel_v612_bancos_dark_2026-11-12.png`
- `.agents/evidencias/panel_v612_bancos_light_2026-11-12.png`
- `.agents/BITACORA.md`
- `.agents/ESTADO.md`

---

## 2026-11-12 - v6.12 aceptada: logos de bancos cerrados

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** registrar la aprobaciÃ³n de DirecciÃ³n y el Ãºltimo ajuste de tamaÃ±o del sÃ­mbolo de Pichincha.

### Hecho

1. **SÃ­mbolo de Pichincha a 56/96 px** dentro de su placa amarilla (antes 44/96): pesa visualmente igual que el anillo de Guayaquil y las barras de Internacional. Se conservan los trazos vectoriales oficiales.
2. **Capturas regeneradas** con el tamaÃ±o final: panel en tema noche, tema dÃ­a y zoom de las tres placas.
3. **DirecciÃ³n aprobÃ³** las tres placas con isotipo (sin palabra). No se abre la variante de lockup completo.

### Evidencia (real, ejecutada)

| Comando / verificaciÃ³n | Resultado |
|---|---|
| `docker compose up -d --build core-api` | Imagen reconstruida y contenedor recreado |
| Chrome headless 1460x800 sobre `/panel` (Banca, noche y dÃ­a) | Tres placas balanceadas; Pichincha amarillo, Guayaquil rosado, Internacional naranja |
| Zoom 150 px de los tres SVG | SÃ­mbolo Pichincha 56/96 centrado; anillo y barras sin cambios (`panel_v612_logos_zoom_2026-11-12.png`) |
| `pytest /app/tests -q` | **296 passed** en 10.06 s (`pytest_v612_2026-11-12.txt`) |

### Decisiones tomadas

1. **Isotipo sobre placa de color, aprobado por DirecciÃ³n.** No se agrega la palabra al logo; el nombre ya estÃ¡ en la tarjeta y a 46 px el lockup no se lee. Alternativa descartada: placas 92x40 con "BANCO PICHINCHA".
2. **TamaÃ±o Ã³ptico igualado a mano.** El cuadrado de Pichincha necesitaba 56/96 para no verse mÃ¡s chico que el anillo y las barras. Alternativa descartada: escalar todo por bounding box, que dejaba a Pichincha pequeÃ±o.

### Bloqueos / preguntas al cliente

Ninguno. Si mÃ¡s adelante DirecciÃ³n pide el lockup completo, se hacen placas 92x40 y se ajusta `.banco-logo`.

### PrÃ³ximo paso exacto

Volver al traspaso de bancos: `docs/BANCOS_PENDIENTES.md` Â§6 â€” agregar el selector de banco en `dlg-pago`, guardar `bank_account_id` en `payments` y desglosar el cierre por banco.

### Archivos tocados

- `services/core-api/app/web/static/brand/bancos/pichincha.svg` (tamaÃ±o del sÃ­mbolo 56/96)
- `.agents/evidencias/panel_v612_bancos_dark_2026-11-12.png`
- `.agents/evidencias/panel_v612_bancos_light_2026-11-12.png`
- `.agents/evidencias/panel_v612_logos_zoom_2026-11-12.png`
- `.agents/evidencias/pytest_v612_2026-11-12.txt`
- `.agents/BITACORA.md`
- `.agents/ESTADO.md`

---

## 2026-11-12 - v6.12 hotfix: cache del logo de Pichincha

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Motivo:** DirecciÃ³n seguÃ­a viendo el logo viejo de Pichincha en el navegador aunque el server ya servÃ­a el nuevo; `pichincha.svg` conservaba el mismo nombre y el navegador reusaba la copia en cachÃ©.

### Hecho

1. **Cache-busting** en las tres imÃ¡genes de la cabecera de Banca: `/static/brand/bancos/<banco>.svg?v=612`. El archivo servido no cambia; la URL sÃ­, asÃ­ que el navegador descarga la versiÃ³n nueva sin exigir recarga forzada.
2. Rebuild de `core-api` y verificaciÃ³n del HTML servido: las tres etiquetas `<img>` llevan `?v=612`.
3. Captura nueva del panel con un navegador sin cachÃ©: Pichincha muestra la placa amarilla con el sÃ­mbolo azul.

### Evidencia (real, ejecutada)

| Comando / verificaciÃ³n | Resultado |
|---|---|
| `GET /panel` | Las tres `<img>` con `?v=612` |
| `GET /static/brand/bancos/pichincha.svg` | 200, 461 bytes, `viewBox="0 0 96 96"` (archivo nuevo) |
| Chrome headless sobre `/panel` (Banca, noche) | Placa amarilla nueva visible (`panel_v612_bancos_dark_2026-11-12.png`) |
| `pytest /app/tests -q` | **296 passed** en 6.36 s (`pytest_v612_cache_2026-11-12.txt`) |

### Decisiones tomadas

1. **VersiÃ³n en la URL del logo en vez de cabeceras de cachÃ©.** Es un panel HTML sin build; `?v=NN` es explÃ­cito, barato y se sube con cada cambio de arte. Alternativa descartada: tocar el middleware de estÃ¡ticos para `no-store`, que castiga todos los assets.

### PrÃ³ximo paso exacto

Recargar `http://localhost:8000/panel` (Ctrl+R normal) y confirmar que Pichincha ya muestra la placa amarilla. Cuando cambie cualquier logo, subir el nÃºmero de `?v=`.

### Archivos tocados

- `services/core-api/app/web/templates/panel.html` (`?v=612` en los tres logos)
- `.agents/evidencias/panel_v612_bancos_dark_2026-11-12.png`
- `.agents/evidencias/pytest_v612_cache_2026-11-12.txt`
- `.agents/BITACORA.md`

---

## 2026-11-12 - Asistente IA conversacional: revisiÃ³n del PDR y propuesta

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** revisar el PDR y los comentarios sobre IA/bot antes de diseÃ±ar un asistente que converse y consulte la base; dejar una propuesta para iterar con DirecciÃ³n. **No se escribiÃ³ cÃ³digo.**

### RevisiÃ³n

1. **El PDR prohÃ­be un chatbot abierto** (`PDR_v4.0.txt` Â§3.2): la IA solo actÃºa como juez binario SÃ/NO. La decisiÃ³n 14 de `ESTADO.md` y la entrada del 2026-11-08 lo ratifican: el bot arma la respuesta con datos de BD y el LLM solo decide.
2. **Lo que ya existe:** 9 consultas del Custodio con permisos por rol, Sabueso, detalle de bancos, `componer_respuesta_lead()`, identidad de WhatsApp, historial `chat_*`, tutoriales como base de conocimiento y Gemini 2.5 Flash con fallback determinÃ­stico.
3. **Lo que no existe:** catÃ¡logo de herramientas, orquestador, auditorÃ­a del asistente, widget global y permisos por rol para el agente.

### Propuesta

`docs/ASISTENTE_IA_PROPUESTA.md` (v0.1): agente con **function calling** sobre un catÃ¡logo fijo de herramientas, sin SQL libre; verificador determinÃ­stico de cifras contra las salidas de las herramientas; permisos por rol; escrituras solo con confirmaciÃ³n y por el Custodio; auditorÃ­a append-only; modo determinÃ­stico sin `GEMINI_API_KEY`; 5 fases (panel interno â†’ WhatsApp staff â†’ cliente/lead â†’ acciones â†’ RAG).

### Evidencia (real, ejecutada)

| VerificaciÃ³n | Resultado |
|---|---|
| Lectura de `docs/PDR_v4.0.txt` | Â§3.1/Â§3.2: matemÃ¡tica determinÃ­stica + juez binario, sin chatbot abierto |
| Lectura de `docs/00_DECISIONES_PENDIENTES.md` | 7 secciones Superadmin; Gemini sin key degrada al juez determinÃ­stico |
| CÃ³digo revisado | `m1_whatsapp/pipeline.py` (`_gate_lead`, `componer_respuesta_lead`), `m1_whatsapp/judges.py`, `custodio/contracts.py` (9 `QUERY_INTENTS`), `custodio/gate.py` (permisos) |
| Tutoriales | 7 archivos en `docs/tutoriales/` pensados como base del bot |
| Base | 34 tablas, 7 vistas, `chat_conversaciones`/`chat_mensajes` (070) |

### Decisiones tomadas

1. **El asistente pedirÃ¡ los nÃºmeros a herramientas; no los redactarÃ¡ de contexto.** Es la Ãºnica forma de cumplir "cero datos inventados" con un bot conversacional. Alternativa descartada: text-to-SQL de solo lectura, que expone el esquema y permite inyecciÃ³n.
2. **La propuesta queda como documento para iterar**, no como cÃ³digo, hasta que DirecciÃ³n responda las 6 decisiones de Â§10.

### Bloqueos / preguntas al cliente

1. Audiencia inicial (panel / WhatsApp staff / clientes).
2. Â¿La v1 solo consulta o tambiÃ©n acciones con confirmaciÃ³n?
3. Proveedor y presupuesto (Gemini ya integrado).
4. AprobaciÃ³n formal del cambio de alcance frente al PDR.
5. Precios y saldos para clientes.
6. Â¿Texto solo o tambiÃ©n audio?

### PrÃ³ximo paso exacto

Iterar con DirecciÃ³n sobre `docs/ASISTENTE_IA_PROPUESTA.md` Â§10; con las seis respuestas, escribir el plan tÃ©cnico de la Fase 1 y empezar `app/asistente/`.

### Archivos tocados

- `docs/ASISTENTE_IA_PROPUESTA.md` (nuevo)
- `.agents/BITACORA.md`
- `.agents/ESTADO.md`

---

## 2026-11-12 - Asistente IA: bibliotecario, skills y manos

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** inventariar los datos reales para diseÃ±ar skills de los dos bots (interno CRM y pÃºblico), definir al bibliotecario y el estado de cada "mano" del bot pÃºblico. **No se escribiÃ³ cÃ³digo.**

### Hecho

1. **Dos personas:** `HORMINOR_INTERNO` (solo CRM/panel, nunca WhatsApp, todo lo que su rol permita) y `HORMINOR_PUBLICO` (WhatsApp/web, solo datos pÃºblicos y propios).
2. **Bibliotecario:** no hay DBA/custodio designado como persona (`BASE_DE_DATOS.md` Â§5); se propone el `bibliotecario` de software con catÃ¡logo de consultas y contrato de "ficha de dato" (valor, fuente, filtro, fecha, vacÃ­o).
3. **CatÃ¡logo de 14 dominios** que el bibliotecario puede responder hoy con las 9 consultas del Custodio, 7 vistas y los endpoints del panel; y 6 cosas que todavÃ­a no puede responder.
4. **17 skills internas propuestas** (13 de lectura para la Fase 1 y 3 borradores con confirmaciÃ³n para la Fase 4).
5. **Inventario de manos pÃºblicas:** 4 existen, 3 parciales y 7 no existen (PDF, agendar, confirmaciÃ³n de SecretarÃ­a, estado de pedido, ubicaciÃ³n, multimedia pÃºblica, recordatorios), con la pieza mÃ­nima de cada una.
6. **DeepSeek** como Ãºnico modelo de atenciÃ³n, con proveedor compatible OpenAI y function calling; Gemini queda solo para el juez binario.

### Evidencia (real, ejecutada)

| VerificaciÃ³n | Resultado |
|---|---|
| `docs/BASE_DE_DATOS.md` Â§3 | 34 tablas, 7 vistas, 19 migraciones, 30 cuentas contables |
| `custodio/contracts.py` | 9 `QUERY_INTENTS` con permisos por rol en `gate.py` |
| Rutas del panel | 60+ endpoints inventariados (cartera, cierre, compras, agenda, bancos, chat, Superadmin) |
| PDF | `requirements.txt` sin WeasyPrint/reportlab; solo dossier HTML imprimible en `/api/v1/dashboard/dossier` |
| Agenda | `dispatch_schedule` (067) es logÃ­stica de entregas con mixers; no hay citas comerciales |
| ConfirmaciÃ³n | `approval_requests` es del Custodio; no hay bandeja de solicitudes pÃºblicas |
| DeepSeek | No hay integraciÃ³n previa en el repo; el patrÃ³n de proveedor ya existe en `judges.py` |

### Decisiones tomadas

1. **El bibliotecario es software, no una persona.** El bot le pide fichas de dato; no lee tablas ni escribe SQL. La designaciÃ³n de un custodio humano de la BD sigue pendiente.
2. **Interno solo por el CRM.** Sin canal WhatsApp para Julio/secretarÃ­a; la identidad es el rol del panel.
3. **Las manos pÃºblicas que no existen se construyen como piezas explÃ­citas** (`solicitudes_publicas`, `citas_comerciales`, motor PDF, biblioteca pÃºblica), no como improvisaciones del prompt.

### Bloqueos / preguntas al cliente

1. Â¿QuÃ© documentos genera el bot pÃºblico y con quÃ© motor PDF?
2. Â¿Citas de visita, llamadas o ambas?
3. Â¿La lista de precios sigue pÃºblica?
4. Modelo y endpoint exactos de DeepSeek; Â¿clave en Superadmin o `.env`?
5. Â¿Se designa custodio humano de la BD en producciÃ³n?

### PrÃ³ximo paso exacto

Iterar `docs/ASISTENTE_IA_SKILLS.md` Â§6 con DirecciÃ³n; con esas respuestas, escribir los manifiestos de skills de la Fase 1 y el plan tÃ©cnico de `app/asistente/`.

### Archivos tocados

- `docs/ASISTENTE_IA_SKILLS.md` (nuevo)
- `.agents/BITACORA.md`
- `.agents/ESTADO.md`

---

## 2026-11-12 - Asistente IA: PDF independiente, agendas, precios/costos y bibliotecario

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** integrar las definiciones de Dirección (PDF independiente, dos agendas, precios, DeepSeek en `.env`, bibliotecario como skill) y auditar si el precio está atado al costo. **No se escribió código de producto.**

### Hecho

1. **Componente PDF independiente** (`docs/ASISTENTE_IA_SKILLS.md` §8): recibe datos y devuelve PDF; no calcula precios ni lee tablas de negocio. Contrato `POST /api/v1/pdf/cotizaciones`, tablas `cotizaciones`/`cotizacion_items`, folio, validez, snapshot de precio, estado `PRELIMINAR` para el bot público. Motor recomendado: WeasyPrint.
2. **Dos agendas** (§9): `dispatch_schedule` queda para obras/entregas; se propone `citas_comerciales` para visitas (`tipo PLANTA/OBRA/VIRTUAL`, `motivo COTIZACION/MEDICION/SEGUIMIENTO`). "Visitar la obra" es un subtipo, no el default.
3. **Auditoría de precios y costos** (§10): existe editor de precio manual (`concrete_recipes.precio_m3`, Superadmin > Recetas) y costos de materiales (`materials.costo_unitario`), pero **no existe cálculo de costo por receta ni margen**. Con la semilla, el margen bruto de materiales va de 25,4% a 29,5% y no hay alerta si el precio cae bajo el costo. Hallazgo confirmado.
4. **DeepSeek** siempre, con `DEEPSEEK_API_KEY` en `.env` y parámetros en `system_settings['asistente']`.
5. **Skill `bibliotecario-bd-horminor`** creada en el patrón de front matter + sub-niveles + SOPs + checklist, con 5 sub-niveles y 5 contratos de operación.

### Evidencia (real, ejecutada)

| Verificación | Resultado |
|---|---|
| `concrete_recipes.precio_m3` | Columna manual, editable en Superadmin > Recetas (`050_seed_oficial_superadmin.sql:23-33`, `panel.html:3426`) |
| Costo de materiales | `materials.costo_unitario`; 4 de 5 con costo; `AGUA` queda `NULL` (`020_seed_recipes.sql:26-32`) |
| Cálculo de costo por receta | **No existe**: `dosificador.py` solo multiplica cantidades; no hay `costo_m3` en el código |
| Margen | `finanzas.simulador_bancario.margen_neto_m3 = 42.50` es un parámetro plano del simulador (`060:191`, `calculos.py:139`) |
| Cálculo manual con la semilla | FC-180 76,16 / FC-210 84,56 / FC-240 92,91 / FC-280 101,43 / FC-350 114,33 por m³ (solo materiales) |
| PDF | `requirements.txt` sin motor PDF; solo dossier HTML imprimible |
| Agenda | `dispatch_schedule` (067) es logística de entregas; no hay citas comerciales |
| Skill | `.agents/skills/bibliotecario-bd-horminor/SKILL.md` creada |

### Decisiones tomadas

1. **El PDF es un componente, no una función del bot.** Bot, secretaría y Julio llaman al mismo endpoint; el contenido lo arma el llamador y el componente solo valida aritmética y renderiza. Alternativa descartada: generar el PDF dentro del asistente.
2. **Una cotización no es una factura.** Lleva folio, validez y snapshot de precio; no toca SRI (fuera de alcance).
3. **El precio publicado sigue siendo decisión de Julio**, pero el sistema debe mostrar costo y margen y avisar si el precio queda bajo el costo. No se autoajusta.
4. **El bibliotecario es software con skill de operación**, no un DBA humano: la designación del custodio de producción sigue pendiente.

### Bloqueos / preguntas al cliente

1. Confirmar el contenido exacto de la cotización (ítems, condiciones, validez) y quién puede emitirla.
2. Definir si el bot público puede emitir `PRELIMINAR` sin secretaría.
3. Cargar el costo del agua y los componentes de costo (mano de obra, energía, CIF, transporte, merma).
4. Confirmar el margen objetivo por resistencia o global.
5. Designar al custodio humano de la BD en producción.

### Próximo paso exacto

Con la guía de skills de Dirección, convertir `bibliotecario-bd-horminor` al formato final y escribir los manifiestos de skills de la Fase 1 (interno) antes de tocar código.

### Archivos tocados

- `docs/ASISTENTE_IA_SKILLS.md` (§8 a §12)
- `.agents/skills/bibliotecario-bd-horminor/SKILL.md` (nuevo)
- `.agents/BITACORA.md`
- `.agents/ESTADO.md`

---

## 2026-11-12 - Skills v7.0: pilares, herramientas y handoff a Carbon

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** adoptar el estándar de skills v7.0 de GuIAloja, convertir los pilares (PDF, banca-mercado, bibliotecario) en skills gobernadoras con herramientas debajo, y dejar el documento listo para llevarlo a Carbon. **No se escribió código de producto.**

### Hecho

1. **Estándar v7.0 adaptado:** 5 componentes obligatorios (`SKILL.md`, `router.md`, `errores.md`, `roles/`, `contracts/`), frontmatter con `name/version/parent_skill/queue/description/inviolable_rules`, router por capas y contratos JSON Schema 2020-12 con `additionalProperties: false`.
2. **Mapa de 14 pilares en 5 colas** (`q_gobierno`, `q_datos`, `q_finanzas`, `q_operacion`, `q_documentos`, `q_publico`), con misiones, herramientas, contratos y fronteras.
3. **Tres skills completas en el repo:**
   - `pdf-cotizaciones` (3 roles, 2 contratos).
   - `banca-mercado` (3 roles, 2 contratos).
   - `bibliotecario-bd-horminor` actualizado al patrón (4 roles, 2 contratos propios).
4. **Handoff a Carbon:** `docs/SKILLS_PILARES_HORMINOR.md` con el encargo, el orden de construcción, la definición de terminado y los 10 vectores del árbitro adversarial (5 del estándar + 5 de Horminor).

### Evidencia (real, ejecutada)

| Verificación | Resultado |
|---|---|
| Estructura de las 3 skills | Los 5 componentes existen en las tres |
| Contratos JSON | 6 archivos parsean; `contract_name` correcto |
| Límite de roles | Máximo 53 líneas (tope 70) |
| Límite de SKILL.md | 3.110 / 3.802 / 4.455 caracteres (tope 12.000) |
| Palabras prohibidas | Sin `TODO` ni placeholders |
| Documento de handoff | `docs/SKILLS_PILARES_HORMINOR.md` (13 secciones) |

### Decisiones tomadas

1. **Cada pilar es una skill que gobierna herramientas determinísticas.** La skill decide qué pedir; la herramienta toca los datos; el contrato impide basura. Alternativa descartada: un prompt único con todas las capacidades.
2. **PDF y Banca y Mercado son pilares con skill propia**, no funciones del asistente.
3. **El bibliotecario es la única skill que lee la base**; las demás piden fichas. Ninguna escribe SQL libre.
4. **Límite de 12.000 caracteres** para `SKILL.md`, más estricto que los 15.000 de GuIAloja, para dejar contexto a las herramientas.
5. **Carbon construye un pilar a la vez**, empezando por el bibliotecario, y no se acepta la primera versión (árbitro adversarial obligatorio).

### Bloqueos / preguntas al cliente

1. Contenido exacto de la cotización y quién puede emitirla.
2. ¿El bot público emite `PRELIMINAR` sin Secretaría?
3. Costos que faltan (agua, mano de obra, energía, CIF, transporte, merma) y margen objetivo.
4. Custodio humano de la BD en producción.
5. Nombre definitivo de las colas y de la skill raíz.

### Próximo paso exacto

Llevar `docs/SKILLS_PILARES_HORMINOR.md` + el estándar v7.0 al chat de Carbon y pedir el primer pilar (`bibliotecario-datos`) con su checklist; revisar la salida y guardarla en `.agents/skills/`.

### Archivos tocados

- `docs/SKILLS_PILARES_HORMINOR.md` (nuevo)
- `docs/ASISTENTE_IA_SKILLS.md` (§13)
- `.agents/skills/pdf-cotizaciones/` (8 archivos)
- `.agents/skills/banca-mercado/` (8 archivos)
- `.agents/skills/bibliotecario-bd-horminor/` (SKILL, router, errores, 4 roles, 2 contratos)
- `.agents/BITACORA.md`
- `.agents/ESTADO.md`
- `AGENTS.md` (skill indexada)

---

## 2026-11-12 - Skills v7.0: auditoría v1.1, catálogo cerrado y arranque de Carbon

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** corregir los 7 hallazgos de la auditoría adversarial y los 2 insumos faltantes antes de construir `bibliotecario-datos` con Carbon.

### Hecho

1. **6 colas congeladas** (`q_gobierno`, `q_datos`, `q_finanzas`, `q_operacion`, `q_documentos`, `q_publico`).
2. **`parent_skill` resuelto:** `null` en raíces, string en skills de una persona, array en compartidas; se agrega `audience`.
3. **Rutas y nombres unificados:** `.agents/skills/bibliotecario-datos/` (renombrada desde `bibliotecario-bd-horminor`).
4. **Contrato de PDF corregido:** montos como texto decimal con `pattern`, `precio_ref` con `vigencia_hash`, `total_esperado`, y `pattern`/`maxLength` en RUC, teléfono, folio y condiciones.
5. **Router corregido:** condiciones por defecto vuelven a Capa 0; un rol, una capa.
6. **Catálogo cerrado nuevo:** `docs/CATALOGO_CONSULTAS.json` con 22 consultas `IMPLEMENTADA` y 6 `PROPUESTA`.
7. **`consulta.json` v1.1:** enum cerrado de 22 ids, `actor_context` obligatorio y whitelist para `persona: PUBLICO` (`recetas_precio_publico`, `empresa_info`).
8. **`ficha_dato.json` v1.1:** exige `fuente_vista_tabla`, `filtros_aplicados`, `consultado_en`, `vacio`, `vigencia_hash` y `esquema_version`.
9. **Paquete de arranque:** `docs/CARBON_ARRANQUE.md` con el orden de pegado y el encargo.

### Evidencia (real, ejecutada)

| Verificación | Resultado |
|---|---|
| Contratos JSON | 11 archivos parsean (3 skills + Custodio + catálogo) |
| Enum vs catálogo | 22 implementadas = 22 en el enum (coinciden exactamente) |
| Límite de roles | máximo 57 líneas |
| Límite de `SKILL.md` | 3.432 / 3.802 / 5.123 caracteres |
| Floats en contratos PDF | 0 ocurrencias de `"number"` |
| Documento | `docs/SKILLS_PILARES_HORMINOR.md` v1.1 con tabla de cambios |

### Decisiones tomadas

1. **El catálogo es la fuente del enum.** Ninguna consulta `PROPUESTA` se puede invocar; el contrato no la conoce.
2. **Montos como texto decimal.** Evita el float binario y permite validar aritmética exacta con `Decimal`.
3. **La vigencia del precio viaja con la línea.** Sin `vigencia_hash` no hay cotización: se cierra el vector de precio viejo.
4. **Carbon construye; el agente local actúa como árbitro adversarial.** Identidad separada, como exige el estándar.
5. **El público solo ve dos consultas.** `empresa_info` y `recetas_precio_publico`; cualquier otra se rechaza antes de ejecutar.

### Bloqueos / preguntas al cliente

1. Contenido exacto de la cotización y quién puede emitirla.
2. ¿El bot público emite `PRELIMINAR` sin Secretaría?
3. Costos faltantes y margen objetivo.
4. Custodio humano de la BD en producción.

### Próximo paso exacto

Pegar en Carbon el paquete de `docs/CARBON_ARRANQUE.md` (estándar v7.0 + `docs/SKILLS_PILARES_HORMINOR.md` v1.1 + `docs/CATALOGO_CONSULTAS.json`) y construir `bibliotecario-datos`; luego auditar la salida con el checklist de §10 y los 10 vectores de §9.

### Archivos tocados

- `docs/SKILLS_PILARES_HORMINOR.md` (v1.1)
- `docs/CATALOGO_CONSULTAS.json` (nuevo)
- `docs/CARBON_ARRANQUE.md` (nuevo)
- `docs/ASISTENTE_IA_SKILLS.md` (§13)
- `.agents/skills/bibliotecario-datos/` (renombrada y actualizada)
- `.agents/skills/pdf-cotizaciones/` (contratos, roles, router y errores)
- `.agents/skills/banca-mercado/SKILL.md` (`audience`)
- `AGENTS.md`, `.agents/ESTADO.md`, `.agents/BITACORA.md`

---

## 2026-11-12 - Arbitraje de bibliotecario-datos: contratos v1.2

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** auditar la propuesta de Carbon para `router.md`, `consulta.json` y `ficha_dato.json` del pilar #1, aceptar lo correcto y corregir lo que abría huecos.

### Veredicto

**Aprobado con 2 correcciones obligatorias.**

Aceptado: 12 parámetros (sin `folio`, con `fecha`), `requeridos` por consulta, `persona=PUBLICO` exige `rol=BOT_PUBLICO`, `ficha_id`, `consulta_id`, `nota` obligatoria en vacío, `vigencia_hash` obligatorio en precios y Capa 2 N/A en el bibliotecario.

Rechazado:

1. **`tipo_valor` con `OBJETO|LISTA`**: `valor` volvería a admitir objetos y no se puede garantizar por JSON Schema que los montos anidados sean texto. Regla: `valor` escalar; una tabla son varias fichas.
2. **`fuente_vista_tabla` con 25 fuentes**: `sabueso` y `sentinel` son servicios, no relaciones. Enum reducido a 23 relaciones reales; el servicio se identifica con `consulta_id`.

### Hecho

1. **Catálogo v1.1:** campo `requeridos` en las 22 implementadas y en las 6 propuestas.
2. **`consulta.json` v1.2:** enum de 22, 12 parámetros, 13 condicionales de requeridos + whitelist pública con rol.
3. **`ficha_dato.json` v1.2:** `ficha_id`, `consulta_id`, 23 fuentes, `nota`, condicionales de tipo, vacío y vigencia.
4. **`router.md`:** Capa 2 N/A; la explicación queda en el pilar consumidor.
5. **`docs/CARBON_ARRANQUE.md` v1.2** actualizado para que Carbon reconstruya sin adivinar.
6. **`docs/SKILLS_PILARES_HORMINOR.md` §16** con el arbitraje y la evidencia.

### Evidencia (real, ejecutada)

| Caso | Resultado |
|---|---|
| Interno `cliente_ficha` con `cliente_id` | VÁLIDO |
| Interno `cliente_ficha` sin `cliente_id` | INVÁLIDO (`cliente_id` required) |
| Público `empresa_info` con `BOT_PUBLICO` | VÁLIDO |
| Público `cartera_cliente` | INVÁLIDO (fuera de whitelist) |
| Público con rol `SECRETARIA` | INVÁLIDO (exige `BOT_PUBLICO`) |
| Parámetro `folio` en implementada | INVÁLIDO (no existe) |
| Ficha DECIMAL como número | INVÁLIDO (exige texto) |
| Ficha vacía sin nota | INVÁLIDO (`nota` requerida) |
| Precio sin `vigencia_hash` | INVÁLIDO |
| Fuente `sabueso` | INVÁLIDO (no es relación) |
| Conteos | 22 consultas, 12 parámetros, 23 fuentes, 14 `allOf` |

### Decisiones tomadas

1. **El catálogo declara los requeridos.** El contrato los copia; Carbon no adivina.
2. **La ficha es escalar.** Las tablas se devuelven como varias fichas; así se puede exigir texto decimal sin excepciones.
3. **Solo relaciones reales como fuente.** Los servicios se referencian por `consulta_id`.
4. **El bibliotecario no redacta.** Capa 2 vive en el consumidor.

### Bloqueos / preguntas al cliente

Siguen las 4 decisiones de negocio: contenido de la cotización, `PRELIMINAR` sin Secretaría, costos faltantes/margen y custodio humano de la BD.

### Próximo paso exacto

Pegar en Carbon `docs/CARBON_ARRANQUE.md` v1.2 + catálogo v1.1 y reconstruir `bibliotecario-datos`; auditar la salida con los 10 vectores.

### Archivos tocados

- `docs/CATALOGO_CONSULTAS.json` (v1.1, `requeridos`)
- `docs/CARBON_ARRANQUE.md` (v1.2)
- `docs/SKILLS_PILARES_HORMINOR.md` (v1.2, §16)
- `.agents/skills/bibliotecario-datos/contracts/consulta.json` (v1.2)
- `.agents/skills/bibliotecario-datos/contracts/ficha_dato.json` (v1.2)
- `.agents/skills/bibliotecario-datos/router.md`
- `.agents/skills/bibliotecario-datos/SKILL.md`
- `.agents/skills/bibliotecario-datos/roles/02_guardian.md`
- `.agents/skills/bibliotecario-datos/roles/03_privacidad.md`
- `.agents/skills/bibliotecario-datos/errores.md`
- `.agents/BITACORA.md`
- `.agents/ESTADO.md`

---

## 2026-11-12 - Ajuste v1.3: ACL por consulta, DECIMAL negativo y PDF 1:1

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** cerrar los cuatro frentes de auditoría anticipados por Dirección antes de disparar Carbon.

### Hecho

1. **ACL por consulta en `consulta.json` v1.3:** 22 condicionales `if/then` que restringen `actor_context.rol` a los roles del catálogo. `balance`, `resultados`, `banco_detalle` y `salud_sistema` quedan fuera de `BODEGA` y `SECRETARIA`.
2. **DECIMAL negativo:** el `pattern` de `ficha_dato.json` acepta `-1234.56` como texto y rechaza el número `-1234.56`.
3. **PDF 1:1:** `precio_ref.ficha_precio_id` se renombró a `precio_ref.ficha_id`; es exactamente el `ficha_id` de la ficha de precio. Contrato `solicitud_cotizacion` v1.2.0.
4. **Referencias de versión:** `docs/CARBON_ARRANQUE.md` apunta a `SKILLS_PILARES_HORMINOR.md` v1.2 y al catálogo v1.1.
5. **Checklist de §11** ampliado con ACL, negativos y calce con PDF.

### Evidencia (real, ejecutada)

| Caso | Resultado |
|---|---|
| `SECRETARIA` + `balance` | INVÁLIDO (solo SUPERADMIN/CONTADORA) |
| `BODEGA` + `resultados` | INVÁLIDO |
| `SECRETARIA` + `banco_detalle` | INVÁLIDO |
| `BODEGA` + `salud_sistema` | INVÁLIDO (solo SUPERADMIN) |
| `BODEGA` + `stock_actual` | VÁLIDO |
| `SECRETARIA` + `cartera_cliente` | VÁLIDO |
| `BOT_PUBLICO` + `empresa_info` | VÁLIDO |
| `BOT_PUBLICO` + `banco_detalle` | INVÁLIDO (whitelist) |
| Ficha DECIMAL `"-1234.56"` | VÁLIDO |
| Ficha DECIMAL `-1234.56` (number) | INVÁLIDO |
| Solicitud PDF con `ficha_id` + hash | VÁLIDO |
| Solicitud PDF sin `ficha_id` | INVÁLIDO |

### Decisiones tomadas

1. **La ACL vive en el contrato, no solo en el rol.** Así un pilar no puede pedir una consulta que su rol no tiene aunque el modelo se equivoque.
2. **Los negativos son texto decimal.** No se abre la puerta a floats para "facilitar" resultados y ajustes.
3. **Un solo identificador de ficha.** `ficha_id` es la llave entre bibliotecario y PDF; no hay dos nombres para lo mismo.

### Próximo paso exacto

Pegar en Carbon `docs/SKILLS_PILARES_HORMINOR.md` v1.2 + `docs/CATALOGO_CONSULTAS.json` v1.1 + `docs/CARBON_ARRANQUE.md` v1.2 y reconstruir `bibliotecario-datos`; luego auditar los 9 archivos con los 10 vectores.

### Archivos tocados

- `.agents/skills/bibliotecario-datos/contracts/consulta.json` (v1.3)
- `.agents/skills/pdf-cotizaciones/contracts/solicitud_cotizacion.json` (v1.2.0)
- `docs/CARBON_ARRANQUE.md`
- `docs/SKILLS_PILARES_HORMINOR.md` (§16)
- `.agents/BITACORA.md`
- `.agents/ESTADO.md`

---

## 2026-11-12 - Protocolo único de auditoría de skills y limpieza

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** centralizar las auditorías con Carbon, cerrar los 3 micro-detalles del pre-vuelo y borrar el contenido histórico que ya no hace falta en el handoff.

### Hecho

1. **3 micro-detalles cerrados:**
   - `CARBON_ARRANQUE.md` §7.4: cada condicional restringe `actor_context.rol` al array `roles`; `persona=INTERNO` no admite `BOT_PUBLICO`.
   - `ficha_dato.json` v1.3: `fuente_vista_tabla` es **array no vacío y único** de las 23 relaciones (soporta consultas multi-tabla).
   - Documento §5.3: `solicitud_cotizacion` 1.2.0 y `ficha_id` con patrón UUID, igual que el contrato PDF.
2. **Protocolo único:** `docs/AUDITORIA_SKILLS_CARBON.md` con flujo, pre-vuelo, 10 vectores, matriz por pilar, formato de veredicto, registro histórico y puntos congelados.
3. **Auditor determinista:** `scripts/auditar_skills.py` (175 verificaciones) con salida a `.agents/evidencias/`.
4. **Limpieza:** se quitaron §15 y §16 del handoff (historia movida al registro del protocolo) y se borraron 30 scripts temporales de auditoría.

### Evidencia (real, ejecutada)

| Verificación | Resultado |
|---|---|
| `python scripts/auditar_skills.py` | **APROBADO (175 verificaciones)** |
| `consulta.json` | v1.3.0, 22 consultas, 12 parámetros, 23 `allOf` |
| `ficha_dato.json` | v1.3.0, `fuente_vista_tabla` array de 23 |
| `solicitud_cotizacion.json` | v1.2.0, `ficha_id` UUID |
| Documentos | 0 caracteres corruptos; §15/§16 eliminadas |
| ACL | `balance`, `resultados`, `banco_detalle`, `salud_sistema` rechazan `BODEGA`/`SECRETARIA` |
| PDF | solicitud con `ficha_id` + `vigencia_hash` válida |

### Decisiones tomadas

1. **Un solo protocolo de auditoría.** El handoff queda para Carbon; el historial y los criterios viven en `AUDITORIA_SKILLS_CARBON.md`.
2. **Lo congelado no se re-audita.** 22 consultas, 12 parámetros, 23 fuentes, ACL y calce PDF quedan cubiertos por el script.
3. **`fuente_vista_tabla` como array.** Una ficha puede citar varias relaciones sin romper las consultas multi-tabla.
4. **La verificación es reproducible.** El script reemplaza los chequeos manuales temporales.

### Próximo paso exacto

Pegar en Carbon el paquete v1.3 (estándar + `SKILLS_PILARES_HORMINOR.md` v1.3 + `CATALOGO_CONSULTAS.json` v1.1 + `CARBON_ARRANQUE.md` v1.3), recibir los 9 archivos y correr `scripts/auditar_skills.py` + los 10 vectores.

### Archivos tocados

- `docs/AUDITORIA_SKILLS_CARBON.md` (nuevo)
- `scripts/auditar_skills.py` (nuevo)
- `docs/SKILLS_PILARES_HORMINOR.md` (v1.3, sin §15/§16)
- `docs/CARBON_ARRANQUE.md` (v1.3)
- `docs/CATALOGO_CONSULTAS.json` (v1.1, ya con `requeridos`)
- `.agents/skills/bibliotecario-datos/contracts/consulta.json` (v1.3)
- `.agents/skills/bibliotecario-datos/contracts/ficha_dato.json` (v1.3)
- `.agents/skills/pdf-cotizaciones/contracts/solicitud_cotizacion.json` (v1.2.0)
- `.agents/skills/bibliotecario-datos/roles/02_guardian.md`
- `.agents/skills/bibliotecario-datos/SKILL.md`
- `.agents/evidencias/auditoria_skills_2026-11-12.txt`
- `.agents/ESTADO.md` y `.agents/BITACORA.md`

---

## 2026-11-12 - Corrección del pre-vuelo v1.3: bloqueo cruzado y roles de 40 líneas

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** verificar la afirmación de "23 reglas y roles de 40–70" antes de dar el visto bueno; se encontraron dos huecos reales en el repo.

### Hallazgos

1. **El bloqueo cruzado INTERNO/BOT_PUBLICO estaba en el prompt, no en el contrato.** `consulta.json` permitía `persona=INTERNO` con `rol=BOT_PUBLICO` en las dos consultas públicas. Se agregó el condicional 24: `persona=INTERNO` exige rol `SUPERADMIN|CONTADORA|SECRETARIA|BODEGA`.
2. **Dos roles estaban por debajo de 40 líneas:** `01_catalogo.md` (38) y `04_migraciones.md` (30), y `pdf/02_emisor.md` (37). El estándar pide 40–70. Se expandieron con contenido real (defaults, evidencia, checklist), no relleno.

### Hecho

- `consulta.json` → v1.4.0 con **24 `allOf`** (22 consultas + whitelist + bloqueo cruzado).
- Roles: `01_catalogo` 53, `02_guardian` 52, `03_privacidad` 41, `04_migraciones` 47, `pdf/02_emisor` 45.
- `scripts/auditar_skills.py`: exige 24 `allOf`, verifica el bloqueo cruzado, exige 40–70 líneas y agrega el caso `INTERNO + BOT_PUBLICO`.
- `docs/CARBON_ARRANQUE.md` §7.4 y §11: la cifra correcta son **24 reglas**.
- Registro de auditoría con la fila "Pre-vuelo v1.3".

### Evidencia (real, ejecutada)

| Verificación | Resultado |
|---|---|
| `python scripts/auditar_skills.py` | **APROBADO (177 verificaciones)** |
| `INTERNO + BOT_PUBLICO + empresa_info` | RECHAZADO |
| `PUBLICO + BOT_PUBLICO + empresa_info` | VÁLIDO |
| Roles | 41–53 líneas (dentro de 40–70) |
| `consulta.json` | v1.4.0, 24 `allOf` |

### Decisión

**No se aprobó la afirmación "23 reglas" hasta corregirla.** El mensaje de pre-vuelo era correcto en todo lo demás, pero daba por cerrado un bloqueo que solo existía en el prompt. La regla queda: un criterio no está implementado hasta que el contrato lo rechaza y el auditor lo prueba.

### Próximo paso exacto

Pegar en Carbon el paquete con `CARBON_ARRANQUE.md` actualizado (24 reglas) y auditar los 9 archivos con el script de 177 verificaciones.

### Archivos tocados

- `.agents/skills/bibliotecario-datos/contracts/consulta.json` (v1.4.0)
- `.agents/skills/bibliotecario-datos/roles/01_catalogo.md` y `04_migraciones.md`
- `.agents/skills/pdf-cotizaciones/roles/02_emisor.md`
- `scripts/auditar_skills.py`
- `docs/AUDITORIA_SKILLS_CARBON.md`
- `docs/CARBON_ARRANQUE.md`
- `docs/SKILLS_PILARES_HORMINOR.md`
- `.agents/evidencias/auditoria_skills_2026-11-12.txt`
- `.agents/ESTADO.md` y `.agents/BITACORA.md`

---

## 2026-11-12 - Continuación autónoma: pilar #1 aprobado y documento de retorno

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** seguir sin Dirección presente, dejar el pilar #1 auditado y un punto de retorno claro.

### Hecho

1. **Veredicto del pilar #1 de referencia:** 10/10 vectores OK, checklist completo y 177 verificaciones en verde. Queda como vara para la entrega de Carbon.
2. **Registro de auditoría actualizado:** fila "Pilar #1 (referencia) APROBADO" y "entrega Carbon PENDIENTE".
3. **PDF:** `SKILL.md` alineado a la versión 1.2.0 del contrato.
4. **Documento de retorno:** `docs/CONTINUACION_2026-11-12.md` con estado, pendientes, comandos y decisiones abiertas.

### Evidencia (real, ejecutada)

| Verificación | Resultado |
|---|---|
| `python scripts/auditar_skills.py` | **APROBADO (177 verificaciones)** |
| Vectores del pilar #1 | 10/10 OK |
| Roles | 41–57 líneas (40–70) |
| `consulta.json` | v1.4.0, 24 `allOf` |
| `ficha_dato.json` | v1.3.0 |
| `solicitud_cotizacion.json` | v1.2.0 |

### Decisión

**La referencia no reemplaza la entrega de Carbon.** Se aprueba como vara y como implementación local, pero la ronda adversarial con Carbon sigue pendiente.

### Próximo paso exacto

Al volver: pegar los 9 archivos de Carbon, correr `python scripts/auditar_skills.py`, pasar §9/§10 y registrar el veredicto. Después: pilar #2 `pdf-cotizaciones`.

### Archivos tocados

- `docs/AUDITORIA_SKILLS_CARBON.md` (§11 y registro)
- `docs/CONTINUACION_2026-11-12.md` (nuevo)
- `.agents/skills/pdf-cotizaciones/SKILL.md` (versión 1.2.0)
- `.agents/BITACORA.md`
- `.agents/ESTADO.md`

---

## 2026-11-12 - Gato: bot interno para Julio y secretaría (loop con datos ficticios)

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** construir el asistente interno `HORMINOR_INTERNO` ("Gato"), probarlo en loop con preguntas reales de Julio y la secretaria, y usar una base ficticia separada.

### Hecho

1. **Persona "Gato"** en `services/core-api/app/asistente/persona.py` y `docs/GATO_PROMPT.md`: gato operativo, "jefe"/"seño", regla de no inventar cifras, permisos y tono.
2. **Bibliotecario de solo lectura** (`app/asistente/bibliotecario.py`): cartera, cliente, cierre, stock, bancos, agenda, órdenes y precios.
3. **Gato determinista** (`app/asistente/gato.py`): 9 intenciones por palabras clave, permisos por rol, formato ecuatoriano (`$5.043,60`), fuente y fecha en cada respuesta.
4. **Base ficticia aislada:** `orminorth_gato_test` (copia de `orminorth_panel_test`) + `db/seeds/gato_ficticio.sql`, todo marcado `[FICTICIO]`/`FICT-`.
5. **Loop de 25 preguntas** (`scripts/gato_loop.py`): Julio y secretaría; incluye rechazo de bancos para secretaría.
6. **Tests:** 15 pruebas puras en `tests/test_gato.py`; suite total **311 passed**.
7. **Documentación:** `docs/GATO_CORPUS.md` con preguntas, datos sembrados, permisos y comandos.

### Evidencia (real, ejecutada)

| Verificación | Resultado |
|---|---|
| `python scripts/gato_loop.py` | **25 preguntas · 0 errores · RESULTADO: OK** (`.agents/evidencias/gato_loop_2026-11-12.txt`) |
| `pytest /app/tests -q` | **311 passed** en 7.92 s (`pytest_gato_2026-11-12.txt`) |
| Base ficticia | 3 clientes, 3 órdenes, 3 pagos, 1 cierre, 2 entregas, 3 bancos, 1 préstamo |
| Permiso secretaría | "¿Cuánto hay en el Pichincha?" → rechazo con alternativa |
| Permiso Julio | Pichincha muestra contable, informado y préstamo |
| Formato | `$63.619,60`, `-$20,00`, `m³`, `sacos` |

### Decisiones tomadas

1. **Base de prueba separada.** `orminorth_gato_test` evita mezclar ficción con datos reales; la semilla es idempotente y todo lleva marca.
2. **Determinista primero.** El loop funciona sin `DEEPSEEK_API_KEY`; el prompt queda listo para el modelo cuando se configure.
3. **Permisos en código, no en el prompt.** La secretaría no ve bancos aunque el modelo se equivoque.
4. **Gato no ejecuta.** Solo consulta; los borradores de cobro/gasto/orden quedan para la fase con Custodio.
5. **Fuente legible + técnica.** "cartera (v_cliente_saldo)" para trazabilidad sin perder lenguaje simple.

### Bloqueos / preguntas al cliente

1. ¿Confirmás el tono de Gato ("jefe"/"seño", "miau" una vez)?
2. ¿Qué preguntas faltan del día a día de la secretaria?
3. ¿La secretaría puede ver precios de venta? Hoy sí; costos no.

### Próximo paso exacto

Conectar `DEEPSEEK_API_KEY` y usar `PROMPT_GATO` como system; exponer `POST /api/v1/asistente/chat` con el rol del panel y auditar cada turno. Después, reemplazar el router por palabras clave con function calling sobre las 22 consultas del bibliotecario.

### Archivos tocados

- `services/core-api/app/asistente/` (nuevo: `persona.py`, `bibliotecario.py`, `gato.py`, `__init__.py`)
- `services/core-api/tests/test_gato.py` (nuevo)
- `scripts/gato_loop.py` (nuevo)
- `db/seeds/gato_ficticio.sql` (nuevo)
- `docs/GATO_PROMPT.md` y `docs/GATO_CORPUS.md` (nuevos)
- `.agents/evidencias/gato_loop_2026-11-12.txt` y `pytest_gato_2026-11-12.txt`
- `.agents/BITACORA.md`
- `.agents/ESTADO.md`

---

## 2026-11-12 - Gato v2.0: pilares, ACL desde catálogo y guarda de cifras

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** corregir los 6 fallos de arquitectura de Gato v1.0 (router rígido, bypass de pilares, ACL en el prompt, fuentes inventadas, voseo y estados mezclados).

### Hecho

1. **Pilares reales:** `app/asistente/pilares.py` define cartera-cobros, caja-cierre, banca-mercado, planta-inventario, agenda-obras-visitas y configuracion-precios. Gato ya no llama al bibliotecario directo: pilar → acción → consulta nombrada.
2. **ACL desde el catálogo:** `catalogo.py` espeja las 22 consultas y sus roles. El orquestador rechaza con estado `ACL` antes de ejecutar. Secretaría no ve cartera total, stock ni bancos; Contadora sí ve bancos; Bodega ve stock.
3. **Prompt v2.0 en español de Ecuador:** tuteo, `actor_context` inyectado, herramientas filtradas por rol, tres estados distintos, trazabilidad desde la ficha y "miau" prohibido en errores.
4. **Fichas y guarda:** `fichas.py` + `herramientas.py` generan fichas con fuente, filtros, fecha y valores; `guardas.py` rechaza cualquier cifra del texto que no exista en las fichas.
5. **Multi-paso y repregunta:** cliente por nombre → `cartera_cliente`; si falta número de orden, banco, fecha o cliente, Gato pregunta una sola vez.
6. **Tool calling DeepSeek:** `proveedores.py` arma `tools=[...]` desde los pilares filtrados por rol, con loop de hasta 3 pasos y la misma guarda. Sin `DEEPSEEK_API_KEY`, el modo determinista usa los mismos pilares.
7. **Base ficticia:** `orminorth_gato_test` + `db/seeds/gato_ficticio.sql`; el loop cubre 25 preguntas y 4 roles.

### Evidencia (real, ejecutada)

| Verificación | Resultado |
|---|---|
| `python scripts/gato_loop.py` | **25 preguntas · 0 errores · RESULTADO: OK** |
| `pytest /app/tests -q` | **318 passed** en 11.66 s |
| ACL Secretaría | `cartera_total`, `stock_actual` y `banco_detalle` → **ACL** |
| ACL Contadora | `banco_detalle` → **OK** |
| ACL Bodega | `stock_actual` → **OK**; `cartera_total` → **ACL** |
| Falta parámetro | "orden de Los Andes" → pide número; "préstamo" → pide banco |
| Multi-paso | "¿Cuánto debe Los Andes y hay cemento?" → dos bloques |
| Guarda de cifras | una cifra sin ficha bloquea la respuesta |
| PROPUESTA | costo/margen → "aún no habilitada" |

### Decisiones tomadas

1. **El prompt no lleva permisos.** Los permisos salen del catálogo y de `pilares.py`; el prompt solo describe el rol y el tono.
2. **Gato pide a los pilares, no al bibliotecario.** Así conserva las reglas de negocio de cada pilar.
3. **Tres estados separados.** Falta parámetro ≠ vacío ≠ ACL/PROPUESTA.
4. **Trazabilidad literal de la ficha.** `fuente_vista_tabla`, `filtros_aplicados` y `consultado_en`; no etiquetas inventadas.
5. **Español de Ecuador.** Se eliminó el voseo rioplatense; "miau" solo en respuestas normales.
6. **DeepSeek opcional pero cableado.** El modo determinista corre sin clave y usa los mismos pilares.

### Bloqueos / preguntas al cliente

1. ¿Confirmas que Secretaría no debe ver el total agregado de cartera? Hoy el catálogo lo restringe.
2. ¿La Contadora debe ver stock? El catálogo dice que sí; el prompt no lo restringe.
3. ¿Qué otras preguntas del día a día faltan en el corpus?

### Próximo paso exacto

Exponer `POST /api/v1/asistente/chat` con `actor_context` del panel y registrar cada turno; después implementar los handlers de las consultas aún no conectadas (balance, resultados, compras, por pagar, disponibilidad, viaje).

### Archivos tocados

- `services/core-api/app/asistente/` (`pilares.py`, `catalogo.py`, `fichas.py`, `herramientas.py`, `orquestador.py`, `redactor.py`, `guardas.py`, `proveedores.py`, `texto.py`, `persona.py`, `gato.py`)
- `services/core-api/tests/test_gato.py`
- `scripts/gato_loop.py`
- `docs/GATO_PROMPT.md` y `docs/GATO_CORPUS.md` (v2.0)
- `.agents/evidencias/gato_loop_2026-11-12.txt` y `pytest_gato_2026-11-12.txt`
- `.agents/ESTADO.md` y `.agents/BITACORA.md`

---

## 2026-11-12 - Gato v2.1: 22 consultas conectadas, guarda blindada y endpoint seguro

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** cerrar los 5 huecos de la auditoría de Gato v2.0 antes de prender DeepSeek y exponer el endpoint.

### Hecho

1. **13 handlers nuevos** hasta completar las 22 consultas del catálogo: `cliente_ficha`, `movimientos_dia`, `stock_proyectado`, `viaje_estado`, `balance`, `resultados`, `compras_pendientes`, `por_pagar`, `disponibilidad_agenda`, `banco_movimientos`, `cuota_mercado`, `empresa_info` y `salud_sistema`. **0 consultas `NO_CONECTADA`**.
2. **Guarda de cifras v2:** acepta `$63.619,60` y `$63,619.60`, negativos `-$20.00`, ignora códigos `FC-210/FC-280`, bloquea cantidades inventadas (`999 sacos`) y exige ficha para "4 clientes".
3. **Orden por cliente:** "¿Cómo va la orden de Los Andes?" busca al cliente y lista sus órdenes; si hay una, la responde. Ya no rebota pidiendo número.
4. **Endpoint `POST /api/v1/asistente/chat`:** el body solo acepta `mensaje` y `conversacion_id`; `actor_context` en el body devuelve 422. El rol sale de `X-Panel-Role` (puente temporal hasta el login); sin rol, 401.
5. **DeepSeek en `.env`:** `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL` y `GATO_LLM=1`; la `DEEPSEEK_API_KEY` quedó vacía porque la clave del mensaje estaba truncada. Al pegarla, `proveedores.py` se activa sin tocar código.
6. **Loop ampliado a 39 preguntas**, con cobertura de los handlers nuevos y 5 trampas (inyección, ambigüedad, banco sin nombre, multi-pilar, orden por cliente).

### Evidencia (real, ejecutada)

| Verificación | Resultado |
|---|---|
| `python scripts/gato_loop.py` | **39 preguntas · 0 errores · OK** |
| `pytest /app/tests -q` | **332 passed** en 7.72 s |
| `scripts/auditar_skills.py` | **177 verificaciones** |
| Guarda US/EU | `$63,619.60` y `$63.619,60` válidos; `999 sacos` rechazado |
| Sin rol en el endpoint | **401** |
| `actor_context` en el body | **422** |
| Orden por cliente | lista la #58 de Los Andes |
| Balance | "todas las cuentas en cero" (sin cifras inventadas) |
| Cuota Orellana | 120.000 m³, 372 m³, 0,31% |
| Mixers mañana | MIXER-01/02 ocupados, MIXER-03 libre |

### Decisiones tomadas

1. **Los permisos no viajan en el body.** El backend resuelve el actor; el request no puede escalar rol.
2. **La guarda es tolerante al formato, no a la invención.** Acepta los dos formatos monetarios y sigue bloqueando cifras sin ficha.
3. **Cartera total sigue cerrada para Secretaría.** Ve saldo por cliente, no el acumulado.
4. **`pilares.py` es provisional.** Cuando cada pilar pase por Carbon y el árbitro, se ajusta a los contratos de las skills; nunca al revés.
5. **Balance sin movimientos se dice en cero**, no se inventa un saldo.

### Bloqueos / preguntas al cliente

1. Pegar la `DEEPSEEK_API_KEY` completa en `.env` para correr el loop con LLM real.
2. Confirmar si Secretaría debe ver el acumulado de cartera (hoy bloqueado por catálogo).

### Próximo paso exacto

Pegar la clave completa en `.env`, reiniciar `core-api` y correr `GATO_LLM=1 python scripts/gato_loop.py`; revisar las 39 respuestas con DeepSeek real y las 5 trampas.

### Archivos tocados

- `services/core-api/app/asistente/` (`bibliotecario.py`, `herramientas.py`, `pilares.py`, `orquestador.py`, `redactor.py`, `guardas.py`, `proveedores.py`, `router.py`)
- `services/core-api/app/main.py` (router)
- `services/core-api/tests/test_gato.py` y `test_asistente_router.py`
- `scripts/gato_loop.py`
- `.env` y `.env.example` (DeepSeek)
- `docs/GATO_PROMPT.md` y `docs/GATO_CORPUS.md`
- `.agents/evidencias/gato_loop_2026-11-12.txt` y `pytest_gato_2026-11-12.txt`
- `.agents/ESTADO.md` y `.agents/BITACORA.md`

---

## 2026-11-12 - Gato visible en el panel y DeepSeek en vivo (39/0)

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** hacer visible a Gato en el panel y probarlo con DeepSeek real, no solo en modo determinista.

### Hecho

1. **Widget de Gato en `/panel`:** botón flotante "Gato" abajo a la derecha, panel de chat con historial, estados y render de tablas Markdown. Usa `api()` y el perfil de "Viendo como".
2. **Actor desde la sesión:** el endpoint resuelve el rol desde `X-Panel-User` contra `panel_users_acl`; el body sigue prohibiendo `actor_context`.
3. **DeepSeek en vivo:** `DEEPSEEK_API_KEY` configurada (35 chars), `GATO_LLM=1`; el loop de 39 preguntas corrió con el modelo real y **0 errores**.
4. **Fichas derivadas:** `faltante_para_minimo`, `total_m3`, `entregas`, `cupo_disponible` para que la guarda acepte cálculos legítimos del LLM (380 sacos, 72 m³, 2.640 USD).
5. **Regla FC:** el prompt aclara que FC-180/210/240/280/350 son resistencias, no órdenes; el tool de precios ya no se confunde.
6. **Payload de tools con `datos`:** el LLM recibe la ficha y el dato crudo para estados (orden, agenda), sin perder la guarda de cifras.
7. **`gato_loop.py` con UTF-8:** ya no revienta al imprimir `→` en consola Windows.

### Evidencia (real, ejecutada)

| Verificación | Resultado |
|---|---|
| `python scripts/gato_loop.py` con DeepSeek | **39 preguntas · 0 errores · 0 `ERROR` de guarda** (`.agents/evidencias/gato_loop_llm_2026-11-12.txt`) |
| `pytest /app/tests -q` | **332 passed** en 13.11 s |
| `scripts/auditar_skills.py` | **177 verificaciones** |
| Endpoint con `X-Panel-User` | 200 y respuesta con fuente |
| Endpoint sin sesión | 401 |
| `actor_context` en body | 422 |
| Panel | widget visible y respuesta en vivo (`panel_gato_v21_2026-11-12.png`) |
| Precio FC-210 | 118.00 USD/m³ (ya no lo confunde con orden) |
| Stock proyectado | 120 sacos, mínimo 500, faltan 380 (ficha) |
| Agenda | 2 entregas, 72.00 m³ (ficha) |

### Decisiones tomadas

1. **El widget usa el perfil del panel, no un rol escrito en el body.** El backend resuelve el rol; no hay escalación desde DevTools.
2. **El LLM puede calcular diferencias, pero solo si la ficha las respalda.** Se agregaron fichas derivadas; la guarda sigue bloqueando lo inventado.
3. **El LLM recibe `datos` además de fichas.** Sin eso no podía decir el estado de una orden; la guarda de cifras sigue siendo la última puerta.
4. **Las resistencias FC no son órdenes.** Se corrigió en prompt y descripción de tools.

### Próximo paso exacto

Probar el widget con el perfil de Secretaría ("Viendo como") para ver el rechazo de bancos/stock en vivo, y luego cargar preguntas reales de la operación.

### Archivos tocados

- `services/core-api/app/web/templates/panel.html` (widget Gato)
- `services/core-api/app/asistente/router.py` (actor desde `panel_users_acl`)
- `services/core-api/app/asistente/` (`persona.py`, `pilares.py`, `herramientas.py`, `guardas.py`, `proveedores.py`, `redactor.py`)
- `scripts/gato_loop.py` (UTF-8)
- `.env` (DeepSeek ya configurado)
- `.agents/evidencias/gato_loop_llm_2026-11-12.txt`, `gato_loop_deterministico_2026-11-12.txt`, `panel_gato_v21_2026-11-12.png`
- `.agents/ESTADO.md` y `.agents/BITACORA.md`

---

## 2026-11-12 - Gato con estilo WhatsApp, fondo opaco y sesión por defecto

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** corregir el fondo transparente del widget y el error "Sesión no autenticada" cuando el panel no tiene perfil seleccionado.

### Hecho

1. **Estilo WhatsApp:** el widget reutiliza las clases `.chat-*` del chat de clientes: fondo sólido, cabecera, burbujas con cola, hora, separador "Hoy" y compositor.
2. **Fondo opaco:** `#0F172A` en noche y `#FFFFFF` en día; se acabó el efecto transparente sobre las fotos.
3. **Tablas legibles:** cabeceras con salto de línea, celdas numéricas alineadas a la derecha y scroll horizontal si hace falta.
4. **Sesión por defecto:** si no hay perfil en "Viendo como", el widget envía `X-Panel-Role: julio` (la misma opción base del selector) en vez de fallar con 401. Si hay perfil, usa su UUID.
5. **Cierre:** botón × en la cabecera y `aria-expanded` en el botón flotante.

### Evidencia (real, ejecutada)

| Verificación | Resultado |
|---|---|
| Panel con perfil Julio | Widget opaco, burbujas WhatsApp y tabla (`panel_gato_v21_2026-11-12.png`) |
| Panel sin perfil | Responde como Julio base, sin 401 |
| Respuesta en vivo | "Jefe, hay 2 clientes con saldo… USD 55.043,60" + tabla |
| `pytest /app/tests -q` | **332 passed** |
| `scripts/auditar_skills.py` | **177 verificaciones** |

### Decisiones tomadas

1. **Se reutiliza el chat existente, no se inventa otro estilo.** Menos CSS y la misma sensación que el chat de clientes.
2. **Sin perfil se usa Julio base, no se bloquea la demo.** El selector ya ofrece "Julio (base Superadmin)" como opción vacía; el widget la respeta.
3. **La tabla se adapta al ancho del panel.** Cabeceras en dos líneas y números a la derecha.

### Próximo paso exacto

Probar el widget con "Viendo como" en Secretaría, Bodega y Contadora para ver los rechazos y permisos en vivo.

### Archivos tocados

- `services/core-api/app/web/templates/panel.html` (widget)
- `.agents/evidencias/panel_gato_v21_2026-11-12.png`
- `.agents/ESTADO.md` y `.agents/BITACORA.md`

---

## 2026-11-12 - Facturas internas v6.13 y prueba con Gato

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** comprobar si Gato puede acceder a facturas. Dirección pidió que la
factura se pueda adjuntar como PDF o foto y que exista una factura ficticia
para probar, sin abrir la facturación electrónica del SRI.

### Hecho

1. **Migración 073** (`client_invoices`): factura interna por cliente, ligada
   opcionalmente a una orden, con subtotal/IVA/total, estado, `es_ficticia`,
   nota y `media_id`. Restricción `total = subtotal + iva_monto`.
2. **PDF interno** (`app/services/factura_pdf.py`): documento imprimible con
   banner **FICTICIA** y la leyenda "NO ES UN COMPROBANTE ELECTRÓNICO DEL SRI".
   Usa DejaVu y Pillow; no agrega dependencias.
3. **Factura de prueba** (`scripts/factura_prueba.py`): crea `PRUEBA-0001` para
   Ing. Reyes con los montos reales de la orden #55 ($37.760 + IVA $5.664 =
   **$43.424**). Es idempotente y guarda el PDF en el volumen de media.
4. **API** (`routers/facturas.py`): `GET/POST /api/v1/clients/{id}/facturas`.
   Acepta PDF, JPG, PNG y WEBP; con orden toma los montos, sin orden exige el
   total. Duplicados responden 409. La subida usa el mismo almacenamiento de
   Bunny/sandbox que el chat.
5. **Panel**: pestaña **Facturas** en el expediente, listado con badge
   FICTICIA y formulario para adjuntar PDF/foto.
6. **Gato**: nueva consulta `cliente_facturas` y acción
   `cartera-cobros/facturas_cliente` (SUPERADMIN, CONTADORA, SECRETARÍA).
   Gato marca la ficticia, muestra el enlace y aclara que el SRI está fuera de
   alcance. En modo determinista y con DeepSeek real.
7. **Documento para Evolution API** (`docs/EVOLUTION_API_PRUEBA.md`): lista
   cerrada de lo que falta para probar WhatsApp real (URL, instancia, API key,
   número corporativo, teléfono de prueba y webhook público).

### Evidencia (real, ejecutada)

| Verificación | Resultado |
|---|---|
| `python scripts/db_migrate.py` | `+ 073_facturas_internas.sql` |
| `python scripts/factura_prueba.py` | Factura `PRUEBA-0001` creada; total **$43.424,00** |
| Segunda ejecución | `[OK] ya existe...` (idempotente) |
| `GET /api/v1/media/{id}/archivo` | `200 application/pdf 132932` |
| `GET /api/v1/clients/{id}/facturas` | 1 factura con `es_ficticia=true` y URL |
| Gato determinista | `OK` con PRUEBA-0001 + FICTICIA; SRI -> `PROPUESTA` |
| Gato DeepSeek | `OK`, tabla con subtotal/IVA/total y advertencia de ficticia |
| Gato con Bodega | Rechazo por rol (sin datos) |
| Panel | Pestaña Facturas visible, 0 errores de consola |
| `pytest /app/tests -q` | **338 passed** en 15.21 s |
| `python scripts/auditar_skills.py` | **APROBADO (177 verificaciones)** |

Evidencia completa: `.agents/evidencias/facturas_v613_2026-11-12.txt`,
`.agents/evidencias/factura_prueba_2026-11-12.pdf`,
`.agents/evidencias/panel_v613_facturas_2026-11-12.jpeg`.

### Decisiones tomadas

1. **Factura interna, no SRI.** Se guarda el documento y sus montos, pero no se
   emite comprobante electrónico: el SRI sigue fuera de alcance (decisión C4).
2. **Los montos salen de la orden.** Si se elige una orden, el backend copia
   subtotal, IVA y total; si no, el usuario debe escribir el total. Cero
   valores inventados.
3. **`es_ficticia` es explícito.** La factura de prueba se marca en base, en el
   PDF, en el panel y en la respuesta de Gato.
4. **Se reutiliza `media_assets`.** El binario vive en Bunny/sandbox; PostgreSQL
   solo guarda el índice y la relación con la factura.

### Bloqueos / preguntas al cliente

1. Validar con Julio el **formato real** de la factura (logo, datos fiscales,
   numeración, autorización) antes de usarla con clientes.
2. Confirmar si la numeración será por cliente o global; hoy es única por
   cliente para la prueba.
3. Para Evolution API faltan las credenciales y el webhook público descritos en
   `docs/EVOLUTION_API_PRUEBA.md`.

### Próximo paso exacto

Revisar con Julio el PDF de prueba y definir los datos fiscales/numeración de la
factura interna. Después, cargar las credenciales de Evolution API y correr la
prueba de texto con un teléfono real.

### Archivos tocados

- `db/migrations/073_facturas_internas.sql`
- `services/core-api/app/services/factura_pdf.py`
- `services/core-api/app/routers/facturas.py`
- `services/core-api/app/main.py`
- `services/core-api/app/m3_secretaria/service.py`
- `services/core-api/app/asistente/` (`catalogo.py`, `pilares.py`, `herramientas.py`, `bibliotecario.py`, `redactor.py`, `orquestador.py`, `proveedores.py`, `persona.py`)
- `services/core-api/app/web/templates/panel.html`
- `services/core-api/tests/test_gato.py`, `tests/test_factura_pdf.py`
- `scripts/factura_prueba.py`
- `docs/GATO_CORPUS.md`, `docs/GATO_PROMPT.md`, `docs/BASE_DE_DATOS.md`, `docs/MODELO_DATOS.md`, `docs/EVOLUTION_API_PRUEBA.md`
- `.agents/evidencias/facturas_v613_2026-11-12.txt`, `factura_prueba_2026-11-12.pdf`, `panel_v613_facturas_2026-11-12.jpeg`
- `.agents/ESTADO.md` y `.agents/BITACORA.md`

---

## 2026-11-12 - Gato v6.13.1: memoria, búsqueda y descarga

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** que Gato siga el hilo de la conversación ("descárgala"), encuentre
"ing reyes" aunque el nombre real tenga punto, y entregue la factura como
descarga desde el chat.

### Hecho

1. **Búsqueda normalizada.** `bibliotecario._norm_busqueda()` quita tildes y
   puntuación, y la consulta normaliza nombre, constructora, ciudad, obra, RUC,
   cédula y teléfono. "ing reyes" ahora encuentra "Ing. Reyes (prueba Hito 1)".
2. **Memoria en PostgreSQL.** Migración `074_gato_memoria.sql` crea
   `gato_turnos`; el endpoint devuelve `conversacion_id`, el widget lo guarda
   por usuario en `localStorage` y el backend pasa los últimos 8 turnos al LLM.
   Si el ID es de otro actor, responde 403.
3. **Conversación fluida.** Con el mismo `conversacion_id`, "descárgala"
   devuelve el PDF de la factura anterior sin repetir el cliente. El prompt
   agrega reglas de historial, ambigüedad ("¿a cuál?") y enlaces de descarga.
4. **Descarga desde el chat.** El backend garantiza
   `Descargar: /api/v1/media/{id}/archivo?download=1`; el widget lo convierte
   en enlace con atributo `download`. Se agregó el botón "↺" para iniciar una
   conversación nueva.
5. **Límite de memoria.** 8 turnos por conversación; se guardan pregunta,
   respuesta, estado, actor y rol. No se guardan secretos.

### Evidencia (real, ejecutada)

| Verificación | Resultado |
|---|---|
| `db_migrate.py` | `+ 074_gato_memoria.sql` |
| "Pásame la factura del ing reyes" | `OK`, encuentra al cliente y la factura |
| "descárgala" con el mismo `conversacion_id` | `OK`, devuelve el PDF anterior |
| `gato_turnos` | 2 turnos con el mismo `conversacion_id` |
| Enlace de descarga | `/api/v1/media/.../archivo?download=1` |
| `pytest /app/tests -q` | **342 passed** en 9.27 s |

Evidencia completa:
`.agents/evidencias/gato_memoria_v6131_2026-11-12.txt`.

### Decisiones tomadas

1. **Memoria en PostgreSQL, no en el navegador.** El historial queda auditables
   y el widget solo guarda el `conversacion_id`.
2. **Ocho turnos, no toda la conversación.** Mantiene el prompt corto y
   suficiente para referencias inmediatas; una conversación larga se puede
   resumir después.
3. **La búsqueda normaliza, no adivina.** "ing reyes" encuentra "Ing. Reyes";
   si hay varios, Gato muestra los nombres y pregunta. No elige por su cuenta.
4. **La descarga se garantiza en el backend.** Aunque el LLM omita el enlace,
   el post-proceso agrega la URL exacta de la ficha; no se inventan enlaces.

### Bloqueos / preguntas al cliente

1. Probar el hilo con Julio y Secretaría durante una conversación real.
2. Definir si la memoria debe durar días o solo la sesión; hoy queda en base.
3. La factura real sigue pendiente de formato, numeración y datos fiscales.

### Próximo paso exacto

Probar en el panel: "Pásame la factura del ing reyes" y luego "descárgala" con
el mismo usuario; verificar que el PDF se descarga y que el botón "↺" inicia
una conversación limpia.

### Archivos tocados

- `db/migrations/074_gato_memoria.sql`
- `services/core-api/app/asistente/memoria.py`
- `services/core-api/app/asistente/router.py`
- `services/core-api/app/asistente/gato.py`
- `services/core-api/app/asistente/orquestador.py`
- `services/core-api/app/asistente/proveedores.py`
- `services/core-api/app/asistente/bibliotecario.py`
- `services/core-api/app/asistente/redactor.py`
- `services/core-api/app/asistente/persona.py`
- `services/core-api/app/web/templates/panel.html`
- `services/core-api/tests/test_gato.py`, `tests/test_asistente_router.py`
- `docs/GATO_PROMPT.md`, `docs/GATO_CORPUS.md`, `docs/BASE_DE_DATOS.md`
- `.agents/evidencias/gato_memoria_v6131_2026-11-12.txt`
- `.agents/ESTADO.md` y `.agents/BITACORA.md`

---

## 2026-11-12 - Primera subida al VPS, deploy key y Evolution

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** subir Horminor al VPS de Contabo usando GitHub y una deploy key
nueva; dejar Evolution API conectado; proteger secretos y no exponer el panel
sin login.

### Hecho

1. **`.gitignore` y `.dockerignore` endurecidos:** `.env*`, `vps-entrada/`,
   `secrets/`, `backups/`, `*.pem`, `*.key`, `*_vps`, `*_deploy`, `*.dump` y
   `*.sql.gz` quedan fuera del repo y del contexto de build.
2. **Llaves nuevas:** `vps-entrada/horminor_vps` (acceso SSH al VPS) y
   `vps-entrada/horminor_github_deploy` (deploy key). La pública del VPS se
   agregó a `authorized_keys`; la de GitHub se registró como deploy key
   **read-only** (id `169704454`).
3. **GitHub:** remoto cambiado a `ObjetivoCesar/horminor-crm`; commit
   `a94a618` en `main`. El repo estaba vacío (`size=0`) y es público.
4. **VPS:** clon en `/opt/horminor` con deploy key; `.env` en `600` con
   secretos nuevos (`POSTGRES_PASSWORD`, `AGENCY_MASTER_KEY`,
   `SENTINEL_MASTER_KEY`, tokens del Custodio y `GATE_API_KEY`).
5. **Compose VPS:** `docker-compose.vps.yml` deja PostgreSQL y Redis sin
   puertos publicados y publica `core-api` solo en `127.0.0.1:8012`. El primer
   intento usó 8010 y quedó público; se corrigió con `!override`.
6. **Caddy:** bloque `horminor.178.238.238.158.sslip.io`; solo `/health` y
   `/api/v1/whatsapp/webhook` son públicos. El panel responde `403` desde
   Internet y `200` por túnel SSH. Respaldo del Caddyfile en
   `Caddyfile.bak.2026-11-12-horminor`.
7. **Evolution:** instancia `horminor` creada (`connecting`), webhook
   `https://horminor.178.238.238.158.sslip.io/api/v1/whatsapp/webhook` con
   `MESSAGES_UPSERT`, `CONNECTION_UPDATE` y `QRCODE_UPDATED`. La instancia se
   activó en `system_settings` (`sandbox=false`), `whatsapp/health` ya reporta
   `notifier: evolution`.
8. **QR:** guardado en `vps-entrada/horminor_qr.png` (privado) y mostrado para
   escanear. Si expira, se regenera con `GET /instance/connect/horminor`.

### Evidencia (real, ejecutada)

| Verificación | Resultado |
|---|---|
| `git push` a `ObjetivoCesar/horminor-crm` | `85bc97b..a94a618 main -> main` |
| Deploy key | `Hi ObjetivoCesar/horminor-crm! You've successfully authenticated` |
| VPS `/opt/horminor` | clone OK, 21 migraciones aplicadas |
| `docker compose ps` | postgres/redis healthy, core-api healthy |
| `curl http://127.0.0.1:8012/health` | `200 {"status":"ok","db":"ok"}` |
| `https://horminor.../health` | `200` |
| `https://horminor.../panel` | `403` (privado) |
| `http://127.0.0.1:8012/panel` | `200` (túnel) |
| `whatsapp/health` | `notifier: evolution` |
| Instancia Evolution | `horminor`, estado `connecting` |
| Webhook | URL y 3 eventos configurados |

Evidencia completa:
`.agents/evidencias/vps_deploy_evolution_2026-11-12.txt`.

### Decisiones tomadas

1. **Deploy key read-only.** El VPS solo necesita leer; el push se hace desde
   local con la credencial de GitHub. Menos privilegio en el servidor.
2. **Panel por túnel SSH.** Sin login no se publica el panel ni las rutas de
   Secretaría/Superadmin. Caddy solo abre `/health` y el webhook.
3. **SSH key separada por proyecto.** No se reutiliza la llave de Agenda
   Turística; se generó una para Horminor.
4. **Secretos nuevos en el VPS.** No se copiaron las claves de desarrollo;
   solo se reutilizaron las de Evolution y DeepSeek.
5. **`sslip.io` como host temporal.** Da TLS sin comprar dominio; cuando
   exista dominio propio solo se cambia el bloque de Caddy.

### Bloqueos / preguntas al cliente

1. **Escanear el QR** de Evolution `horminor` desde WhatsApp > Dispositivos
   vinculados.
2. Entregar un **teléfono de prueba** para enviar el primer texto real.
3. **Rotar la API key de Evolution** que se compartió por chat.
4. Definir el dominio propio (opcional) y el correo para TLS.

### Próximo paso exacto

Escanear el QR, confirmar que la instancia pasa a `open`, enviar un texto desde
el panel (por túnel SSH) a un teléfono de prueba y revisar el webhook. Después,
rotar la API key y cargar el backup diario.

### Archivos tocados

- `.gitignore`, `.dockerignore`
- `docker-compose.vps.yml`
- `scripts/activar_evolution.py`
- `docs/DESPLIEGUE_VPS_HORMINOR.md`, `docs/EVOLUTION_API_PRUEBA.md`
- `.agents/ESTADO.md` y `.agents/BITACORA.md`
- Fuera del repo: `vps-entrada/horminor_vps`, `horminor_github_deploy`,
  `horminor.env`, `horminor_qr.png`, `horminor.caddy`

---

## 2026-11-12 - Gato secretaria: recordatorios programados por WhatsApp

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Objetivo:** confirmar si Gato puede actuar como secretaria y agregar la
creación de tareas con hora para que envíe un recordatorio por WhatsApp, en
local y verificable.

### Hecho

1. **Migración 075 (`gato_recordatorios`).** Una fila es una tarea: creador,
   cliente, teléfono, mensaje, `programado_at` (UTC), zona, estado, intentos y
   error. Índice parcial para los pendientes.
2. **`asistente/recordatorios.py`.** Interpreta la frase ("a las 18:40",
   "mañana a las 9", "en 30 minutos", ISO del LLM), resuelve el destino en
   `clients` y expone `crear`, `listar`, `cancelar` y `ejecutar`.
3. **`asistente/despachador.py`.** El "cron" es una tarea `asyncio` dentro de la
   API (cada 20 s), que reclama con `FOR UPDATE SKIP LOCKED` y envía por el
   notificador del Módulo 1. Se arranca en el `lifespan` de `main.py`.
4. **Herramientas de Gato.** Nuevo pilar `recordatorios` con
   `recordatorio_crear`, `recordatorio_listar` y `recordatorio_cancelar`,
   disponibles para SUPERADMIN y SECRETARIA; declaradas en `proveedores.py`
   para el tool calling de DeepSeek y en `orquestador.py` para el modo
   determinista.
5. **HTTP.** `GET/POST /api/v1/asistente/recordatorios` y
   `POST /api/v1/asistente/recordatorios/{id}/cancelar`, con el rol resuelto en
   el backend.
6. **Prompt.** Reglas nuevas: no inventar teléfono, copiar el mensaje literal,
   decir "programado" y no "enviado".
7. **Doc.** `docs/GATO_RECORDATORIOS.md` con el mapa de piezas y los pendientes.

### Evidencia (real, ejecutada)

| Verificación | Resultado |
|---|---|
| `pytest /app/tests -q` | **357 passed** (342 + 15 nuevos) |
| Log de arranque | `despachador de recordatorios activo (cada 20s)` |
| Ing. Reyes (sin teléfono) | Gato **no crea** la tarea y pide el número |
| Cliente con teléfono | fila `PENDIENTE` a las 18:42 |
| Tick del despachador | `ENVIADO`, `intentos=1`, `enviado_at 18:42:20` |
| `sandbox_outbox` | id 19, destino `0990000013`, mensaje exacto |
| `GET /recordatorios` | devuelve la fila con `programado_local 12/11/2026 18:42` |

Evidencia completa: `.agents/evidencias/gato_recordatorios_2026-11-12.txt`.

### Decisiones tomadas

1. **Tarea de fondo, no cron del sistema.** El PDR no trae Celery y el
   despliegue es un contenedor; `FOR UPDATE SKIP LOCKED` evita duplicados si
   algún día hay dos réplicas. Alternativa descartada: cron del host con
   `docker exec`, que rompe la portabilidad y no conoce el estado de la API.
2. **El teléfono sale del CRM, nunca del modelo.** Si el cliente no tiene
   número, no se crea la tarea. Alternativa descartada: aceptar cualquier número
   dictado sin registro, que abre la puerta a enviar datos a terceros.
3. **Una sola vez, no recurrente.** La repetición ("todos los lunes") queda
   como propuesta para no inventar semántica de recurrencia.
4. **Estados con reintento acotado.** Tres intentos y `FALLIDO` con el error;
   sin canal, la fila vuelve a `PENDIENTE` sin gastar intento.

### Bloqueos / preguntas al cliente

1. **Código de país.** `clients.telefono_whatsapp` guarda números locales
   (`0990000013`) y Evolution espera `593990000013`. Hoy el recordatorio usa el
   número tal cual, igual que el aviso de salida de mixer. Decidir si se
   normaliza en el CRM o al enviar.
2. **UI.** Falta la lista de recordatorios en el panel (la API ya existe).
3. **Alcance.** ¿Gato puede escribir a un cliente sin que Julio/Secretaría
   confirme, o el recordatorio debe quedar en revisión antes de enviarse?

### Próximo paso exacto

Probar en `/panel` la frase "Gato escríbele al Cliente Prueba Hito 3 a las
18:45 y recuérdale que tiene una cita en las oficinas de Horminor", ver el
mensaje en el outbox del Superadmin y luego decidir el punto 1 (código de país).

### Archivos tocados

- `db/migrations/075_gato_recordatorios.sql`
- `services/core-api/app/asistente/recordatorios.py`
- `services/core-api/app/asistente/despachador.py`
- `services/core-api/app/asistente/herramientas.py`
- `services/core-api/app/asistente/orquestador.py`
- `services/core-api/app/asistente/pilares.py`
- `services/core-api/app/asistente/proveedores.py`
- `services/core-api/app/asistente/redactor.py`
- `services/core-api/app/asistente/persona.py`
- `services/core-api/app/asistente/router.py`
- `services/core-api/app/main.py`
- `services/core-api/tests/test_recordatorios.py`
- `docs/GATO_RECORDATORIOS.md`
- `.agents/evidencias/gato_recordatorios_2026-11-12.txt`

### Addendum (misma sesión) — normalización de teléfonos y documento del sistema

**Hecho.**

1. **`formato_whatsapp()` en `m1_whatsapp/models.py`.** Deja el número como lo
   espera Evolution: `0990000013`, `990000013`, `593990000013`,
   `+593 99 000 0013` y `00593990000013` producen `593990000013`; un formato
   desconocido se devuelve tal cual (no inventa país). No se tocó
   `normalizar_telefono()`, que sigue sirviendo para comparar identidad.
2. **Tres capas de normalización:** al crear el recordatorio, al despachar
   (cubre filas viejas) y en `EvolutionNotifier.enviar_texto` (cubre también los
   avisos de salida de mixer).
3. **`docs/GATO_SECRETARIA.md`** v1.0.0: arquitectura, flujo de 12 pasos,
   modelo de datos, máquina de estados, reglas de hora, permisos, despachador,
   teléfonos, canales, API, prompt, observabilidad, pruebas, operación,
   pendientes P0/P1/P2, decisiones descartadas, riesgos y **paquete de trabajo
   para Carbon**. `docs/GATO_RECORDATORIOS.md` queda como puntero.

**Evidencia.**

| Verificación | Resultado |
|---|---|
| `pytest /app/tests -q` | **365 passed** (357 + 8 de `formato_whatsapp`) |
| Recordatorio con `0990000013` | fila guardada como `593990000013` |
| `sandbox_outbox` | id 20, destino `593990000013`, 19:00:10 |

**Decisión.** Se normaliza en el notificador además de en el alta: el número
local en el CRM es un dato de entrada, no un error, y así cualquier llamador
(trips incluidos) queda cubierto. Alternativa descartada: normalizar solo al
crear, que dejaba los avisos de mixer con el mismo defecto.

**Próximo paso exacto.** Revisar `docs/GATO_SECRETARIA.md` §15 y decidir P0-2
(¿aprobación previa obligatoria?) antes de desplegar al VPS.

### Addendum 2 (misma sesión) — auditoría adversarial y documento v1.1

**Objetivo.** Atacar la implementación antes de llamarla terminada. El
documento 1.0 afirmaba cosas que el código no cumplía.

**Fallos demostrados (salida real, no teoría).**

| # | Fallo | Salida |
|---|---|---|
| B1 | "a las 7 de la mañana" | programa **mañana 19:00** |
| B1b | Dos horas en una frase | toma la primera (18:40) y no la del recordatorio (17:00) |
| B2 | Cancelar en `ENVIANDO` | devuelve 404 y el mensaje sale |
| B3 | Caída tras enviar | la recuperación de 5 min reenvía |
| B4 | `conversacion_id` / `creado_por` | NULL y `"panel"` en 2/2 filas |
| B5 | Doble clic | no hay idempotencia: 2 filas |
| B6 | "programa de mantenimiento" | pide destinatario (falso positivo) |
| B7 | `021234567` | `593021234567` (fijo mal normalizado) |
| B8 | `ENVIADO` | 2xx de Evolution, no entrega |

**Hecho.**

1. `docs/GATO_SECRETARIA.md` **v1.1**: separa garantías de promesas, documenta
   B1–B8 con salida, redefine el tope diario como valor configurable
   (`gato.limite_envios_dia`, default NULL = PENDIENTE, no se inventa la cifra),
   decide el parser determinista (solo formatos inequívocos), mantiene el número
   dictado **marcado** como `origen_destino=DICTADO` y reescribe el paquete de
   Carbon como C1–C7.
2. Estado real declarado: **prototipo verificado en local**, no desplegado; la
   tabla no existe en el VPS (verificado: `count = 0`).

**Decisión.** El número dictado se conserva: es un caso operativo real ("el
dueño pidió que llamen al maestro"). Se resuelve con trazabilidad, no
prohibiéndolo. Alternativa descartada: exigir siempre cliente registrado, que
frena la operación.

**Próximo paso exacto.** Ejecutar C1 (confirmación) y C2 (tope diario) con el
paquete de Carbon; no desplegar antes.

### Addendum 3 (misma sesión) — v6.15: ratificación implementada

**Decisiones de Dirección (2026-11-12).**

1. **Ratificación obligatoria:** sí, Gato debe pedir confirmación.
2. **El chat es interno:** solo Julio y Secretaría lo usan; el cliente solo
   recibe notificaciones. Por eso **se descarta el tope diario** como control
   anti-abuso (queda anotado para si algún día el acceso se abre).
3. **Hora con IA:** el modelo interpreta el lenguaje natural; el backend calcula
   la hora en Ecuador.
4. **Trazabilidad:** guardar siempre quién y en qué conversación.

**Hecho.**

1. **Migración 076:** estado `BORRADOR`, `origen_destino` (`CRM`/`DICTADO`),
   `confirmado_por`, `confirmado_at`, `clave_idempotencia` única.
2. **`recordatorios.py`:** crear nace en BORRADOR y devuelve la lectura de
   vuelta; `confirmar`, `descartar`, `pendiente_de`; el "sí"/"no" se resuelve
   en el router, sin depender del LLM.
3. **Parser corregido:** "a las 7 de la mañana" → 07:00; dos horas → la última;
   fijos `021234567` → `59321234567`.
4. **Hora sin ambigüedad:** el LLM pasa la frase, no un ISO; `render_prompt`
   muestra hora local. Se corrigió un envío 5 h corrido detectado en la prueba.
5. **Trazabilidad real:** `conversacion_id`, `creado_por` y `confirmado_por`
   poblados; `gato._actor` ya no descarta el actor de la sesión.
6. **Carrera de cancelación:** el despachador relee `estado` antes de enviar.
7. **Bug de SQL:** `ON CONFLICT` contra índice parcial necesita el predicado
   `WHERE clave_idempotencia IS NOT NULL`; sin eso toda creación fallaba y caía
   al modo determinista.
8. **Doc v1.2** con el flujo nuevo y el paquete de Carbon renumerado (C8–C12).

**Evidencia.**

| Verificación | Resultado |
|---|---|
| `pytest /app/tests -q` | **372 passed** |
| Crear con "en 3 minutos" (19:37) | BORRADOR a las **19:40**, hora correcta |
| "sí" | `PENDIENTE`, `confirmado_por=julio` |
| Tick | `ENVIADO` 19:40:37, outbox 22 |
| "no" | `CANCELADO`, sin outbox |
| Número dictado | `origen_destino=DICTADO`, `593990000014`, aviso |
| Doble intención de hora | la última (17:00, no 18:40) |

Evidencia completa: `.agents/evidencias/gato_ratificacion_2026-11-12.txt`.

**Bloqueos abiertos.** Número inexistente en WhatsApp (C8), UI en el panel (C9),
documento por WhatsApp (C10), acuse de entrega (C11), test de integración con
base real (C12) y **despliegue al VPS** (la 075/076 no están aplicadas allá).

**Próximo paso exacto.** Probar en `/panel` el flujo "prepara → sí" con el perfil
de Secretaría y, si responde bien, desplegar 075/076 al VPS antes de usar un
número real.

### Addendum 4 (misma sesión) — v6.16: adjuntos, "ahora mismo" y ratificación tardía

**Origen.** Prueba real de Julio: "revisa si el Ing Reyes nos envió el pago",
luego "notifícale al 0967491847... pásale la factura", "ahora mismo", "19:50".
El mensaje nunca salió.

**Diagnóstico (con base, no suposición).** La fila `98d4e995` quedó en
`BORRADOR` sin `confirmado_por`: faltó el "sí". Además, `confirmar` rechazaba
cuando la hora ya había pasado, así que la ratificación tardía era un callejón
sin salida. Y "pásale la factura" viajaba como texto: no existía envío de
documentos.

**Hecho.**

1. `parsear_cuando` acepta "ahora mismo", "ya", "de una", "en este momento".
2. `confirmar` reprograma con `GREATEST(programado_at, now())`: ya no rechaza.
3. Mensaje: verbos ampliados (`notifícale`, `pásale`, `pídele`, ...).
4. Adjuntos: migración 077 (`media_id`), `enviar_documento()` en los tres
   notificadores, despachador que carga el archivo del sandbox o del CDN.
5. Migración 078: el outbox admite `DOCUMENTO` (el primer intento falló con
   `CheckViolationError`; el reintento funcionó).
6. `adjuntar_factura` y `factura_de` en la herramienta; aviso si es ficticia.

**Evidencia.**

| Verificación | Resultado |
|---|---|
| Confirmar 4 min tarde | `ENVIADO`, outbox 23 (texto) |
| "ahora mismo" + número dictado + factura | `BORRADOR` con `origen=DICTADO` y adjunto PRUEBA-0001 |
| "sí" | `ENVIADO` en el tick, outbox 25 |
| Outbox 25 | `DOCUMENTO`, `application/pdf`, 132.932 bytes |
| `pytest` | **374 passed** |

Evidencia completa: `.agents/evidencias/gato_adjuntos_2026-11-12.txt`.

**Decisión.** El texto dictado no se reescribe aunque el adjunto lo haga
redundante ("pásale la factura" + PDF). Se respeta la literalidad; el aviso de
que va adjunta se agrega en la ratificación, no en el mensaje.

**Pendiente.** Desplegar 075–078 al VPS; número vivo (C8); UI (C9); acuse (C11);
test de integración (C12).

### Addendum 5 (misma sesión) — despliegue al VPS y envío real

**Hecho.**

1. **Commit `7850241`** (Gato recordatorios) y **`85e1168`** (fix), subidos a
   `ObjetivoCesar/horminor-crm`; el VPS hizo `git pull`.
2. **Migraciones 075–078 aplicadas** al reiniciar la API (01:13:49). Tabla
   `gato_recordatorios` con 21 columnas; despachador activo.
3. **Tres clientes ficticios** (`PRUEBA`) con teléfono y factura propia
   (`PRUEBA-0002/3/4`), marcados `es_ficticia=true` y con nota de ficticio.
4. **Envío real verificado.** Borrador al 0967491847 con la factura PRUEBA-0002;
   "sí" → `ENVIADO` a las 20:19:55; Evolution registra
   `documentMessage · PRUEBA-0002.pdf`.
5. **Dos bugs del VPS corregidos:** faltaba `import base64` en
   `notifications.py` (todo envío de documento fallaba) y `modo` reportaba
   `SANDBOX` por Bunny, aunque el notificador fuera Evolution. Se agregó
   `envio` al health y el aviso usa ese campo.

**Evidencia.** `.agents/evidencias/vps_despliegue_recordatorios_2026-11-12.txt`.

**Lección.** El camino de documentos nunca se ejecutó en local porque SANDBOX no
usa `base64`; el primer envío real lo destapó. De aquí en adelante, cualquier
cambio del notificador se prueba al menos una vez con Evolution.

**Próximo paso exacto.** Confirmar en el teléfono 0967491847 que llegó
`PRUEBA-0002.pdf`; luego definir la UI (C9) y el acuse de entrega (C11).

### Addendum 6 (misma sesión) — Gato redacta el mensaje

**Motivo.** Julio probó el flujo: funcionó, pero pidió dictar cada texto. Su
frase: *"solo lo de redactar el mensaje está feísimo... para eso le envío yo
mismo"*. La regla "el mensaje es del usuario" convertía a Gato en un formulario.

**Decisión.** Gato redacta; el candado pasa de "no redactar" a "no inventar
cifras".

1. **Prompt:** puede redactar breve, en nombre de Horminor, sin promesas ni
   enlaces de pago. Solo cifras que estén en las fichas.
2. **Código:** `recordatorios.cifras_de()` + `_cifras_permitidas()` extraen los
   montos del mensaje y los comparan con `v_cliente_saldo` y `client_invoices`.
   Si sobra uno, no se crea el borrador.
3. **No interrogar:** si el cliente está en el CRM, no se pide el número; el
   backend lo resuelve.

**Evidencia.**

| Prueba | Resultado |
|---|---|
| "pásale al Ing. Reyes su factura y su saldo" (VPS) | borrador con mensaje redactado, sin pedir texto |
| Mensaje redactado | menciona USD 43.424,00 y USD 0,00, ambos en la ficha |
| Cifra inventada (99.999,99) | `ERROR`, sin fila creada |
| `pytest` | **376 passed** |

**Pendiente.** El mensaje de la API para `ERROR` responde 200 con `estado=ERROR`;
conviene devolver 422 en una próxima pasada. C9 (UI) y C11 (acuse) siguen
abiertos.

---

## 2026-11-13 — Cierre: Gato secretaria (ratificación, adjuntos y redacción)

**Agente:** OpenCode (DeepSeek V4.1 Flash)
**Duración:** sesión larga, continuación del 2026-11-12
**Objetivo:** convertir a Gato en una secretaria real: crear recordatorios por
WhatsApp con ratificación, adjuntar facturas y enviarlos desde el VPS.

### Hecho

1. **Migraciones 075–078** (recordatorios, ratificación, adjunto, `DOCUMENTO` en
   el outbox), aplicadas en local y en el VPS.
2. **Ratificación en dos pasos:** `BORRADOR → "sí" → PENDIENTE → ENVIADO`;
   "no" cancela. El "sí/no" se resuelve en el router, sin depender del LLM.
3. **Despachador** interno cada 20 s con `FOR UPDATE SKIP LOCKED`, reintentos y
   relectura de estado antes de enviar.
4. **Adjuntos reales:** `enviar_documento()` en Evolution y SANDBOX; el PDF sale
   de `media_assets` (sandbox o CDN).
5. **Teléfonos:** `formato_whatsapp()` normaliza `0990000013`, `990000013`,
   `+593…` y `00593…` a `593990000013`; fijos corregidos.
6. **Hora:** "de la mañana/tarde" y "ahora mismo"; la última hora de la frase
   manda; la IA pasa la frase, no un ISO.
7. **Redacción propia:** Gato escribe el mensaje breve; el backend rechaza
   cualquier cifra que no exista en la ficha (`cifras_de`/`_cifras_permitidas`).
8. **Trazabilidad:** `conversacion_id`, `creado_por`, `confirmado_por`;
   `origen_destino` distingue CRM de número dictado; clave de idempotencia.
9. **VPS:** despliegue con `docker compose -f docker-compose.yml -f
   docker-compose.vps.yml`, 4 clientes ficticios con su PDF, envíos reales.
10. **Documento del sistema:** `docs/GATO_SECRETARIA.md` v1.3 con el paquete
    C8–C12.

### Evidencia (real, ejecutada)

| Verificación | Resultado |
|---|---|
| `pytest /app/tests -q` | **376 passed** |
| Migraciones en VPS | 075, 076, 077, 078 aplicadas 01:13:49 |
| Envío de texto (local) | outbox 19/20/21/22/23 |
| Envío de PDF (VPS) | `documentMessage · PRUEBA-0002.pdf` al 0967491847 |
| Envío redactado (VPS) | mensaje propio con saldo verificado, `ENVIADO` |
| Candado de cifras | `99.999,99` rechazado, sin fila |
| Normalización | 5 formatos → `593990000013` |

### Decisiones tomadas

1. **Ratificar antes de enviar.** Un error de lectura no llega al cliente.
   Alternativa descartada: enviar directo y avisar después.
2. **La IA pasa la frase, no la fecha.** El modelo mezclaba UTC y local (5 h de
   error). Alternativa descartada: ISO en el modelo.
3. **Gato redacta, el código verifica las cifras.** Alternativa descartada:
   obligar a dictar el texto, que convertía a Gato en un formulario.
4. **Número dictado permitido y marcado.** Es un caso operativo real.
   Alternativa descartada: exigir siempre cliente registrado.
5. **Sin tope diario.** El canal de creación es interno (Julio y Secretaría).
6. **`ENVIADO` = aceptado por Evolution**, no entregado.

### Bloqueos / preguntas al cliente

1. **Datos ficticios en el VPS:** cuatro clientes `(PRUEBA)` con facturas de
   prueba. Julio debe decidir cuándo se limpian y se cargan los reales.
2. **Aprobación previa:** hoy cualquier SUPERADMIN/SECRETARIA ratifica y envía.
   ¿Se exige un segundo visto bueno?
3. **Consentimiento de mensajes** (LOPDP): no hay registro de opt-in.
4. **Acuse de entrega:** pendiente (C11).

### Próximo paso exacto

Implementar **C9** (pestaña de recordatorios en `/panel` con Ratificar,
Descartar y Cancelar) y **C8** (validar el número en WhatsApp antes de crear).
Criterio: crear un recordatorio desde la pestaña y verlo llegar al 0967491847
con `envio: evolution`.

### Archivos tocados

- `db/migrations/075_gato_recordatorios.sql`, `076_gato_ratificacion.sql`,
  `077_gato_adjuntos.sql`, `078_outbox_documento.sql`
- `services/core-api/app/asistente/recordatorios.py`, `despachador.py`,
  `herramientas.py`, `orquestador.py`, `pilares.py`, `proveedores.py`,
  `redactor.py`, `persona.py`, `router.py`, `gato.py`
- `services/core-api/app/main.py`, `app/sandbox.py`,
  `app/m1_whatsapp/{models,notifications,runtime,__init__}.py`
- `services/core-api/tests/test_recordatorios.py`, `test_m1_whatsapp.py`,
  `test_asistente_router.py`
- `docs/GATO_SECRETARIA.md`, `docs/GATO_RECORDATORIOS.md`
- `.agents/ESTADO.md`, `.agents/BITACORA.md`
- Evidencias: `gato_recordatorios_2026-11-12.txt`,
  `gato_ratificacion_2026-11-12.txt`, `gato_adjuntos_2026-11-12.txt`,
  `vps_despliegue_recordatorios_2026-11-12.txt`
