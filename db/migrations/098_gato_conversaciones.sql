-- =====================================================================
-- ORMINORTH - Migracion 098: conversaciones reales de Gato
-- Motivo: gato_turnos tiene conversacion_id, pero no una cabecera con
--         apertura/cierre. Sin ella, el refresh no cierra nada y el
--         contexto de dictados viejos contamina operaciones nuevas.
--
-- Reglas:
--   * Todo id es uuid. actor_id es text (compatible con gato_turnos).
--   * Una sola conversacion abierta por actor.
--   * No se borra evidencia: las relaciones auditables usan RESTRICT.
--   * Backfill antes de las FK; NOT VALID + VALIDATE.
-- =====================================================================

-- 1. Preflight: un conversacion_id no puede pertenecer a dos actores.
DO $$
DECLARE
    conflictos integer;
BEGIN
    SELECT count(*) INTO conflictos
      FROM (
            SELECT conversacion_id
              FROM gato_turnos
             GROUP BY conversacion_id
            HAVING count(DISTINCT actor_id) > 1
           ) x;
    IF conflictos > 0 THEN
        RAISE EXCEPTION
            '098: hay % conversacion_id con mas de un actor en gato_turnos; conciliar antes de migrar',
            conflictos;
    END IF;

    SELECT count(*) INTO conflictos
      FROM (
            SELECT conversacion_id
              FROM gato_recordatorios
             WHERE conversacion_id IS NOT NULL
             GROUP BY conversacion_id
            HAVING count(DISTINCT creado_por) > 1
           ) x;
    IF conflictos > 0 THEN
        RAISE EXCEPTION
            '098: hay % conversacion_id con mas de un creado_por en gato_recordatorios; conciliar antes de migrar',
            conflictos;
    END IF;
END $$;

-- 2. Cabecera de conversacion
CREATE TABLE IF NOT EXISTS gato_conversaciones (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id            text NOT NULL,
    perfil_id           uuid NULL REFERENCES panel_users_acl(id),
    rol_actor           text NOT NULL,
    abierta_en          timestamptz NOT NULL DEFAULT now(),
    cerrada_en          timestamptz NULL,
    ultimo_turno_en     timestamptz NOT NULL DEFAULT now(),
    titulo              text NULL,
    resumen             text NULL,
    estado_dialogo_json jsonb NOT NULL DEFAULT '{"estado":"LIBRE"}'::jsonb,
    lock_version        integer NOT NULL DEFAULT 1,
    CONSTRAINT chk_gato_conv_cierre
        CHECK (cerrada_en IS NULL OR cerrada_en >= abierta_en),
    CONSTRAINT chk_gato_conv_lock CHECK (lock_version >= 1)
);

CREATE INDEX IF NOT EXISTS ix_gato_conversaciones_actor
    ON gato_conversaciones (actor_id, ultimo_turno_en DESC);

-- 3. Backfill: una cabecera por conversacion_id historico
INSERT INTO gato_conversaciones (
    id, actor_id, rol_actor, abierta_en, ultimo_turno_en,
    titulo, resumen, estado_dialogo_json, lock_version
)
SELECT conversacion_id,
       min(actor_id),
       min(rol_actor),
       min(created_at),
       max(created_at),
       'Conversacion historica',
       NULL,
       '{"estado":"LIBRE"}'::jsonb,
       1
  FROM gato_turnos
 GROUP BY conversacion_id
ON CONFLICT (id) DO NOTHING;

-- Dejar abierta solo la mas reciente por actor; las demas se cierran.
WITH ranked AS (
    SELECT id,
           row_number() OVER (
               PARTITION BY actor_id
               ORDER BY ultimo_turno_en DESC, abierta_en DESC
           ) AS rn
      FROM gato_conversaciones
)
UPDATE gato_conversaciones c
   SET cerrada_en = c.ultimo_turno_en,
       lock_version = c.lock_version + 1
  FROM ranked r
 WHERE c.id = r.id
   AND r.rn > 1
   AND c.cerrada_en IS NULL;

-- El indice unico se crea DESPUES del backfill: antes chocaria con las
-- cabeceras historicas que todavia estan abiertas.
CREATE UNIQUE INDEX IF NOT EXISTS uq_gato_conversacion_abierta_actor
    ON gato_conversaciones (actor_id)
    WHERE cerrada_en IS NULL;

