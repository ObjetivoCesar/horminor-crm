# Rol 03 — Publicador

- **Nivel funcional:** operativo
- **Mecanismo preferido:** Capa 0 (render + storage)
- **Misión:** renderizar la plantilla, archivar el PDF en la carpeta del cliente y dejarlo disponible con una URL estable.

## Reglas inviolables

1. La plantilla sale del enum: `cotizacion_v1`.
2. El branding viene de `empresa.bot_publico`; si falta un dato, se omite la línea.
3. El PDF preliminar lleva la marca `PRELIMINAR` visible.
4. Si el precio es `PROVISIONAL`, el PDF lleva la marca visible `PRECIO PROVISIONAL`.
5. Si Bunny falla, se guarda en el volumen local y `pdf_url` queda `null` con ruta interna.
6. El archivo se nombra con el folio: `COT-2026-000123.pdf`.
7. El PDF se registra en `media_assets`: es la carpeta del cliente, no una carpeta paralela.

## Entradas

- `cotizacion_emitida` del rol 02.
- Contenido calculado del rol 01.

## Salidas

```json
{
  "folio": "COT-2026-000123",
  "pdf_url": "https://horminor.b-cdn.net/cotizaciones/COT-2026-000123.pdf",
  "pdf_local": null,
  "bytes": 48213,
  "media_id": "9f1c…",
  "storage_path": "clientes/Constructora_Andina_1790012345001/COT-2026-000123.pdf"
}
```

## Archivo en la carpeta del cliente

1. Se inserta en `media_assets` con `cliente_id`, `tipo = 'DOCUMENTO'`,
   `storage_path` bajo la carpeta del cliente y `etiquetas = ["COTIZACION"]`.
2. `sha256` se calcula sobre el PDF final; sin hash no hay registro.
3. El archivo aparece en la carpeta forense de Secretaría junto a fotos y
   comprobantes.
4. Si el cliente no tiene cédula, la carpeta usa el nombre y queda marcada como
   provisional; no se inventa un documento.

## Envío por WhatsApp

1. El publicador entrega el PDF y el texto al canal; el canal envía.
2. Se guardan `enviada_at`, `enviada_por`, `canal_envio` y `whatsapp_msg_id`.
3. Si el envío falla, la cotización queda `ENVIADA` con `canal_envio = PANEL` y
   el PDF archivado. El registro no se pierde aunque el mensaje no salga.
4. El publicador **no** redacta el mensaje comercial: lo recibe del emisor.

## Rechazos automáticos

- `PLANTILLA_DESCONOCIDA` si no está en el enum.
- `RENDER_FALLIDO` si el motor PDF lanza.
- `STORAGE_NO_CONFIGURADO` no es rechazo: se degrada a local y se avisa.
- `ARCHIVO_SIN_HASH` si no se puede calcular el `sha256`.

## Nota de motor

Recomendado: WeasyPrint. El contrato no cambia si mañana se usa Chromium
headless; solo cambia este rol.
