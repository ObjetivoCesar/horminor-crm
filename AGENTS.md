# AGENTS.md — Horminor / Centinela

Contrato de trabajo para cualquier agente (OpenCode, Antigravity, Codex, Claude)
que toque este repositorio. Léelo completo antes de editar. No es documentación
decorativa: son reglas operativas.

---

## 1. Contexto en 30 segundos

- **Cliente:** Julio Villavicencio — Horminor (hormigón premezclado y planta
  móvil, El Coca / Orellana y Sucumbíos, Ecuador). El repositorio y la carpeta
  conservan el nombre histórico `orminorth`; la marca visible es **HORMINOR**.
- **Producto:** ERP/CRM modular + automatización por WhatsApp + Nodo Centinela
  de telemetría para el CRM de la agencia.
- **Fuente de verdad del alcance:** `docs/PDR_v4.0.pdf` y su versión de texto
  `docs/PDR_v4.0.txt` (PDR v4.0). Si algo no está ahí, no se asume: se pregunta.
- **Stack:** PostgreSQL 15 + Redis 7 + FastAPI + Evolution API + Bunny.net,
  todo en Docker. Objetivo final: VPS Linux.
- **Estado:** Hito 1 **cerrado** con la semilla oficial (5 recetas confirmadas)
  y el Centro de Configuración Superadmin de 7 secciones. Hito 3 **cerrado en
  modo SANDBOX** (WhatsApp encolado, Bunny simulado, Juez determinístico).
  Módulos 3 (Secretaría + Caja) y 4 (Dashboard de Julio y Ases) construidos y
  verificados en local. El panel `/panel` usa la marca **HORMINOR**, sidebar
  tipo CRM, tipografía Poppins servida desde `/static` y tema día/noche. La
  producción real solo espera credenciales y teléfonos, que se cargan desde el
  Superadmin sin reiniciar. El Custodio v4.4.0 (Gate contable, libro mayor,
  testigo, router HTTP con tokens de servicio y ventanilla de pagos) está
  implementado y verificado contra el clon con `ROLLBACK`; faltan el formulario
  de pagos en el panel y el login de usuario final. Ver `.agents/ESTADO.md`.
- **Datos que faltan:** `docs/00_DECISIONES_PENDIENTES.md`.

## 2. Arranque de sesión (obligatorio, en este orden)

1. `.agents/ESTADO.md` → qué está hecho, qué está bloqueado, próximo paso.
2. Últimas 3 entradas de `.agents/BITACORA.md` → qué pasó la última vez.
3. Según la tarea:
   - levantar/verificar el entorno → `.agents/skills/orminorth-entorno/SKILL.md`
   - correr o interpretar un Test de Candado → `.agents/skills/orminorth-candado/SKILL.md`
   - diagnosticar salud del sistema → `.agents/skills/orminorth-diag-centinela/SKILL.md`
   - tocar datos de negocio → `.agents/procesos/04-datos-negocio.md`
   - crear una migración → `.agents/procesos/03-migraciones.md`

## 3. Reglas duras

1. **Cero datos de negocio inventados.** Si Julio no entregó una receta, un
   precio, un teléfono o un stock, va `NULL` y se marca `PENDIENTE`. Nunca un
   valor "razonable" que parezca real.
2. **Cero datos de negocio en el código.** Todo vive en `system_settings` o en
   `concrete_recipes`. Si escribes un precio o un teléfono en Python, está mal.
3. **Evidencia o no existe.** Un hito se cierra con el comando ejecutado y su
   salida registrada en la bitácora. "Debería funcionar" no cierra nada.
4. **No editar migraciones ya aplicadas.** Se crea `0NN_descripcion.sql`.
5. **La IA no calcula.** El Módulo 2 es aritmética con `Decimal`. Si te tienta
   usar un LLM para sumar, multiplicar o decidir un estado, no lo hagas.
6. **El JSONB manda.** `mixer_dispatches.tracking_payload` es el contrato; las
   columnas planas las sincroniza el trigger. No las escribas a mano.
7. **Un módulo cerrado no se reabre.** Si hay que cambiarlo, se documenta la
   razón en la bitácora y se abre una decisión explícita.
8. **Contexto fuera del chat.** Salidas largas (logs, tests, dumps) van a
   `.agents/evidencias/` y en la conversación solo se cita la ruta y el
   resumen. No pegues 200 líneas de log en el chat.
9. **Secretos fuera del repo.** `.env` está en `.gitignore`. Nunca escribas
   claves reales en documentación, ejemplos ni bitácora.

## 4. Cierre de sesión (obligatorio)

1. Añadir una entrada nueva al final de `.agents/BITACORA.md` (plantilla en
   `.agents/plantillas/entrada-bitacora.md`), con: objetivo, hecho, evidencia,
   decisiones, bloqueos y **próximo paso exacto**.
