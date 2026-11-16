# Router conversacional del Cerebro — cierre de fase

> **Estado:** cerrado el 2026-11-16. Se conserva como está; no se amplía.
> **Versión estable:** `router-1.7`.
> **Ubicación:** `experiments/router_horminor/` (prototipo aislado).
> **Alcance:** laboratorio de desarrollo. **No está conectado al CRM operativo.**

Este documento explica qué es el router, cómo está armado, cómo se corrigen los
encargos, qué garantiza, qué no hace y qué queda pendiente. Es el punto de
entrada para retomarlo dentro de seis meses sin releer el historial del chat.

---

## 1. Qué es y para qué existe

El router conversacional es la pieza que escucha a Julio en lenguaje natural,
separa sus instrucciones en encargos independientes, propone un responsable,
pide solo las aclaraciones necesarias y entrega un plan que Julio confirma o
corrige. **Nada se ejecuta:** al confirmar se muestra el plan de lo que se
crearía.

Existe para probar, sin tocar el CRM ni conectar Gato, si el Cerebro puede
trabajar como asistente de dirección: útil, corregible y comprensible, no
infalible.

**Decisión de cierre:** la arquitectura se detiene aquí. Los errores que
aparezcan se resuelven con el sistema de correcciones ya construido, no con un
rediseño.

---

## 2. Componentes

| Componente | Archivo | Qué hace |
|---|---|---|
| Lectores | `router.py` (`_leer_hechos`, `_leer_trabajo`, `_leer_restricciones`) | Tres lecturas independientes del dictado: hechos, trabajo pedido y restricciones/condiciones |
| Reconciliador | `router.py` (`construir`) | Une las tres lecturas con reglas fijas; descarta lo que no tiene cita; arma el borrador |
| Borrador | `model.py` (`BorradorRouter`, `Encargo`) | Encargos, preguntas, notas, datos de contexto y versión |
| Resumen | `router.py` (`resumen_conversacional`) | Mensaje natural para Julio, con viñetas y sin jerga técnica |
| Conversación | `conversacion.py` | Distingue confirmación de corrección y redacta la respuesta |
| Corrección | `correccion.py` | Aplica cambios de campo, resuelve cliente y destinatarios, responde aclaraciones |
| Plan | `confirmacion.py` | Convierte el borrador confirmado en plan y verifica correspondencia |
| Traza | `errores.py` + `evidencias/errores.jsonl` | Registro append-only de aclaraciones y correcciones con antes/después |
| Laboratorio | `lab.py` | Interfaz interna de diagnóstico en `http://localhost:8055` |
| Pruebas | `tests_core.py` | 21 pruebas determinísticas del router |
| Congelado | `congelar.py` + `VERSION.json` | Hashes de la versión estable |

**Los prompts** viven en `prompts.py` (lectores y corrección). El router usa un
cliente LLM compartido con el experimento D/D+ (`experiments/d_vs_dmas/llm.py`).

---

## 3. Flujo

```
Dictado de Julio (texto)
        │
        ▼
Tres lecturas en paralelo: hechos · trabajo · restricciones
        │
        ▼
Reconciliador determinístico: descarta citas falsas, separa encargos,
asigna responsable sugerido, deja preguntas y datos por investigar
        │
        ▼
Borrador v1 + resumen natural para Julio
        │
        ├── Julio responde: aclaración → actualiza datos y retira preguntas
        ├── Julio responde: corrección → cambia el campo citado, deja el resto
        ├── Julio responde: confirmación → plan + verificación de correspondencia
        └── Julio cancela → borrador cerrado; nada se ejecuta
        │
        ▼
Cada cambio genera una versión nueva y una entrada en la traza (antes/después)
```

### Reglas que sostienen el comportamiento

1. **Cita o no existe.** Un dato sin cita textual se descarta.
2. **Autorización literal.** Solo «envíalo», «mándalo» o «autorizo» autorizan un
   envío; una paráfrasis del modelo no.
3. **Condición literal.** Una restricción se conserva solo si la cita trae
   «hasta que», «antes de», «depende» o «condicionado».
4. **Falta de datos investigables.** No se pregunta lo que el responsable puede
   averiguar: va a «por investigar».
5. **Responsable propuesto.** Si el dictado no nombra área, se propone jefe de
   planta o secretaría según el tipo de trabajo, marcado como sugerencia.
6. **Pago esperado no es pago recibido**; preparar un mensaje no es enviarlo;
   crear una tarea de despacho no autoriza un camión.

---

## 4. Cómo se corrigen los encargos

Julio escribe en la caja de respuesta del laboratorio, en lenguaje natural. No
elige campos ni códigos.

| Lo que escribe | Lo que hace el sistema |
|---|---|
| «El volumen es 42, la resistencia 210 y el anticipo está confirmado» | Actualiza los datos, retira esas preguntas y registra una `ACLARACION` |
| «No es Díaz Sur, es DIALSUR, y notifícales a los dos» | Cambia el cliente, ajusta destinatarios y conserva el resto |
| «Donde dije bomba era la mezcladora» | Cambia solo ese campo; no toca los demás encargos |
| «Cancela el tercer encargo» | Marca ese encargo como cancelado; los otros siguen |
| «Sí, confirmo» | Devuelve el plan y verifica que corresponda al borrador |

