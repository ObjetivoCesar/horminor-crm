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
