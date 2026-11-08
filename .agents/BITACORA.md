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

