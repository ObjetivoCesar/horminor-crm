# Cotizaciones — v6.21

> **Estado:** migración **080** aplicada; API de alta, edición, aceptación y
> conversión implementada; vista **Cotizaciones** en la columna izquierda con
> permiso ACL aprobable desde Superadmin. PDF, WhatsApp y Gato quedan para
> Q4/Q5. Los precios, extras y condiciones los define Julio; el sistema no
> inventa ninguno. El texto legal del contrato sigue sujeto a revisión
> (`docs/CONTRATOS.md`).
>
> **Decisión de aprobación (2026-11-13):** “aprobable desde Superadmin” se
> implementó como **permiso del módulo** en el checklist de perfiles. La
> aprobación transaccional de cada cotización no se activó; si Julio la pide, se
> agrega un estado `PENDIENTE_APROBACION` sin rehacer la tabla.

## 1. Por qué existe

Julio cotiza en la oficina o en la obra. A veces hay rubros que **no se cobran
pero se gastan**: “uso de retro para abrir paso para entrar con el mixer”. Hoy
eso vive en la cabeza, en un WhatsApp o en un papel.

La cotización es el documento que ordena toda la cadena comercial. De ella
salen la etiqueta de venta, el contrato, la orden, el despacho y la factura. Se
crea desde el panel (Secretaría o Julio) o desde Gato.

## 2. Cadena documental

```
Cotización -> (aceptada) -> etiqueta VENTA en el cliente
            -> Contrato (opcional) -> Orden -> Despacho -> Factura
```

| Documento | Qué fija | Qué no hace |
|---|---|---|
| **Cotización** | volumen, resistencia, precio/m³, extras, validez | no compromete la producción |
| **Etiqueta `VENTA`** | el cliente queda marcado como venta ganada | no crea orden ni cobra |
| **Contrato** | formaliza la cotización aceptada; firma Julio | no ejecuta |
| **Orden** | volumen pactado, resistencia, precio, extras cobrables | no cobra el excedente |
| **Despacho** | volumen real, mixer, chofer | no cambia lo pactado |
| **Factura** | cobra lo pactado + extras cobrables | no cobra el excedente |

Decisiones cerradas con Julio:

1. **Primero la cotización.** Cuando el cliente aprueba, el cliente recibe la
   etiqueta **`VENTA`** y desde ahí se habilita la orden o el contrato.
2. **La etiqueta no crea la orden.** Aceptar una cotización no debe producir una
   orden fantasma si al final no se despacha. La conversión es un paso explícito.
3. **El contrato es opcional.** No toda venta necesita contrato; **toda venta sí
   pasa primero por cotización**, y la cotización y la orden son obligatorias
   para ejecutar.

## 3. Modelo de datos

### 3.1 `cotizaciones`

| Campo | Tipo | Regla |
|---|---|---|
| `id` | uuid | PK |
| `numero` | text | único: `HORM-COT-AAAA-0001` |
| `cliente_id` | uuid | obligatorio |
| `obra_direccion` | text | obligatoria |
| `volumen_m3` | numeric | obligatorio; 10 m³ es un ejemplo |
| `resistencia` | text | `NULL` = cualquiera del catálogo |
| `precio_m3` | numeric | obligatorio para enviar; `NULL` = pendiente |
| `precio_estado` | text | `PROVISIONAL` / `OFICIAL`; ver 3.6 |
| `incluye_equipo` | boolean | `true` |
| `incluye_bombeo` | boolean | `true` |
| `acceso_notas` | text | “retro para abrir paso”, etc. |
| `forma_pago` | text | `EFECTIVO`, `TRANSFERENCIA`, `ABONO`, `FIADO` |
| `valida_hasta` | date | `fecha_emision + validez_dias` (15 por defecto) |
| `estado` | text | `BORRADOR`, `ENVIADA`, `ACEPTADA`, `RECHAZADA`, `VENCIDA`, `CONVERTIDA` |
| `version` | integer | empieza en 1 |
| `subtotal` | numeric | volumen × precio + extras cobrables |
| `iva_pct` / `iva_monto` / `total` | numeric | IVA según la configuración vigente |
| `pdf_media_id` | uuid | FK `media_assets` |
| `enviada_at` / `enviada_por` | timestamptz / text | cuándo y quién la mandó |
| `canal_envio` | text | `WHATSAPP`, `IMPRESA`, `PANEL` |
| `whatsapp_msg_id` | text | id del mensaje saliente, si aplica |
| `aceptada_at` / `convertida_at` | timestamptz | trazabilidad |
| `orden_id` / `contrato_id` | uuid | lo que generó al convertir |
| `origen` | text | `PANEL`, `GATO`, `OBRA` |
| `creado_por` / `aprobado_por` | text | trazabilidad |
| `notas` | text | libre |
| `created_at` / `updated_at` | timestamptz | |

