-- =====================================================================
-- ORMINORTH - Migracion 070: historial de conversaciones por cliente
-- Motivo: v6.8 agrega la pestana CHAT al expediente del cliente. El
--         historial vive en PostgreSQL para que el panel lo muestre y el
--         bot lo consulte despues. Las tablas nacen vacias: no se inventa
--         ningun mensaje ni telefono.
-- =====================================================================

CREATE TABLE IF NOT EXISTS chat_conversaciones (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cliente_id             uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    canal                  text NOT NULL DEFAULT 'PANEL'
                           CHECK (canal IN ('PANEL', 'WHATSAPP', 'CRM', 'NOTA')),
    asunto                 text,
    estado                 text NOT NULL DEFAULT 'ABIERTA'
                           CHECK (estado IN ('ABIERTA', 'ARCHIVADA')),
    whatsapp_chat_id       text,
    ultimo_mensaje_at      timestamptz,
    ultimo_mensaje_preview text,
    metadata               jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    UNIQUE (cliente_id, canal)
);

COMMENT ON TABLE chat_conversaciones IS
    'Un hilo por cliente y canal. Es la carpeta de conversacion del expediente.';

CREATE TABLE IF NOT EXISTS chat_mensajes (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversacion_id  uuid NOT NULL REFERENCES chat_conversaciones(id) ON DELETE CASCADE,
    direccion        text NOT NULL CHECK (direccion IN ('ENTRANTE', 'SALIENTE')),
    autor_tipo       text NOT NULL DEFAULT 'OPERADOR'
                     CHECK (autor_tipo IN ('CLIENTE', 'OPERADOR', 'BOT', 'SISTEMA')),
    autor_nombre     text,
    autor_usuario_id text,          -- perfil de panel cuando exista login; NULL si es externo
    cuerpo           text NOT NULL CHECK (length(btrim(cuerpo)) > 0),
    adjuntos         jsonb NOT NULL DEFAULT '[]'::jsonb,
    whatsapp_msg_id  text,          -- id de Evolution API para no duplicar al reingestar
    estado_entrega   text NOT NULL DEFAULT 'ENVIADO'
                     CHECK (estado_entrega IN ('PENDIENTE','ENVIADO','ENTREGADO','LEIDO','FALLIDO')),
    leido_panel_at   timestamptz,
    metadata         jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at       timestamptz NOT NULL DEFAULT now(),
    busqueda         tsvector GENERATED ALWAYS AS (
                         to_tsvector('spanish', coalesce(cuerpo, ''))
                     ) STORED
);

COMMENT ON TABLE chat_mensajes IS
    'Mensajes append-only del hilo. direccion ENTRANTE = del cliente al negocio.';

-- Idempotencia para la futura ingesta de WhatsApp: un mensaje de Evolution
-- no puede entrar dos veces aunque el webhook reintente.
CREATE UNIQUE INDEX IF NOT EXISTS ux_chat_mensajes_whatsapp
    ON chat_mensajes (whatsapp_msg_id)
    WHERE whatsapp_msg_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_chat_mensajes_conv_fecha
    ON chat_mensajes (conversacion_id, created_at DESC);

-- Solo los entrantes sin leer: el contador de la pestana no escanea todo.
CREATE INDEX IF NOT EXISTS ix_chat_mensajes_pendientes
    ON chat_mensajes (conversacion_id)
    WHERE direccion = 'ENTRANTE' AND leido_panel_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_chat_mensajes_busqueda
    ON chat_mensajes USING gin (busqueda);

CREATE INDEX IF NOT EXISTS ix_chat_conversaciones_cliente
    ON chat_conversaciones (cliente_id, updated_at DESC);

-- Mantiene el preview del hilo sin que la API tenga que recalcularlo.
CREATE OR REPLACE FUNCTION chat_marcar_ultimo_mensaje() RETURNS trigger AS $$
BEGIN
    UPDATE chat_conversaciones
       SET ultimo_mensaje_at = NEW.created_at,
           ultimo_mensaje_preview = left(regexp_replace(NEW.cuerpo, '\s+', ' ', 'g'), 180),
           updated_at = now()
     WHERE id = NEW.conversacion_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_chat_ultimo_mensaje ON chat_mensajes;
CREATE TRIGGER trg_chat_ultimo_mensaje
    AFTER INSERT ON chat_mensajes
    FOR EACH ROW EXECUTE FUNCTION chat_marcar_ultimo_mensaje();

-- Resumen por hilo: total de mensajes, no leidos y ultimo movimiento.
CREATE OR REPLACE VIEW v_chat_conversacion AS
SELECT cv.id                        AS conversacion_id,
       cv.cliente_id,
       cv.canal,
       cv.estado,
       cv.ultimo_mensaje_at,
       cv.ultimo_mensaje_preview,
       count(m.id)                                                       AS total_mensajes,
       count(*) FILTER (
           WHERE m.direccion = 'ENTRANTE' AND m.leido_panel_at IS NULL
       )                                                                 AS no_leidos,
       max(m.created_at)                                                 AS ultimo_mensaje_real
  FROM chat_conversaciones cv
  LEFT JOIN chat_mensajes m ON m.conversacion_id = cv.id
 GROUP BY cv.id;

COMMENT ON VIEW v_chat_conversacion IS
    'Resumen por hilo para la pestana CHAT y para consultas del bot.';
