# Diagnóstico arquitectónico del Cerebro — Horminor

> **Tipo de documento:** investigación, no implementación.
> **Corte del código:** commit `2a5fd93` (laboratorio v8.6, 620 pruebas).
> **Fecha:** 2026-11-16.
> **Alcance:** solo el Cerebro (voz → hechos → encargos → acciones). No incluye
> el ERP, Gato como interfaz ni el flujo comercial externo.
>
> **Regla de este documento:** describe lo implementado, no lo deseable. Cada
> afirmación se apoya en una función con archivo y línea, en un registro de la
> base o en una prueba ejecutada. Lo que es hipótesis está marcado como tal.

---

## 1. Recorrido real de una instrucción

### 1.1 Texto pegado en el laboratorio

```
POST /api/v1/cerebro/interpretar        app/cerebro/router.py:121
  └─ interpretar()                      app/cerebro/extractor.py:974
       ├─ normalizar_con_mapa()          app/voz/normalizador_ec.py:527
       ├─ extraer()                      app/cerebro/extractor.py:177   ← LLM
       │    └─ validar_sobre()           app/cerebro/sobre.py:107
       ├─ construir_hechos()             app/cerebro/extractor.py:264
       │    ├─ validar_hecho()           app/cerebro/hechos.py:215
       │    ├─ _inferir_telefono()       app/cerebro/extractor.py:628
       │    ├─ _completar_cuando_de_tarea() app/cerebro/extractor.py:562
       │    ├─ _degradar_pago_no_declarado() app/cerebro/extractor.py:532
       │    ├─ _ajustar_incertidumbre()  app/cerebro/extractor.py:449
       │    └─ asignar(segmentar(texto)) app/cerebro/encargos.py:78 / 39
       ├─ _borrador_desde_hechos()       app/cerebro/extractor.py:893
       │    ├─ _resolver_cliente()       app/cerebro/extractor.py:734
       │    ├─ _resolver_receta()        app/cerebro/extractor.py:793
       │    └─ compilar()                app/cerebro/compilador.py:1433
       │         ├─ segmentar()          app/cerebro/encargos.py:39
       │         ├─ _texto_del_grupo()   app/cerebro/compilador.py:1396
       │         ├─ _compilar_asunto()   app/cerebro/compilador.py:817
       │         │    ├─ _condiciones()  app/cerebro/compilador.py:613
       │         │    ├─ _ficha_tarea()  app/cerebro/compilador.py:385
       │         │    └─ mensaje_es_final() app/cerebro/compilador.py:748
       │         └─ _unificar_clientes() app/cerebro/compilador.py:1612
       ├─ resumen_legible()              app/cerebro/revision.py:245
       └─ INSERT cerebro_extracciones + cerebro_borradores
```

### 1.2 Audio

```
POST /api/v1/voz/transcribir            app/voz/router.py:38
  └─ ingestar_audio()                   app/voz/ingesta.py
       └─ proveedor STT (Groq/Whisper)  app/voz/proveedores/groq.py
            └─ voz_transcripciones (texto_crudo, segmentos_json con palabras)

POST /api/v1/cerebro/interpretar {transcripcion_id}
  └─ mismo camino que 1.1, con palabras STT para alinear citas y ventanas
```

### 1.3 Confirmación

```
POST /api/v1/cerebro/borradores/{id}/confirmar   app/cerebro/router.py:724
  ├─ exigir_modulo("cerebro", mutacion=True)      app/panel_acl.py
  ├─ valida estado, rol, bloqueo, dependencia, duplicado
  ├─ validar_confirmacion_recordatorio()          app/cerebro/router.py:675
  │    ├─ exige mensaje final si `mensaje_por_confirmar`
  │    └─ exige aceptar el envío inmediato si `programado_inferido`
  ├─ _ejecutar_tarea() → recordatorios.crear()    app/cerebro/router.py:1161
  │  o _ejecutar_tarea_interna() → internas.crear()  app/cerebro/router.py:1196
  └─ INSERT cerebro_ejecuciones + UPDATE del borrador
```

