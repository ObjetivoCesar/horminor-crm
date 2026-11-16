-- =====================================================================
-- ORMINORTH - Migracion 092: encargos independientes dentro de un dictado
-- Motivo: un audio con tres instrucciones ("primero... segundo... tercero")
--         se compilaba como un solo asunto: los hechos de dos encargos se
--         pisaban y el texto completo contaminaba la lectura de cada uno.
--         Ahora cada encargo tiene su estado, sus acciones y su decision.
--         Cancelar un encargo no cancela el dictado entero.
-- =====================================================================

ALTER TABLE cerebro_borradores
    ADD COLUMN IF NOT EXISTS encargos_json jsonb NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN cerebro_borradores.encargos_json IS
    'Resumen por encargo (texto, estado, acciones y preguntas). Nace con el '
    'borrador; una correccion crea una version nueva.';

ALTER TABLE cerebro_ejecuciones
    ADD COLUMN IF NOT EXISTS encargo integer NOT NULL DEFAULT 1;
ALTER TABLE cerebro_ejecuciones
    DROP CONSTRAINT IF EXISTS chk_ejecucion_encargo;
ALTER TABLE cerebro_ejecuciones
    ADD CONSTRAINT chk_ejecucion_encargo CHECK (encargo >= 1);

COMMENT ON COLUMN cerebro_ejecuciones.encargo IS
    'Encargo del borrador al que pertenece la ejecucion. Permite confirmar y '
    'cancelar por asunto, no por dictado completo.';

ALTER TABLE cerebro_correcciones
    ADD COLUMN IF NOT EXISTS encargo integer NOT NULL DEFAULT 1;

COMMENT ON COLUMN cerebro_correcciones.encargo IS
    'Encargo corregido. Dos asuntos pueden compartir clave (dos tarea.mensaje): '
    'la correccion alcanza solo al indicado.';

-- Decisiones sobre un encargo: hoy solo la cancelacion. Append-only: una
-- cancelacion no se borra; si se quiere rehacer, se dicta de nuevo.
CREATE TABLE IF NOT EXISTS cerebro_encargos_decisiones (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    borrador_id uuid NOT NULL REFERENCES cerebro_borradores(id),
    encargo integer NOT NULL CHECK (encargo >= 1),
    decision text NOT NULL CHECK (decision IN ('CANCELADO')),
    motivo text NOT NULL,
    decidido_por text NOT NULL,
    rol_base text NOT NULL,
    creado_en timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cerebro_encargo_cancelado
    ON cerebro_encargos_decisiones (borrador_id, encargo, decision);

CREATE INDEX IF NOT EXISTS idx_cerebro_encargos_decisiones
    ON cerebro_encargos_decisiones (borrador_id, creado_en DESC);

CREATE OR REPLACE FUNCTION fn_decision_encargo_append_only()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Las decisiones de encargo son append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cerebro_encargos_decisiones ON cerebro_encargos_decisiones;
CREATE TRIGGER trg_cerebro_encargos_decisiones
    BEFORE UPDATE OR DELETE ON cerebro_encargos_decisiones
    FOR EACH ROW EXECUTE FUNCTION fn_decision_encargo_append_only();

-- El trigger de payload del borrador tambien protege el resumen por encargo.
CREATE OR REPLACE FUNCTION fn_borrador_payload_immutable()
RETURNS trigger AS $$
BEGIN
    IF NEW.acciones_propuestas_json IS DISTINCT FROM OLD.acciones_propuestas_json
       OR NEW.condiciones_json IS DISTINCT FROM OLD.condiciones_json
       OR NEW.encargos_json IS DISTINCT FROM OLD.encargos_json
       OR NEW.extraccion_id IS DISTINCT FROM OLD.extraccion_id
       OR NEW.borrador_padre_id IS DISTINCT FROM OLD.borrador_padre_id
       OR NEW.version IS DISTINCT FROM OLD.version
       OR NEW.creado_por IS DISTINCT FROM OLD.creado_por THEN
        RAISE EXCEPTION 'El payload del borrador es inmutable; cree una version nueva';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
