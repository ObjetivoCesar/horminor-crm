-- =====================================================================
-- ORMINORTH - Migracion 030: umbral de aviso termico
--
-- Este valor NO viene en el PDR: el documento solo fija el limite de
-- 150 min. Se agrega como parametro ajustable (propuesto por ingenieria)
-- para que el panel pueda pintar "POR_VENCER" antes de que se cumpla.
-- Julio puede cambiarlo sin tocar codigo.
-- =====================================================================

INSERT INTO system_settings (key, value, descripcion) VALUES
    ('operacion.umbral_por_vencer_minutos', '30'::jsonb,
     'PROPUESTO POR INGENIERIA: minutos antes del limite termico para marcar el viaje como POR_VENCER. Ajustable.')
ON CONFLICT (key) DO NOTHING;
