# Skills de Horminor — pilares, herramientas y handoff a Carbon (v1.3)

> **Para qué sirve:** paquete que se lleva al chat de diseño con Carbon.
> Contiene el estándar adaptado, el mapa de pilares, dos skills completas, el
> catálogo cerrado de consultas y el encargo exacto.
>
> **No es código de producto.** Es la especificación que después se implementa
> en `services/core-api/app/asistente/`.
>
> **Contratos v1.4:** 12 parámetros, `requeridos` y ACL por consulta, bloqueo
> cruzado INTERNO/BOT_PUBLICO, ficha con fuentes múltiples. El historial de
> auditorías y el protocolo viven en **`docs/AUDITORIA_SKILLS_CARBON.md`**.
>
> Complementa: `docs/ASISTENTE_IA_PROPUESTA.md`, `docs/ASISTENTE_IA_SKILLS.md`.

---

## 0. Cómo usar este documento con Carbon

Pegar en el chat, en este orden:

1. El **estándar v7.0**.
2. Este documento completo.
3. `docs/CATALOGO_CONSULTAS.json`.
4. El encargo de §11.

Carbon devuelve, por pilar: `SKILL.md`, `router.md`, `errores.md`,
`roles/*.md` y `contracts/*.json`, sin placeholders. Si un dato falta, se
declara `UNKNOWN` y se bloquea la transición.

**Límite de longitud:** `SKILL.md` ≤ **12.000 caracteres**.

---

## 1. Contexto mínimo

- **Cliente:** Horminor (hormigón premezclado, El Coca / Orellana y Sucumbíos).
- **Producto:** ERP/CRM modular, panel `/panel`, Custodio contable, WhatsApp.
- **Base:** PostgreSQL 15, 34 tablas, 7 vistas, 19 migraciones.
- **Modelo de atención:** **DeepSeek**, API key en `.env`.
- **Regla del PDR:** la matemática es determinística; la IA no calcula ni
  inventa cifras (`PDR_v4.0.txt` §3.1/§3.2).
- **Dos personas:** `HORMINOR_INTERNO` (solo CRM) y `HORMINOR_PUBLICO`
  (clientes y leads).
- **Prohibido:** costos y márgenes en el canal público.

---

## 2. Skill, herramienta y contrato

| Pieza | Qué es | Quién la ejecuta | Ejemplo |
|---|---|---|---|
| **Skill** | Gobernadora de un pilar: reglas, límites, estados | El orquestador (DeepSeek) | `banca-mercado` |
| **Herramienta** | Función determinística con entrada/salida validada | El backend | `banca.detalle(slug)` |
| **Contrato** | JSON Schema 2020-12 | Validador (Capa 0) | `consulta_banco.json` |

**La skill no hace el trabajo: lo gobierna.** La herramienta toca los datos; el
contrato impide que entre basura. Ningún pilar ejecuta SQL libre.

---

## 3. Estándar v7.0 adaptado

### 3.1 Los 5 componentes (obligatorios)

```
.agents/skills/<pilar>/
├── SKILL.md
├── router.md
├── errores.md
├── roles/
│   ├── 01_<rol>.md
│   └── 02_<rol>.md
└── contracts/
    ├── <entrada>.json
    └── <salida>.json
```

### 3.2 Frontmatter obligatorio

```yaml
---
name: <pilar>
version: 1.0.0
parent_skill: <string | [string, string] | null>
audience: INTERNO | PUBLICO | AMBAS
queue: <cola>
description: <misión 1 línea + cola + frontera>
inviolable_rules:
  - "<regla que nunca se rompe>"
---
```

**Regla de `parent_skill` (resuelta):**

| Tipo de skill | `parent_skill` |
|---|---|
| Raíz (`asistente-horminor`, `asistente-publico`) | `null` |
| Solo interna | `"asistente-horminor"` |
| Solo pública | `"asistente-publico"` |
| Compartida ("Ambas") | `["asistente-horminor", "asistente-publico"]` |

`audience` es una extensión de Horminor y debe coincidir con `parent_skill`.
Una skill compartida sin `audience: AMBAS` se rechaza en el checklist.

### 3.3 Colas (6, congeladas)

