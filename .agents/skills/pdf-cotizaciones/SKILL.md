---
name: pdf-cotizaciones
version: 1.3.0
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
  - "Sin validez explícita no se emite: 15 días por defecto, configurable."
  - "Un precio PROVISIONAL no se emite fuera de SANDBOX."
  - "Un precio con vigencia_hash que no coincide con el vigente se rechaza."
  - "Los extras son un solo rubro global; los de costo interno no salen al cliente."
  - "Una cotización del bot público sin confirmar lleva marca PRELIMINAR."
  - "Bot, panel y secretaría usan el mismo endpoint; no hay tres generadores."
---

# 📄 SKILL: PDF de cotizaciones (v1.3)

## 1. Misión y límites

**Misión:** convertir una `solicitud_cotizacion` válida en un PDF con folio,
branding, validez y snapshot de precio.

**Hace:**
- Valida el contrato de entrada y la aritmética con `Decimal`.
- Verifica que el `vigencia_hash` de cada precio sea el vigente.
- Rechaza precios `PROVISIONAL` fuera de SANDBOX.
- Suma los extras solo si son `cobrable = true`.
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
- No cobra el excedente despachado: la medición es pactada.

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
  ├─ precio PROVISIONAL y entorno real
  │        └─ RECHAZADA (PRECIO_PROVISIONAL)
  ├─ total_esperado distinto
  │        └─ RECHAZADA (ARITMETICA_NO_CUADRA)
  ├─ actor sin permiso
  │        └─ RECHAZADA
  ├─ canal BOT y sin confirmación
  │        └─ PRELIMINAR
  ▼
EMITIDA                      (folio asignado + PDF guardado)
  ├─ ENVIADA                 (WhatsApp + media_assets en la carpeta del cliente)
  ├─ ACEPTADA                (etiqueta VENTA al cliente; habilita conversión)
  └─ ANULADA                 (solo con motivo y actor autorizado)
```

## 3. Tabla de navegación

| Componente | Ruta | Uso |
|---|---|---|
| Router de capas | `router.md` | Qué mecanismo resuelve cada tarea |
| Errores | `errores.md` | Anomalías y calibración |
| Armador | `roles/01_armador.md` | Valida líneas, extras, vigencia y aritmética |
| Emisor | `roles/02_emisor.md` | Permisos, folio y persistencia |
| Publicador | `roles/03_publicador.md` | Render, storage, WhatsApp y carpeta |
| Entrada | `contracts/solicitud_cotizacion.json` | JSON Schema 2020-12 |
| Salida | `contracts/cotizacion_emitida.json` | JSON Schema 2020-12 |

## 4. Reglas de datos

- Los montos viajan como **texto decimal** (`"20.5"`, `"118.00"`), nunca float.
- `cantidad_m3 > 0` y `precio_m3 >= 0`; `iva_pct` entre 0 y 30.
- `subtotal = cantidad_m3 × precio_m3` redondeado a 2 decimales.
- `subtotal_total = subtotal + suma(extras con cobrable = true)`.
- `iva = subtotal_total × iva_pct / 100`; `total = subtotal_total + iva`.
- Si llega `total_esperado`, debe coincidir con el total calculado.
- Cada línea exige `precio_ref.ficha_id` y `precio_ref.vigencia_hash`.
- La moneda es USD; no se aceptan otras.
- El folio es único e inmutable.
- `validez_dias` por defecto **15**; el rango válido es 1–90.

## 5. Extras: un solo rubro global

No hay categorías. Un extra es cualquier cosa ajena a Horminor que haya que
incluir para poder ejecutar el trabajo (retro para abrir paso, permiso, espera).
Se describe a mano.

| Campo | Regla |
|---|---|
| `descripcion` | obligatoria, texto libre, 3–200 caracteres |
| `monto` | texto decimal o `null` (solo nota, sin monto) |
| `cobrable` | `true` suma al cliente; `false` es costo interno |
| `nota` | opcional |

- Los `cobrable = true` se imprimen y suman al total.
- Los `cobrable = false` **no** se imprimen en la copia del cliente; solo en la
  copia interna marcada `USO INTERNO`.
- Un extra sin monto no altera la aritmética: es una advertencia, no un cobro.
- Al convertir a orden se copian únicamente los cobrables.

## 6. Validez y precio

- `valida_hasta = fecha_emision + validez_dias` (15 por defecto).
- Vencida la fecha, la cotización pasa a `VENCIDA`; se re-emite con versión
  nueva. No se “revive” cambiando la fecha.
- La lista de precios vive en `concrete_recipes.precio_m3` (Superadmin >
  formulas_y_precios). Esta skill no la edita ni la crea.
- `precio_estado = PROVISIONAL` significa semilla sin confirmar: no se emite
  fuera de SANDBOX. En SANDBOX el PDF lleva la marca visible
  **PRECIO PROVISIONAL**.
- `precio_estado = OFICIAL` es el único que puede llegar a un cliente real.

## 7. Envío y archivo

1. El emisor asigna folio y persiste la cotización.
2. El publicador renderiza y guarda el PDF.
3. El PDF se registra en `media_assets` con `cliente_id`,
   `tipo = 'DOCUMENTO'` y `etiquetas = ["COTIZACION"]`: queda en la carpeta del
   cliente, no en una carpeta paralela.
4. El canal envía por WhatsApp y devuelve `whatsapp_msg_id`.
5. Si el envío falla, la cotización queda `ENVIADA` con `canal_envio = PANEL` y
   el PDF archivado. El registro no se pierde.

## 8. Aceptación y etiqueta

- `ACEPTADA` solo la marca Julio o Secretaría, nunca Gato solo.
- Al aceptar se asigna la etiqueta **`VENTA`** al cliente (`cliente_etiquetas`).
- La etiqueta no crea orden ni contrato: la conversión es un paso explícito y
  posterior.
- Una cotización `VENCIDA` o `RECHAZADA` no se convierte.
