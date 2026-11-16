# Router Horminor — prototipo aislado

> **Qué es.** El Cerebro como asistente de dirección: escucha, interpreta,
> organiza el trabajo, propone responsables y espera la confirmación de Julio.
> **No ejecuta nada.** Al confirmar devuelve el plan de lo que se crearía.
>
> **Versión:** `router-1.5` · **Estado:** prototipo en el experimento, sin tocar
> el panel productivo ni Gato.

## Filosofía

- **Libertad para interpretar y proponer. Confirmación para delegar o
  comprometer a la empresa.**
- Un dato que el responsable debe averiguar **no bloquea** la tarea.
- Solo se pregunta lo necesario para entender la instrucción o asignarla.
- Preparar, notificar y ejecutar son cosas distintas.
- La falta de revisión (lector C caído) **no autoriza** envíos ni operaciones.

## Los tres responsables reales

| Rol | Qué hace |
|---|---|
| **JULIO** | decide, autoriza dinero, compromete a la empresa |
| **SECRETARIA** | clientes, documentos, comunicaciones, pagos por verificar, seguimientos |
| **JEFE_PLANTA** | producción, operarios, equipos, materiales, camiones, despachos |

No hay usuarios para operarios. «Que los chicos estén temprano» se propone al
jefe de planta, no a cada operario. Si no se puede determinar el responsable, se
pregunta en el borrador.

## Arquitectura

```
dictado
  ├─ Lector A (hechos)      ─┐
  ├─ Lector B (trabajo)     ─┼─► conciliador ─► borrador conversacional
  └─ Lector C (malentendidos)┘        │
                                      ├─ restricciones por referente y alcance
                                      ├─ fusión de «avísame» como resultado
                                      └─ preguntas solo si hacen falta

confirmación ─► plan (CREAR_TAREA / PREPARAR / PREPARAR_Y_ENVIAR / operación condicionada)
                 └─ verificación de correspondencia exacta
```

## Uso

```powershell
# desde orminorth/
python -m experiments.router_horminor.tests_core
python -m experiments.router_horminor.cli "Que secretaría revise el pago de La Pradera"
python -m experiments.router_horminor.cli "..." --corregir "No era para secretaría, era para el jefe de planta" --confirmar
python -m experiments.router_horminor.evidencia_escenarios
python -m experiments.router_horminor.lab     # http://localhost:8055
python -m experiments.router_horminor.congelar
```

## Reglas de corrección

- «No era para secretaría, era para el jefe de planta» cambia **solo** el
  encargo identificado (por ordinal, por título o por ser el único).
- Si hay varios y no se identifica, **pregunta**; no adivina.
- Cada corrección crea una versión nueva y conserva la anterior.

## Plan de confirmación

- Una tarea por encargo confirmado; ninguna adicional.
- «Avisar cuando termine» se integra como resultado esperado, no como segunda
  tarea.
- Comunicación externa: **PREPARAR** salvo autorización explícita.
- Operación condicionada (despacho, dinero) no se ejecuta con esta confirmación.
- `verificar_correspondencia` comprueba que no se agregue ni omita nada.

## Límites de esta etapa

- Sin persistencia: el borrador vive en memoria y en archivos de evidencia.
- Sin integración con `/panel/cerebro` todavía (etapa 3).
- Sin audio en este laboratorio: se escribe el dictado.
- La calidad depende del modelo; no hay corpus humano de correcciones aún.