| Cola | Dominio |
|---|---|
| `q_gobierno` | Raíces y enrutamiento |
| `q_datos` | Bibliotecario, configuración, salud |
| `q_finanzas` | Cartera, caja, banca, contabilidad |
| `q_operacion` | Planta, compras, agenda |
| `q_documentos` | PDF y cotizaciones |
| `q_publico` | Solicitudes del bot público |

### 3.4 Capas

| Capa | Mecanismo |
|---|---|
| 0 | Código determinista (validadores, Decimal, ACL, SQL) |
| 1 | DeepSeek Flash (clasificación) |
| 2 | DeepSeek Chat (composición) |
| 3 | DeepSeek Reasoner + humano (auditoría) |

Cada rol declara **una sola capa**. Si una operación necesita otra capa, se
desglosa en `router.md`, no en el rol.

### 3.5 Regla de estados

`UNKNOWN` bloquea la transición o manda a cuarentena. `vacio: true` es un
estado válido. Un dato de otro cliente es rechazo.

---

## 4. Mapa de pilares

**14 skills, 2 personas, 6 colas.**

### 4.1 Gobierno

| Skill | Parent | Audience | Cola | Misión |
|---|---|---|---|---|
| `asistente-horminor` | `null` | INTERNO | `q_gobierno` | Orquestar el CRM |
| `asistente-publico` | `null` | PUBLICO | `q_gobierno` | Atender clientes y leads |
| `bibliotecario-datos` | ambas raíces | AMBAS | `q_datos` | Única puerta de lectura |

### 4.2 Finanzas

| Skill | Parent | Audience | Cola | Misión |
|---|---|---|---|---|
| `cartera-cobros` | interno | INTERNO | `q_finanzas` | Saldos, cupos y borradores de cobro |
| `caja-cierre` | interno | INTERNO | `q_finanzas` | Cobros, gastos y cierre |
| `banca-mercado` | interno | INTERNO | `q_finanzas` | Bancos, cuota y simulador |
| `contabilidad-reportes` | interno | INTERNO | `q_finanzas` | Balance, resultados, DSCR |

### 4.3 Operación

| Skill | Parent | Audience | Cola | Misión |
|---|---|---|---|---|
| `planta-inventario` | interno | INTERNO | `q_operacion` | Stock, kardex y alertas |
| `compras-proveedores` | interno | INTERNO | `q_operacion` | Compras y por pagar |
| `agenda-obras-visitas` | ambas raíces | AMBAS | `q_operacion` | Entregas y citas comerciales |

### 4.4 Documentos

| Skill | Parent | Audience | Cola | Misión |
|---|---|---|---|---|
| `pdf-cotizaciones` | ambas raíces | AMBAS | `q_documentos` | Cotización con folio |

### 4.5 Público y configuración

| Skill | Parent | Audience | Cola | Misión |
|---|---|---|---|---|
| `solicitudes-publicas` | público | PUBLICO | `q_publico` | Solicitudes y confirmación |
| `configuracion-precios` | interno | INTERNO | `q_datos` | Empresa, recetas, precios, costos |
| `salud-sistema` | interno | INTERNO | `q_datos` | Centinela y errores |

### 4.6 Fronteras

- `banca-mercado` no cobra ni paga: solo lee y simula.
- `cartera-cobros` no emite PDF: pide a `pdf-cotizaciones`.
- `pdf-cotizaciones` no calcula precios ni lee clientes.
- `agenda-obras-visitas` no decide disponibilidad de mixers por su cuenta.
- `bibliotecario-datos` no compone respuestas: devuelve fichas.
- `configuracion-precios` no publica costos al bot.

---

## 5. Ejemplo completo 1 — `pdf-cotizaciones`

### 5.1 `SKILL.md`

**Misión:** convertir una solicitud válida en un PDF con folio, validez y
snapshot de precio. **No** calcula precios, **no** lee clientes, **no** factura.

**Estados:**