### 3.2 `cotizacion_extras` — un solo rubro

**No hay categorías.** Julio lo pidió así: un único rubro **global** para
cualquier cosa ajena a Horminor que haya que incluir para poder hacer el
trabajo. Distancia, acceso, espera, retro, permiso municipal: todo entra en la
misma línea con descripción libre.

| Campo | Tipo | Regla |
|---|---|---|
| `id` | uuid | PK |
| `cotizacion_id` | uuid | FK |
| `descripcion` | text | obligatoria, texto libre: “uso de retro para abrir paso” |
| `monto` | numeric | `NULL` = solo nota, sin monto |
| `cobrable` | boolean | `false` por defecto: costo interno |
| `nota` | text | ampliación |
| `orden` | integer | orden de impresión |

| Tipo | `cobrable` | Suma al cliente | Suma al costo | Se imprime al cliente |
|---|---|---|---|---|
| Extra cobrable | `true` | sí | no | sí |
| Costo interno | `false` | no | sí (si hay monto) | **no** |

El ejemplo de Julio —retro para abrir paso— es `cobrable = false`: se gasta, no
se cobra, y debe verse en la copia interna. Si algún día decide cobrarlo, cambia
el checkbox y pasa al total.

Una sola tabla, un solo rubro. Agregar categorías después es barato; quitarlas
cuando ya hay datos cargados, no.

### 3.3 `cotizacion_versiones`

Cada envío o cambio de precio genera una versión con snapshot, hash y PDF. La
versión **aceptada** es la que se convierte en contrato u orden. Las anteriores
quedan inmutables.

### 3.4 `orden_extras`

Al convertir una cotización se copian **solo** los extras cobrables. La orden
mantiene su `total` base (volumen × precio) y una vista `v_orden_total` suma los
extras. La factura usa esa vista. Así el extra no se esconde dentro del precio
por m³.

### 3.5 `cliente_etiquetas`

| Campo | Tipo | Regla |
|---|---|---|
| `id` | uuid | PK |
| `cliente_id` | uuid | FK |
| `etiqueta` | text | `VENTA`, `PROSPECTO`, `RECURRENTE`, `MOROSO`... |
| `origen` | text | `COTIZACION`, `MANUAL`, `COBRANZA` |
| `origen_id` | uuid | cotización que la generó, si aplica |
| `created_at` | timestamptz | |

- `VENTA` se asigna **automáticamente** cuando una cotización pasa a `ACEPTADA`.
- Las demás son manuales. `MOROSO` la pondrá Cobranza cuando exista la regla.
- Una etiqueta no borra historial: se agrega, no se reemplaza.

### 3.6 Lista de precios (Superadmin)

La lista **ya existe**: `concrete_recipes.precio_m3` + `iva_pct`, editable en
**Superadmin > formulas_y_precios**. No se crea otra tabla de precios.

Hoy esos valores son semilla provisional. Para que un precio ficticio no llegue
a un cliente real se agrega:

| Campo | Tipo | Regla |
|---|---|---|
| `precio_estado` | text | `PROVISIONAL` (default) / `OFICIAL` |

Regla dura:

- `PROVISIONAL` **no emite** cotización fuera de SANDBOX. Devuelve
  `PRECIO_PROVISIONAL` y pide a Julio marcarlo como `OFICIAL`.
