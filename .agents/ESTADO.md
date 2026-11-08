# ESTADO DEL PROYECTO

> Foto del presente. Se reescribe en cada sesión. La historia está en `BITACORA.md`.
> Última actualización: **2026-11-08**

## Hitos

| Hito | Módulo | Estado | Evidencia | Qué falta para cerrar |
|---|---|---|---|---|
| 1 | M0 — Datos y configuración | 🟡 Construido, **candado abierto** | `BITACORA` 2026-11-08 | Recetas reales validadas por Julio |
| 2 | M2 — Motor determinístico | 🟡 Construido, verificado local | 33 tests + lock test | Probar desde el CRM de la agencia en el VPS |
| 2 | M5 — Nodo Centinela | 🟡 Construido, verificado local | `daily-audit` 20–25 ms | Clave real + URL del webhook del CRM |
| 3 | M1 — WhatsApp (Evolution + Jeb + Bunny) | ⚪ No iniciado | — | Identificación de remitentes + credenciales |
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
creadas por el Test de Candado. Se pueden regenerar con el script.

## Bloqueos actuales (ordenados por impacto)

1. **Recetas reales inexistentes.** FC-210 tiene 7,5 sacos/m³ derivado del
   ejemplo del PDR; FC-180/280/350 vacías. Sin esto no hay kardex ni alerta de
   merma, y el Hito 1 no cierra.
2. **Identidad de remitentes de WhatsApp sin definir.** Un solo número para
   bodeguero, chofer, cliente y leads. Bloquea el Hito 3.
3. **Flota real sin confirmar.** Hoy solo `MIXER-01` de 8 m³.
4. **Precios y stock inicial sin datos.** `orders.total` queda `NULL`.
5. **Credenciales de Evolution API y Bunny.net.** Hoy el Centinela los reporta
   `NO_CONFIGURADO` (correcto, no es un error).

Detalle completo y cómo cerrar cada uno: `../docs/00_DECISIONES_PENDIENTES.md`.

## Próximo paso exacto

Elegir una de las dos rutas:

- **A (recomendada):** Julio entrega la tabla de dosificaciones → cargarla con
  `procesos/04-datos-negocio.md` → correr el Test de Candado → cerrar Hito 1.
- **B:** arrancar el Módulo 1 con identificación por número registrado, dejando
  la regla en `system_settings` para cambiarla sin reescribir el bot.

## Decisiones de arquitectura vigentes

| # | Decisión | Porqué |
|---|---|---|
| 1 | 12 tablas (el PDR dice 10 sin enumerarlas) | Cubre todo lo que el propio PDR nombra |
| 2 | `tracking_payload` JSONB es autoritativo | Contrato entre M1 y M3 sin acoplamiento |
| 3 | Kardex teórico por viaje, no por orden | Cada JSON de viaje es autosuficiente |
| 4 | `materials.stock_actual` = stock real | Evita mezclar teórico con físico |
| 5 | Receta no confirmada ⇒ motor bloqueado | Preferimos sistema detenido a inventario falso |
| 6 | Migraciones SQL planas + advisory lock | Sin ORM: el contrato es SQL |
| 7 | `timestamptz` en UTC, zona operativa en BD | El offset no se escribe en el código |

## Riesgos abiertos

- Sin backups de PostgreSQL definidos (se van a generar carpetas bancarias).
- Sin proxy inverso ni TLS: no se puede exponer el webhook de Evolution.
- `.env` con clave `dev-only-key-hito2`: **no usar en producción**.
- Primera llamada al Centinela ~250–400 ms por apertura de conexiones; en
  caliente 20–25 ms. El PDR exige <200 ms; conviene precalentar el pool.
