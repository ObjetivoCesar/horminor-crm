-- =====================================================================
-- HORMINOR / CENTINELA - Migracion 063: nucleo del Custodio v4.3
--
-- Decisiones aplicadas (2026-11-09):
--   1. Cada venta EFECTIVO / TRANSFERENCIA / ABONO inicial genera un
--      payments tipo COBRO. FIADO no genera COBRO (es credito).
--   2. IVA 15% por defecto para ventas NUEVAS; el saldo y el cupo usan
--      total_con_iva. Los historicos quedan SIN IVA (total_con_iva = total)
--      hasta que Julio confirme el tratamiento retroactivo.
--   3. Inventario y COGS por PROMEDIO PONDERADO.
--   4. Altas de proveedores, activos fijos y pasivos bancarios por el Gate.
--   5. materials.ultimo_levantamiento_at queda NULL hasta que Julio
--      entregue la fecha del ultimo conteo fisico. No se inventa.
--
-- Esta migracion NO aplica datos de negocio nuevos. Los parametros que
-- faltan quedan NULL o marcados como pendientes en system_settings.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Ajustes a tablas existentes
-- ---------------------------------------------------------------------

-- 1.1 Kardex: la anulacion es un movimiento de reversa, no un borrado.
ALTER TABLE inventory_movements
    DROP CONSTRAINT IF EXISTS inventory_movements_tipo_check;
ALTER TABLE inventory_movements
    ADD CONSTRAINT inventory_movements_tipo_check
    CHECK (tipo IN ('TEORICO', 'REAL', 'COMPRA', 'AJUSTE', 'ANULACION'));

ALTER TABLE inventory_movements
    ADD COLUMN IF NOT EXISTS costo_unitario_snapshot numeric(14,4);

COMMENT ON COLUMN inventory_movements.costo_unitario_snapshot IS
    'Costo promedio ponderado vigente al momento del movimiento. NULL en movimientos historicos sin costo confirmado.';

CREATE INDEX IF NOT EXISTS ix_invmov_tipo_created
    ON inventory_movements (tipo, created_at DESC);

-- 1.2 Materiales: fecha real del ultimo conteo fisico.
--     NULL = Julio aun no la confirma. No usar NOW() como sustituto.
ALTER TABLE materials
    ADD COLUMN IF NOT EXISTS ultimo_levantamiento_at timestamptz;
ALTER TABLE materials
    ALTER COLUMN ultimo_levantamiento_at DROP NOT NULL;
ALTER TABLE materials
    ALTER COLUMN ultimo_levantamiento_at DROP DEFAULT;

COMMENT ON COLUMN materials.ultimo_levantamiento_at IS
    'Fecha del ultimo conteo fisico confirmado por Julio. NULL = pendiente; v_stock_proyectado marca SIN_FECHA_CONTEO y no aplica consumos teoricos.';

-- 1.3 Ordenes: IVA y total bruto.
--     total sigue siendo el subtotal generado (volumen_m3 * precio_m3).
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS aplica_iva boolean NOT NULL DEFAULT false;
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS iva_pct numeric(5,2) NOT NULL DEFAULT 0;
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS iva_monto numeric(12,2) NOT NULL DEFAULT 0;
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS total_con_iva numeric(12,2);

ALTER TABLE orders
    ALTER COLUMN total_con_iva DROP NOT NULL;
ALTER TABLE orders
    ALTER COLUMN total_con_iva DROP DEFAULT;

-- Historicos: la base real no tenia IVA modelado. Se dejan sin IVA
-- (total_con_iva = total) y se marcan como pendientes de confirmacion.
UPDATE orders
   SET aplica_iva = false,
       iva_pct = 0,
       iva_monto = 0,
       total_con_iva = total
 WHERE (total_con_iva IS NULL AND total IS NOT NULL)
    OR (total_con_iva = 0 AND total IS NOT NULL AND total > 0);

ALTER TABLE orders
    DROP CONSTRAINT IF EXISTS orders_iva_pct_check;
ALTER TABLE orders
    ADD CONSTRAINT orders_iva_pct_check
    CHECK (iva_pct >= 0 AND iva_pct <= 100);

