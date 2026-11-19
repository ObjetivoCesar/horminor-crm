-- =====================================================================
-- ORMINORTH - Migracion 097: trazabilidad de las citas comerciales
-- Motivo: confirmar, cancelar o reagendar una cita debe dejar constancia
--         con motivo y actor (regla 7 del nucleo comercial).
--         El evento sobrevive si la cita se elimina: cita_id queda NULL.
-- =====================================================================

CREATE TABLE IF NOT EXISTS cita_eventos (
    id          bigserial PRIMARY KEY,
    cita_id     uuid REFERENCES citas(id) ON DELETE SET NULL,
    tipo        text NOT NULL,
    detalle     jsonb NOT NULL DEFAULT '{}'::jsonb,
    actor       text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_cita_eventos_cita
    ON cita_eventos (cita_id, created_at DESC);

CREATE TRIGGER trg_cita_eventos_append_only
    BEFORE UPDATE OR DELETE ON cita_eventos
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_update_delete();
