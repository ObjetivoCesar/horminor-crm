-- =====================================================================
-- ORMINORTH - Migracion 080: cotizaciones y cadena comercial
-- Motivo: toda venta pasa primero por cotizacion. Se agregan las tablas
--         del diseno docs/COTIZACIONES.md (v6.20) y el estado del precio.
-- Regla: ningun precio, extra ni plazo se inventa. Lo que falta va NULL.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Estado del precio en la lista oficial (Superadmin > formulas)
-- ---------------------------------------------------------------------
ALTER TABLE concrete_recipes
    ADD COLUMN IF NOT EXISTS precio_estado text NOT NULL DEFAULT 'PROVISIONAL';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'concrete_recipes_precio_estado_check'
    ) THEN
        ALTER TABLE concrete_recipes
            ADD CONSTRAINT concrete_recipes_precio_estado_check
            CHECK (precio_estado IN ('PROVISIONAL', 'OFICIAL'));
    END IF;
END $$;

COMMENT ON COLUMN concrete_recipes.precio_estado IS
    'PROVISIONAL no debe emitir fuera de SANDBOX. OFICIAL lo autoriza Julio.';

-- ---------------------------------------------------------------------
-- 2. Secuencia de numeros HORM-COT-AAAA-0001
-- ---------------------------------------------------------------------
CREATE SEQUENCE IF NOT EXISTS cotizaciones_numero_seq START 1;

