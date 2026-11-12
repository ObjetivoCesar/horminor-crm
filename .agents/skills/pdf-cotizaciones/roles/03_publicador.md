# Rol 03 — Publicador

- **Nivel funcional:** operativo
- **Mecanismo preferido:** Capa 0 (render + storage)
- **Misión:** renderizar la plantilla y dejar el PDF disponible con una URL estable.

## Reglas inviolables

1. La plantilla sale del enum: `cotizacion_v1`.
2. El branding viene de `empresa.bot_publico`; si falta un dato, se omite la línea.
3. El PDF preliminar lleva la marca `PRELIMINAR` visible.
4. Si Bunny falla, se guarda en el volumen local y `pdf_url` queda `null` con ruta interna.
5. El archivo se nombra con el folio: `COT-2026-000123.pdf`.

## Entradas

- `cotizacion_emitida` del rol 02.
- Contenido calculado del rol 01.

## Salidas

```json
{
  "folio": "COT-2026-000123",
  "pdf_url": "https://horminor.b-cdn.net/cotizaciones/COT-2026-000123.pdf",
  "pdf_local": null,
  "bytes": 48213
}
```

## Rechazos automáticos

- `PLANTILLA_DESCONOCIDA` si no está en el enum.
- `RENDER_FALLIDO` si el motor PDF lanza.
- `STORAGE_NO_CONFIGURADO` no es rechazo: se degrada a local y se avisa.

## Nota de motor

Recomendado: WeasyPrint. El contrato no cambia si mañana se usa Chromium
headless; solo cambia este rol.
