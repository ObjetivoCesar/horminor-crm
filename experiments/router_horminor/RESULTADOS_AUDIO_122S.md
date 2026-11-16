# Audio real de 122 s — contrato Díaz Sur

> **Versión:** router-1.2 · **Fecha:** 2026-11-16
> **Original:** borrador `93647d2c-1b05-4fe5-9095-770ddecc52a2`, transcripción
> `37deb787-d140-44fb-80e4-078057dc34ca`, 122.216 ms, prompt `cerebro-v7`.
> **Evidencia:** `evidencias/caso_diaz_sur_original.json` y
> `evidencias/caso_diaz_sur_resultado.json`.
> **Sin cambios en el motor productivo ni en Gato.**

---

## 1. V07: por qué produjo cero acciones

La reproducción en memoria confirma:

- **17 hechos** en el sobre guardado.
- `dictado_revocado` devuelve **true** por la marca **«mejor no»**, que aparece
  **dentro de «mejor nos abastecemos»**. No es una revocación: es una decisión
  logística.
- Resultado: `SIN_ACCIONES`, 0 acciones, 0 preguntas. El dictado entero se
  descartó.
- Al reconstruir hoy, el backend acepta **14** de los 17 hechos: los tres del
  pago (`monto`, `forma`, `recibido`) se rechazan porque su cita guardada dice
  «27000 USD» y el texto normalizado actual dice «27 1000 USD». Es una deriva de
  normalización, no un error del modelo.

**Díaz Sur / Dualsur:** el sobre guardado dice `cliente.nombre = Dualsur`
(`CORREGIDO_EN_AUDIO`) aunque el audio dice «Díaz Sur». Es el vocabulario
aprendido (`Díaz Sur → Dualsur`) aplicado como pista. El router, que no recibe
esa pista, conserva **Díaz Sur**. La corrección aprendida es legítima, pero debe
ser visible y revisable: hoy cambia el nombre sin avisar en el borrador.

---

## 2. Lectura del router

**Encargo A — jefe de planta**
- Evaluar y coordinar el traslado de la planta móvil al terreno, producir y
  despachar desde ahí sábados y domingos, reduciendo transporte.
- Responsable: **JEFE_PLANTA** (sugerido).
- Es una **propuesta de coordinación**: no se autoriza mover maquinaria.
- Por investigar: factibilidad, logística de montaje, energía/agua/espacio,
  operarios de fin de semana, volumen por fin de semana.

**Encargo B — secretaría**
- Preparar los documentos del contrato (380 m³, un mes, 13 %, FC-240) para el
  responsable del contrato.
- Responsable: **SECRETARIA** (sugerido).
- Documentos **preparados**, no enviados.

**Encargo C — secretaría**
- Preparar el recordatorio de la transferencia de **27.000 USD** para la firma.
- Responsable: **SECRETARIA**.
- **Preparar no es enviar**: falta autorización explícita.
- Destinatario propuesto: **Julio Alvarado Meneses** (primer contacto
  mencionado), con pregunta breve: «¿El recordatorio va para Julio Alvarado
  Meneses o para Mauricio Santander?».

**Pago esperado, no recibido:** `pago.recibido = false`; el resumen dice «el
pago de 27.000 USD todavía no está confirmado».

**Datos del contrato conservados como contexto** (no generan tareas): cliente,
380 m³, un mes, sábados y domingos, planta móvil, 13 %, FC-240, 27.000 USD.

---

## 3. Respuesta conversacional (generada, no literal)

> «Julio, entendí que tenemos un contrato de 380 m³ con Díaz Sur. Propongo 3
> encargos: 2 para secretaría, 1 para el jefe de planta. E1 Preparar documentos
> del contrato… E2 Recordatorio de transferencia por firma de contrato… E3
> Evaluar traslado de planta móvil… El pago de 27.000 USD todavía no está
> confirmado. Antes de confirmar: ¿El recordatorio va para Julio Alvarado
> Meneses o para Mauricio Santander?»

