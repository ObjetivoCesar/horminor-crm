# Tutorial 05 — Banca y Mercado

## Qué hace

Presenta la cuota de mercado, la valorización, el simulador bancario y los
indicadores financieros que usan Julio y los ases gerenciales.

![Banca y Mercado](assets/tutoriales/05_banca.png)

## Paso a paso

1. Entrar a **Banca y Mercado**.
2. Revisar **Cuota de Mercado Regional** y el período seleccionado.
3. Abrir **Valorización / DCF** y confirmar que las tasas estén completas.
4. Revisar los escenarios del **Simulador Bancario**: monto, plazo, cuota y
   DSCR proyectado.
5. Si falta una tasa, cargarla en Superadmin > Tasas y conteo de silos.

## Preguntas frecuentes

**¿Por qué el DSCR aparece vacío?**
Porque faltan tasas financieras confirmadas (WACC, crecimiento, impuesto,
inflación, DSCR mínimo). El sistema no inventa esos valores.

**¿Qué significa cuota de mercado 0.31%?**
Es la producción de Horminor dividida para el mercado estimado de la zona. Si
el benchmark no está confirmado, se muestra como referencia.

**¿El simulador compromete un préstamo?**
No. Solo proyecta escenarios; no registra deuda ni pago.

## Auditar en 60 segundos

1. Ventas del período = órdenes no anuladas.
2. Cuota = volumen Horminor / mercado del período.
3. DSCR = flujo incremental del equipo / cuota mensual.
4. Verificar que las tasas usadas sean las mismas de Superadmin.
5. Comparar el total facturado con la cartera de clientes.

## Advertencias

- No cambiar tasas para "mejorar" el DSCR sin aprobación de Julio/Contadora.
- No usar el simulador como una obligación financiera.
- Los benchmarks provinciales son datos de mercado, no precios de venta.