2. Actualizar la tabla de hitos de `.agents/ESTADO.md` si cambió algo.
3. Si tomaste una decisión de arquitectura, dejarla escrita en la entrada de la
   bitácora con el porqué y la alternativa descartada.

## 5. Comandos canónicos

Desde `orminorth/`:

```powershell
# levantar todo
docker compose up -d --build

# estado de contenedores
docker ps --filter name=orminorth --format "{{.Names}}  {{.Status}}"

# migraciones
docker compose run --rm --no-deps core-api python scripts/db_migrate.py

# tests
docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto

# Test de Candado del Hito 1
docker compose run --rm --no-deps core-api python scripts/hito1_lock_test.py

# Test de Candado del Hito 3 (bodega, chofer y cliente)
docker compose run --rm --no-deps core-api python scripts/hito3_lock_test.py

# Centinela
curl.exe -H "X-Agency-Master-Key: $env:AGENCY_MASTER_KEY" http://localhost:8000/api/v1/sentinel/daily-audit

# apagar sin perder datos
docker compose stop
```

## 6. Mapa del repositorio

| Ruta | Qué es |
|---|---|
| `db/migrations/` | Esquema y seeds versionados (se aplican al arrancar) |
| `services/core-api/app/m1_whatsapp/` | WhatsApp: webhook, debounce, identidad, Juez "Jeb", Bunny |
| `services/core-api/app/superadmin/` | Configuración en caliente: 7 secciones + CRUD recetas/flota |
| `services/core-api/app/m2_planta/` | Motor determinístico (dosificador, kardex) |
| `services/core-api/app/m3_secretaria/` | Ventanilla, carpeta forense y cierre de caja |
| `services/core-api/app/m4_dashboard/` | KPIs, cuota de mercado, simulador y dossier |
| `services/core-api/app/m5_sentinel/` | Centinela (12 chequeos) |
| `services/core-api/app/sandbox.py` | Adaptadores SANDBOX (WhatsApp, Bunny, Juez) |
| `services/core-api/app/web/` | Panel HTML en `/panel` (3 vistas, sin build) + `/static` (Poppins y logo Horminor) |
| `services/core-api/app/services/ordenes.py` | Alta de orden: M0 + M2 |
| `services/core-api/app/custodio/` | Gate contable: 14 intents, 9 consultas, ledger, testigo y catálogo |
| `services/core-api/app/http_gate/` | Router HTTP, tokens de servicio y ventanilla de pagos |
| `services/core-api/app/routers/` | HTTP: health, catálogo, órdenes |
| `services/core-api/tests/` | pytest (247 tests) |
| `scripts/hito1_lock_test.py` | Test de Candado del Hito 1 |
| `scripts/hito3_lock_test.py` | Test de Candado del Hito 3 |
| `scripts/custodio_v43_check.py` | Check de integración del Custodio en el clon, con `ROLLBACK` |
| `scripts/http_gate_v44_check.py` | Check HTTP v4.4.0 contra el clon, con `ROLLBACK` |
| `scripts/backup_db.sh` | Backup diario verificado con retención 14/6 |
| `docs/OPERACION_BACKUPS.md` | Cron, retención y restauración de prueba |
| `docs/` | Decisiones pendientes y modelo de datos |
| `.agents/` | Memoria, procesos, skills y evidencias |

## 7. Skills disponibles

| Skill | Usar cuando |
|---|---|
| `orminorth-entorno` | Hay que levantar, reiniciar o verificar el stack local |
| `orminorth-candado` | Hay que ejecutar o interpretar un Test de Candado |
| `orminorth-diag-centinela` | El Centinela reporta WARN/CRÍTICO o hay que leer su JSON |
| `orminorth-bitacora` | Hay que registrar una sesión o actualizar el estado |

## 8. Lo que este proyecto NO tiene todavía

No lo asumas ni lo simules:

- Autenticación/login de usuarios en Superadmin y Secretaría (desacoplada para
  el final; no exponer esas rutas a Internet mientras sigan abiertas).
- Credenciales reales de Evolution API, Bunny.net ni Gemini: en SANDBOX los
  adaptadores de `app/sandbox.py` cubren el flujo; al cargarlas se apaga el
  switch y pasan los clientes reales.
- Teléfonos reales del personal: `whatsapp.staff` tiene semillas de
  demostración; la regla de identidad ya está implementada y se edita en
  caliente desde el Superadmin.
- RUC, horario, cuentas bancarias, placas y choferes reales (las semillas están
  marcadas como provisionales y son editables).
- Precio de mercado por provincia y umbral de merma: el PDR no fija las cifras;
  quedan `NULL`/`NO_CONFIGURADO` hasta que Julio los entregue.
- Despliegue en VPS, proxy inverso, TLS ni backups.
- Facturación electrónica SRI (**fuera de alcance**, ratificado 2026-11-08).
