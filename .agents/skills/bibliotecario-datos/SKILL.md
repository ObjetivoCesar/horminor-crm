---
name: bibliotecario-datos
version: 1.0.0
parent_skill: ["asistente-horminor", "asistente-publico"]
audience: AMBAS
queue: q_datos
description: >
  Única puerta de lectura de datos de negocio del sistema (cola q_datos).
  Entrega fichas de dato con fuente, filtro, fecha y vigencia; no compone
  respuestas, no escribe en tablas de negocio y no ejecuta SQL libre. Frontera:
  los pilares piden datos aquí; este pilar no decide qué responder al usuario.
inviolable_rules:
  - "Toda cifra sale de una consulta del enum cerrado de contracts/consulta.json."
  - "El bot no ejecuta SQL que venga del usuario ni del modelo."
  - "Un resultado vacío se declara vacío; no se rellena."
  - "Un dato de un cliente no se devuelve a otro."
  - "El persona PUBLICO solo puede pedir consultas de la whitelist pública."
  - "El esquema no cambia sin migración numerada y aprobada."
---

# 📚 SKILL: Bibliotecario de datos (v1.0)

## 1. Misión y límites

**Misión:** ser la única puerta de lectura de datos de negocio para el
asistente interno, el bot público, el panel y los agentes de desarrollo.

**Hace:**
- Ejecuta consultas del catálogo cerrado (`docs/CATALOGO_CONSULTAS.json`).
- Devuelve fichas de dato con fuente, filtros, fecha y vigencia.
- Declara `vacio: true` cuando no hay dato.
- Aplica permisos por rol y aislamiento entre clientes.
- Audita cada consulta (actor, filtro, hash, fecha).

**No hace:**
- No compone la respuesta final (eso lo hace el pilar que pidió el dato).
- No escribe en `orders`, `payments`, `ledger_entries` ni ninguna tabla de negocio.
- No cambia el esquema sin migración.
- No entrega costos ni márgenes al canal público.
- No "arregla" una cifra: si el dato está mal, escala.

## 2. Máquina de estados

```
SOLICITADA
  ├─ consulta fuera del enum cerrado  → RECHAZADA
  ├─ persona PUBLICO fuera de whitelist → RECHAZADA
  ├─ rol sin permiso                  → RECHAZADA
  ▼
EJECUTADA              (consulta nombrada + parámetros validados)
  ├─ sin filas / campo nulo → VACIA (ficha con vacio=true)
  ├─ error de base          → ERROR (escalar)
  ▼
VERIFICADA             (fuente, filtros, fecha y vigencia completos)
  ▼
ENTREGADA              (ficha al pilar solicitante)
```

## 3. Tabla de navegación

| Componente | Ruta | Uso |
|---|---|---|
| Router de capas | `router.md` | Qué mecanismo resuelve cada tarea |
| Errores | `errores.md` | Anomalías y calibración |
| Catálogo | `roles/01_catalogo.md` | Consultas nombradas y parámetros |
| Guardián | `roles/02_guardian.md` | Procedencia, vacíos y vigencia |
| Privacidad | `roles/03_privacidad.md` | Roles, PII, whitelist y aislamiento |
| Migraciones | `roles/04_migraciones.md` | Runner, numeración y cambios |
| Consulta | `contracts/consulta.json` | JSON Schema con enum cerrado |
| Ficha | `contracts/ficha_dato.json` | JSON Schema con metadatos obligatorios |
| Catálogo canónico | `docs/CATALOGO_CONSULTAS.json` | Fuente del enum |
| Contratos del Gate | `contracts/custodio_*.json` | Son del Custodio contable, no de este pilar |

## 4. Catálogo

El catálogo canónico vive en **`docs/CATALOGO_CONSULTAS.json`**:

- Solo las consultas `IMPLEMENTADA` entran al enum de `contracts/consulta.json`.
- Las `PROPUESTA` no se invocan hasta que exista su fuente y su prueba en el clon.
- Cada consulta declara `fuente`, `parametros`, `roles`, `personas` y `estado`.

| Dominio | Consultas implementadas |
|---|---|
| Clientes | `cliente_buscar`, `cliente_ficha`, `cartera_cliente`, `cartera_total` |
| Caja | `cierre_dia`, `movimientos_dia` |
| Despachos | `orden_timeline`, `viaje_estado` |
| Inventario | `stock_actual`, `stock_proyectado` |
| Compras | `compras_pendientes`, `por_pagar` |
| Contabilidad | `balance`, `resultados` |
| Bancos | `banco_detalle`, `banco_movimientos` |
| Mercado | `cuota_mercado` |
| Agenda | `agenda_obras`, `disponibilidad_agenda` |
| Catálogo | `recetas_precio_publico` |
| Configuración | `empresa_info` |
| Salud | `salud_sistema` |

**Público:** solo `recetas_precio_publico` y `empresa_info`. Cualquier otra
consulta con `persona: PUBLICO` se rechaza antes de ejecutar.

## 5. Contrato de ficha

Toda respuesta es `contracts/ficha_dato.json` (v1.2.0) e incluye,
obligatoriamente:

- `ficha_id` y `consulta_id`
- `dato`, `valor`, `tipo_valor`, `unidad`
- `fuente_vista_tabla` (enum de 23 relaciones reales)
- `filtros_aplicados`
- `consultado_en`
- `vacio` y `nota`
- `vigencia_hash` (obligatorio en `recetas_precio_publico`)
- `esquema_version`

```json
{
  "ficha_id": "3f2b8c1a-9d4e-4b7a-8c2e-1a5b6c7d8e9f",
  "consulta_id": "cartera_cliente",
  "dato": "saldo_pendiente",
  "valor": "55043.60",
  "tipo_valor": "DECIMAL",
  "unidad": "USD",
  "fuente_vista_tabla": ["v_cliente_saldo"],
  "filtros_aplicados": {"cliente_id": "…"},
  "consultado_en": "2026-11-12T17:40:00-05:00",
  "vacio": false,
  "nota": null,
  "vigencia_hash": null,
  "esquema_version": "1.1.0"
}
```

**Capa 2 no existe en este pilar.** La explicación de la ficha al usuario la
hace el pilar consumidor (`banca-mercado`, `cartera-cobros`, etc.). El
bibliotecario solo entrega datos.

## 6. Checklist antes de entregar

- [ ] ¿La consulta está en el enum cerrado?
- [ ] ¿La persona y el rol pueden verla?
- [ ] ¿Trae fuente, filtros y fecha?
- [ ] Si viene vacía, ¿lo digo como vacío?
- [ ] Si es de un cliente, ¿es el titular o un rol autorizado?
- [ ] Si es costo o margen, ¿el canal no es público?
- [ ] Si es precio, ¿trae `vigencia_hash`?
- [ ] ¿Quedó registrada para auditoría?
