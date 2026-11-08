# ESTADO DEL PROYECTO

> Foto del presente. Se reescribe en cada sesión. La historia está en `BITACORA.md`.
> Última actualización: **2026-11-08**

## Hitos

| Hito | Módulo | Estado | Evidencia | Qué falta para cerrar |
|---|---|---|---|---|
| 1 | M0 — Datos y configuración | 🟢 **Cerrado** con semilla oficial | `evidencias/hito1_lock_2026-11-08.txt`: `[CANDADO CERRADO]`, 235 movimientos de kardex, órdenes valoradas ($37.760 y $8.216) | Nada bloqueante. Re-verificar si se editan recetas |
| — | Superadmin — Configuración en caliente | 🟢 Construido y editable desde el panel | 7 secciones, CRUD de recetas/flota, simulador de WhatsApp y outbox | Autenticación antes de exponerlo a Internet |
| 2 | M2 — Motor determinístico | 🟡 Construido, verificado local | `evidencias/hito3_4_pytest_2026-11-08.txt`: **180 tests** + candado Hito 1 | Probar desde el CRM de la agencia en el VPS |
| 2 | M5 — Nodo Centinela | 🟡 Construido, verificado local | `evidencias/hito3_4_live_2026-11-08.txt`: 12 checks, `modo=SANDBOX`, `judge_mode=DETERMINISTIC_FALLBACK`; Evolution/Bunny en OK | Webhook real del CRM; umbral de merma que defina Julio |
| 3 | M1 — WhatsApp (Evolution + Jeb + Bunny) | 🟢 **Cerrado en SANDBOX** | `evidencias/hito3_lock_2026-11-08.txt`: `[CANDADO CERRADO EN SANDBOX]`; 4 compuertas, JSONB y outbox | Producción real: cargar credenciales, apagar SANDBOX y repetir el candado |
| 4 | M3 — Ventanilla de Secretaría + Caja | 🟢 Construido y verificado local | `/panel` y endpoints `/api/v1/secretaria/*`; tests `test_m3_secretaria.py` | Autenticación; validación con la secretaria real |
| 5 | M4 — Dashboard de Julio + Ases | 🟢 Construido y verificado local | KPIs, cuota de mercado, simulador y dossier; tests `test_m4_dashboard.py` | Validar números con Julio; auth para exponer |
| — | Despliegue en VPS | ⚪ No iniciado | — | VPS, dominio, TLS, proxy, backups |

Leyenda: ⚪ no iniciado · 🟡 en curso / candado abierto · 🟢 cerrado y congelado

## Dónde está corriendo

| Componente | Local | VPS |
|---|---|---|
| PostgreSQL 15 | `localhost:5433` (contenedor `orminorth-postgres`) | — |
| Redis 7 | `localhost:6380` (contenedor `orminorth-redis`) | — |
| Core API | `http://localhost:8000` (contenedor `orminorth-core-api`) | — |
| Panel (M3 + M4 + Superadmin) | `http://localhost:8000/panel` | — |

Datos de demo en local: órdenes del Ing. Reyes (320 m³ FC-210 y 52 m³ FC-350),
orden del candado del Hito 3 (16 m³) y clientes de fixture con provincia
Orellana/Sucumbíos para verificar la cuota de mercado. Se regeneran con los
scripts de candado.

## Bloqueos actuales (ordenados por impacto)

1. **Credenciales reales de Evolution API, Bunny.net y Gemini.** Ya **no
   bloquean** demos ni el cierre lógico: en SANDBOX el WhatsApp se encola en
   `sandbox_outbox`, Bunny devuelve URLs simuladas y el Juez es determinístico.
   Se cargan desde el Superadmin (`whatsapp_evolution_y_cdn`) y se apaga el
   switch para pasar a producción.
2. **Teléfonos reales del personal.** La identidad ya está implementada
   (número registrado + códigos `#BODEGA`, `#CAJA`, `#ADMIN`, `#M<n>`);
   `whatsapp.staff` tiene semillas de demostración editables en
   `directorio_roles_whatsapp`.
3. **Datos que Julio todavía no entregó:** RUC, horario, cuentas bancarias,
   placas, choferes, precio de mercado por provincia y umbral de merma. Quedan
   `NULL`/vacíos o como semilla marcada; no se inventaron.
4. **Sin autenticación.** `/panel`, `/api/v1/secretaria/*` y
   `/api/v1/superadmin/*` están abiertos: no exponerlos a Internet hasta
   implementar login.
5. **Respaldo externo.** Todo el proyecto y la base viven en un solo disco.

> **Repositorio: solo local (ratificado 2026-11-08).** El código vivirá en el
> VPS; GitHub no es requisito para avanzar. Los commits locales en `orminorth/`
> son la fuente de verdad y el respaldo. `git push` deja de ser un bloqueo y
> pasa a ser una tarea opcional del despliegue (clonar el repo en el VPS).

## Próximo paso exacto

1. **Producción del Hito 3:** cargar credenciales reales en
   `PUT /api/v1/superadmin/config/whatsapp_evolution_y_cdn`, poner
   `evolution_sandbox=false` y `bunny_sandbox=false`, y repetir
   `docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py`.
2. **Autenticación:** login para Superadmin/Secretaría antes de publicar el
   panel en el VPS.
3. **Validación con Julio:** revisar los KPIs, la cuota de mercado y los dos
   escenarios del simulador; cargar benchmarks/precios reales por provincia.
4. **Despliegue:** cuando exista el VPS, copiar el repo, levantar el stack y
   configurar TLS, proxy inverso y backups.

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
