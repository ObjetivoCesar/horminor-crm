-- Agenda de Gato: visitas con contacto libre y recordatorios internos.
ALTER TABLE citas
    ADD COLUMN IF NOT EXISTS contacto_agenda text,
    ADD COLUMN IF NOT EXISTS clave_gato text;

CREATE UNIQUE INDEX IF NOT EXISTS ux_citas_clave_gato
    ON citas (clave_gato) WHERE clave_gato IS NOT NULL;

ALTER TABLE gato_recordatorios
    ALTER COLUMN telefono DROP NOT NULL,
    DROP CONSTRAINT IF EXISTS gato_recordatorios_estado_check,
    DROP CONSTRAINT IF EXISTS gato_recordatorios_origen_check;

ALTER TABLE gato_recordatorios
    ADD CONSTRAINT gato_recordatorios_estado_check
        CHECK (estado IN ('BORRADOR', 'AGENDADO', 'PENDIENTE', 'ENVIANDO',
                          'ENVIADO', 'FALLIDO', 'CANCELADO')),
    ADD CONSTRAINT gato_recordatorios_origen_check
        CHECK (origen_destino IN ('CRM', 'DICTADO', 'PANEL')),
    ADD CONSTRAINT gato_recordatorios_canal_estado_check
        CHECK ((origen_destino = 'PANEL' AND telefono IS NULL
                AND estado IN ('AGENDADO', 'CANCELADO'))
            OR (origen_destino <> 'PANEL' AND telefono IS NOT NULL
                AND estado <> 'AGENDADO'));
