-- =====================================================================
-- HORMINOR / CENTINELA - Migracion 064: vistas del Custodio v4.3
--
-- Compatibilidad dura:
--   v_cliente_saldo conserva las 8 columnas y tipos de 001_init.sql:
--   id, nombre, estado, total_m3, total_facturado, total_cobrado,
--   total_fiado, saldo_pendiente.
--   Al final agrega ruc, credit_limit_usd y saldo_a_favor.
--
-- Los historicos tienen total_con_iva = total (migracion 063), por eso
-- el KPI por_cobrar del Dashboard V2 no cambia: 47,864 / 2 clientes.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Saldo del cliente
--    - Una venta de contado genera un COBRO; por eso facturado - cobrado
--      funciona para contado, abono y fiado.
--    - FIADO no genera COBRO: queda como deuda.
--    - Los pagos con metodo FIADO no son efectivo y no se suman a cobrado.
--    - COALESCE(total_con_iva, total) mantiene visibles las ordenes creadas
--      por codigo viejo que aun no escribe total_con_iva.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_cliente_saldo AS
WITH ventas AS (
    SELECT
        o.cliente_id,
        COALESCE(SUM(o.volumen_m3), 0) AS total_m3,
        COALESCE(SUM(COALESCE(o.total_con_iva, o.total)), 0) AS total_facturado,
        COALESCE(SUM(
            CASE WHEN o.forma_pago = 'FIADO'
                 THEN COALESCE(o.total_con_iva, o.total)
                 ELSE 0 END
        ), 0) AS total_fiado
    FROM orders o
    WHERE o.estado <> 'ANULADA'
    GROUP BY o.cliente_id
),
cobros AS (
    SELECT
        p.cliente_id,
        COALESCE(SUM(p.monto), 0) AS total_cobrado
    FROM payments p
    WHERE p.tipo_movimiento = 'COBRO'
      AND p.metodo <> 'FIADO'
      AND p.deleted_at IS NULL
      AND p.cliente_id IS NOT NULL
    GROUP BY p.cliente_id
)
SELECT
    c.id,
    c.nombre,
    c.estado,
    COALESCE(v.total_m3, 0) AS total_m3,
    COALESCE(v.total_facturado, 0) AS total_facturado,
    COALESCE(cb.total_cobrado, 0) AS total_cobrado,
    COALESCE(v.total_fiado, 0) AS total_fiado,
    GREATEST(
        COALESCE(v.total_facturado, 0) - COALESCE(cb.total_cobrado, 0),
        0
    ) AS saldo_pendiente,
    c.ruc,
    c.credit_limit_usd,
    GREATEST(
        COALESCE(cb.total_cobrado, 0) - COALESCE(v.total_facturado, 0),
        0
    ) AS saldo_a_favor
FROM clients c
LEFT JOIN ventas v ON v.cliente_id = c.id
LEFT JOIN cobros cb ON cb.cliente_id = c.id;

COMMENT ON VIEW v_cliente_saldo IS
    'Saldo por cliente. total_facturado usa total_con_iva; total_cobrado solo COBRO no FIADO y no borrado. saldo_pendiente = facturado - cobrado.';

-- ---------------------------------------------------------------------
-- 2. Stock proyectado
--    stock_actual es el stock fisico confirmado. El teorico posterior al
--    ultimo conteo se suma aparte. Si no hay fecha de conteo, no se aplica
--    ningun teorico: se marca SIN_FECHA_CONTEO.
--    ANULACION se suma en valor absoluto (es una reversa positiva).
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_stock_proyectado AS
WITH movs_post_corte AS (
    SELECT
        im.material_id,
        COALESCE(SUM(
            CASE
                WHEN im.tipo = 'TEORICO' THEN im.cantidad
                WHEN im.tipo = 'ANULACION' THEN abs(im.cantidad)
                ELSE 0
            END
        ), 0) AS delta_teorico_post_corte
    FROM inventory_movements im
    JOIN materials m ON m.id = im.material_id
    WHERE m.ultimo_levantamiento_at IS NOT NULL
      AND im.created_at > m.ultimo_levantamiento_at
    GROUP BY im.material_id
)
SELECT
    m.id AS material_id,
    m.codigo,
    m.nombre,
    m.unidad,
    m.stock_actual AS stock_real_fisico,
    COALESCE(mp.delta_teorico_post_corte, 0) AS consumo_teorico_acumulado,
    CASE
        WHEN m.stock_actual IS NULL THEN NULL
        ELSE m.stock_actual + COALESCE(mp.delta_teorico_post_corte, 0)
    END AS stock_proyectado_disponible,
    m.stock_minimo,
    m.costo_unitario,
    m.ultimo_levantamiento_at,
    CASE
        WHEN m.stock_actual IS NULL THEN 'SIN_LEVANTAR'
        WHEN m.ultimo_levantamiento_at IS NULL THEN 'SIN_FECHA_CONTEO'
        WHEN m.stock_minimo IS NULL THEN 'SIN_UMBRAL'
        WHEN m.stock_actual + COALESCE(mp.delta_teorico_post_corte, 0)
             <= m.stock_minimo THEN 'CRITICO'
        ELSE 'OK'
    END AS estado_alerta_proyectada
