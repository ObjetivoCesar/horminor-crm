-- =====================================================================
-- ORMINORTH - Migracion 072: cuentas bancarias y detalle por banco
-- Motivo: v6.11 convierte la cabecera de Banca en una consola por banco
--         (saldo, prestamos y movimientos). No se inventan numeros ni
--         saldos: las cuentas nacen PENDIENTES y el saldo informado es
--         NULL hasta que Gerencia lo cargue.
-- =====================================================================

CREATE TABLE IF NOT EXISTS bank_accounts (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                  text NOT NULL UNIQUE,
    nombre                text NOT NULL,
    tipo_cuenta           text NOT NULL DEFAULT 'CORRIENTE'
                          CHECK (tipo_cuenta IN ('CORRIENTE', 'AHORRO')),
    numero_cuenta         text,
    titular               text,
    moneda                text NOT NULL DEFAULT 'USD',
    accounting_account_id uuid UNIQUE REFERENCES accounting_accounts(id) ON DELETE SET NULL,
    saldo_informado       numeric(14, 2),
    saldo_informado_at    timestamptz,
    estado                text NOT NULL DEFAULT 'PENDIENTE'
                          CHECK (estado IN ('ACTIVA', 'PENDIENTE', 'CERRADA')),
    notas                 text,
    metadata              jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE bank_accounts IS
    'Catalogo de cuentas bancarias. El saldo contable sale del libro mayor; saldo_informado es la foto que carga Gerencia.';

INSERT INTO bank_accounts (slug, nombre, tipo_cuenta, estado)
VALUES
    ('pichincha', 'Banco Pichincha', 'CORRIENTE', 'PENDIENTE'),
    ('guayaquil', 'Banco Guayaquil', 'CORRIENTE', 'PENDIENTE'),
    ('internacional', 'Banco Internacional', 'CORRIENTE', 'PENDIENTE')
ON CONFLICT (slug) DO NOTHING;

-- Una cuenta contable hija por banco, colgada de 1102 (Bancos y Cuentas
-- Gerencia). Asi el balance y los movimientos tienen un lugar real donde
-- vivir y no se mezclan entre bancos.
INSERT INTO accounting_accounts (
    code, slug, name, account_type, normal_balance, parent_group,
    default_bolsa, requires_voucher, is_system_locked, visible_en_ventanilla,
    created_by
)
VALUES
    ('1102.01', 'banco_pichincha_cta', 'Banco Pichincha', 'ASSET', 'DEBIT',
     'ACTIVO_CORRIENTE', 'BANCO_GERENCIA', false, false, false, 'MIGRATION_072'),
    ('1102.02', 'banco_guayaquil_cta', 'Banco Guayaquil', 'ASSET', 'DEBIT',
     'ACTIVO_CORRIENTE', 'BANCO_GERENCIA', false, false, false, 'MIGRATION_072'),
    ('1102.03', 'banco_internacional_cta', 'Banco Internacional', 'ASSET', 'DEBIT',
     'ACTIVO_CORRIENTE', 'BANCO_GERENCIA', false, false, false, 'MIGRATION_072')
ON CONFLICT (code) DO NOTHING;

UPDATE bank_accounts b
   SET accounting_account_id = a.id
  FROM accounting_accounts a
 WHERE a.code = CASE b.slug
                    WHEN 'pichincha' THEN '1102.01'
                    WHEN 'guayaquil' THEN '1102.02'
                    WHEN 'internacional' THEN '1102.03'
                END
   AND b.accounting_account_id IS NULL;

-- Copia el numero enmascarado que ya existe en empresa.bot_publico, sin
-- tocarlo a mano ni inventarlo. Solo aplica si la cuenta esta vacia.
UPDATE bank_accounts b
   SET numero_cuenta = datos.numero
  FROM (
      SELECT b2.slug,
             substring(cuenta FROM '#([0-9A-Za-z]+)') AS numero
        FROM bank_accounts b2
        CROSS JOIN system_settings s
        CROSS JOIN LATERAL jsonb_array_elements_text(s.value -> 'bank_accounts') AS cuenta
       WHERE s.key = 'empresa.bot_publico'
         AND lower(cuenta) LIKE '%' || b2.slug || '%'
  ) datos
 WHERE b.slug = datos.slug
   AND b.numero_cuenta IS NULL
   AND datos.numero IS NOT NULL;

ALTER TABLE financial_liabilities
    ADD COLUMN IF NOT EXISTS bank_account_id uuid
    REFERENCES bank_accounts(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_financial_liabilities_banco
    ON financial_liabilities (bank_account_id)
    WHERE deleted_at IS NULL;
