-- =====================================================================
-- ORMINORTH - Migracion 085: capa de Voz, Cerebro, borradores y hechos
-- Motivo: permitir que Julio o la secretaria dicten un audio y que el
--         sistema proponga un borrador verificable, sin inventar datos y
--         sin escribir nada hasta que un humano confirme.
-- Reglas:
--   * Aditiva. No se toca ninguna migracion aplicada.
--   * El audio vive primero en voz_ingestas porque media_assets exige
--     cliente_id NOT NULL; se vincula cuando el cliente existe.
--   * Los registros historicos son append-only. Los estados viven en
--     tablas separadas y mutables.
--   * Los topes de gasto nacen NULL: los define Direccion, no el codigo.
-- =====================================================================

-- 0. Interruptores y limites (los topes economicos quedan PENDIENTES)
INSERT INTO system_settings (key, value, descripcion)
VALUES
    ('voz.enabled', 'false'::jsonb,
     'Activa la ingesta y transcripcion de audio. Nace apagado hasta cargar el proveedor STT.'),
    ('cerebro.enabled', 'false'::jsonb,
     'Activa la extraccion y los borradores del Cerebro. Nace apagado hasta cargar el LLM.'),
    ('voz.max_duracion_seg', '300'::jsonb,
     'Tope tecnico de duracion de un audio, en segundos.'),
    ('voz.cuota_usd_dia', 'null'::jsonb,
     'PENDIENTE: tope diario de gasto STT+LLM del canal en vivo, en USD.'),
    ('whatsapp.mineria_usd_dia', 'null'::jsonb,
     'PENDIENTE: tope diario de gasto para minar el historial de WhatsApp, en USD.')
ON CONFLICT (key) DO NOTHING;

-- Modulos nuevos del checklist ACL. Nacen apagados; Julio (SUPERADMIN) los
-- tiene porque ya opera todos los modulos.
UPDATE panel_users_acl
   SET modulos_permitidos = modulos_permitidos || '{"voz": false, "cerebro": false}'::jsonb
 WHERE NOT (modulos_permitidos ? 'voz');

UPDATE panel_users_acl
   SET modulos_permitidos = jsonb_set(
           jsonb_set(modulos_permitidos, '{voz}', 'true'::jsonb),
           '{cerebro}', 'true'::jsonb
       )
 WHERE rol_base = 'SUPERADMIN';

-- 1. Ingesta cruda del audio (append-only, no exige cliente previo)
CREATE TABLE voz_ingestas (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    audio_sha256 char(64) NOT NULL CHECK (audio_sha256 ~ '^[0-9a-f]{64}$'),
    canal_origen text NOT NULL CHECK (canal_origen IN (
        'PANEL_WEB', 'WHATSAPP_M1', 'WHATSAPP_MINERIA'
    )),
    emisor_usuario text NULL,
    emisor_telefono text NULL,
    storage_backend text NOT NULL CHECK (storage_backend IN ('BUNNY', 'SANDBOX')),
    storage_path text NOT NULL,
    mime_original text NOT NULL,
    tamano_bytes integer NOT NULL CHECK (tamano_bytes > 0),
    duracion_ms integer NULL CHECK (duracion_ms IS NULL OR duracion_ms > 0),
    creado_en timestamptz NOT NULL DEFAULT now()
);

COMMENT ON COLUMN voz_ingestas.duracion_ms IS
    'Duracion real si el cliente o el STT la informan. NULL no se inventa.';
COMMENT ON COLUMN voz_ingestas.storage_backend IS
    'Mismo vocabulario que media_assets.backend: BUNNY o SANDBOX.';

CREATE INDEX idx_voz_ingestas_sha ON voz_ingestas (audio_sha256, canal_origen);
CREATE INDEX idx_voz_ingestas_telefono ON voz_ingestas (emisor_telefono)
    WHERE emisor_telefono IS NOT NULL;

-- 2. Vinculo diferido al expediente del cliente (append-only)
CREATE TABLE voz_ingesta_media_links (
    ingesta_id uuid NOT NULL REFERENCES voz_ingestas(id),
    media_asset_id uuid NOT NULL REFERENCES media_assets(id),
    cliente_id uuid NOT NULL REFERENCES clients(id),
    vinculado_por text NOT NULL,
    vinculado_en timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (ingesta_id, media_asset_id)
);

