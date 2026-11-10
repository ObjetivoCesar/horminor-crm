# ESTADO DEL PROYECTO

> Foto del presente. Se reescribe en cada sesión. La historia está en `BITACORA.md`.
> Última actualización: **2026-11-09** (Hito **Custodio + Panel de
> Pagos/Gastos/Tasas/Conteo** cerrado: Custodio v4.4.0 con HTTP, panel de
> cobros/abonos/gastos, Superadmin de tasas y conteo, y backup diario.
> 14 migraciones, 29 tablas, 6 vistas, 27 cuentas; **265 tests** y los 2
> candados en verde. Quedan operativos: cargar tasas, ejecutar el conteo real
> e instalar el cron de backups.
> Se sum� la operaci�n v6.0: compras de material, tope de caja chica,
> cierre con compras y agenda real de entregas/mixers. El login de usuario pasa al **backlog
> exclusivo pre-VPS**.)

## Hitos

| Hito | Módulo | Estado | Evidencia | Qué falta para cerrar |
|---|---|---|---|---|
| 1 | M0 — Datos y configuración | 🟢 **Cerrado** con semilla oficial | `evidencias/hito1_lock_2026-11-08.txt`: `[CANDADO CERRADO]`, 235 movimientos de kardex, órdenes valoradas ($37.760 y $8.216) | Nada bloqueante. Re-verificar si se editan recetas |
| — | Superadmin — Configuración en caliente | 🟢 Construido y editable desde el panel | 7 secciones, CRUD de recetas/flota, simulador de WhatsApp y outbox | Autenticación antes de exponerlo a Internet |
| 2 | M2 — Motor determinístico | 🟡 Construido, verificado local | `evidencias/pytest_panel_v44_2026-11-09.txt`: **247 tests** + candado Hito 1 | Probar desde el CRM de la agencia en el VPS |
| 2 | M5 — Nodo Centinela | 🟡 Construido, verificado local | `evidencias/hito3_4_live_2026-11-08.txt`: 12 checks, `modo=SANDBOX`, `judge_mode=DETERMINISTIC_FALLBACK`; Evolution/Bunny en OK | Webhook real del CRM; umbral de merma que defina Julio |
| 3 | M1 — WhatsApp (Evolution + Jeb + Bunny) | 🟢 **Cerrado en SANDBOX** | `evidencias/hito3_lock_2026-11-08.txt`: `[CANDADO CERRADO EN SANDBOX]`; 4 compuertas, JSONB y outbox | Producción real: cargar credenciales, apagar SANDBOX y repetir el candado |
| 4 | M3 — Ventanilla de Secretaría + Caja | 🟢 **Cerrado** y verificado local | `/panel` (tab Secretaría) con formularios de cobro/abono y gasto; carpeta forense; `POST /api/v1/panel/pagos` probado; tests `test_m3_secretaria.py` | Validación con la secretaria real (afinamiento, no bloqueante) |
| 4b | Custodio v4.4 + Panel de Pagos/Gastos/Tasas/Conteo | 🟢 **Cerrado** (2026-11-09) | `evidencias/pytest_panel_v44_2026-11-09.txt` (**247 tests**); `evidencias/http_gate_v44_check_2026-11-09.txt` (`HTTP GATE V4.4: OK`, 12 pasos, `ROLLBACK` 17 tablas); `/panel` con `dlg-pago`, `dlg-gasto`, `conteo-materiales`, `fin-wacc`; `GET /api/v1/panel/catalog` → 26 cuentas | Nada bloqueante. Cargar tasas, ejecutar conteo real e instalar cron quedan como operación del cliente/VPS |
| 4c | v6.0 - Compras, caja chica y agenda | OK **Cerrado** (2026-11-09) | 067 aplicada; panel con compras/cierre/agenda; recepcion en Planta; `evidencias/pytest_v6_2026-11-09.txt` (**265 tests**); `evidencias/clone_v6_2026-11-09.txt` | Confirmar tope y proveedores reales |
| 5 | M4 — Dashboard de Julio + Ases | 🟢 Construido y verificado local | *Dashboard Julio* con 3 tarjetas iguales: mercado El Coca **0.31% (372/120,000 m³)**, ventas **404 m³ / $55,043.60 / 51 viajes** (la captura aprobada 2026-11-08 mostraba $47,864 sin IVA), y provincias **Orellana 372 + Sucumbíos 16 + sin provincia 16**; Banca **215,000 / 404 / 0.19% / 214,596 m³**; 2 escenarios; tests `test_m4_dashboard.py` | Validar con Julio el ángulo de mercado; auth para exponer |
| — | Despliegue en VPS | ⚪ No iniciado | — | VPS, dominio, TLS, proxy, backups |

