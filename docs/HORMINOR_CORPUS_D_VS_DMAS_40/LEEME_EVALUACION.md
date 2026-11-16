# Evaluación independiente del Cerebro Horminor (D vs. D+)

Contiene **40 dictados sintéticos inéditos respecto de los siete P1–P7**, creados como candidatos a corpus de evaluación. No son audios reales de Julio.

## Archivos
- `corpus_nuevo_40.jsonl`: entradas solamente.
- `guia_referencia_preliminar_NO_HUMANA.jsonl`: interpretación **preliminar generada por IA**; NO constituye doble anotación humana ni un patrón oro definitivo.

## Procedimiento para evitar contaminación
1. Definir y congelar prompts, esquemas y código de D y D+ (checksums/commits); solo compartir el **formato**, no el contenido de estos casos, antes del congelamiento.
2. Dos revisores humanos autorizados revisan cada caso por separado **antes de conocer las respuestas de los motores**. Pueden usar la guía como apoyo solo después de sus anotaciones independientes.
3. Resolver discrepancias en una referencia adjudicada. No tratar la etiqueta IA como autoridad.
4. Ejecutar todos los brazos sobre las mismas entradas y versión de modelo. Mantener bloqueados los prompts durante esa ronda.
5. Reportar resultados también por categoría y por tipo de riesgo.
6. No usar este corpus para reescribir los prompts y luego seguir anunciándolo como prueba independiente; si se entrena con él, pasa a regresión y necesita otro conjunto oculto.

**Advertencia:** ninguno de estos textos prueba por sí mismo que el motor funcione en voz humana, con ruido de planta, acentos locales, múltiples audios o hilos de WhatsApp.

## Ajustes recomendados al plan D+
- El alcance de restricciones no puede resolverse solo por solapamiento textual: requiere referencias entre órdenes.
- Separar canal de ejecución, actor encargado y alcance interno/externo.
- Usar identificador de mensaje/request para idempotencia; texto idéntico puede ser una orden nueva.
- Medir tiempos por fase y extremo a extremo, incluyendo STT.
- Un resultado 0/40 para acciones inventadas es señal preliminar, no prueba de riesgo cero.
