-- =====================================================================
-- HORMINOR - Migracion 073: facturas internas adjuntas al cliente
-- Motivo: Direccion pidio poder guardar la factura de una venta como
--         PDF o foto y que Gato pueda consultarla. La facturacion
--         electronica del SRI sigue FUERA de alcance: esta tabla es un
--         registro interno, sin clave de acceso, XML ni autorizacion.
-- Regla de datos: los montos salen de la orden o los carga el usuario.
--         Nunca se inventan. `es_ficticia` marca los documentos de prueba.
-- =====================================================================

CREATE TABLE IF NOT EXISTS client_invoices (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cliente_id       uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    orden_id         uuid REFERENCES orders(id) ON DELETE SET NULL,
    numero           text NOT NULL,
    fecha            date NOT NULL DEFAULT CURRENT_DATE,
    subtotal         numeric(12, 2) NOT NULL,
    iva_pct          numeric(5, 2) NOT NULL DEFAULT 0,
    iva_monto        numeric(12, 2) NOT NULL DEFAULT 0,
    total            numeric(12, 2) NOT NULL,
    estado           text NOT NULL DEFAULT 'EMITIDA'
                     CHECK (estado IN ('BORRADOR', 'EMITIDA', 'ANULADA')),
    es_ficticia      boolean NOT NULL DEFAULT false,
    nota             text,
    media_id         uuid REFERENCES media_assets(id) ON DELETE SET NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT client_invoices_numero_cliente UNIQUE (cliente_id, numero),
    CONSTRAINT client_invoices_total_coherente CHECK (total = subtotal + iva_monto),
    CONSTRAINT client_invoices_montos CHECK (subtotal >= 0 AND iva_monto >= 0)
);

COMMENT ON TABLE client_invoices IS
    'Factura interna adjunta al cliente (PDF o foto). NO es un comprobante electronico SRI. Los montos salen de la orden o los carga el usuario; es_ficticia marca pruebas.';

COMMENT ON COLUMN client_invoices.es_ficticia IS
    'true = documento de prueba. Se muestra con la marca FICTICIA y no sirve para cobro.';

CREATE INDEX IF NOT EXISTS ix_client_invoices_cliente_fecha
    ON client_invoices (cliente_id, fecha DESC);

CREATE INDEX IF NOT EXISTS ix_client_invoices_orden
    ON client_invoices (orden_id)
    WHERE orden_id IS NOT NULL;
