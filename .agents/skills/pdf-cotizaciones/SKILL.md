---
name: pdf-cotizaciones
version: 1.2.0
parent_skill: ["asistente-horminor", "asistente-publico"]
audience: AMBAS
queue: q_documentos
description: >
  Emite cotizaciones en PDF con folio, validez y snapshot de precio (cola
  q_documentos). No calcula precios ni lee clientes: recibe los datos del
  cotizador y solo valida aritmética, vigencia, permisos y plantilla. Frontera:
  no es factura y no comparte lógica con el asistente.
inviolable_rules:
  - "Una cotización no es una factura: se rotula COTIZACIÓN y no lleva datos SRI."
  - "El precio se congela al emitir: el ítem guarda el precio y su vigencia_hash."
  - "Sin validez explícita no se emite."
  - "Un precio con vigencia_hash que no coincide con el vigente se rechaza."
  - "Una cotización del bot público sin confirmar lleva marca PRELIMINAR."
  - "Bot, panel y secretaría usan el mismo endpoint; no hay tres generadores."
---

# 📄 SKILL: PDF de cotizaciones (v1.1)

## 1. Misión y límites

**Misión:** convertir una `solicitud_cotizacion` válida en un PDF con folio,
branding, validez y snapshot de precio.

**Hace:**
- Valida el contrato de entrada y la aritmética con `Decimal`.
- Verifica que el `vigencia_hash` de cada precio sea el vigente.
- Verifica permisos del actor.
- Asigna folio atómico por año (`COT-2026-000123`).
- Renderiza la plantilla `cotizacion_v1`.
- Guarda el PDF (Bunny o volumen local) y devuelve `pdf_url`.

**No hace:**
- No calcula precios ni decide si el margen es bueno.
- No busca clientes ni lee `clients`.
- No decide disponibilidad ni agenda.
- No es factura ni proforma electrónica (SRI fuera de alcance).
- No envía el PDF por WhatsApp: eso lo hace el canal que lo pidió.

## 2. Máquina de estados

```
RECIBIDA
  ├─ falta dato crítico (cliente, línea, precio, IVA, validez)
  │        └─ CUARENTENA (no se emite; se devuelve el campo faltante)
  ├─ contrato inválido
  │        └─ RECHAZADA
  ▼
VALIDADA                     (JSON Schema + Decimal + vigencia_hash)
  ├─ precio caducado
  │        └─ RECHAZADA (PRECIO_CADUCADO)
  ├─ total_esperado distinto
  │        └─ RECHAZADA (ARITMETICA_NO_CUADRA)
  ├─ actor sin permiso
  │        └─ RECHAZADA
  ├─ canal BOT y sin confirmación
  │        └─ PRELIMINAR
  ▼
EMITIDA                      (folio asignado + PDF guardado)
  ├─ ACEPTADA
  └─ ANULADA                  (solo con motivo y actor autorizado)
```

## 3. Tabla de navegación

| Componente | Ruta | Uso |
|---|---|---|
| Router de capas | `router.md` | Qué mecanismo resuelve cada tarea |
| Errores | `errores.md` | Anomalías y calibración |
| Armador | `roles/01_armador.md` | Valida líneas, vigencia y aritmética |
| Emisor | `roles/02_emisor.md` | Permisos, folio y persistencia |
| Publicador | `roles/03_publicador.md` | Guarda el PDF y devuelve URL |
| Entrada | `contracts/solicitud_cotizacion.json` | JSON Schema 2020-12 |
| Salida | `contracts/cotizacion_emitida.json` | JSON Schema 2020-12 |

## 4. Reglas de datos

- Los montos viajan como **texto decimal** (`"20.5"`, `"118.00"`), nunca float.
- `cantidad_m3 > 0` y `precio_m3 >= 0`; `iva_pct` entre 0 y 30.
- `subtotal = cantidad_m3 × precio_m3` redondeado a 2 decimales.
- `iva = subtotal × iva_pct / 100`; `total = subtotal + iva`.
- Si llega `total_esperado`, debe coincidir con el total calculado.
- Cada línea exige `precio_ref.ficha_precio_id` y `precio_ref.vigencia_hash`.
- La moneda es USD; no se aceptan otras.
- El folio es único e inmutable.
