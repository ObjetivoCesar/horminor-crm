# Experimento D vs D+ — Cerebro Horminor

> **Estado:** arnés experimental. **No toca el motor productivo.**
> **Versión del experimento:** `d-vs-dmas-1.0` · **Arnés:** `harness-1.1`
> **Contratos:** `contracts-1.0` · **Conciliación:** `reconcile-1.0`
> **Prompts:** `a1-v1`, `a2-v1`, `a3-v1`, `d-v1`, `arb-v1`

## Qué hace

Compara tres formas de interpretar un dictado, sin escribir en la base ni
modificar prompts operativos:

| Brazo | Qué es |
|---|---|
| `V7` | motor actual a nivel de interpretación: prompt productivo → hechos → `compilar`, sin base de datos (sin cliente/receta) |
| `D` | una llamada con contrato de órdenes + restricciones, validada por el conciliador |
| `D+` | tres lectores independientes en paralelo (A1 hechos, A2 órdenes, A3 restricciones) + conciliación determinística |
| `D+ARB` | D+ con árbitro LLM **solo** si quedan conflictos |

## Arquitectura

```
dictado
  ├─ V7  : prompt productivo ──► sobre ──► construir_hechos ──► compilar
  ├─ D   : una llamada ──► SobreUnico (asuntos + órdenes + restricciones)
  └─ D+  : A1 hechos ─┐
           A2 órdenes ├─► conciliar() ─► órdenes con estado
           A3 restric. ┘     │
                             └─ conflictos ─► [árbitro opcional]
```

Reglas del conciliador:

1. Toda orden necesita **cita localizable** y **soporte semántico** del tipo.
2. Las restricciones se asocian por **referente** (directo, demostrativo,
   ordinal, anáfora) y por solape de cita.
3. `GLOBAL` exige lenguaje global en la cita; si no, se degrada a `ASUNTO`.
4. Prohibición o dependencia ⇒ orden **BLOQUEADA** (visible, no ejecutable).
5. Referente ambiguo ⇒ conflicto `POR_ACLARAR`.
6. A3 caído ⇒ **ninguna orden avanza**: todas quedan BLOQUEADAS.
7. El conciliador no crea órdenes; solo valida, asocia y bloquea.

## Uso

```powershell
# desde orminorth/
python -m experiments.d_vs_dmas.tests_encoding
python -m experiments.d_vs_dmas.spike --repeticiones 5
python -m experiments.d_vs_dmas.evaluate --brazo all
python -m experiments.d_vs_dmas.inspect E07 E14 E27
python -m experiments.d_vs_dmas.fichas
python -m experiments.d_vs_dmas.idempotencia
python -m experiments.d_vs_dmas.freeze
```

El spike y el evaluador escriben en `experiments/d_vs_dmas/runs/` (ignorado por
git). No requieren la base: leen `DEEPSEEK_API_KEY` del entorno o del `.env`.

**Evaluación:** `evaluate` excluye por defecto E01–E03 (usados para probar el
arnés). Usa `--incluir-prueba` solo para depurar.

**Codificación:** la etapa 1 corrompió literales al editar con PowerShell.
Corregido en `harness-1.1`; `prompts.py` conserva la huella original. La prueba
`tests_encoding` verifica fuente, payload, recepción y archivo.

## Referencia

`reference.py` carga el corpus y la guía **preliminar NO humana**. Todo resultado
se marca `referencia_validada: false`. Los números sirven para validar el arnés,
**no** para declarar calidad. La referencia definitiva debe ser una lectura
humana revisada, independiente del sistema.

## Límites conocidos

- El brazo V7 no resuelve cliente ni receta contra la base: no creará
  cotizaciones. Es una comparación de **interpretación**, no de ejecución.
- El adaptador de la referencia preliminar reduce frases a tipos de orden; no
  evalúa responsables, canales ni restricciones.
- El coste en USD requiere precios configurados; por ahora se miden tokens.
- Tres lectores del mismo modelo no garantizan independencia estadística.