-- 3. Cola de trabajo del STT (estado mutable; permite reintentos)
CREATE TABLE voz_trabajos_stt (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ingesta_id uuid NOT NULL REFERENCES voz_ingestas(id),
    intento_num integer NOT NULL DEFAULT 1 CHECK (intento_num >= 1),
    estado text NOT NULL CHECK (estado IN (
        'PENDIENTE', 'PROCESANDO', 'COMPLETADO', 'FALLIDO',
        'DEGRADADO_SIN_CREDENCIAL'
    )),
    proveedor_stt text NOT NULL,
    modelo_stt text NOT NULL,
    error_detalle text NULL,
    costo_stt_usd numeric(10, 6) NOT NULL DEFAULT 0 CHECK (costo_stt_usd >= 0),
    actualizado_en timestamptz NOT NULL DEFAULT now(),
    creado_en timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_voz_trabajo_intento UNIQUE (ingesta_id, intento_num)
);

CREATE INDEX idx_voz_trabajos_cola ON voz_trabajos_stt (estado, creado_en);

-- Solo un trabajo COMPLETADO por ingesta; los fallidos se pueden reintentar.
CREATE UNIQUE INDEX uq_voz_ingesta_completada
    ON voz_trabajos_stt (ingesta_id)
    WHERE estado = 'COMPLETADO';

-- 4. Transcripcion inmutable (una por trabajo)
CREATE TABLE voz_transcripciones (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ingesta_id uuid NOT NULL REFERENCES voz_ingestas(id),
    trabajo_stt_id uuid NOT NULL UNIQUE REFERENCES voz_trabajos_stt(id),
    idioma_detectado text NOT NULL DEFAULT 'es-EC',
    texto_crudo text NOT NULL,
    texto_normalizado text NOT NULL,
    segmentos_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    confianza_global numeric(4, 3) NOT NULL
        CHECK (confianza_global >= 0 AND confianza_global <= 1),
    duracion_ms integer NULL CHECK (duracion_ms IS NULL OR duracion_ms > 0),
    creado_en timestamptz NOT NULL DEFAULT now()
);

-- 5. Sobre de extraccion del Cerebro (append-only)
--    idempotency_key la calcula el servicio e incluye version_prompt para
--    poder re-extraer con un prompt nuevo sin chocar.
CREATE TABLE cerebro_extracciones (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    transcripcion_id uuid NULL REFERENCES voz_transcripciones(id),
    chat_mensaje_id uuid NULL REFERENCES chat_mensajes(id),
    idempotency_key text NOT NULL UNIQUE,
    usuario_solicitante text NOT NULL,
    rol_base_solicitante text NOT NULL CHECK (rol_base_solicitante IN (
        'SUPERADMIN', 'SECRETARIA', 'CONTADORA', 'BODEGA', 'CHOFER',
        'VENDEDOR', 'AUDITOR_EXTERNO'
    )),
    modelo_llm text NOT NULL,
    version_prompt text NOT NULL,
    sobre_json jsonb NOT NULL,
    tokens_entrada integer NOT NULL DEFAULT 0 CHECK (tokens_entrada >= 0),
    tokens_salida integer NOT NULL DEFAULT 0 CHECK (tokens_salida >= 0),
    latencia_ms integer NOT NULL DEFAULT 0 CHECK (latencia_ms >= 0),
    costo_llm_usd numeric(10, 6) NOT NULL DEFAULT 0 CHECK (costo_llm_usd >= 0),
    creado_en timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_fuente_extraccion CHECK (
        transcripcion_id IS NOT NULL OR chat_mensaje_id IS NOT NULL
    )
);

CREATE INDEX idx_cerebro_extracciones_trans ON cerebro_extracciones (transcripcion_id);
CREATE INDEX idx_cerebro_extracciones_chat ON cerebro_extracciones (chat_mensaje_id);