ALTER TABLE orders
    DROP CONSTRAINT IF EXISTS orders_iva_coherente;
ALTER TABLE orders
    ADD CONSTRAINT orders_iva_coherente
    CHECK (
        (aplica_iva = false AND iva_pct = 0 AND iva_monto = 0)
        OR
        (aplica_iva = true AND iva_monto = round(total * iva_pct / 100, 2))
    );

ALTER TABLE orders
    DROP CONSTRAINT IF EXISTS orders_total_con_iva_coherente;
ALTER TABLE orders
    ADD CONSTRAINT orders_total_con_iva_coherente
    CHECK (
        (total IS NULL AND total_con_iva IS NULL)
        OR
        (total IS NOT NULL AND total_con_iva = total + iva_monto)
    );

COMMENT ON COLUMN orders.aplica_iva IS
    'true = la venta nueva aplica IVA. Default de aplicacion: true (decision 2026-11-09); el servicio copia iva_pct desde concrete_recipes.';
COMMENT ON COLUMN orders.iva_pct IS
    'Porcentaje de IVA aplicado. 15.00 para recetas confirmadas; 0 en ordenes historicas sin IVA confirmado.';
COMMENT ON COLUMN orders.iva_monto IS
    'IVA calculado: round(total * iva_pct / 100, 2).';
COMMENT ON COLUMN orders.total_con_iva IS
    'Total bruto de la venta (subtotal + IVA). Historicos sin IVA confirmado: igual a total.';

-- 1.4 Payments: movimientos de caja y gastos sin cliente.
--     (Se altera despues del plan de cuentas, porque account_id lo referencia.)

