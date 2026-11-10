-- =====================================================================
-- ORMINORTH - Migracion 068: agenda configurable y usuarios con ACL
-- Motivo: v6.2 agrega horarios de planta editables en caliente, topes
--         de caja chica/compra y perfiles de panel con checklist de
--         modulos. No se borra ninguna cuenta ni se toca data real.
-- =====================================================================

-- ---------------------------------------------------------------------------
-- 1. Horarios de planta y reglas del componente de agenda
-- ---------------------------------------------------------------------------
INSERT INTO system_settings (key, value, descripcion)
VALUES (
    'agenda.parametros',
    '{
        "hora_apertura": "07:00",
        "hora_cierre": "18:00",
        "duracion_entrega_default_min": 90,
        "intervalo_slot_min": 30,
        "dias_laborables": ["LUN", "MAR", "MIE", "JUE", "VIE", "SAB"]
    }'::jsonb,
    'Horarios y reglas del componente HorminorAgenda. Editable en Superadmin.'
)
ON CONFLICT (key) DO UPDATE
   SET value = system_settings.value || EXCLUDED.value,
       actualizado_at = now();

-- ---------------------------------------------------------------------------
-- 2. Topes de caja chica y compra en efectivo
-- ---------------------------------------------------------------------------
INSERT INTO system_settings (key, value, descripcion)
VALUES (
    'secretaria.pagos',
    '{
        "caja_chica_max_monto_usd": "100.00",
        "compras_efectivo_max_monto_usd": "300.00",
        "fondo_base_caja_chica_usd": "200.00"
    }'::jsonb,
    'Reglas de la ventanilla de pagos, tope de caja chica y compras en efectivo'
)
ON CONFLICT (key) DO UPDATE
   SET value = system_settings.value || EXCLUDED.value,
       actualizado_at = now();

-- ---------------------------------------------------------------------------
-- 3. Usuarios/perfiles del panel con checklist de modulos
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS panel_users_acl (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre VARCHAR(120) NOT NULL,
    rol_base VARCHAR(40) NOT NULL
        CHECK (rol_base IN (
            'SUPERADMIN', 'SECRETARIA', 'CONTADORA', 'BODEGA', 'CHOFER',
            'VENDEDOR', 'AUDITOR_EXTERNO'
        )),
    telefono_whatsapp VARCHAR(30),
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    modulos_permitidos JSONB NOT NULL DEFAULT '{
        "dashboard_gerencial": false,
        "secretaria_ventanilla": false,
        "secretaria_cobros_gastos": false,
        "secretaria_cierre_caja": false,
        "agenda_despachos": false,
        "compras_materiales": false,
        "planta_kardex": false,
        "clientes_cartera": false,
        "finanzas_balance_auditoria": false,
        "superadmin_config": false
    }'::jsonb,
    modo_acceso VARCHAR(20) NOT NULL DEFAULT 'EDICION'
        CHECK (modo_acceso IN ('SOLO_LECTURA', 'EDICION')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_panel_users_acl_nombre
    ON panel_users_acl (lower(nombre))
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_panel_users_acl_activo
    ON panel_users_acl (activo)
    WHERE deleted_at IS NULL;

-- Semilla de perfiles tipo. Son provisionales y editables desde Superadmin.
INSERT INTO panel_users_acl
    (nombre, rol_base, telefono_whatsapp, activo, modulos_permitidos, modo_acceso)
SELECT
    'Julio Villavicencio',
    'SUPERADMIN',
    NULL,
    TRUE,
    '{
        "dashboard_gerencial": true,
        "secretaria_ventanilla": true,
        "secretaria_cobros_gastos": true,
        "secretaria_cierre_caja": true,
        "agenda_despachos": true,
        "compras_materiales": true,
        "planta_kardex": true,
        "clientes_cartera": true,
        "finanzas_balance_auditoria": true,
        "superadmin_config": true
    }'::jsonb,
    'EDICION'
WHERE NOT EXISTS (
    SELECT 1 FROM panel_users_acl
     WHERE lower(nombre) = lower('Julio Villavicencio') AND deleted_at IS NULL
);

INSERT INTO panel_users_acl
    (nombre, rol_base, telefono_whatsapp, activo, modulos_permitidos, modo_acceso)
SELECT
    'Secretaria Ventanilla',
    'SECRETARIA',
    NULL,
    TRUE,
    '{
        "dashboard_gerencial": false,
        "secretaria_ventanilla": true,
        "secretaria_cobros_gastos": true,
        "secretaria_cierre_caja": true,
        "agenda_despachos": true,
        "compras_materiales": true,
        "planta_kardex": false,
        "clientes_cartera": true,
        "finanzas_balance_auditoria": false,
        "superadmin_config": false
    }'::jsonb,
    'EDICION'
WHERE NOT EXISTS (
    SELECT 1 FROM panel_users_acl
     WHERE lower(nombre) = lower('Secretaria Ventanilla') AND deleted_at IS NULL
);

INSERT INTO panel_users_acl
    (nombre, rol_base, telefono_whatsapp, activo, modulos_permitidos, modo_acceso)
SELECT
    'Auditor Externo',
    'AUDITOR_EXTERNO',
    NULL,
    TRUE,
    '{
        "dashboard_gerencial": true,
        "secretaria_ventanilla": false,
        "secretaria_cobros_gastos": false,
        "secretaria_cierre_caja": true,
        "agenda_despachos": false,
        "compras_materiales": false,
        "planta_kardex": false,
        "clientes_cartera": true,
        "finanzas_balance_auditoria": true,
        "superadmin_config": false
    }'::jsonb,
    'SOLO_LECTURA'
WHERE NOT EXISTS (
    SELECT 1 FROM panel_users_acl
     WHERE lower(nombre) = lower('Auditor Externo') AND deleted_at IS NULL
);

INSERT INTO panel_users_acl
    (nombre, rol_base, telefono_whatsapp, activo, modulos_permitidos, modo_acceso)
SELECT
    'Vendedor de Campo',
    'VENDEDOR',
    NULL,
    TRUE,
    '{
        "dashboard_gerencial": false,
        "secretaria_ventanilla": true,
        "secretaria_cobros_gastos": false,
        "secretaria_cierre_caja": false,
        "agenda_despachos": true,
        "compras_materiales": false,
        "planta_kardex": false,
        "clientes_cartera": true,
        "finanzas_balance_auditoria": false,
        "superadmin_config": false
    }'::jsonb,
    'EDICION'
WHERE NOT EXISTS (
    SELECT 1 FROM panel_users_acl
     WHERE lower(nombre) = lower('Vendedor de Campo') AND deleted_at IS NULL
);

INSERT INTO panel_users_acl
    (nombre, rol_base, telefono_whatsapp, activo, modulos_permitidos, modo_acceso)
SELECT
    'Jefe de Planta / Bodega',
    'BODEGA',
    NULL,
    TRUE,
    '{
        "dashboard_gerencial": false,
        "secretaria_ventanilla": false,
        "secretaria_cobros_gastos": false,
        "secretaria_cierre_caja": false,
        "agenda_despachos": true,
        "compras_materiales": true,
        "planta_kardex": true,
        "clientes_cartera": false,
        "finanzas_balance_auditoria": false,
        "superadmin_config": false
    }'::jsonb,
    'EDICION'
WHERE NOT EXISTS (
    SELECT 1 FROM panel_users_acl
     WHERE lower(nombre) = lower('Jefe de Planta / Bodega') AND deleted_at IS NULL
);
