# Manual de manejo — Dashboard de Julio (borrador de trabajo)

> **Estado:** notas vivas. Se convertirán en el manual final cuando C5/C6 esté
> cerrado y Julio valide los datos. No es todavía un documento para imprimir.
>
> **Última actualización:** 2026-11-13.
> **Fuente:** `docs/DASHBOARD_JULIO_ANALISIS.md`,
> `docs/DASHBOARD_OPERATIVO.md`, `docs/CARBON_CORRECCIONES_DASHBOARD.md`.

---

## 1. Para quién es este manual

| Persona | Qué usa | Qué decide |
|---|---|---|
| **Julio** (Gerente) | Las 4 ventanas | Aceptar/reprogramar pedidos, comprar material, llamar a cobrar |
| **Secretaría** | Cobranza y caja, Agenda | Cobrar, agendar, capturar vencimientos |
| **Bodega** | Inventario vs ventas, Inventario por fechas | Comprar, contar, avisar merma |
| **Contadora** | Cobranza y caja | Aging, DSO, conciliación |
| **Superadmin** | Configuración | Flota, capacidad, umbrales |

---

## 2. Qué es y qué no es el tablero

**Es** una cabina de decisión: cada ventana responde una pregunta y propone una
acción.

**No es** un reporte histórico ni un adorno. Si un número no cambia una
decisión, no está arriba.

**Regla de oro:** si falta un dato, el tablero lo dice. No muestra un cero
disfrazado ni un promedio inventado.

---

## 3. Las cuatro ventanas

El banner superior (`¿Qué necesitas decidir hoy?`) es lo primero. La ventana
activa se pinta en **amarillo sólido**. Al cambiar de ventana cambian el
submenú, las 3 tarjetas KPI y los gráficos.

### 3.1 Operación y capacidad (por defecto)

**Pregunta:** ¿cuánto puedo producir y entregar hoy y qué puedo prometer?

**Qué muestra:**
- **Capacidad declarada:** `min(flota, planta, jornada)`. Con 2 camiones de
  7 m³ y 3 viajes/día = **42 m³/día**.
- **Comprometido hoy/semana/mes** contra esa capacidad.
- **Vendido sin plan:** m³ confirmados que no tienen agenda.
- **Sin despachar:** m³ que aún no han salido de planta.
- **Serie por día:** viajes ejecutados (sólido) vs programados sin salida
  (gris).
- **Mezcla por resistencia:** FC-210, FC-350, etc.

**Estados que puede ver:**
- `CONFIGURACION_INCONSISTENTE`: la flota configurada no coincide con la
  declarada. **No se inventa capacidad.**
- `NO_CONFIGURADO`: falta `viajes_max_dia` o la capacidad de planta.
- `CONFIGURADO_PARCIAL`: hay flota, pero falta planta.
- `LIBRE` / `AJUSTADO` / `SATURADO`: semáforo de ocupación (cuando los umbrales
  estén confirmados).

**Acción:**
- Si `SATURADO`: no prometer más para hoy; pasar al siguiente día hábil.
- Si hay **vendido sin plan**: Secretaría debe agendar antes de prometer.
- Si `CONFIGURACION_INCONSISTENTE`: Julio debe reconciliar la flota en
  Superadmin.

### 3.1.1 Meta comercial y punto de equilibrio

**No son lo mismo.** El tablero muestra los dos por separado:

| Indicador | Qué responde | Qué necesita |
|---|---|---|
| **Meta comercial** | ¿superamos el objetivo de ventas del mes? | meta mensual en m³ (Superadmin) |
| **Punto de equilibrio contable** | ¿cuántos m³ cubren los costos fijos? | costos fijos, costo variable/m³ y precio/m³ |

**Meta comercial:**
- `cumplimiento = vendido_mes / meta_mensual`.
- Si `vendido_mes > meta`, el mensaje es motivador: “Superaste la meta por X m³
  = Y días de planta”.
