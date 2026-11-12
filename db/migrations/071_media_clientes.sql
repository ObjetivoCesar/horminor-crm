-- =====================================================================
-- ORMINORTH - Migracion 071: cedula del cliente e indice de multimedia
-- Motivo: v6.9 agrega fotos, videos, audios y documentos a la carpeta del
--         cliente. Los archivos viven en Bunny.net; PostgreSQL guarda el
--         indice y las etiquetas. No se inventa ninguna cedula: nace NULL.
-- =====================================================================

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS cedula TEXT;

COMMENT ON COLUMN clients.cedula IS
    'Cedula del cliente para carpetas y busqueda. NULL = PENDIENTE de cargar.';

-- Evita homonimos en la carpeta de Bunny: nombre + cedula. Si la cedula
-- falta, la API usa RUC o el id del cliente, nunca un valor inventado.
CREATE UNIQUE INDEX IF NOT EXISTS ux_clients_cedula
    ON clients (cedula)
    WHERE cedula IS NOT NULL AND btrim(cedula) <> '';

CREATE TABLE IF NOT EXISTS media_assets (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cliente_id       uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    conversacion_id  uuid REFERENCES chat_conversaciones(id) ON DELETE SET NULL,
    mensaje_id       uuid REFERENCES chat_mensajes(id) ON DELETE SET NULL,
    dispatch_id      uuid REFERENCES mixer_dispatches(id) ON DELETE SET NULL,
    tipo             text NOT NULL
                     CHECK (tipo IN ('IMAGEN', 'VIDEO', 'AUDIO', 'DOCUMENTO')),
    backend          text NOT NULL DEFAULT 'SANDBOX'
                     CHECK (backend IN ('BUNNY', 'SANDBOX')),
    storage_path     text NOT NULL,          -- ruta canonica dentro del Storage Zone
    cdn_url          text,                   -- URL sin firmar; la API firma al leer
    nombre_original  text,
    mime_original    text,
    mime_final       text,
    bytes_original   bigint,
    bytes_final      bigint,
    ancho            integer,
    alto             integer,
    duracion_seg     numeric(10, 2),
    sha256           text NOT NULL,
    etiquetas        jsonb NOT NULL DEFAULT '[]'::jsonb,
    metadata         jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at       timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE media_assets IS
    'Indice de archivos del cliente. El binario vive en Bunny.net (o en el sandbox local), nunca en PostgreSQL.';

CREATE INDEX IF NOT EXISTS ix_media_cliente_fecha
    ON media_assets (cliente_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_media_mensaje
    ON media_assets (mensaje_id)
    WHERE mensaje_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_media_sha256
    ON media_assets (sha256);
