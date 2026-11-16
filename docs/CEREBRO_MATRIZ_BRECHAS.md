# Cerebro — matriz de brechas y estado real

> **Qué es esto.** Respuesta al Entregable 1 de la auditoría adversarial:
> cada requisito, con su estado real, el componente que lo resuelve, la prueba
> que lo demuestra y la evidencia. No es una descripción comercial: es un
> parte de situación.
>
> **Fecha:** 2026-11-15 · **Corte:** incremento v2 (090) · **Suites:** 586 pruebas.
>
> **Cómo leer los estados**
>
> - **VERIFICADO**: existe, tiene prueba automatizada y, cuando aplica, corrida
>   en vivo registrada en `.agents/evidencias/`.
> - **PARCIAL**: existe la parte principal; falta un caso o un canal.
> - **PENDIENTE**: no existe.
> - **NO VERIFICADO**: existe el diseño o el código, pero no hay prueba que lo
>   demuestre en el escenario concreto.

---

## 0. Lo que cambió en este incremento

| # | Mejora | Estado | Dónde |
|---|---|---|---|
| 1 | Notificación en tres actos (avisada, vista, acusada) + prioridad + plazo + escalada | **VERIFICADO** | `cerebro_tareas_internas`, `internas.py`, `/panel` |
| 2 | Ficha determinística de la tarea (tipo, referencia, pendiente, resultado esperado) | **VERIFICADO** | `compilador._ficha_tarea` |
| 3 | Duda explícita `TENTATIVO` que no se vuelve dato definitivo | **VERIFICADO** | `hechos.py`, `compilador.py`, `revision.py`, prompt v6 |
| 4 | Intención antes que teléfono (delegar ≠ enviar) | **VERIFICADO** | `internas.detectar_intencion_tarea` |
| 5 | Pruebas F, K, L + incertidumbre + duplicación + retiro de aprendizaje | **VERIFICADO** | `test_v92_adversarial.py`, evidencia en vivo |
| 6 | Contrato WhatsApp–Cerebro–CRM | **VERIFICADO (documento)** | `docs/CONTRATO_WHATSAPP_CEREBRO.md` |
| 7 | Documento de estado corregido (retención, métricas, notificaciones) | **VERIFICADO** | `docs/CEREBRO_RESUMEN_PARA_REVISION.md` |
| 8 | Manual Vivo, mapa, índice y nombres visibles | **VERIFICADO** | `docs/HORMINOR_MANUAL_FUNCIONAL.md`; skill `orminorth-manual-funcional` |
| 9 | Revocación completa del dictado (F) y negación de instrucción citada (L) | **VERIFICADO** | `dictado_revocado`, `test_*revocacion*`, live en `/interpretar` |

---

## 1. Matriz de requisitos

### 1.1 Conversación y correcciones

| Requisito | Estado | Componente | Prueba / evidencia |
|---|---|---|---|
| Relacionar cada mensaje con su solicitud | **PENDIENTE** | requiere M1 + hilo | contrato definido (D) |
| Corregir por texto o audio sin entrar al panel | **PARCIAL** | corrección por panel y por API; falta WhatsApp | `POST /borradores/{id}/corregir`; `cerebro_lab_correccion` |
| Mantener los datos no corregidos | **VERIFICADO** | `revision.aplicar` + cadena | `test_aplicar_no_toca_los_demas_hechos`; cadena v1→v2→v3 en vivo |
| Recuperar una conversación interrumpida | **PENDIENTE** | requiere hilo persistido | contrato (D) |
| Impedir que una confirmación vieja apruebe otra versión | **VERIFICADO** | `SUPERADO_POR_CORRECCION` | `test_*` de correcciones; respuesta 409 en vivo |
| Varias solicitudes sin mezclar datos | **PARCIAL** | acciones separadas por borrador; falta hilo | `Borrador` por extracción |
| Completar una instrucción por WhatsApp de punta a punta | **PENDIENTE** | fase siguiente | — |

### 1.2 Aprendizaje