### 1.4 Qué decide el LLM y qué decide el código

| Decisión | Quién decide | Dónde |
|---|---|---|
| Qué datos se mencionan | **LLM** propone; el backend valida la cita | `extraer`, `construir_hechos` |
| A qué encargo pertenece cada hecho | **LLM** lo propone; `asignar` lo valida y renumera | `HechoIn.encargo`, `encargos.asignar` |
| Qué es una duda | LLM + **código** (`_ajustar_incertidumbre`) | `extractor.py:449` |
| Qué es una negación o revocación | **Código** (marcas de texto) | `compilador.dictado_revocado:451`, `_condicion_negada:546` |
| Enviar vs delegar | **Código** | `internas.detectar_intencion_tarea:199` |
| A quién se asigna una tarea | **Código** | `internas.detectar_rol_interno:162`, `persona_dictada:177` |
| Si hay acción de cotización | **Código** | `_compilar_asunto:817` |
| Precio y dinero | **Código** (receta + guardas) | `_resolver_receta`, `_dinero_ya_entro` |
| Qué preguntas se hacen | **Código** | `_compilar_asunto`, `_sin_duplicados:804` |
| El resumen | **Código**, con los hechos | `revision.resumen_legible:245` |

**Consecuencia:** el LLM solo aporta hechos y una propuesta de agrupación. Todo
lo demás —canal, responsable, acción, dinero— lo decide código con reglas de
texto. Los siete errores P1–P7 nacen casi todos en ese código, no en el modelo.

---

## 2. Cómo se detectan y separan los encargos

1. **El modelo numera** cada hecho con `encargo` (regla 25 del prompt v7).
2. `segmentar()` (`encargos.py:39`) corta por ordinales («primero… segundo…»).
   Es el único respaldo determinístico.
3. `asignar()` (`encargos.py:78`):
   - si el modelo propuso más de un encargo, **respeta esa separación** y
     renumera 1..N;
   - si no, corta por posición de la cita y los ordinales.
4. `compilar()` (`compilador.py:1433`) agrupa por `hecho.encargo`, y para cada
   grupo arma su texto con `_texto_del_grupo()`: el tramo ordinal o, si no hay,
   **la concatenación de las citas del grupo**.
5. Si un tramo no tiene `tarea.mensaje` pero nombra un área, **se sintetiza** un
   hecho `tarea.mensaje` con el texto del tramo (`compilador.py:1467-1500`).

**Límites observados:**
- El corte por ordinales no reconoce cambios de asunto sin ordinales; depende
  del modelo.
- La síntesis del punto 5 es la causa de la tarea duplicada de P2/P3: agrega una
  instrucción que ya existía en otro encargo.
- No hay validación de que dos hechos de la misma oración pertenezcan al mismo
  encargo.

---

## 3. Intención, destinatario y responsable

`detectar_intencion_tarea()` (`internas.py:199`) decide ENVIAR / DELEGAR:

```
si el texto dice «que <área> …»      → DELEGAR
si hay verbo de envío (envíale…)     → ENVIAR (o DELEGAR si el área no tiene teléfono)
si hay verbo de encargo o un área    → DELEGAR
si no                                 → None → el compilador asume ENVIAR
```

- `ALIAS_ROL` (`internas.py:42`) solo conoce **secretaría, bodega, contadora,
  ventas**. «chicos de planta» (P1), «logística» (P7) y «me avisen» (P7) no
  están y caen en `None` → **ENVIAR**.
- `detectar_rol_interno()` busca el alias **en el texto del encargo**, no en el
  dictado completo. Es correcto para evitar contaminación, pero deja sin área a
  los encargos cuya cita no la repite.
- `detectar_intencion_tarea` no distingue «comunicar» de «enviar por WhatsApp»:
  solo hay dos valores. Una llamada, una coordinación o un aviso interno no
  tienen representación propia.
