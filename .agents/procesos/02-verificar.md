# Proceso 02 — Verificar y dejar evidencia

"Funciona" no es una verificación. Esto sí:

## Batería mínima después de cualquier cambio

```powershell
# 1. El stack está arriba
docker ps --filter name=orminorth --format "{{.Names}}  {{.Status}}"

# 2. Tests unitarios e integración
docker compose run --rm --no-deps core-api python -m pytest /app/tests -q -o asyncio_mode=auto

# 3. Candado del hito correspondiente
docker compose run --rm --no-deps core-api python scripts/hito1_lock_test.py

# 4. Salud de la API
Invoke-RestMethod http://localhost:8000/health
```

Resultado esperado: `33 passed` (o más), todas las verificaciones del candado
en `[OK]`, y `{"status":"ok"}`.

## Criterios de aceptación por hito

### Hito 1 — Módulo 0

- [ ] 12 tablas y 3 vistas creadas.
- [ ] Pedido del Ing. Reyes: 320 m³ FC-210 → 40 viajes; 52 m³ FC-350 → 7 viajes.
- [ ] La suma de volúmenes por viaje coincide con el volumen pedido.
- [ ] `v_dispatch_timeline` devuelve los viajes sin error.
- [ ] `v_inventario` devuelve los 5 materiales.
- [ ] Kardex teórico se genera **solo** cuando la receta está confirmada.
- [ ] Recetas reales cargadas (esto depende de Julio).

### Hito 2 — Módulos 2 y 5

- [ ] Calculadora determinística cubierta por tests.
- [ ] `daily-audit` responde con `X-Agency-Master-Key`.
- [ ] Sin header → `401`. Clave insegura → `503`.
- [ ] Cada chequeo degrada a `NO_CONFIGURADO`, nunca tumba la respuesta.
- [ ] Latencia caliente < 200 ms (el PDR lo exige).

## Cómo se guarda la evidencia

1. Si la salida es corta: se copia el resumen real en la entrada de bitácora.
2. Si es larga: se guarda completa en `.agents/evidencias/AAAA-MM-DD_nombre.txt`
   y en la bitácora se cita la ruta + 3 líneas de resumen.
3. Nunca se escribe el resultado "esperado" como si fuera real.
4. Si algo falla: se registra el fallo, el comando y la causa. Un fallo
   documentado es información; un fallo escondido es una bomba.

## Pruebas manuales que no se automatizan (aún)

- Crear orden desde el panel de secretaría (Hito 4).
- Simulación de 3 celulares por WhatsApp (Hito 3).
- Generación del PDF bancario (Hito 5).

Para estas, el guion exacto se documenta en la bitácora y la evidencia es la
captura o el archivo resultante.
