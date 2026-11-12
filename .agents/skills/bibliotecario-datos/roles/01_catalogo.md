# Rol 01 — Catálogo

- **Nivel funcional:** consulta
- **Mecanismo preferido:** Capa 0 (enum cerrado + JSON Schema)
- **Misión:** encontrar la consulta correcta dentro del catálogo cerrado y ejecutarla con parámetros válidos.

## Reglas inviolables

1. La consulta se identifica por un `id` del enum de `contracts/consulta.json`.
2. No hay coincidencias difusas: si el id no está, es `CONSULTA_NO_DISPONIBLE`.
3. Los parámetros se validan contra el contrato antes de tocar la base.
4. No se concatenan valores en SQL: todo va parametrizado.
5. `limite` por defecto 50, máximo 500.
6. La consulta y sus parámetros deben existir en `docs/CATALOGO_CONSULTAS.json`.
7. Una consulta en estado `PROPUESTA` no se ejecuta aunque su id exista.

## Entradas

Contrato `contracts/consulta.json` (v1.4.0):

```json
{
  "consulta": "cartera_cliente",
  "actor_context": {"persona": "INTERNO", "rol": "SECRETARIA", "actor_id": "panel:ana", "cliente_id": null},
  "parametros": {"cliente_id": "…", "limite": 50}
}
```

## Salidas

Filas crudas de la consulta, listas para el Guardián.

## Defaults

- Si `limite` no llega, se usa 50; si llega fuera de 1–500, se rechaza.
- El bibliotecario **no inventa fechas**: si una consulta declara `desde`/`hasta`
  como requeridos, el pilar consumidor debe enviarlos.
- `material` ausente en `stock_actual` o `stock_proyectado` significa "todos".

## Ejemplo de rechazo

```json
{"consulta": "cartera_cliente", "actor_context": {"persona": "INTERNO", "rol": "SECRETARIA", "actor_id": "panel:ana"}, "parametros": {}}
→ PARAMETRO_INVALIDO: falta cliente_id
```

## Rechazos automáticos

- `CONSULTA_NO_DISPONIBLE` si el id no está en el enum.
- `CONSULTA_EN_PROPUESTA` si la consulta existe pero su estado es `PROPUESTA`.
- `PARAMETRO_INVALIDO` si falta un requerido o sobra uno.
- `PARAMETRO_FUERA_DE_CATALOGO` si la consulta no declara ese parámetro.
- `LIMITE_INVALIDO` si está fuera de 1–500.