FROM materials m
LEFT JOIN movs_post_corte mp ON mp.material_id = m.id;

COMMENT ON VIEW v_stock_proyectado IS
    'Stock fisico + consumos TEORICO posteriores al ultimo conteo. Sin fecha de conteo no aplica teoricos y marca SIN_FECHA_CONTEO.';

-- ---------------------------------------------------------------------
-- 3. Balance general
--    Respeta fusiones de cuentas (merged_into_id) sin reescribir el ledger.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_balance_general AS
WITH cuentas_efectivas AS (
    SELECT
        COALESCE(aa.merged_into_id, aa.id) AS effective_account_id,
        le.debe,
        le.haber
    FROM ledger_entries le
    JOIN accounting_accounts aa ON aa.id = le.account_id
),
saldos AS (
    SELECT
        a.id AS account_id,
        a.code,
        a.slug,
        a.name,
        a.account_type,
        a.parent_group,
        a.normal_balance,
        CASE
            WHEN a.normal_balance = 'DEBIT'
                THEN COALESCE(SUM(ce.debe - ce.haber), 0)
            ELSE COALESCE(SUM(ce.haber - ce.debe), 0)
        END::numeric(14,2) AS saldo_neto
    FROM accounting_accounts a
    LEFT JOIN cuentas_efectivas ce ON ce.effective_account_id = a.id
    WHERE a.deleted_at IS NULL
    GROUP BY
        a.id, a.code, a.slug, a.name, a.account_type,
        a.parent_group, a.normal_balance
)
SELECT * FROM saldos ORDER BY code;

COMMENT ON VIEW v_balance_general IS
    'Saldo por cuenta contable segun su naturaleza (DEBIT/CREDIT). Las cuentas fusionadas suman en la cuenta destino.';

-- ---------------------------------------------------------------------
-- 4. Estado de resultados por mes y cuenta
--    El servicio filtra el rango de fechas y suma periodos.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_estado_resultados AS
WITH asientos AS (
    SELECT
        COALESCE(aa.merged_into_id, aa.id) AS effective_account_id,
        le.fecha_asiento,
        le.debe,
        le.haber
    FROM ledger_entries le
    JOIN accounting_accounts aa ON aa.id = le.account_id
),
agrupado AS (
    SELECT
        date_trunc('month', e.fecha_asiento)::date AS periodo,
        a.id AS account_id,
        a.code,
        a.slug,
        a.name,
        a.account_type,
        a.parent_group,
        COALESCE(SUM(e.debe), 0)::numeric(14,2) AS debe,
        COALESCE(SUM(e.haber), 0)::numeric(14,2) AS haber,
        CASE
            WHEN a.account_type = 'REVENUE'
                THEN COALESCE(SUM(e.haber - e.debe), 0)
            ELSE COALESCE(SUM(e.debe - e.haber), 0)
        END::numeric(14,2) AS saldo
    FROM asientos e
    JOIN accounting_accounts a ON a.id = e.effective_account_id
    WHERE a.account_type IN ('REVENUE', 'EXPENSE')
      AND a.deleted_at IS NULL
    GROUP BY
        date_trunc('month', e.fecha_asiento)::date,
        a.id, a.code, a.slug, a.name, a.account_type, a.parent_group
)
SELECT * FROM agrupado ORDER BY periodo, code;

COMMENT ON VIEW v_estado_resultados IS
    'P&L mensual por cuenta de ingreso/gasto. saldo positivo = ingreso o gasto segun account_type. No incluye cuentas de balance.';
