-- =====================================================================
-- ORMINORTH - Migracion 096: nucleo comercial (leads y citas)
-- Motivo: leads y agendamiento son un modulo independiente del canal.
--         La fecha de negocio sale de app/tiempo.py (America/Guayaquil).
-- Nada de negocio se inventa: umbrales y plazos nacen NULL.
-- =====================================================================

-- 1. Leads -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS leads (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    telefono_e164       text NOT NULL UNIQUE,
    nombre              text,
    origen              text NOT NULL DEFAULT 'WHATSAPP'
                        CHECK (origen IN ('WHATSAPP', 'GATO', 'PANEL', 'OTRO')),
    estado              text NOT NULL DEFAULT 'CONTACTO'
                        CHECK (estado IN (
                            'CONTACTO', 'LEAD', 'CALIFICADO', 'EN_ESPERA',
                            'HANDOFF', 'CAIDO', 'CONVERTIDO'
                        )),
    interes             text,
    cliente_id          uuid REFERENCES clients(id) ON DELETE SET NULL,
    motivo_caida        text
                        CHECK (motivo_caida IN (
                            'SIN_RESPUESTA', 'NO_INTERESADO', 'COMPETENCIA',
                            'PRECIO', 'SIN_CONTACTO', 'NO_APLICA', 'OTRO'
                        )),
    recontactar_at      timestamptz,
    intentos_recontacto integer NOT NULL DEFAULT 0,
    ultimo_contacto_at  timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_leads_estado ON leads (estado);
CREATE INDEX IF NOT EXISTS ix_leads_recontactar
    ON leads (recontactar_at)
    WHERE estado = 'EN_ESPERA';

COMMENT ON TABLE leads IS
    'Contacto que ya tuvo al menos una respuesta de la empresa.';

-- 2. Eventos del lead (append-only) -------------------------------------
CREATE TABLE IF NOT EXISTS lead_eventos (
    id          bigserial PRIMARY KEY,
    lead_id     uuid NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    tipo        text NOT NULL,
    detalle     jsonb NOT NULL DEFAULT '{}'::jsonb,
    actor       text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_lead_eventos_lead
    ON lead_eventos (lead_id, created_at DESC);

CREATE TRIGGER trg_lead_eventos_append_only
    BEFORE UPDATE OR DELETE ON lead_eventos
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_update_delete();

-- 3. Reglas de caida por intencion --------------------------------------
CREATE TABLE IF NOT EXISTS lead_reglas_caida (
    clave           text PRIMARY KEY,
    intencion       text NOT NULL,
    patrones        jsonb NOT NULL DEFAULT '[]'::jsonb,
    estado_destino  text NOT NULL,
    motivo          text,
    gracia_dias     integer,
    intentos        integer,
    activo          boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE lead_reglas_caida IS
    'Semantica operativa de la caida; los plazos NULL esperan a Julio.';

INSERT INTO lead_reglas_caida
    (clave, intencion, patrones, estado_destino, motivo, activo)
VALUES
    ('RECHAZO', 'RECHAZO_EXPLICITO',
     '["no me interesa","no gracias","no estoy interesado","asi estoy bien"]'::jsonb,
     'CAIDO', 'NO_INTERESADO', true),
    ('COMPETENCIA', 'YA_TIENE_PROVEEDOR',
     '["ya compre","ya tengo","trabajo con otro","ya tengo proveedor"]'::jsonb,
     'CAIDO', 'COMPETENCIA', true),
    ('PRECIO', 'OBJECION_PRECIO',
     '["esta caro","muy caro","no tengo presupuesto"]'::jsonb,
     'EN_ESPERA', 'PRECIO', true),
    ('APLAZAMIENTO', 'APLAZA',
     '["le aviso","en unos dias","la proxima semana","despues le digo"]'::jsonb,
     'EN_ESPERA', NULL, true),
    ('NO_DECISOR', 'NO_ES_QUIEN_DECIDE',
     '["yo solo pregunto","no soy el dueno","el que decide es"]'::jsonb,
     'HANDOFF', 'SIN_CONTACTO', true),
    ('NO_APLICA', 'NUMERO_EQUIVOCADO',
     '["numero equivocado","no soy yo","no es mi numero"]'::jsonb,
     'CAIDO', 'NO_APLICA', true),
    ('SIN_RESPUESTA', 'SILENCIO',
     '[]'::jsonb,
     'CAIDO', 'SIN_RESPUESTA', false)
ON CONFLICT (clave) DO NOTHING;

-- 4. Citas ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS citas (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cliente_id      uuid REFERENCES clients(id) ON DELETE SET NULL,
    lead_id         uuid REFERENCES leads(id) ON DELETE SET NULL,
    tipo            text NOT NULL
                    CHECK (tipo IN ('VISITA', 'REUNION', 'MEDICION', 'ENTREGA')),
    fecha           date NOT NULL,
    hora_inicio     time NOT NULL,
    duracion_min    integer NOT NULL DEFAULT 60,
    estado          text NOT NULL DEFAULT 'SOLICITADA'
                    CHECK (estado IN (
                        'SOLICITADA', 'CONFIRMADA', 'REALIZADA',
                        'CANCELADA', 'REAGENDADA'
                    )),
    origen          text NOT NULL
                    CHECK (origen IN ('PANEL', 'WHATSAPP', 'GATO', 'MIAU')),
    solicitada_por  text,
    notas           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_citas_fecha ON citas (fecha, hora_inicio);
CREATE INDEX IF NOT EXISTS ix_citas_cliente ON citas (cliente_id);
CREATE INDEX IF NOT EXISTS ix_citas_lead ON citas (lead_id);

-- 5. Parametros de negocio (NULL hasta que Julio los defina) -------------
INSERT INTO system_settings (key, value) VALUES
    ('leads.recontacto_dias', 'null'::jsonb),
    ('leads.max_intentos', 'null'::jsonb),
    ('agenda.citas_horario_inicio', 'null'::jsonb),
    ('agenda.citas_horario_fin', 'null'::jsonb),
    ('agenda.citas_duracion_min', 'null'::jsonb)
ON CONFLICT (key) DO NOTHING;