| Requisito | Estado | Componente | Prueba / evidencia |
|---|---|---|---|
| Nivel 1: vocabulario de nombres y jerga | **VERIFICADO** | `cerebro_correcciones` + `v_cerebro_vocabulario` | `test_el_prompt_lleva_las_correcciones_aprendidas`; en vivo «Díaz Sur»→«Dualsur» |
| Nivel 1 con ámbito y no reemplazo ciego | **PARCIAL** | pares clave→valor; falta ámbito/contexto | `test_vocabulario_*` |
| Nivel 2: significado de expresiones («rebaja del cinco») | **PENDIENTE** | propuesta: sugerencia + confirmación | — |
| Nivel 3: lugares y referencias geográficas | **PENDIENTE** | requiere tabla de lugares | — |
| Evitar que un error humano contamine el aprendizaje | **VERIFICADO** | el humano es autoridad; el par se puede retirar | `test_retirar_un_par_equivocado_exige_motivo`; migración 090 |
| Retirar una asociación equivocada | **VERIFICADO** | `cerebro_vocabulario_retiros` | `test_el_vocabulario_excluye_los_pares_retirados`; en vivo |
| Medir si entiende mejor que la semana anterior | **PARCIAL** | informe lista correcciones; faltan tasas | `scripts/informe_cerebro_errores.py` |

### 1.3 Interpretación

| Requisito | Estado | Componente | Prueba / evidencia |
|---|---|---|---|
| Hechos con cita verificada | **VERIFICADO** | `extractor.construir_hechos` | `test_construir_hechos_rechaza_cita_ausente` |
| Distinguir afirmado / negado / tentativo / condicionado | **VERIFICADO** | `TENTATIVO` + guarda de negación | `test_un_descuento_negado_no_se_aplica_*`, `test_un_volumen_tentativo_*` |
| Datos modificados dentro del audio | **VERIFICADO** | último valor gana | `test_la_ultima_correccion_del_audio_es_la_que_manda` |
| Referencias ambiguas | **PARCIAL** | preguntas del compilador | `test_diaz_sur_pregunta_a_cual_de_los_dos_contactos` |
| Confianza de transcripción ≠ confianza de interpretación | **PARCIAL** | confianza por palabra + estado del hecho; no formalizado | `test_v86_voz_alineacion` |
| No bloquear todo por un dato faltante | **VERIFICADO** | propone lo que puede y pregunta lo que falta | Díaz Sur: propone cliente y pide obra |
| Preguntar sin obligar a regrabar | **VERIFICADO** | corrección por hecho | laboratorio `/panel/cerebro` |

### 1.4 Delegación

| Requisito | Estado | Componente | Prueba / evidencia |
|---|---|---|---|
| Separar instrucción, tarea, responsable, aviso, ejecución y cierre | **VERIFICADO** | borrador / tarea / ejecución / eventos | migraciones 085, 088, 090 |
| La tarea dice qué se espera, no solo copia el audio | **VERIFICADO** | ficha determinística | `test_la_ficha_resume_los_hechos_sin_redactar` |
| Ficha flexible para instrucciones informales | **VERIFICADO** | campos opcionales | `test_la_ficha_admite_una_instruccion_informal_sin_campos` |
| No crear una tarea financiera por mencionar una transferencia | **VERIFICADO** | la tarea nace de `tarea.*`, no de `pago.*` | `test_la_ficha_*`; Díaz Sur no propone abono |
| Intención antes que teléfono | **VERIFICADO** | `detectar_intencion_tarea` | `test_delegar_con_telefono_no_crea_un_whatsapp` |
| Enviar solo con número y permiso | **VERIFICADO** | recordatorios + roles | `test_enviar_a_una_persona_con_numero_sigue_siendo_whatsapp` |
| Devolver resultado explícito si el envío falla | **PARCIAL** | estado `FALLIDO` + `ultimo_error`; falta avisar a Julio | `gato_recordatorios` |

### 1.5 Notificaciones y seguimiento

| Requisito | Estado | Componente | Prueba / evidencia |
|---|---|---|---|
| Aviso, vista y acuse como eventos distintos | **VERIFICADO** | `vista_en`, `acusada_en`, eventos VISTA/ACUSADA | evidencia en vivo (guarda de tareas) |
| Acuse simple, sin nota | **VERIFICADO** | `POST /tareas-internas/{id}/acusar` | en vivo: estado sigue NOTIFICADA |
| Nota obligatoria al resolver o justificar | **VERIFICADO** | `resolver` | `test_las_transiciones_no_se_saltan_pasos` |
| Prioridad normal/urgente | **VERIFICADO** | `prioridad` + detector | migración 090; evidencia |
| Plazo configurable | **VERIFICADO** | `plazo_en` (2 h urgente / 24 h normal, o explícito) | evidencia |
| Orden por urgencia y vencimiento | **VERIFICADO** | `listar` | evidencia |
| Escalamiento por vencimiento | **VERIFICADO** | `POST /escalar` (SUPERADMIN) | evidencia |
| Saber si secretaría recibió el encargo | **VERIFICADO** | acuse | en vivo |
| No afirmar que se midió el trabajo de una persona | **VERIFICADO** | se mide tiempo **entre eventos** | este documento |

