# Leads — protocolo y ciclo de vida

> **Qué es.** Cómo nace un lead desde WhatsApp, cuándo deja de ser un simple
> contacto, cómo se convierte en cliente y qué pasa con los leads caídos.
>
> **Dueño del tema:** este archivo. Si cambia una regla, se actualiza aquí y se
> borra lo que dejó de ser cierto.
>
> **Estado:** **implementado 2026-11-19** (migración 096, `app/comercial/leads.py`).
> Las cifras de recontacto siguen `NULL` hasta que Julio las defina.
>
> **Relacionado:** `docs/MOMENTO_CERO.md` (convertir lead en cliente),
> `docs/CONTINUIDAD_CEREBRO.md` (Gato público vs Miau interno).

---

## 1. Definiciones

| Término | Qué es |
|---|---|
| **Contacto** | Un número que escribió por primera vez. Todavía no es lead: solo hay un entrante. |
| **Lead** | Contacto **con al menos una respuesta de la empresa**. Es la primera regla y no se negocia. |
| **Lead calificado** | Dio nombre, interés, obra o volumen; hay algo concreto para ofrecer. |
| **Cliente** | Contrato cerrado y momento cero ejecutado (carpeta + cliente en el CRM). |
| **Lead caído** | Lead que no avanzó en el plazo definido. Se etiqueta y se recontacta. |

---

## 2. Protocolo de creación

```
mensaje entrante de un número desconocido
  → el módulo crea el CONTACTO (origen lo fija el servidor)
  → la empresa responde (Gato automático o una persona)   → nace el LEAD
  → el lead vuelve a escribir                             → se registra el mensaje
      → si trae una señal de intención (rechazo, precio, aplazamiento…) se aplica
      → si no trae señal y estaba CAIDO o EN_ESPERA, revive a LEAD
  → si nadie responde nunca: queda CONTACTO sin respuesta (no es lead)
```

**Dos hechos separados (no uno):**

| Hecho | Función | Efecto |
|---|---|---|
| La **empresa** responde | `registrar_respuesta` | Marca la primera respuesta; un `CONTACTO` pasa a `LEAD`. El texto de la empresa **no** se interpreta como intención del cliente. |
| El **lead** escribe | `registrar_mensaje` | Aplica las reglas de caída; un `CAIDO`/`EN_ESPERA` **revive a `LEAD`** y se limpia `motivo_caida`. |

**Regla 1 (la que pediste):** para que un contacto pase a lead debe existir
**al menos una respuesta de la empresa**. Un entrante solo, sin respuesta, no
es un lead.

**Regla 2:** la respuesta no puede revelar contexto interno ni datos de otros
clientes.

**Regla 3:** un teléfono = un lead. Si vuelve a escribir, se reutiliza el mismo
y se deja evento de reingreso.

**Regla 4:** el lead no se convierte en cliente por hablar: se convierte cuando
se cierra el contrato y se ejecuta el momento cero.

**Regla 5:** el **origen lo decide el servidor** según la puerta (`PANEL`,
`GATO`, `WHATSAPP`). El cliente HTTP no puede etiquetarlo.

---

## 3. Estados

| Estado | Cuándo |
|---|---|
| `CONTACTO` | Primer entrante; aún sin respuesta de la empresa |
| `LEAD` | Ya hubo al menos una respuesta |
| `CALIFICADO` | Hay nombre, interés, obra o volumen |
| `EN_ESPERA` | El lead aplazó o pidió que lo contacten luego; tiene fecha de recontacto |
| `HANDOFF` | No es quien decide; se pidió el contacto del decisor |
| `CAIDO` | No avanzó; se etiqueta con motivo para recontacto |
| `CONVERTIDO` | Se creó el cliente (momento cero) |

La transición a `CONVERTIDO` la hace el alta del cliente y guarda
`cliente_id`; no se crea un cliente nuevo si el lead ya lo tiene.

**Reactivación (implementada):** si un lead `CAIDO` o `EN_ESPERA` vuelve a
escribir, o si la empresa le responde, vuelve a `LEAD`; el `motivo_caida`
anterior se limpia y el cambio queda en `lead_eventos` con su actor. No se
borra el historial: se agrega el evento nuevo.

**Cambio manual:** `POST /leads/{id}/estado` permite a una persona fijar
cualquiera de los siete estados con `motivo` y `actor`. La propuesta del sistema
nunca es irreversible.

---

## 4. Tablas implementadas (migración 096)

```sql
-- Real, no propuesta. El detalle completo está en
-- db/migrations/096_nucleo_comercial_leads_citas.sql
CREATE TABLE leads (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    telefono_e164       text NOT NULL UNIQUE,
    nombre              text,
    origen              text NOT NULL DEFAULT 'WHATSAPP'
                        CHECK (origen IN ('WHATSAPP', 'GATO', 'PANEL', 'OTRO')),
    estado              text NOT NULL DEFAULT 'CONTACTO'
                        CHECK (estado IN ('CONTACTO','LEAD','CALIFICADO',
                                          'EN_ESPERA','HANDOFF','CAIDO','CONVERTIDO')),
    interes             text,
    cliente_id          uuid REFERENCES clients(id) ON DELETE SET NULL,
    motivo_caida        text
                        CHECK (motivo_caida IN ('SIN_RESPUESTA','NO_INTERESADO',
                               'COMPETENCIA','PRECIO','SIN_CONTACTO','NO_APLICA','OTRO')),
    recontactar_at      timestamptz,
    intentos_recontacto integer NOT NULL DEFAULT 0,
    ultimo_contacto_at  timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE lead_eventos (          -- append-only (trigger)
    id bigserial PRIMARY KEY,
    lead_id uuid NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    tipo text NOT NULL,              -- CREADO, RESPONDIDO, REINGRESO, CAIDO, REVIVIDO…
    detalle jsonb NOT NULL DEFAULT '{}'::jsonb,
    actor text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE lead_reglas_caida (     -- editable sin desplegar
    clave text PRIMARY KEY,
    intencion text NOT NULL,
    patrones jsonb NOT NULL DEFAULT '[]'::jsonb,
    estado_destino text NOT NULL,
    motivo text,
    gracia_dias integer,
    intentos integer,
    activo boolean NOT NULL DEFAULT true
);
```