- El destinatario del hecho no es el responsable de la tarea. `tarea.destinatario`
  se usa para las dos cosas: en un recordatorio es a quién se le escribe; en una
  tarea interna es a quién se le asigna. **Esa ambigüedad es de diseño.**

---

## 4. Negaciones, dudas y revocaciones

| Mecanismo | Función | Alcance real |
|---|---|---|
| Revocación del dictado | `dictado_revocado` (`compilador.py:451`) | **Todo el texto**. Si aparece «mejor no», «no lo hagas», etc., el dictado entero queda `SIN_ACCIONES`. |
| Negación de un dato | `_condicion_negada` (`compilador.py:546`) | Solo descuento y precio: ventana de 50 caracteres. |
| Duda | `_ajustar_incertidumbre` (`extractor.py:449`) | Por cercanía; marca o degrada `TENTATIVO`. |
| Condiciones | `_condiciones` (`compilador.py:613`) | Solo tres familias: plazo, entrega contra pago, expediente. |

**Consecuencia directa:**
- **P4**: «Bueno, no, mejor no preparen todavía la cotización» activa
  `dictado_revocado` y **borra también** la instrucción válida «pero sí quiero
  que secretaría…». La revocación es total, no por asunto.
- **P1**: «Todavía no le envíes nada hasta que yo confirme el mensaje» no es una
  revocación (no hay «no lo hagas»), así que no bloquea nada; el mensaje se
  propone como final.
- **P5**: «sin cobrarles todavía» no encaja en ninguna de las tres condiciones y
  solo queda dentro del texto de la instrucción.

---

## 5. Tiempo y contexto

- `hora_de_cita`, `hora_explicita`, `hora_de_recordatorio`, `sostiene_fecha`
  (`cerebro/tiempo.py:82-108`) distinguen una hora de una fecha.
- `_completar_cuando_de_tarea` (`extractor.py:562`) toma una hora de la frase
  del recordatorio cuando el modelo no la extrajo.
- No existe un tipo «plazo» ni «ventana»: el plazo es texto libre
  (`cotizacion.plazo_entrega`) y la hora de entrega es un hecho aparte.

**Consecuencia directa:**
- **P7**: «antes de las seis de la mañana» es una hora de **entrega**, pero
  `_completar_cuando_de_tarea` la copia como `tarea.cuando = 06:00`, es decir,
  como **hora límite de la tarea**. El dato es correcto; el significado se
  pierde al cambiar de clave.

---

## 6. Cómo se construyen las acciones

`_compilar_asunto()` (`compilador.py:817`) decide por presencia de hechos:

| Acción | Se activa cuando | Riesgo observado |
|---|---|---|
| `crear_cliente` | hay `cliente.nombre` y el cliente no existe | puede crear un cliente por una mención, sin orden explícita |
| `crear_cotizacion_borrador` | hay volumen + obra + resistencia + precio (de receta) | **P3**: crea cotización aunque el dictado diga «antes de preparar cualquier cotización» / «no quiero que le den un precio todavía» |
| `crear_tarea_interna` | hay `tarea.mensaje` y la intención es DELEGAR, o se sintetiza el tramo | **P2/P3**: duplica la instrucción |
| `crear_tarea_recordatorio` | hay mensaje + destino y la intención es ENVIAR | **P1/P7**: manda a WhatsApp lo que era interno |
| `enviar_cotizacion_whatsapp` | `cotizacion.enviar` es verdadero | correcto |
| `registrar_abono_cliente` | monto + recibido confirmado | correcto |

**La acción se deriva de los hechos, no de una orden.** Es la causa raíz de la
pregunta «¿estamos confundiendo hechos con intenciones?»: sí, en la cotización.

---

## 7. Diagnóstico general

1. **Hechos ≠ intención.** El compilador infiere la orden de la presencia de
   datos. Un dictado que solo describe («tenemos una obra…») puede producir una
   cotización.
2. **Destinatario = responsable.** Un solo campo sirve para «a quién le escribo»
   y «a quién le encargo». P1 y P7 muestran el cruce.
