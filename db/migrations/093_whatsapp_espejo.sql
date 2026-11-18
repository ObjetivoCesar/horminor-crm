-- =====================================================================
-- ORMINORTH - Migracion 093: lista blanca del espejo de WhatsApp
-- Motivo: la instancia Evolution `horminor` esta conectada a un numero
--         personal con 41.748 mensajes y 1.286 contactos. El espejo del
--         CRM solo puede persistir conversaciones de los telefonos
--         expresamente autorizados; el resto no se importa ni se guarda.
--
-- Nada de negocio se inventa aqui: las tablas nacen vacias. El numero de
-- prueba se registra despues desde la API (activar/desactivar), nunca
-- desde una semilla.
-- =====================================================================

-- Lista blanca provisional. `telefono_e164` usa los digitos con codigo de
-- pais tal como los arma formato_whatsapp (Ecuador: 593 + 9 digitos).
CREATE TABLE IF NOT EXISTS whatsapp_espejo_numeros (
    telefono_e164          text PRIMARY KEY,
    cliente_id             uuid REFERENCES clients(id) ON DELETE SET NULL,
    etiqueta               text,
    activo                 boolean NOT NULL DEFAULT true,
    ultima_sincronizacion_at timestamptz,
    ultimo_mensaje_at      timestamptz,
    mensajes_importados    integer NOT NULL DEFAULT 0,
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    CHECK (telefono_e164 ~ '^[0-9]{8,15}$')
);

COMMENT ON TABLE whatsapp_espejo_numeros IS
    'Lista blanca del espejo de WhatsApp. Solo estos telefonos se importan.';

CREATE INDEX IF NOT EXISTS ix_espejo_numeros_cliente
    ON whatsapp_espejo_numeros (cliente_id)
    WHERE activo;

-- Un numero de WhatsApp puede llegar con tres formas: el JID de telefono
-- (@s.whatsapp.net), el LID opaco (@lid) o el remoteJidAlt del evento.
-- Aqui se fija a que telefono autorizado pertenece cada forma.
CREATE TABLE IF NOT EXISTS whatsapp_espejo_jids (
    jid            text PRIMARY KEY,
    telefono_e164  text NOT NULL
                   REFERENCES whatsapp_espejo_numeros(telefono_e164)
                   ON DELETE CASCADE,
    origen         text NOT NULL DEFAULT 'PN'
                   CHECK (origen IN ('PN', 'LID', 'ALT')),
    created_at     timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE whatsapp_espejo_jids IS
    'Alias JID -> telefono autorizado. Resuelve @lid y remoteJidAlt.';

CREATE INDEX IF NOT EXISTS ix_espejo_jids_telefono
    ON whatsapp_espejo_jids (telefono_e164);

-- Identidades ambiguas: un @lid sin remoteJidAlt ni alias conocido. No se
-- vincula ni se importa el mensaje. Se guardan solo identificadores, nunca
-- el contenido, para poder resolverlo despues sin exponer datos ajenos.
CREATE TABLE IF NOT EXISTS whatsapp_espejo_pendientes (
    id               bigserial PRIMARY KEY,
    jid              text NOT NULL,
    remote_jid_alt   text,
    mensaje_id       text,
    motivo           text NOT NULL,
    from_me          boolean NOT NULL DEFAULT false,
    mensaje_tipo     text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    revisado_at      timestamptz,
    UNIQUE (jid, mensaje_id)
);

COMMENT ON TABLE whatsapp_espejo_pendientes IS
    'JIDs ambiguos sin contenido: se resuelven antes de vincular o importar.';

CREATE INDEX IF NOT EXISTS ix_espejo_pendientes_revision
    ON whatsapp_espejo_pendientes (created_at DESC)
    WHERE revisado_at IS NULL;

-- Marca de agua de la ultima sincronizacion por telefono autorizado.
-- Sirve para auditoria y para no reescanear todo en cada clic.
CREATE TABLE IF NOT EXISTS whatsapp_espejo_cursor (
    telefono_e164  text PRIMARY KEY
                   REFERENCES whatsapp_espejo_numeros(telefono_e164)
                   ON DELETE CASCADE,
    ultimo_msg_id  text,
    ultimo_msg_at  timestamptz,
    paginas_leidas integer NOT NULL DEFAULT 0,
    updated_at     timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE whatsapp_espejo_cursor IS
    'Progreso del backfill por numero. La idempotencia real la da whatsapp_msg_id.';