**Trazabilidad:** cada aclaración o corrección se agrega a
`evidencias/errores.jsonl` con mensaje de Julio, campos cambiados, versión antes
y versión después. El archivo es append-only: no se borra ni se reescribe.

---

## 5. Qué funciona hoy (laboratorio)

- Interpretar un dictado de varios asuntos y separarlo en encargos.
- Proponer responsable y marcar la propuesta como sugerida.
- Convertir conflictos del dictado en preguntas concretas con opciones.
- Responder varias aclaraciones en un solo mensaje.
- Corregir un encargo sin tocar los demás.
- Cancelar un encargo y confirmar el resto.
- Ver el plan final sin crear nada.
- Dejar traza de cada aclaración y corrección.
- Conservar el dictado y el último borrador al refrescar la página.

**Evidencia:** 21/21 pruebas del router y las pruebas manuales registradas en
`docs/AUDITORIA_PRUEBAS_MANUALES_2026-11-16.md`.

---

## 6. Qué no hace (y no se amplía en esta fase)

- **No está conectado al CRM.** No crea clientes, cotizaciones, tareas ni
  recordatorios. No escribe en la base.
- **No envía mensajes** ni autoriza despachos. Gato sigue desconectado.
- **No mantiene un hilo entre dictados.** Cada dictado es un borrador nuevo; la
  memoria conversacional es de otra fase.
- **No registra el dictado ni el mensaje mostrado.** La traza guarda
  correcciones y aclaraciones, no la conversación completa.
- **Confirmaciones sin corrección no dejan rastro** en la traza.
- **Las órdenes nuevas dentro de una respuesta se pierden** (por ejemplo,
  «prepara la cotización» después de confirmar un volumen).
- **Un cambio con antes = después** puede registrarse como corrección aplicada.
- **La preferencia de canal** («llamada, no WhatsApp») queda como texto en la
  condición, no como atributo del encargo.
- **Las pruebas automáticas escriben en la misma traza** que las pruebas
  manuales.

Estas limitaciones quedan documentadas y **no se resuelven ahora**. Se
atenderán de forma progresiva si las conversaciones reales lo justifican.

---

## 7. Laboratorio frente a uso operativo

| Aspecto | Laboratorio (`:8055`) | CRM operativo |
|---|---|---|
| Dónde vive | `experiments/router_horminor/` | `services/core-api/app/cerebro/` |
| Quién lo usa | Equipo técnico, para diagnosticar | Julio y secretaría (futuro) |
| Qué escribe | JSON en memoria y traza de errores | Base de datos del CRM |
| Qué ejecuta | Nada: solo propone | Tareas, recordatorios y avisos |
| Canal | Página local | Panel y, más adelante, Gato |
| Estado | **Cerrado, se conserva** | Sigue con V07; sin cambios |

`/panel/cerebro` **no** ejecuta este router: hoy corre la versión anterior del
motor. El router no se ha integrado al panel y **no se integrará en esta fase**.
Tanto el laboratorio como `/panel/cerebro` son instrumentos internos de
diagnóstico; no representan la experiencia final del usuario.

---

## 8. Cómo verificar que sigue funcionando

Desde `orminorth/`:

```powershell
# pruebas del router (21)
python -m experiments.router_horminor.tests_core

# laboratorio local (uso interno)
python -m experiments.router_horminor.lab
# abrir http://localhost:8055

# suite del CRM (620)
docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto

# hashes de la versión estable
python -m experiments.router_horminor.congelar
```

**Versión congelada:** `router-1.7`. Los hashes están en `VERSION.json`; si un
archivo cambia, los hashes dejan de coincidir y eso es la señal de que la
versión ya no es la auditada.

---

## 9. Backlog (sin fecha, sin compromiso)

### Evaluar Jev, de TypeSafe AI

**Idea:** evaluar a Jev (TypeSafe AI) como posible clasificador o verificador
especializado de:

- intención de cada frase;
- responsable correcto;
- órdenes nuevas dentro de una respuesta;
- malentendidos conversacionales.

**Estado:** idea registrada. **No implementada. No integrada. Sin fecha.**

**Condición para retomarla:** que las conversaciones reales muestren una
necesidad que el router actual no cubra y que el sistema de correcciones no
resuelva de forma aceptable. Hasta entonces, no se evalúa, no se contrata y no
se toca el código.

---

## 10. Reglas de conservación

1. **No ampliar** el router en esta fase: sin analizadores, reglas, interfaces
   ni cambios de arquitectura nuevos.
2. **Corregir por la vía existente**: la caja de respuesta y la traza.
3. **Conservar el historial** de errores y correcciones; es la materia prima de
   las mejoras futuras.
4. **Gato sigue desconectado**; sin mensajes externos, operaciones financieras
   ni despachos automáticos.
5. **No desarrollar más interfaces**: el laboratorio y `/panel/cerebro` son
   instrumentos internos.
6. **Una regresión se informa, no se rediseña.**

---

## 11. Bitácora del documento

| Versión | Fecha | Cambio |
|---|---|---|
| v1 | 2026-11-16 | Cierre de fase: componentes, flujo, correcciones, límites, laboratorio frente a operación y backlog de Jev. |
