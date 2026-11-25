-- =====================================================================
-- ORMINORTH - Migracion 101: settings y trazabilidad de skills de Gato
-- Motivo:
--   1. Parametros configurables en caliente para politicas de Gato
--      (permiso de envio de Secretaria, confirmacion de recordatorio
--      personal, margen de reservas y aprobacion de precio).
--   2. Enlace opcional de envio programado de cotizacion en
--      `gato_recordatorios` para saber que version del PDF salio, a que
--      hora se programo y con que id de proveedor.
-- =====================================================================

INSERT INTO system_settings (key, value, descripcion) VALUES
    (
        'gato.secretaria_envia_cotizacion_aprobada',
        'false'::jsonb,
        'PENDIENTE de ratificar: si Secretaria puede enviar por su cuenta una cotizacion ya aprobada.'
    ),
    (
        'gato.confirmar_recordatorio_personal',
        'false'::jsonb,
        'false = un recordatorio personal inequivoco y sin choque se agenda en un turno; true = pide confirmacion.'
    ),
    (
        'agenda.margen_reservas_min',
        'null'::jsonb,
        'PENDIENTE de ratificar por Julio: margen operativo en minutos entre reservas de flota.'
    ),
    (
        'cotizaciones.quien_aprueba_precio',
        '"SUPERADMIN"'::jsonb,
        'Quien puede aprobar un precio provisional para una propuesta concreta.'
    )
ON CONFLICT (key) DO NOTHING;

ALTER TABLE gato_recordatorios
    ADD COLUMN IF NOT EXISTS cotizacion_id uuid NULL
        REFERENCES cotizaciones(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS cotizacion_version integer NULL,
    ADD COLUMN IF NOT EXISTS proveedor_msg_id text NULL;

CREATE INDEX IF NOT EXISTS ix_gato_recordatorios_cotizacion
    ON gato_recordatorios (cotizacion_id)
    WHERE cotizacion_id IS NOT NULL;

COMMENT ON COLUMN gato_recordatorios.cotizacion_id IS
    'Cotizacion vinculada cuando un envio de PDF se programa en la cola de WhatsApp.';
COMMENT ON COLUMN gato_recordatorios.cotizacion_version IS
    'Version exacta del documento programado para enviar.';
COMMENT ON COLUMN gato_recordatorios.proveedor_msg_id IS
    'Identificador devuelto por Evolution API al aceptar el envio.';
