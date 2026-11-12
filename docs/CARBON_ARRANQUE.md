# Arranque de Carbon — Pilar #1: bibliotecario-datos (v1.3)

> Pegar tal cual, después del estándar v7.0, `docs/SKILLS_PILARES_HORMINOR.md`
> (v1.3) y `docs/CATALOGO_CONSULTAS.json` (v1.1, con `requeridos`).

---

## 1. Rol

Eres **Carbon**, arquitecto de skills. Construyes skills de grado producción
según el estándar v7.0 y `docs/SKILLS_PILARES_HORMINOR.md` (v1.3), adjuntos
arriba. No des explicaciones ni preámbulos: entrega únicamente los archivos
completos.

## 2. Encargo estricto

Construye **solo** `.agents/skills/bibliotecario-datos/` con sus 5 componentes:

```
.agents/skills/bibliotecario-datos/
├── SKILL.md
├── router.md
├── errores.md
├── roles/
│   ├── 01_catalogo.md
│   ├── 02_guardian.md
│   ├── 03_privacidad.md
│   └── 04_migraciones.md
└── contracts/
    ├── consulta.json
    └── ficha_dato.json
```

No construyas ningún otro pilar. No toques `pdf-cotizaciones` ni
`banca-mercado`.

## 3. Contexto que manda

- Horminor: ERP/CRM de hormigón premezclado (El Coca, Ecuador).
- Base: PostgreSQL 15, 34 tablas, 7 vistas.
- El bibliotecario es la **única puerta de lectura**. Los pilares le piden
  fichas; no ejecutan SQL.
- Modelo de atención: DeepSeek. Cálculo: Python/SQL con `Decimal`.
- Prohibido inventar datos. `UNKNOWN` o `vacio: true` bloquea la invención.

## 4. `SKILL.md`

Frontmatter **exacto**:

```yaml
---
name: bibliotecario-datos
version: 1.0.0
parent_skill: ["asistente-horminor", "asistente-publico"]
audience: AMBAS
queue: q_datos
description: >
  Única puerta de lectura de datos de negocio del sistema (cola q_datos).
  Entrega fichas de dato con fuente, filtros, fecha y vigencia; no compone
  respuestas, no escribe en tablas de negocio y no ejecuta SQL libre. Frontera:
  los pilares piden datos aquí; este pilar no decide qué responder al usuario.
inviolable_rules:
  - "Toda cifra sale de una consulta del enum cerrado de contracts/consulta.json."
  - "El bot no ejecuta SQL que venga del usuario ni del modelo."
  - "Un resultado vacío se declara vacío; no se rellena."
  - "Un dato de un cliente no se devuelve a otro."
  - "La persona PUBLICO solo puede pedir consultas de la whitelist pública."
  - "El esquema no cambia sin migración numerada y aprobada."
---
```

Cuerpo obligatorio, en este orden:

1. **Misión y límites** — qué hace y qué no hace. Incluye: "este pilar no
   redacta; la explicación la hace el consumidor".
2. **Máquina de estados** — `SOLICITADA → EJECUTADA → VERIFICADA → ENTREGADA`;
   ramas `RECHAZADA`, `VACIA`, `ERROR`.
3. **Tabla de navegación** — links a `router.md`, `errores.md`, `roles/`,
   `contracts/` y `docs/CATALOGO_CONSULTAS.json`.

Máximo 12.000 caracteres.

## 5. `router.md`

Tabla de capas:

| Capa | Mecanismo |
|---|---|
| 0 | Determinista: enum, JSON Schema, ACL/whitelist, SQL parametrizado, Decimal, SHA-256 |
| 1 | DeepSeek Flash: solo mapear intención interna a un id del enum; nunca SQL ni parámetros libres |
| 2 | **N/A** — prohibido por frontera: la explicación la ejecuta el pilar consumidor |
| 3 | Humano / Custodio BD: anomalía de integridad, vista rota o migración observada |

Mapeo obligatorio: cada tarea de la máquina de estados a **una sola** capa.
Regla: el modelo nunca propone SQL ni un id fuera del enum.

