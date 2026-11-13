# Cotizaciones — propuesta v6.19

> **Estado:** propuesta de diseño. Los precios, extras y categorías los define
> Julio; el sistema no inventa ninguno. El texto legal del contrato que salga de
> una cotización sigue sujeto a revisión (`docs/CONTRATOS.md`).

## 1. Por qué existe

Julio cotiza en la oficina o en la obra. A veces hay rubros que **no se cobran
pero se gastan**: “uso de retro para abrir paso para entrar con el mixer”. Hoy
eso vive en la cabeza, en un WhatsApp o en un papel.

La cotización es el documento que ordena toda la cadena comercial. De ella
salen el contrato, la orden, el despacho y la factura. Y debe poder crearse
desde el panel (Secretaría o Julio) o desde Gato.

## 2. Cadena documental

```
Cotización -> (aceptada) -> Contrato (opcional) -> Orden -> Despacho -> Factura
```

| Documento | Qué fija | Qué no hace |
|---|---|---|
| **Cotización** | volumen, resistencia, precio/m³, extras, validez | no compromete la producción |
| **Contrato** | formaliza la cotización aceptada; firma Julio | no ejecuta |
| **Orden** | volumen pactado, resistencia, precio, extras cobrables | no cobra el excedente |
| **Despacho** | volumen real, mixer, chofer | no cambia lo pactado |
| **Factura** | cobra lo pactado + extras cobrables | no cobra el excedente |

El contrato es **opcional**: no toda venta de 10 m³ necesita contrato. La
cotización y la orden sí son obligatorias para ejecutar.

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
| `incluye_equipo` | boolean | `true` |
| `incluye_bombeo` | boolean | `true` |
| `distancia_km` | numeric | `NULL` si no aplica |
| `acceso_notas` | text | “retro para abrir paso”, etc. |
| `forma_pago` | text | `EFECTIVO`, `TRANSFERENCIA`, `ABONO`, `FIADO` |
| `valida_hasta` | date | `NULL` hasta definir |
| `estado` | text | `BORRADOR`, `ENVIADA`, `ACEPTADA`, `RECHAZADA`, `VENCIDA`, `CONVERTIDA` |
| `version` | integer | empieza en 1 |
| `subtotal` | numeric | volumen × precio + extras cobrables |
| `iva_pct` / `iva_monto` / `total` | numeric | IVA según la configuración vigente |
| `pdf_media_id` | uuid | FK `media_assets` |
| `origen` | text | `PANEL`, `GATO`, `OBRA` |
| `creado_por` / `aprobado_por` | text | trazabilidad |
| `notas` | text | libre |
| `created_at` / `updated_at` | timestamptz | |

### 3.2 `cotizacion_extras`

| Campo | Tipo | Regla |
|---|---|---|
| `id` | uuid | PK |
| `cotizacion_id` | uuid | FK |
| `descripcion` | text | obligatoria; texto libre |
| `categoria` | text | `DISTANCIA`, `ACCESO`, `BOMBEO`, `ESPERA`, `OTRO` |
| `monto` | numeric | `NULL` = solo nota, sin monto |
| `cobrable` | boolean | `false` por defecto: costo interno |
| `nota` | text | ampliación |
| `orden` | integer | orden de impresión |

**Dos naturalezas, no una:**

| Tipo | `cobrable` | Suma al cliente | Suma al costo | Se imprime al cliente |
|---|---|---|---|---|
| Extra cobrable | `true` | sí | no | sí |
| Costo interno | `false` | no | sí (si hay monto) | no |

El ejemplo de Julio —retro para abrir paso— es `cobrable = false`: se gasta,
no se cobra, y debe verse en la copia interna. Si algún día decide cobrarlo,
cambia el checkbox y pasa al total.

### 3.3 `cotizacion_versiones`

Cada envío o cambio de precio genera una versión con snapshot, hash y PDF. La
versión **aceptada** es la que se convierte en contrato u orden. Las anteriores
quedan inmutables.

### 3.4 `orden_extras`

Al convertir una cotización, se copian solo los extras **cobrables**. La orden
mantiene su `total` base (volumen × precio) y una vista `v_orden_total` suma
los extras. La factura usa esa vista. Así el extra no se esconde dentro del
precio por m³.

### 3.5 `system_settings`

| Llave | Valor inicial | Para qué |
|---|---|---|
| `cotizaciones.validez_dias` | `NULL` | días de validez; lo define Julio |
| `cotizaciones.categorias_extras` | `["DISTANCIA","ACCESO","BOMBEO","ESPERA","OTRO"]` | lista editable |
| `cotizaciones.excedente_alerta_pct` | `NULL` | umbral para avisar si el despacho excede mucho lo pactado |