Leyenda: ⚪ no iniciado · 🟡 en curso / candado abierto · 🟢 cerrado y congelado

## Dónde está corriendo

| Componente | Local | VPS |
|---|---|---|
| PostgreSQL 15 | `localhost:5433` (contenedor `orminorth-postgres`) | — |
| Redis 7 | `localhost:6380` (contenedor `orminorth-redis`) | — |
| Core API | `http://localhost:8000` (contenedor `orminorth-core-api`) | — |
| Panel (M3 + M4 + Superadmin) | `http://localhost:8000/panel` · Horminor, top header 72 px, sidebar de 6 tabs, dashboard número-primero (mercado, ventas y provincias), obras con SVG locales, agenda y actividad plegables, Poppins local, tema día/noche | — |

Datos de demo en local: órdenes del Ing. Reyes (320 m³ FC-210 y 52 m³ FC-350),
orden del candado del Hito 3 (16 m³) y clientes de fixture con provincia
Orellana/Sucumbíos para verificar la cuota de mercado. Se regeneran con los
scripts de candado.

## Evidencia de la última sesión

- **v6.0 cerrada el 2026-11-09.** Migraci�n 067 aplicada a la base real: ventanilla curada (5401/5301/5201 + 1106), tope de caja chica configurable, compras con proveedores y recepci�n, cierre que resta compras en efectivo y agenda real de entregas/mixers. pytest /app/tests -> **265 passed**. Evidencia: .agents/evidencias/pytest_v6_2026-11-09.txt, clone_v6_2026-11-09.txt, panel_v6_2026-11-09.txt.
- **UX de Secretaría ajustada el 2026-11-09.** La vista abre con acciones
  visibles (cobrar/abonar, gasto, nueva orden) y el orden por tarea: acciones →
  resumen + cierre → cartera → órdenes. Cartera con buscador y cobro por fila.
  `pytest /app/tests` → **247 passed**, consola del navegador sin errores.
  Evidencia: `.agents/evidencias/pytest_ux_secretaria_2026-11-09.txt`.
- **v5.1: panel, Superadmin y backup el 2026-11-09.** El panel de Secretaría
  registra cobros/abonos y gastos contra `/api/v1/panel/pagos`; Superadmin
  edita `finanzas.parametros_contables` y registra el conteo físico; el backup
  diario `scripts/backup_db.sh` verifica el dump con `pg_restore --list`.
  `pytest /app/tests` → **247 passed**; `http_gate_v44_check.py` → **OK** con
  12 verificaciones y `ROLLBACK` en 17 tablas.
- **Custodio v4.4.0 con HTTP cerrado el 2026-11-09.** `app/http_gate/` expone
  `POST /api/v1/custodio/mutations`, `/queries`, `/witness` y
  `GET /catalog` con tokens de servicio; `POST /api/v1/secretaria/pagos`
  registra `COBRO`, `GASTO_CAJA_CHICA` y `GASTO_BANCARIO`, valida saldo,
  separa abono/anticipo y es idempotente. `scripts/http_gate_v44_check.py`
  contra `orminorth_v43` → **HTTP GATE V4.4: OK** con 10 verificaciones y
  `ROLLBACK` en 17 tablas. Evidencia:
  `.agents/evidencias/http_gate_v44_check_2026-11-09.txt`.
