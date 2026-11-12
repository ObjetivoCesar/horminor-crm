# Tutorial 03 — Carpetas de Clientes

## Qué hace

Es el buscador y expediente de clientes. Permite encontrar a alguien aunque no
se recuerde el nombre exacto, filtrar por deuda/obra/pagos y revisar órdenes,
viajes, abonos y ficha en un solo lugar.

![Carpetas de Clientes](assets/tutoriales/03_carpetas_clientes.png)

## Paso a paso

### Encontrar un cliente

1. Entrar a **Carpetas de Clientes**.
2. Usar el buscador **Sabueso** con:
   - nombre o apellido en cualquier orden: `reyes julio`, `baca beles`;
   - volumen: `7m3`, `16 m3`;
   - resistencia: `FC-210`, `fc210`;
   - número de orden: `#56`;
   - obra o ciudad: `Loreto`, `El Coca`;
   - referencia de pago: `transferencia`.
3. Revisar el subtítulo **Coincide con:** para confirmar por qué apareció.
4. Hacer clic en el cliente o en una sugerencia del autocompletado.

### Filtrar la cartera

- **Con deuda / Fiado:** ordena de mayor a menor deuda.
- **En obra / Entregas activas:** clientes con órdenes recientes o agenda.
- **Pagos y Transferencias:** clientes con cobros o saldo a favor.
- **Todos y Prospectos:** padrón completo y leads de WhatsApp.

Combinar con ciudad, forma de pago, fecha, resistencia, rango de m³ y orden.
La lista se pagina de 12 en 12.

### Revisar el expediente

1. **Órdenes y Viajes:** cada orden tiene un botón `Ver N viajes ▾`; solo se
   despliegan los viajes de esa orden.
2. **Pagos y Estado de Cuenta:** cobros, abonos y anticipos.
3. **Ficha y Datos:** nombre, constructora, RUC, WhatsApp, ciudad, obra
   frecuente y cupo de crédito.
4. **💬 Chat:** espejo de la conversación de WhatsApp con ese cliente. Se
   escribe en el cuadro de abajo; `Enter` envía y `Shift+Enter` salta de línea.
   El clip 📎 abre Galería, Cámara, Documento, Audio, Ubicación y Contacto.
   Las fotos se convierten a WebP y los videos se comprimen antes de subirse a
   Bunny; el audio se envía tal cual. Mientras Evolution no esté conectado, los
   mensajes quedan en cola (`PENDIENTE`) y se avisa en la cabecera. El número
   sobre la pestaña indica mensajes entrantes sin leer.

## Preguntas frecuentes

**¿Por qué no encuentra “Vaca” si escribo “baca”?**
El buscador normaliza b/v, z/s/c, ll/y y elimina tildes. Si el cliente fue
guardado con otro texto, probar con una palabra de la obra o `#orden`.

**¿Por qué un cliente aparece como prospecto?**
Su estado es `PROSPECTO` o no tiene órdenes. Se puede cambiar en la ficha.

**¿Cómo creo un cliente?**
Botón **+ Nuevo cliente** en la tarjeta de la lista o al final del banner.
Nombre es obligatorio; ciudad, obra y cupo son opcionales.

## Auditar en 60 segundos

1. Verificar que **Con deuda** coincida con la suma de `v_cliente_saldo`.
2. Abrir el cliente y comparar saldo pendiente con sus órdenes y pagos.
3. Confirmar que los viajes mostrados pertenecen a la orden expandida.
4. Revisar que la ficha tenga ciudad/obra si se usan filtros por zona.

## Lo que el bot no debe hacer

- No afirmar que un cliente no existe si la búsqueda no devuelve resultados;
  pedir otro dato (obra, orden, teléfono).
- No cambiar cupo de crédito sin confirmación.
- No borrar clientes: el sistema no tiene borrado destructivo en esta etapa.