### 1.6 Integraciones y robustez

| Requisito | Estado | Componente | Prueba / evidencia |
|---|---|---|---|
| No duplicar tareas con la misma clave | **VERIFICADO** | `clave_externa` única | en vivo: `repetido: True` |
| No duplicar ejecuciones al confirmar dos veces | **VERIFICADO** | `cerebro_ejecuciones` + retorno `repetido` | `test_*` + código |
| Un fallo del módulo no borra la tarea | **VERIFICADO** | ejecución `FALLIDO` separada | `cerebro_ejecuciones` |
| Corregir no altera una acción ya ejecutada | **VERIFICADO** | corrección solo sobre borradores abiertos | 409 en vivo |
| Reconciliar un envío con estado desconocido | **NO VERIFICADO** | depende del proveedor | contrato (D) §6 |
| Reintento sin doble mensaje | **NO VERIFICADO** | requiere prueba con proveedor | contrato (D) §6 |

### 1.7 Seguridad del modelo

| Requisito | Estado | Componente | Prueba / evidencia |
|---|---|---|---|
| Esquema cerrado de claves | **VERIFICADO** | `sobre.py` + compilador | `test_una_clave_desconocida_no_tiene_efecto` |
| El audio no puede dar órdenes al sistema | **VERIFICADO** | el texto es dato; el compilador decide | `test_una_instruccion_citada_no_se_ejecuta`, `test_una_instruccion_maliciosa_queda_como_texto_de_la_tarea` |
| Negación dentro del audio no se ejecuta | **VERIFICADO** | guarda determinística | `test_un_descuento_negado_no_se_aplica_*` |
| Permisos por riesgo en el canal futuro | **PENDIENTE** | contrato (D) §5 | — |

---

## 2. Pruebas adversariales A–L

| Test | Estado | Dónde se demuestra |
|---|---|---|
| **A** corrección por voz en WhatsApp | **PENDIENTE** (existe por panel) | fase WhatsApp |
| **B** aprendizaje contextual | **PARCIAL**: nivel 1 sí | `test_el_prompt_lleva_las_correcciones_aprendidas` |
| **C** cotización incompleta | **PARCIAL**: pregunta; no delega el pendiente | Díaz Sur en vivo |
| **D** transferencia futura | **VERIFICADO**: no registra abono | guarda de dinero (`test_v87`) |
| **E** recordatorio programado | **VERIFICADO** (SANDBOX) | `test_v87` + cola |
| **F** revocación en el mismo audio | **VERIFICADO**: cambio de valor y cancelación completa | `test_la_ultima_correccion_*`, `test_la_revocacion_completa_*` |
| **G** cancelación posterior | **PARCIAL**: existe en Gato; no expuesto desde el Cerebro | `recordatorios.cancelar` |
| **H** fallo técnico | **PARCIAL**: no duplica; falta aviso | `cerebro_ejecuciones` |
| **I** aviso no atendido | **VERIFICADO**: vencida + escalada | evidencia |
| **J** asuntos múltiples | **PARCIAL**: acciones separadas; sin hilo | contrato (D) |
| **K** asociación aprendida equivocada | **VERIFICADO** | `test_retirar_un_par_equivocado_exige_motivo` |
| **L** instrucción maliciosa/citada | **VERIFICADO**: ni se ejecuta ni se delega | `test_una_instruccion_citada_y_negada_*` |
| **TENTATIVO** | **VERIFICADO** | `test_un_*tentativo*` |
| **INTENCIÓN** | **VERIFICADO** | `test_delegar_con_telefono_*` |
| **NOTIFICACIONES** | **VERIFICADO** | evidencia en vivo |
| **IDEMPOTENCIA** | **VERIFICADO** | evidencia en vivo §6 |

---

## 3. Evidencia reproducible

```powershell
docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto
docker compose run --rm --no-deps core-api python scripts/evidencia_tareas_internas.py
docker compose run --rm --no-deps core-api python scripts/informe_cerebro_errores.py --dias 7
```

- Suite: **586 pruebas en verde**.
- `.agents/evidencias/cerebro_tareas_internas_2026-11-15.txt`: aviso, vista,
  acuse, resolución, registro, escalada, idempotencia y retiro.
- `.agents/evidencias/cerebro_guarda_dinero_2026-11-15.txt`: dinero.
- `.agents/evidencias/cerebro_informe_errores_2026-11-15.md`: informe semanal.

---

## 4. Límites que este documento no esconde

