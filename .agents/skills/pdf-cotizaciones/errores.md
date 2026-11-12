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
