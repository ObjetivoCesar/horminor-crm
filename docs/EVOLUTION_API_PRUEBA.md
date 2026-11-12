# Qué se necesita para probar Evolution API

> Objetivo: pasar el WhatsApp del proyecto de **SANDBOX** a una instancia real
> de Evolution API, sin inventar envíos ni tocar datos de producción.
> Fecha: 2026-11-12. Dueño de las credenciales: Abel / Julio.

---

## 1. Mínimo indispensable (5 datos)

| # | Dato | Para qué | Dónde se carga |
|---|---|---|---|
| 1 | **URL base de Evolution** con HTTPS, por ejemplo `https://evo.tudominio.com` | El backend le pega a `/message/sendText/{instancia}` | Superadmin > WhatsApp/Evolution o `.env`: `EVOLUTION_URL` |
| 2 | **Nombre exacto de la instancia** | Debe existir y estar conectada | `EVOLUTION_INSTANCE` |
| 3 | **API key global o de la instancia** | Cabecera `apikey` en cada llamada | `EVOLUTION_API_KEY` |
| 4 | **Número corporativo de Horminor** en formato internacional (`5939XXXXXXXX`) y nombre visible | Es el que envía; debe estar `open` y con QR escaneado | Configuración de la instancia |
| 5 | **Un teléfono de prueba** con WhatsApp (`5939XXXXXXXX`) | Recibe el mensaje de prueba; no debe ser el número corporativo | Solo para la prueba |

Sin esos cinco, cualquier prueba sería una simulación y no cuenta como
evidencia real.

---

## 2. Para recibir mensajes del cliente (webhook)

Evolution necesita llamar a:

```text
POST https://<dominio-publico>/api/v1/whatsapp/webhook
```

Ese endpoint **no puede ser `localhost:8000`**: Evolution corre en la nube o en
otro servidor y no puede entrar a la máquina local. Opciones:

1. **VPS con dominio y TLS** (lo definitivo).
2. **Túnel temporal** (Cloudflare Tunnel o ngrok) apuntando a
   `http://localhost:8000`, solo para la prueba.

Además, en Evolution deben estar suscritos al menos estos eventos:

- `MESSAGES_UPSERT`
- `CONNECTION_UPDATE`
- `QRCODE_UPDATED`

El endpoint ya responde `202` y normaliza `messages.upsert` /
`MESSAGES_UPSERT`; hoy el pipeline procesa viajes y evidencias, pero **todavía
no persiste el mensaje entrante en el hilo del cliente** (Bloque C de
`.agents/tareas/2026-11-12_ABEL.md`). Para la prueba inicial basta con ver que
el webhook recibe; para cerrar el chat espejo hay que completar ese bloque.

---

## 3. Para enviar multimedia

| Dato | Para qué |
|---|---|
| **Storage Zone, API key, CDN host y token key de Bunny.net** | Guardar fotos, PDFs y videos del chat y de las facturas |
| Un **PDF o foto pequeña** de prueba (< 5 MB) | Verificar la subida y la URL firmada |

Bunny es independiente de Evolution, pero el chat con adjuntos reales necesita
ambos.

---

## 4. Datos de prueba y permisos

1. **Número de prueba** de Julio o Abel, con WhatsApp activo.
2. **Autorización explícita** para enviar mensajes desde el número corporativo
   durante la ventana de prueba.
3. **Nada de clientes reales** en la primera prueba: usar un contacto de
   prueba y mensajes marcados como `PRUEBA`.
4. Confirmar si la instancia es **Evolution Cloud o autohospedada** y su
   **versión** (v2.x), porque los endpoints cambian entre versiones.
5. Acceso al **Superadmin** para guardar la configuración en caliente y apagar
   `sandbox` en `integraciones.evolution`.

---

## 5. Regla de secretos

- La API key **no** se pega en el chat, en la bitácora, en un commit ni en
  documentación.
- Se carga en `.env` (ignorado por git) o desde **Superadmin** en
  `system_settings`.
- Si se comparte por chat para destrabar la prueba, **rotarla después**.

---

## 6. Checklist de aceptación de la prueba

| # | Verificación | Resultado esperado |
|---|---|---|
| 1 | `curl.exe http://localhost:8000/api/v1/whatsapp/health` | `notifier: evolution`, `modo` real |
| 2 | Enviar texto desde el chat del panel a un teléfono de prueba | Llega al WhatsApp y el mensaje queda `ENVIADO` |
| 3 | Responder desde el teléfono de prueba | El webhook recibe `202`; el mensaje aparece en el hilo (requiere Bloque C) |
| 4 | Subir una foto/PDF desde el clip del chat | Se guarda en Bunny bajo `clientes/<nombre>_<cedula>/` y se ve en el hilo |
| 5 | Abrir la URL del CDN sin token | `403`; con token firmado, `200` |
| 6 | `python scripts/media_v69_check.py` | `MEDIA V6.9: OK` |
| 7 | `pytest /app/tests -q` | En verde |
| 8 | Bitácora | Entrada con la evidencia real |

---

## 7. Qué ya está listo y qué falta

| Pieza | Estado |
|---|---|
| Envío de **texto** por Evolution | Implementado (`EvolutionNotifier`) |
| Webhook que recibe y normaliza eventos | Implementado (`POST /api/v1/whatsapp/webhook`) |
| Persistencia del entrante en `chat_mensajes` | **Pendiente** (Bloque C) |
| Envío de **multimedia** saliente | **Pendiente** (Bloque D) |
| Carga de credenciales sin reiniciar | Implementado (Superadmin) |
| Bunny real con token | Listo, faltan credenciales |

---

## 8. Formato en que conviene recibir los datos

Para no filtrar secretos en el chat, entregar así:

```text
EVOLUTION_URL=https://...
EVOLUTION_INSTANCE=...
EVOLUTION_API_KEY=...        (rotar después de la prueba)
TELEFONO_CORPORATIVO=5939...
TELEFONO_PRUEBA=5939...
WEBHOOK_PUBLICO=https://.../api/v1/whatsapp/webhook
```

Si no hay dominio público todavía, decirlo: en ese caso la prueba se limita a
**envío de texto** y el webhook se prueba con `POST /api/v1/whatsapp/simulate`
(requiere clave maestra), no con un mensaje real.
