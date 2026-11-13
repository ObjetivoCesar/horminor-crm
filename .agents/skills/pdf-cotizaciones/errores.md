# Registro de errores — `pdf-cotizaciones` (`q_documentos`)

| Tipo | Severidad | Causa raíz | Solución propuesta | Estado |
|---|---|---|---|---|
| Aritmética no cuadra | ALTA | `total_esperado` distinto a la suma de líneas | Recalcular con Decimal y rechazar | RESUELTO |
| Precio caducado | ALTA | `vigencia_hash` no coincide con el vigente | `PRECIO_CADUCADO`, pedir precio nuevo | RESUELTO |
| Precio sin referencia | ALTA | Línea sin `precio_ref` | Rechazo en el contrato | RESUELTO |
| Monto como número | MEDIA | El llamador envía float | El contrato exige texto decimal | RESUELTO |
| Sin validez | MEDIA | `validez_dias` opcional | Campo obligatorio | RESUELTO |
| Actor sin permiso | CRÍTICA | Endpoint sin ACL | Validar rol antes de emitir | RESUELTO |
| Datos personales incompletos | MEDIA | Cliente sin nombre o RUC | `CUARENTENA` y devolver el campo | RESUELTO |
| Bunny caído | MEDIA | Storage no configurado | Guardar local y `pdf_url=null` | PENDIENTE REVISIÓN |
| Folio duplicado | ALTA | Secuencia no atómica | Secuencia por año con bloqueo | RESUELTO |
| Preliminar enviada como definitiva | ALTA | El canal ignoró el estado | Marca PRELIMINAR y `estado` en la respuesta | RESUELTO |
| Plantilla inexistente | MEDIA | `plantilla` fuera del enum | Rechazo en el contrato | RESUELTO |
| Precio provisional a cliente real | CRÍTICA | Semilla ficticia emitida fuera de SANDBOX | `PRECIO_PROVISIONAL` y marca visible | RESUELTO |
| Extra con categoría | MEDIA | El llamador envía `categoria` | Rubro único global; `additionalProperties: false` | RESUELTO |
| Extra interno impreso al cliente | ALTA | Se imprimió un `cobrable=false` | Copia interna separada y filtro por `cobrable` | RESUELTO |
| PDF no archivado en el cliente | MEDIA | Se guardó fuera de `media_assets` | Registro obligatorio con `cliente_id` y `sha256` | RESUELTO |
