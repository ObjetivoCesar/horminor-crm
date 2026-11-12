# WhatsApp, chat espejo y multimedia del cliente

> Decisión vigente: **2026-11-11**.
> Regla: WhatsApp es el canal; el panel es el espejo y el índice. Ningún
> archivo binario se guarda en PostgreSQL y nada se inventa.

---

## 1. La decisión de fondo

El PDR es explícito: la operación de campo y la conversación con el cliente
ocurren en **WhatsApp (Evolution API)**; Secretaría y Gerencia usan el panel.
Por eso la pestaña `💬 Chat` del expediente **no crea un canal nuevo**: muestra
el mismo hilo de WhatsApp y, cuando Evolution esté conectado, responde por ahí.

| Pieza | Rol |
|---|---|
| WhatsApp (Evolution) | Canal oficial con el cliente y el chofer |
| PostgreSQL | Historial e índice: quién, cuándo, qué dijo y qué archivo |
| Bunny.net | Almacén de fotos, videos, audios y documentos |
| Panel | Espejo de la conversación + consola de Secretaría |

Mientras Evolution no tenga credenciales, el panel funciona en **modo
espejo sin conexión**: los mensajes salientes quedan `PENDIENTE` y se avisa en
pantalla. No se finge un envío.

---

## 2. Carpetas en Bunny.net

### 2.1 Convención

La carpeta raíz es `clientes/` y cada cliente tiene **una carpeta estable**:

```text
clientes/<nombre_cliente>_<cedula>/
    2026-11-11_imagen_9f3a1c2b.webp
    2026-11-11_video_44d0ab71.mp4
    2026-11-11_audio_1c9e77aa.webm
    2026-11-11_documento_77b2e901.pdf
```

- **Nombre + cédula** evita homónimos, como pediste.
- Si la cédula no está cargada, se usa el **RUC**; si tampoco existe, el
  **id del cliente**. Nunca se inventa un documento.
- El nombre se normaliza a minúsculas y sin tildes (`ing_reyes_velez_1712345678`).
- **No hay subcarpetas por obra o viaje**: eso serían etiquetas, y las etiquetas
  van en la base. Una carpeta que cambia de nombre cuando corriges la razón
  social rompe enlaces; el id no cambia.

### 2.2 ¿Carpeta por cliente u por obra?

Tu decisión fue **cliente**. La obra, la orden y el viaje se guardan como
etiquetas en `media_assets.etiquetas`:

```json
["obra:loreto", "orden:56", "viaje:3", "etapa:vaciado"]
```

Así una foto puede pertenecer al chat, a la obra y al viaje sin duplicar el
archivo ni moverlo de carpeta. Si más adelante quieres ver “solo fotos de la
obra de Loreto”, se filtra por etiqueta, no se navega otra carpeta.

### 2.3 Evidencia forense del viaje

