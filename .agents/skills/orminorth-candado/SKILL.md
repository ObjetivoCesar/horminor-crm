---
name: orminorth-candado
description: Ejecuta e interpreta el Test de Candado del Hito 1 de Orminorth (pedido del Ing. Reyes, reparto de viajes, kardex y recetas). Usar cuando hay que comprobar si el Módulo 0 está listo para cerrarse o cuando se cargaron recetas nuevas.
---

# Skill: Test de Candado del Hito 1

## Ejecutar

```powershell
docker compose run --rm --no-deps core-api python scripts/hito1_lock_test.py
```

El script es idempotente: borra y recrea solo las órdenes con `notas = 'HITO1-LOCK'`.
No toca datos reales.

Modo diagnóstico (calcula el kardex con la receta provisional derivada del PDR):

```powershell
docker compose run --rm --no-deps core-api python scripts/hito1_lock_test.py --provisional
```

## Qué verifica

1. Migraciones aplicadas y 12 tablas creadas.
2. 320 m³ FC-210 → exactamente 40 viajes de 8 m³.
3. 52 m³ FC-350 → 7 viajes (6×8 + 4) con política `ultimo_parcial`.
4. La suma de volúmenes coincide con lo pedido.
5. `mixer_dispatches` y `v_dispatch_timeline` devuelven las filas.
6. `v_inventario` devuelve los 5 materiales.

## Cómo interpretar

- Todos `[OK]`, "CANDADO ABIERTO", 0 movimientos de kardex → estructura
  correcta, **recetas sin confirmar**. Es el estado esperado mientras Julio no
  entregue la dosificación.
- Todos `[OK]` + "receta PROVISIONAL" en el listado → falta validar la receta.
- Con `--provisional`: 80 movimientos (40 viajes × cemento + retardante) y
  2.400 sacos / 384 L para 320 m³. Si no cuadra, el motor está mal; **no** el dato.
- Cualquier `[FALLA]` → el script sale con código 1. No se cierra el hito.

## Regla de cierre

El Hito 1 solo se marca 🟢 cuando, con las recetas reales cargadas
(`procesos/04-datos-negocio.md`):

1. El candado da todos `[OK]`.
2. El kardex se genera **sin** aviso de provisional.
3. La salida queda registrada en `.agents/BITACORA.md` y en `ESTADO.md`.

Nunca "arregles" el candado bajando el criterio (por ejemplo, aceptando 6 viajes
para 52 m³ sin que el cliente haya definido esa política).
