# Skill madre: documentos y una sola verdad

> **Cuándo usarla:** al abrir una sesión, al cambiar una decisión, al terminar
> una función, o cuando dos documentos se contradicen.
>
> **Regla que protege:** una sesión nueva leerá el documento equivocado y
> escribirá código que rompe lo que ya funciona. Este proyecto ya perdió tiempo
> por eso.

## 1. Qué se lee al empezar (en este orden)

1. `AGENTS.md` (contrato operativo).
2. **`docs/HITOS.md` (orden de trabajo vigente)**.
3. `.agents/ESTADO.md` (foto del presente).
4. Últimas 3 entradas de `.agents/BITACORA.md`.
4. El documento del área que vas a tocar (`.agents/MAPA_MODULOS.md` dice cuál).

**No leas todo el proyecto.** Si necesitas leer más de lo que dice este orden,
el documento del área está incompleto: complétalo antes de programar.

## 2. Una sola verdad

- Cada tema tiene **un** documento dueño. Los demás lo enlazan, no lo copian.
- Si cambias una decisión, actualizas el dueño **en la misma sesión**.
- El documento viejo se **borra** o se mueve a `.agents/archivo/` (solo si tiene
  valor histórico). No se deja "por si acaso".
- Está prohibido dejar dos fuentes que se contradigan, aunque una diga "BETA" o
  "antiguo".

## 2.1 Qué va en cada documento (no duplicar)

| Documento | Qué guarda | Qué NO guarda |
|---|---|---|
| `docs/HITOS.md` | Orden, criterios de cierre, estado en una línea, registro de avance con **enlaces** | Narrativa, comandos, decisiones largas |
| `.agents/BITACORA.md` | Historia: qué se hizo, con qué, evidencia, decisiones y bloqueos | El plan vigente |
| `.agents/ESTADO.md` | Foto del presente: dónde corre, qué está roto, bloqueos | La tabla de hitos (esa vive en HITOS) |

**Regla:** HITOS **enlaza**, no copia. Si una fila del registro de avance repite
lo que ya cuenta la bitácora, se borra la fila o se deja solo el enlace.

## 3. Qué hacer al cerrar

1. Añadir la entrada de bitácora (append-only).
2. Actualizar `ESTADO.md` si cambió el presente.
3. Actualizar el documento dueño del tema.
4. Borrar o archivar lo que dejó de ser cierto.
5. Si cambió una función visible: `docs/HORMINOR_MANUAL_FUNCIONAL.md`.
6. Si cambió una decisión de arquitectura:
   `docs/CONTINUIDAD_CEREBRO.md`.
7. Si hay una forma nueva de extenderse sin leer todo:
   escribirla en el documento de contrato del área (por ejemplo
   `docs/MOMENTO_CERO.md`).

## 4. Checklist antes de programar

- [ ] ¿Este documento es el dueño del tema o una copia vieja?
- [ ] ¿La decisión que voy a implementar está escrita y es la vigente?
- [ ] ¿Hay dos documentos que digan cosas distintas?
- [ ] ¿La extensión que voy a hacer cabe en un contrato existente?
- [ ] ¿Al terminar, qué documento actualizo y cuál borro?

## 5. Señales de alarma

- Un documento dice "pendiente" de algo que ya está implementado.
- Dos documentos listan módulos distintos.
- Un documento describe una ruta que ya no existe.
- Una skill manda leer archivos que ya no existen.

Cuando aparezca una, no la ignores: se corrige en esa sesión.