**Por qué una tabla aparte y no `clients.estado`:** un lead no es un cliente.
Meterlo en `clients` obliga a limpiar contactos que nunca contrataron y rompe
la carpeta y la cartera. Se vinculan solo al convertir.

**Parámetros de negocio (no se inventan):** en `system_settings`:

| Clave | Valor |
|---|---|
| `leads.recontacto_dias` | `NULL` hasta que Julio diga el plazo |
| `leads.max_intentos` | `NULL` hasta que Julio diga el máximo |
| `leads.motivos_caida` | catálogo editable |

**Deuda conocida:** `lead_eventos` es append-only y referencia `leads` con
`ON DELETE CASCADE`. Borrar un lead arrastra sus eventos (el trigger no cubre
el `DELETE` en cascada). Por eso **no se borra un lead**: se marca `CAIDO` o
`CONVERTIDO`. Queda registrado como pendiente; no se cambió el esquema.

---

## 5. Cuándo un lead está caído: por intención, no por días

La regla no es "pasaron X días". El sistema lee **señales** y propone el estado;
una persona puede confirmar o corregir. Los días y los intentos son parámetros,
no la definición.

**Dónde viven las reglas (tres capas, una sola verdad):**

| Capa | Dónde | Qué contiene |
|---|---|---|
| Semántica | este documento (§5) | Qué significa cada señal y a qué estado lleva |
| Operación | tabla `lead_reglas_caida` | Patrones, estado destino, gracia e intentos; editable sin desplegar |
| Auditoría | `lead_eventos` | Cada decisión, con la señal que la disparó |

| Señal | Ejemplo | Efecto |
|---|---|---|
| Rechazo explícito | "no me interesa", "no gracias", "así estoy bien" | `CAIDO(NO_INTERESADO)` inmediato, sin esperar |
| Ya tiene proveedor | "ya compré", "trabajo con otro", "ya tengo" | `CAIDO(COMPETENCIA)` |
| Precio sin retorno | "está caro", "no tengo presupuesto" | `EN_ESPERA(PRECIO)` y ofrecer alternativa; si no responde, `CAIDO(PRECIO)` |
| Aplazamiento propio | "le aviso", "en unos días", "la próxima semana" | `EN_ESPERA` con la fecha que dijo (o la gracia configurada); al vencer sin respuesta, intento; sin respuesta, `CAIDO(SIN_RESPUESTA)` |
| Silencio tras pedir información | pidió precios y no volvió | Intentos de recontacto; al agotarlos, `CAIDO(SIN_RESPUESTA)` |
| No es quien decide | "yo solo pregunto", "el dueño es..." | `HANDOFF`: pedir el contacto del decisor; sin dato, `CAIDO(SIN_CONTACTO)` |
| Número equivocado o spam | "no soy yo", "número equivocado" | `CAIDO(NO_APLICA)` |
| Sin intención | solo saludó y no preguntó nada | Se queda `CONTACTO`; no es lead |

**Reglas de operación:**

1. El rechazo explícito **nunca espera** días ni intentos.
2. El aplazamiento **no es caída**: es una cita de recontacto con la fecha que
   dio el lead.
3. La ausencia de respuesta **sí** puede cerrar el lead, pero solo después de
   los intentos configurados.
4. El sistema **propone**; una persona puede revertir. Toda decisión deja
   evento con la señal.
5. Los patrones se pueden ampliar sin tocar código: se agregan filas a
   `lead_reglas_caida`.

**Parámetros que faltan (no se inventan):** `leads.recontacto_dias`,
`leads.max_intentos` y la gracia de cada señal quedan `NULL` hasta que Julio
los defina. Mientras estén en `NULL`, solo se cierran por rechazo explícito.

**Implementado 2026-11-19:** los patrones viven en `lead_reglas_caida` y se
editan sin desplegar; el módulo evalúa el mensaje del lead, no el de la
empresa. Caso abierto: `EN_ESPERA(PRECIO)` sin fecha de recontacto mientras
`leads.recontacto_dias` sea `NULL`; no se inventó un plazo. La reactivación
está probada: al volver a escribir, el lead revive a `LEAD` y se limpia el
motivo anterior.

## 6. Preguntas abiertas (no se deciden por Julio)

1. ¿Una respuesta automática del bot cuenta como "la primera respuesta" o debe
   ser una persona?
2. ¿Cuántos días para considerar caído un lead?
3. ¿Cuántos intentos de recontacto y cada cuánto?
4. ¿Quién puede marcar `CAIDO`: solo una persona o también el sistema por
   inactividad?
