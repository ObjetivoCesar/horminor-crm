# Tutorial 01 — Dashboard de Julio

## Qué hace

Es la vista gerencial para ver en segundos cómo se mueve la operación:
cuota de mercado, ventas del período, mixers en calle, agenda real de entregas
y alertas del Centinela.

![Dashboard de Julio](assets/tutoriales/01_dashboard.png)

## Paso a paso

1. Entrar a `/panel` y seleccionar **Dashboard Julio** en el menú superior.
2. Revisar las tres tarjetas superiores: mercado, ventas y provincias.
3. Usar los filtros de período, planta, resistencia y estado de pago.
4. Bajar a **Mixers en calle** para ver las obras activas.
5. Revisar la **Agenda real** (`HorminorAgenda`): es la misma agenda de
   Secretaría y Planta. Un clic en un día muestra las entregas.
6. Abrir **Detalle operativo** si se necesita caja, mixers o bodega.

## Preguntas frecuentes

**¿Por qué la agenda no muestra un despacho?**
Porque la entrega no está en `dispatch_schedule`, está cancelada o la fecha
está fuera del rango visible. La agenda no se llena con `orders.created_at`.

**¿Por qué el mercado muestra 0.31%?**
Es la cuota calculada con la producción del período contra el mercado estimado
de El Coca. Si falta el benchmark provincial, el número queda como referencia.

**¿Puedo crear una entrega desde aquí?**
Sí. Usar **+ Agendar desde obra (Reserva)**. Se abre el mismo formulario de
Secretaría y el estado inicial es `RESERVA_CAMPO`.

## Auditar en 60 segundos

1. Comparar **Ventas del período** con la suma de órdenes no anuladas.
2. Revisar que **Mixers en calle** coincida con la agenda de hoy.
3. Abrir el cierre de caja del día en Secretaría y comparar el efectivo
   esperado con el dashboard.
4. Si hay una alerta del Centinela, abrir la campana y leer el chequeo exacto.

## Datos que no se inventan

- Mercado total, benchmarks por provincia y merma crítica salen de
  `system_settings`/configuración. Si faltan, el dashboard lo indica.
- Las ventas históricas sin IVA pueden aparecer con su total neto.