- `scripts/custodio_v43_check.py` → **CUSTODIO V4.4: OK** con 30 solicitudes
  (21 ACCEPT, 6 REJECT, 3 PENDING), 8 testigos, 4 aprobaciones y 9 consultas;
  incluye anulación con `CONVERTIR_A_ANTICIPO_CLIENTE`,
  `DEVOLVER_DINERO_CAJA_O_BANCO` y anticipo 1103/2102. Evidencia:
  `.agents/evidencias/custodio_v44_check_2026-11-09.txt`.
- `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` → **242 passed**, exit 0 (`.agents/evidencias/pytest_http_v44_2026-11-09.txt`).
- Hito 1 → `[CANDADO CERRADO]` y Hito 3 → `[CANDADO CERRADO EN SANDBOX]`
  (`.agents/evidencias/hito1_lock_http_v44_2026-11-09.txt`,
  `hito3_lock_http_v44_2026-11-09.txt`).
- Base real: 13 migraciones, órdenes #9/#55/#56/#57, cartera
  **55,043.60 / 2 clientes / fiado 55,043.60**, `payments=0`, 249 movimientos
  y materiales intactos. Evidencia:
  `.agents/evidencias/base_real_v44_final_2026-11-09.txt`.
- **Custodio v4.3 implementado y verificado el 2026-11-09.** `app/custodio/`
  (`contracts.py`, `ledger.py`, `catalog_hygiene.py`, `witness.py`, `gate.py`)
  cubre **14/14 intents de mutación, 9 consultas, 8 solicitudes de testigo y
  2 aprobaciones**. `scripts/custodio_v43_check.py` contra `orminorth_v43` →
  **CUSTODIO V4.3: OK** con 23 solicitudes (17 ACCEPT, 4 REJECT, 2 PENDING),
  asientos balanceados, cartera, compras, depreciación, préstamo, anulación y
  catálogo contable; **ROLLBACK verificado en 17 tablas**. Evidencia:
  `.agents/evidencias/custodio_v43_check_2026-11-09.txt`.
- `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` → **223 passed**, exit 0 (`.agents/evidencias/pytest_custodio_v43_2026-11-09.txt`), incluidos 26 tests puros del Custodio.
- Hito 1 → `[CANDADO CERRADO]` y Hito 3 → `[CANDADO CERRADO EN SANDBOX]`
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
  idempotente por `ANULA:<id>`; las correcciones físicas usan `AJUSTE`.
  `scripts/kardex_v43_check.py` contra `orminorth_v43` →
  **KARDEX V4.3: OK** (promedio 9.1000, snapshot, reversa de 140 a 150,
  rechazo de anulación física y `ROLLBACK` total).
- `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` → **197 passed**, exit 0 (`.agents/evidencias/pytest_kardex_v43_2026-11-09.txt`).
- Hito 1 → `[CANDADO CERRADO]`, 235 movimientos de kardex (`.agents/evidencias/hito1_lock_kardex_v43_2026-11-09.txt`).
- Hito 3 → `[CANDADO CERRADO EN SANDBOX]` (`.agents/evidencias/hito3_lock_kardex_v43_2026-11-09.txt`).
- **Refactor v4.3 aplicado y verificado el 2026-11-09.** `crear_orden` lee
  `finanzas.iva_default_aplica` y el `iva_pct` de la receta, escribe
  `aplica_iva`/`iva_pct`/`iva_monto`/`total_con_iva` e inserta el `COBRO` de
  contado o abono en la misma transacción; `FIADO` no genera `COBRO`.
  `scripts/refactor_v43_check.py` contra `orminorth_v43` →
  **REFACTOR V4.3: OK** (4 ventas, cartera, `deleted_at`, caja y dashboard;
  0 registros de prueba al terminar). Evidencia:
  `.agents/evidencias/refactor_v43_check_2026-11-09.txt`.
