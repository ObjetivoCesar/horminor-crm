-- =====================================================================
-- ORMINORTH - Migracion 081: respuesta del cliente a una cotizacion
-- Motivo: el cliente confirma/negocia/rechaza por WhatsApp. Necesitamos
--         un evento auditable y saber cual fue la ultima respuesta.
-- Regla: el mensaje literal se guarda; la IA no decide precios ni estados
--        ambiguos. Solo una confirmacion explicita acepta la cotizacion.
-- =====================================================================

ALTER TABLE cotizaciones
    ADD COLUMN IF NOT EXISTS ultima_respuesta_at timestamptz;

ALTER TABLE cotizaciones
    ADD COLUMN IF NOT EXISTS ultima_respuesta_tipo text;

CREATE TABLE IF NOT EXISTS cotizacion_eventos (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cotizacion_id  uuid NOT NULL REFERENCES cotizaciones(id) ON DELETE CASCADE,
    tipo           text NOT NULL
                   CHECK (tipo IN ('ENVIO', 'CONFIRMACION', 'NEGOCIACION', 'RECHAZO', 'PREGUNTA', 'NOTA')),
    canal          text NOT NULL DEFAULT 'WHATSAPP'
                   CHECK (canal IN ('WHATSAPP', 'PANEL', 'IMPRESA', 'OBRA')),
    mensaje        text,
    whatsapp_msg_id text,
    actor          text,
    payload        jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_cotizacion_eventos_cot
    ON cotizacion_eventos (cotizacion_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_cotizaciones_respuesta
    ON cotizaciones (ultima_respuesta_at DESC)
    WHERE ultima_respuesta_at IS NOT NULL;

COMMENT ON TABLE cotizacion_eventos IS
    'Auditoria de envios y respuestas del cliente. El mensaje literal no se reescribe.';
