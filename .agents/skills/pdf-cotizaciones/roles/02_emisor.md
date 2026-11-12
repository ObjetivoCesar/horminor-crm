# Rol 02 — Emisor

- **Nivel funcional:** decisión
- **Mecanismo preferido:** Capa 0 (ACL + persistencia)
- **Misión:** autorizar la emisión, asignar folio y persistir la cotización con su snapshot de precio y vigencia.

## Reglas inviolables

1. Solo `SUPERADMIN`, `CONTADORA` y `SECRETARIA` pueden emitir.
2. `BOT_PUBLICO` solo puede emitir en estado `PRELIMINAR`.
3. El folio es `COT-<año>-<secuencia>` y nunca se reutiliza.
4. El precio y su `vigencia_hash` se copian a `cotizacion_items`.
5. Una cotización `EMITIDA` no se edita: se anula y se emite otra.
6. No se emite si el rol 01 no devolvió `estado_sugerido: VALIDADA`.
7. La emisión y el folio van en una sola transacción.

## Entradas

- `cotizacion_calculada` del rol 01.
- `creado_por` con `actor_id`, `rol` y `canal`.

## Salidas

Contrato `contracts/cotizacion_emitida.json` (v1.1.0): folio, estado, líneas con
snapshot y `vigencia_hash`, subtotal, IVA, total, validez, `emitido_at` y
`pdf_url`.

## Persistencia

`cotizaciones` (cabecera) + `cotizacion_items` (snapshot con precio y hash). La
transacción es única: si falla el folio, no queda cabecera.

## Evidencia

- `SELECT` del folio emitido con sus ítems.
- `vigencia_hash` idéntico al de la ficha de precio.
- Si el canal es `BOT`, `estado = PRELIMINAR`.

## Rechazos automáticos

- `ACTOR_NO_AUTORIZADO` si el rol no está en la lista.
- `PRELIMINAR_NO_PERMITIDO` si el canal es público y el actor no es `BOT_PUBLICO`.
- `FOLIO_DUPLICADO` si la secuencia ya existe (reintentar una vez).
- `ESTADO_INVALIDO` si se intenta emitir desde `ANULADA` o sin `VALIDADA`.
- `VIGENCIA_INCONSISTENTE` si el hash no coincide con la ficha.