- Órdenes reales #55/#56/#57 con IVA 15 % y bruto **$43,424.00 / $9,448.40 /
  $2,171.20** (los candados las recrean con el código nuevo); cartera real
  **55,043.60 / 2 clientes / fiado 55,043.60**; `payments` sigue en 0 porque las
  tres son FIADO. La #9 histórica conserva `total`/`total_con_iva` `NULL`.
  Los costos de materiales siguen en **8.2000 / 14.0000 / 16.5000 / 3.8000** y
  el stock en **3,500 / 450 / 550 / 600**; el kardex no tocó datos reales.
- **Custodio v4.3 aplicado el 2026-11-09.** `.agents/evidencias/revision_v43_2026-11-09.txt`: 11 migraciones, 28 tablas, 6 vistas, 26 cuentas, `por_cobrar 47,864 / 2 clientes / fiado 47,864` (foto previa al refactor); respaldo previo `pre_v43_orminorth.dump`.
- `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` (pre-refactor) → **180 passed**, exit 0 (`.agents/evidencias/pytest_v43_2026-11-09.txt`).
- Hito 1 → `[CANDADO CERRADO]`, 235 movimientos de kardex (`.agents/evidencias/hito1_lock_v43_2026-11-09.txt`).
- Hito 3 → `[CANDADO CERRADO EN SANDBOX]` (`.agents/evidencias/hito3_lock_v43_2026-11-09.txt`).
- Pruebas SQL en `orminorth_v43` → 7 guardas OK, 0 FALLO (`.agents/evidencias/sql_tests_v43_2026-11-09.txt`).
- Contratos v1.3.0 → 4 esquemas válidos, 14/14 ramas (`.agents/evidencias/contracts_v13_2026-11-09.txt`).
- `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` (sesión previa) → **180 passed**, exit 0 (`.agents/evidencias/pytest_panel_horminor_2026-11-08.txt`).
- Playwright 1440×1000 → 3 tarjetas de **253 px** cada una, anillo **0.31%**, **372 / 120,000 m³**, ventas **404 m³ / $47,864 / 4 órdenes / 51 viajes**, provincias Orellana/Sucumbíos/sin provincia, 2 obras con SVG locales, **3 KPIs plegados**, Poppins OK, overflow 0, **0 errores de consola**, **0 requests fallidos**.
- Playwright Banca → **mercado 215,000 m³ · ventas 404 m³ · 0.19% · brecha 214,596 m³**, 2 provincias, 2 escenarios.
- Playwright 390×844 → las 3 tarjetas se apilan, overflow 0, 6 tabs visibles, top header sticky, 2 obras.
- Capturas: `.agents/evidencias/panel_horminor_dashboard_dark.png`, `panel_horminor_dashboard_light.png`, `panel_horminor_banca.png`, `panel_horminor_secretaria.png`, `panel_horminor_superadmin.png`, `panel_horminor_movil.png`, `panel_horminor_clientes.png`, `panel_horminor_planta.png`, `panel_horminor_notificaciones.png`, `panel_horminor_busqueda.png`.
- Design system: `.agents/diseno/horminor_design_system.json`.

## Bloqueos actuales (ordenados por impacto)

1. **Credenciales reales de Evolution API, Bunny.net y Gemini.** Ya **no
   bloquean** demos ni el cierre lógico: en SANDBOX el WhatsApp se encola en
   `sandbox_outbox`, Bunny devuelve URLs simuladas y el Juez es determinístico.
   Abel las sube el **2026-11-09**; se cargan desde el Superadmin
   (`whatsapp_evolution_y_cdn`) y se apaga el switch para pasar a producción.
2. **Teléfonos reales del personal.** La identidad ya está implementada
   (número registrado + códigos `#BODEGA`, `#CAJA`, `#ADMIN`, `#M<n>`);
   `whatsapp.staff` tiene semillas de demostración editables en
   `directorio_roles_whatsapp`.
