# Contratos de suministro y personal — propuesta v6.19

> **Estado:** propuesta de diseño. No es un contrato válido ni asesoría legal.
> El texto legal base debe revisarlo un abogado laboral o la contadora antes de
> imprimir el primer contrato real. Las cifras (precio, salario, tarifas) quedan
> `NULL` hasta que Julio las cargue o salgan de una orden.

## 1. Principio: el sistema es la fuente

Julio lo dijo así: *“se crean aquí en digital y se imprimen, pero nosotros somos
la fuente”*. Eso fija tres reglas:

1. **El contrato nace en el sistema**, no en un Word aparte.
2. **El impreso es una foto**: lleva número, versión y hash del contenido.
3. **Un contrato activo no se edita.** Si cambia el precio, el volumen, el
   salario o el cargo, se crea una **versión nueva** (adenda) con su motivo. La
   anterior queda inmutable y sigue siendo la que se firmó.

## 2. Dos contratos distintos

| Tipo | Qué es | Firma |
|---|---|---|
| **SUMINISTRO** | El cliente compra hormigón **por m³**, de cualquiera de las especificaciones del catálogo. HORMINOR prepara, entrega y **incluye máquina y bombeo**. No incluye colocación, vibrado ni curado. | Julio |
| **TRABAJO** | Personal con **salario mensual**, anticipos de ley y horas extra según contrato. | Julio |

**Regla de firma:** Secretaría prepara el borrador; **solo Julio** lo pasa a
`ACTIVO`. Se controla en la API y en el botón del panel, no en un comentario.

## 3. Modelo de datos

Una sola tabla `contratos` con `tipo` y un `datos` JSONB para lo específico.
Dos tablas separadas llenarían todo de columnas `NULL`; para documentos, un
discriminador es más honesto.

### 3.1 `contratos`

| Campo | Tipo | Regla |
|---|---|---|
| `id` | uuid | PK |
| `numero` | text | único: `HORM-CS-AAAA-0001` / `HORM-CT-AAAA-0001` |
| `tipo` | text | `SUMINISTRO` / `TRABAJO` |
| `cliente_id` | uuid | obligatorio si `SUMINISTRO` |
| `personal_id` | uuid | obligatorio si `TRABAJO` |
| `fecha_inicio` | date | obligatoria |
| `fecha_fin` | date | `NULL` si indefinido |
| `estado` | text | `BORRADOR`, `ACTIVO`, `FINALIZADO`, `ANULADO` |
| `version` | integer | empieza en 1 |
| `contenido_hash` | text | SHA-256 del HTML/PDF renderizado |
| `pdf_media_id` | uuid | FK `media_assets` |
| `firmado_por` | text | solo `JULIO` al activar |
| `datos` | jsonb | campos del tipo |
| `creado_por` | text | usuario del panel |
| `created_at` / `updated_at` | timestamptz | |

Restricción:

```
(tipo = 'SUMINISTRO' AND cliente_id IS NOT NULL AND personal_id IS NULL)
OR
(tipo = 'TRABAJO'    AND personal_id IS NOT NULL AND cliente_id IS NULL)
```

### 3.2 `datos` de SUMINISTRO

| Campo | Tipo | Regla |
|---|---|---|
| `orden_id` | uuid | `NULL` si se crea manual; si existe, precarga todo |
| `volumen_m3` | numeric | obligatorio; **10 m³ es un ejemplo, no un paquete fijo** |
| `precio_m3` | numeric | obligatorio; sale de la orden o lo carga Julio |
| `resistencia` | text | `NULL` = cualquiera del catálogo |
| `incluye_equipo` | boolean | `true` por defecto |
| `incluye_bombeo` | boolean | `true` por defecto |
| `direccion_obra` | text | obligatoria |
| `forma_pago` | text | `EFECTIVO`, `TRANSFERENCIA`, `ABONO`, `FIADO` |
| `plazo_entrega` | text | fecha o ventana |
| `medicion` | text | `PACTADO` — se cobra el volumen acordado; el excedente despachado es costo, no cobro |
| `extras` | jsonb | rubro **global** manual: descripción libre, monto, `cobrable`. Sin categorías. Ver `docs/COTIZACIONES.md` |

El total del contrato es `volumen_m3 * precio_m3` (más IVA si aplica). Se
congela al firmar.

La medición es **pactada**: se cobra el volumen acordado. Si se despacha un
poco más —que es lo habitual—, ese excedente se registra como costo/merma y
**no se le cobra al cliente**. La diferencia se ve en el tablero, no en la
factura. Si se despacha menos, también se cobra lo pactado.

### 3.3 `datos` de TRABAJO

| Campo | Tipo | Regla |
|---|---|---|
| `tipo_contrato` | text | `OBRA_CIERTA` — cerrado con Julio el 2026-11-13 |
| `cargo` | text | obligatorio |
| `jornada_horas_semana` | numeric | `NULL` hasta cargar |
| `horario` | jsonb | `{"entrada":"07:00","salida":"17:00","dias":[...]}` |
| `salario_base` | numeric | mensual, `NULL` hasta cargar |
| `modalidad_pago` | text | `MENSUAL`, con **anticipos** durante la obra y **saldo final** al cierre |
| `horas_extra_modo` | text | `POR_HORA`, `MONTO_FIJO`, `NO_APLICA` |
| `tarifa_hora_extra` | numeric | `NULL` hasta cargar |
| `anticipos_permitidos` | boolean | `true` (de ley) |

### 3.4 `anticipos_salario`