---

## 4. Corrección y confirmación

Corrección: «No, el recordatorio va para Mauricio, no para Julio Alvarado».

- Cambió **solo E2**: destinatario Julio Alvarado → **Mauricio Santander**.
- E1 y E3 quedaron idénticos. Versión **2**; la versión 1 se conserva.
- Vía: LLM (la frase no usa el patrón «no era para X»).

Plan tras confirmar:

| Encargo | Responsable | Acción |
|---|---|---|
| E1 documentos | SECRETARIA | crear tarea + preparar comunicación |
| E2 recordatorio | SECRETARIA | crear tarea + **preparar** (no enviar) |
| E3 planta móvil | JEFE_PLANTA | crear tarea; operación no ejecutada |

- Comunicaciones: **PREPARAR** en ambos casos; ninguna se envía.
- Correspondencia confirmado ↔ plan: **OK** (3 tareas, 3 encargos, 0 extras).

---

## 5. Divergencias encontradas y corregidas en el experimento

| # | Divergencia | Corrección (general, no memorizada) |
|---|---|---|
| 1 | «27 1000 USD» se leyó como 271.000 | reparación determinística: `N 1000` = N mil |
| 2 | «hay que enviarle» se tomó como autorización | autorización solo con «envíalo», «mándalo», «autorizo»… |
| 3 | una decisión logística se marcó como cita de cliente | cita de tercero exige «me dijo», «nos pidió», «solicitó»… |
| 4 | «ver si podemos…» y descripciones se adjuntaban como condiciones | la condición exige «hasta que», «antes de», «depende», «condicionado»… |
| 5 | se inventó «verificar la transferencia» | un pago anunciado no crea tarea de verificarlo |
| 6 | destinatario «Díaz Sur» sin aclaración | propone el primer contacto y pregunta si hay varios |

Ninguna corrección se apoya en una frase literal de este audio.

---

## 6. Comparación V07 vs router

| Criterio | V07 | Router 1.2 |
|---|---|---|
| Hechos | 17 guardados; 14 reconstruidos | 380, 240, 13 %, plazo, días, planta, 2 contactos, 27.000 |
| Revocación | **falsa** («mejor nos») | no aplica: C distingue decisión de revocación |
| Encargos | 0 | 3 (planta, documentos, recordatorio) |
| Responsables | — | JEFE_PLANTA / SECRETARIA / SECRETARIA |
| Pago | — | esperado, no recibido |
| Envío externo | — | preparar, no enviar |
| Preguntas | 0 | 1 (destinatario del recordatorio) |
| Corrección | — | solo E2; versión nueva |
| Confirmación | — | plan con correspondencia OK |

---

## 7. Variación nueva (no usada para diseñar)

«Contrato con Constructora Andina, 120 m³ FC-210, dos meses, solo sábados;
mejor nos organizamos con la planta fija; descuento 5 %; responsable ingeniera
Paredes, jefe de obra Torres; transferencia de 8 mil; preparen documentos y un
recordatorio para Torres, pero no lo envíen todavía.»

Resultado: 3 encargos (documentos, recordatorio a Torres condicionado, planta
fija), 2 para secretaría y 1 para jefe de planta; **no** apareció la tarea
inventada de verificar el pago; **no** se envió nada; correspondencia OK. El
monto se conservó en 8.000.

---

## 8. Pruebas y límites

- `tests_core.py`: **17/17** determinísticas (incluye monto, autorización,
  pago anunciado, condición falsa).
- Motor productivo: **620 passed**; `app/` sin cambios.
- Límites: sin persistencia; 122 s es un caso de diagnóstico, no de
  entrenamiento; la variabilidad del modelo puede cambiar títulos; falta un
  corpus humano de correcciones.

**Primer punto de divergencia del audio:** V07, en `dictado_revocado`
(`app/cerebro/compilador.py`), por coincidencia de subcadena «mejor no» dentro de
«mejor nos» — antes de compilar cualquier acción.
