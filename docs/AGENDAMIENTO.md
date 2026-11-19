# Agendamiento — citas comerciales

> **Estado:** **implementado 2026-11-19** (migraciones 096 y 097,
> `app/comercial/citas.py`). La agenda de **entregas** sigue separada.
>
> **Dueño del tema:** este archivo.
>
> **Relacionado:** `docs/NUCLEO_COMERCIAL.md` (contrato de uso) y
> `docs/LEADS.md` (origen del lead).

## 1. Lo que ya existía (no se reconstruye)

| Pieza | Dónde | Qué resuelve |
|---|---|---|
| `dispatch_schedule` | migración 067 | Agenda de **entregas** y ocupación de mixers |
| Configuración de agenda | migración 068 | Horarios de planta y reglas |
| `HorminorAgenda` | panel | Vista de la agenda de entregas |
| Recordatorios de Gato | `app/asistente/recordatorios.py` | Avisos por WhatsApp |

La cita **comercial** (visita, reunión, medición) vive en `citas`; la entrega
de hormigón no se movió.

## 2. Modelo implementado (migración 096)

```sql
CREATE TABLE citas (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cliente_id      uuid REFERENCES clients(id) ON DELETE SET NULL,
    lead_id         uuid REFERENCES leads(id) ON DELETE SET NULL,
    tipo            text NOT NULL CHECK (tipo IN ('VISITA','REUNION','MEDICION','ENTREGA')),
    fecha           date NOT NULL,
    hora_inicio     time NOT NULL,
    duracion_min    integer NOT NULL DEFAULT 60,
    estado          text NOT NULL DEFAULT 'SOLICITADA'
                    CHECK (estado IN ('SOLICITADA','CONFIRMADA','REALIZADA',
                                      'CANCELADA','REAGENDADA')),
    origen          text NOT NULL CHECK (origen IN ('PANEL','WHATSAPP','GATO','MIAU')),
    solicitada_por  text,
    notas           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
```

La auditoría vive en **`cita_eventos`** (migración 097): `cita_id`, `tipo`,
`detalle` (JSONB), `actor` y `created_at`, con trigger append-only. Si la cita
se elimina, el evento sobrevive con `cita_id = NULL`.

## 3. Reglas implementadas

1. **Origen fijado por el servidor:** el panel crea con `PANEL`, Gato con
   `GATO` y el webhook de WhatsApp con `WHATSAPP`. El cuerpo no acepta `origen`.
2. **Gato solo solicita.** La cita nace `SOLICITADA`; confirmar es una acción
   humana (panel) o de la regla que defina Julio. Gato público no confirma.
3. **Máquina de estados:**

   | Desde | Puede pasar a |
   |---|---|
   | `SOLICITADA` | `CONFIRMADA`, `CANCELADA`, `REAGENDADA` |
   | `CONFIRMADA` | `REALIZADA`, `CANCELADA`, `REAGENDADA` |
   | `REAGENDADA` | `CONFIRMADA`, `CANCELADA` |
   | `REALIZADA` | — (final) |
   | `CANCELADA` | — (final) |

   No se confirma una cita cancelada ni se realiza una sin confirmar.
4. **Choque del mismo lead o cliente:** se rechaza si se solapa con otra cita
   del mismo `lead_id` o `cliente_id` (misma fecha, intervalos de
   `duracion_min`). **No** se inventa capacidad global ni se valida contra la
   agenda de entregas.
5. **Cancelación con motivo:** `POST /citas/{id}/cancelar` acepta `motivo` y lo
   guarda en `cita_eventos`.
6. **Fecha de Ecuador:** `app/tiempo.py` (`America/Guayaquil`).
7. **Visibilidad:** las citas comerciales se ven en **Secretaría → Leads y
   citas → Citas** y por `GET /api/v1/comercial/citas`. No se muestran en
   `HorminorAgenda` (agenda operativa de entregas); si Julio las quiere allí,
   es trabajo de H4/UX, no de este módulo.

## 4. API implementada

| Método | Ruta | Para qué |
|---|---|---|
| `GET` | `/api/v1/comercial/disponibilidad?fecha=` | Citas del día + horario configurado |
| `GET` | `/api/v1/comercial/citas?fecha=\|desde=` | Listar citas |
| `POST` | `/api/v1/comercial/citas` | Crear (panel / Gato / WhatsApp) → `SOLICITADA` |
| `POST` | `/api/v1/comercial/citas/{id}/confirmar` | Confirmar (persona) |
| `POST` | `/api/v1/comercial/citas/{id}/cancelar` | Cancelar con `motivo` |

`disponibilidad` **no calcula huecos libres**: devuelve las citas del día y el
horario configurado (`agenda.citas_horario_inicio/fin`, `agenda.citas_duracion_min`).
Si esos valores faltan, responde `horario_configurado: false`; no inventa un
horario.

## 5. Pendiente de decisión (no se inventa)

- Horario de atención y duración por tipo de cita (hoy quedan `NULL` si Julio
  no los cargó).
- Quién confirma: siempre una persona o hay confirmación automática.
- Si Gato puede ofrecer horarios o solo tomar la solicitud.
- Si las citas comerciales deben verse también en la agenda operativa.
