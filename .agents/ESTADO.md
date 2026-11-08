# ESTADO DEL PROYECTO

> Foto del presente. Se reescribe en cada sesión. La historia está en `BITACORA.md`.
> Última actualización: **2026-11-08**

## Hitos

| Hito | Módulo | Estado | Evidencia | Qué falta para cerrar |
|---|---|---|---|---|
| 1 | M0 — Datos y configuración | 🟢 **Cerrado** con semilla oficial | `evidencias/hito1_lock_cierre.txt`: 17/17 `[OK]`, `[CANDADO CERRADO]`, 235 movimientos de kardex | Nada bloqueante. Re-verificar si se editan recetas |
| — | Superadmin — Configuración en caliente | 🟡 Construido y verificado local | `evidencias/superadmin_config.txt`: 7 secciones, CRUD y recarga en vivo | Frontend y autenticación (al final del proyecto) |
| 2 | M2 — Motor determinístico | 🟡 Construido, verificado local | 157 tests + candado Hito 1 cerrado | Probar desde el CRM de la agencia en el VPS |
| 2 | M5 — Nodo Centinela | 🟡 Construido, verificado local | `evidencias/centinela_cierre_hito1.json`: 12 checks, `recetas_provisionales=OK` | Clave real + URL del webhook del CRM |
| 3 | M1 — WhatsApp (Evolution + Jeb + Bunny) | 🟡 Construido, **candado abierto** | `evidencias/hito3_lock_cierre_hito1.txt`: 34/34 `[OK]` + 157 tests | Credenciales reales y teléfonos del personal |
| 4 | M3 — Ventanilla de secretaría | ⚪ No iniciado | — | Decidir stack del panel (Aquatech) |
| 5 | M4 — Dashboard de Julio + Ases | ⚪ No iniciado | — | Fórmulas de DSCR y cuota de mercado |
| — | Despliegue en VPS | ⚪ No iniciado | — | VPS, dominio, TLS, proxy, backups |

Leyenda: ⚪ no iniciado · 🟡 en curso / candado abierto · 🟢 cerrado y congelado

## Dónde está corriendo

| Componente | Local | VPS |
|---|---|---|
| PostgreSQL 15 | `localhost:5433` (contenedor `orminorth-postgres`) | — |
| Redis 7 | `localhost:6380` (contenedor `orminorth-redis`) | — |
| Core API | `http://localhost:8000` (contenedor `orminorth-core-api`) | — |

Datos de demo en local: órdenes del Ing. Reyes (320 m³ FC-210 y 52 m³ FC-350)
creadas por el Test de Candado, más viajes sintéticos del candado del Hito 3.
Se pueden regenerar con los scripts.

## Bloqueos actuales (ordenados por impacto)

1. **Credenciales reales de Evolution API, Bunny.net y Gemini.** El Módulo 1
   funciona con el juez determinístico y Bunny en memoria; el Centinela los
   reporta `NO_CONFIGURADO` (correcto, no es un error). Se cargan desde el
   Superadmin (`whatsapp_evolution_y_cdn`) o por `.env`.
2. **Teléfonos reales del personal.** La identidad ya está implementada
   (número registrado + códigos `#BODEGA`, `#CAJA`, `#ADMIN`, `#M<n>`), pero
   `whatsapp.staff` sigue vacío. Se edita en
   `directorio_roles_whatsapp` sin reiniciar el servidor.
3. **Datos que Julio todavía no entregó:** RUC, horario, cuentas bancarias,
   placas, choferes y tope de crédito automático. Quedan `NULL`/vacíos y el bot
   omite esas líneas; no se inventaron.
4. **`git push` bloqueado con 403** por credenciales de otra cuenta
   (`ObjetivoCesar`). El commit local sí se hace.

## Próximo paso exacto

1. **Ruta A (Hito 3):** la agencia entrega credenciales de Evolution/Bunny/Gemini
   y los teléfonos del personal → cargarlos en el Superadmin o `.env` →
   repetir `hito3_lock_test.py` con los servicios reales y cerrar Hito 3.
2. **Ruta B (Frontend):** consumir
   `GET /api/v1/superadmin/config` para construir el panel de las 7 secciones.
   La autenticación se agrega al final, como acordado.
3. **En paralelo:** corregir las credenciales de git y hacer `git push` (ver
   bitácora 2026-11-08: hoy falla con 403 por cuenta equivocada).

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

## Riesgos abiertos

- Sin backups de PostgreSQL definidos (se van a generar carpetas bancarias).
- Sin proxy inverso ni TLS: no se puede exponer el webhook de Evolution.
- `.env` con clave de desarrollo: **no usar en producción** (rotar antes del VPS).
- El push a GitHub está bloqueado por credenciales de otra cuenta (`ObjetivoCesar`).
- Las rutas Superadmin están abiertas: **no exponerlas a Internet** hasta que
  exista autenticación.
- La primera llamada al Centinela puede tardar más por apertura del pool; en
  caliente medimos ~100 ms con 12 checks (el PDR exige <200 ms).