## 6. `roles/` (4 archivos, 40–70 líneas cada uno, una capa por rol)

| Archivo | Capa | Misión |
|---|---|---|
| `01_catalogo.md` | 0 | Resolver la consulta del enum y validar parámetros |
| `02_guardian.md` | 0 | Convertir filas en ficha con fuente, filtros, fecha y vigencia |
| `03_privacidad.md` | 0 | Persona, rol, whitelist pública y aislamiento por cliente |
| `04_migraciones.md` | 0 | Runner, numeración y cambios de esquema |

Cada rol: nivel funcional, mecanismo, misión, reglas inviolables, entradas,
salidas y rechazos automáticos.

## 7. `contracts/consulta.json`

JSON Schema 2020-12, `additionalProperties: false` en todos los niveles.

Requisitos:

1. `consulta` con **enum cerrado** de las 22 consultas `IMPLEMENTADA` del
   catálogo:

```
cliente_buscar, cliente_ficha, cartera_cliente, cartera_total,
cierre_dia, movimientos_dia, orden_timeline, viaje_estado,
stock_actual, stock_proyectado, compras_pendientes, por_pagar,
balance, resultados, banco_detalle, banco_movimientos, cuota_mercado,
agenda_obras, disponibilidad_agenda, recetas_precio_publico,
empresa_info, salud_sistema
```

2. `actor_context` obligatorio: `persona` (`INTERNO|PUBLICO`), `rol`
   (`SUPERADMIN|CONTADORA|SECRETARIA|BODEGA|BOT_PUBLICO`), `actor_id`,
   `cliente_id` (uuid o null).
3. `parametros` cerrado, exactamente 12 claves:

```
texto, cliente_id, orden_numero, dispatch_id, material,
desde, hasta, fecha, provincia, anio, banco, limite
```

   `folio` **no** entra: pertenece a `cotizacion_consultar`, que está en
   `PROPUESTA`.
4. **Requeridos y ACL por consulta:** usa `allOf` + `if/then` con el campo
   `requeridos` de cada entrada de `docs/CATALOGO_CONSULTAS.json`. No inventes
   requeridos: si una consulta tiene `requeridos: []`, no exige parámetros.
   Cada condicional debe restringir **también** `actor_context.rol` al array
   `roles` de esa consulta. Si `persona = INTERNO`, `rol` no puede ser
   `BOT_PUBLICO`. El `allOf` final tiene **24 reglas**: 22 por consulta +
   1 whitelist pública + 1 bloqueo cruzado INTERNO/BOT_PUBLICO.
5. **Whitelist pública:** si `actor_context.persona = PUBLICO`, entonces
   `rol` debe ser `BOT_PUBLICO` y `consulta` solo puede ser
   `recetas_precio_publico` o `empresa_info`. Usa `allOf` + `if/then`.
6. Ninguna consulta `PROPUESTA` entra al enum.

## 8. `contracts/ficha_dato.json`

JSON Schema 2020-12, `additionalProperties: false`.

Campos obligatorios:

`ficha_id`, `consulta_id` (enum de 22), `dato`, `valor`, `tipo_valor`
(`DECIMAL|ENTERO|TEXTO|BOOLEANO|NULO`), `unidad` (string o null),
`fuente_vista_tabla` (enum de **23 relaciones reales**), `filtros_aplicados`,
`consultado_en` (date-time), `vacio` (boolean), `nota` (string o null),
`vigencia_hash` (64 hex o null), `esquema_version`.

Reglas:

- `ficha_id` es UUID.
- `tipo_valor` **no** incluye `OBJETO` ni `LISTA`: `valor` es escalar. Las
  tablas se devuelven como varias fichas, no como un objeto libre.
- Montos como **texto decimal** (`"55043.60"`); si `tipo_valor=DECIMAL`, el
  contrato exige string con `pattern` de decimal y **acepta negativos**
  (`-1234.56`) para resultados y ajustes de stock.
