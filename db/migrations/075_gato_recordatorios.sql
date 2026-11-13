-- =====================================================================
-- HORMINOR - Migracion 075: recordatorios programados de Gato
-- Motivo: Gato deja de ser solo consulta y puede agendar un mensaje de
--         WhatsApp para una hora exacta ("escribele al Ing. Reyes a las
--         18:40 y recuerdale la cita"). La fila es la tarea; el despachador
--         de la API la envia cuando llega la hora.
-- Datos: solo lo que dicta el usuario. Si el cliente no tiene telefono
--        registrado, no se crea el recordatorio (no se inventa el numero).
-- =====================================================================

CREATE TABLE IF NOT EXISTS gato_recordatorios (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    creado_por           text NOT NULL,
    rol_actor            text NOT NULL,
    conversacion_id      uuid,
    cliente_id           uuid REFERENCES clients(id) ON DELETE SET NULL,
    destinatario_nombre  text,
    telefono             text NOT NULL,
    mensaje              text NOT NULL,
    programado_at        timestamptz NOT NULL,
    zona                 text NOT NULL DEFAULT 'America/Guayaquil',
    estado               text NOT NULL DEFAULT 'PENDIENTE'
        CHECK (estado IN ('PENDIENTE', 'ENVIANDO', 'ENVIADO', 'FALLIDO', 'CANCELADO')),
    intentos             integer NOT NULL DEFAULT 0,
    ultimo_error         text,
    enviado_at           timestamptz,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE gato_recordatorios IS
    'Tareas de envio programado creadas desde Gato. `programado_at` es absoluto (UTC); `zona` es solo para mostrar.';

CREATE INDEX IF NOT EXISTS ix_gato_recordatorios_pendientes
    ON gato_recordatorios (programado_at)
    WHERE estado = 'PENDIENTE';

CREATE INDEX IF NOT EXISTS ix_gato_recordatorios_actor
    ON gato_recordatorios (creado_por, created_at DESC);