## 4. Medición y excedente

La cotización y el contrato cobran **el volumen pactado**. El despacho suele
llevar un poco más; ese excedente **no se cobra**.

- `excedente_m3 = max(volumen_despachado - volumen_pactado, 0)`
- `costo_excedente = excedente_m3 × costo_m3` si el costo está disponible.
- Si no hay costo, se muestran los m³ y “costo sin dato”.
- Si se despacha menos, también se cobra lo pactado.

Esto no es un detalle contable: es una **fuga de margen**. Si siempre se manda
un poco más, el costo real por m³ es mayor que el precio. El tablero debe
mostrarlo, no esconderlo.

## 5. Estados y permisos

| Estado | Quién | Qué pasa |
|---|---|---|
| `BORRADOR` | Secretaría, Julio, Gato | se puede editar |
| `ENVIADA` | Secretaría, Julio; Gato con ratificación | se congela la versión enviada |
| `ACEPTADA` | Julio o Secretaría | se congela y habilita conversión |
| `RECHAZADA` / `VENCIDA` | — | cerrada, no convierte |
| `CONVERTIDA` | Julio o Secretaría | genera contrato y/u orden |

Reglas duras:

- **Precio:** Secretaría puede usar la lista; **solo Julio** puede cambiarlo a
  mano. Si no hay precio, la cotización queda en `BORRADOR`.
- **Gato** crea borradores y consulta, pero no aprueba, no cambia precios y no
  convierte sin un “sí” humano.
- Toda cotización guarda `creado_por` y `origen`.

## 6. Gato

Ejemplo:

> “Cotiza 15 m³ FC-210 para Constructora X, con retro para abrir paso”

Gato:

1. Identifica cliente y obra.
2. Usa el precio de la lista; si no hay, pregunta. **No inventa.**
3. Agrega el extra como `cobrable = false` y `categoria = ACCESO`.
4. Deja el borrador y pide los datos que falten en una sola frase.
5. Para enviarla, muestra el PDF y espera “sí”.

Reutiliza el patrón de recordatorios: borrador → ratificación → envío. No se
inventa un flujo nuevo.

## 7. PDF

**Copia del cliente:** número, fecha, cliente, obra, volumen, resistencia,
precio/m³, equipo y bombeo incluidos, extras cobrables, subtotal, IVA, total,
validez, forma de pago y firma.

**Copia interna:** la misma, más los extras de costo interno, el excedente
despachado y el margen estimado. Marcada `USO INTERNO`.

Ambas con número, versión y hash.

## 8. Tablero

Dos indicadores, sin inflar el dashboard:

1. **Cotizaciones abiertas** (`BORRADOR` + `ENVIADA`): cantidad y valor. Es
   pipeline, no ingreso.
2. **Excedente despachado:** m³ de más y su costo. Es fuga de margen.

Van en la franja de resumen o en Cobranza, no como pestaña nueva.

## 9. Preguntas abiertas

1. ¿Cuántos días vale una cotización?
2. ¿Qué categorías de extras usa Julio además de distancia y acceso?
3. ¿Toda venta pasa por cotización o solo cuando el cliente la pide?
4. ¿La cotización se envía por WhatsApp con PDF o solo se imprime?
5. ¿El precio de la lista es por resistencia y planta, o único?

## 10. Fases

| Fase | Qué | Criterio |
|---|---|---|
| Q1 | Revisión de este documento con Julio | Categorías y validez definidas |
| Q2 | Migración 080: `cotizaciones`, `cotizacion_extras`, `cotizacion_versiones`, `orden_extras`, settings | Esquema aplicado, precios `NULL` donde falta |
| Q3 | API: alta, edición, envío, aceptación, conversión | Tests de estados; no se convierte una vencida |
| Q4 | PDF cliente e interno | Cotización de prueba con hash |
| Q5 | Gato: borrador, consulta y envío con ratificación | Un mensaje + “sí” = PDF enviado |
| Q6 | Pestaña en el panel (Secretaría/Julio) | Se crea y convierte sin salir del panel |
| Q7 | Indicadores en el tablero | Pipeline y excedente visibles |

**Secuencia:** primero se cierra la fase 2 del dashboard (endpoints) y la
pestaña Ocupación. Después Q1–Q2. La cotización va **antes** que el contrato:
el contrato es la cotización aceptada. Si se construye al revés, se duplican
campos y luego hay que refactorizar.
