# Router de capas — `bibliotecario-datos`

| Capa | Mecanismo | Coste relativo |
|---|---|---|
| 0 | Código determinista (enum, JSON Schema, ACL/whitelist, SQL parametrizado, Decimal, SHA-256) | $0 |
| 1 | DeepSeek Flash (solo si hay que mapear una intención interna a un id del enum; nunca genera SQL ni parámetros libres) | Bajo |
| 2 | **N/A** — prohibido por frontera: la explicación al usuario la ejecuta el pilar consumidor | — |
| 3 | Humano / Custodio BD (anomalía de integridad, vista rota o migración observada) | Alto |

## Mapeo tarea → capa

| Tarea | Capa | Mecanismo |
|---|---|---|
| Resolver una consulta del enum | 0 | Búsqueda exacta por id |
| Validar `actor_context` y parámetros | 0 | JSON Schema 2020-12 |
| Aplicar whitelist pública | 0 | Enum + persona + rol |
| Aplicar permisos por rol | 0 | ACL |
| Ejecutar la consulta | 0 | SQL parametrizado |
| Calcular `vigencia_hash` de precio | 0 | SHA-256 de receta + precio |
| Detectar resultado vacío | 0 | Regla fija |
| Detectar inconsistencia de integridad | 0 | Regla fija + escalar |
| Elegir la consulta desde una intención | 1 | DeepSeek Flash |
| Corregir un dato inconsistente | 3 | Humano + migración |

## Regla de escalado

- El modelo **nunca** propone SQL ni un id fuera del enum. Si no hay consulta,
  la respuesta es `CONSULTA_NO_DISPONIBLE` y se pide crear la consulta.
- Una consulta `PROPUESTA` no se ejecuta aunque el id exista en el catálogo.
- Este pilar no redacta: devuelve fichas. La capa 2 vive en el consumidor.
