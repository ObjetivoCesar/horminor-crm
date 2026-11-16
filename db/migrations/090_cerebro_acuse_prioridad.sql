-- =====================================================================
-- ORMINORTH - Migracion 090: acuse de recibo, prioridad y retiro de
--                        vocabulario aprendido
-- Motivo: una notificacion mostrada no es una notificacion leida. La
--         tarea interna necesita tres momentos distintos (avisada, vista,
--         acusada) ademas de la resolucion; prioridad y plazo para saber
--         que atender primero; y una forma de retirar una asociacion
--         aprendida que resulto equivocada, sin borrar el pasado.
-- =====================================================================

ALTER TABLE cerebro_tareas_internas
    ADD COLUMN IF NOT EXISTS prioridad text NOT NULL DEFAULT 'NORMAL',
    ADD COLUMN IF NOT EXISTS plazo_en timestamptz NULL,
    ADD COLUMN IF NOT EXISTS vista_en timestamptz NULL,
    ADD COLUMN IF NOT EXISTS vista_por text NULL,
    ADD COLUMN IF NOT EXISTS acusada_en timestamptz NULL,
    ADD COLUMN IF NOT EXISTS acusada_por text NULL,
    ADD COLUMN IF NOT EXISTS escalada_en timestamptz NULL,
    ADD COLUMN IF NOT EXISTS escalada_por text NULL;

ALTER TABLE cerebro_tareas_internas
    DROP CONSTRAINT IF EXISTS chk_tarea_interna_prioridad;

ALTER TABLE cerebro_tareas_internas
    ADD CONSTRAINT chk_tarea_interna_prioridad CHECK (
        prioridad IN ('NORMAL', 'URGENTE')
    );

COMMENT ON COLUMN cerebro_tareas_internas.prioridad IS
    'NORMAL o URGENTE. No la decide el modelo: la marca el dictado y el plazo.';
COMMENT ON COLUMN cerebro_tareas_internas.plazo_en IS
    'Fecha limite para atender la tarea. NULL = sin plazo explicito (politica por prioridad).';
COMMENT ON COLUMN cerebro_tareas_internas.vista_en IS
    'Cuando una persona abrio el detalle de la tarea. No es acuse de recibo.';
COMMENT ON COLUMN cerebro_tareas_internas.acusada_en IS
    'Cuando una persona confirmo que recibio el encargo. No significa que lo hizo.';
COMMENT ON COLUMN cerebro_tareas_internas.escalada_en IS
    'Cuando un supervisor decidio escalar una tarea vencida sin atencion.';

CREATE INDEX IF NOT EXISTS idx_cerebro_tareas_internas_plazo
    ON cerebro_tareas_internas (plazo_en)
    WHERE resuelta_en IS NULL;

-- Retiro de una asociacion aprendida («Díaz Sur» -> «Dualsur») cuando se
-- comprueba que estaba equivocada. Es una fila nueva: la correccion original
-- no se borra, solo deja de usarse como pista.
CREATE TABLE IF NOT EXISTS cerebro_vocabulario_retiros (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    clave text NOT NULL,
    valor_anterior text NOT NULL,
    valor_nuevo text NOT NULL,
    motivo text NOT NULL,
    retirado_por text NOT NULL,
    rol_base text NOT NULL,
    creado_en timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cerebro_vocabulario_retiros
    ON cerebro_vocabulario_retiros (clave, valor_anterior, valor_nuevo);

COMMENT ON TABLE cerebro_vocabulario_retiros IS
    'Append-only. Retira una asociacion del vocabulario aprendido sin borrar la correccion que la origino.';

CREATE OR REPLACE FUNCTION fn_cerebro_vocabulario_retiros_immutable()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'cerebro_vocabulario_retiros es append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cerebro_vocabulario_retiros_immutable
    ON cerebro_vocabulario_retiros;
CREATE TRIGGER trg_cerebro_vocabulario_retiros_immutable
    BEFORE UPDATE OR DELETE ON cerebro_vocabulario_retiros
    FOR EACH ROW EXECUTE FUNCTION fn_cerebro_vocabulario_retiros_immutable();

-- El vocabulario que se le pasa al modelo excluye los pares retirados.
CREATE OR REPLACE VIEW v_cerebro_vocabulario AS
SELECT c.clave,
       c.valor_anterior,
       c.valor_nuevo,
       count(*) AS veces,
       max(c.creado_en) AS ultima_vez
  FROM cerebro_correcciones c
 WHERE c.valor_anterior IS NOT NULL
   AND c.valor_anterior <> c.valor_nuevo
   AND NOT EXISTS (
       SELECT 1
         FROM cerebro_vocabulario_retiros r
        WHERE r.clave = c.clave
          AND r.valor_anterior = c.valor_anterior
          AND r.valor_nuevo = c.valor_nuevo
   )
 GROUP BY c.clave, c.valor_anterior, c.valor_nuevo
 ORDER BY veces DESC, ultima_vez DESC;

COMMENT ON VIEW v_cerebro_vocabulario IS
    'Pares de correccion agrupados, sin los retirados: insumo del prompt y del informe.';

DROP VIEW IF EXISTS v_cerebro_tareas_internas;

CREATE VIEW v_cerebro_tareas_internas AS
SELECT t.id,
       t.instruccion,
       t.asignado_rol,
       t.asignado_a,
       t.asignado_a_id,
       t.origen,
       t.extraccion_id,
       t.borrador_id,
       t.estado,
       t.resolucion,
       t.resolucion_nota,
       t.prioridad,
       t.plazo_en,
       t.notificada_en,
       t.vista_en,
       t.acusada_en,
       t.escalada_en,
       t.resuelta_en,
       t.registrada_en,
       t.creado_por,
       t.metadatos,
       CASE
           WHEN t.resuelta_en IS NOT NULL THEN
               round(extract(epoch FROM (t.resuelta_en - t.notificada_en)) / 60)::integer
           ELSE NULL
       END AS minutos_hasta_resolucion,
       CASE
           WHEN t.registrada_en IS NOT NULL THEN
               round(extract(epoch FROM (t.registrada_en - t.notificada_en)) / 60)::integer
           ELSE NULL
       END AS minutos_hasta_registro,
       CASE
           WHEN t.resuelta_en IS NULL THEN
               round(extract(epoch FROM (now() - t.notificada_en)) / 60)::integer
           ELSE NULL
       END AS minutos_abierta,
       (t.resuelta_en IS NULL AND t.plazo_en IS NOT NULL AND t.plazo_en < now())
           AS vencida,
       (t.acusada_en IS NULL) AS sin_acuse,
       (t.acusada_en IS NULL AND t.plazo_en IS NOT NULL AND t.plazo_en < now())
           AS requiere_escalamiento
  FROM cerebro_tareas_internas t;

COMMENT ON VIEW v_cerebro_tareas_internas IS
    'Tareas internas con relojes, vencimiento y acuse. vencida = paso el plazo sin resolverse; requiere_escalamiento = vencida y sin acuse.';
