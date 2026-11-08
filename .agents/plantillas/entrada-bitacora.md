# Plantilla de entrada de bitácora

Copiar al final de `.agents/BITACORA.md`. No borrar entradas anteriores.

```markdown
## AAAA-MM-DD — Título corto de la sesión

**Agente:**
**Duración:**
**Objetivo:**

### Hecho
1.
2.

### Evidencia (real, ejecutada)

| Comando | Resultado |
|---|---|
|  |  |

### Decisiones tomadas
1. **Decisión.** Motivo. Alternativa descartada.

### Bloqueos / preguntas al cliente
1.

### Próximo paso exacto
(Una acción concreta, no un tema. Si aplica, con el comando literal.)

### Archivos tocados
-
```

## Reglas

- **Evidencia:** pegar el resultado real, no el esperado. Si falló, se registra
  el fallo y su causa; un fallo documentado vale más que un éxito inventado.
- **Decisiones:** siempre con el porqué y la alternativa descartada.
- **Bloqueos:** si dependen del cliente, decirlo explícitamente y enlazar la
  pregunta en `../docs/00_DECISIONES_PENDIENTES.md`.
- **Próximo paso:** debe poder ejecutarlo otro agente sin preguntar nada.
- **Secretos:** nunca escribir claves, tokens ni teléfonos reales.
