# Contratos de personal y horas extra — propuesta v6.19

> **Estado:** propuesta de diseño. No es un contrato válido ni asesoría legal.
> El texto legal base debe revisarlo un abogado laboral o la contadora antes de
> imprimir el primer contrato real. Las cifras (salario, tarifas) quedan `NULL`
> hasta que Julio las cargue.

## 1. Principio: el sistema es la fuente

Julio lo dijo así: *“se crean aquí en digital y se imprimen, pero nosotros somos
la fuente”*. Eso fija tres reglas:

1. **El contrato nace en el sistema**, no en un Word aparte.
2. **El impreso es una foto**: lleva número, versión y hash del contenido.
3. **Un contrato activo no se edita.** Si cambia el salario, la jornada o el
   cargo, se crea una **versión nueva** (adenda) con su motivo. La versión
   anterior queda inmutable y sigue siendo la que se firmó.

Sin esto, el impreso y la base se separan y nadie sabe cuál manda.

## 2. Alcance

**Incluye**

- Ficha de personal (nombre, cédula, cargo, teléfono, estado).
- Contrato con número, tipo, vigencia, jornada, remuneración y modalidad de
  horas extra.
- Versiones inmutables y hash del documento impreso.
- Registro de horas extra ligado al contrato, con autorización de Secretaría o
  Julio.
- Impresión a PDF con el mismo patrón que la factura interna.

**No incluye (por ahora)**

- Nómina, roles de pago, IESS ni retenciones.
- Registro del contrato en el Ministerio del Trabajo.
- Firma electrónica certificada.
- Cálculo legal de recargos: la tarifa sale del contrato, no de una constante
  escondida en el código.

## 3. Modelo de datos

### 3.1 `personal`

| Campo | Tipo | Regla |
|---|---|---|
| `id` | uuid | PK |
| `nombre` | text | obligatorio |
| `cedula` | text | único, `NULL` permitido |
| `cargo` | text | `NULL` hasta cargar |
| `telefono` | text | `NULL` permitido |
| `estado` | text | `ACTIVO` / `INACTIVO` |
| `created_at` | timestamptz | default `now()` |

### 3.2 `contratos`

| Campo | Tipo | Regla |
|---|---|---|
| `id` | uuid | PK |
| `numero` | text | único, formato `HORM-CT-AAAA-0001` |
| `personal_id` | uuid | FK `personal` |
| `tipo` | text | `INDEFINIDO`, `FIJO`, `OBRA`, `PRUEBA` |
| `fecha_inicio` | date | obligatoria |
| `fecha_fin` | date | `NULL` si es indefinido |
| `cargo` | text | obligatorio |
| `funciones` | text | `NULL` hasta cargar |
| `jornada_horas_semana` | numeric | `NULL` hasta cargar |
| `horario` | jsonb | `{"entrada":"07:00","salida":"17:00","dias":[...]}` |
| `salario_base` | numeric | `NULL` hasta cargar |
| `modalidad_pago` | text | `MENSUAL`, `QUINCENAL`, `SEMANAL`, `POR_DIA`, `POR_M3` |
| `horas_extra_modo` | text | `POR_HORA`, `MONTO_FIJO`, `NO_APLICA` |
| `tarifa_hora_extra` | numeric | `NULL` hasta cargar |
| `estado` | text | `BORRADOR`, `ACTIVO`, `FINALIZADO`, `ANULADO` |
| `version` | integer | empieza en 1 |
| `contenido_hash` | text | SHA-256 del HTML/PDF renderizado |
| `pdf_media_id` | uuid | FK `media_assets` |
| `creado_por` | text | usuario del panel |
| `created_at` / `updated_at` | timestamptz | |

### 3.3 `contrato_versiones`

Cada versión guarda el snapshot y el hash. La versión 1 es el contrato
original; las siguientes son adendas, renovaciones o correcciones.

| Campo | Tipo |
|---|---|
| `id` | uuid |
| `contrato_id` | uuid |
| `version` | integer |
| `motivo` | text (`ADENDA`, `RENOVACION`, `CORRECCION`, `TERMINACION`) |
| `snapshot` | jsonb |
| `hash` | text |
| `pdf_media_id` | uuid |
| `creado_por` | text |
| `created_at` | timestamptz |

### 3.4 `jornada_eventos` (horas extra)

| Campo | Tipo | Regla |
|---|---|---|
| `id` | uuid | PK |
| `personal_id` | uuid | FK |
| `contrato_id` | uuid | FK |
| `fecha` | date | día del evento |
| `inicio` / `fin` | timestamptz | hora real |
| `minutos` | integer | generado: `(fin - inicio)` en minutos |
| `tipo` | text | `ORDINARIA`, `EXTRA`, `NOCTURNA`, `FERIADO` |
| `orden_id` | uuid | `NULL` permitido |
| `mixer_codigo` | text | `NULL` permitido |
| `motivo` | text | obligatorio |
| `autorizado_por` | text | Secretaría o Julio |
| `autorizado_rol` | text | `SECRETARIA` / `JULIO` |
| `created_at` | timestamptz | |

