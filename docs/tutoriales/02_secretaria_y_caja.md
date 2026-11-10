# Tutorial 02 — Secretaría y Caja

## Qué hace

Concentra la ventanilla diaria: cobrar a un cliente, registrar un gasto,
comprar material, crear una orden, cerrar la caja y ver la agenda de entregas.

![Secretaría y Caja](assets/tutoriales/02_secretaria.png)

## Paso a paso

### Cobrar o abonar

1. Entrar a **Secretaría y Caja**.
2. Pulsar **Cobrar / abonar**.
3. Elegir cliente, orden (opcional), monto y método (`EFECTIVO` o
   `TRANSFERENCIA`).
4. Si el pago supera el saldo, marcar **Registrar el excedente como anticipo**.
5. Confirmar. El pago queda en el ledger y actualiza la cartera.

### Gasto operativo

1. Pulsar **Gasto operativo**.
2. Elegir rubro, método y monto.
3. Si el método es efectivo y supera el tope de caja chica, el sistema bloquea
   y pide autorización de exceso o transferencia.
4. Agregar referencia si el rubro la exige.
5. Confirmar.

### Compra de material

1. Pulsar **Compra de material**.
2. Elegir o crear proveedor.
3. Elegir material, cantidad, costo, IVA y modalidad de pago.
4. Elegir recepción inmediata o en tránsito.
5. Confirmar. La compra debita inventario; si es en efectivo, el cierre la
   descuenta.

### Cierre de caja

1. Pulsar **Cierre de caja del día**.
2. Revisar cobros, gastos y compras en efectivo.
3. Escribir el efectivo contado.
4. Confirmar el cierre. La diferencia queda registrada.

## Preguntas frecuentes

**¿Por qué un gasto no se guarda?**
Puede superar el tope de caja chica, faltar el comprobante o la cuenta no ser
monetaria. El mensaje indica el código exacto.

**¿Dónde veo el tope de caja chica?**
En el modal de gasto o en Superadmin > Caja chica y horarios. El valor vive en
`system_settings['secretaria.pagos']`.

**¿Las compras en efectivo salen del cierre?**
Sí. Se restan como `compras_efectivo` del efectivo esperado.

## Auditar en 60 segundos

1. Cobros del día = suma de `payments` con `tipo_movimiento=COBRO`.
2. Gastos de caja chica = suma de `GASTO_CAJA_CHICA`.
3. Compras en efectivo = `supplier_payments` con método `EFECTIVO` y bolsa
   `CAJA_DIARIA`.
4. Efectivo esperado = cobros efectivo − caja chica − compras efectivo.
5. Comparar con el conteo físico. Cualquier diferencia debe estar en el cierre.

## Pantallas relacionadas

- Agenda real: mismo componente que Dashboard y Planta.
- Cartera: botón **Cobrar** por fila.
- Planta: compras en tránsito y recepción.
