-- 067 - Afinamiento operativo v6.0
-- Ventanilla curada, anticipos de sueldo, proveedor comodin, tope de caja
-- chica y motor real de agendamiento de entregas/mixers.
--
-- Reglas:
--   * No se borra ninguna cuenta contable: solo se marca que cuenta es
--     visible en la ventanilla diaria.
--   * El proveedor comodin NO lleva RUC inventado: queda NULL y marcado
--     "(POR CLASIFICAR)"; Julio/Bodega lo reemplazan por el real.
--   * El tope de caja chica es un parametro editable, no un valor en codigo.

-- ---------------------------------------------------------------------------
-- 1. Visibilidad de cuentas en la ventanilla de Secretaria
-- ---------------------------------------------------------------------------
ALTER TABLE accounting_accounts
    ADD COLUMN IF NOT EXISTS visible_en_ventanilla BOOLEAN NOT NULL DEFAULT false;

-- Solo las cuentas que se pagan de verdad en ventanilla.
UPDATE accounting_accounts
   SET visible_en_ventanilla = true
 WHERE code IN ('5401', '5301', '5201');

-- 1105 ya esta ocupada por IVA Credito Tributario. El anticipo de sueldo
-- usa 1106 y se registra como ACTIVO (no es un gasto: es un anticipo que
-- luego se cruza contra la nomina).
INSERT INTO accounting_accounts (
    code, slug, name, account_type, normal_balance, parent_group,
    default_bolsa, requires_voucher, is_system_locked, visible_en_ventanilla
) VALUES (
    '1106', 'anticipos_sueldo_personal',
    'Anticipos de Sueldo y Quincenas al Personal',
    'ASSET', 'DEBIT', 'ACTIVO_CORRIENTE',
    'CAJA_DIARIA', true, false, true
)
ON CONFLICT (code) DO UPDATE
   SET visible_en_ventanilla = true;

-- ---------------------------------------------------------------------------
-- 2. Tope de caja chica configurable (Superadmin)
-- ---------------------------------------------------------------------------
INSERT INTO system_settings (key, value, descripcion)
VALUES (
    'secretaria.pagos',
    '{"monto_minimo":"0.01","abono_parcial":true,"validar_saldo":true,"permitir_anticipo":true,"caja_chica_max_monto_usd":"100.00","exigir_autorizacion_exceso":true}'::jsonb,
    'Reglas de la ventanilla de pagos y tope de caja chica'
)
ON CONFLICT (key) DO UPDATE
   SET value = system_settings.value || EXCLUDED.value,
       actualizado_at = now();

-- ---------------------------------------------------------------------------
-- 3. Proveedor comodin para destrabar compras (sin RUC inventado)
-- ---------------------------------------------------------------------------
INSERT INTO suppliers (nombre, identificacion, telefono, activo)
SELECT 'PROVEEDOR GENERAL (POR CLASIFICAR)', NULL, NULL, true
 WHERE NOT EXISTS (
    SELECT 1 FROM suppliers
     WHERE nombre = 'PROVEEDOR GENERAL (POR CLASIFICAR)'
 );

-- ---------------------------------------------------------------------------
-- 4. Motor real de agendamiento de entregas / ocupacion de mixers
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dispatch_schedule (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID REFERENCES orders(id),
    cliente_id UUID NOT NULL REFERENCES clients(id),
    planta_id UUID REFERENCES plants(id),
    mixer_codigo TEXT,
    chofer_nombre TEXT,
    receta_codigo TEXT,
    volumen_m3 NUMERIC(12,2) NOT NULL CHECK (volumen_m3 > 0),
    fecha_entrega DATE NOT NULL,
    hora_inicio TIME NOT NULL,
    duracion_estimada_min INTEGER NOT NULL DEFAULT 90
        CHECK (duracion_estimada_min >= 30),
    hora_fin_estimada TIME GENERATED ALWAYS AS (
        hora_inicio + (duracion_estimada_min * INTERVAL '1 minute')
    ) STORED,
    direccion_obra TEXT NOT NULL,
    contacto_obra_telefono TEXT,
    estado TEXT NOT NULL DEFAULT 'PROGRAMADO'
        CHECK (estado IN (
            'RESERVA_CAMPO', 'PROGRAMADO', 'EN_PLANTA', 'EN_RUTA',
            'COMPLETADO', 'REAGENDADO', 'CANCELADO'
        )),
    motivo_reagendamiento TEXT,
    reagendado_de_id UUID REFERENCES dispatch_schedule(id),
    creado_por_rol TEXT NOT NULL DEFAULT 'SECRETARIA',
    creado_por_id TEXT NOT NULL DEFAULT 'panel',
    notificar_whatsapp BOOLEAN NOT NULL DEFAULT true,
    ultimo_aviso_whatsapp_at TIMESTAMPTZ,
    notas TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_dispatch_schedule_fecha_estado
    ON dispatch_schedule (fecha_entrega, estado)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_dispatch_schedule_mixer_ocupacion
    ON dispatch_schedule (fecha_entrega, mixer_codigo, hora_inicio)
    WHERE deleted_at IS NULL
      AND estado NOT IN ('CANCELADO', 'REAGENDADO');

CREATE INDEX IF NOT EXISTS idx_dispatch_schedule_cliente
    ON dispatch_schedule (cliente_id)
    WHERE deleted_at IS NULL;