| Campo | Tipo |
|---|---|
| `id` | uuid |
| `contrato_id` | uuid |
| `fecha` | date |
| `monto` | numeric |
| `motivo` | text |
| `autorizado_por` | text (Julio o Secretaría) |
| `estado` | `PENDIENTE`, `DESCONTADO`, `ANULADO` |
| `created_at` | timestamptz |

El límite y la forma de descuento (siguiente salario o cuotas) quedan
configurables. **No se hardcodea el porcentaje de ley.**

### 3.5 `contrato_versiones`

Cada versión guarda el snapshot, el hash y el PDF. La versión 1 es el contrato
original; las siguientes son adendas, renovaciones, correcciones o terminación.

### 3.6 `jornada_eventos` (horas extra)

Persona, contrato, fecha, inicio, fin, minutos, tipo, orden, mixer, motivo,
`autorizado_por`. El dinero no se guarda: se calcula al reportar solo si la
tarifa del contrato no es `NULL`.

### 3.7 `system_settings`

| Llave | Valor inicial | Para qué |
|---|---|---|
| `personal.jornada` | `{"entrada":"07:00","salida":"17:00","dias":["LUN","MAR","MIE","JUE","VIE","SAB"]}` | línea base de horas extra |
| `personal.horas_extra` | `{"requiere_autorizacion":true,"autorizadores":["SECRETARIA","JULIO"]}` | quién aprueba |

La tarifa no va acá: es por contrato.

## 4. Ciclo de vida

```
BORRADOR -> (vista previa) -> ACTIVO (versión 1, hash, PDF, firma Julio)
ACTIVO -> ADENDA (versión 2, 3...) -> ACTIVO
ACTIVO -> FINALIZADO (fin de vigencia o terminación)
BORRADOR -> ANULADO (nunca se firmó)
```

- Un contrato `ACTIVO` no se edita. Se versiona.
- El `numero` no cambia nunca.
- El hash se calcula sobre el contenido renderizado, no sobre la base.
- Si el PDF no coincide con el hash, el impreso no es válido.

## 5. Contrato de suministro (base a revisar)

Una página, generada desde una orden cuando existe:

1. Comparecientes.
2. Objeto: suministro de hormigón premezclado **por m³**, con equipo y bombeo
   incluidos; preparación y entrega por HORMINOR.
3. Volumen, resistencia (o “cualquiera del catálogo”) y precio por m³.
4. Forma de pago y plazo.
5. Lugar de entrega y contacto en obra.
6. Medición: se cobra el volumen pactado. El excedente despachado no se cobra.
7. Extras: solo los rubros marcados como cobrables. Los de costo interno no se
   imprimen en la copia del cliente.
8. Exclusión: no incluye colocación, vibrado ni curado, salvo pacto escrito.
9. Calidad y muestras: `[REVISAR]`.
10. Terminación y firma de Julio.

## 6. Contrato de trabajo (base a revisar)

1. Comparecientes.
2. Cargo y funciones.
3. Jornada y horario.
4. Salario mensual y modalidad de pago.
5. Anticipos de ley: forma de solicitud y descuento.
6. Horas extra: modalidad, autorización y cálculo.
7. Obligaciones, confidencialidad y terminación.
8. Firma de Julio.

## 7. Impresión

- Mismo patrón que la factura interna: HTML -> PDF.
- Encabezado: HORMINOR, número, versión, fecha.
- Pie: hash corto, página, “Documento generado por el sistema”.
- El PDF se guarda en `media_assets` y queda enlazado a la versión.

## 8. Preguntas abiertas

Cerrada el 2026-11-13: **contrato de trabajo de obra cierta**, con anticipos
durante la obra y saldo final al cierre. El porcentaje del anticipo sigue
pendiente de Julio.

Siguen abiertas:

1. **Porcentaje de anticipo** y forma de descuento contra el saldo final.
2. **Cotización previa:** toda venta pasa primero por cotización (cerrado); la
   pregunta que queda es si el contrato de suministro se firma siempre o solo
   cuando el cliente lo pide. Ver `docs/COTIZACIONES.md`.

Los extras ya están cerrados: **un solo rubro global** con descripción libre,
`cobrable` o costo interno. No hay categorías.

## 9. Fases

| Fase | Qué | Criterio |
|---|---|---|
| Q1 | Módulo de cotizaciones (ver `docs/COTIZACIONES.md`) | Cotización aceptada que genera contrato/orden |
| C1 | Revisión de este documento con Julio/contadora | Texto base aprobado o corregido |
| C2 | Migración 081: `contratos`, `contrato_versiones`, `anticipos_salario`, `jornada_eventos`, settings | Esquema aplicado, `NULL` donde falta dato |
| C3 | API: alta, versión, hash, estado, firma solo Julio | Tests de ciclo de vida; no se edita un activo |
| C4 | Impresión PDF de suministro y trabajo | Un contrato de prueba con hash verificable |
| C5 | Horas extra por chat + barra en Ocupación | Un mensaje + “sí” = evento registrado |
| C6 | Lista de contratos en el panel | Secretaría prepara, Julio firma |

**Secuencia:** primero se cierra la fase 2 del dashboard (endpoints) y la
pestaña Ocupación; después Q1 (cotizaciones) y recién C1–C2. La cotización va
antes que el contrato porque **el contrato es la cotización aceptada**: si se
construye al revés, se duplican campos y luego hay que refactorizar. Si se
mezclan, el tablero vuelve a quedar a medias.
