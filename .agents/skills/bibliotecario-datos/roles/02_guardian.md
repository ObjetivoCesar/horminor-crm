# Rol 02 — Guardián de integridad

- **Nivel funcional:** control
- **Mecanismo preferido:** Capa 0 (reglas fijas)
- **Misión:** convertir filas crudas en una ficha de dato con procedencia, frescura y vigencia.

## Reglas inviolables

1. Toda ficha lleva `ficha_id`, `consulta_id`, `fuente_vista_tabla`,
   `filtros_aplicados`, `consultado_en`, `vacio`, `nota` y `esquema_version`.
2. Si no hay filas o el campo es nulo: `vacio: true` y una `nota` de al menos 3 caracteres.
3. No se rellena un nulo con 0, "N/A" ni un promedio.
4. Si la consulta devuelve más filas de las esperadas, se rechaza.
5. Los montos viajan como texto decimal (`"55043.60"`, `tipo_valor: DECIMAL`), nunca como number.
6. `fuente_vista_tabla` solo puede ser una de las 23 relaciones del enum; `sabueso` y `sentinel` no son tablas.
7. `vigencia_hash` es obligatorio cuando `consulta_id` es `recetas_precio_publico`.

## Entradas

Filas crudas del Catálogo + metadatos de la consulta.

## Salidas

Contrato `contracts/ficha_dato.json` (v1.2.0):

```json
{
  "ficha_id": "3f2b8c1a-9d4e-4b7a-8c2e-1a5b6c7d8e9f",
  "consulta_id": "cartera_cliente",
  "dato": "saldo_pendiente",
  "valor": "55043.60",
  "tipo_valor": "DECIMAL",
  "unidad": "USD",
  "fuente_vista_tabla": ["v_cliente_saldo"],
  "filtros_aplicados": {"cliente_id": "…"},
  "consultado_en": "2026-11-12T17:40:00-05:00",
  "vacio": false,
  "nota": null,
  "vigencia_hash": null,
  "esquema_version": "1.1.0"
}
```

## Rechazos automáticos

- `FUENTE_AUSENTE` si la consulta no declara vista/tabla.
- `FUENTE_NO_PERMITIDA` si no está en el enum de 23 relaciones.
- `FILTRO_AUSENTE` si se consultó un cliente sin su id.
- `MULTIPLES_FILAS` si se esperaba una y llegaron varias.
- `VALOR_NULO` no es rechazo: se convierte en `vacio=true` con nota.
- `VIGENCIA_AUSENTE` si es `recetas_precio_publico` y falta el hash.
- `MONTO_COMO_NUMBER` si un DECIMAL llega como número y no como texto.
