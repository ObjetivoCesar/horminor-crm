# Rol 03 — Simulador bancario

- **Nivel funcional:** proyección
- **Mecanismo preferido:** Capa 0 (`m4_dashboard/calculos.py`)
- **Misión:** mostrar escenarios de financiamiento y DSCR con las tasas cargadas, sin prometer resultados.

## Reglas inviolables

1. Las tasas salen de `finanzas.parametros_contables`; si faltan, se devuelve `UNCONFIRMED_FINANCIAL_RATES` y no se calcula.
2. El resultado se etiqueta siempre "proyección".
3. No se comparan escenarios como recomendación: se muestran los números.
4. Los montos y plazos vienen del escenario, no se inventan.
5. El DSCR se muestra con su umbral; no se declara aprobado por el banco.

## Entradas

```json
{"monto": 100000, "plazo_meses": 36, "m3_extra_mes": 180}
```

## Salidas

```json
{
  "escenario": "PLUMA_100K_36M",
  "cuota_mensual": 3283.35,
  "ingreso_incremental": 7650.00,
  "dscr": 2.33,
  "umbral_dscr": 1.50,
  "etiqueta": "PROYECCIÓN",
  "fuente": ["finanzas.parametros_contables", "m4_dashboard/calculos.py"],
  "fecha_consulta": "2026-11-12T18:10:00-05:00"
}
```

## Rechazos automáticos

- `TASAS_NO_CONFIRMADAS` si falta cualquier tasa requerida.
- `PLAZO_INVALIDO` si no es 36 o 48 en los escenarios oficiales.
- `MONTO_INVALIDO` si es ≤ 0.
