-- =====================================================================
-- ORMINORTH - Migracion 094: preview del hilo monotono
-- Motivo: el espejo de WhatsApp importa historial por paginas y no
--         necesariamente en orden cronologico. La funcion 070 escribia
--         siempre `ultimo_mensaje_at`/`ultimo_mensaje_preview` con el
--         ultimo INSERT, de modo que un mensaje viejo del backfill podia
--         pisar el preview mas reciente del hilo.
--
-- Regla nueva: el preview solo avanza. Si el mensaje insertado es mas
-- antiguo que el ultimo registrado, la conversacion no se toca.
-- Idempotente: se puede reaplicar sin perder datos.
-- =====================================================================

CREATE OR REPLACE FUNCTION chat_marcar_ultimo_mensaje() RETURNS trigger AS $$
BEGIN
    UPDATE chat_conversaciones
       SET ultimo_mensaje_at = NEW.created_at,
           ultimo_mensaje_preview = left(regexp_replace(NEW.cuerpo, '\s+', ' ', 'g'), 180),
           updated_at = now()
     WHERE id = NEW.conversacion_id
       AND (
           ultimo_mensaje_at IS NULL
           OR NEW.created_at >= ultimo_mensaje_at
       );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION chat_marcar_ultimo_mensaje() IS
    'Preview del hilo monotono: un mensaje mas antiguo no pisa al mas reciente.';
