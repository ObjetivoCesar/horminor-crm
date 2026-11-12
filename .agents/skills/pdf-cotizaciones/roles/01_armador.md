# Rol 01 — Armador de cotización

- **Nivel funcional:** operativo
- **Mecanismo preferido:** Capa 0 (código determinista)
- **Misión:** convertir líneas sueltas en una cotización cuadrada, con validez, vigencia y totales correctos.

## Reglas inviolables

1. Los montos llegan como texto y se convierten a `Decimal`; nunca a `float`.
2. `cantidad_m3 > 0`; `precio_m3 >= 0`; `iva_pct` entre 0 y 30.
3. `validez_dias` es obligatorio y debe ser ≥ 1.
4. Cada línea exige `precio_ref.vigencia_hash` y debe coincidir con el vigente.
5. Si llega `total_esperado`, se compara con el total calculado.
6. Un dato faltante no se completa: se devuelve en `faltantes`.

## Entradas

Contrato `contracts/solicitud_cotizacion.json` (v1.1.0).

## Salidas

Objeto `cotizacion_calculada`:

```json
{
  "cliente": {"nombre": "…", "ruc": null, "telefono": null, "obra": null},
  "lineas": [
    {
      "descripcion": "Hormigón FC-210",
      "cantidad_m3": "20.0000",
      "precio_m3": "118.00",
      "subtotal": "2360.00",
      "vigencia_hash": "…64 hex…"
    }
  ],
  "subtotal": "2360.00",
  "iva_pct": "15.00",
  "iva": "354.00",
  "total": "2714.00",
  "validez_dias": 7,
  "estado_sugerido": "VALIDADA"
}
```

## Verificación de vigencia

1. Se pide a `bibliotecario-datos` la consulta `recetas_precio_publico`.
2. Se compara el `vigencia_hash` de la ficha con el de cada línea.
3. Si no coincide: `PRECIO_CADUCADO` y no se emite.
4. Si el precio no trae `precio_ref`: `PRECIO_SIN_REFERENCIA`.

## Rechazos automáticos

- `LINEAS_VACIAS`, `CANTIDAD_INVALIDA`, `PRECIO_INVALIDO`, `IVA_FUERA_DE_RANGO`.
- `VALIDEZ_FALTANTE`, `CLIENTE_INCOMPLETO`.
- `PRECIO_CADUCADO`, `PRECIO_SIN_REFERENCIA`.
- `ARITMETICA_NO_CUADRA` si `total_esperado` no coincide.
