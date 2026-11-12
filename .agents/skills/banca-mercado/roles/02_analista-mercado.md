# Rol 02 — Analista de mercado

- **Nivel funcional:** consulta y cálculo
- **Mecanismo preferido:** Capa 0 (consulta + Decimal)
- **Misión:** devolver la cuota de mercado por provincia, la brecha y el benchmark usado.

## Reglas inviolables

1. La demanda sale de `market_benchmarks`; no se estima.
2. Las ventas sin provincia se informan en `sin_provincia_m3` y no se reparten.
3. El porcentaje usa `ventas / demanda` con Decimal y 2 decimales.
4. La brecha es `demanda − ventas`, nunca negativa (si supera, se informa aparte).
5. Sin benchmark, la respuesta es "sin definir" con el año consultado.

## Entradas

Contrato `contracts/resumen_mercado.json`:

```json
{"provincia": "TODAS", "periodo": "12_MESES_MOVILES", "anio": 2026}
```

## Salidas

```json
{
  "periodo": "12_MESES_MOVILES",
  "anio": 2026,
  "provincias": [
    {"provincia": "ORELLANA", "demanda_m3": 120000, "ventas_m3": 372, "cuota_pct": 0.31, "brecha_m3": 119628},
    {"provincia": "SUCUMBIOS", "demanda_m3": 95000, "ventas_m3": 16, "cuota_pct": 0.02, "brecha_m3": 94984}
  ],
  "sin_provincia_m3": 16,
  "fuente": ["market_benchmarks", "orders"],
  "fecha_consulta": "2026-11-12T18:10:00-05:00"
}
```

## Rechazos automáticos

- `PERIODO_INVALIDO` si no es `12_MESES_MOVILES` o `ANIO_CALENDARIO`.
- `PROVINCIA_INVALIDA` si no está en el catálogo.
- `BENCHMARK_AUSENTE` no es rechazo: devuelve `vacio: true` para esa provincia.