- Los “días de planta” salen de `(vendido_mes − meta) / capacidad_día`. Si la
  capacidad no está declarada, se muestra la diferencia en m³ pero no los días.
- Si no hay meta: `NO_CONFIGURADO`; no se inventa un objetivo.

**Punto de equilibrio contable:**
- `margen_m3 = precio_m3 − costo_variable_m3`.
- `punto_equilibrio_m3 = costos_fijos_mensual / margen_m3`.
- Si falta un dato o el margen es ≤ 0: `NO_CONFIGURADO` con la lista de
  faltantes. Nunca se muestra un punto de equilibrio falso.
- La meta comercial **no** es el punto de equilibrio: una puede superarse sin
  cubrir costos fijos.

**Dónde se carga:** Superadmin → Tasas y conteo de silos → “Meta comercial y
punto de equilibrio”.

### 3.2 Inventario vs ventas

**Pregunta:** ¿el material alcanza para lo que ya vendí?

**Qué muestra:**
- **Explosión MRP:** m³ vendidos × receta = material necesario.
- **Tres lecturas por material:**
  1. **Declarado:** `materials.stock_actual` (semilla o conteo).
  2. **Kardex:** stock declarado + movimientos teóricos.
  3. **Corregido por asimetría:** descuenta los insumos que faltan en el kardex
     (caso 8-nov: arena, ripio, agua).
- **Cobertura %** contra el requerido.
- **Material crítico** (el de menor cobertura).
- **m³ FC-210 disponibles** declarados y netos.

**Estados:**
- `FALTA_MATERIAL` (< 100 %): no alcanza.
- `AJUSTADO` (100–120 %): comprar en 24 h.
- `HOLGADO` (> 120 %): operación normal.
- `SIN_LEVANTAR`: material sin stock (agua).

**Acción:**
- `FALTA_MATERIAL`: frenar despacho sin respaldo y comprar el déficit.
- `SIN_CONTEO_FISICO`: ordenar conteo; la alerta usa la lectura más
  conservadora.

### 3.3 Inventario por fechas

**Pregunta:** ¿cómo se movió el material y cuándo fue el último conteo?

**Qué muestra:**
- **Consumo por día** (kardex), separado por material y unidad.
- **Movimientos** (TEORICO, REAL, COMPRA, AJUSTE, ANULACION).
- **Último conteo** por material o `SIN CONTEO`.
- **Asimetrías:** viajes con cemento pero sin áridos/agua (hoy: 2 del 8-nov).

**Acción:**
- Si no hay conteo: Bodega debe levantarlo. Sin conteo, el stock proyectado no
  se activa.
- Si hay asimetría: revisar el viaje y corregir el kardex (no borrar historia).

### 3.4 Cobranza y caja

**Pregunta:** ¿cuánto me deben, qué está vencido y cuánto entra esta semana?

**Qué muestra:**
- **Saldo real único:** factura real reemplaza la orden; la factura ficticia se
  excluye. Hoy: **55.043,60**.
- **Cubos:** Vencida, Por vencer 7, Corriente, Sin vencimiento.
- **Aging de 8 cubos:** 1–30, 31–60, 61–90, >90, por vencer 7/30, corriente,
  sin vencimiento.
- **Exigibilidad:** confirmado/facturado, con salida de planta, sin salir.
- **Caja esperada 7/30 días** y **DSO**.
- **Bandeja de documentos** con cliente, emisión, vencimiento, saldo y cubo.

**Presets (el "juego de filtros"):**
- **Todos:** cartera completa.
- **Urgencia 7 días:** vencido + por vencer esta semana.
- **Mora:** vencido con días de mora.
- **Clientes grandes:** top 5 por saldo.
- **Sin vencimiento:** deuda ciega, no priorizable.
- **Cupo excedido:** saldo > cupo o cliente sin cupo.
- **Listo para cobrar:** recepción confirmada o factura real.