-- ---------------------------------------------------------------------
-- 3. Cotizaciones
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cotizaciones (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    numero                text NOT NULL UNIQUE,
    cliente_id            uuid NOT NULL REFERENCES clients(id),
    obra_direccion        text NOT NULL,
    volumen_m3            numeric(10,2) NOT NULL CHECK (volumen_m3 > 0),
    resistencia           text REFERENCES concrete_recipes(resistencia),
    precio_m3             numeric(10,2) CHECK (precio_m3 IS NULL OR precio_m3 >= 0),
    precio_estado         text NOT NULL DEFAULT 'PROVISIONAL'
                          CHECK (precio_estado IN ('PROVISIONAL', 'OFICIAL')),
    incluye_equipo        boolean NOT NULL DEFAULT true,
    incluye_bombeo        boolean NOT NULL DEFAULT true,
    acceso_notas          text,
    forma_pago            text NOT NULL DEFAULT 'FIADO'
                          CHECK (forma_pago IN ('EFECTIVO', 'TRANSFERENCIA', 'ABONO', 'FIADO')),
    valida_hasta          date,
    estado                text NOT NULL DEFAULT 'BORRADOR'
                          CHECK (estado IN ('BORRADOR', 'ENVIADA', 'ACEPTADA', 'RECHAZADA', 'VENCIDA', 'CONVERTIDA')),
    version               integer NOT NULL DEFAULT 1 CHECK (version > 0),
    subtotal              numeric(14,2),
    iva_pct               numeric(5,2) NOT NULL DEFAULT 0 CHECK (iva_pct >= 0 AND iva_pct <= 100),
    iva_monto             numeric(14,2) NOT NULL DEFAULT 0 CHECK (iva_monto >= 0),
    total                 numeric(14,2),
    pdf_media_id          uuid REFERENCES media_assets(id),
    enviada_at            timestamptz,
    enviada_por           text,
    canal_envio           text CHECK (canal_envio IS NULL OR canal_envio IN ('WHATSAPP', 'IMPRESA', 'PANEL')),
    whatsapp_msg_id       text,
    aceptada_at           timestamptz,
    convertida_at         timestamptz,
    orden_id              uuid REFERENCES orders(id),
    contrato_id           uuid,
    origen                text NOT NULL DEFAULT 'PANEL'
                          CHECK (origen IN ('PANEL', 'GATO', 'OBRA')),
    creado_por            text,
    aprobado_por          text,
    notas                 text,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_cotizaciones_cliente ON cotizaciones (cliente_id);
CREATE INDEX IF NOT EXISTS ix_cotizaciones_estado ON cotizaciones (estado);
CREATE INDEX IF NOT EXISTS ix_cotizaciones_created ON cotizaciones (created_at DESC);

COMMENT ON TABLE cotizaciones IS
    'Documento comercial previo a la orden. No compromete produccion.';

-- ---------------------------------------------------------------------
-- 4. Extras: un solo rubro global, con o sin monto cobrable
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cotizacion_extras (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cotizacion_id  uuid NOT NULL REFERENCES cotizaciones(id) ON DELETE CASCADE,
    descripcion    text NOT NULL,
    monto          numeric(14,2) CHECK (monto IS NULL OR monto >= 0),
    cobrable       boolean NOT NULL DEFAULT false,
    nota           text,
    orden          integer NOT NULL DEFAULT 0,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_cotizacion_extras_cot ON cotizacion_extras (cotizacion_id);

COMMENT ON TABLE cotizacion_extras IS
    'Rubro global: cualquier cosa ajena a Horminor. cobrable=false es costo interno y no se imprime al cliente.';

-- ---------------------------------------------------------------------
-- 5. Versiones inmutables de la cotizacion
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cotizacion_versiones (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cotizacion_id  uuid NOT NULL REFERENCES cotizaciones(id) ON DELETE CASCADE,
    version        integer NOT NULL CHECK (version > 0),
    snapshot       jsonb NOT NULL,
    hash           text NOT NULL,
    pdf_media_id   uuid REFERENCES media_assets(id),
    es_aceptada    boolean NOT NULL DEFAULT false,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (cotizacion_id, version)
);

CREATE INDEX IF NOT EXISTS ix_cotizacion_versiones_cot ON cotizacion_versiones (cotizacion_id);

-- ---------------------------------------------------------------------
-- 6. Extras que pasan a la orden al convertir
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orden_extras (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    orden_id     uuid NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    descripcion  text NOT NULL,
    monto        numeric(14,2) NOT NULL CHECK (monto >= 0),
    cobrable     boolean NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_orden_extras_orden ON orden_extras (orden_id);

-- ---------------------------------------------------------------------
-- 7. Etiquetas del cliente (VENTA se asigna al aceptar)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cliente_etiquetas (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cliente_id  uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    etiqueta    text NOT NULL,
    origen      text NOT NULL DEFAULT 'MANUAL'
                CHECK (origen IN ('COTIZACION', 'MANUAL', 'COBRANZA')),
    origen_id   uuid,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (cliente_id, etiqueta)
);

CREATE INDEX IF NOT EXISTS ix_cliente_etiquetas_cliente ON cliente_etiquetas (cliente_id);

-- ---------------------------------------------------------------------
-- 8. Total de la orden con extras (la orden conserva su total base)
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_orden_total AS
SELECT
    o.id,
    o.numero,
    o.cliente_id,
    o.resistencia,
    o.volumen_m3,
    o.precio_m3,
    COALESCE(o.total, 0)                                        AS total_base,
    COALESCE(SUM(oe.monto) FILTER (WHERE oe.cobrable), 0)       AS total_extras,
    COALESCE(o.total, 0)
        + COALESCE(SUM(oe.monto) FILTER (WHERE oe.cobrable), 0) AS total_con_extras,
    o.estado,
    o.created_at
FROM orders o
LEFT JOIN orden_extras oe ON oe.orden_id = o.id
GROUP BY o.id, o.numero, o.cliente_id, o.resistencia, o.volumen_m3,
         o.precio_m3, o.total, o.estado, o.created_at;

-- ---------------------------------------------------------------------
-- 9. Parametros de cotizaciones
-- ---------------------------------------------------------------------
INSERT INTO system_settings (key, value, descripcion)
VALUES
    ('cotizaciones.validez_dias', '15'::jsonb,
     'Dias de validez de una cotizacion. Editable por Julio.'),
    ('cotizaciones.envio', '{"canal": "WHATSAPP", "archivar_en_cliente": true}'::jsonb,
     'Canal de envio y archivo en la carpeta del cliente.'),
    ('cotizaciones.excedente_alerta_pct', 'null'::jsonb,
     'Umbral de excedente despachado. NULL = sin umbral definido.')
ON CONFLICT (key) DO NOTHING;

-- ---------------------------------------------------------------------
-- 10. ACL: Cotizaciones arranca habilitado solo para Superadmin.
--     Los demas perfiles lo reciben cuando Superadmin los apruebe.
-- ---------------------------------------------------------------------
UPDATE panel_users_acl
   SET modulos_permitidos = modulos_permitidos
       || jsonb_build_object('cotizaciones', (rol_base = 'SUPERADMIN')),
       updated_at = now()
 WHERE deleted_at IS NULL
   AND NOT (modulos_permitidos ? 'cotizaciones');
