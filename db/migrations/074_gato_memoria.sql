-- =====================================================================
-- HORMINOR - Migracion 074: memoria de conversaciones de Gato
-- Motivo: Gato debe seguir el hilo ("esa factura", "descargala", "y el
--         saldo") sin repetir preguntas. Se guarda cada turno en PostgreSQL,
--         ligado a un `conversacion_id` y al actor que pregunto.
-- No guarda secretos ni datos fuera del CRM: solo pregunta, respuesta y
-- estado del asistente.
-- =====================================================================

CREATE TABLE IF NOT EXISTS gato_turnos (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversacion_id  uuid NOT NULL,
    actor_id         text NOT NULL,
    rol_actor        text NOT NULL,
    pregunta         text NOT NULL,
    respuesta        text NOT NULL,
    estado           text NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE gato_turnos IS
    'Memoria append-only de Gato. Cada fila es un turno usuario/asistente; el historial se reconstruye por conversacion_id.';

CREATE INDEX IF NOT EXISTS ix_gato_turnos_conversacion
    ON gato_turnos (conversacion_id, created_at DESC);
