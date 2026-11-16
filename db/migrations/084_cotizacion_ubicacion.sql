-- =====================================================================
-- ORMINORTH - Migracion 084: ubicacion de la obra en la cotizacion
-- Motivo: el mixer necesita llegar. La obra se describe con texto libre y,
--         cuando el cliente comparte su pin de WhatsApp o el asesor usa el
--         GPS del navegador, se guardan coordenadas reales. Nada se inventa:
--         sin dato queda NULL y la UI lo dice.
-- Regla: la ubicacion es del cliente/obra, no del sistema. No se estima.
-- =====================================================================

ALTER TABLE cotizaciones
    ADD COLUMN IF NOT EXISTS ubicacion_texto text,
    ADD COLUMN IF NOT EXISTS ubicacion_lat numeric(10, 7),
    ADD COLUMN IF NOT EXISTS ubicacion_lng numeric(10, 7),
    ADD COLUMN IF NOT EXISTS ubicacion_origen text,
    ADD COLUMN IF NOT EXISTS ubicacion_solicitada_at timestamptz,
    ADD COLUMN IF NOT EXISTS ubicacion_recibida_at timestamptz;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'cotizaciones_ubicacion_origen_check'
    ) THEN
        ALTER TABLE cotizaciones
            ADD CONSTRAINT cotizaciones_ubicacion_origen_check
            CHECK (
                ubicacion_origen IS NULL
                OR ubicacion_origen IN ('MANUAL', 'GPS', 'WHATSAPP', 'MAPA')
            );
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'cotizaciones_ubicacion_rango_check'
    ) THEN
        ALTER TABLE cotizaciones
            ADD CONSTRAINT cotizaciones_ubicacion_rango_check
            CHECK (
                (ubicacion_lat IS NULL AND ubicacion_lng IS NULL)
                OR (
                    ubicacion_lat BETWEEN -90 AND 90
                    AND ubicacion_lng BETWEEN -180 AND 180
                )
            );
    END IF;
END $$;

COMMENT ON COLUMN cotizaciones.ubicacion_texto IS
    'Referencia escrita por el asesor o el cliente (sector, via, enlace). NULL = pendiente.';
COMMENT ON COLUMN cotizaciones.ubicacion_lat IS
    'Latitud real compartida por WhatsApp o GPS del navegador. NULL = sin pin.';
COMMENT ON COLUMN cotizaciones.ubicacion_lng IS
    'Longitud real compartida por WhatsApp o GPS del navegador. NULL = sin pin.';
COMMENT ON COLUMN cotizaciones.ubicacion_origen IS
    'MANUAL (texto), GPS (navegador), WHATSAPP (pin del cliente) o MAPA (enlace pegado).';
COMMENT ON COLUMN cotizaciones.ubicacion_solicitada_at IS
    'Ultima vez que Secretaria pidio el pin por WhatsApp.';
COMMENT ON COLUMN cotizaciones.ubicacion_recibida_at IS
    'Cuando llego el pin por WhatsApp. NULL = aun no responde.';

-- Los eventos de ubicacion viajan por la misma bitacora de la cotizacion.
-- El CHECK original (081) solo permitia ENVIO/CONFIRMACION/NEGOCIACION/
-- RECHAZO/PREGUNTA/NOTA; se amplia sin tocar el historico.
DO $$
BEGIN
    ALTER TABLE cotizacion_eventos
        DROP CONSTRAINT IF EXISTS cotizacion_eventos_tipo_check;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'cotizacion_eventos_tipo_check_ext'
    ) THEN
        ALTER TABLE cotizacion_eventos
            ADD CONSTRAINT cotizacion_eventos_tipo_check_ext
            CHECK (
                tipo IN (
                    'ENVIO', 'CONFIRMACION', 'NEGOCIACION', 'RECHAZO', 'PREGUNTA',
                    'NOTA', 'UBICACION_SOLICITADA', 'UBICACION_RECIBIDA'
                )
            );
    END IF;
END $$;

-- Mensaje con el que se pide el pin. Es plantilla de comunicacion, no dato
-- de negocio: Julio la puede editar en caliente desde system_settings.
INSERT INTO system_settings (key, value, descripcion)
VALUES (
    'cotizaciones.pedir_ubicacion',
    jsonb_build_object(
        'texto',
        'Hola. Para despachar el hormigon a la obra necesitamos la ubicacion exacta. '
        'Toca el clip > Ubicacion > Enviar mi ubicacion actual y quedara registrada en la cotizacion.'
    ),
    'Texto que se envia por WhatsApp cuando Secretaria pide el pin de la obra.'
)
ON CONFLICT (key) DO NOTHING;
