# Estabilidad de WhatsApp — por qué se cae y cómo evitarlo

> **Dueño del tema:** este archivo.
> **Fecha:** 2026-11-18.
> **Síntoma:** la instancia figura `open`, los mensajes salientes funcionan,
> pero **deja de recibir** entrantes sin error visible. "Sincronizar" no trae
> nada porque el mensaje nunca llegó a Evolution.

## 1. Diagnóstico

| Hecho | Evidencia |
|---|---|
| La instancia está `open` | `connectionState/horminor` |
| No hay errores en el log | `SessionError`, `Bad MAC`, `device_removed`: 0 |
| El último entrante quedó a una hora fija | 18-N 17:25; después, nada |
| Los salientes siguen funcionando | el bot responde |
| Revincular con QR lo arregla | 2 veces en 2 días |

**Conclusión:** no es el CRM ni el espejo. Es la sesión de WhatsApp (Baileys /
Evolution v2.3.7) que queda **zombie**: abierta para enviar, sorda para recibir.
Los mensajes del hueco **no se pueden recuperar** con Sincronizar.

## 2. Lo que NO sirve

- Pulsar "Sincronizar": no hay nada guardado que traer.
- Reiniciar la instancia: a veces vuelve, a veces no.
- Revincular con QR cada vez: arregla hoy, no evita mañana.

## 3. Prevención por capas

### Capa 1 — Detectarlo antes que el cliente (obligatorio)

Un **vigilante** cada 5 minutos:

1. Lee el último mensaje **entrante** de la instancia.
2. Compara con el último **saliente** y con la hora actual.
3. Si hay salientes recientes pero **cero entrantes** en N minutos de horario
   de atención, marca `SOSPECHOSO`.
4. Si sigue así 15 minutos más, **reinicia la instancia** una vez.
5. Si tras el reinicio sigue igual, **avisa por un canal externo** (correo o
   Telegram) con el enlace para revincular.

**Regla:** la alerta no puede viajar por el mismo WhatsApp que está caído.

### Capa 2 — Aislar el riesgo (recomendado)

Hoy el contenedor de Evolution es **compartido** con otros negocios. Actualizar
la versión afecta a todos, y por eso no se hace.

- Levantar un **contenedor Evolution propio para Horminor**, con su versión
  fijada y actualizable sin tocar a los demás.
- Migrar la instancia `horminor` a ese contenedor (mismo número, nuevo QR).
- Dejar el contenedor compartido como estaba.

### Capa 3 — Versión estable (recomendado)

- Probar en el contenedor propio una versión más nueva de Evolution (o la
  última estable) y comparar durante una semana.
- Si el problema desaparece, se queda; si no, se documenta y se vuelve atrás.

### Capa 4 — Largo plazo (decisión de negocio)

- **WhatsApp Cloud API oficial**: sin QR, sin Baileys, con SLA. Requiere cuenta
  de negocio, verificación y costo por conversación.
- Es la única solución que elimina la causa, no el síntoma.

## 4. Qué hacer cuando vuelva a pasar

1. Revisar `minutos_sin_entrantes` (vigilante o consulta manual).
2. Reiniciar la instancia una vez.
3. Si no vuelve, revincular con QR.
4. **No** prometer al cliente que el mensaje "está en el sistema": no llegó.
5. Registrar la hora del corte en la bitácora.

## 5. Métricas a vigilar

| Métrica | Umbral sugerido |
|---|---|
| `minutos_sin_entrantes` en horario de atención | > 60 → sospechoso |
| Reinicios de la instancia por semana | > 2 → revisar versión |
| Revinculaciones por semana | > 1 → aislamiento/versión |
| Mensajes entrantes por día | caída a 0 → alerta |

## 6. Decisión pendiente

- ¿Canal de alerta: correo, Telegram u otro?
- ¿Ventana de horario para considerar "silencio anormal"?
- ¿Se aprueba el contenedor Evolution propio para Horminor?

## 7. Implementado (2026-11-18)

- Script: `scripts/vigilante_whatsapp.py` en el host.
- Cron cada 5 minutos con `flock`:
  `*/5 * * * * ... /opt/horminor/scripts/vigilante_whatsapp.py`.
- Estado: `/opt/horminor/vigilante_status.json`.
- Bitacora del vigilante: `/var/log/vigilante_horminor.log`.
- Reglas:
  - Instancia `open` y sin entrantes por 90 min en horario (L-S 07:00-19:00):
    reinicia una vez con enfriamiento de 45 min.
  - Instancia `close`: avisa que hace falta QR y **no** reinicia.
  - Avisos repetidos: no se repiten antes de 30 min.
- Alerta externa: se envia a `VIGILANTE_WEBHOOK` si esta configurado. Sin
  webhook, solo queda en el log y en el JSON.

**Pendiente de decision:** Telegram o correo para el webhook.
