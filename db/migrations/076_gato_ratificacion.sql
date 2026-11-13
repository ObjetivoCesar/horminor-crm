-- =====================================================================
-- HORMINOR - Migracion 076: ratificacion y trazabilidad de recordatorios
-- Motivo: Gato no debe agendar a un cliente sin que Julio o Secretaria
--         ratifiquen. La tarea nace en BORRADOR, se lee de vuelta en el
--         chat y solo pasa a PENDIENTE cuando el usuario responde "si".
-- Tambien distingue si el destino vino del CRM o se dicto, y bloquea
--         duplicados con una clave de idempotencia.
-- No se edita la 075 (ya aplicada).
-- =====================================================================

-- 1. Nuevo estado BORRADOR
ALTER TABLE gato_recordatorios
    DROP CONSTRAINT IF EXISTS gato_recordatorios_estado_check;

ALTER TABLE gato_recordatorios
    ADD CONSTRAINT gato_recordatorios_estado_check
    CHECK (estado IN (
        'BORRADOR', 'PENDIENTE', 'ENVIANDO', 'ENVIADO', 'FALLIDO', 'CANCELADO'
    ));

-- 2. Origen del destino: CRM o numero dictado
ALTER TABLE gato_recordatorios
    ADD COLUMN IF NOT EXISTS origen_destino text NOT NULL DEFAULT 'CRM';

ALTER TABLE gato_recordatorios
    DROP CONSTRAINT IF EXISTS gato_recordatorios_origen_check;

ALTER TABLE gato_recordatorios
    ADD CONSTRAINT gato_recordatorios_origen_check
    CHECK (origen_destino IN ('CRM', 'DICTADO'));

-- 3. Quien ratifico y cuando
ALTER TABLE gato_recordatorios
    ADD COLUMN IF NOT EXISTS confirmado_por text;

ALTER TABLE gato_recordatorios
    ADD COLUMN IF NOT EXISTS confirmado_at timestamptz;

-- 4. Idempotencia: dos clics no crean dos tareas
ALTER TABLE gato_recordatorios
    ADD COLUMN IF NOT EXISTS clave_idempotencia text;

CREATE UNIQUE INDEX IF NOT EXISTS ux_gato_recordatorios_idempotencia
    ON gato_recordatorios (clave_idempotencia)
    WHERE clave_idempotencia IS NOT NULL;

COMMENT ON COLUMN gato_recordatorios.origen_destino IS
    'CRM = telefono tomado de clients.telefono_whatsapp; DICTADO = numero dado en el chat.';
COMMENT ON COLUMN gato_recordatorios.clave_idempotencia IS
    'sha256 de creador + conversacion + destino + mensaje + hora. Evita duplicados por doble clic.';
