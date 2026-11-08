# Proceso 00 — Método de hitos y Test de Candado

El PDR define 5 hitos y una regla: **no se abre el siguiente hasta sellar el
anterior**. Esta es la forma práctica de aplicarla.

## El ciclo

```
Planificar -> Construir -> Probar -> Cerrar con candado
```

1. **Planificar:** qué entra y qué NO entra en el hito. Se escribe en la
   entrada de bitácora antes de codificar.
2. **Construir:** código + migración + test. Todo dato de negocio que falte va
   `NULL` o marcado `PENDIENTE`.
3. **Probar:** se ejecuta el Test de Candado del hito (no "un test que pasa",
   sino el criterio del PDR).
4. **Cerrar:** se registra la evidencia y se marca 🟢 en `ESTADO.md`. El módulo
   queda congelado: cambios futuros = nueva decisión documentada.

## Anatomía de un Test de Candado

Un candado tiene tres partes y las tres deben quedar escritas:

1. **Preparación:** datos y estado inicial (idealmente un script idempotente).
2. **Acción:** el flujo real que el PDR describe.
3. **Criterio:** condiciones objetivas que deben cumplirse, expresadas como
   `[OK] / [FALLA]` y con código de salida distinto de cero si falla.

El candado se guarda como script en `scripts/` para poder repetirlo. Si el
candado es manual (ej. "la secretaria crea una orden"), se documenta el guion
exacto y se guarda la evidencia (captura o JSON) en `evidencias/`.

## Estados de un hito

| Estado | Significado |
|---|---|
| ⚪ No iniciado | Nada construido |
| 🟡 En curso | Construido total o parcialmente; el candado no está sellado |
| 🟢 Cerrado | Candado ejecutado con evidencia y módulo congelado |

**Importante:** un hito 🟡 por culpa del cliente (falta un dato) **no bloquea
preparar el siguiente**, siempre que se registre como "preparado, no cerrado".
Lo que no se permite es declarar cerrado algo que no pasó su prueba.

## Qué hacer cuando falta un dato del cliente

1. No inventarlo.
2. Dejar el sistema en un estado seguro y explícito (`NULL`, `confirmado =
   false`, `NO_CONFIGURADO`).
3. Escribir la pregunta en `../docs/00_DECISIONES_PENDIENTES.md` y en la
   bitácora.
4. Seguir con la parte que no depende de ese dato.

## Deuda técnica

Si durante un hito aparece algo que hay que arreglar pero no es del alcance, se
anota en la bitácora bajo "Deuda" y se sigue. No se arregla de paso, no se
olvida.
