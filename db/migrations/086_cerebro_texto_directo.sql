-- =====================================================================
-- ORMINORTH - Migracion 086: fuente de texto directo para el Cerebro
-- Motivo: el endpoint /cerebro/interpretar acepta texto pegado o dictado
--         ademas de una transcripcion. La 085 exigia transcripcion o
--         mensaje de chat; el texto directo tambien es una fuente legitima
--         y debe quedar registrado.
-- =====================================================================

ALTER TABLE cerebro_extracciones
    ADD COLUMN IF NOT EXISTS texto_directo text NULL;

COMMENT ON COLUMN cerebro_extracciones.texto_directo IS
    'Texto pegado o dictado sin audio asociado. NULL cuando la fuente es una transcripcion o un mensaje.';

ALTER TABLE cerebro_extracciones
    DROP CONSTRAINT IF EXISTS chk_fuente_extraccion;

ALTER TABLE cerebro_extracciones
    ADD CONSTRAINT chk_fuente_extraccion CHECK (
        transcripcion_id IS NOT NULL
        OR chat_mensaje_id IS NOT NULL
        OR texto_directo IS NOT NULL
    );
