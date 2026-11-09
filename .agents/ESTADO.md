# ESTADO DEL PROYECTO

> Foto del presente. Se reescribe en cada sesión. La historia está en `BITACORA.md`.
> Última actualización: **2026-11-09** (Custodio v4.3 aplicado y consumido por
> ventas/caja/dashboard: 11 migraciones, 28 tablas, 6 vistas, 26 cuentas;
> 192 tests y los 2 candados en verde. Quedan kardex y Gate/testigo)

## Hitos

| Hito | Módulo | Estado | Evidencia | Qué falta para cerrar |
|---|---|---|---|---|
| 1 | M0 — Datos y configuración | 🟢 **Cerrado** con semilla oficial | `evidencias/hito1_lock_2026-11-08.txt`: `[CANDADO CERRADO]`, 235 movimientos de kardex, órdenes valoradas ($37.760 y $8.216) | Nada bloqueante. Re-verificar si se editan recetas |
| — | Superadmin — Configuración en caliente | 🟢 Construido y editable desde el panel | 7 secciones, CRUD de recetas/flota, simulador de WhatsApp y outbox | Autenticación antes de exponerlo a Internet |
| 2 | M2 — Motor determinístico | 🟡 Construido, verificado local | `evidencias/pytest_refactor_v43_2026-11-09.txt`: **192 tests** + candado Hito 1 | Probar desde el CRM de la agencia en el VPS |
| 2 | M5 — Nodo Centinela | 🟡 Construido, verificado local | `evidencias/hito3_4_live_2026-11-08.txt`: 12 checks, `modo=SANDBOX`, `judge_mode=DETERMINISTIC_FALLBACK`; Evolution/Bunny en OK | Webhook real del CRM; umbral de merma que defina Julio |
| 3 | M1 — WhatsApp (Evolution + Jeb + Bunny) | 🟢 **Cerrado en SANDBOX** | `evidencias/hito3_lock_2026-11-08.txt`: `[CANDADO CERRADO EN SANDBOX]`; 4 compuertas, JSONB y outbox | Producción real: cargar credenciales, apagar SANDBOX y repetir el candado |
| 4 | M3 — Ventanilla de Secretaría + Caja | 🟢 Construido y verificado local | `/panel` (tab Secretaría), carpeta forense con 47 viajes de mixer, `GET .../carpeta` 200 tras fix JSONB; tests `test_m3_secretaria.py` | Autenticación; validación con la secretaria real; POST de pagos/abonos |
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

- **Refactor v4.3 aplicado y verificado el 2026-11-09.** `crear_orden` lee
  `finanzas.iva_default_aplica` y el `iva_pct` de la receta, escribe
  `aplica_iva`/`iva_pct`/`iva_monto`/`total_con_iva` e inserta el `COBRO` de
  contado o abono en la misma transacción; `FIADO` no genera `COBRO`.
  `scripts/refactor_v43_check.py` contra `orminorth_v43` →
  **REFACTOR V4.3: OK** (4 ventas, cartera, `deleted_at`, caja y dashboard;
  0 registros de prueba al terminar). Evidencia:
  `.agents/evidencias/refactor_v43_check_2026-11-09.txt`.
- `docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto` → **192 passed**, exit 0 (`.agents/evidencias/pytest_refactor_v43_2026-11-09.txt`).
- Hito 1 → `[CANDADO CERRADO]`, 235 movimientos de kardex (`.agents/evidencias/hito1_lock_refactor_v43_2026-11-09.txt`).
- Hito 3 → `[CANDADO CERRADO EN SANDBOX]` (`.agents/evidencias/hito3_lock_refactor_v43_2026-11-09.txt`).
- Órdenes reales #43/#44/#45 con IVA 15 % y bruto **$43,424.00 / $9,448.40 /
  $2,171.20** (los candados las recrean con el código nuevo); cartera real
  **55,043.60 / 2 clientes / fiado 55,043.60**; `payments` sigue en 0 porque las
  tres son FIADO. La #9 histórica conserva `total`/`total_con_iva` `NULL`.
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
5. **Sin POST de pagos/abonos.** Secretaría muestra los cobros del cierre en
   solo lectura; no se pueden registrar abonos nuevos desde el panel.
6. **Sin autenticación.** `/panel`, `/api/v1/secretaria/*` y
   `/api/v1/superadmin/*` están abiertos: no exponerlos a Internet hasta
   implementar login.
7. **Responsable/custodio de la base de datos sin designar.** No hay un DBA ni
   un custodio formal de PostgreSQL en producción documentado. El desarrollo
   técnico lo sostiene César Reyes y los datos de negocio son de Julio; el
   custodio operativo del VPS queda **pendiente de confirmar** (ver
   `docs/BASE_DE_DATOS.md`, sección 5).
8. **Respaldo externo.** Todo el proyecto y la base viven en un solo disco. Hay
   un respaldo manual previo a v4.3, pero no política automática.
9. **Código pendiente en kardex y Custodio ejecutable.** `crear_orden`, caja y
   dashboard ya consumen v4.3; el kardex todavía no maneja `ANULACION` ni costo
   promedio ponderado, y faltan `gate.py`, `witness.py` y
   `catalog_hygiene.py`.