3. **Datos que Julio todavía no entregó:** RUC, horario, cuentas bancarias,
   placas, choferes, precio de mercado por provincia y umbral de merma. Quedan
   `NULL`/vacíos o como semilla marcada; no se inventaron.
4. **Capacidad operativa de planta (m³ por período) sin definir.** El dashboard
   ya no la usa para el anillo principal (muestra el mercado real de El Coca);
   sigue faltando para un KPI de capacidad operativa. Dueño del dato: Julio.
5. **Formulario de pagos implementado.** `/panel` ya registra cobros, abonos y
   gastos contra `/api/v1/panel/pagos`; falta validarlo con la secretaria real.
6. **Login de usuario final — backlog exclusivo pre-VPS (decisión 2026-11-09).**
   El panel sigue afinándose en local con el puente `X-Panel-Role`; el login
   (`panel_users`, hash, cookie `HttpOnly`) se implementa **solo antes de
   publicar en el VPS**. Mientras tanto, `/panel`, `/api/v1/panel/*` y
   `/api/v1/secretaria/*` no se exponen a Internet.
7. **Backup diario listo, cron pendiente.** `scripts/backup_db.sh` genera,
   verifica y retiene 14 días/6 meses; falta instalarlo en el VPS y copiar los
   dumps fuera de la máquina.
8. **Respaldo externo.** Todo el proyecto y la base viven en un solo disco. Hay
   un respaldo manual previo a v4.3, pero no política automática.
9. **Circuito HTTP cerrado.** El Custodio, el router, la ventanilla de pagos y
   el panel están implementados; solo falta el login de usuario.
10. **Decisiones de negocio cerradas; quedan datos operativos.** IVA histórico,
    fecha de conteo, valoración/DSCR, rol `CONTADORA`, reembolso y nota de
    crédito ya tienen decisión. Falta que Julio/Contadora carguen las tasas,
    que Bodega ejecute el conteo físico y que se validen con la operación real.

> **Repositorio: solo local (ratificado 2026-11-08).** El código vivirá en el
> VPS; GitHub no es requisito para avanzar. Los commits locales en `orminorth/`
> son la fuente de verdad y el respaldo. `git push` deja de ser un bloqueo y
> pasa a ser una tarea opcional del despliegue (clonar el repo en el VPS).

## Próximo paso exacto

1. **Probar el panel en local con la secretaria** (cobro/abono, gasto, tasas y
   conteo) y ajustar pantallas/flujos según lo que pida Julio. El login no
   bloquea esta etapa.
2. **Cargar las tasas financieras** en Superadmin >
   `finanzas.parametros_contables` (`wacc_anual_pct`,
   `crecimiento_anual_pct`, `participacion_trabajadores_pct`,
   `impuesto_renta_pct`, `dscr_minimo_banco`) para activar valoración/DSCR.
3. **Ejecutar el conteo físico** de los 5 materiales desde Superadmin; hoy
   siguen `SIN_FECHA_CONTEO`.
4. **Instalar el cron de backup** (`backup_db.sh`) y copiar los dumps fuera del
   VPS; probar una restauración mensual.
5. **Dashboard V2 aprobado por Julio (2026-11-08).** La captura de referencia es
   `.agents/evidencias/panel_horminor_dashboard_v2_dark_2026-11-08.png`; el
   ángulo comercial es **372 m³ vendidos de 120,000 m³ (0.31%)** en El Coca.
   Sigue pendiente que Julio entregue la **capacidad operativa de planta**.
6. **Producción del Hito 3:** cargar credenciales reales en
   `PUT /api/v1/superadmin/config/whatsapp_evolution_y_cdn`, poner
   `evolution_sandbox=false` y `bunny_sandbox=false`, y repetir
   `docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py`.
