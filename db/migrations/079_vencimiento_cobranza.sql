-- =====================================================================
-- ORMINORTH - Migracion 079: vencimiento de documentos por cobrar
-- Motivo: el tablero de Cobranza necesita fecha de vencimiento para
--         calcular antiguedad. Ni orders ni client_invoices la tienen.
--         Se agrega NULL: no se inventan fechas. Los formularios de
--         ordenes y facturas deben capturarla cuando se disenen.
-- =====================================================================

ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS fecha_vencimiento date;

COMMENT ON COLUMN orders.fecha_vencimiento IS
    'Vencimiento del saldo de la orden. NULL = pendiente de capturar en el formulario de ordenes. No inventar.';

ALTER TABLE client_invoices
    ADD COLUMN IF NOT EXISTS fecha_vencimiento date;

COMMENT ON COLUMN client_invoices.fecha_vencimiento IS
    'Vencimiento de la factura interna. NULL = pendiente de capturar en el formulario de facturas. No inventar.';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conname = 'client_invoices_vencimiento_coherente'
    ) THEN
        ALTER TABLE client_invoices
            ADD CONSTRAINT client_invoices_vencimiento_coherente
            CHECK (fecha_vencimiento IS NULL OR fecha_vencimiento >= fecha);
    END IF;
END $$;

-- Indices parciales: solo documentos con vencimiento y no anulados.
CREATE INDEX IF NOT EXISTS ix_orders_vencimiento
    ON orders (fecha_vencimiento)
    WHERE fecha_vencimiento IS NOT NULL AND estado <> 'ANULADA';

CREATE INDEX IF NOT EXISTS ix_client_invoices_vencimiento
    ON client_invoices (fecha_vencimiento)
    WHERE fecha_vencimiento IS NOT NULL AND estado <> 'ANULADA';

-- ---------------------------------------------------------------------
-- Documentos por cobrar con su vencimiento.
-- OJO: monto_documento es el total del documento, NO el saldo pendiente.
-- La imputacion pago -> documento todavia no existe; el saldo real por
-- cliente sale de v_cliente_saldo. Este vista sirve para fechas y
-- antiguedad documental, no para afirmar cuanto queda por cobrar de cada
-- documento.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_cobranza_documentos AS
SELECT
    'ORDEN'::text                         AS tipo,
    o.id                                  AS documento_id,
    o.numero::text                        AS numero,
    o.cliente_id,
    c.nombre                              AS cliente,
    o.created_at::date                    AS fecha_emision,
    o.fecha_vencimiento,
    (CURRENT_DATE - o.created_at::date)   AS dias_desde_emision,
    (o.fecha_vencimiento - CURRENT_DATE)  AS dias_para_vencer,
    COALESCE(o.total_con_iva, o.total, 0) AS monto_documento,
    o.estado,
    CASE
        WHEN o.fecha_vencimiento IS NULL             THEN 'SIN_VENCIMIENTO'
        WHEN o.fecha_vencimiento < CURRENT_DATE      THEN 'VENCIDA'
        WHEN o.fecha_vencimiento <= CURRENT_DATE + 7 THEN 'POR_VENCER_7'
        ELSE 'CORRIENTE'
    END                                   AS estado_vencimiento
FROM orders o
JOIN clients c ON c.id = o.cliente_id
WHERE o.estado <> 'ANULADA'

UNION ALL

SELECT
    'FACTURA'::text,
    i.id,
    i.numero,
    i.cliente_id,
    c.nombre,
    i.fecha,
    i.fecha_vencimiento,
    (CURRENT_DATE - i.fecha),
    (i.fecha_vencimiento - CURRENT_DATE),
    i.total,
    i.estado,
    CASE
        WHEN i.fecha_vencimiento IS NULL             THEN 'SIN_VENCIMIENTO'
        WHEN i.fecha_vencimiento < CURRENT_DATE      THEN 'VENCIDA'
        WHEN i.fecha_vencimiento <= CURRENT_DATE + 7 THEN 'POR_VENCER_7'
        ELSE 'CORRIENTE'
    END
FROM client_invoices i
JOIN clients c ON c.id = i.cliente_id
WHERE i.estado <> 'ANULADA';

COMMENT ON VIEW v_cobranza_documentos IS
    'Documentos por cobrar con su vencimiento. monto_documento es el total del documento, NO el saldo pendiente: la imputacion pago->documento aun no existe. El saldo real por cliente sale de v_cliente_saldo.';
