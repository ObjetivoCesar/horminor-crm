---
name: orminorth-manual-funcional
description: Explica qué hace cada función del CRM Horminor, por qué existe y qué consecuencias tiene, usando el Manual Vivo como única fuente oficial. Usar cuando Julio, la secretaría o cualquier persona pregunte "¿qué significa esto?", "¿para qué sirve este botón?", "¿qué pasa si presiono aquí?" o cuando un agente de IA necesite entender el comportamiento funcional antes de tocar código.
---

# Skill: consultar el Manual Vivo de Horminor

## Regla de oro

**Una sola fuente de definiciones:**
`docs/HORMINOR_MANUAL_FUNCIONAL.md`.

Esta skill **no repite** las definiciones. Solo indica cómo consultarlas, cómo
responder y cómo mantenerlas. Si encuentras dos explicaciones distintas, gana el
manual y se corrige la otra.

## 1. Antes de responder o de tocar código

1. Abre `docs/HORMINOR_MANUAL_FUNCIONAL.md`.
2. Busca el término por **nombre técnico** (`ACUSADA`, `TENTATIVO`…), por
   **nombre visible** («Recepción confirmada», «Resultado registrado») o por
   **sinónimo** («acuse», «darse por enterado»), usando el índice (§11) o la
   búsqueda de texto.
3. Si el término no está, **no lo inventes**: dilo y propone agregarlo al manual.

## 2. Cómo responder a una persona

- Usa el **nombre visible**, no el técnico, salvo que pregunten por el técnico.
- Explica en este orden: qué significa → para qué existe → qué NO significa →
  ejemplo.
- Nunca prometas una función que esté en «Todavía no existe» (§10).
- Si la pregunta es sobre un botón, di también **qué no hace** (por ejemplo,
  «Confirmar que recibí la tarea» no marca la tarea como hecha).

## 3. Cómo responder a un agente de IA o a un desarrollador

- Cita el término y su **referencia técnica** (archivo, tabla, endpoint).
- Distingue **estado**, **evento** y **acción**; no los mezcles al proponer
  cambios de UI o de modelo de datos.
- Si vas a cambiar un nombre visible, respeta §8 del manual: los nombres técnicos
  no se tocan; las etiquetas sí.

## 4. Cuándo actualizar el manual

Cualquier función nueva o cambio de comportamiento de negocio obliga a
actualizar el término correspondiente y la bitácora del manual (§12), con:

- qué concepto se agregó o cambió,
- qué comportamiento cambió,
- qué usuarios se ven afectados,
- con qué componente técnico se relaciona,
- fecha y versión.

**No se considera terminada una funcionalidad de negocio si su explicación está
ausente o desactualizada.** La suite de pruebas verifica que el manual y esta
skill existan y apunten al documento correcto.

## 5. Límites

- El manual documenta **lo implementado**. Lo pendiente vive en «Todavía no
  existe» y en `docs/CEREBRO_MATRIZ_BRECHAS.md`.
- Para el *cómo* técnico, enlaza a `docs/CEREBRO_VOZ_DISENO.md` y
  `docs/CONTRATO_WHATSAPP_CEREBRO.md`; no copies sus definiciones acá.