1. **No hay conversación por WhatsApp todavía.** El Cerebro se usa por panel y
   por API. El contrato está escrito; la implementación es la fase siguiente.
2. **La interpretación no es 100 % determinística.** El prompt pide citas,
   estados y no inventar; el backend verifica, ignora lo tentativo y aplica
   guardas. Aun así, un modelo puede equivocarse de una forma que las guardas no
   cubran: por eso todo se confirma con un humano.
3. **El tiempo medido es entre eventos**, no tiempo de trabajo.
4. **Las pruebas adversariales del canal** (A, H, J) dependen de la fase de
   WhatsApp y de las credenciales reales.

---

## 5. Siguiente fase (condición de Dirección)

El siguiente hito de producto es **el Cerebro conversando con Julio por
WhatsApp**: audio, respuestas, correcciones, confirmaciones y la pregunta
«¿qué pasó con lo que le encargué ayer a secretaría?».

Prerrequisitos técnicos, en orden:

1. Persistir los mensajes entrantes de WhatsApp (hoy `chat_mensajes` no recibe
   los entrantes; M1 no los guarda).
2. Hilo de conversación y «asunto» por mensaje, según el contrato (D).
3. Reutilizar las mismas operaciones de corrección y confirmación que usa el
   panel: **un solo Cerebro, dos canales**.
4. Consulta de estado de tareas para responder «¿qué pasó con lo de ayer?».

---

## 6. Incremento 2026-11-16 — conservación de instrucciones

> **Origen.** Un audio espontáneo de Julio en `/panel/cerebro` (anticipo de USD
> 17.000, 250 m³ FC-240, ingeniero Julio Cartuche, la rectificación «la
> cotización, no la cotización, el recordatorio del pago», entrega contra pago,
> plazo de dos meses y encargo al expediente). La suite estaba en verde y aun
> así el borrador perdió parte del encargo. Corte anterior: 090 y 586 pruebas;
> ahora **091 y 601 pruebas**.

| # | Hallazgo | ¿Era falla? | Causa real | Corrección | Prueba |
|---|---|---|---|---|---|
| A | Se perdió el plazo de dos meses | **Sí** | El plazo vivía solo en los parámetros de `crear_cotizacion_borrador`. Sin dirección de obra la cotización no se arma, y con ella desaparecía el plazo. | `Condicion` + `condiciones_json` (091): el plazo se conserva aparte, con su cita, aunque no haya acción. | `test_el_plazo_no_se_pierde...` |
| B | No se conservó «entrega contra pago» | **Sí** | No existía clave ni condición para esa frase; el modelo no la extrajo. | Detección determinística sobre el texto (`entrega.contra_pago`), con la frase como cita. No crea acción de despacho. | `test_la_entrega_contra_pago...` |
| C | El encargo al expediente no apareció | **Sí** | Tampoco existía clave; el LLM no lo extrajo y no había respaldo. | Condición `expediente.completar` + tarea interna para secretaría con la instrucción copiada y nota de qué falta verificar. | `test_el_encargo_al_expediente...` |
| D | El recordatorio usaba la frase dictada como mensaje | **Sí** | El compilador copiaba `tarea.mensaje` a `mensaje` sin distinguir instrucción de mensaje final. | Se separan `instruccion` y `mensaje`; `mensaje_por_confirmar` exige texto autorizado al confirmar (`MENSAJE_POR_CONFIRMAR`). | `test_el_recordatorio_no_hereda...`, `test_confirmar_sin_mensaje_final...` |
| E | `tarea.cuando = ahora` sin hora dictada | **Parcial** | La inferencia era correcta pero no pedía aceptación explícita. | `programado_inferido` ahora exige `enviar_ahora` al confirmar (`CONFIRMAR_ENVIO_INMEDIATO`). | `test_confirmar_sin_aceptar_envio...` |
| F | `pago.recibido = no` sin declaración expresa | **Sí** (de redacción) | El LLM infirió «no recibido» de «el pago que tiene que hacernos» y se leía como estado financiero. | Si no hay negación explícita, el hecho baja a `INFERIDO` y el resumen dice «sin ingreso confirmado». Si se declara, dice «que todavía no entra». | `test_pago_no_recibido_sin_negacion...` |
| G | «Programado» con confirmación pendiente | **No** | La secuencia es correcta: el recordatorio se creó en la misma petición de confirmación (00:21:46), 19 s después del borrador (00:21:27), no antes. Lo confuso era la etiqueta: el borrador seguía en `REQUIERE_ACLARACION`. | La respuesta expone `confirmado_parcial` y `preguntas_pendientes`; la UI dice «Programado · quedan preguntas». | Evidencia SQL en `.agents/evidencias/cerebro_conservacion_2026-11-16.txt` |

