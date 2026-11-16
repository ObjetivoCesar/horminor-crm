# Paquete de auditoría del Cerebro — índice

> **Qué es.** Material para que un auditor externo (ChatGPT u otra persona)
> compruebe el diagnóstico sin acceso al repositorio completo.
> **Corte:** commit `2a5fd93`, laboratorio v8.6, 620 pruebas.
> **Fecha:** 2026-11-16.
> **Contenido:** solo Cerebro y voz. No incluye el ERP, Gato, credenciales,
> `.env`, tokens ni configuración de servidores.

## Documentos principales

| Documento | Ruta | Para qué |
|---|---|---|
| Diagnóstico arquitectónico | `docs/AUDITORIA_ARQUITECTURA_CEREBRO.md` | flujo real, decisiones LLM vs código, causas y límites |
| Trazabilidad P1–P7 | `docs/TRAZABILIDAD_P1_P7.md` | qué se conservó de cada prueba y dónde nace cada error |
| Alternativas | `docs/ALTERNATIVAS_SOLUCION_CEREBRO.md` | A, B, C y D con riesgos, coste y pruebas |

## Material de apoyo

| Archivo | Contenido |
|---|---|
| `prompt_cerebro_v7.txt` | prompt literal y claves permitidas (`cerebro-v7`) |
| `codigo/extractor.py` | normalización → LLM → hechos → encargos |
| `codigo/compilador.py` | hechos → acciones, condiciones, preguntas |
| `codigo/encargos.py` | segmentación y asignación de encargos |
| `codigo/internas.py` | intención (enviar/delegar), rol, tareas internas |
| `codigo/revision.py` | correcciones versionadas y resumen |
| `codigo/router.py` | endpoints: interpretar, corregir, confirmar, cancelar |
| `codigo/hechos.py` | hecho citado y validación de la cita |
| `codigo/sobre.py` | contrato de la respuesta del LLM |
| `codigo/tiempo.py` | horas, fechas y plazos |
| `codigo/normalizador_ec.py` | normalización es-EC y alineación con STT |
| `codigo/recordatorios.py` | guarda de cifras y creación del recordatorio |
| `esquema_cerebro.sql` | DDL de las 14 tablas del Cerebro y la voz |
| `p1_p7_registros.json` | los 8 borradores completos de P1–P7 |
| `pruebas_inventario.md` | qué cubre y qué no cubre la suite de 620 |

## Contrato relacionado

`docs/CONTRATO_WHATSAPP_CEREBRO.md` describe el contrato de canal (mensajes,
conversaciones, asuntos, confirmaciones) que la fase de WhatsApp deberá cumplir.

## Sanitización

- No hay `.env`, tokens, claves de Groq, de Evolution ni de Bunny.
- Los nombres y teléfonos de P1–P7 son **datos ficticios de prueba**
  (`0965555555` incluido). No son clientes reales.
- El código copiado lee la configuración de variables de entorno; no contiene
  secretos embebidos.

## Cómo verificar el diagnóstico

1. Abrir `p1_p7_registros.json` y localizar cada caso por `caso`.
2. Comparar `sobre` (lo que propuso el modelo) con `acciones` (lo que decidió el
   compilador). El punto de divergencia está descrito en `TRAZABILIDAD_P1_P7.md`.
3. Leer la función citada en `codigo/` y comprobar la regla.
4. Para una reproducción, usar un entorno aislado y marcar el resultado como
   **nuevo**: el registro original ya está aquí y no debe confundirse con una
   ejecución posterior.

## Lo que este paquete no permite

- Ver el cuerpo HTTP crudo del LLM (no se registra).
- Ver las notas del verificador (no se persisten).
- Ver los hechos tal como los procesó el backend (no hay tabla; se derivan del
  sobre con el código del corte).
