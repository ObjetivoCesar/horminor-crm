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