-- 6. Borradores (payload inmutable; estado y lock mutables)
CREATE TABLE cerebro_borradores (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    extraccion_id uuid NOT NULL REFERENCES cerebro_extracciones(id),
    borrador_padre_id uuid NULL REFERENCES cerebro_borradores(id),
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    estado text NOT NULL CHECK (estado IN (
        'PENDIENTE_CONFIRMACION', 'REQUIERE_ACLARACION', 'CONFIRMADO',
        'RECHAZADO', 'SUPERADO_POR_CORRECCION', 'EJECUTADO', 'ERROR_EJECUCION'
    )),
    acciones_propuestas_json jsonb NOT NULL,
    preguntas_pendientes_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    creado_por text NOT NULL,
    confirmado_por text NULL,
    confirmado_en timestamptz NULL,
    lock_version integer NOT NULL DEFAULT 1 CHECK (lock_version >= 1),
    creado_en timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_cerebro_borradores_estado ON cerebro_borradores (estado, creado_en DESC);

-- 7. Ejecucion por accion (append-only; el reintento es una fila nueva)
CREATE TABLE cerebro_ejecuciones (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    borrador_id uuid NOT NULL REFERENCES cerebro_borradores(id),
    orden_ejecucion integer NOT NULL CHECK (orden_ejecucion >= 1),
    intento_num integer NOT NULL DEFAULT 1 CHECK (intento_num >= 1),
    accion_nombre text NOT NULL,
    request_id_custodio text NOT NULL,
    parametros_ejecutados_json jsonb NOT NULL,
    estado text NOT NULL CHECK (estado IN (
        'EXITOSO', 'FALLIDO', 'OMITIDO_POR_DEPENDENCIA'
    )),
    entidad_destino_tabla text NULL,
    entidad_destino_id uuid NULL,
    error_mensaje text NULL,
    ejecutado_en timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_cerebro_ejecucion_intento
        UNIQUE (borrador_id, orden_ejecucion, intento_num)
);

-- Un request_id solo puede tener una ejecucion exitosa; los fallos se auditan.
CREATE UNIQUE INDEX uq_cerebro_ejecucion_exitosa
    ON cerebro_ejecuciones (request_id_custodio)
    WHERE estado = 'EXITOSO';

-- 8. Hechos del expediente (append-only; sin columna de vigencia)
CREATE TABLE client_facts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cliente_id uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    extraccion_id uuid NULL REFERENCES cerebro_extracciones(id),
    transcripcion_id uuid NULL REFERENCES voz_transcripciones(id),
    chat_mensaje_id uuid NULL REFERENCES chat_mensajes(id),
    categoria text NOT NULL CHECK (categoria IN (
        'DATO_CONTACTO', 'REFERENCIA_OBRA', 'ACUERDO_COMERCIAL',
        'COMPROMISO_PAGO', 'PREFERENCIA', 'INCIDENTE', 'CONSENTIMIENTO_VOZ'
    )),
    hablante_atribuido text NOT NULL CHECK (hablante_atribuido IN (
        'CLIENTE', 'SUPERADMIN', 'SECRETARIA', 'VENDEDOR', 'CHOFER',
        'TERCERO', 'NO_DETERMINADO'
    )),
    hecho_texto text NOT NULL,
    hecho_hash char(64) NOT NULL CHECK (hecho_hash ~ '^[0-9a-f]{64}$'),
    fecha_evento date NULL,
    provenance_json jsonb NOT NULL,
    confianza numeric(4, 3) NOT NULL CHECK (confianza >= 0 AND confianza <= 1),
    creado_por text NOT NULL,
    creado_en timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_client_fact_dedup UNIQUE (cliente_id, categoria, hecho_hash)
);

CREATE INDEX idx_client_facts_cliente ON client_facts (cliente_id, creado_en DESC);
CREATE INDEX idx_client_facts_fecha ON client_facts (cliente_id, fecha_evento DESC)
    WHERE fecha_evento IS NOT NULL;

COMMENT ON COLUMN client_facts.hecho_hash IS
    'SHA-256 de categoria + hecho_texto + fecha_evento + fuente. Dos acuerdos iguales en fechas distintas son hechos distintos.';

