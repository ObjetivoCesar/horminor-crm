# Auditoría de skills con Carbon — protocolo único (v1.0)

> **Qué es:** el único documento que gobierna las auditorías de skills con
> Carbon. Reemplaza las secciones históricas de auditoría que estaban
> dispersas en `docs/SKILLS_PILARES_HORMINOR.md` (§15 y §16).
>
> **Regla de oro:** Carbon construye; el árbitro audita con contexto separado;
> Dirección aprueba. Ningún pilar se implementa sin veredicto.
>
> Fecha: 2026-11-12.

---

## 1. Flujo

```
1. Pre-vuelo determinista   → scripts/auditar_skills.py
2. Carbon construye 1 pilar → 5 componentes
3. Árbitro audita           → 10 vectores + matriz del pilar
4. Veredicto                → APROBADO / RECHAZADO con hallazgos
5. Corrección y re-auditoría (mínimo una ronda)
6. Registro en §7 + bitácora
7. Recién ahí: implementación en app/asistente/
```

**No se acepta la primera versión.** Si no hubo ronda adversarial, se rechaza
sin leer el contenido.

---

## 2. Pre-vuelo determinista

Script: **`scripts/auditar_skills.py`**.

Comprueba sin IA:

- Los contratos JSON parsean.
- Catálogo: 22 implementadas, 5 propuestas, `requeridos ⊆ parametros`.
- `consulta.json`: enum = implementadas, 12 parámetros, 22 condicionales de
  consulta + 1 whitelist + 1 bloqueo cruzado (24 reglas).
- Cada condicional restringe `actor_context.rol` al array `roles`.
- `persona=PUBLICO` exige `BOT_PUBLICO` y solo dos consultas.
- `persona=INTERNO` no admite `BOT_PUBLICO` (bloqueo cruzado).
- ACL: `balance`, `resultados`, `banco_detalle` y `salud_sistema` fuera de
  `BODEGA` y `SECRETARIA`.
- `ficha_dato.json`: `ficha_id`, `consulta_id`, 23 relaciones en array,
  `tipo_valor` sin `OBJETO|LISTA`, DECIMAL con negativos.
- `solicitud_cotizacion.json`: montos como texto, `ficha_id` UUID y
  `vigencia_hash` de 64 hex.
- Límites: `SKILL.md` ≤ 12.000 caracteres; roles entre 40 y 70 líneas.
- Cero `TODO` y placeholders.

Salida: `APROBADO` / `FALLÓ` con el detalle. Evidencia en
`.agents/evidencias/`.

```powershell
python scripts/auditar_skills.py --salida .agents/evidencias/auditoria_skills_<fecha>.txt
```

---

## 3. Los 10 vectores

### Del estándar v7.0

1. **Solapamiento** con otra skill: ¿hace lo que ya hace un vecino?
2. **Escape de responsabilidad**: ¿puede producir algo prohibido?
3. **Estados ambiguos**: ¿qué pasa si el gate rechaza 3 veces?
4. **Contratos abstractos**: ¿hay campos que permiten basura?
5. **Capa mal asignada**: ¿una tarea de Capa 3 que resuelve Capa 0?

### De Horminor

6. **Cifra inventada**: ¿algún número no viene de una ficha?
7. **Fuga entre clientes**: ¿el rol público ve a otro?
8. **Costo expuesto**: ¿un costo o margen llegó al canal público?
9. **Precio viejo**: ¿se cotizó sin `vigencia_hash` vigente?
10. **Acción sin confirmación**: ¿emitió, cobró o agendó sin aprobación?

---

## 4. Matriz de frentes por pilar