-- Cabeceras para recordatorios con conversacion_id sin cabecera.
INSERT INTO gato_conversaciones (
    id, actor_id, rol_actor, abierta_en, ultimo_turno_en,
    cerrada_en, titulo, resumen, estado_dialogo_json, lock_version
)
SELECT r.conversacion_id,
       min(r.creado_por),
       min(r.rol_actor),
       min(r.created_at),
       max(r.created_at),
       max(r.created_at),
       'Recordatorio historico',
       NULL,
       '{"estado":"LIBRE"}'::jsonb,
       1
  FROM gato_recordatorios r
  LEFT JOIN gato_conversaciones c ON c.id = r.conversacion_id
 WHERE r.conversacion_id IS NOT NULL
   AND c.id IS NULL
 GROUP BY r.conversacion_id
ON CONFLICT (id) DO NOTHING;

-- 4. Idempotencia de turno desde el cliente
ALTER TABLE gato_turnos
    ADD COLUMN IF NOT EXISTS client_turn_id text NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_gato_turnos_conv_client_turn
    ON gato_turnos (conversacion_id, client_turn_id)
    WHERE client_turn_id IS NOT NULL;

-- 5. FK de turnos y recordatorios a la cabecera
ALTER TABLE gato_turnos
    ADD CONSTRAINT fk_gato_turnos_conversacion
    FOREIGN KEY (conversacion_id) REFERENCES gato_conversaciones(id)
    NOT VALID;
ALTER TABLE gato_turnos VALIDATE CONSTRAINT fk_gato_turnos_conversacion;

ALTER TABLE gato_recordatorios
    ADD CONSTRAINT fk_gato_recordatorios_conversacion
    FOREIGN KEY (conversacion_id) REFERENCES gato_conversaciones(id)
    NOT VALID;
ALTER TABLE gato_recordatorios VALIDATE CONSTRAINT fk_gato_recordatorios_conversacion;

-- 6. Puente turno <-> borrador (un turno puede producir varios borradores)
CREATE TABLE IF NOT EXISTS gato_turno_borradores (
    turno_id    uuid NOT NULL REFERENCES gato_turnos(id) ON DELETE RESTRICT,
    borrador_id uuid NOT NULL REFERENCES cerebro_borradores(id) ON DELETE RESTRICT,
    creado_en   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (turno_id, borrador_id)
);

CREATE INDEX IF NOT EXISTS ix_gato_turno_borradores_borrador
    ON gato_turno_borradores (borrador_id);

-- 7. Enlaces del Cerebro a la conversacion y al cliente
ALTER TABLE cerebro_borradores
    ADD COLUMN IF NOT EXISTS conversacion_id uuid NULL
        REFERENCES gato_conversaciones(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS cliente_id uuid NULL
        REFERENCES clients(id) ON DELETE RESTRICT;

ALTER TABLE cerebro_extracciones
    ADD COLUMN IF NOT EXISTS conversacion_id uuid NULL
        REFERENCES gato_conversaciones(id) ON DELETE RESTRICT;

ALTER TABLE cerebro_tareas_internas
    ADD COLUMN IF NOT EXISTS cliente_id uuid NULL
        REFERENCES clients(id) ON DELETE RESTRICT;

CREATE INDEX IF NOT EXISTS ix_cerebro_borradores_conversacion
    ON cerebro_borradores (conversacion_id, creado_en DESC);
CREATE INDEX IF NOT EXISTS ix_cerebro_extracciones_conversacion
    ON cerebro_extracciones (conversacion_id, creado_en DESC);
CREATE INDEX IF NOT EXISTS ix_cerebro_tareas_internas_cliente
    ON cerebro_tareas_internas (cliente_id, creado_en DESC);

COMMENT ON TABLE gato_conversaciones IS
    'Conversacion de Gato con apertura, cierre y estado de dialogo. Una sola abierta por actor.';
COMMENT ON COLUMN gato_conversaciones.estado_dialogo_json IS
    'Solo un pendiente activo: LIBRE | ESPERANDO_CLIENTE | ESPERANDO_CONFIRMACION.';
COMMENT ON TABLE gato_turno_borradores IS
    'Puente N:M turno de Gato <-> borrador del Cerebro.';