El dinero **no** se guarda aquí. Se calcula al reportar:
`minutos / 60 * tarifa_hora_extra` solo si la tarifa no es `NULL`. Si el
contrato es `MONTO_FIJO`, se muestra el monto contractual y las horas aparte.

### 3.5 `system_settings`

| Llave | Valor inicial | Para qué |
|---|---|---|
| `personal.jornada` | `{"entrada":"07:00","salida":"17:00","dias":["LUN","MAR","MIE","JUE","VIE","SAB"]}` | línea base de horas extra |
| `personal.horas_extra` | `{"requiere_autorizacion":true,"autorizadores":["SECRETARIA","JULIO"]}` | quién puede aprobar |

La tarifa no va acá: es por contrato.

## 4. Ciclo de vida

```
BORRADOR -> (vista previa) -> ACTIVO (versión 1, hash, PDF)
ACTIVO -> ADENDA (versión 2, 3...) -> ACTIVO
ACTIVO -> FINALIZADO (fin de vigencia o terminación)
BORRADOR -> ANULADO (nunca se firmó)
```

Reglas duras:

- Un contrato `ACTIVO` no se edita. Se versiona.
- El `numero` no cambia nunca.
- El hash se calcula sobre el contenido renderizado, no sobre la base.
- Si el PDF no coincide con el hash, el impreso no es válido.

## 5. Contrato estándar (base a revisar)

Secciones mínimas, con el texto legal marcado `[REVISAR]`:

1. Comparecientes (empleador y trabajador).
2. Antecedentes y objeto del contrato.
3. Cargo y funciones.
4. Jornada y horario (desde `personal.jornada` y el contrato).
5. Remuneración y modalidad de pago.
6. Horas extra: modalidad, autorización y forma de cálculo.
7. Obligaciones y prohibiciones.
8. Confidencialidad y uso de información.
9. Terminación.
10. Firma y huella.

**No invento cláusulas como definitivas.** El documento sale con
`[REVISAR]` en los puntos que dependen de la ley o de la decisión de Julio.
La primera impresión real no se hace hasta que la contadora o el abogado
aprueben el texto.

## 6. Impresión

- Mismo patrón que `services/core-api/app/routers/facturas.py` (HTML -> PDF).
- Encabezado: HORMINOR, número, versión, fecha.
- Pie: hash corto, página, “Documento generado por el sistema”.
- El PDF se guarda en `media_assets` y queda enlazado a la versión.
- Sin QR por ahora; el hash y el número alcanzan para verificar contra la base.

## 7. Horas extra desde el chat

Flujo, reutilizando el patrón de recordatorios:

1. Julio o Secretaría escriben: *“el mixer 2 salió 5:40 y volvió 19:10”*.
2. Gato identifica persona/contrato, propone el evento con los minutos
   calculados por el backend y pide ratificación.
3. “Sí” -> se registra `jornada_eventos` con `autorizado_por`.
4. El tablero de Ocupación muestra “horas fuera de jornada” como barra aparte.

La IA extrae la frase; **no calcula minutos ni dinero**.

## 8. Preguntas abiertas para Julio

1. ¿Qué tipos de contrato usa hoy? (indefinido, fijo, por obra, prueba)
2. ¿El salario es mensual, quincenal, semanal, por día o por m³?
3. ¿Hay período de prueba? ¿Cuánto?
4. ¿Quién firma por la empresa: Julio, Secretaría o ambos?
5. ¿Se necesita cláusula de confidencialidad o exclusividad?
6. ¿Los contratos se numeran por año?
7. ¿La adenda de salario se imprime y se firma, o basta el registro digital?

## 9. Fases

| Fase | Qué | Criterio |
|---|---|---|
| C1 | Este documento + revisión con Julio/contadora | Texto base aprobado o corregido |
| C2 | Migración 080: `personal`, `contratos`, `contrato_versiones`, `jornada_eventos`, settings | Esquema aplicado, `NULL` donde falta dato |
| C3 | API: alta, versión, hash, estado | Tests de ciclo de vida; no se edita un activo |
| C4 | Impresión PDF | Un contrato de prueba con hash verificable |
| C5 | Horas extra por chat + barra en Ocupación | Un mensaje + “sí” = evento registrado |
| C6 | Lista de contratos en el panel | Secretaría ve y descarga; Julio aprueba |

**Secuencia:** esto no entra en medio del tablero. Primero se cierra la fase 2
del dashboard (endpoints) y la pestaña Ocupación; después arranca C1–C2. Si se
mezclan, el tablero vuelve a quedar a medias.