| Pilar | Qué se audita con lupa |
|---|---|
| `bibliotecario-datos` | ACL por consulta, whitelist pública + rol, 23 fuentes, DECIMAL texto, `vigencia_hash`, `ficha_id` 1:1 con PDF |
| `pdf-cotizaciones` | Aritmética Decimal, `vigencia_hash`, folio único, PRELIMINAR, storage caído, cotización ≠ factura |
| `banca-mercado` | Contable ≠ informado, movimientos solo con cuenta hija, benchmark ausente, simulador como proyección, nunca público |
| `cartera-cobros` | Venta ≠ cobro, sobrepago/anticipo 1103/2102, `deleted_at`, PII del cliente, borradores sin ejecutar |
| `caja-cierre` | Doble conteo ventas/cobros, diferencia de efectivo, bolsas, gastos sin rubro |
| `planta-inventario` | Stock real vs teórico, reversa de kardex, `costo_unitario_snapshot`, conteo sin fecha |
| `compras-proveedores` | Crédito vs pago, en tránsito, recepciones, datos de proveedor |
| `agenda-obras-visitas` | Mixers vs asesores, no auto-confirmar, `PENDIENTE_CONFIRMACION`, reagendamiento |
| `configuracion-precios` | Precio vs costo, margen, precio viejo, jamás público, SRI fuera de alcance |
| `contabilidad-reportes` | Balance vs resultados, asientos borrados, tasas faltantes (`UNCONFIRMED_FINANCIAL_RATES`) |
| `solicitudes-publicas` | Estado de la solicitud, confirmación de Secretaría, no prometer plazos |
| `asistente-horminor` / `asistente-publico` | Enrutamiento correcto, cero cruce de personas, catálogo permitido |
| `salud-sistema` | Cero secretos, solo lectura, no exponer logs crudos |

---

## 5. Formato de veredicto

```
VEREDICTO: APROBADO | RECHAZADO
Pilar: <nombre>  Versión: <x.y.z>  Fecha: <AAAA-MM-DD>
Ronda: <n>

Hallazgos:
  H1 [CRÍTICO|ALTO|MEDIO|BAJO] <qué> → <evidencia> → <corrección mínima>
  ...

Checklist §10: <n>/<n>
Vectores: <n>/10
```

- **APROBADO** exige: 5 componentes, checklist completo, 10 vectores sin
  hallazgos críticos y una ronda adversarial cerrada.
- **RECHAZADO** exige al menos un hallazgo con corrección concreta.
- Un hallazgo sin evidencia no cuenta.
- Un `TODO` es rechazo automático.

---

## 6. Qué NO se re-audita (congelado)

Estos puntos ya están cubiertos por el script; si vuelven a fallar, es un
defecto del validador, no del pilar:

1. 22 consultas implementadas y su orden.
2. 12 parámetros sin `folio` y con `fecha`.
3. 23 relaciones reales (sin `sabueso` ni `sentinel`).
4. ACL de `balance`, `resultados`, `banco_detalle` y `salud_sistema`.
5. Whitelist pública con `BOT_PUBLICO`.
6. `ficha_id` UUID y `vigencia_hash` de 64 hex.
7. `precio_ref.ficha_id` 1:1 con la ficha de precio.
8. Montos como texto decimal (incluye negativos).

---

## 7. Registro histórico

| Fecha | Objeto | Hallazgos | Corrección | Estado |
|---|---|---|---|---|
| 2026-11-12 | Handoff v1.0 | 7 estructurales + 2 insumos | Handoff v1.1 + catálogo | CERRADO |
| 2026-11-12 | Propuesta Carbon v1.2 | 2 (OBJETO/LISTA, fuentes con servicios) | Ficha escalar + 23 relaciones | CERRADO |
| 2026-11-12 | Pre-vuelo v1.2 | 3 micro-detalles (ACL en §7, array de fuentes, erratas) | Contratos v1.3 + doc v1.3 | CERRADO |
| 2026-11-12 | Pre-vuelo v1.3 | 2 (bloqueo cruzado no implementado, roles < 40 líneas) | Contratos v1.4 + roles 40–70 | CERRADO |
| 2026-11-12 | Pilar #1 (referencia) | 0 | 5 componentes + 177 checks + 10 vectores | APROBADO (referencia) |
| — | Pilar #1 (entrega Carbon) | — | — | PENDIENTE |

