# Tutorial 04 — Planta, Flota y Kardex

## Qué hace

Muestra existencias reales de insumos, compras en tránsito, kardex teórico vs.
real, flota de mixers y la cola de despachos por camión.

![Planta y kardex](assets/tutoriales/04_planta.png)

## Paso a paso

1. Entrar a **Planta, Flota y Kardex**.
2. Revisar las tarjetas de stock: cemento, arena, ripio, agua y retardante.
3. En **Compras en tránsito**, usar **Recibir** cuando llegue el material.
4. Revisar **Kardex teórico vs. real** y la alerta de merma.
5. En **Flota de mixers**, confirmar placas, capacidad y chofer.
6. En **Agenda de planta**, elegir un mixer para ver solo su cola del día.

## Preguntas frecuentes

**¿Cuándo se actualiza el stock?**
Al registrar una compra con recepción inmediata o al recibir una compra en
tránsito. La venta consume kardex teórico según la receta.

**¿Por qué el stock dice SIN_LEVANTAR?**
Porque falta el conteo físico. Se registra en Superadmin > Tasas y conteo de
silos.

**¿Qué significa merma?**
Diferencia entre consumo teórico y real. El umbral se configura en Superadmin.

## Auditar en 60 segundos

1. Stock actual = movimientos de inventario acumulados.
2. Compras en tránsito = `purchase_items` con cantidad recibida menor a la
   comprada.
3. Movimientos recientes = últimos 20 de `inventory_movements`.
4. Cola de planta = `dispatch_schedule` del día filtrada por mixer.

## Advertencias

- No ajustar stock a mano sin registrar el conteo físico.
- No recibir más cantidad de la comprada.
- El costo promedio se actualiza con cada compra; no se escribe en el frontend.
