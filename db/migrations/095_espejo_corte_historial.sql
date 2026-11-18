-- 095_espejo_corte_historial.sql
--
-- Regla pedida por Julio (2026-11-17): la sincronizacion no debe copiar todo
-- el historial de WhatsApp. Solo cuenta lo que paso desde que el contacto es
-- cliente o lead.
--
-- `desde` es el corte por numero autorizado: la sincronizacion ignora los
-- mensajes anteriores. NULL significa "sin corte" (se respeta lo ya cargado).

ALTER TABLE whatsapp_espejo_numeros
    ADD COLUMN IF NOT EXISTS desde timestamptz;

COMMENT ON COLUMN whatsapp_espejo_numeros.desde IS
    'Corte de historial: no se importan mensajes anteriores a esta fecha. '
    'Por defecto, el alta del cliente en el CRM.';
