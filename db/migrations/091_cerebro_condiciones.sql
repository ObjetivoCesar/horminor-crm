-- =====================================================================
-- ORMINORTH - Migracion 091: condiciones conservadas del dictado
-- Motivo: un dictado trae condiciones (plazo, entrega contra pago,
--         encargo al expediente) que no son columnas de ninguna accion.
--         Si la accion que las llevaba no se puede compilar, la condicion
--         desaparecia del borrador y el hablante perdia parte de su
--         encargo. Ahora se guardan aparte, con su cita, y siguen visibles
--         aunque no exista todavia un ejecutor para ellas.
-- =====================================================================

ALTER TABLE cerebro_borradores
    ADD COLUMN IF NOT EXISTS condiciones_json jsonb NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN cerebro_borradores.condiciones_json IS
    'Condiciones y encargos sostenidos por una cita que no se convierten en '
    'accion ejecutable. Se conservan para que no se pierda el encargo; no '
    'autorizan nada por si solas.';

-- El payload del borrador sigue siendo inmutable: las condiciones nacen con el
-- borrador y una correccion crea una version nueva. Se amplia el trigger de la
-- 085 (sin reescribirla) para que tambien proteja esta columna.
CREATE OR REPLACE FUNCTION fn_borrador_payload_immutable()
RETURNS trigger AS $$
BEGIN
    IF NEW.acciones_propuestas_json IS DISTINCT FROM OLD.acciones_propuestas_json
       OR NEW.condiciones_json IS DISTINCT FROM OLD.condiciones_json
       OR NEW.extraccion_id IS DISTINCT FROM OLD.extraccion_id
       OR NEW.borrador_padre_id IS DISTINCT FROM OLD.borrador_padre_id
       OR NEW.version IS DISTINCT FROM OLD.version
       OR NEW.creado_por IS DISTINCT FROM OLD.creado_por THEN
        RAISE EXCEPTION 'El payload del borrador es inmutable; cree una version nueva';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
