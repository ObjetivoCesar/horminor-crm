-- =====================================================================
-- ORMINORTH - Migracion 087: correcciones humanas del Cerebro
-- Motivo: el dictado es la primera lectura, no la verdad. Julio o la
--         secretaria corrigen lo que el sistema entendio («Diaz Sur» ->
--         «Dualsur») antes de confirmar. Esa correccion es un dato nuevo,
--         no una reescritura: se guarda como fila propia y sirve de
--         vocabulario para futuras extracciones y para el informe tecnico.
-- =====================================================================

CREATE TABLE cerebro_correcciones (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    borrador_id uuid NOT NULL REFERENCES cerebro_borradores(id),
    borrador_nuevo_id uuid NULL REFERENCES cerebro_borradores(id),
    extraccion_id uuid NOT NULL REFERENCES cerebro_extracciones(id),
    clave text NOT NULL,
    valor_anterior text NULL,
    valor_nuevo text NOT NULL,
    cita text NULL,
    corregido_por text NOT NULL,
    rol_base text NOT NULL,
    creado_en timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_correccion_distinta CHECK (
        valor_anterior IS NULL OR valor_anterior <> valor_nuevo
    )
);

CREATE INDEX idx_cerebro_correcciones_borrador
    ON cerebro_correcciones (borrador_id, creado_en);
CREATE INDEX idx_cerebro_correcciones_clave
    ON cerebro_correcciones (clave, creado_en DESC);

COMMENT ON TABLE cerebro_correcciones IS
    'Append-only. Cada fila es una persona corrigiendo un hecho del Cerebro. El borrador anterior no se reescribe: se marca SUPERADO_POR_CORRECCION.';

COMMENT ON COLUMN cerebro_correcciones.cita IS
    'Cita del hecho original (lo que dijo el audio segun el STT), no el valor corregido.';

CREATE OR REPLACE FUNCTION fn_cerebro_correcciones_immutable()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'cerebro_correcciones es append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_cerebro_correcciones_immutable
    BEFORE UPDATE OR DELETE ON cerebro_correcciones
    FOR EACH ROW EXECUTE FUNCTION fn_cerebro_correcciones_immutable();

-- Vista de vocabulario: pares «lo que se transcribio» -> «lo que quiso decir».
-- La usan el extractor (como pista) y el informe semanal. No es una tabla de
-- verdad: si el par se repite, es que el STT falla siempre igual.
CREATE OR REPLACE VIEW v_cerebro_vocabulario AS
SELECT clave,
       valor_anterior,
       valor_nuevo,
       count(*) AS veces,
       max(creado_en) AS ultima_vez
  FROM cerebro_correcciones
 WHERE valor_anterior IS NOT NULL
   AND valor_anterior <> valor_nuevo
 GROUP BY clave, valor_anterior, valor_nuevo
 ORDER BY veces DESC, ultima_vez DESC;

COMMENT ON VIEW v_cerebro_vocabulario IS
    'Pares de correccion agrupados: insumo del prompt y del informe de errores a Abelito.';