3. **Comunicar = enviar WhatsApp.** Solo hay dos canales en el modelo de
   intención (ENVIAR/DELEGAR); llamar, coordinar o avisar internamente no
   existen.
4. **Segmentación delegada al modelo con respaldo pobre.** Funciona con
   ordinales y con el prompt v7, pero no hay validación semántica de la
   agrupación; la síntesis añade un encargo que no existía.
5. **Restricciones sin representación.** Negación, condición, plazo y
   prohibición viven en textos y listas distintas. «No cobren todavía» no se
   propaga a la acción de cobranza porque no existe ese vínculo.
6. **Sin dependencias entre acciones.** «Verificar pago antes de autorizar
   despacho» se puede escribir en una instrucción, pero no existe un grafo
   acción → condición → acción.
7. **Revocación total.** Un «mejor no» cancela el dictado completo, no el asunto.
8. **Preguntas de más.** La falta de un dato bloquea el encargo entero; no hay
   forma de «dejar pendiente para secretaría» sin preguntar a Julio.
9. **Reparto de responsabilidades difuso.** El extractor decide dudas y horas;
   el compilador decide canal, responsable y acción; el prompt también sugiere
   intención. Tres capas toman decisiones semánticas con reglas distintas.

---

## 8. Por qué 620 pruebas no detectaron esto

| Medición | Valor |
|---|---|
| Archivos de prueba | 41 |
| Funciones de prueba | 553 (620 casos con `parametrize`) |
| Pruebas del Cerebro (v85–v96) | 160 |
| Pruebas que construyen `HechoCitado` a mano | 129 (6 archivos) |
| Pruebas que llaman `construir_hechos` | 11 (un archivo) |
| Pruebas que recorren extractor + compilador juntos | 11 (con `SobreIn` escrito a mano y LLM simulado) |
| Pruebas con respuesta **real** de un modelo | **0** |
| Pruebas de flujo completo por HTTP del Cerebro | **0** |
| Pruebas que solo verifican «hay acciones» | varias (p. ej. `test_v87` afirma nombres de acción, no la ausencia de las incorrectas) |
| Pruebas de duplicación entre encargos | 1 (`test_v95`, misma clave en dos encargos) |
| Pruebas de revocación parcial | **0** |
| Pruebas de «interno vs WhatsApp» con roles no listados | **0** |

La suite valida **reglas aisladas con entradas ideales**. No valida la
variabilidad del modelo, ni frases espontáneas, ni el significado de una hora
según la clave, ni la ausencia de una acción prohibida. P1–P7 son precisamente
esos casos.

---

## 9. Límites de esta investigación

- Los registros P1–P7 existen y están íntegros (ver Documento 2). **No** hay
  traza del prompt exacto enviado ni de la respuesta HTTP cruda; sí del `sobre`
  validado que se guardó y del texto de entrada.
- No se ejecutó ninguna prueba nueva sobre estos casos para no alterar la
  evidencia. Cualquier reproducción posterior deberá hacerse en un entorno
  aislado y marcarse como nueva.
- Las conclusiones sobre «qué esperaba Julio» en cada caso son hipótesis hasta
  contrastarlas con los resultados visibles que él conserva.

---

## 10. Material de apoyo

| Archivo | Contenido |
|---|---|
| `docs/auditoria_cerebro/prompt_cerebro_v7.txt` | prompt y claves literales |
| `docs/auditoria_cerebro/codigo/` | copia de los 11 archivos relevantes |
| `docs/auditoria_cerebro/esquema_cerebro.sql` | DDL de las 14 tablas del Cerebro y la voz |
| `docs/auditoria_cerebro/p1_p7_registros.json` | registro íntegro de los 8 borradores |
| `docs/auditoria_cerebro/pruebas_inventario.md` | inventario de la suite |
| `docs/TRAZABILIDAD_P1_P7.md` | caso por caso y primer punto de divergencia |
| `docs/ALTERNATIVAS_SOLUCION_CEREBRO.md` | tres estrategias comparadas |
