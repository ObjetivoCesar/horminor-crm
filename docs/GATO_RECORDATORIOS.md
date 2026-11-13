# Gato recordatorios (puntero)

El documento completo del sistema vive en **`docs/GATO_SECRETARIA.md`**:
arquitectura, flujo end-to-end, modelo de datos, estados, interpretación del
lenguaje, permisos, despachador, normalización de teléfonos, API, pruebas,
operación, pendientes priorizados y el paquete de trabajo para Carbon.

Resumen de una línea: Gato crea una tarea en `gato_recordatorios` y un
despachador interno la envía por WhatsApp a la hora indicada.
