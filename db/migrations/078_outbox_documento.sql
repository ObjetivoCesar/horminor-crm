-- =====================================================================
-- HORMINOR - Migracion 078: tipo DOCUMENTO en el outbox del sandbox
-- Motivo: los recordatorios con factura adjunta envian un archivo. El
--         outbox solo admitia TEXTO, MEDIA y ALERTA, asi que el envio
--         fallaba con CheckViolationError y el recordatorio reintentaba.
-- =====================================================================

ALTER TABLE sandbox_outbox
    DROP CONSTRAINT IF EXISTS sandbox_outbox_tipo_check;

ALTER TABLE sandbox_outbox
    ADD CONSTRAINT sandbox_outbox_tipo_check
    CHECK (tipo IN ('TEXTO', 'MEDIA', 'ALERTA', 'DOCUMENTO'));
