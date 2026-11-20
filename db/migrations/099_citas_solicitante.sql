-- =====================================================================
-- ORMINORTH - Migracion 099: quien solicito la cita
-- Motivo: Gato necesita corregir o cancelar la cita que acaba de crear
--         aunque se refresque el chat. El nombre visible no es identidad
--         suficiente: dos personas pueden llamarse igual. Se guarda el id
--         del perfil que la solicito, sin tocar las citas existentes.
-- =====================================================================

ALTER TABLE citas
    ADD COLUMN IF NOT EXISTS solicitada_por_id uuid NULL
        REFERENCES panel_users_acl(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_citas_solicitante
    ON citas (solicitada_por_id, created_at DESC);

COMMENT ON COLUMN citas.solicitada_por_id IS
    'Perfil del panel que solicito la cita. Sirve para que Gato encuentre la suya al corregir o cancelar; el nombre sigue en solicitada_por.';
