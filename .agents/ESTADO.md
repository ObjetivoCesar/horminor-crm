# ESTADO DEL PROYECTO

> Foto del presente. Se reescribe en cada sesión. La historia está en `BITACORA.md`.
> Última actualización: **2026-11-08**

## Hitos

| Hito | Módulo | Estado | Evidencia | Qué falta para cerrar |
|---|---|---|---|---|
| 1 | M0 — Datos y configuración | 🟡 Construido, **candado abierto** | `evidencias/hito1_lock_post_hito3.txt` (8/8 `[OK]`) | Recetas reales validadas por Julio |
| 2 | M2 — Motor determinístico | 🟡 Construido, verificado local | 134 tests + candado Hito 1 | Probar desde el CRM de la agencia en el VPS |
| 2 | M5 — Nodo Centinela | 🟡 Construido, verificado local | `evidencias/hito3_centinela.json` (12 checks, 77.3 ms) | Clave real + URL del webhook del CRM |
| 3 | M1 — WhatsApp (Evolution + Jeb + Bunny) | 🟡 Construido, **candado abierto** | `evidencias/hito3_lock.txt` (28/28 `[OK]`) + 134 tests | Credenciales reales y teléfonos del personal |
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

1. **Recetas reales inexistentes.** FC-210 tiene 7,5 sacos/m³ derivado del
   ejemplo del PDR; FC-180/280/350 vacías. Sin esto no hay kardex ni alerta de
   merma, y el Hito 1 no cierra.
2. **Credenciales reales de Evolution API, Bunny.net y Gemini.** El Módulo 1
   funciona con el juez determinístico y Bunny en memoria; el Centinela los
   reporta `NO_CONFIGURADO` (correcto, no es un error).
3. **Teléfonos reales del personal.** La identidad ya está implementada
   (número registrado + códigos `#BODEGA`, `#CAJA`, `#ADMIN`, `#M<n>`), pero
   `whatsapp.staff` sigue vacío: sin datos reales no se puede probar con los
   celulares de Orminorth.
4. **Flota real sin confirmar.** Hoy solo `MIXER-01` de 8 m³.
5. **Precios y stock inicial sin datos.** `orders.total` queda `NULL`.

Detalle completo y cómo cerrar cada uno: `../docs/00_DECISIONES_PENDIENTES.md`.

## Próximo paso exacto

1. **Ruta A (Hito 1):** Julio entrega la tabla de dosificaciones → cargarla con
   `procesos/04-datos-negocio.md` → correr `hito1_lock_test.py` → cerrar Hito 1.
2. **Ruta B (Hito 3):** la agencia entrega credenciales de Evolution/Bunny/Gemini
   y los teléfonos del personal → cargarlos en `.env` y `whatsapp.staff` →
   repetir `hito3_lock_test.py` con los servicios reales y cerrar Hito 3.
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

## Riesgos abiertos

- Sin backups de PostgreSQL definidos (se van a generar carpetas bancarias).
- Sin proxy inverso ni TLS: no se puede exponer el webhook de Evolution.
- `.env` con clave de desarrollo: **no usar en producción** (rotar antes del VPS).
- El push a GitHub está bloqueado por credenciales de otra cuenta (`ObjetivoCesar`).
- La primera llamada al Centinela puede tardar más por apertura del pool; en
  caliente medimos 77.3 ms con 12 checks (el PDR exige <200 ms).