-- ---------------------------------------------------------------------
-- 2. Idempotencia del Gate
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS processed_requests (
    request_id       uuid PRIMARY KEY,
    payload_sha256   text NOT NULL,
    actor_role       text NOT NULL,
    actor_id         text NOT NULL,
    channel          text NOT NULL
                     CHECK (channel IN ('WEB_PANEL', 'WHATSAPP', 'SYSTEM_CRON', 'TEST')),
    intent           text NOT NULL,
    response_status  text NOT NULL,
    response_payload jsonb NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE processed_requests IS
    'Idempotencia del Gate: request_id unico + hash del payload. Un reintento con el mismo hash devuelve la misma respuesta; un hash distinto se rechaza.';

-- ---------------------------------------------------------------------
-- 3. Plan de cuentas contables
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounting_accounts (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code             text NOT NULL UNIQUE,
    slug             text NOT NULL UNIQUE,
    name             text NOT NULL,
    account_type     text NOT NULL
                     CHECK (account_type IN ('ASSET', 'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE')),
    normal_balance   text NOT NULL
                     CHECK (normal_balance IN ('DEBIT', 'CREDIT')),
    parent_group     text NOT NULL
                     CHECK (parent_group IN (
                         'ACTIVO_CORRIENTE', 'ACTIVO_NO_CORRIENTE',
                         'PASIVO_CORRIENTE', 'PASIVO_LARGO_PLAZO',
                         'PATRIMONIO_NETO', 'INGRESO_OPERATIVO',
                         'COSTO_DIRECTO', 'CIF_PLANTA',
                         'GASTO_ADMIN_FIJO', 'CAJA_CHICA', 'FISCAL_FINANCIERO'
                     )),
    default_bolsa    text NOT NULL DEFAULT 'BANCO_GERENCIA'
                     CHECK (default_bolsa IN (
                         'CAJA_DIARIA', 'BANCO_GERENCIA',
                         'CARTERA_O_PASIVO', 'NO_MONETARIO'
                     )),
    requires_voucher boolean NOT NULL DEFAULT false,
    is_system_locked boolean NOT NULL DEFAULT false,
    merged_into_id   uuid REFERENCES accounting_accounts(id),
    deleted_at       timestamptz,
    created_by       text NOT NULL DEFAULT 'SYSTEM',
    created_at       timestamptz NOT NULL DEFAULT now()
);

INSERT INTO accounting_accounts
    (code, slug, name, account_type, normal_balance, parent_group,
     default_bolsa, requires_voucher, is_system_locked)
VALUES
    ('1101', 'caja_diaria_secretaria', 'Caja Diaria Secretaria', 'ASSET', 'DEBIT', 'ACTIVO_CORRIENTE', 'CAJA_DIARIA', false, true),
    ('1102', 'bancos_gerencia', 'Bancos y Cuentas Gerencia', 'ASSET', 'DEBIT', 'ACTIVO_CORRIENTE', 'BANCO_GERENCIA', true, true),
    ('1103', 'cuentas_por_cobrar_clientes', 'Cuentas por Cobrar Clientes (Fiado)', 'ASSET', 'DEBIT', 'ACTIVO_CORRIENTE', 'CARTERA_O_PASIVO', false, true),
    ('1104', 'inventario_insumos_silos', 'Inventario de Insumos en Silos y Bodega', 'ASSET', 'DEBIT', 'ACTIVO_CORRIENTE', 'CARTERA_O_PASIVO', false, true),
    ('1105', 'iva_credito_tributario', 'IVA Credito Tributario', 'ASSET', 'DEBIT', 'ACTIVO_CORRIENTE', 'CARTERA_O_PASIVO', true, true),
    ('1201', 'propiedad_planta_equipo', 'Propiedad, Planta, Mixers y Equipos', 'ASSET', 'DEBIT', 'ACTIVO_NO_CORRIENTE', 'NO_MONETARIO', true, true),
    ('1202', 'depreciacion_acumulada_activos', '(-) Depreciacion Acumulada Activos Fijos', 'ASSET', 'CREDIT', 'ACTIVO_NO_CORRIENTE', 'NO_MONETARIO', false, true),
    ('2101', 'cuentas_por_pagar_proveedores', 'Cuentas por Pagar Proveedores', 'LIABILITY', 'CREDIT', 'PASIVO_CORRIENTE', 'CARTERA_O_PASIVO', true, true),
    ('2102', 'anticipos_de_clientes', 'Anticipos Recibidos de Clientes', 'LIABILITY', 'CREDIT', 'PASIVO_CORRIENTE', 'CARTERA_O_PASIVO', false, true),
    ('2103', 'iva_interno_por_liquidar', 'IVA Interno por Liquidar', 'LIABILITY', 'CREDIT', 'PASIVO_CORRIENTE', 'CARTERA_O_PASIVO', false, true),
    ('2201', 'prestamos_bancarios_lp', 'Prestamos y Obligaciones Bancarias', 'LIABILITY', 'CREDIT', 'PASIVO_LARGO_PLAZO', 'BANCO_GERENCIA', true, true),
    ('3101', 'capital_social_y_apertura', 'Capital Social y Saldos de Apertura', 'EQUITY', 'CREDIT', 'PATRIMONIO_NETO', 'NO_MONETARIO', false, true),
    ('3102', 'resultados_acumulados', 'Utilidades / Resultados Acumulados', 'EQUITY', 'CREDIT', 'PATRIMONIO_NETO', 'NO_MONETARIO', false, true),
    ('4101', 'ventas_hormigon', 'Ventas de Hormigon Premezclado', 'REVENUE', 'CREDIT', 'INGRESO_OPERATIVO', 'CARTERA_O_PASIVO', false, true),
    ('5101', 'costo_directo_produccion_cogs', 'Costo Directo de Produccion (COGS Hormigon)', 'EXPENSE', 'DEBIT', 'COSTO_DIRECTO', 'NO_MONETARIO', false, true),
    ('5102', 'insumos_menores_no_inventariables', 'Insumos Menores de Planta No Inventariables', 'EXPENSE', 'DEBIT', 'COSTO_DIRECTO', 'BANCO_GERENCIA', true, false),
    ('5103', 'combustible_diesel_planta_mixers', 'Diesel y Combustible Operativo', 'EXPENSE', 'DEBIT', 'COSTO_DIRECTO', 'BANCO_GERENCIA', true, false),
    ('5105', 'merma_ajuste_inventario', 'Costo por Merma o Ajuste Fisico de Silos', 'EXPENSE', 'DEBIT', 'COSTO_DIRECTO', 'NO_MONETARIO', false, true),
    ('5201', 'mantenimiento_repuestos_mixers', 'Mantenimiento y Repuestos de Mixers y Planta', 'EXPENSE', 'DEBIT', 'CIF_PLANTA', 'BANCO_GERENCIA', true, false),
    ('5202', 'sueldos_operadores_choferes', 'Nomina de Planta y Choferes', 'EXPENSE', 'DEBIT', 'CIF_PLANTA', 'BANCO_GERENCIA', true, false),
    ('5203', 'gasto_depreciacion_planta_flota', 'Gasto por Depreciacion Mensual (NIC 16)', 'EXPENSE', 'DEBIT', 'CIF_PLANTA', 'NO_MONETARIO', false, true),
    ('5301', 'materiales_oficina_papeleria', 'Materiales de Oficina y Papeleria', 'EXPENSE', 'DEBIT', 'GASTO_ADMIN_FIJO', 'CAJA_DIARIA', true, false),
    ('5302', 'sueldos_administrativos', 'Sueldos y Honorarios Administrativos', 'EXPENSE', 'DEBIT', 'GASTO_ADMIN_FIJO', 'BANCO_GERENCIA', true, false),
    ('5303', 'servicios_basicos_internet_luz', 'Servicios Basicos (Luz, Agua, Internet)', 'EXPENSE', 'DEBIT', 'GASTO_ADMIN_FIJO', 'BANCO_GERENCIA', true, false),
    ('5401', 'viaticos_peajes_caja_chica', 'Viaticos, Peajes y Gastos Menores Caja Chica', 'EXPENSE', 'DEBIT', 'CAJA_CHICA', 'CAJA_DIARIA', false, false),
    ('5501', 'intereses_comisiones_bancarias', 'Intereses de Prestamos y Comisiones Bancarias', 'EXPENSE', 'DEBIT', 'FISCAL_FINANCIERO', 'BANCO_GERENCIA', true, false)
ON CONFLICT DO NOTHING;

COMMENT ON TABLE accounting_accounts IS
    'Plan de cuentas del Custodio. is_system_locked = true impide renombrar o fusionar la cuenta raiz.';
COMMENT ON COLUMN accounting_accounts.merged_into_id IS
    'Si la cuenta fue fusionada, apunta a la cuenta destino. El ledger historico no se reescribe.';

-- ---------------------------------------------------------------------
-- 3.1 Payments: movimientos de caja y gastos sin cliente
-- ---------------------------------------------------------------------
ALTER TABLE payments
    ALTER COLUMN cliente_id DROP NOT NULL;

ALTER TABLE payments
    DROP CONSTRAINT IF EXISTS payments_tipo_movimiento_check;
ALTER TABLE payments
    ADD CONSTRAINT payments_tipo_movimiento_check
    CHECK (tipo_movimiento IN (
        'COBRO', 'GASTO_CAJA_CHICA', 'GASTO_BANCARIO', 'REEMBOLSO_CAJA'
    ));

ALTER TABLE payments
    ADD COLUMN IF NOT EXISTS account_id uuid REFERENCES accounting_accounts(id);
ALTER TABLE payments
    ADD COLUMN IF NOT EXISTS bolsa text NOT NULL DEFAULT 'CAJA_DIARIA';
ALTER TABLE payments
    ADD COLUMN IF NOT EXISTS es_anticipo boolean NOT NULL DEFAULT false;
ALTER TABLE payments
    ADD COLUMN IF NOT EXISTS deleted_at timestamptz;

ALTER TABLE payments
    DROP CONSTRAINT IF EXISTS payments_bolsa_check;
ALTER TABLE payments
    ADD CONSTRAINT payments_bolsa_check
    CHECK (bolsa IN ('CAJA_DIARIA', 'BANCO_GERENCIA'));

CREATE INDEX IF NOT EXISTS ix_payments_order
    ON payments (order_id);
CREATE INDEX IF NOT EXISTS ix_payments_tipo_fecha
    ON payments (tipo_movimiento, fecha DESC);

COMMENT ON COLUMN payments.account_id IS
    'Cuenta contable del movimiento. COBRO: 1101/1102; gasto: cuenta de gasto. NULL en movimientos historicos.';
COMMENT ON COLUMN payments.bolsa IS
    'CAJA_DIARIA = efectivo fisico; BANCO_GERENCIA = cuenta bancaria.';
COMMENT ON COLUMN payments.es_anticipo IS
    'true = cobro anticipado sin orden asociada; queda como saldo a favor del cliente.';
COMMENT ON COLUMN payments.deleted_at IS
    'Borrado logico. Las vistas y el cierre de caja deben filtrar deleted_at IS NULL.';

-- ---------------------------------------------------------------------
-- 4. Proveedores, compras, recepciones y pagos a proveedores
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS suppliers (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre         text NOT NULL,
    identificacion text,
    telefono       text,
    activo         boolean NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_suppliers_identificacion
    ON suppliers (identificacion)
    WHERE identificacion IS NOT NULL;

CREATE TABLE IF NOT EXISTS purchases (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_id            uuid NOT NULL REFERENCES suppliers(id),
    fecha_compra           date NOT NULL,
    modalidad_pago         text NOT NULL
                           CHECK (modalidad_pago IN (
                               'CONTADO_EFECTIVO', 'CONTADO_TRANSFERENCIA',
                               'CREDITO_PROVEEDOR', 'MIXTO_ABONO_CREDITO'
                           )),
    subtotal               numeric(14,2) NOT NULL CHECK (subtotal >= 0),
    iva_monto              numeric(14,2) NOT NULL DEFAULT 0 CHECK (iva_monto >= 0),
    monto_total            numeric(14,2) NOT NULL CHECK (monto_total > 0),
    monto_pagado           numeric(14,2) NOT NULL DEFAULT 0 CHECK (monto_pagado >= 0),
    saldo_pendiente        numeric(14,2)
                           GENERATED ALWAYS AS (monto_total - monto_pagado) STORED,
    fecha_vencimiento      date,
    estado_recepcion       text NOT NULL DEFAULT 'PENDIENTE'
                           CHECK (estado_recepcion IN (
                               'PENDIENTE', 'PARCIAL', 'COMPLETA', 'NO_APLICA'
                           )),
    referencia_comprobante text,
    notas                  text,
    deleted_at             timestamptz,
    created_at             timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT purchases_pago_no_excede_total
        CHECK (monto_pagado <= monto_total)
);

ALTER TABLE purchases
    ALTER COLUMN fecha_compra DROP DEFAULT;

ALTER TABLE purchases
    DROP CONSTRAINT IF EXISTS purchases_pago_no_excede_total;
ALTER TABLE purchases
    ADD CONSTRAINT purchases_pago_no_excede_total
    CHECK (monto_pagado <= monto_total);

CREATE INDEX IF NOT EXISTS ix_purchases_supplier
    ON purchases (supplier_id, fecha_compra DESC);
CREATE INDEX IF NOT EXISTS ix_purchases_estado
    ON purchases (estado_recepcion, fecha_compra DESC);

CREATE TABLE IF NOT EXISTS purchase_items (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    purchase_id        uuid NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
    material_id        uuid REFERENCES materials(id),
    account_id         uuid NOT NULL REFERENCES accounting_accounts(id),
    descripcion        text NOT NULL,
    cantidad_comprada  numeric(14,4) NOT NULL CHECK (cantidad_comprada > 0),
    cantidad_recibida  numeric(14,4) NOT NULL DEFAULT 0 CHECK (cantidad_recibida >= 0),
    costo_unitario     numeric(14,4) NOT NULL CHECK (costo_unitario >= 0),
    subtotal_item      numeric(14,2) NOT NULL CHECK (subtotal_item >= 0),
    CONSTRAINT purchase_items_subtotal_coherente
        CHECK (subtotal_item = round(cantidad_comprada * costo_unitario, 2))
);

ALTER TABLE purchase_items
    DROP CONSTRAINT IF EXISTS purchase_items_subtotal_coherente;
ALTER TABLE purchase_items
    ADD CONSTRAINT purchase_items_subtotal_coherente
    CHECK (subtotal_item = round(cantidad_comprada * costo_unitario, 2));

CREATE INDEX IF NOT EXISTS ix_purchase_items_purchase
    ON purchase_items (purchase_id);

CREATE TABLE IF NOT EXISTS goods_receipts (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    purchase_item_id      uuid NOT NULL REFERENCES purchase_items(id),
    inventory_movement_id bigint REFERENCES inventory_movements(id),
    fecha_recepcion       timestamptz NOT NULL DEFAULT now(),
    cantidad_recibida     numeric(14,4) NOT NULL CHECK (cantidad_recibida > 0),
    recibido_por          text NOT NULL,
    guia_remision         text
);

CREATE TABLE IF NOT EXISTS supplier_payments (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_id uuid NOT NULL REFERENCES suppliers(id),
    purchase_id uuid REFERENCES purchases(id),
    fecha       date NOT NULL,
    metodo      text NOT NULL CHECK (metodo IN ('EFECTIVO', 'TRANSFERENCIA')),
    bolsa       text NOT NULL CHECK (bolsa IN ('CAJA_DIARIA', 'BANCO_GERENCIA')),
    monto       numeric(14,2) NOT NULL CHECK (monto > 0),
    referencia  text,
    deleted_at  timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE supplier_payments
    ALTER COLUMN fecha DROP DEFAULT;

CREATE INDEX IF NOT EXISTS ix_supplier_payments_supplier
    ON supplier_payments (supplier_id, fecha DESC);
CREATE INDEX IF NOT EXISTS ix_supplier_payments_purchase
    ON supplier_payments (purchase_id);

-- ---------------------------------------------------------------------
-- 5. Activos fijos, depreciacion y pasivos bancarios
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fixed_assets (
    id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo                   text NOT NULL UNIQUE,
    nombre                   text NOT NULL,
    categoria                text NOT NULL
                             CHECK (categoria IN (
                                 'VEHICULO_PESADO', 'MAQUINARIA_PLANTA',
                                 'EQUIPO_OFICINA', 'TERRENO_INFRAESTRUCTURA'
                             )),
    fecha_adquisicion        date NOT NULL,
    fecha_inicio_depreciacion date NOT NULL,
    costo_historico          numeric(14,2) NOT NULL CHECK (costo_historico > 0),
    valor_residual           numeric(14,2) NOT NULL DEFAULT 0 CHECK (valor_residual >= 0),
    vida_util_meses          integer NOT NULL CHECK (vida_util_meses > 0),
    depreciacion_acumulada   numeric(14,2) NOT NULL DEFAULT 0 CHECK (depreciacion_acumulada >= 0),
    estado                   text NOT NULL DEFAULT 'ACTIVO'
                             CHECK (estado IN (
                                 'ACTIVO', 'DEPRECIADO_TOTAL', 'DADO_DE_BAJA'
                             )),
    deleted_at               timestamptz,
    created_at               timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fixed_assets_residual_no_excede_costo
        CHECK (valor_residual <= costo_historico),
    CONSTRAINT fixed_assets_depreciacion_no_excede_base
        CHECK (depreciacion_acumulada <= costo_historico - valor_residual)
);

ALTER TABLE fixed_assets
    ALTER COLUMN fecha_adquisicion DROP DEFAULT;
ALTER TABLE fixed_assets
    ALTER COLUMN fecha_inicio_depreciacion DROP DEFAULT;

ALTER TABLE fixed_assets
    DROP CONSTRAINT IF EXISTS fixed_assets_residual_no_excede_costo;
ALTER TABLE fixed_assets
    ADD CONSTRAINT fixed_assets_residual_no_excede_costo
    CHECK (valor_residual <= costo_historico);
ALTER TABLE fixed_assets
    DROP CONSTRAINT IF EXISTS fixed_assets_depreciacion_no_excede_base;
ALTER TABLE fixed_assets
    ADD CONSTRAINT fixed_assets_depreciacion_no_excede_base
    CHECK (depreciacion_acumulada <= costo_historico - valor_residual);

CREATE TABLE IF NOT EXISTS depreciation_runs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id            uuid NOT NULL REFERENCES fixed_assets(id),
    periodo_ym          text NOT NULL CHECK (periodo_ym ~ '^[0-9]{4}-[0-9]{2}$'),
    cuota_depreciada    numeric(14,2) NOT NULL CHECK (cuota_depreciada >= 0),
    transaction_group_id uuid NOT NULL,
    executed_by         text NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (asset_id, periodo_ym)
);

CREATE TABLE IF NOT EXISTS financial_liabilities (
    id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entidad_financiera        text NOT NULL,
    numero_operacion          text NOT NULL,
    fecha_desembolso          date NOT NULL,
    monto_original            numeric(14,2) NOT NULL CHECK (monto_original > 0),
    saldo_capital_actual      numeric(14,2) NOT NULL CHECK (saldo_capital_actual >= 0),
    tasa_interes_anual_pct    numeric(6,2) NOT NULL CHECK (tasa_interes_anual_pct >= 0),
    cuota_mensual_referencial numeric(14,2) NOT NULL CHECK (cuota_mensual_referencial >= 0),
    plazo_restante_meses      integer NOT NULL CHECK (plazo_restante_meses >= 0),
    deleted_at                timestamptz,
    created_at                timestamptz NOT NULL DEFAULT now(),
    UNIQUE (entidad_financiera, numero_operacion)
);

ALTER TABLE financial_liabilities
    ALTER COLUMN fecha_desembolso DROP DEFAULT;

CREATE TABLE IF NOT EXISTS loan_payments (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    liability_id            uuid NOT NULL REFERENCES financial_liabilities(id),
    fecha                   date NOT NULL,
    bolsa                   text NOT NULL DEFAULT 'BANCO_GERENCIA'
                            CHECK (bolsa IN ('CAJA_DIARIA', 'BANCO_GERENCIA')),
    monto_capital           numeric(14,2) NOT NULL CHECK (monto_capital >= 0),
    monto_interes           numeric(14,2) NOT NULL CHECK (monto_interes >= 0),
    monto_total             numeric(14,2)
                            GENERATED ALWAYS AS (monto_capital + monto_interes) STORED,
    saldo_restante_snapshot numeric(14,2) NOT NULL CHECK (saldo_restante_snapshot >= 0),
    referencia              text,
    transaction_group_id    uuid NOT NULL,
    created_at              timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT loan_payments_monto_positivo
        CHECK (monto_capital + monto_interes > 0)
);

ALTER TABLE loan_payments
    ALTER COLUMN fecha DROP DEFAULT;

ALTER TABLE loan_payments
    DROP CONSTRAINT IF EXISTS loan_payments_monto_positivo;
ALTER TABLE loan_payments
    ADD CONSTRAINT loan_payments_monto_positivo
    CHECK (monto_capital + monto_interes > 0);

-- ---------------------------------------------------------------------
-- 6. Libro mayor inmutable de partida doble
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ledger_entries (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_group_id uuid NOT NULL,
    fecha_asiento        date NOT NULL,
    account_id           uuid NOT NULL REFERENCES accounting_accounts(id),
    debe                 numeric(14,2) NOT NULL DEFAULT 0 CHECK (debe >= 0),
    haber                numeric(14,2) NOT NULL DEFAULT 0 CHECK (haber >= 0),
    source_type          text NOT NULL,
    source_id            text,
    descripcion          text NOT NULL,
    is_reversal          boolean NOT NULL DEFAULT false,
    reverses_group_id    uuid,
    created_by_role      text NOT NULL,
    created_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ledger_entries_partida_doble
        CHECK ((debe > 0 AND haber = 0) OR (haber > 0 AND debe = 0))
);

ALTER TABLE ledger_entries
    ALTER COLUMN fecha_asiento DROP DEFAULT;
ALTER TABLE ledger_entries
    ALTER COLUMN source_id TYPE text USING source_id::text;

CREATE INDEX IF NOT EXISTS ix_ledger_group
    ON ledger_entries (transaction_group_id);
CREATE INDEX IF NOT EXISTS ix_ledger_account_fecha
    ON ledger_entries (account_id, fecha_asiento DESC);
CREATE INDEX IF NOT EXISTS ix_ledger_fecha
    ON ledger_entries (fecha_asiento DESC);

COMMENT ON COLUMN ledger_entries.source_id IS
    'TEXT para aceptar UUID (orders, payments, purchases) y bigint (inventory_movements).';

-- ---------------------------------------------------------------------
-- 7. Testigo forense y cola de aprobaciones
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_witness_log (
    id                            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    target_table                  text NOT NULL,
    target_record_id              text NOT NULL,
    action_type                   text NOT NULL
                                  CHECK (action_type IN (
                                      'CORRECTION_WITH_WITNESS',
                                      'CATEGORY_MERGE',
                                      'ORDER_CANCELLATION'
                                  )),
    valor_anterior                jsonb NOT NULL,
    valor_nuevo                   jsonb NOT NULL,
    motivo                        text NOT NULL CHECK (char_length(motivo) >= 10),
    autor_role                    text NOT NULL,
    autor_id                      text NOT NULL,
    approved_by_superadmin        text,
    reversal_transaction_group_id uuid,
    created_at                    timestamptz NOT NULL DEFAULT now()
);

-- Compatibilidad si una version previa creo la columna como uuid.
ALTER TABLE audit_witness_log
    ALTER COLUMN target_record_id TYPE text USING target_record_id::text;

COMMENT ON COLUMN audit_witness_log.target_record_id IS
    'TEXT para aceptar UUID y bigint (inventory_movements.id).';

CREATE TABLE IF NOT EXISTS approval_requests (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    original_request_id uuid NOT NULL REFERENCES processed_requests(request_id),
    requester_role      text NOT NULL,
    requester_id        text NOT NULL,
    intent              text NOT NULL,
    contract_payload    jsonb NOT NULL,
    motivo              text NOT NULL,
    status              text NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
    resolution_comment  text,
    resolved_by         text,
    resolved_at         timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE approval_requests
    ADD COLUMN IF NOT EXISTS resolution_comment text;

-- ---------------------------------------------------------------------
-- 8. Inmutabilidad del ledger y del testigo
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_ledger_entries_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'ledger_entries es inmutable: registre una reversa con is_reversal = true';
END;
$$;

DROP TRIGGER IF EXISTS trg_ledger_entries_immutable ON ledger_entries;
CREATE TRIGGER trg_ledger_entries_immutable
    BEFORE UPDATE OR DELETE ON ledger_entries
    FOR EACH ROW EXECUTE FUNCTION fn_ledger_entries_immutable();

CREATE OR REPLACE FUNCTION fn_audit_witness_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'audit_witness_log es inmutable: registre un nuevo testigo';
END;
$$;

DROP TRIGGER IF EXISTS trg_audit_witness_immutable ON audit_witness_log;
CREATE TRIGGER trg_audit_witness_immutable
    BEFORE UPDATE OR DELETE ON audit_witness_log
    FOR EACH ROW EXECUTE FUNCTION fn_audit_witness_immutable();

-- ---------------------------------------------------------------------
-- 9. Parametros tecnicos y de negocio pendientes
-- ---------------------------------------------------------------------
INSERT INTO system_settings (key, value, descripcion) VALUES
    ('finanzas.costo_inventario_metodo',
     '"PROMEDIO_PONDERADO"'::jsonb,
     'Metodo de valoracion de inventario y COGS confirmado el 2026-11-09.'),
    ('finanzas.iva_default_aplica',
     'true'::jsonb,
     'Las ventas nuevas aplican IVA por defecto. El porcentaje sale de concrete_recipes.iva_pct.'),
    ('finanzas.iva_historico_confirmado',
     'false'::jsonb,
     'Las ordenes anteriores al 2026-11-09 quedaron sin IVA (total_con_iva = total). Pendiente confirmar con Julio si se backfillean.'),
    ('finanzas.parametros_contables',
     '{
        "opening_balances_set": false,
        "participacion_trabajadores_pct": null,
        "impuesto_renta_pct": null,
        "wacc_anual_pct": null,
        "crecimiento_anual_pct": null,
        "inflacion_costos_pct": null,
        "dscr_minimo_banco": null,
        "secretaria_can_create_categories": false
      }'::jsonb,
     'Parametros contables que Julio aun no entrega. NULL = pendiente; no inventar.')
ON CONFLICT (key) DO NOTHING;

COMMENT ON TABLE ledger_entries IS
    'Libro mayor de partida doble. Solo INSERT: las correcciones se hacen con una reversa (is_reversal = true) y un asiento nuevo.';
COMMENT ON TABLE audit_witness_log IS
    'Testigo forense de correcciones. Solo INSERT; guarda valor anterior, valor nuevo y motivo.';