- En SANDBOX se emite con marca visible **“PRECIO PROVISIONAL”** para que nadie
  confunda una prueba con una oferta.
- Julio puede cargar valores ficticios hoy y cambiarlos en Superadmin sin tocar
  código. Eso es exactamente lo que pidió, con un candado para que no se
  escape a producción.

### 3.7 `system_settings`

| Llave | Valor inicial | Para qué |
|---|---|---|
| `cotizaciones.validez_dias` | `15` | modificable por Julio |
| `cotizaciones.excedente_alerta_pct` | `NULL` | umbral para avisar si el despacho excede mucho lo pactado |
| `cotizaciones.envio` | `{"canal":"WHATSAPP","archivar_en_cliente":true}` | envío y carpeta |

No hay `categorias_extras`: el rubro es uno solo.

## 4. Medición y excedente

La cotización y el contrato cobran **el volumen pactado**. El despacho suele
llevar un poco más; ese excedente **no se cobra**.

- `excedente_m3 = max(volumen_despachado - volumen_pactado, 0)`
- `costo_excedente = excedente_m3 × costo_m3` si el costo está disponible.
- Si no hay costo, se muestran los m³ y “costo sin dato”.
- Si se despacha menos, también se cobra lo pactado.

No es un detalle contable: es una **fuga de margen**. Si siempre se manda un
poco más, el costo real por m³ es mayor que el precio. El tablero lo muestra, no
lo esconde.

## 5. Estados y permisos

| Estado | Quién | Qué pasa |
|---|---|---|
| `BORRADOR` | Secretaría, Julio, Gato | se puede editar |
| `ENVIADA` | Secretaría, Julio; Gato con ratificación | se congela la versión y el PDF |
| `ACEPTADA` | Julio o Secretaría | se congela, etiqueta `VENTA` al cliente, habilita conversión |
| `RECHAZADA` / `VENCIDA` | — | cerrada, no convierte |
| `CONVERTIDA` | Julio o Secretaría | genera contrato y/u orden |

Reglas duras:

- **Precio:** Secretaría usa la lista; **solo Julio** lo cambia a mano. Sin
  precio, la cotización queda en `BORRADOR`.
- **Gato** crea borradores y consulta; no aprueba, no cambia precios y no
  convierte sin un “sí” humano.
- Toda cotización guarda `creado_por` y `origen`.
- Una cotización `VENCIDA` no se convierte. Se re-emite (versión nueva), no se
  “revive” cambiando la fecha.

## 6. Envío por WhatsApp y carpeta del cliente

Decisión de Julio: **se envía por WhatsApp en PDF y queda registrado en la
carpeta del cliente.**

1. Se renderiza el PDF (mismo patrón que la factura interna).
2. Se guarda en `media_assets` con `cliente_id`, `tipo = 'DOCUMENTO'`,
   `storage_path` en la carpeta del cliente y `etiquetas = ["COTIZACION"]`.
   El archivo aparece en la carpeta forense de Secretaría, junto a fotos y
   comprobantes. No hay una carpeta paralela.
3. Se envía por el canal de WhatsApp existente.
4. Se guarda `enviada_at`, `enviada_por`, `canal_envio` y `whatsapp_msg_id`.

Si WhatsApp falla, la cotización queda `ENVIADA` con `canal_envio = PANEL` y el
PDF archivado: el registro no se pierde aunque el mensaje no salga.

## 7. Gato

Ejemplo:

> “Cotiza 15 m³ FC-210 para Constructora X, con retro para abrir paso”

Gato:

1. Identifica cliente y obra.
2. Usa el precio de la lista; si es `PROVISIONAL` o falta, pregunta. **No
   inventa.**
3. Agrega el extra como `cobrable = false` con descripción libre.
4. Deja el borrador y pide los datos que falten en una sola frase.
5. Para enviarla, muestra el PDF y espera “sí”.

Reutiliza el patrón de recordatorios: borrador → ratificación → envío. No se
inventa un flujo nuevo.

## 8. PDF