La evidencia del chofer (Gate #3) conserva su ruta histórica
`ordenes/<orden>/viaje_<n>_<mensaje>.<ext>` porque es un contrato de auditoría
del PDR. Esa foto puede además registrarse en `media_assets` con etiquetas
`orden` y `viaje`, para que aparezca en la galería del cliente sin copiarla.

---

## 3. Token authentication de Bunny (explicado simple)

Hoy el CDN de Bunny es público: quien tenga la URL puede abrir la foto. Como
son fotos de obras y conversaciones de clientes, eso no es aceptable en
producción.

**Token authentication** es una firma en la URL:

```text
https://cdn.horminor.com/clientes/reyes_1712345678/2026-11-11_imagen_9f3a.webp
  ?token=Q2FsaWRhZE11eUJ1ZW5h...&expires=1794449000
```

- El backend firma con una clave secreta (`BUNNY_TOKEN_KEY`) y una expiración.
- Bunny valida la firma; si alguien cambia la ruta o la fecha, el enlace deja
  de servir.
- La clave **no** viaja al navegador; solo viaja el token calculado.
- Se activa en el Pull Zone de Bunny: *Security → Token Authentication*.
- Si `BUNNY_TOKEN_KEY` está vacía, la API devuelve la URL pública. Eso sirve
  para local, no para producción.

Implementado en `app/services/media.py::firmar_url_bunny()` y usado al leer
cada mensaje (`/api/v1/clients/{id}/chat`). La URL firmada **no se guarda** en
la base: se regenera en cada lectura.

---

## 4. Límites y defensas

| Tipo | Peso máximo | Procesamiento |
|---|---|---|
| Imagen | 25 MB | WebP, lado mayor 1920 px, calidad 82, sin EXIF |
| Video | 250 MB | H.264/AAC, máximo 1280×720, CRF 28, hasta 180 s |
| Audio | 40 MB | Se guarda tal cual (opus/ogg/mp3/m4a/wav) |
| Documento | 25 MB | PDF, Word, Excel, CSV, TXT, PPTX |

**Formatos de imagen aceptados:** JPG, JPEG, PNG, WebP, GIF (se toma el
primer cuadro), BMP, TIFF y HEIC/HEIF de iPhone. Todos se convierten a WebP;
no importa el formato de origen. No se aceptan SVG ni RAW de cámara. Si el
archivo ya es WebP y pesa menos, se respeta el resultado de la compresión.

**Video:** MP4, MOV, M4V, WebM, 3GP, AVI y MKV se re-codifican a MP4.
**Audio:** OGG, OPUS, MP3, M4A, WAV, AAC y AMR pasan sin re-codificar.
**Documentos:** PDF, DOC/DOCX, XLS/XLSX, CSV, TXT y PPT/PPTX.

Defensas ya implementadas:

1. **Lista blanca de extensiones**; `.exe`, `.bat`, `.sh`, `.js`, `.svg`,
   `.html`, `.py` y similares se rechazan antes de leer.
2. **Tope por tipo** antes de procesar; si se pasa, `413`.
3. **Bombas de descompresión**: `Pillow` con `MAX_IMAGE_PIXELS` (50 Mpx).
4. **Path traversal**: la ruta del sandbox se resuelve y debe quedar dentro
   del directorio base.
5. **EXIF eliminado** al convertir a WebP (ubicación, cámara, etc.).
6. **Video re-codificado**: no se conserva el archivo original con metadatos.
7. **Sin binarios en PostgreSQL**: solo el índice.
8. **Límite en memoria**: 30 subidas/hora y 180 mensajes/hora por IP. Frena
   bucles y saturación accidental; en producción conviene Redis o el API
   gateway.

Pendiente de endurecer:

- Antivirus/ClamAV para documentos (hoy solo extensión y tamaño).
- Cuota de almacenamiento por cliente y política de retención.
- Borrado lógico y purga programada en Bunny.
- Miniaturas de video (hoy el navegador genera el poster).

---

## 5. Índice en PostgreSQL

`media_assets` (migración `071_media_clientes.sql`) guarda:

| Campo | Para qué |
|---|---|
| `cliente_id` | Dueño del archivo |
| `conversacion_id`, `mensaje_id` | Hilo y mensaje al que pertenece |
| `dispatch_id` | Viaje, si es evidencia de mixer |
| `tipo` | `IMAGEN`, `VIDEO`, `AUDIO`, `DOCUMENTO` |
| `backend` | `BUNNY` o `SANDBOX` |
| `storage_path` | Ruta canónica dentro del Storage Zone |
| `cdn_url` | URL sin firmar (la firmada se calcula al leer) |
| `mime_final`, `bytes_final`, `ancho`, `alto`, `duracion_seg` | Ficha técnica |
| `sha256` | Integridad y futura deduplicación |
| `etiquetas` | Obra, orden, viaje, etapa |
| `metadata` | Origen, canal, datos extra |

El mensaje del chat guarda en `adjuntos` solo una **referencia**
(`media_id`, tipo, mime, peso); la URL se resuelve al leer. Así una URL firmada
nunca queda vencida dentro de la base.

`clients.cedula` se agregó en la misma migración, `NULL` hasta que Julio la
cargue. La carpeta usa cédula → RUC → id, en ese orden.

---

## 6. Modo SANDBOX (desarrollo)

Si Bunny no está configurado, el archivo comprimido se guarda en el volumen
Docker `orminorth-media` (`/app/media_sandbox`) y se sirve por
`GET /api/v1/media/{id}/archivo`. Es **solo para desarrollo**: el PDR prohíbe
guardar archivos en el VPS de producción. Al cargar las credenciales de Bunny,
los archivos nuevos van al CDN y el sandbox deja de usarse.

---

## 7. Estado de Evolution y qué falta

Hoy: `modo = SANDBOX`, `notifier = sandbox`, sin número corporativo. El panel
marca los mensajes como `PENDIENTE`.

Cuando conectes tu número:

1. Cargar URL, instancia y API key de Evolution (Superadmin o `.env`).
2. Apagar `sandbox` en `integraciones.evolution`.
3. Verificar `/api/v1/whatsapp/health` → `notifier: evolution`.
4. Persistir los mensajes entrantes en `chat_mensajes` desde el webhook
   (hoy el pipeline actualiza el viaje, no el hilo). Es el siguiente paso de
   código.
5. Enviar multimedia saliente por Evolution (hoy solo texto).
6. Respetar la ventana de 24 h: fuera de ella se necesitan plantillas
   aprobadas por Meta.

---

## 8. Fases

| Fase | Qué | Estado |
|---|---|---|
| A | UI espejo WhatsApp, clip, adjuntos, columnas iguales | Implementado |
| B | Compresión, límites, índice `media_assets`, sandbox | Implementado |
| C | Bunny real + token authentication | Listo, falta cargar credenciales |
| D | Persistencia del webhook de Evolution en el hilo | Pendiente |
| E | Envío de texto y multimedia por Evolution | Pendiente (texto listo) |
| F | Cuotas, retención, antivirus y rate limit | Pendiente |
