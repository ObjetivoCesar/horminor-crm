---
name: orminorth-bitacora
description: Registra una sesión de trabajo de Orminorth en la bitácora y actualiza el estado del proyecto. Usar al terminar cualquier sesión, al tomar una decisión de arquitectura, al cargar datos del cliente o cuando aparece un bloqueo nuevo.
---

# Skill: cerrar la sesión en orden

## 1. Añadir la entrada (append-only)

Al final de `.agents/BITACORA.md`, con la plantilla de
`.agents/plantillas/entrada-bitacora.md`:

```markdown
## AAAA-MM-DD — Título corto

**Agente:**
**Duración:**
**Objetivo:**

### Hecho
### Evidencia (real, ejecutada)
### Decisiones tomadas
### Bloqueos / preguntas al cliente
### Próximo paso exacto
### Archivos tocados
```

Nunca borres ni edites entradas viejas. Si te equivocaste, escribe una entrada
nueva que lo corrija y referencia la anterior.

## 2. Actualizar `.agents/ESTADO.md`

Solo si cambió algo real:

- Estado de un hito (⚪ → 🟡 → 🟢).
- Un bloqueo nuevo o resuelto.
- Una decisión de arquitectura vigente.
- El "Próximo paso exacto".

`ESTADO.md` se reescribe; la bitácora no.

## 3. Reglas de calidad

- **Evidencia real**, no esperada. Si falló, se documenta el fallo.
- **Decisiones con el porqué** y la alternativa descartada.
- **Próximo paso ejecutable** por otro agente sin preguntar nada.
- **Sin secretos:** ni claves, ni tokens, ni teléfonos reales.
- Si la salida de un comando es larga: `.agents/evidencias/AAAA-MM-DD_nombre.txt`
  y en la bitácora solo la ruta + resumen.

## 4. Señales de que la sesión no está cerrada

- "Ya casi funciona" sin comando ejecutado.
- Un `TODO` en el código sin entrada en la bitácora.
- Un dato de negocio cargado sin decir de dónde salió.
- Una decisión tomada "porque parecía razonable" sin registrarla.
