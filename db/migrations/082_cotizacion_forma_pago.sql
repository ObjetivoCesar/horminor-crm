-- =====================================================================
-- ORMINORTH - Migracion 082: la forma de pago se define al convertir
-- Motivo: en la cotizacion no se pregunta efectivo/fiado; eso pertenece a
--         la conversion a cliente/orden. La cotizacion queda POR_DEFINIR.
-- =====================================================================

ALTER TABLE cotizaciones
    DROP CONSTRAINT IF EXISTS cotizaciones_forma_pago_check;

ALTER TABLE cotizaciones
    ALTER COLUMN forma_pago SET DEFAULT 'POR_DEFINIR';

ALTER TABLE cotizaciones
    ADD CONSTRAINT cotizaciones_forma_pago_check
    CHECK (forma_pago IN ('POR_DEFINIR', 'EFECTIVO', 'TRANSFERENCIA', 'ABONO', 'FIADO'));

UPDATE cotizaciones
   SET forma_pago = 'POR_DEFINIR'
 WHERE forma_pago IS NULL;