**Hallazgo extra (recompilación).** Al recompilar el mismo sobre, un dato de
texto podía rechazarse porque el verificador comparaba el valor contra el texto
normalizado («2 meses») y no contra la cita cruda («dos meses»). Corregido:
la cita cruda también sostiene el hecho.

**Prueba de conservación.** `scripts/evidencia_conservacion.py` toma el dictado
real de la base, rehace los hechos sin LLM, recompila y compara
*dictado → hechos → resumen → acciones y condiciones*. Resultado:
`CONSERVACION: OK — ninguna instrucción relevante se perdió` (10 de 10).

**Lo que sigue sin existir.** La confirmación por el mismo chat de WhatsApp
(requiere persistir entrantes y autorizar por riesgo, no solo por número), la
conexión Gato–Cerebro y el flujo externo. No se tocaron.

---

## 7. Incremento 2026-11-16 — tres encargos independientes

> **Origen.** Criterio de aceptación del laboratorio: un dictado con tres
> asuntos («primero… segundo… tercero…»), corregir uno, cancelar otro y
> confirmar el tercero. Corte anterior: 091 y 601 pruebas; ahora **092 y 610**.

**Lo que se encontró (antes de corregir).** El motor trataba el dictado como un
solo asunto. Con el texto real produjo **una** acción (`crear_tarea_interna`),
perdió el tercer encargo, convirtió el recordatorio externo al ingeniero en
tarea interna porque la palabra «secretaría» del primer encargo teñía todo el
texto, y el resumen mezcló datos de dos asuntos. No era un caso de prompt: la
estructura de hechos no representaba varios asuntos.

| # | Cambio | Estado | Dónde |
|---|---|---|---|
| 1 | Segmentación determinística del dictado por ordinales | **VERIFICADO** | `cerebro/encargos.py` |
| 2 | `encargo` en cada hecho; el hecho se asigna por su cita | **VERIFICADO** | `HechoCitado.encargo`, `construir_hechos` |
| 3 | Cada encargo se compila con **su propio texto** (sin contaminación) | **VERIFICADO** | `compilar()` + `_compilar_asunto` |
| 4 | Estado, acciones y preguntas por encargo | **VERIFICADO** | `EncargoResumen`, `encargos_json` (092) |
| 5 | Corrección dirigida a un encargo; clave repetida exige indicar cuál | **VERIFICADO** | `CorregirIn.encargo`, `ENCARGO_AMBIGUO` |
| 6 | Cancelación por encargo, append-only, con motivo y autor | **VERIFICADO** | `cerebro_encargos_decisiones`, `POST …/encargos/{n}/cancelar` |
| 7 | Confirmar un encargo cancelado se rechaza | **VERIFICADO** | `ENCARGO_CANCELADO` |
| 8 | Cancelar un recordatorio ya **PENDIENTE** lo cancela; si ya se **ENVIÓ**, avisa | **VERIFICADO** | `ENCARGO_YA_ENVIADO`, `recordatorios.cancelar` |
| 9 | Cifras dictadas se propagan a la guarda del mensaje | **VERIFICADO** | `cifras_autorizadas` en el recordatorio |
| 10 | Estado real por encargo (propuesto / pendiente / confirmado / ejecutado / cancelado) | **VERIFICADO** | `estado_actual` en `GET /borradores/{id}` |

**Prueba de aceptación (ejecutada en vivo, SANDBOX).**

| Encargo | Decisión | Resultado real |
|---|---|---|
| A — revisar medidas / 30 m³ FC-240 | Corregido a 35 m³ | versión 2, hecho `CORREGIDO_POR_HUMANO`; no se ejecutó nada |
| B — recordatorio al ing. Mauricio | Cancelado | decisión registrada; **sin** recordatorio pendiente ni enviado |
| C — revisar despachos | Confirmado | **una** tarea interna para secretaría; repetir la confirmación no duplica |

Evidencia: `.agents/evidencias/cerebro_encargos_2026-11-16.txt`
(`ENCARGOS: OK — tres asuntos independientes, sin mezcla`) y
`.agents/evidencias/cerebro_v84_...` para las guardas.

**Dependencia de la siguiente fase (no implementada).** El encargo vive dentro
de un dictado. Sostener «cancela el segundo» en **otro** audio exige conversación
persistida con asuntos e hilos; eso pertenece a la fase conversacional y no se
simuló aquí.
