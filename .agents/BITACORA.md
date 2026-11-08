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
