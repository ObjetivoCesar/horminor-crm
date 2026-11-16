# WhatsApp interno del Cerebro — secuencia de implementación

> **Para qué sirve.** Convertir el laboratorio validado en el canal por el que
> Julio y secretaría conversan con el Cerebro, sin abrir nada al cliente ni
> reconstruir el CRM.
>
> **Estado:** plan técnico. **No implementado.** Fecha: 2026-11-16.
> **Contrato de datos:** `docs/CONTRATO_WHATSAPP_CEREBRO.md`.
> **Arquitectura:** `docs/CONTINUIDAD_CEREBRO.md` §2.

---

## 1. Principio que no se negocia

La separación entre flujo interno y comercial es **técnica**: permisos,
herramientas y fuentes de datos distintos. El prompt no es un control de
seguridad. Un número de teléfono **identifica**, no autoriza una operación
sensible.

```
WhatsApp Evolution
   └─ webhook (M1) ──► clasificador de canal
                         ├─ INTERNO (Julio / secretaría autorizados)
                         │    └─ Cerebro: interpretar → resumen → corregir →
                         │       confirmar → tarea/consulta
                         └─ EXTERNO (cliente)
                              └─ flujo comercial limitado (otra fase)
```

Si el remitente no está en la lista interna autorizada, **no** entra al Cerebro:
va al flujo comercial o a un humano.

## 2. Qué ya existe (dependencias verificadas)

| Pieza | Estado | Dónde |
|---|---|---|
| Interpretación con hechos citados y encargos | Verificado | `POST /api/v1/cerebro/interpretar` |
| Corrección versionada | Verificado | `POST /borradores/{id}/corregir` |
| Confirmación con mensaje y momento autorizados | Verificado | `POST /borradores/{id}/confirmar` |
| Cancelación por encargo | Verificado | `POST /borradores/{id}/encargos/{n}/cancelar` |
| Tareas internas con aviso, vista, acuse y cierre | Verificado | `cerebro_tareas_internas`, `/panel` |
| Idempotencia por clave externa | Verificado | `gato_recordatorios.clave_idempotencia`, `cerebro_tareas_internas` |
| Auditoría append-only | Verificado | `cerebro_ejecuciones`, `cerebro_correcciones`, `cerebro_encargos_decisiones` |
| Ingesta de audio y STT (Groq/Whisper) | Verificado | `POST /api/v1/voz/transcribir` |
| ACL por módulo (`voz`, `cerebro`) | Verificado | `panel_users_acl`, `exigir_modulo` |
| Webhook de Evolution con debounce e identidad | Verificado en SANDBOX | `app/m1_whatsapp/` |
| Mensajes entrantes persistidos | **NO** | M1 los procesa y no los guarda |
| Hilo/asunto por conversación | **NO** | el encargo vive dentro de un dictado |
| Autorización por riesgo del remitente | **NO** | solo existe la identidad por número/rol |

## 3. Secuencia técnica (cada paso con su compuerta)

### Paso 0 — Persistir entrantes (base de todo)
- **Qué:** guardar cada mensaje entrante (texto, audio, tipo, `whatsapp_msg_id`,
  remitente, conversación) antes de procesarlo.
- **Dónde:** M1; tablas `chat_conversaciones`/`chat_mensajes` ya existen.
- **Dependencias:** ninguna nueva.
- **Compuerta:** reenviar el mismo mensaje no duplica; el adjunto conserva su
  `media_asset`.
- **Por qué primero:** sin entrantes no hay hilo, ni corrección posterior, ni
  auditoría del canal.

### Paso 1 — Clasificador de canal y remitente
- **Qué:** resolver remitente → `panel_users_acl` (rol y permisos) y decidir
  canal INTERNO / EXTERNO. Desconocido → humano.
- **Dónde:** M1, antes del Cerebro.
- **Dependencias:** directorio de teléfonos ya editable desde Superadmin.
- **Compuerta:** un número no autorizado no alcanza ninguna ruta `/cerebro`;
  el rechazo queda registrado.