```
RECIBIDA
  ├─ falta dato → CUARENTENA
  ├─ contrato inválido → RECHAZADA
  ▼
VALIDADA (Schema + Decimal + vigencia_hash)
  ├─ precio caducado → RECHAZADA
  ├─ total_esperado distinto → RECHAZADA
  ├─ actor sin permiso → RECHAZADA
  ├─ canal BOT sin confirmación → PRELIMINAR
  ▼
EMITIDA → ACEPTADA | ANULADA
```

### 5.2 Roles (una capa cada uno)

| Rol | Capa | Qué hace |
|---|---|---|
| `01_armador.md` | 0 | Valida líneas, Decimal, vigencia y total |
| `02_emisor.md` | 0 | ACL, folio y persistencia |
| `03_publicador.md` | 0 | Render, storage y URL |

### 5.3 `contracts/solicitud_cotizacion.json` (ejemplo)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "contract_name": "solicitud_cotizacion",
  "version": "1.2.0",
  "type": "object",
  "additionalProperties": false,
  "required": ["plantilla", "cliente", "lineas", "iva_pct", "validez_dias", "creado_por"],
  "properties": {
    "plantilla": {"type": "string", "enum": ["cotizacion_v1"]},
    "cliente": {
      "type": "object",
      "additionalProperties": false,
      "required": ["nombre"],
      "properties": {
        "nombre": {"type": "string", "minLength": 2, "maxLength": 160},
        "ruc": {"type": ["string", "null"], "pattern": "^\\d{10,13}$"},
        "telefono": {"type": ["string", "null"], "pattern": "^\\+?\\d{7,15}$"},
        "obra": {"type": ["string", "null"], "maxLength": 200}
      }
    },
    "lineas": {
      "type": "array", "minItems": 1, "maxItems": 30,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["descripcion", "cantidad_m3", "precio_m3", "precio_ref"],
        "properties": {
          "descripcion": {"type": "string", "minLength": 3, "maxLength": 200},
          "cantidad_m3": {"type": "string", "pattern": "^(?!0+(\\.0{1,4})?$)\\d+(\\.\\d{1,4})?$"},
          "precio_m3": {"type": "string", "pattern": "^\\d+(\\.\\d{1,2})?$"},
          "precio_ref": {
            "type": "object",
            "additionalProperties": false,
            "required": ["ficha_id", "vigencia_hash"],
            "properties": {
              "ficha_id": {"type": "string", "pattern": "^[0-9a-fA-F-]{36}$"},
              "vigencia_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"}
            }
          }
        }
      }
    },
    "total_esperado": {"type": ["string", "null"], "pattern": "^\\d+(\\.\\d{1,2})?$"},
    "iva_pct": {"type": "string", "pattern": "^\\d{1,2}(\\.\\d{1,2})?$"},
    "validez_dias": {"type": "integer", "minimum": 1, "maximum": 90},
    "condiciones": {"type": ["string", "null"], "maxLength": 500},
    "solicitud_id": {"type": ["string", "null"], "pattern": "^[A-Za-z0-9_-]{1,64}$"},
    "creado_por": {
      "type": "object",
      "additionalProperties": false,
      "required": ["actor_id", "rol", "canal"],
      "properties": {
        "actor_id": {"type": "string", "minLength": 1, "maxLength": 80},
        "rol": {"type": "string", "enum": ["SUPERADMIN", "CONTADORA", "SECRETARIA", "BOT_PUBLICO"]},
        "canal": {"type": "string", "enum": ["WEB_PANEL", "WHATSAPP", "BOT"]}
      }
    }
  }
}
```

### 5.4 `router.md`

| Tarea | Capa | Mecanismo |
|---|---|---|
| Validar contrato | 0 | JSON Schema |
| Validar aritmética | 0 | Decimal |
| Verificar `vigencia_hash` | 0 | Consulta de precio + hash |
| Comparar `total_esperado` | 0 | Decimal |
| Redactar condiciones por defecto | 0 | Plantilla fija |
| Autorizar actor | 0 | ACL |
| Explicar la cotización | 2 | DeepSeek Chat |
| Detectar cotización ambigua | 2 | DeepSeek Chat |
| Anulación con reclamo | 3 | Humano |

### 5.5 `errores.md`

| Tipo | Severidad | Causa raíz | Solución | Estado |
|---|---|---|---|---|
| Aritmética no cuadra | ALTA | Total distinto a la suma | Recalcular y rechazar | RESUELTO |
| Precio caducado | ALTA | `vigencia_hash` viejo | Rechazar y pedir precio vigente | RESUELTO |
| Sin referencia de precio | ALTA | Línea sin `precio_ref` | Rechazo en contrato | RESUELTO |
| Sin validez | MEDIA | Campo opcional | Obligatorio | RESUELTO |
| Actor sin permiso | CRÍTICA | Endpoint sin ACL | Validar rol | RESUELTO |
| Bunny caído | MEDIA | Storage no configurado | Guardar local | PENDIENTE REVISIÓN |
| Folio duplicado | ALTA | Secuencia no atómica | Secuencia por año | RESUELTO |

---

## 6. Ejemplo completo 2 — `banca-mercado`

### 6.1 `SKILL.md`

**Misión:** responder por bancos y mercado. Solo lectura, solo interno.

**Estados:**

```
RECIBIDA → IDENTIFICADA → CONSULTADA → VERIFICADA → RESPONDIDA
                │              ├─ vacío → SIN_DATO
                │              └─ inconsistencia → ESCALADA
                └─ rol/persona inválida → RECHAZADA