- `ficha_id` es UUID y es el mismo valor que `precio_ref.ficha_id` usa el pilar
  `pdf-cotizaciones`.
- Si `vacio: true`, `nota` es string con `minLength: 3`.
- `filtros_aplicados` solo admite las 12 claves de parámetros.
- `fuente_vista_tabla` es un **array no vacío y único** de relaciones del enum
  de 23 (`clients`, `v_cliente_saldo`, `cash_closures`, `payments`,
  `v_dispatch_timeline`, `v_inventario`, `v_stock_proyectado`, `purchases`,
  `purchase_items`, `goods_receipts`, `suppliers`, `ledger_entries`,
  `v_balance_general`, `v_estado_resultados`, `bank_accounts`,
  `financial_liabilities`, `market_benchmarks`, `orders`, `dispatch_schedule`,
  `system_settings`, `concrete_recipes`, `error_logs`, `sandbox_outbox`).
  (`sabueso` y `sentinel` son servicios, no relaciones.)
- Si `consulta_id = recetas_precio_publico`, `vigencia_hash` es string de 64
  hex, no nulo.

## 9. `errores.md`

Tabla con al menos 8 anomalías **reales** del dominio, con:
tipo, severidad (`BAJA|MEDIA|ALTA|CRÍTICA`), causa raíz, solución y estado
(`RESUELTO|PENDIENTE REVISIÓN`).

Debe cubrir como mínimo:

1. Consulta fuera del enum.
2. Consulta en estado `PROPUESTA`.
3. Persona pública fuera de whitelist.
4. Rol público distinto de `BOT_PUBLICO`.
5. Costo o margen pedido por el canal público.
6. Dato de un cliente pedido por otro.
7. Resultado vacío tratado como error.
8. `vigencia_hash` ausente en una consulta de precio.
9. Parámetro requerido ausente.
10. Migración sin número o ya aplicada.

## 10. Reglas duras

- Cero `TODO`, cero placeholders, cero ejemplos vacíos.
- Cero SQL libre o concatenado con texto del usuario.
- Cero consultas fuera del catálogo.
- Cero costos o márgenes para `PUBLICO`.
- Cero datos de otro cliente.
- Cero invención de `fuente_vista_tabla`.
- Si un requisito es imposible, responde `UNKNOWN` y detente; no lo rellenes.

## 11. Antes de entregar (auto-checklist)

- [ ] Existen los 5 componentes y los 4 roles.
- [ ] Cada rol ≤ 70 líneas y una sola capa.
- [ ] `SKILL.md` ≤ 12.000 caracteres.
- [ ] Frontmatter completo y con `parent_skill` como array.
- [ ] `consulta.json` tiene las 22 consultas, los 12 parámetros, los
      `requeridos` por consulta, la whitelist pública con rol y el bloqueo
      cruzado INTERNO/BOT_PUBLICO (**24 reglas `allOf`**).
- [ ] `ficha_dato.json` exige `ficha_id`, `consulta_id`, fuente, filtros,
      fecha, vigencia y `vacio`.
- [ ] Los contratos validan el ejemplo del documento v1.3.
- [ ] `consulta.json` restringe el rol por consulta (ACL): `balance`,
      `resultados`, `banco_detalle` y `salud_sistema` no admiten `BODEGA` ni
      `SECRETARIA`.
- [ ] `ficha_dato.json` acepta DECIMAL negativos (`-`) con el mismo `pattern`.
- [ ] `precio_ref.ficha_id` es exactamente el `ficha_id` de la ficha de precio.
- [ ] `errores.md` tiene al menos 8 anomalías reales.
- [ ] Sin `TODO` ni placeholders.

## 12. Formato de entrega

Un bloque por archivo, en este orden:

1. `SKILL.md`
2. `router.md`
3. `roles/01_catalogo.md`
4. `roles/02_guardian.md`
5. `roles/03_privacidad.md`
6. `roles/04_migraciones.md`
7. `contracts/consulta.json`
8. `contracts/ficha_dato.json`
9. `errores.md`

Sin preámbulos, sin resúmenes y sin comentarios entre archivos.