-- 9. Superacion de un hecho (append-only, sin UPDATE sobre client_facts)
CREATE TABLE client_fact_supersedes (
    fact_id_superado uuid NOT NULL REFERENCES client_facts(id),
    fact_id_nuevo uuid NOT NULL REFERENCES client_facts(id),
    motivo text NOT NULL,
    registrado_por text NOT NULL,
    registrado_en timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (fact_id_superado, fact_id_nuevo),
    CONSTRAINT uq_client_fact_supersede_nuevo UNIQUE (fact_id_nuevo),
    CONSTRAINT chk_no_self_supersede CHECK (fact_id_superado <> fact_id_nuevo)
);

-- 10. Cursor de mineria (mutable; chat_mensajes.id es uuid)
CREATE TABLE whatsapp_mineria_cursores (
    telefono_normalizado text PRIMARY KEY,
    ultimo_chat_mensaje_id uuid NULL REFERENCES chat_mensajes(id),
    total_mensajes_procesados integer NOT NULL DEFAULT 0
        CHECK (total_mensajes_procesados >= 0),
    total_audios_transcritos integer NOT NULL DEFAULT 0
        CHECK (total_audios_transcritos >= 0),
    estado text NOT NULL DEFAULT 'PAUSADO' CHECK (estado IN (
        'ACTIVO', 'PAUSADO', 'COMPLETADO', 'ERROR'
    )),
    ultimo_error text NULL,
    actualizado_en timestamptz NOT NULL DEFAULT now()
);

-- 11. Fecha tentativa de entrega (decision 2026-11-14: date + time, sin hora
--     inventada). La fecha firme sigue en dispatch_schedule.
ALTER TABLE cotizaciones
    ADD COLUMN IF NOT EXISTS fecha_entrega_tentativa date NULL,
    ADD COLUMN IF NOT EXISTS hora_entrega_tentativa time NULL;

-- 12. Inmutabilidad
CREATE OR REPLACE FUNCTION fn_prevent_update_delete()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Operacion % prohibida en tabla append-only %', TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_voz_ingestas_immutable
    BEFORE UPDATE OR DELETE ON voz_ingestas
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_update_delete();

CREATE TRIGGER trg_voz_ingesta_media_links_immutable
    BEFORE UPDATE OR DELETE ON voz_ingesta_media_links
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_update_delete();

CREATE TRIGGER trg_voz_transcripciones_immutable
    BEFORE UPDATE OR DELETE ON voz_transcripciones
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_update_delete();

CREATE TRIGGER trg_cerebro_extracciones_immutable
    BEFORE UPDATE OR DELETE ON cerebro_extracciones
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_update_delete();

CREATE TRIGGER trg_cerebro_ejecuciones_immutable
    BEFORE UPDATE OR DELETE ON cerebro_ejecuciones
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_update_delete();

CREATE TRIGGER trg_client_facts_immutable
    BEFORE UPDATE OR DELETE ON client_facts
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_update_delete();

CREATE TRIGGER trg_client_fact_supersedes_immutable
    BEFORE UPDATE OR DELETE ON client_fact_supersedes
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_update_delete();

-- El payload del borrador no se puede reescribir: las correcciones crean otra
-- fila y el anterior pasa a SUPERADO_POR_CORRECCION.
CREATE OR REPLACE FUNCTION fn_borrador_payload_immutable()
RETURNS trigger AS $$
BEGIN
    IF NEW.acciones_propuestas_json IS DISTINCT FROM OLD.acciones_propuestas_json
       OR NEW.extraccion_id IS DISTINCT FROM OLD.extraccion_id
       OR NEW.borrador_padre_id IS DISTINCT FROM OLD.borrador_padre_id
       OR NEW.version IS DISTINCT FROM OLD.version
       OR NEW.creado_por IS DISTINCT FROM OLD.creado_por THEN
        RAISE EXCEPTION 'El payload del borrador es inmutable; cree una version nueva';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_cerebro_borrador_payload
    BEFORE UPDATE ON cerebro_borradores
    FOR EACH ROW EXECUTE FUNCTION fn_borrador_payload_immutable();