**Estados:**
- `SIN_FECHAS_VENCIMIENTO`: no se puede calcular aging; la caja esperada es
  `null`, no $0,00.
- `SIN_HISTORIAL_PAGOS`: no hay DSO.
- `SIN_CUPO_ASIGNADO`: el cliente tiene deuda pero no cupo configurado.

**Acción:**
- Llamar primero por **monto** o por **días de mora** (según el preset).
- Completar `fecha_vencimiento` en las órdenes/facturas para activar la caja.
- No fiar a quien está en `CUPO_EXCEDIDO` sin aprobación de Julio.

---

## 4. Cómo leer los colores y los badges

| Color / badge | Significado |
|---|---|
| **Amarillo sólido** | Ventana activa |
| **Ámbar** | Ajustado / atención |
| **Rojo** | Vencido / falta material / crítico |
| **Verde** | Holgado / confirmado |
| **Gris** | Sin dato / programado sin ejecutar |
| `SIN_CONTEO`, `SIN_FECHA`, `NO_CONFIGURADO` | El dato no existe; no es un cero |

**Hecho vs plan:** en los gráficos, lo sólido es ejecutado/confirmado; lo gris o
rayado es programado/teórico. No se mezclan.

---

## 5. Qué hacer cuando el tablero dice que falta un dato

### 5.1 Capacidad (`CONFIGURACION_INCONSISTENTE`)

1. Ir a **Superadmin → Recetas, flota y precios**.
2. En la tabla de flota, completar **Viajes máx/día** y **Planta asignada**.
3. En **Capacidad declarada**, cargar m³/hora y horas efectivas de cada planta,
   el ciclo de viaje y los mixers esperados.
4. Guardar. El tablero recalcula sin reiniciar.
5. Si Julio confirma 2 camiones de 7 m³ y 3 viajes/día, la capacidad será
   **42 m³/día**.

> **No se estima.** Si falta un dato, el tablero sigue en `NO_CONFIGURADO`.

### 5.2 Stock (`SIN_CONTEO_FISICO`)

1. Bodega hace el conteo físico.
2. Se registra en **Superadmin → Tasas y conteo de silos** (o en el flujo de
   bodega).
3. Se sella `ultimo_levantamiento_at`.
4. Recién ahí `v_stock_proyectado` empieza a descontar movimientos post-conteo.

### 5.3 Cobranza (`SIN_VENCIMIENTO`)

1. Abrir la orden o factura.
2. Capturar `fecha_vencimiento` (C4, pendiente en formularios).
3. El documento entra al cubo que corresponde y la caja esperada deja de ser
   `null`.

---

## 6. Superadmin: capacidad paso a paso

*(Esta sección se completará con capturas cuando C5 esté cerrado.)*

1. Panel → **Superadmin y WhatsApp** → **Recetas, flota y precios**.
2. **Flota de mixers:** por cada camión:
   - Código, placa, capacidad m³.
   - **Viajes máx/día** (ej. 3).
   - **Planta asignada** (ej. `PLANTA-COCA`).
   - Activo.
3. **Capacidad declarada:**
   - Planta Fija: m³/hora y horas efectivas.
   - Planta Móvil: m³/hora y horas efectivas.
   - Ciclo de viaje (min).
   - Mixers activos esperados.
   - Umbrales de ocupación (70/90 propuesto).
4. Guardar. Verificar en **Operación y capacidad** que el estado cambió.

---

## 7. Glosario

| Término | Significado |
|---|---|
| **m³** | Metro cúbico de hormigón |
| **FC-210 / FC-350** | Resistencia del hormigón (kg/cm²) |
| **MRP** | Explosión de materiales: m³ × receta |
| **Kardex** | Historial de movimientos de inventario |
| **Aging** | Antigüedad de la deuda por tramos |
| **DSO** | Días promedio de cobro |
| **Sin plan** | Vendido sin fecha/mixer en agenda |
| **Sin despachar** | Vendido que aún no salió de planta |
| **Exigible** | Con recepción confirmada o factura real |
| **Documento único** | Factura real reemplaza la orden; no se suman |
| **CONFIGURACION_INCONSISTENTE** | La flota configurada no coincide con la real |
| **NO_CONFIGURADO** | Falta un parámetro; no se inventa |

