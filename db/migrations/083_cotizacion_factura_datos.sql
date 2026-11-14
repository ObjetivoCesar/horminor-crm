-- =====================================================================
-- ORMINORTH - Migracion 083: datos de factura capturados al convertir
-- Motivo: la cotizacion no pregunta forma de pago ni datos fiscales. Al
--         convertir a cliente se capturan para emitir la factura interna.
-- =====================================================================

ALTER TABLE cotizaciones
    ADD COLUMN IF NOT EXISTS factura_datos jsonb NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN cotizaciones.factura_datos IS
    'Razon social, RUC/CI, direccion, email y fechas capturados al convertir. NULL/{} = pendiente.';
