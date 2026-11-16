# Procedimiento de revisión ciega — referencia humana

> **Qué es.** Cómo convertir cada dictado en una referencia de calidad sin que
> el sistema influya en la respuesta.

## Reglas

1. **Ciego al sistema.** Quien revisa no ve salidas de V7, D ni D+ antes de
   cerrar su ficha. Tampoco ve la guía preliminar de IA.
2. **Dos revisores independientes.** Cada caso lo completan dos personas por
   separado. Si no hay dos, se registra la limitación y el resultado es
   **exploratorio**, no concluyente.
3. **Adjudicación.** Las diferencias se resuelven en una reunión con Julio; se
   anota el criterio en `adjudicacion`.
4. **Cita obligatoria.** Toda orden y toda restricción debe citar un fragmento
   literal del dictado. Sin cita, no cuenta.
5. **No completar con lo que “parece razonable”.** Si el dictado no lo dice, va
   en `aclaraciones` o queda vacío.
6. **Prioridad.** Los casos marcados `[PRIORIDAD]` (pagos, comunicaciones
   externas, revocaciones, despachos y permisos) se revisan primero y con dos
   personas siempre que sea posible.

## Cómo completar cada ficha

- **Órdenes reales:** solo lo que Julio pide hacer. Una descripción («tenemos
  una obra de 60 m³») no es una orden.
- **Descriptivo:** datos que se mencionan pero no piden nada.
- **Tipo:** COTIZAR, ENVIAR_MENSAJE, DELEGAR, VERIFICAR, REGISTRAR, CONSTANCIA,
  CONSULTAR, LLAMAR o COORDINAR.
- **Responsable:** quién hace el trabajo (SECRETARIA, BODEGA, CONTABILIDAD,
  PLANTA, LOGISTICA, JULIO, u otro que se escriba).
- **Destinatario:** a quién se le comunica algo, si aplica. No es el
  responsable.
- **Ámbito:** INTERNO, EXTERNO o MIXTO.
- **Medio:** WHATSAPP, LLAMADA, CRM, PRESENCIAL o NINGUNO.
- **Ejecutor:** HUMANO o MODULO_CRM. El Cerebro no hace llamadas.
- **Condiciones/prohibiciones:** con su cita; indicar si alcanzan a una orden,
  a un asunto o a todo el dictado.
- **Aclaraciones:** lo que el sistema tendría que preguntar.
- **Prohibidas:** acciones que definitivamente no deben ejecutarse.

## Registro

Cada ficha termina con `revisor_1`, `revisor_2`, `fecha` y `adjudicacion`.
La plantilla para el evaluador es `referencia_revision.jsonl`; una ficha sin
`revisor_1` se considera **no validada** y el evaluador la marca como tal.
