# Router de capas — `pdf-cotizaciones`

| Capa | Mecanismo | Coste relativo |
|---|---|---|
| 0 | Código determinista (JSON Schema, Decimal, hash, ACL, folio) | $0 |
| 1 | Clasificador rápido (DeepSeek Flash: intención de cotizar) | Bajo |
| 2 | Generativo económico (DeepSeek Chat: explicar y desambiguar) | Medio |
| 3 | Humano (anulación con reclamo) | Alto |

## Mapeo tarea → capa

| Tarea | Capa | Mecanismo |
|---|---|---|
| Validar contrato de entrada | 0 | JSON Schema 2020-12 |
| Verificar aritmética | 0 | Decimal |
| Verificar `vigencia_hash` | 0 | Consulta de precio + SHA-256 |
| Comparar `total_esperado` | 0 | Decimal |
| Autorizar al actor | 0 | ACL por rol |
| Asignar folio | 0 | Secuencia atómica por año |
| Redactar condiciones por defecto | 0 | Plantilla fija |
| Renderizar plantilla | 0 | Motor PDF |
| Guardar y devolver URL | 0 | Bunny o volumen local |
| Detectar una cotización ambigua | 2 | DeepSeek Chat |
| Explicar la cotización al usuario | 2 | DeepSeek Chat con la ficha emitida |
| Anular con reclamo del cliente | 3 | Humano + bitácora |

## Regla de escalado

- Si la capa 0 rechaza dos veces por el mismo campo, se devuelve el campo
  faltante y se detiene. No se reintenta con el modelo.
- La capa 2 nunca inventa precios: solo explica los que vienen en la ficha.