---

## 8. Limitaciones actuales (a cerrar antes del manual final)

1. **C4 pendiente:** los formularios de orden/factura no capturan
   `fecha_vencimiento`.
2. **Presets de cobranza:** ya filtran la bandeja, pero falta validar con
   Secretaría y Contadora.
3. **Gráficos:** capacidad, despacho, cobertura, kardex y aging ya se dibujan;
   falta pulir en móvil y tema día.
4. **Datos de Julio:** flota 2×7, stock actual/inicial y política de
   exigibilidad siguen sin confirmar.
5. **Manual final:** falta captura de pantalla por ventana, glosario ilustrado y
   firma de Julio.
6. **Meta y punto de equilibrio:** la estructura está lista, pero faltan la meta
   mensual y los costos fijos/variables de la reunión con Julio y Contadora.
7. **Cotizaciones:** falta PDF, envío por WhatsApp y que la factura sume los
   extras de `orden_extras`. La bandeja, aceptación y conversión ya funcionan.

---

## 9. Cotizaciones

**La cotización va antes que la orden.** Aceptar una cotización **no** crea la
orden: solo asigna la etiqueta `VENTA` al cliente. La conversión es un botón
aparte.

**Crear una cotización:**
1. Columna izquierda → **Cotizaciones**.
2. **Nueva cotización**.
3. Cliente, obra, resistencia y volumen.
4. El precio se llena con la lista de Superadmin. Si dice `PROVISIONAL`, no es
   un precio oficial: Julio debe cambiarlo en Superadmin.
5. Extras: un solo rubro global, descripción libre. Si **no** es cobrable, es
   costo interno y no se imprime al cliente.
6. Guardar borrador.

**Estados:**
- `BORRADOR`: se puede editar.
- `ACEPTADA`: el cliente aprobó; se asignó `VENTA`.
- `CONVERTIDA`: ya generó una orden.
- `VENCIDA`: pasó la fecha de validez; se re-emite, no se “revive”.

**Aprobación desde Superadmin:** el módulo aparece en la columna izquierda solo
si el perfil tiene marcado **Cotizaciones y ventas** en el checklist de
Superadmin. Julio (Superadmin) lo tiene por defecto; Secretaría y los demás
perfiles lo reciben cuando Julio lo apruebe.

**Límite actual:** la orden conserva su total base; los extras cobrables quedan
en `orden_extras` y la vista `v_orden_total` los suma. La factura todavía no los
incluye. PDF y envío por WhatsApp quedan para la siguiente fase.

## 10. Preguntas que el manual debe responder cuando esté cerrado

1. ¿Qué hago si el tablero dice `SATURADO`?
2. ¿A quién llamo primero: al de mayor saldo o al de mayor mora?
3. ¿Cuándo se considera "cobrable" una orden?
4. ¿Cada cuánto se hace el conteo físico?
5. ¿Quién puede cambiar la capacidad?
6. ¿Qué significa que el cemento esté al 8,97 % de cobertura?
7. ¿Por qué el tablero dice 404 sin plan y 388 sin despachar?
8. ¿Qué pasa si la factura es ficticia?

---

## 11. Bitácora del manual

- **2026-11-13:** creado el borrador con las 4 ventanas, estados, glosario y
  pasos de Superadmin. Pendiente: capturas y validación con Julio.
- **2026-11-13:** agregado el módulo **Cotizaciones** (bandeja, formulario,
  aceptación, conversión y permiso ACL). Pendiente: PDF y WhatsApp.