```

Reglas: nunca inventa saldos; contable ≠ informado; movimientos solo con cuenta
hija; simulador etiquetado "proyección"; el público no la usa.

### 6.2 Roles (una capa cada uno)

| Rol | Capa | Qué hace |
|---|---|---|
| `01_consultor-bancos.md` | 0 | Cuentas, saldos, préstamos, movimientos |
| `02_analista-mercado.md` | 0 | Cuota, brecha, benchmarks |
| `03_simulador.md` | 0 | Escenarios y DSCR |

### 6.3 `router.md`

| Tarea | Capa | Mecanismo |
|---|---|---|
| Leer saldo y movimientos | 0 | Consulta nombrada |
| Separar contable/informado | 0 | Regla fija |
| Calcular cuota y brecha | 0 | `m4_dashboard/calculos.py` |
| Explicar el número | 2 | DeepSeek Chat con ficha |
| Detectar inconsistencia | 2 | DeepSeek Chat + escalar |

### 6.4 `errores.md`

| Tipo | Severidad | Causa raíz | Solución | Estado |
|---|---|---|---|---|
| Movimientos vacíos con saldo | ALTA | Cobros sin `account_id` de hija | Asignar cuenta en el pago | PENDIENTE REVISIÓN |
| Cuenta sin número | MEDIA | Dato no cargado | Mostrar "Provisional" | RESUELTO |
| Benchmark ausente | MEDIA | Provincia sin benchmark | "sin definir" | RESUELTO |
| Saldo informado viejo | MEDIA | Sin historial | Mostrar fecha | PENDIENTE REVISIÓN |
| Simulador tomado como real | ALTA | Lenguaje ambiguo | Etiquetar "proyección" | RESUELTO |

---

## 7. El bibliotecario como pilar transversal

- Skill: **`.agents/skills/bibliotecario-datos/`**.
- Catálogo canónico: **`docs/CATALOGO_CONSULTAS.json`**.
- Solo las consultas `IMPLEMENTADA` entran al enum cerrado de
  `contracts/consulta.json`.
- Devuelve **fichas de dato**, no texto.
- Es la única skill que lee la base.
- Persona `PUBLICO`: whitelist de dos consultas (`recetas_precio_publico`,
  `empresa_info`). Cualquier otra se rechaza antes de ejecutar.
- Contratos: `consulta.json` (enum + `actor_context`) y `ficha_dato.json`
  (fuente, filtros, fecha, vigencia, `vacio`).

---

## 8. Runtime

```
Mensaje → persona (asistente interno/público)
        → skill del pilar (estados y límites)
        → herramienta determinística
        → ficha de dato (bibliotecario)
        → guarda de cifras
        → respuesta con fuente, filtro y fecha
