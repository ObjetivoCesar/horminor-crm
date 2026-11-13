-- =====================================================================
-- HORMINOR - Migracion 077: adjuntos en recordatorios
-- Motivo: "pasale la factura" no puede quedar como texto: el mensaje debe
--         llevar el PDF adjunto. El recordatorio apunta al archivo en
--         media_assets y el despachador lo envia como documento.
-- =====================================================================

ALTER TABLE gato_recordatorios
    ADD COLUMN IF NOT EXISTS media_id uuid REFERENCES media_assets(id) ON DELETE SET NULL;

COMMENT ON COLUMN gato_recordatorios.media_id IS
    'Archivo adjunto (factura interna, PDF o foto). Si es NULL, el recordatorio es solo texto.';

CREATE INDEX IF NOT EXISTS ix_gato_recordatorios_media
    ON gato_recordatorios (media_id)
    WHERE media_id IS NOT NULL;
