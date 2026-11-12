# Registro de errores — `bibliotecario-datos` (`q_datos`)

| Tipo | Severidad | Causa raíz | Solución propuesta | Estado |
|---|---|---|---|---|
| Consulta fuera del enum | MEDIA | El pilar pide algo que no está implementado | `CONSULTA_NO_DISPONIBLE` y pedir alta | RESUELTO |
| Consulta en estado PROPUESTA | MEDIA | El catálogo la lista pero su fuente no existe | Rechazo `CONSULTA_EN_PROPUESTA` | RESUELTO |
| Persona pública fuera de whitelist | CRÍTICA | Catálogo sin filtro por persona | Enum condicional en `consulta.json` | RESUELTO |
| Rol público distinto de BOT_PUBLICO | CRÍTICA | `persona=PUBLICO` con rol interno | `if/then` exige `rol=BOT_PUBLICO` | RESUELTO |
| Parámetro requerido ausente | MEDIA | El pilar no envió el `requeridos` de la consulta | Condicional `allOf/if/then` por consulta | RESUELTO |
| Tenant scope ausente | CRÍTICA | Consulta de cliente sin `cliente_id` | Rechazo `TENANT_SCOPE_AUSENTE` | RESUELTO |
| Costo en canal público | CRÍTICA | Consulta financiera habilitada a `PUBLICO` | Whitelist y `COSTO_NO_AUTORIZADO` | RESUELTO |
| Cifra no coincide con el ledger | ALTA | Vista desactualizada o filtro mal aplicado | Reproducir y abrir incidente | PENDIENTE REVISIÓN |
| Resultado vacío tratado como error | BAJA | El pilar no distingue `vacio` | Ficha con `vacio=true` y nota | RESUELTO |
| Vigencia de precio ausente | ALTA | La consulta de precio no calcula hash | `VIGENCIA_AUSENTE` y bloquear cotización | RESUELTO |
| Consulta lenta | MEDIA | Vista sin índice | Revisar plan y agregar índice | PENDIENTE REVISIÓN |
| Migración sin número | ALTA | Archivo fuera del runner | Rechazo y renumeración | RESUELTO |
| Fecha de consulta ausente | BAJA | Plantilla de ficha incompleta | Campo obligatorio en el contrato | RESUELTO |
