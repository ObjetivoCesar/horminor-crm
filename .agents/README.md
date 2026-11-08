# `.agents/` — Memoria operativa de Orminorth

Esta carpeta existe para que el proyecto siga siendo entendible dentro de tres
días, tres semanas o tres meses, y para que **cualquier agente** (OpenCode,
Antigravity, Codex, Claude) retome el trabajo sin rehacer preguntas ni inventar
contexto.

No depende de una herramienta. Son archivos Markdown planos que viajan con el
repositorio.

## Cómo está organizado

| Ruta | Para qué | Cuándo se lee |
|---|---|---|
| `ESTADO.md` | Tablero: hitos, bloqueos, próximo paso | **Al empezar toda sesión** |
| `BITACORA.md` | Registro append-only de sesiones y decisiones | Al empezar (últimas 3) y al cerrar (añadir) |
| `procesos/` | Procedimientos paso a paso | Cuando la tarea coincide |
| `skills/` | Instrucciones autocontenidas para tareas repetibles | Cuando la tarea coincide |
| `plantillas/` | Formatos para no improvisar | Al escribir |
| `evidencias/` | Salidas reales de comandos y tests | Cuando hace falta probar algo |

## El ciclo (la parte que evita perder la cordura)

```
ESTADO  ->  trabajar  ->  verificar con evidencia  ->  BITACORA  ->  ESTADO
```

1. **Antes:** leer `ESTADO.md` y las últimas entradas.
2. **Durante:** si algo no está en el PDR, se pregunta; no se rellena.
3. **Al probar:** la salida real va a `evidencias/` o queda citada en la bitácora.
4. **Al cerrar:** entrada nueva + tabla de estado actualizada.

Regla de oro: **si no está en la bitácora, no pasó**. Una sesión sin entrada es
una sesión que el siguiente agente tendrá que repetir.

## Sobre `context-mode` (Antigravity)

El documento de referencia de la agencia describe el MCP `context-mode` para
Antigravity (`ctx_search`, `ctx_index`, `ctx_execute`, `ctx_stats`), que indexa
salidas grandes en un sandbox para no contaminar el contexto.

Ese servidor **no está instalado en este entorno y no hace falta instalarlo**.
La misma disciplina se aplica a mano:

- Las salidas voluminosas se escriben en `.agents/evidencias/`.
- En la conversación se cita la ruta y un resumen de 3 líneas.
- La bitácora guarda **conclusiones**, no volcados.

Si más adelante quieren montar `context-mode` en Antigravity para este
proyecto, esta carpeta sigue siendo válida: el MCP acelera la búsqueda, no
reemplaza la memoria escrita.

## Reglas de esta carpeta

- `BITACORA.md` es **append-only**: nunca se borra una entrada. Si algo se
  corrigió, se escribe una entrada nueva que lo diga.
- `ESTADO.md` sí se reescribe: es una foto del presente, no historia.
- Las skills son instrucciones para agentes, no documentación para el cliente.
- Nada de secretos: claves, tokens y teléfonos reales no entran aquí.
