# Núcleo comercial — contrato de uso

> **Dueño del tema:** este archivo.
> **Regla que no se negocia:** leads y citas tienen **un solo dueño**: el módulo
> comercial (`/api/v1/comercial/*`). El panel, Gato y WhatsApp **no** crean
> leads ni citas por su cuenta: **piden** y el módulo decide.
>
> Relacionado: `docs/HITOS.md` (H1), `docs/LEADS.md` (reglas),
> `docs/AGENDAMIENTO.md` (citas).

## 1. La regla

Los consumidores solo dicen **"dame / notifícame / agenda a…"**. No calculan
estados, no comparan fechas, no escriben SQL del módulo.

| Consumidor | Qué puede pedir | Qué NO hace |
|---|---|---|
| **Panel (Secretaría)** | Listar leads y citas, crear lead, crear cita, confirmar/cancelar | No decide reglas ni fechas |
| **Gato interno (Miau)** | "dame los leads caídos", "agenda una visita a…" | No escribe en `leads` ni en `citas` |
| **Gato público (WhatsApp)** | "registra a este número", "solicita una cita" | No confirma citas ni ve contexto interno |
| **Webhook de WhatsApp** | Entregar el mensaje al módulo | No crea leads por su cuenta |

## 2. Interfaz

- `GET /api/v1/comercial/hoy` — la fecha de negocio (servidor, `America/Guayaquil`).
- `POST /api/v1/comercial/leads` — crear o reutilizar por teléfono. **Nace
  `CONTACTO`**; el origen lo pone el servidor (`PANEL` en esta ruta).
- `POST /api/v1/comercial/leads/{id}/respuesta` — **la empresa respondió**: nace
  el `LEAD` (marca la primera respuesta).
- `POST /api/v1/comercial/leads/{id}/mensaje` — **mensaje del lead**: aplica las
  reglas de intención (`lead_reglas_caida`) y revive un `CAIDO`/`EN_ESPERA`.
- `POST /api/v1/comercial/leads/{id}/estado` — cambio manual de estado; una
  persona puede revertir lo que propuso el sistema.
- `GET /api/v1/comercial/leads?estado=` — listar por estado.
- `POST /api/v1/comercial/citas` — crear la **solicitud** (`SOLICITADA`).
- `POST /api/v1/comercial/citas/{id}/confirmar|cancelar` — transición de estado;
  cancelar guarda `motivo`.
- `GET /api/v1/comercial/citas?fecha=|desde=` y `GET /api/v1/comercial/disponibilidad`.

**Origen** (`WHATSAPP`, `GATO`, `PANEL`) es un dato que **fija el servidor**
según la puerta de entrada. No se acepta en el cuerpo (`LeadIn`/`CitaIn` usan
`extra="forbid"`: enviarlo devuelve 422). Así el panel no puede etiquetar un
lead como si viniera de WhatsApp.

**Dos hechos distintos, no uno:**

| Hecho | Ruta | Efecto |
|---|---|---|
| La **empresa** responde | `/respuesta` | Nace el `LEAD` si era `CONTACTO`; el texto de la empresa no aplica reglas de caída |
| El **lead** escribe | `/mensaje` | Aplica intención; si estaba `CAIDO` o `EN_ESPERA`, revive a `LEAD` |

**Citas:** `SOLICITADA → CONFIRMADA → REALIZADA`, con `CANCELADA` y
`REAGENDADA` como salidas válidas. Se rechaza el solapamiento del **mismo lead o
cliente**; no se inventa capacidad global. Cada transición deja fila en
`cita_eventos` (append-only, migración 097).

## 3. Prohibiciones

1. **Nada de fechas locales** en el consumidor: siempre `app/tiempo.py` o
   `GET /comercial/hoy`.
2. **Nada de SQL** de `leads` o `citas` fuera del módulo.
3. **Nada de lógica duplicada** de caída, recontacto o confirmación.
4. **Nada de crear un lead por cada mensaje**: el módulo reutiliza por teléfono.
5. **Nada de confirmar una cita desde Gato público**: solo solicita.

## 4. Cómo se conecta cada uno

- **Panel:** `cargarComercial()` llama a la API y pinta; los formularios no
  envían `origen` (el servidor los registra como `PANEL`).
- **Gato interno:** usa el módulo con origen `GATO`; si falta un dato, pregunta.
- **Gato público / WhatsApp:** usa el módulo con origen `WHATSAPP` para
  registrar y solicitar; no confirma.
- **Webhook:** `ComercialWhatsApp` entrega el mensaje; la decisión de crear el
  lead es del módulo (regla: al menos una respuesta de la empresa). El webhook
  no hace `INSERT` en `leads` ni en `citas`.

| Consumidor | Puerta | Origen que fija el servidor |
|---|---|---|
| Panel | `POST /leads` y `POST /citas` | `PANEL` |
| Gato interno | `app/asistente/comercial_bridge.py` | `GATO` |
| WhatsApp | `app/comercial/whatsapp.py` | `WHATSAPP` |

## 5. Checklist antes de tocar esto

- [ ] ¿Estoy llamando a la API o reimplementando la regla?
- [ ] ¿La fecha sale del servidor?
- [ ] ¿El origen está bien puesto?
- [ ] ¿Estoy confirmando una cita desde donde no se debe?
- [ ] ¿La UI muestra estados del módulo o inventa los suyos?