---

## 8. Historial que se movió aquí

Las secciones §15 (cambios v1.1) y §16 (arbitraje v1.2) de
`docs/SKILLS_PILARES_HORMINOR.md` se eliminaron de ese documento para que el
handoff quede solo con lo que Carbon necesita. Su contenido histórico vive en
la tabla de §7. No se perdió nada: la bitácora conserva el detalle.

---

## 9. Dónde más hacen falta auditorías

Además de los 13 pilares de §4, hay tres frentes que no son skills pero se
auditan con el mismo rigor:

1. **Runtime del asistente** (`app/asistente/`): carga de skills, tools,
   guarda de cifras y auditoría por turno. Se audita antes de conectar DeepSeek.
2. **Migración del catálogo**: cada consulta `PROPUESTA` que pase a
   `IMPLEMENTADA` exige prueba en el clon y actualización del enum.
3. **Integración PDF ↔ bibliotecario**: el primer pilar #2 debe probar una
   cotización real con `ficha_id` y `vigencia_hash` vigentes.

---

## 10. Evidencia

Cada auditoría deja:

- Salida del script en `.agents/evidencias/auditoria_skills_<fecha>.txt`.
- Veredicto en el chat y resumen en `.agents/BITACORA.md`.
- Si se aprobó, la versión queda en `.agents/skills/<pilar>/`.

---

## 11. Veredicto de referencia — Pilar #1 `bibliotecario-datos` (2026-11-12)

> **Alcance:** se audita la implementación de referencia del repo
> (`.agents/skills/bibliotecario-datos/`), no una entrega de Carbon. Sirve como
> vara para comparar lo que devuelva Carbon.

**VEREDICTO: APROBADO (referencia)**

| Vector | Resultado | Evidencia |
|---|---|---|
| 1. Solapamiento | OK | Es la única skill que lee la base; los demás pilares piden fichas |
| 2. Escape de responsabilidad | OK | Sin escrituras ni SQL libre; enum cerrado; ACL por consulta; bloqueo cruzado |
| 3. Estados ambiguos | OK | `SOLICITADA → EJECUTADA → VERIFICADA → ENTREGADA`; ramas `RECHAZADA/VACIA/ERROR` |
| 4. Contratos abstractos | OK | 24 `allOf`, `additionalProperties:false`, 12 parámetros, 23 fuentes, UUID y hash 64 hex |
| 5. Capa mal asignada | OK | Capa 2 N/A; 0/1/3 mapeadas en `router.md` |
| 6. Cifra inventada | OK | Ficha con fuente, filtros, fecha, `vacio`, `nota`; `CUARENTENA` bloquea |
| 7. Fuga entre clientes | OK para lo implementado | Whitelist pública + `BOT_PUBLICO`; `mi_resumen` (PROPUESTA) exigirá `tenant_scope.cliente_id` |
| 8. Costo expuesto | OK | `recetas_costo` y `margen_receta` son PROPUESTA y solo roles financieros |
| 9. Precio viejo | OK | `vigencia_hash` obligatorio en `recetas_precio_publico`; PDF lo exige en `precio_ref` |
| 10. Acción sin confirmación | OK | Solo lectura; las escrituras son de otros pilares |

**Checklist §10:** 9/9 archivos, `SKILL.md` 5.480 caracteres, roles 41–53 líneas,
contratos válidos, Cero `TODO`.

**Script:** `python scripts/auditar_skills.py` → **APROBADO (177 verificaciones)**.

**Pendiente conocido:** cuando `mi_resumen` pase de PROPUESTA a IMPLEMENTADA,
agregar el condicional que exige `cliente_id` para `persona=PUBLICO`. Hoy no
existe una consulta pública con datos de cliente, así que no hay hueco activo.