10. **IVA histórico, fecha de conteo, fórmula 10 años/DSCR y rol `CONTADORA`
    siguen pendientes de Julio/Dirección.** No se inventaron: los históricos
    quedaron `total_con_iva = total` (o `NULL` si los recreó un candado), los
    materiales `SIN_FECHA_CONTEO` y no existe vista de valoración especulativa.

> **Repositorio: solo local (ratificado 2026-11-08).** El código vivirá en el
> VPS; GitHub no es requisito para avanzar. Los commits locales en `orminorth/`
> son la fuente de verdad y el respaldo. `git push` deja de ser un bloqueo y
> pasa a ser una tarea opcional del despliegue (clonar el repo en el VPS).

## Próximo paso exacto

1. **Refactorizar el kardex para consumir v4.3** (prioridad):
   - `services/core-api/app/m2_planta/kardex.py`: costo promedio ponderado,
     `ANULACION` como reversa y `costo_unitario_snapshot`.
   - Pruebas nuevas + **192 tests + Hito 1 + Hito 3** después del refactor.
2. **Implementar el Custodio ejecutable:** `gate.py`, `witness.py`,
   `catalog_hygiene.py` y sus pruebas contra los contratos v1.3.0.
3. **Confirmar con Julio/Dirección:** IVA histórico de la orden #9, fecha de
   conteo, fórmula de valoración 10 años/DSCR y rol `CONTADORA`.
4. **Dashboard V2 aprobado por Julio (2026-11-08).** La captura de referencia es
   `.agents/evidencias/panel_horminor_dashboard_v2_dark_2026-11-08.png`; el
   ángulo comercial es **372 m³ vendidos de 120,000 m³ (0.31%)** en El Coca.
   Sigue pendiente que Julio entregue la **capacidad operativa de planta**.
5. **Producción del Hito 3:** cargar credenciales reales en
   `PUT /api/v1/superadmin/config/whatsapp_evolution_y_cdn`, poner
   `evolution_sandbox=false` y `bunny_sandbox=false`, y repetir
   `docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py`.
6. **Autenticación:** login para Superadmin/Secretaría antes de publicar el
   panel en el VPS.
7. **Despliegue:** cuando exista el VPS, copiar el repo, levantar el stack y
   configurar TLS, proxy inverso y backups.
8. **Backups de PostgreSQL:** definir política y custodio del volumen
   `orminorth-pgdata` (hoy solo existe el respaldo manual previo a v4.3).

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
| 29 | **Dashboard V2 número-primero con el mercado como ancla comercial** | Tres tarjetas iguales (Mercado El Coca, Ventas 2026, Dónde vendes) que responden qué necesita Julio; agenda y actividad bajan a una fila inferior; caja/mixers/bodega quedan en `<details>`. La tarjeta de mercado muestra **0.31% / 372 m³ / 120,000 m³** y la de Banca **215,000 / 404 / 0.19% / 214,596 m³** sin párrafos. Se conservan IDs, `data-*`, rutas API y los 192 tests; ilustraciones SVG locales sin build ni CDN. Alternativa descartada: seguir mostrando el anillo de eficiencia (2/51 viajes) como protagonista, que no vende posicionamiento |
| 30 | **`v_cliente_saldo` conserva las 8 columnas originales** | Los 3 consumidores y `catalog.py` dependen de `id, nombre, estado, total_m3, total_facturado, total_cobrado, total_fiado, saldo_pendiente`; v4.3 agrega `ruc`, `credit_limit_usd` y `saldo_a_favor` al final. Alternativa descartada: reordenar o cambiar tipos, que rompía consumidores |
| 31 | **Fallback `COALESCE(total_con_iva, total)` en la vista** | Mantiene visibles las órdenes históricas sin bruto (la #9) sin inventarles IVA. Las ventas nuevas ya escriben `total_con_iva`; el fallback queda permanentemente para históricos |
| 32 | **IVA 15 % solo para ventas nuevas; históricos sin IVA** | La decisión de Julio fue default 15 % en ventas nuevas; la #9 anterior queda con `total_con_iva = total`/`NULL` y `finanzas.iva_historico_confirmado=false` hasta confirmación retroactiva |
| 33 | **Inventario por promedio ponderado** | Confirmado el 2026-11-09; `inventory_movements.costo_unitario_snapshot` guarda el costo vigente y el kardex calculará COGS con esa base |
| 34 | **Gate idempotente + ledger/testigo inmutables** | `processed_requests` guarda `request_id` + hash; `ledger_entries` y `audit_witness_log` solo permiten INSERT y las correcciones se hacen con reversa/testigo. Alternativa descartada: `UPDATE` directo, que borra la trazabilidad |
| 35 | **IVA y COBRO inicial en la transacción de la orden** | `crear_orden` valida el abono contra el bruto y escribe orden + `payments` juntos: si falla el pago, no queda una venta contada como cobrada. El router no inserta pagos por su cuenta. Alternativa descartada: un segundo `INSERT` desde el endpoint, que dejaba ventas huérfanas si fallaba |

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
