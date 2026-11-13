# Correcciones a la respuesta de Carbon — Dashboard de Julio

> **Veredicto:** el diseño se acepta. La arquitectura de decisiones, la
> taxonomía de filtros, los presets, el modelo de capacidad y la rúbrica son
> sólidos. El SQL y la integración con el repo actual tienen errores que
> impiden ejecutarlo. Esta hoja los corrige.
>
> **Base de contraste:** PostgreSQL local, 2026-11-13, 37 tablas, 8 vistas,
> 26 migraciones, 386 tests.

---

## A. Errores que bloquean la ejecución

| # | Carbon dice | La base real tiene | Corrección exacta | Dónde |
|---|---|---|---|---|
| A1 | `orders.fecha` | `orders.created_at` (no existe `fecha`) | `o.created_at::date` | `CONSULTAS.sql` Q1 (líneas 576, 604, 632), Q1b (632), Q3b (750), Q4 (796, 533) |
| A2 | `orders.plant_id` | `orders.planta_id` | `o.planta_id` | Q1 (573, 579), Q1b (634), taxonomía (132) |
| A3 | `concrete_recipes.codigo`, `cemento_sacos`, `arena_m3`, `ripio_m3`, `retardante_litros`, `agua_litros` | `resistencia`, `cemento_sacos_m3`, `arena_m3_m3`, `ripio_m3_m3`, `retardante_litros_m3`, `agua_litros_m3` | Renombrar las 5 ramas del `UNION ALL` y usar `cr.resistencia` | Q2 (666–674) |
| A4 | `PUT /api/v1/superadmin/settings` | `PUT /api/v1/superadmin/config/{seccion}` | Usar la ruta real o crear alias | `CONFIG_CAPACIDAD.json` meta (439) |
| A5 | `flota_y_operacion` lee/escribe `capacidad_plantas`, `supuestos_capacidad`, `umbrales_ocupacion` | Solo lee/escribe `mixers`, `politica_ultimo_viaje`, `reloj_termico` | Extender `leer_seccion`/`guardar_seccion` de `store.py` (397–421 y 561–589) | C0 |
| A6 | `viajes_max_dia` se guarda desde el formulario | `_normalizar_mixer()` lo descarta: solo devuelve `codigo`, `placa`, `capacidad_m3`, `chofer_asignado`, `activo` | Agregar `viajes_max_dia` y `planta_asignada` a `_normalizar_mixer` (store.py:188–203) y al store en memoria | C0 |
| A7 | Serie: 8-nov = 2 ejecutados; 9-nov = 49 programados | Los 2 viajes con `salida_planta` son del **9-nov** (orden #57). El 8-nov tiene 2 viajes `PROGRAMADO` (orden #9) | Agrupar por fecha del **viaje** (`COALESCE(salida_planta, md.created_at)`), no por `orders.fecha` | Q1b (616–638) y ejemplo 1105–1107 |
| A8 | `#view-dashboard.panel-section` | `<section class="view active" data-view="dashboard">` | Conservar el wrapper real y agregar solo los IDs nuevos | UI_SPEC (977) |
| A9 | `CONTRATO_METRICAS.json` dentro de un bloque ` ```json ` | El bloque no cierra antes de `ARCHIVO 4`; el JSON no parsea | Cerrar el fence o separar los 8 archivos | Respuesta (261–432) |

---

## B. Errores de coherencia (no bloquean, pero mienten)

| # | Carbon dice | Verdad | Corrección |
|---|---|---|---|
| B1 | Arena neta 251,880 m³; Ripio neto 289,280 m³ | El kardex del 8-nov **omite** 8,32 m³ de arena y 10,88 m³ de ripio (Carbon mismo lo detecta en A2). Si se corrige: **243,56** y **278,40** | Mostrar las dos lecturas: `neto_registrado` y `neto_corregido_por_asimetria`; no una sola |
| B2 | `P4: $1.085,60 con viaje salido` | Los **2** viajes de la orden #57 tienen `salida_planta` (16 m³ = $2.171,20). El confirmado es 8 m³ = $1.085,60 | Etiquetar "recepción confirmada", no "viaje salido" |
| B3 | `T06: 251/249 registros` | Hay **249** movimientos | Corregir el typo |
| B4 | `T01`: acepta `CONFIGURACION_INCONSISTENTE` **o** `NO_CONFIGURADO` | Un test con dos respuestas posibles no prueba nada | Fijar el estado exacto para la semilla actual |
| B5 | Capacidad de jornada 84 m³/día en T02 | 660 min / 110 min = 6 viajes por mixer × 7 m³ × 2 = 84 | Correcto; mantener el supuesto visible |
| B6 | `cobertura_neta_pct` de cemento 8,97 % | 288 / 3.212 = 8,97 % | Correcto; sirve como alerta |
| B7 | `ventas_equivalencia.m3_fc210_disponibles_neto_kardex = 38,4` | 288 / 7,5 = 38,4 | Correcto |

---

## C. Lo que Carbon hizo mejor que el análisis previo

1. **Corrigió la aritmética del cemento:** el total teórico es **3.212** sacos
   (120 del 8-nov + 3.092 del 9-nov), no 3.092. Si 3.500 era el stock inicial,
   quedan **288**, no 408.
2. **Detectó el retardante crítico:** 600 − 526,4 = **73,6 L**, por debajo del
   mínimo de 100.
3. **Detectó la asimetría del 8-nov:** 2 viajes descontaron cemento y
   retardante, pero no arena (8,32 m³), ripio (10,88 m³) ni agua (2.960 L).
4. **Cascada FIFO bietápica** para pagos sin `order_id` y facturación parcial.
5. **Exclusión de la factura ficticia** `PRUEBA-0001`; el total único queda en
   **55.043,60**.
6. **Separación ejecutado vs programado** en la serie de viajes.
7. **Estados de capacidad** `NO_CONFIGURADO` / `CONFIGURACION_INCONSISTENTE`.
8. **Presets de cobranza** con SQL lógico y salida esperada.

Estos ocho puntos se conservan tal cual.

---

## D. Correcciones de implementación (código, no diseño)

### D1. `CONSULTAS.sql` — parches exactos

```sql
-- Q1 / Q1b / Q3b / Q4
o.created_at::date            -- en lugar de o.fecha
o.planta_id                   -- en lugar de o.plant_id

-- Q2
SELECT cr.resistencia, 'CEMENTO', cr.cemento_sacos_m3::numeric(14,4)
UNION ALL SELECT cr.resistencia, 'ARENA', cr.arena_m3_m3::numeric(14,4)
UNION ALL SELECT cr.resistencia, 'RIPIO', cr.ripio_m3_m3::numeric(14,4)
UNION ALL SELECT cr.resistencia, 'RETARDANTE', cr.retardante_litros_m3::numeric(14,4)
UNION ALL SELECT cr.resistencia, 'AGUA', cr.agua_litros_m3::numeric(14,4)
```

### D2. Serie diaria — agrupar por viaje

```sql
LEFT JOIN public.mixer_dispatches md
       ON COALESCE(
            (md.tracking_payload->'tiempos_forenses'->>'salida_planta')::timestamptz,
            md.created_at
          )::date = gs.dia::date
```

### D3. Superadmin — extender el contrato de flota

En `store.py`:

```python
def _normalizar_mixer(datos):
    ...
    return {
        "codigo": ...,
        "placa": ...,
        "capacidad_m3": capacidad,
        "viajes_max_dia": int(datos.get("viajes_max_dia") or 0),
        "planta_asignada": _texto(datos.get("planta_asignada")),
        "chofer_asignado": ...,
        "activo": ...,
    }
```

Y en `leer_seccion(SECCION_FLOTA)` devolver además:

```python
"capacidad_plantas": await self._setting("flota.capacidad_plantas", {}),
"supuestos_capacidad": await self._setting("flota.supuestos_capacidad", {}),
"umbrales_ocupacion": await self._setting("operacion.umbrales_ocupacion", {}),
```

Guardar esos tres en `guardar_seccion`. Sin esto, la fase C0 no persiste.

### D4. UI — wrapper real

No renombrar `<section class="view" data-view="dashboard">`. Agregar
`id="view-dashboard"` si hace falta, pero conservar `class="view"` y
`data-view="dashboard"` para no romper los 386 tests.

### D5. Tests — estados exactos

- `T01` debe esperar **un** estado: `CONFIGURACION_INCONSISTENTE` para la
  semilla actual (3 mixers, sin `viajes_max_dia`).
- `T06` debe leer **249** movimientos.
- `T13` debe verificar el wrapper real, no `panel-section`.

---

## E. Preguntas que siguen abiertas (bloquean el cierre)

1. **Flota real:** ¿2 camiones de 7 m³? ¿El tercero de la semilla existe o está
   inactivo?
2. **Stock físico:** ¿3.500 sacos es el stock de hoy o el inicial? ¿Los 249
   movimientos son consumos reales?
3. **Cobrable:** ¿la orden confirmada sin entregar se cobra, o solo lo
   entregado/facturado?
4. **Capacidad de planta:** m³/hora y horas efectivas.
5. **Días de crédito y umbral de mora.**
6. **Umbral de ocupación** (70/90 propuesto).

Mientras no haya respuesta: `NO_CONFIGURADO` / `CONFIGURACION_INCONSISTENTE`,
nunca un número inventado.

---

## F. Criterio de aceptación de la versión corregida

1. `Q1`–`Q4` ejecutan sin error contra la base local.
2. `T01`–`T14` en verde; los 386 tests previos siguen en verde.
3. Capacidad: `CONFIGURACION_INCONSISTENTE` con la semilla; `42.00` al cargar
   2×7×3.
4. Cobranza: total único `55.043,60`; factura ficticia excluida; Δ = 0,00.
5. Inventario: cemento 3.212 necesarios, 288 netos, retardante 73,6 L.
6. UI: banner Ventanilla primero, activa amarilla, Agenda real, sin errores de
   consola.
7. Sin floats, sin datos inventados, sin placeholders.

---

## G. Mensaje corto para devolverle a Carbon

```text
El diseño se acepta. Antes de implementar, corrige estos puntos:
1. orders no tiene `fecha`: usa created_at::date.
2. orders no tiene `plant_id`: usa planta_id.
3. concrete_recipes usa resistencia, cemento_sacos_m3, arena_m3_m3,
   ripio_m3_m3, retardante_litros_m3, agua_litros_m3.
4. La ruta es /api/v1/superadmin/config/{seccion}, no /settings.
5. flota_y_operacion solo persiste mixers, politica y reloj: agrega
   capacidad_plantas, supuestos_capacidad y umbrales_ocupacion en store.py.
6. _normalizar_mixer descarta viajes_max_dia: agrégalo.
7. La serie diaria está invertida: los 2 viajes con salida son del 9-nov.
   Agrupa por fecha del viaje, no por orders.fecha.
8. Arena/ripio netos: 243,56 y 278,40 si corriges la asimetría del 8-nov;
   muestra las dos lecturas.
9. El wrapper real es <section class="view" data-view="dashboard">.
10. Cierra el fence de CONTRATO_METRICAS.json; hoy no parsea.
11. T06 son 249 movimientos, no 251.
12. T01 debe esperar un solo estado.
```