### Paso 2 — Autorización por riesgo (no solo por número)
- **Qué:** clasificar la acción por riesgo. Consultas y tareas internas: la
  identidad basta. Dinero, envío externo o cancelación sensible: exigir
  confirmación adicional (código de un solo uso al panel, o doble confirmación
  ya existente) y ventana de validez.
- **Dónde:** guarda previa a `confirmar`; reutiliza la doble confirmación.
- **Dependencias:** Paso 1.
- **Compuerta:** un mensaje desde un número conocido pero sin la segunda prueba
  **no** ejecuta una acción sensible.

### Paso 3 — Hilo y asunto entre mensajes
- **Qué:** cada conversación tiene asuntos abiertos (los `encargo` del
  laboratorio) con su borrador vigente; un mensaje nuevo puede referirse a uno
  («cancela el segundo», «corrige los metros»).
- **Dónde:** tabla de asuntos por conversación, enlazada a `cerebro_borradores`.
- **Dependencias:** Pasos 0 y 1.
- **Compuerta:** dos asuntos del mismo hilo no comparten hechos; una corrección
  a un asunto no cambia el otro (ya probado dentro de un dictado).
- **Riesgo:** es la pieza que hoy **no existe**; sin ella solo se puede
  interpretar un audio aislado y responder con su resumen.

### Paso 4 — Respuesta en lenguaje natural
- **Qué:** devolver el resumen por encargo, las preguntas y el estado, con las
  etiquetas ya acordadas (propuesto, pendiente, confirmado, acciones ejecutadas,
  notificado, resuelto, registrado).
- **Dónde:** un redactor determinístico a partir del borrador; el LLM no decide
  estados.
- **Dependencias:** Pasos 0–3.
- **Compuerta:** la respuesta no afirma que el trabajo está hecho cuando solo se
  creó la tarea.

### Paso 5 — Confirmación y corrección por chat
- **Qué:** «sí», «dale», «corrige a 35», «cancela el de Mauricio» operan sobre
  la **versión vigente** del asunto, con las mismas guardas del panel.
- **Dependencias:** Pasos 3 y 4.
- **Compuerta:** confirmar dos veces no duplica; una versión superada no se
  puede confirmar; cancelar un encargo no cancela el dictado.

### Paso 6 — Consulta de estado del CRM
- **Qué:** «¿qué pasó con lo de ayer?», «¿cómo van los despachos?» usando el
  bibliotecario de solo lectura y las consultas nombradas, con ACL.
- **Dependencias:** Paso 1 (rol) y catálogo de consultas existente.
- **Compuerta:** el resultado respeta el ACL; sin dato, responde «no consta».

### Paso 7 — Aislamiento del flujo comercial
- **Qué:** el flujo externo no comparte proceso, herramientas ni fuentes con el
  interno. Sin acceso a memoria, cartera, pagos, expedientes ni tareas.
- **Dependencias:** Pasos 1 y 2.
- **Compuerta:** una prueba adversarial demuestra que un mensaje externo no
  puede invocar ninguna herramienta interna, ni por texto ni por inyección.

## 4. Orden, dependencias y qué se puede paralelizar

```
0 entrantes ─► 1 canal/rol ─► 2 riesgo ─► 5 confirmar/corregir
                    │                         ▲
                    └─► 3 hilo/asunto ─► 4 respuesta ─┘
                                              │
                                              └─► 7 aislamiento externo
6 consultas CRM (paralelo a 3–5, depende de 1)
```

Los pasos 0 y 6 pueden empezar en paralelo. El 7 no debe esperar al 5: conviene
escribir primero la prueba adversarial de aislamiento.

## 5. Lo que NO se hace en esta fase

- Conectar Gato como interfaz ni cambiar sus herramientas.
- Redactar mensajes comerciales externos con el LLM.
- Dar por buena la identidad por número para dinero o envíos.
- Sustituir el panel: WhatsApp es un canal del mismo Cerebro, no otro Cerebro.

## 6. Decisiones pendientes del cliente

1. Qué teléfonos son de Julio y de secretaría (datos reales, no semilla).
2. Qué segundo factor acepta para acciones sensibles.
3. Qué resumen exacto se entrega al transferir una conversación externa.
4. Retención y consentimiento de audio (LOPDP).
