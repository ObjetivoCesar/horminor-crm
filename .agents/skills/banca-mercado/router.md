# Router de capas — `banca-mercado`

| Capa | Mecanismo | Coste relativo |
|---|---|---|
| 0 | Código determinista (SQL nombrado, Decimal, ACL) | $0 |
| 1 | Clasificador rápido (DeepSeek Flash: ¿banco o mercado?) | Bajo |
| 2 | Generativo económico (DeepSeek Chat: explicar y desambiguar) | Medio |
| 3 | Humano (inconsistencia contable) | Alto |

## Mapeo tarea → capa

| Tarea | Capa | Mecanismo |
|---|---|---|
| Listar bancos | 0 | Consulta nombrada |
| Detalle de un banco | 0 | `bank_accounts` + `v_balance_general` |
| Movimientos del banco | 0 | `payments` con `account_id` de la hija |
| Préstamos y cuotas | 0 | `financial_liabilities`, `loan_payments` |
| Cuota de mercado | 0 | `market_benchmarks` + `orders` |
| Brecha y porcentaje | 0 | `m4_dashboard/calculos.py` |
| Escenarios y DSCR | 0 | Simulador existente |
| Reconocer "el Pichincha" vs "el Guayaquil" | 1 | DeepSeek Flash |
| Explicar por qué el saldo es X | 2 | DeepSeek Chat con fichas |
| Detectar inconsistencia | 2 | DeepSeek Chat + `ESCALADA` |
| Resolver reclamo contable | 3 | Humano |

## Regla de escalado

- La capa 2 no calcula: solo redacta con las fichas de la capa 0.
- Si la capa 0 devuelve `vacio: true`, la respuesta es "sin dato" y el lugar
  donde se carga. No se reintenta con otra consulta "parecida".
