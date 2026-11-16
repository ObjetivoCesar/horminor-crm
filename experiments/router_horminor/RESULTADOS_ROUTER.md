# Resultados del router — etapa 1 y 2

> **Versión:** router-1.1 · **Fecha:** 2026-11-16
> **Evidencia:** `experiments/router_horminor/evidencias/`
> **Estado:** prototipo aislado; **el motor productivo y Gato siguen intactos**.

## 1. Qué cambió respecto de D+

| Antes (D/D+) | Ahora (router) |
|---|---|
| bloqueaba por datos faltantes | el dato va a **por investigar** del responsable |
| proponía departamentos inventados | solo **Julio, secretaría, jefe de planta** |
| mezclaba responsable y destinatario | campos separados |
| restricción de despacho podía bloquear la planificación | la tarea se crea; la **operación** queda condicionada |
| «avísame» podía ser otra tarea | se integra como **resultado esperado** |
| corrección por clave técnica | corrección en **lenguaje natural** sobre un encargo |
| confirmación ejecutaba acciones | confirmación produce un **plan** y se verifica |

## 2. Escenarios de aceptación (ejecutados en vivo)

| Caso | Encargos | Asignación | Preguntas | Plan | Correspondencia |
|---|---|---|---|---|---|
| A — operarios temprano | 1 | JEFE_PLANTA | 0 | 1 tarea con aviso como resultado | OK |
| B — volumen por averiguar | 1 | SECRETARIA | 0 | 1 tarea, volumen en por investigar | OK |
| C — tres encargos + corrección | 3 | 1 secretaría + 2 planta (tras corrección) | 0 | 3 tareas, solo E2 cambió (v2) | OK |
| D — despacho condicionado al pago | 2 | planta + secretaría | 0 | 2 tareas; salida **no** autorizada | OK |
| E — cita del cliente | 1 | SECRETARIA | 0 | revisión con «no ejecutar la solicitud» | OK |
| F — tarea + aviso | 1 | JEFE_PLANTA | 0 | 1 tarea con resultado esperado | OK |
| E07 — WhatsApp condicionado | 1 | SECRETARIA | 0 | comunicación **PREPARAR** (no enviar) | OK |
| E11 — revocación parcial | 1 | JEFE_PLANTA | 0 | revisión conservada; llamada cancelada | OK |
| E14 — dependencia de pago | 2 | secretaría + planta | 0 | 2 tareas; operación condicionada | OK |
| E27 — orden citada del cliente | 1 | SECRETARIA | 0 | revisión; no se ejecuta lo pedido | OK |

**Cero preguntas innecesarias** en los diez casos: los datos que el responsable
puede averiguar no se le devuelven a Julio.

## 3. La experiencia pedida

El laboratorio (`/`, puerto 8055) devolvió exactamente:

> «Julio, entendí 3 encargo(s): 2 tarea(s) para secretaría, 1 para el jefe de
> planta. E1 Revisar el pago de La Pradera · E2 Contactar al cliente… · E3
> Preparar la coordinación del despacho (condicionado)… ¿Confirmas?»

Al corregir «No era para secretaría, era para el jefe de planta lo de contactar
al cliente», solo cambió E2; E1 y E3 quedaron idénticos y el borrador pasó a
versión 2. Al confirmar, el plan mostró **tres tareas**, ninguna adicional, y
`Correspondencia: OK`.

## 4. Seguridad

- Ninguna tarea, mensaje ni operación se ejecutó: el resultado es un plan.
- Un WhatsApp solo se **prepara** sin autorización explícita.
- Una operación condicionada (despacho, dinero) queda con `autorizada: false`.
- Si el lector C falla, no se autoriza ninguna comunicación externa.
- `verificar_correspondencia` falla si el plan agrega, omite o duplica encargos.

## 5. Pruebas

- `tests_core.py`: **13/13** determinísticas (datos que no bloquean, preparar vs
  enviar, corrección de un solo encargo, cancelar, correspondencia, cita de
  cliente, sin C, clave idempotente, sin responsable, resultado esperado).
- Escenarios en vivo: 10/10 con correspondencia OK.
- `pytest` del motor: **620 passed** (no se tocó `app/`).

## 6. Límites

1. Sin persistencia ni migraciones: el borrador vive en memoria/archivos.
2. Sin integración con `/panel/cerebro` (etapa 3 pendiente).
3. Sin audio en este laboratorio: se escribe el dictado.
4. Variabilidad del modelo: dos corridas pueden partir un encargo de forma algo
   distinta; el conciliador fusiona avisos, pero no reescribe títulos.
5. Sin corpus humano de correcciones para medir aprendizaje.

## 7. Siguiente paso

Etapa 3: llevar este flujo a `/panel/cerebro` conservando correcciones y
confirmaciones existentes, sin conectar herramientas ejecutoras reales. Antes de
esa integración hay que decidir dónde persisten los borradores del router
(tabla nueva o almacenamiento temporal) y cómo convive con el borrador actual.
