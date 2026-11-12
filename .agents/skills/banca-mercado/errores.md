# Registro de errores — `banca-mercado` (`q_finanzas`)

| Tipo | Severidad | Causa raíz | Solución propuesta | Estado |
|---|---|---|---|---|
| Movimientos vacíos con saldo | ALTA | Cobros sin `account_id` de la cuenta hija | Asignar la cuenta en el pago | PENDIENTE REVISIÓN |
| Cuenta sin número | MEDIA | Gerencia no cargó el dato | Mostrar "Provisional" | RESUELTO |
| Benchmark ausente | MEDIA | Provincia sin benchmark | Responder "sin definir" | RESUELTO |
| Saldo informado viejo | MEDIA | No hay historial del saldo | Mostrar `saldo_informado_at` | PENDIENTE REVISIÓN |
| Simulador tomado como real | ALTA | Lenguaje ambiguo | Etiquetar "proyección" y citar tasas | RESUELTO |
| Préstamo sin banco | MEDIA | `bank_account_id` nulo en fila histórica | Cruzar por entidad y no duplicar | RESUELTO |
| Rol público pide banco | CRÍTICA | Catálogo mal filtrado | Rechazo en Capa 0 | RESUELTO |
| Dos bancos con el mismo alias | BAJA | Nombre ambiguo | Pedir aclaración una vez | RESUELTO |