7. **Backlog pre-VPS (no antes):** implementar el login de usuario
   (`panel_users`, hash `scrypt`, cookie `HttpOnly`) y proteger `/panel` y las
   rutas de Secretaría/Superadmin. Después: VPS, TLS, proxy inverso y cron de
   backups.

## Decisiones de arquitectura vigentes

| # | Decisión | Porqué |
|---|---|---|
| 1 | 12 tablas (el PDR dice 10 sin enumerarlas) | Cubre todo lo que el propio PDR nombra |
| 2 | `tracking_payload` JSONB es autoritativo | Contrato entre M1 y M3 sin acoplamiento |
| 3 | Kardex teórico por viaje, no por orden | Cada JSON de viaje es autosuficiente |
| 4 | `materials.stock_actual` = stock real | Evita mezclar teórico con físico |
| 5 | Receta provisional **no** bloquea la venta | El viaje marca `receta_provisional` y el Centinela avisa; detener la venta cuesta más |
| 6 | Migraciones SQL planas + advisory lock | Sin ORM: el contrato es SQL |
| 7 | `timestamptz` en UTC, zona operativa en BD | El offset no se escribe en el código |
| 8 | Identidad WhatsApp: número registrado > código de operador > lead | Una sola regla, en base de datos, sin reescribir el bot |
| 9 | Debounce de 14 s sobre Redis, con degradación a memoria | El webhook responde de inmediato y la API sigue arriba si Redis falla |
| 10 | Dos umbrales térmicos (60 y 30 min antes) | Aviso temprano para reaccionar y crítico para escalar |
| 11 | Alertas sin webhook quedan como `NO_CONFIGURADO` en `error_logs` | No se finge un envío que no ocurrió |
| 12 | **Todo parámetro de negocio es dinámico** (semilla 050 + Superadmin) | Julio no bloquea el avance; el frontend edita sin tocar código |
| 13 | **Sin login en Superadmin/Secretaría por ahora** | No frenar pruebas de API ni integración del Frontend; se desacopla al final |
| 14 | El bot arma su respuesta con datos de BD; el LLM solo decide SÍ/NO | Cero precios o promesas inventadas por el modelo |
| 15 | **SANDBOX por adaptadores inyectables** | El mismo contrato pasa a producción al cargar credenciales; sin `if` de sandbox en el pipeline |
| 16 | **Outbox persistido** en `sandbox_outbox` + memoria | El simulador y los tests ven lo mismo; no se finge un envío real |
| 17 | **Cupo de crédito alerta, no bloquea** | La venta se registra con `excede_cupo_credito=true`; bloquear cuesta más que cobrar |
| 18 | **Precio de orden = explícito o precio de receta** | La venta queda valorada; si no hay precio en ninguno, el total queda NULL y pendiente |
| 19 | **`clients.provincia` para cuota de mercado** | La demanda es provincial; las ventas sin provincia se informan aparte, no se reparten |
| 20 | **Panel único HTML sin build ni CDN** | Funciona en local y VPS sin toolchain de frontend; se puede migrar después |
| 21 | **Centinela sin llamadas externas en SANDBOX** | Un WARN por el CDN real confundía la salud del sistema |
| 22 | **Migración 061 separada** | La 060 ya estaba aplicada; no se edita una migración aplicada |
| 23 | **Tema visual V2 en tokens CSS** (`data-theme` + `localStorage`) | Oscuro ejecutivo por defecto para Julio; claro de oficina conmutable para Secretaría; sin build ni CDN y sin tocar contratos ni tests |
| 24 | **Marca visible Horminor; carpeta/repo siguen como `orminorth`** | Es lo que ve el cliente; renombrar rutas, contenedores e historial rompería comandos sin aportar valor |
| 25 | **Poppins local y sidebar CRM de 258 px** | La tipografía de la referencia queda servida desde `/static` (sin Google Fonts); la sidebar reproduce la captura y colapsa a barra superior en <900 px |
| 26 | **Corrección de marca en migración 062** | Las migraciones 050/060 ya estaban aplicadas; se corrige el ADN público y Bunny sin editar el pasado |
| 27 | **Panel con shell ShikshaQ y jerarquía número-primero** | Top header fijo, sidebar de 6 tabs, donut/actividad/calendario y 3 obras; los párrafos se reemplazan por cifras grandes y barras. Se conservan IDs, `data-*`, rutas y contratos; cero build y cero CDN. Alternativa descartada: copiar los textos largos del API, que cansan la lectura |
| 28 | **`_json_objeto()` normaliza JSONB en M3** | `obtener_carpeta` hacía `dict(tracking_payload)` y devolvía 500 cuando asyncpg entrega JSONB como texto. El helper acepta texto o mapping y devuelve `{}` si no se puede parsear; la carpeta forense volvió a 200 sin tocar el contrato |
| 29 | **Dashboard V2 número-primero con el mercado como ancla comercial** | Tres tarjetas iguales (Mercado El Coca, Ventas 2026, Dónde vendes) que responden qué necesita Julio; agenda y actividad bajan a una fila inferior; caja/mixers/bodega quedan en `<details>`. La tarjeta de mercado muestra **0.31% / 372 m³ / 120,000 m³** y la de Banca **215,000 / 404 / 0.19% / 214,596 m³** sin párrafos. Se conservan IDs, `data-*`, rutas API y los tests existentes; ilustraciones SVG locales sin build ni CDN. Alternativa descartada: seguir mostrando el anillo de eficiencia (2/51 viajes) como protagonista, que no vende posicionamiento |
| 30 | **`v_cliente_saldo` conserva las 8 columnas originales** | Los 3 consumidores y `catalog.py` dependen de `id, nombre, estado, total_m3, total_facturado, total_cobrado, total_fiado, saldo_pendiente`; v4.3 agrega `ruc`, `credit_limit_usd` y `saldo_a_favor` al final. Alternativa descartada: reordenar o cambiar tipos, que rompía consumidores |
| 31 | **Fallback `COALESCE(total_con_iva, total)` en la vista** | Mantiene visibles las órdenes históricas sin bruto (la #9) sin inventarles IVA. Las ventas nuevas ya escriben `total_con_iva`; el fallback queda permanentemente para históricos |
| 32 | **IVA 15 % solo para ventas nuevas; históricos sin IVA** | La decisión de Julio fue default 15 % en ventas nuevas; la #9 anterior queda con `total_con_iva = total`/`NULL` y `finanzas.iva_historico_confirmado=false` hasta confirmación retroactiva |
| 33 | **Inventario por promedio ponderado** | Confirmado el 2026-11-09; `inventory_movements.costo_unitario_snapshot` guarda el costo vigente y el kardex calcula COGS con esa base |
| 34 | **Gate idempotente + ledger/testigo inmutables** | `processed_requests` guarda `request_id` + hash; `ledger_entries` y `audit_witness_log` solo permiten INSERT y las correcciones se hacen con reversa/testigo. Alternativa descartada: `UPDATE` directo, que borra la trazabilidad |
| 35 | **IVA y COBRO inicial en la transacción de la orden** | `crear_orden` valida el abono contra el bruto y escribe orden + `payments` juntos: si falla el pago, no queda una venta contada como cobrada. El router no inserta pagos por su cuenta. Alternativa descartada: un segundo `INSERT` desde el endpoint, que dejaba ventas huérfanas si fallaba |
| 36 | **El pago inicial de una compra va en un asiento `SUPPLIER_PAYMENT` separado** | Si el pago se asentara dentro de `PURCHASE`, corregir el pago con testigo revertiría también la compra. Separado, cada documento tiene su propia reversa y su propio testigo |
| 37 | **Corrección con testigo limitada al asiento vigente y a compras de servicio de una línea** | Solo se revierte el asiento sin reversa previa (evita duplicar el ajuste) y una compra con inventario o varias líneas exige nota de crédito: redistribuir stock o costos desde una cabecera sería inventar datos |
| 38 | **Valoración/DSCR parametrizados y anulación con modos** | Si faltan tasas en `finanzas.parametros_contables`, el Gate devuelve la foto real y `UNCONFIRMED_FINANCIAL_RATES`; si existen, calcula DCF/DSCR. La anulación con cobros exige `modo_resolucion_cobro` y no consume la aprobación si falta |
| 39 | **Router HTTP con tokens de servicio y roles oficiales** | `CUSTODIO_TOKEN_SUPERADMIN/CONTADORA/SECRETARIA/BODEGA/CHOFER` + `X-Actor-Id` + `X-Channel`; el rol nunca viaja en el JSON. `SECRETARIA` y `CONTADORA` cobran; `BODEGA` y `CHOFER` no |
| 40 | **Pagos con split 1103/2102** | Abono parcial permitido. Si `monto > saldo` y `es_anticipo=false` → `PAYMENT_EXCEEDS_PENDING_BALANCE`; si `es_anticipo=true`, la deuda va a `1103` y el excedente a `2102`, con `saldo_a_favor` |
| 41 | **Reembolso con `modo_resolucion_cobro`** | `CONVERTIR_A_ANTICIPO_CLIENTE` reclasifica a `2102`; `DEVOLVER_DINERO_CAJA_O_BANCO` inserta `REEMBOLSO_CAJA` y borra lógicamente el cobro original |
| 42 | **IVA por defecto apagado** | `066` deja `finanzas.iva_default_aplica=false`. Las ventas nuevas solo llevan IVA si el contrato envía `aplica_iva=true`; el panel y los candados lo envían, así que la cartera verificada de $55,043.60 no cambia |
| 43 | **El navegador no recibe tokens del Custodio** | El panel llama a `/api/v1/panel/pagos` y `/api/v1/panel/catalog`; el servidor resuelve el actor (`X-Panel-Role` mientras no haya login). Los `CUSTODIO_TOKEN_*` quedan solo en el backend |
| 44 | **Superadmin edita tasas y conteo, no valores inventados** | `finanzas.parametros_contables` se edita con inputs; el conteo físico se registra con stock real y sella `ultimo_levantamiento_at`. Los valores siguen siendo de Julio/Bodega |
| 45 | **Backup diario verificable, no solo un dump** | `backup_db.sh` valida con `pg_restore --list`, retiene 14 días y 6 meses, y se complementa con copia externa y restauración mensual |
| 46 | **Login desacoplado al backlog pre-VPS** | Se sigue afinando `/panel` con el puente `X-Panel-Role` (sin credenciales ni bloqueo de rutas) para no perder agilidad en pantallas y flujos. El login (`panel_users`, hash, cookie `HttpOnly`) se implementa únicamente antes de exponer el panel a Internet. Alternativa descartada: bloquear rutas ahora, que obliga a crear usuarios y frena las pruebas locales |

## Riesgos abiertos

- Sin backups de PostgreSQL definidos (se van a generar carpetas bancarias).
- Sin proxy inverso ni TLS: no se puede exponer el webhook de Evolution.
- `.env` con clave de desarrollo: **no usar en producción** (rotar antes del VPS).
- **Todo el proyecto vive en un solo disco.** Al no usar repositorio remoto, no
  hay copia fuera de la máquina: hacer respaldo periódico del repo (otra unidad,
  disco externo o carpeta en la nube). Esta es la única deuda real de "solo
  local".
- Las rutas del panel, Secretaría y Superadmin están abiertas: **no exponerlas
  a Internet** hasta que exista autenticación.
- Las semillas de staff, flota, bancos y benchmarks son de **demostración**;
  reemplazarlas por datos reales antes de operar.
- La primera llamada al Centinela puede tardar más por apertura del pool; en
  caliente medimos ~100 ms con 12 checks (el PDR exige <200 ms).
