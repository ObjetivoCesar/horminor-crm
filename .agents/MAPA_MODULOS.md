# Mapa de módulos y componentes — HORMINOR

> **Para qué existe:** que cualquier agente sepa, antes de tocar código, **dónde
> está el diseño de cada módulo, qué skill lo gobierna y en qué estado va**. Sin
> esto se rediseña desde cero lo que ya se decidió, o se construye al revés.
>
> **Cuándo se lee:** al empezar una tarea que toca un módulo, un documento o una
> pantalla. Se lee junto con `ESTADO.md`.
>
> **Cuándo se actualiza:** el mismo día en que cambia una decisión de módulo. Si
> no está aquí, el siguiente agente no lo va a encontrar.

## 1. Regla de oro

Cada módulo tiene **tres piezas** y las tres viven en el repositorio:

| Pieza | Dónde | Para qué |
|---|---|---|
| Diseño | `docs/<MODULO>.md` | qué es, qué no es, campos, estados, fases |
| Skill | `.agents/skills/<skill>/SKILL.md` | cómo lo ejecuta un agente sin improvisar |
| Tareas | `.agents/tareas/PENDIENTES.md` | qué falta y con qué criterio se cierra |

Si un módulo no tiene las tres, está a medias aunque el código compile.

## 2. Módulos construidos

| Módulo | Código | Diseño | Skill | Estado |
|---|---|---|---|---|
| M1 WhatsApp | `app/m1_whatsapp/` | `docs/GATO_SECRETARIA.md` | — | Operativo; Evolution real probado en VPS |
| M2 Planta | `app/m2_planta/` | `docs/MODELO_DATOS.md` | — | Operativo: dosificador y kardex |
| M3 Secretaría | `app/m3_secretaria/` | `docs/00_DECISIONES_PENDIENTES.md` | — | Operativo: ventanilla, carpeta forense, caja |
| M4 Dashboard | `app/m4_dashboard/` | `docs/BASE_DE_DATOS.md` | — | **En rediseño** (ver 3.1) |
| M5 Centinela | `app/m5_sentinel/` | `docs/00_DECISIONES_PENDIENTES.md` | `orminorth-diag-centinela` | Operativo: 12 chequeos |
| Custodio | `app/custodio/`, `app/http_gate/` | `docs/CUSTODIO_*.md` | `custodio-bd-horminor` | v4.4 verificado con `ROLLBACK` |
| Gato | `app/asistente/` | `docs/GATO_CORPUS.md`, `docs/GATO_PROMPT.md` | — | Recordatorios en VPS; cotizaciones y horas extra pendientes |
| Superadmin | `app/superadmin/` | `docs/BASE_DE_DATOS.md` | `configuracion-precios` (propuesta) | 7 secciones operativas |
| Media / carpeta del cliente | `app/services/media.py` | migración `071` | — | Operativo en SANDBOX; Bunny real pendiente |
| Agenda / disponibilidad | `app/agenda/` | migración `067` | `agenda-obras-visitas` (propuesta) | Operativo |

## 3. Módulos en diseño (todavía sin código)

### 3.1 Dashboard operativo — Ocupación, Inventario, Cobranza

- **Diseño:** `docs/DASHBOARD_OPERATIVO.md` (pendiente crear) + este mapa.
- **Skill propuesta:** ninguna todavía; el tablero es lectura, no una skill.
- **Decidido:** tres pestañas (Ocupación por defecto, Inventario, Cobranza);
  submenú propio; se elimina “Filtros de obras”; resumen anual comprimido.
- **Hecho:** migración `079` (vencimiento y `v_cobranza_documentos`), evidencia
  en `.agents/evidencias/dashboard_cobranza_2026-11-13.txt`.
- **Hecho (2026-11-13):** tres pestañas con submenú en el panel, sin “Filtros de
  obras”; endpoints `/dashboard/inventario` y `/dashboard/cobranza` con tests.
  Evidencia en `.agents/evidencias/dashboard_operativo_2026-11-13.txt`.
- **Falta:** endpoint `operacion` (timeline de mixers) y capacidad comprometida.

### 3.2 Cotizaciones

- **Diseño:** `docs/COTIZACIONES.md` v6.20.
- **Skill:** `pdf-cotizaciones` v1.3.0 (emisión del PDF) + pilar propuesto
  `cotizaciones-comercial` (alta, extras, estados, conversión).
- **Decidido:** cotización primero; aceptar asigna etiqueta `VENTA`; 15 días
  modificable; envío por WhatsApp con PDF archivado en la carpeta del cliente;
  extras = **un solo rubro global**; medición **pactada**.
- **Falta:** migración `080` y API.

### 3.3 Contratos (suministro y trabajo)

- **Diseño:** `docs/CONTRATOS.md` v6.19.
- **Skill propuesta:** `contratos-documentos`.
- **Decidido:** dos tipos en una tabla con `datos` JSONB; Secretaría prepara y
  **solo Julio firma** (`BORRADOR → ACTIVO`); activo no se edita, se adenda;
  hash del impreso.
- **Falta:** revisión del texto legal con Julio/contadora; migración `081`.

### 3.4 Horas extra y jornada

- **Diseño:** `docs/CONTRATOS.md` §3.6 y §3.7.
- **Skill propuesta:** `personal-jornada`.
- **Decidido:** jornada ordinaria 07:00–17:00 configurable; autorizan Secretaría
  o Julio; **se paga por contrato**, sin tarifa global; sin tarifa se muestran
  horas, no dólares.
- **Falta:** migración `081` (`jornada_eventos`), registro desde Gato y barra en
  Ocupación.

### 3.5 Inventario físico

- **Diseño:** `docs/BASE_DE_DATOS.md` + `v_stock_proyectado`.
- **Estado:** bloqueado. Sin conteo físico todo sale `SIN_LEVANTAR`.
- **Falta:** que Bodega ejecute el conteo y lo registre desde Superadmin.

## 4. Fronteras que no se cruzan

- `pdf-cotizaciones` **no** calcula precios ni lee `clients`: recibe todo.
- La cotización **no** crea orden: la conversión es explícita.
- El contrato **no** ejecuta: la orden sí.
- El despacho **no** cambia lo pactado: el excedente es costo, no cobro.
- Gato **no** aprueba, no cambia precios y no convierte sin un “sí” humano.
- El dashboard **no** calcula en JavaScript: si suma en el navegador, está mal.

## 5. Cómo agregar un módulo a este mapa

1. Crear `docs/<MODULO>.md` con: qué es, qué no es, modelo de datos, estados,
   permisos, fases y preguntas abiertas.
2. Crear o actualizar la skill en `.agents/skills/<skill>/`.
3. Agregar las tareas a `.agents/tareas/PENDIENTES.md` con criterio de cierre.
4. Agregar la fila en este mapa.
5. Registrar la decisión en `BITACORA.md`.

Sin los cinco pasos, el módulo no está “en diseño”: está en la cabeza de alguien.
