-- =====================================================================
-- ORMINORTH - Migracion 088: tareas internas con reloj
-- Motivo: un audio puede dar una instruccion a alguien del equipo sin
--         telefono («que revisen en secretaria como van los despachos»).
--         Eso no es un WhatsApp: es una tarea interna. El CRM deja el
--         aviso, y la persona lo resuelve o lo justifica y lo registra con
--         metadatos. Cada paso queda con su hora para poder medir cuanto
--         tardo, sin que nadie tenga que declararlo.
-- =====================================================================

CREATE TABLE cerebro_tareas_internas (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    clave_externa text NOT NULL,
    instruccion text NOT NULL,
    asignado_rol text NOT NULL,
    asignado_a text NULL,
    asignado_a_id uuid NULL REFERENCES panel_users_acl(id),
    origen text NOT NULL DEFAULT 'CEREBRO',
    extraccion_id uuid NULL REFERENCES cerebro_extracciones(id),
    borrador_id uuid NULL REFERENCES cerebro_borradores(id),
    cita text NULL,
    hablante text NULL,
    estado text NOT NULL DEFAULT 'NOTIFICADA',
    notificada_en timestamptz NOT NULL DEFAULT now(),
    notificada_por text NOT NULL DEFAULT 'SISTEMA',
    resuelta_en timestamptz NULL,
    resuelta_por text NULL,
    resolucion text NULL,
    resolucion_nota text NULL,
    registrada_en timestamptz NULL,
    registrada_por text NULL,
    metadatos jsonb NOT NULL DEFAULT '{}'::jsonb,
    creado_en timestamptz NOT NULL DEFAULT now(),
    creado_por text NOT NULL,
    actualizado_en timestamptz NOT NULL DEFAULT now(),
    lock_version integer NOT NULL DEFAULT 1,
    CONSTRAINT uq_cerebro_tareas_internas_clave UNIQUE (clave_externa),
    CONSTRAINT chk_tarea_interna_estado CHECK (
        estado IN ('NOTIFICADA', 'RESUELTA', 'JUSTIFICADA', 'REGISTRADA')
    ),
    CONSTRAINT chk_tarea_interna_rol CHECK (
        asignado_rol IN (
            'SECRETARIA', 'BODEGA', 'CONTADORA', 'VENDEDOR', 'SUPERADMIN'
        )
    ),
    CONSTRAINT chk_tarea_interna_resolucion CHECK (
        (estado = 'NOTIFICADA'
            AND resuelta_en IS NULL AND resolucion IS NULL)
        OR (estado IN ('RESUELTA', 'JUSTIFICADA', 'REGISTRADA')
            AND resuelta_en IS NOT NULL AND resolucion IS NOT NULL)
    ),
    CONSTRAINT chk_tarea_interna_registro CHECK (
        (estado = 'REGISTRADA' AND registrada_en IS NOT NULL)
        OR (estado <> 'REGISTRADA' AND registrada_en IS NULL)
    )
);

CREATE INDEX idx_cerebro_tareas_internas_abiertas
    ON cerebro_tareas_internas (estado, notificada_en)
    WHERE estado IN ('NOTIFICADA', 'RESUELTA', 'JUSTIFICADA');
CREATE INDEX idx_cerebro_tareas_internas_rol
    ON cerebro_tareas_internas (asignado_rol, notificada_en DESC);
CREATE INDEX idx_cerebro_tareas_internas_borrador
    ON cerebro_tareas_internas (borrador_id);

COMMENT ON TABLE cerebro_tareas_internas IS
    'Instrucciones internas dadas por audio/voz. El CRM deja el aviso y la persona lo resuelve o justifica y lo registra con metadatos; cada paso queda con su hora.';

COMMENT ON COLUMN cerebro_tareas_internas.instruccion IS
    'Lo que se dicto, tal cual. No se redacta ni se resume con IA.';

COMMENT ON COLUMN cerebro_tareas_internas.notificada_en IS
    'Cuando el sistema dejo el aviso en el panel. Es el inicio del reloj.';

COMMENT ON COLUMN cerebro_tareas_internas.resolucion IS
    'RESUELTA: se hizo. JUSTIFICADA: no hacia falta o no se pudo, con su nota.';

COMMENT ON COLUMN cerebro_tareas_internas.metadatos IS
    'Metadatos del cierre: referencia, comprobante, comentario. Vacio por defecto, nunca inventado.';

-- Historial append-only: la linea de tiempo real de la tarea.
CREATE TABLE cerebro_tareas_internas_eventos (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tarea_id uuid NOT NULL REFERENCES cerebro_tareas_internas(id),
    estado text NOT NULL,
    actor_id uuid NULL,
    actor_nombre text NOT NULL,
    rol_actor text NOT NULL,
    nota text NULL,
    metadatos jsonb NOT NULL DEFAULT '{}'::jsonb,
    creado_en timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_cerebro_tareas_internas_eventos
    ON cerebro_tareas_internas_eventos (tarea_id, creado_en);

COMMENT ON TABLE cerebro_tareas_internas_eventos IS
    'Append-only. Cada cambio de estado de una tarea interna, con actor y hora.';

CREATE OR REPLACE FUNCTION fn_cerebro_tareas_internas_eventos_immutable()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'cerebro_tareas_internas_eventos es append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_cerebro_tareas_internas_eventos_immutable
    BEFORE UPDATE OR DELETE ON cerebro_tareas_internas_eventos
    FOR EACH ROW EXECUTE FUNCTION fn_cerebro_tareas_internas_eventos_immutable();

-- Vista con los relojes ya calculados: la usa el panel y el informe semanal.
CREATE OR REPLACE VIEW v_cerebro_tareas_internas AS
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
       t.notificada_en,
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
       (t.resuelta_en IS NULL AND t.notificada_en < now() - interval '24 hours')
           AS vencida_24h
  FROM cerebro_tareas_internas t;

COMMENT ON VIEW v_cerebro_tareas_internas IS
    'Tareas internas con minutos hasta resolucion y hasta registro. minutos_abierta corre mientras no se resuelve.';
