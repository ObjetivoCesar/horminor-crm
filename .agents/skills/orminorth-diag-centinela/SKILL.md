---
name: orminorth-diag-centinela
description: Consulta e interpreta el Nodo Centinela de Orminorth (salud de VPS, WhatsApp, Bunny.net, viajes en riesgo, caja y errores). Usar cuando el CRM de la agencia pide el diagnóstico diario, cuando el sistema se siente lento/caído o cuando hay que explicar un estado WARN o CRITICO.
---

# Skill: diagnóstico con el Centinela

## Consultar

```powershell
$k = (Select-String -Path .env -Pattern '^AGENCY_MASTER_KEY=(.*)$').Matches.Groups[1].Value
Invoke-RestMethod -Uri http://localhost:8000/api/v1/sentinel/daily-audit `
  -Headers @{ "X-Agency-Master-Key" = $k } | ConvertTo-Json -Depth 5
```

En producción, el CRM de la agencia usa el mismo endpoint con su clave.

## Leer la respuesta

| Campo | Qué significa |
|---|---|
| `estado_global` | Peor estado de todos los chequeos |
| `checks[].estado` | `OK` · `WARN` · `CRITICO` · `NO_CONFIGURADO` |
| `resumen_operativo` | Números para el informe diario |

Regla de agregación: hay `CRITICO` → global `CRITICO`; si no, hay `WARN` →
`WARN`; si no, hay `OK` → `OK`; si todos son `NO_CONFIGURADO` → `NO_CONFIGURADO`.

## Diagnóstico por síntoma

| Chequeo | Estado | Qué revisar |
|---|---|---|
| `evolution` | `NO_CONFIGURADO` | Faltan `EVOLUTION_URL/INSTANCE/API_KEY` en `.env` |
| `bunny` | `NO_CONFIGURADO` | Falta `BUNNY_CDN_HOST` |
| `caja` | `WARN` | La secretaría no cerró caja ayer (o no existe la tabla de cierre en ese día) |
| `merma` | `NO_CONFIGURADO` | `operacion.merma_cemento_pct_alerta` sigue en `null` |
| `riesgo_termico` | `CRITICO` | Viaje con límite de 150 min vencido sin confirmación del cliente |
| `viajes_en_ruta` | `WARN` | Viaje con más de 90 min sin llegada confirmada |
| `errores` | `WARN` | Hay filas `ERROR`/`CRITICAL` en `error_logs` (24 h) |

Casi todos los `NO_CONFIGURADO` de hoy son **correctos**: faltan credenciales
del cliente, no hay un bug.

## Reglas

- No cambies umbrales para "quitar" una alerta. Si el umbral está mal, es una
  decisión que se documenta en la bitácora.
- No inventes el estado de Evolution/Bunny. Si falta credencial, se reporta.
- El endpoint nunca debe devolver 500 por un chequeo caído: si lo hace, el bug
  está en `app/m5_sentinel/audit.py`.
- Latencia objetivo: < 200 ms en caliente. Si sube, revisar el pool asyncpg.
