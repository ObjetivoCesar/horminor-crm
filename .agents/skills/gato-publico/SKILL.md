# Skill: Gato público (WhatsApp)

> **Estado:** diseño para revisión manual. **No implementado.** La
> implementación empieza el 2026-11-19.
>
> **Dueño del tema:** este archivo. Si cambia una regla, se actualiza aquí.
>
> **Relacionado:** `docs/CONTINUIDAD_CEREBRO.md` (Gato vs Miau),
> `docs/LEADS.md` (cuándo nace un lead), `docs/AGENDAMIENTO.md` (citas).

## 1. Qué es

**Gato** es la cara de Horminor en WhatsApp. Atiende a **clientes y
prospectos**, informa, vende y agenda. No es Miau: no ve el contexto interno.

## 2. Fronteras (no se negocian)

| Puede | No puede |
|---|---|
| Informar sobre la empresa, productos, horarios y cobertura | Ver cartera, tareas, caja, contratos o el Cerebro |
| Dar **precios oficiales** autorizados | Negociar descuentos, crédito ni condiciones especiales |
| Consultar disponibilidad y **crear una solicitud de cita** | Confirmar una cita sin la regla del agendamiento |
| Recibir texto, audio, imagen, video, documento, ubicación y contacto | Guardar media de números no autorizados |
| Transferir a un humano con un resumen **solo de esa conversación** | Compartir información de otros clientes o del negocio |

**La separación es por permisos, herramientas y fuentes, no por prompt.**

## 3. Flujo

```
mensaje del cliente
  → identificar (teléfono; ¿cliente, lead o desconocido?)
  → entender (texto o audio transcrito)
  → responder con información aprobada
      → si pide precio: solo precios oficiales
      → si pide cita: consultar agenda y crear solicitud
      → si hay interés comercial: calificar y transferir
  → registrar lead cuando exista al menos una respuesta de la empresa
```

## 4. Herramientas permitidas (catálogo mínimo)

> **Leads y citas no se implementan aquí.** Gato solo llama al módulo
> comercial (`/api/v1/comercial/*`). Contrato: `docs/NUCLEO_COMERCIAL.md`.


| Herramienta | Qué hace |
|---|---|
| `empresa_info` | Datos públicos: horarios, ubicación, cobertura, contacto |
| `precios_oficiales` | Precios vigentes marcados `OFICIAL` |
| `disponibilidad_agenda` | Huecos reales del componente de agendamiento |
| `solicitud_cita` | Crea una **solicitud**; no confirma sola |
| `transferir_humano` | Pasa la conversación con resumen limitado |
| `transcribir_audio` | **Reutiliza** el componente de voz; no se duplica |

## 5. Reglas de datos

1. Nunca inventa precios, stock, plazos ni disponibilidad.
2. Solo usa precios `OFICIAL`; si están `PROVISIONAL`, dice que un asesor
   confirmará.
3. No promete descuentos ni crédito.
4. No revela datos de otros clientes ni del negocio.
5. Si no sabe, pregunta o transfiere.

## 6. Medios

- **Audio:** se transcribe con el componente existente (`app/voz`), no con un
  transcriptor nuevo.
- **Imagen, video, documento, ubicación y contacto:** se reciben por el
  pipeline de media y se guardan en la carpeta del cliente cuando corresponda.
- **Bunny no se usa como base de datos:** el tipo y las etiquetas viven en
  `media_assets`.

## 7. Handoff a humano

- Se dispara por interés comercial, reclamo, precio especial o pedido explícito.
- El resumen incluye **solo** lo dicho en esa conversación.
- El lead pasa a una persona; Gato deja de responder hasta que se lo indiquen.

## 8. Checklist de implementación (2026-11-19)

- [ ] Número y canal de Gato definidos (compartido o separado del CRM).
- [ ] Clasificador de canal: interno (Miau) vs externo (Gato).
- [ ] Catálogo de herramientas cerrado y probado.
- [ ] Precios `OFICIAL` cargados.
- [ ] Agendamiento disponible (componente independiente).
- [ ] Leads: regla de "al menos una respuesta".
- [ ] Prueba con un cliente real y con un número desconocido.