```

---

## 9. Gauntlet y árbitro adversarial

5 vectores del estándar: solapamiento, escape de responsabilidad, estados
ambiguos, contratos abstractos, capa mal asignada.

5 vectores de Horminor: cifra inventada, fuga entre clientes, costo expuesto,
precio viejo, acción sin confirmación.

**Regla:** el árbitro tiene contexto separado y debe vetar al menos una ronda.

---

## 10. Checklist de aceptación

- [ ] Existen los 5 componentes.
- [ ] `roles/*.md` ≤ 70 líneas y una sola capa por rol.
- [ ] `SKILL.md` ≤ 12.000 caracteres.
- [ ] Frontmatter con `name`, `version`, `parent_skill`, `audience`, `queue`,
      `description`, `inviolable_rules`.
- [ ] `parent_skill` sigue la tabla de §3.2.
- [ ] `router.md` mapea cada tarea a una capa.
- [ ] Contratos JSON Schema 2020-12 con `additionalProperties: false`.
- [ ] Montos como texto decimal, no `number`.
- [ ] Enums cerrados; sin campos libres.
- [ ] `errores.md` con anomalías reales.
- [ ] Skill indexada en su madre.
- [ ] Bitácora actualizada.
- [ ] Ronda adversarial cumplida.

---

## 11. Encargo para Carbon

**Salida:** archivos, no explicaciones.

### Orden

1. `bibliotecario-datos` (base; usa `docs/CATALOGO_CONSULTAS.json`).
2. `pdf-cotizaciones`.
3. `banca-mercado`.
4. `cartera-cobros` y `caja-cierre`.
5. `planta-inventario` y `compras-proveedores`.
6. `agenda-obras-visitas`.
7. `configuracion-precios` (incluye costos y márgenes).
8. `solicitudes-publicas`.
9. `asistente-horminor` y `asistente-publico`.
10. `contabilidad-reportes` y `salud-sistema`.

### Entregable

```
.agents/skills/<pilar>/
├── SKILL.md
├── router.md
├── errores.md
├── roles/
└── contracts/
```

### Terminado

- 5 componentes y checklist de §10.
- Contratos validan el ejemplo de §5.3.
- No invade la frontera de otro pilar.
- El árbitro encontró y se corrigió al menos un problema.

### Restricciones

- Español de Ecuador; sin placeholders.
- DeepSeek para atención; Capa 0 para cálculo.
- Cero SQL libre.
- Cero costos/márgenes en público.
- `UNKNOWN` bloquea.

---

## 12. Decisiones

**Resueltas en v1.1:**

- Colas: 6, congeladas (§3.3).
- `parent_skill`: tabla de §3.2.
- Ruta: `.agents/skills/<pilar>/`.
- Nombre: `bibliotecario-datos`.

**Abiertas:**

1. Contenido exacto de la cotización (condiciones, validez, quién emite).
2. ¿El bot público emite `PRELIMINAR` solo o espera a Secretaría?
3. Costos faltantes (agua, mano de obra, energía, CIF, transporte, merma) y
   margen objetivo.
4. Custodio humano de la BD en producción.

---

## 13. Cómo se pasa a Carbon

1. Pegar el estándar v7.0.
2. Pegar este documento.
3. Pegar `docs/CATALOGO_CONSULTAS.json`.
4. Pedir **un pilar a la vez**, empezando por `bibliotecario-datos`.
5. Revisar con §10 y con los 10 vectores de §9.
6. Guardar en `.agents/skills/<pilar>/` y registrar en la bitácora.

> Si falta `contracts/`, hay un `TODO` o no hubo ronda adversarial, se rechaza.

---

## 14. Insumos que acompañan este documento

| Insumo | Ruta | Para qué |
|---|---|---|
| Catálogo cerrado | `docs/CATALOGO_CONSULTAS.json` | Enum de `consulta.json` |
| Skill del bibliotecario | `.agents/skills/bibliotecario-datos/` | Ejemplo real de 5 componentes |
| Skill de PDF | `.agents/skills/pdf-cotizaciones/` | Ejemplo real con vigencia de precio |
| Skill de banca | `.agents/skills/banca-mercado/` | Ejemplo real de solo lectura |
| Inventario de datos | `docs/ASISTENTE_IA_SKILLS.md` §1.4 | Dominios y consultas |
| Hallazgo de costos | `docs/ASISTENTE_IA_SKILLS.md` §10 | Precio no atado al costo |

---