**Copia del cliente:** número, fecha, cliente, obra, volumen, resistencia,
precio/m³, equipo y bombeo incluidos, extras cobrables, subtotal, IVA, total,
validez (15 días), forma de pago y firma.

**Copia interna:** la misma, más los extras de costo interno, el excedente
despachado y el margen estimado. Marcada `USO INTERNO`.

Ambas con número, versión y hash.

## 9. Tablero

Dos indicadores, sin inflar el dashboard:

1. **Cotizaciones abiertas** (`BORRADOR` + `ENVIADA`): cantidad y valor. Es
   pipeline, no ingreso.
2. **Excedente despachado:** m³ de más y su costo. Es fuga de margen.

Van en la franja de resumen o en Cobranza, no como pestaña nueva.

## 10. Preguntas abiertas

Cerradas el 2026-11-13:

1. **Toda venta pasa primero por cotización.** No hay orden sin cotización
   previa. La cotización aceptada habilita la etiqueta `VENTA` y la conversión.
2. **La lista de precios está en Superadmin** (`concrete_recipes.precio_m3`).
   Hoy los valores son ficticios y van marcados `PROVISIONAL`; Julio los
   reemplazará en la reunión. Serán variables.
3. **El IVA se muestra desglosado** (subtotal, IVA, total) en la cotización y en
   la factura.

Sigue abierta:

4. ¿La lista lleva un valor por resistencia o uno solo por planta?

## 11. Fases

| Fase | Qué | Criterio |
|---|---|---|
| Q1 | Revisión de este documento con Julio | cerrada: extras, validez, envío y etiqueta definidos |
| Q2 | Migración 080: `cotizaciones`, `cotizacion_extras`, `cotizacion_versiones`, `orden_extras`, `cliente_etiquetas`, `precio_estado`, settings | Esquema aplicado, precios `PROVISIONAL` donde falta |
| Q3 | API: alta, edición, envío, aceptación, conversión | Tests de estados; no se convierte una vencida |
| Q4 | PDF cliente e interno + WhatsApp + `media_assets` | Cotización de prueba con hash, visible en la carpeta del cliente |
| Q5 | Gato: borrador, consulta y envío con ratificación | Un mensaje + “sí” = PDF enviado |
| Q6 | Pestaña en el panel (Secretaría/Julio) | Se crea y convierte sin salir del panel |
| Q7 | Indicadores en el tablero | Pipeline y excedente visibles |

**Secuencia:** primero se cierra la fase 2 del dashboard (endpoints) y la
pestaña Ocupación. Después Q2–Q4. La cotización va **antes** que el contrato: el
contrato es la cotización aceptada. Si se construye al revés, se duplican campos
y luego hay que refactorizar.

## 12. Implementación actual (2026-11-13)

| Pieza | Estado |
|---|---|
| Migración 080 (`cotizaciones`, `cotizacion_extras`, `cotizacion_versiones`, `orden_extras`, `cliente_etiquetas`, `precio_estado`) | aplicada |
| `POST /api/v1/cotizaciones` | crea borrador, calcula IVA y versión 1 |
| `GET /api/v1/cotizaciones` / `/{id}` | bandeja y detalle |
| `PUT /api/v1/cotizaciones/{id}` | solo `BORRADOR`; crea versión nueva |
| `POST /api/v1/cotizaciones/{id}/aceptar` | `ACEPTADA` + etiqueta `VENTA` |
| `POST /api/v1/cotizaciones/{id}/convertir` | crea orden con `crear_orden` y copia extras cobrables |
| Vista **Cotizaciones** | columna izquierda, bandeja + detalle + formulario |
| ACL | módulo `cotizaciones`; Superadmin lo aprueba por perfil |
| PDF / WhatsApp / Gato | pendientes (Q4/Q5) |

**Límite conocido:** la orden conserva su total base; los extras cobrables viven
en `orden_extras` y la vista `v_orden_total` los suma. La factura/cartera que
use `orders.total` no los incluye todavía. Se cierra cuando se conecte la
factura a `v_orden_total`.
