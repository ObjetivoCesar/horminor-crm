# Rol 03 — Privacidad y roles

- **Nivel funcional:** control
- **Mecanismo preferido:** Capa 0 (ACL + whitelist por persona)
- **Misión:** impedir que una consulta devuelva datos que la persona o el rol no pueden ver.

## Reglas inviolables

1. `persona: PUBLICO` exige `rol: BOT_PUBLICO`; cualquier otro rol es `ROL_PUBLICO_INVALIDO`.
2. `persona: PUBLICO` solo ejecuta `recetas_precio_publico` y `empresa_info`.
3. Toda consulta con `persona: PUBLICO` que toque datos de un cliente exige
   `actor_context.cliente_id`; si falta, `TENANT_SCOPE_AUSENTE`.
4. Un `CLIENTE` solo consulta su propio `cliente_id`; se resuelve por su
   teléfono registrado, nunca por el texto del mensaje.
5. `SECRETARIA`, `CONTADORA` y `SUPERADMIN` usan `PERMISOS_CONSULTA` del Custodio.
6. Costos y márgenes: solo `SUPERADMIN` y `CONTADORA`; nunca `BOT_PUBLICO`.
7. Un dato de un cliente no se devuelve a otro "para comparar".

## Entradas

- `actor_context` validado por el contrato.
- Consulta solicitada y parámetros.

## Salidas

Permiso concedido o rechazo con código.

## Rechazos automáticos

- `SIN_PERMISO` si el rol no está en la lista de la consulta.
- `PERSONA_NO_PERMITIDA` si la persona no está en `personas` del catálogo.
- `ROL_PUBLICO_INVALIDO` si `persona=PUBLICO` y el rol no es `BOT_PUBLICO`.
- `PUBLICO_FUERA_DE_WHITELIST` si la consulta no es pública.
- `TENANT_SCOPE_AUSENTE` si falta el cliente en una consulta de cliente.
- `CLIENTE_AJENO` si el `cliente_id` no coincide con la identidad.
- `COSTO_NO_AUTORIZADO` si la consulta es de costos y el rol no es financiero.

## Auditoría

Cada rechazo se registra con actor, persona, consulta, motivo y fecha. Un rechazo
no se reintenta con otra consulta equivalente.
