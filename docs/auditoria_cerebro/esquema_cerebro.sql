--
-- PostgreSQL database dump
--


-- Dumped from database version 15.19
-- Dumped by pg_dump version 15.19

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: cerebro_borradores; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cerebro_borradores (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    extraccion_id uuid NOT NULL,
    borrador_padre_id uuid,
    version integer DEFAULT 1 NOT NULL,
    estado text NOT NULL,
    acciones_propuestas_json jsonb NOT NULL,
    preguntas_pendientes_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    creado_por text NOT NULL,
    confirmado_por text,
    confirmado_en timestamp with time zone,
    lock_version integer DEFAULT 1 NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    condiciones_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    encargos_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    CONSTRAINT cerebro_borradores_estado_check CHECK ((estado = ANY (ARRAY['SIN_ACCIONES'::text, 'PENDIENTE_CONFIRMACION'::text, 'REQUIERE_ACLARACION'::text, 'CONFIRMADO'::text, 'RECHAZADO'::text, 'SUPERADO_POR_CORRECCION'::text, 'EJECUTADO'::text, 'ERROR_EJECUCION'::text]))),
    CONSTRAINT cerebro_borradores_lock_version_check CHECK ((lock_version >= 1)),
    CONSTRAINT cerebro_borradores_version_check CHECK ((version >= 1))
);


--
-- Name: COLUMN cerebro_borradores.condiciones_json; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.cerebro_borradores.condiciones_json IS 'Condiciones y encargos sostenidos por una cita que no se convierten en accion ejecutable. Se conservan para que no se pierda el encargo; no autorizan nada por si solas.';


--
-- Name: COLUMN cerebro_borradores.encargos_json; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.cerebro_borradores.encargos_json IS 'Resumen por encargo (texto, estado, acciones y preguntas). Nace con el borrador; una correccion crea una version nueva.';


--
-- Name: CONSTRAINT cerebro_borradores_estado_check ON cerebro_borradores; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT cerebro_borradores_estado_check ON public.cerebro_borradores IS 'Estados del borrador. SIN_ACCIONES = el dictado no pide nada ejecutable; se guarda igual para dejar constancia.';


--
-- Name: cerebro_correcciones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cerebro_correcciones (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    borrador_id uuid NOT NULL,
    borrador_nuevo_id uuid,
    extraccion_id uuid NOT NULL,
    clave text NOT NULL,
    valor_anterior text,
    valor_nuevo text NOT NULL,
    cita text,
    corregido_por text NOT NULL,
    rol_base text NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    encargo integer DEFAULT 1 NOT NULL,
    CONSTRAINT chk_correccion_distinta CHECK (((valor_anterior IS NULL) OR (valor_anterior <> valor_nuevo)))
);


--
-- Name: TABLE cerebro_correcciones; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.cerebro_correcciones IS 'Append-only. Cada fila es una persona corrigiendo un hecho del Cerebro. El borrador anterior no se reescribe: se marca SUPERADO_POR_CORRECCION.';


--
-- Name: COLUMN cerebro_correcciones.cita; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.cerebro_correcciones.cita IS 'Cita del hecho original (lo que dijo el audio segun el STT), no el valor corregido.';


--
-- Name: COLUMN cerebro_correcciones.encargo; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.cerebro_correcciones.encargo IS 'Encargo corregido. Dos asuntos pueden compartir clave (dos tarea.mensaje): la correccion alcanza solo al indicado.';


--
-- Name: cerebro_ejecuciones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cerebro_ejecuciones (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    borrador_id uuid NOT NULL,
    orden_ejecucion integer NOT NULL,
    intento_num integer DEFAULT 1 NOT NULL,
    accion_nombre text NOT NULL,
    request_id_custodio text NOT NULL,
    parametros_ejecutados_json jsonb NOT NULL,
    estado text NOT NULL,
    entidad_destino_tabla text,
    entidad_destino_id uuid,
    error_mensaje text,
    ejecutado_en timestamp with time zone DEFAULT now() NOT NULL,
    encargo integer DEFAULT 1 NOT NULL,
    CONSTRAINT cerebro_ejecuciones_estado_check CHECK ((estado = ANY (ARRAY['EXITOSO'::text, 'FALLIDO'::text, 'OMITIDO_POR_DEPENDENCIA'::text]))),
    CONSTRAINT cerebro_ejecuciones_intento_num_check CHECK ((intento_num >= 1)),
    CONSTRAINT cerebro_ejecuciones_orden_ejecucion_check CHECK ((orden_ejecucion >= 1)),
    CONSTRAINT chk_ejecucion_encargo CHECK ((encargo >= 1))
);


--
-- Name: COLUMN cerebro_ejecuciones.encargo; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.cerebro_ejecuciones.encargo IS 'Encargo del borrador al que pertenece la ejecucion. Permite confirmar y cancelar por asunto, no por dictado completo.';


--
-- Name: cerebro_encargos_decisiones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cerebro_encargos_decisiones (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    borrador_id uuid NOT NULL,
    encargo integer NOT NULL,
    decision text NOT NULL,
    motivo text NOT NULL,
    decidido_por text NOT NULL,
    rol_base text NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT cerebro_encargos_decisiones_decision_check CHECK ((decision = 'CANCELADO'::text)),
    CONSTRAINT cerebro_encargos_decisiones_encargo_check CHECK ((encargo >= 1))
);


--
-- Name: cerebro_extracciones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cerebro_extracciones (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    transcripcion_id uuid,
    chat_mensaje_id uuid,
    idempotency_key text NOT NULL,
    usuario_solicitante text NOT NULL,
    rol_base_solicitante text NOT NULL,
    modelo_llm text NOT NULL,
    version_prompt text NOT NULL,
    sobre_json jsonb NOT NULL,
    tokens_entrada integer DEFAULT 0 NOT NULL,
    tokens_salida integer DEFAULT 0 NOT NULL,
    latencia_ms integer DEFAULT 0 NOT NULL,
    costo_llm_usd numeric(10,6) DEFAULT 0 NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    texto_directo text,
    CONSTRAINT cerebro_extracciones_costo_llm_usd_check CHECK ((costo_llm_usd >= (0)::numeric)),
    CONSTRAINT cerebro_extracciones_latencia_ms_check CHECK ((latencia_ms >= 0)),
    CONSTRAINT cerebro_extracciones_rol_base_solicitante_check CHECK ((rol_base_solicitante = ANY (ARRAY['SUPERADMIN'::text, 'SECRETARIA'::text, 'CONTADORA'::text, 'BODEGA'::text, 'CHOFER'::text, 'VENDEDOR'::text, 'AUDITOR_EXTERNO'::text]))),
    CONSTRAINT cerebro_extracciones_tokens_entrada_check CHECK ((tokens_entrada >= 0)),
    CONSTRAINT cerebro_extracciones_tokens_salida_check CHECK ((tokens_salida >= 0)),
    CONSTRAINT chk_fuente_extraccion CHECK (((transcripcion_id IS NOT NULL) OR (chat_mensaje_id IS NOT NULL) OR (texto_directo IS NOT NULL)))
);


--
-- Name: COLUMN cerebro_extracciones.texto_directo; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.cerebro_extracciones.texto_directo IS 'Texto pegado o dictado sin audio asociado. NULL cuando la fuente es una transcripcion o un mensaje.';


--
-- Name: cerebro_tareas_internas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cerebro_tareas_internas (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clave_externa text NOT NULL,
    instruccion text NOT NULL,
    asignado_rol text NOT NULL,
    asignado_a text,
    asignado_a_id uuid,
    origen text DEFAULT 'CEREBRO'::text NOT NULL,
    extraccion_id uuid,
    borrador_id uuid,
    cita text,
    hablante text,
    estado text DEFAULT 'NOTIFICADA'::text NOT NULL,
    notificada_en timestamp with time zone DEFAULT now() NOT NULL,
    notificada_por text DEFAULT 'SISTEMA'::text NOT NULL,
    resuelta_en timestamp with time zone,
    resuelta_por text,
    resolucion text,
    resolucion_nota text,
    registrada_en timestamp with time zone,
    registrada_por text,
    metadatos jsonb DEFAULT '{}'::jsonb NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    creado_por text NOT NULL,
    actualizado_en timestamp with time zone DEFAULT now() NOT NULL,
    lock_version integer DEFAULT 1 NOT NULL,
    prioridad text DEFAULT 'NORMAL'::text NOT NULL,
    plazo_en timestamp with time zone,
    vista_en timestamp with time zone,
    vista_por text,
    acusada_en timestamp with time zone,
    acusada_por text,
    escalada_en timestamp with time zone,
    escalada_por text,
    CONSTRAINT chk_tarea_interna_estado CHECK ((estado = ANY (ARRAY['NOTIFICADA'::text, 'RESUELTA'::text, 'JUSTIFICADA'::text, 'REGISTRADA'::text]))),
    CONSTRAINT chk_tarea_interna_prioridad CHECK ((prioridad = ANY (ARRAY['NORMAL'::text, 'URGENTE'::text]))),
    CONSTRAINT chk_tarea_interna_registro CHECK ((((estado = 'REGISTRADA'::text) AND (registrada_en IS NOT NULL)) OR ((estado <> 'REGISTRADA'::text) AND (registrada_en IS NULL)))),
    CONSTRAINT chk_tarea_interna_resolucion CHECK ((((estado = 'NOTIFICADA'::text) AND (resuelta_en IS NULL) AND (resolucion IS NULL)) OR ((estado = ANY (ARRAY['RESUELTA'::text, 'JUSTIFICADA'::text, 'REGISTRADA'::text])) AND (resuelta_en IS NOT NULL) AND (resolucion IS NOT NULL)))),
    CONSTRAINT chk_tarea_interna_rol CHECK ((asignado_rol = ANY (ARRAY['SECRETARIA'::text, 'BODEGA'::text, 'CONTADORA'::text, 'VENDEDOR'::text, 'SUPERADMIN'::text])))
);


--
-- Name: TABLE cerebro_tareas_internas; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.cerebro_tareas_internas IS 'Instrucciones internas dadas por audio/voz. El CRM deja el aviso y la persona lo resuelve o justifica y lo registra con metadatos; cada paso queda con su hora.';


--
-- Name: COLUMN cerebro_tareas_internas.instruccion; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.cerebro_tareas_internas.instruccion IS 'Lo que se dicto, tal cual. No se redacta ni se resume con IA.';


--
-- Name: COLUMN cerebro_tareas_internas.notificada_en; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.cerebro_tareas_internas.notificada_en IS 'Cuando el sistema dejo el aviso en el panel. Es el inicio del reloj.';


--
-- Name: COLUMN cerebro_tareas_internas.resolucion; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.cerebro_tareas_internas.resolucion IS 'RESUELTA: se hizo. JUSTIFICADA: no hacia falta o no se pudo, con su nota.';


--
-- Name: COLUMN cerebro_tareas_internas.metadatos; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.cerebro_tareas_internas.metadatos IS 'Metadatos del cierre: referencia, comprobante, comentario. Vacio por defecto, nunca inventado.';


--
-- Name: COLUMN cerebro_tareas_internas.prioridad; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.cerebro_tareas_internas.prioridad IS 'NORMAL o URGENTE. No la decide el modelo: la marca el dictado y el plazo.';


--
-- Name: COLUMN cerebro_tareas_internas.plazo_en; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.cerebro_tareas_internas.plazo_en IS 'Fecha limite para atender la tarea. NULL = sin plazo explicito (politica por prioridad).';


--
-- Name: COLUMN cerebro_tareas_internas.vista_en; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.cerebro_tareas_internas.vista_en IS 'Cuando una persona abrio el detalle de la tarea. No es acuse de recibo.';


--
-- Name: COLUMN cerebro_tareas_internas.acusada_en; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.cerebro_tareas_internas.acusada_en IS 'Cuando una persona confirmo que recibio el encargo. No significa que lo hizo.';


--
-- Name: COLUMN cerebro_tareas_internas.escalada_en; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.cerebro_tareas_internas.escalada_en IS 'Cuando un supervisor decidio escalar una tarea vencida sin atencion.';


--
-- Name: cerebro_tareas_internas_eventos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cerebro_tareas_internas_eventos (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tarea_id uuid NOT NULL,
    estado text NOT NULL,
    actor_id uuid,
    actor_nombre text NOT NULL,
    rol_actor text NOT NULL,
    nota text,
    metadatos jsonb DEFAULT '{}'::jsonb NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE cerebro_tareas_internas_eventos; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.cerebro_tareas_internas_eventos IS 'Append-only. Cada cambio de estado de una tarea interna, con actor y hora.';


--
-- Name: cerebro_vocabulario_retiros; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cerebro_vocabulario_retiros (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clave text NOT NULL,
    valor_anterior text NOT NULL,
    valor_nuevo text NOT NULL,
    motivo text NOT NULL,
    retirado_por text NOT NULL,
    rol_base text NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE cerebro_vocabulario_retiros; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.cerebro_vocabulario_retiros IS 'Append-only. Retira una asociacion del vocabulario aprendido sin borrar la correccion que la origino.';


--
-- Name: client_fact_supersedes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.client_fact_supersedes (
    fact_id_superado uuid NOT NULL,
    fact_id_nuevo uuid NOT NULL,
    motivo text NOT NULL,
    registrado_por text NOT NULL,
    registrado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_no_self_supersede CHECK ((fact_id_superado <> fact_id_nuevo))
);


--
-- Name: client_facts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.client_facts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    cliente_id uuid NOT NULL,
    extraccion_id uuid,
    transcripcion_id uuid,
    chat_mensaje_id uuid,
    categoria text NOT NULL,
    hablante_atribuido text NOT NULL,
    hecho_texto text NOT NULL,
    hecho_hash character(64) NOT NULL,
    fecha_evento date,
    provenance_json jsonb NOT NULL,
    confianza numeric(4,3) NOT NULL,
    creado_por text NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT client_facts_categoria_check CHECK ((categoria = ANY (ARRAY['DATO_CONTACTO'::text, 'REFERENCIA_OBRA'::text, 'ACUERDO_COMERCIAL'::text, 'COMPROMISO_PAGO'::text, 'PREFERENCIA'::text, 'INCIDENTE'::text, 'CONSENTIMIENTO_VOZ'::text]))),
    CONSTRAINT client_facts_confianza_check CHECK (((confianza >= (0)::numeric) AND (confianza <= (1)::numeric))),
    CONSTRAINT client_facts_hablante_atribuido_check CHECK ((hablante_atribuido = ANY (ARRAY['CLIENTE'::text, 'SUPERADMIN'::text, 'SECRETARIA'::text, 'VENDEDOR'::text, 'CHOFER'::text, 'TERCERO'::text, 'NO_DETERMINADO'::text]))),
    CONSTRAINT client_facts_hecho_hash_check CHECK ((hecho_hash ~ '^[0-9a-f]{64}$'::text))
);


--
-- Name: COLUMN client_facts.hecho_hash; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.client_facts.hecho_hash IS 'SHA-256 de categoria + hecho_texto + fecha_evento + fuente. Dos acuerdos iguales en fechas distintas son hechos distintos.';


--
-- Name: voz_ingesta_media_links; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.voz_ingesta_media_links (
    ingesta_id uuid NOT NULL,
    media_asset_id uuid NOT NULL,
    cliente_id uuid NOT NULL,
    vinculado_por text NOT NULL,
    vinculado_en timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: voz_ingestas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.voz_ingestas (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    audio_sha256 character(64) NOT NULL,
    canal_origen text NOT NULL,
    emisor_usuario text,
    emisor_telefono text,
    storage_backend text NOT NULL,
    storage_path text NOT NULL,
    mime_original text NOT NULL,
    tamano_bytes integer NOT NULL,
    duracion_ms integer,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT voz_ingestas_audio_sha256_check CHECK ((audio_sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT voz_ingestas_canal_origen_check CHECK ((canal_origen = ANY (ARRAY['PANEL_WEB'::text, 'WHATSAPP_M1'::text, 'WHATSAPP_MINERIA'::text]))),
    CONSTRAINT voz_ingestas_duracion_ms_check CHECK (((duracion_ms IS NULL) OR (duracion_ms > 0))),
    CONSTRAINT voz_ingestas_storage_backend_check CHECK ((storage_backend = ANY (ARRAY['BUNNY'::text, 'SANDBOX'::text]))),
    CONSTRAINT voz_ingestas_tamano_bytes_check CHECK ((tamano_bytes > 0))
);


--
-- Name: COLUMN voz_ingestas.storage_backend; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.voz_ingestas.storage_backend IS 'Mismo vocabulario que media_assets.backend: BUNNY o SANDBOX.';


--
-- Name: COLUMN voz_ingestas.duracion_ms; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.voz_ingestas.duracion_ms IS 'Duracion real si el cliente o el STT la informan. NULL no se inventa.';


--
-- Name: voz_trabajos_stt; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.voz_trabajos_stt (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    ingesta_id uuid NOT NULL,
    intento_num integer DEFAULT 1 NOT NULL,
    estado text NOT NULL,
    proveedor_stt text NOT NULL,
    modelo_stt text NOT NULL,
    error_detalle text,
    costo_stt_usd numeric(10,6) DEFAULT 0 NOT NULL,
    actualizado_en timestamp with time zone DEFAULT now() NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT voz_trabajos_stt_costo_stt_usd_check CHECK ((costo_stt_usd >= (0)::numeric)),
    CONSTRAINT voz_trabajos_stt_estado_check CHECK ((estado = ANY (ARRAY['PENDIENTE'::text, 'PROCESANDO'::text, 'COMPLETADO'::text, 'FALLIDO'::text, 'DEGRADADO_SIN_CREDENCIAL'::text]))),
    CONSTRAINT voz_trabajos_stt_intento_num_check CHECK ((intento_num >= 1))
);


--
-- Name: voz_transcripciones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.voz_transcripciones (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    ingesta_id uuid NOT NULL,
    trabajo_stt_id uuid NOT NULL,
    idioma_detectado text DEFAULT 'es-EC'::text NOT NULL,
    texto_crudo text NOT NULL,
    texto_normalizado text NOT NULL,
    segmentos_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    confianza_global numeric(4,3) NOT NULL,
    duracion_ms integer,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT voz_transcripciones_confianza_global_check CHECK (((confianza_global >= (0)::numeric) AND (confianza_global <= (1)::numeric))),
    CONSTRAINT voz_transcripciones_duracion_ms_check CHECK (((duracion_ms IS NULL) OR (duracion_ms > 0)))
);


--
-- Name: cerebro_borradores cerebro_borradores_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_borradores
    ADD CONSTRAINT cerebro_borradores_pkey PRIMARY KEY (id);


--
-- Name: cerebro_correcciones cerebro_correcciones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_correcciones
    ADD CONSTRAINT cerebro_correcciones_pkey PRIMARY KEY (id);


--
-- Name: cerebro_ejecuciones cerebro_ejecuciones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_ejecuciones
    ADD CONSTRAINT cerebro_ejecuciones_pkey PRIMARY KEY (id);


--
-- Name: cerebro_encargos_decisiones cerebro_encargos_decisiones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_encargos_decisiones
    ADD CONSTRAINT cerebro_encargos_decisiones_pkey PRIMARY KEY (id);


--
-- Name: cerebro_extracciones cerebro_extracciones_idempotency_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_extracciones
    ADD CONSTRAINT cerebro_extracciones_idempotency_key_key UNIQUE (idempotency_key);


--
-- Name: cerebro_extracciones cerebro_extracciones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_extracciones
    ADD CONSTRAINT cerebro_extracciones_pkey PRIMARY KEY (id);


--
-- Name: cerebro_tareas_internas_eventos cerebro_tareas_internas_eventos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_tareas_internas_eventos
    ADD CONSTRAINT cerebro_tareas_internas_eventos_pkey PRIMARY KEY (id);


--
-- Name: cerebro_tareas_internas cerebro_tareas_internas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_tareas_internas
    ADD CONSTRAINT cerebro_tareas_internas_pkey PRIMARY KEY (id);


--
-- Name: cerebro_vocabulario_retiros cerebro_vocabulario_retiros_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_vocabulario_retiros
    ADD CONSTRAINT cerebro_vocabulario_retiros_pkey PRIMARY KEY (id);


--
-- Name: client_fact_supersedes client_fact_supersedes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_fact_supersedes
    ADD CONSTRAINT client_fact_supersedes_pkey PRIMARY KEY (fact_id_superado, fact_id_nuevo);


--
-- Name: client_facts client_facts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_facts
    ADD CONSTRAINT client_facts_pkey PRIMARY KEY (id);


--
-- Name: cerebro_ejecuciones uq_cerebro_ejecucion_intento; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_ejecuciones
    ADD CONSTRAINT uq_cerebro_ejecucion_intento UNIQUE (borrador_id, orden_ejecucion, intento_num);


--
-- Name: cerebro_tareas_internas uq_cerebro_tareas_internas_clave; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_tareas_internas
    ADD CONSTRAINT uq_cerebro_tareas_internas_clave UNIQUE (clave_externa);


--
-- Name: client_facts uq_client_fact_dedup; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_facts
    ADD CONSTRAINT uq_client_fact_dedup UNIQUE (cliente_id, categoria, hecho_hash);


--
-- Name: client_fact_supersedes uq_client_fact_supersede_nuevo; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_fact_supersedes
    ADD CONSTRAINT uq_client_fact_supersede_nuevo UNIQUE (fact_id_nuevo);


--
-- Name: voz_trabajos_stt uq_voz_trabajo_intento; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.voz_trabajos_stt
    ADD CONSTRAINT uq_voz_trabajo_intento UNIQUE (ingesta_id, intento_num);


--
-- Name: voz_ingesta_media_links voz_ingesta_media_links_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.voz_ingesta_media_links
    ADD CONSTRAINT voz_ingesta_media_links_pkey PRIMARY KEY (ingesta_id, media_asset_id);


--
-- Name: voz_ingestas voz_ingestas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.voz_ingestas
    ADD CONSTRAINT voz_ingestas_pkey PRIMARY KEY (id);


--
-- Name: voz_trabajos_stt voz_trabajos_stt_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.voz_trabajos_stt
    ADD CONSTRAINT voz_trabajos_stt_pkey PRIMARY KEY (id);


--
-- Name: voz_transcripciones voz_transcripciones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.voz_transcripciones
    ADD CONSTRAINT voz_transcripciones_pkey PRIMARY KEY (id);


--
-- Name: voz_transcripciones voz_transcripciones_trabajo_stt_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.voz_transcripciones
    ADD CONSTRAINT voz_transcripciones_trabajo_stt_id_key UNIQUE (trabajo_stt_id);


--
-- Name: idx_cerebro_borradores_estado; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cerebro_borradores_estado ON public.cerebro_borradores USING btree (estado, creado_en DESC);


--
-- Name: idx_cerebro_correcciones_borrador; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cerebro_correcciones_borrador ON public.cerebro_correcciones USING btree (borrador_id, creado_en);


--
-- Name: idx_cerebro_correcciones_clave; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cerebro_correcciones_clave ON public.cerebro_correcciones USING btree (clave, creado_en DESC);


--
-- Name: idx_cerebro_encargos_decisiones; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cerebro_encargos_decisiones ON public.cerebro_encargos_decisiones USING btree (borrador_id, creado_en DESC);


--
-- Name: idx_cerebro_extracciones_chat; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cerebro_extracciones_chat ON public.cerebro_extracciones USING btree (chat_mensaje_id);


--
-- Name: idx_cerebro_extracciones_trans; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cerebro_extracciones_trans ON public.cerebro_extracciones USING btree (transcripcion_id);


--
-- Name: idx_cerebro_tareas_internas_abiertas; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cerebro_tareas_internas_abiertas ON public.cerebro_tareas_internas USING btree (estado, notificada_en) WHERE (estado = ANY (ARRAY['NOTIFICADA'::text, 'RESUELTA'::text, 'JUSTIFICADA'::text]));


--
-- Name: idx_cerebro_tareas_internas_borrador; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cerebro_tareas_internas_borrador ON public.cerebro_tareas_internas USING btree (borrador_id);


--
-- Name: idx_cerebro_tareas_internas_eventos; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cerebro_tareas_internas_eventos ON public.cerebro_tareas_internas_eventos USING btree (tarea_id, creado_en);


--
-- Name: idx_cerebro_tareas_internas_plazo; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cerebro_tareas_internas_plazo ON public.cerebro_tareas_internas USING btree (plazo_en) WHERE (resuelta_en IS NULL);


--
-- Name: idx_cerebro_tareas_internas_rol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cerebro_tareas_internas_rol ON public.cerebro_tareas_internas USING btree (asignado_rol, notificada_en DESC);


--
-- Name: idx_cerebro_vocabulario_retiros; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cerebro_vocabulario_retiros ON public.cerebro_vocabulario_retiros USING btree (clave, valor_anterior, valor_nuevo);


--
-- Name: idx_client_facts_cliente; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_client_facts_cliente ON public.client_facts USING btree (cliente_id, creado_en DESC);


--
-- Name: idx_client_facts_fecha; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_client_facts_fecha ON public.client_facts USING btree (cliente_id, fecha_evento DESC) WHERE (fecha_evento IS NOT NULL);


--
-- Name: idx_voz_ingestas_sha; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_voz_ingestas_sha ON public.voz_ingestas USING btree (audio_sha256, canal_origen);


--
-- Name: idx_voz_ingestas_telefono; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_voz_ingestas_telefono ON public.voz_ingestas USING btree (emisor_telefono) WHERE (emisor_telefono IS NOT NULL);


--
-- Name: idx_voz_trabajos_cola; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_voz_trabajos_cola ON public.voz_trabajos_stt USING btree (estado, creado_en);


--
-- Name: uq_cerebro_ejecucion_exitosa; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_cerebro_ejecucion_exitosa ON public.cerebro_ejecuciones USING btree (request_id_custodio) WHERE (estado = 'EXITOSO'::text);


--
-- Name: uq_voz_ingesta_completada; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_voz_ingesta_completada ON public.voz_trabajos_stt USING btree (ingesta_id) WHERE (estado = 'COMPLETADO'::text);


--
-- Name: ux_cerebro_encargo_cancelado; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ux_cerebro_encargo_cancelado ON public.cerebro_encargos_decisiones USING btree (borrador_id, encargo, decision);


--
-- Name: cerebro_borradores trg_cerebro_borrador_payload; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_cerebro_borrador_payload BEFORE UPDATE ON public.cerebro_borradores FOR EACH ROW EXECUTE FUNCTION public.fn_borrador_payload_immutable();


--
-- Name: cerebro_correcciones trg_cerebro_correcciones_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_cerebro_correcciones_immutable BEFORE DELETE OR UPDATE ON public.cerebro_correcciones FOR EACH ROW EXECUTE FUNCTION public.fn_cerebro_correcciones_immutable();


--
-- Name: cerebro_ejecuciones trg_cerebro_ejecuciones_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_cerebro_ejecuciones_immutable BEFORE DELETE OR UPDATE ON public.cerebro_ejecuciones FOR EACH ROW EXECUTE FUNCTION public.fn_prevent_update_delete();


--
-- Name: cerebro_encargos_decisiones trg_cerebro_encargos_decisiones; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_cerebro_encargos_decisiones BEFORE DELETE OR UPDATE ON public.cerebro_encargos_decisiones FOR EACH ROW EXECUTE FUNCTION public.fn_decision_encargo_append_only();


--
-- Name: cerebro_extracciones trg_cerebro_extracciones_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_cerebro_extracciones_immutable BEFORE DELETE OR UPDATE ON public.cerebro_extracciones FOR EACH ROW EXECUTE FUNCTION public.fn_prevent_update_delete();


--
-- Name: cerebro_tareas_internas_eventos trg_cerebro_tareas_internas_eventos_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_cerebro_tareas_internas_eventos_immutable BEFORE DELETE OR UPDATE ON public.cerebro_tareas_internas_eventos FOR EACH ROW EXECUTE FUNCTION public.fn_cerebro_tareas_internas_eventos_immutable();


--
-- Name: cerebro_vocabulario_retiros trg_cerebro_vocabulario_retiros_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_cerebro_vocabulario_retiros_immutable BEFORE DELETE OR UPDATE ON public.cerebro_vocabulario_retiros FOR EACH ROW EXECUTE FUNCTION public.fn_cerebro_vocabulario_retiros_immutable();


--
-- Name: client_fact_supersedes trg_client_fact_supersedes_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_client_fact_supersedes_immutable BEFORE DELETE OR UPDATE ON public.client_fact_supersedes FOR EACH ROW EXECUTE FUNCTION public.fn_prevent_update_delete();


--
-- Name: client_facts trg_client_facts_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_client_facts_immutable BEFORE DELETE OR UPDATE ON public.client_facts FOR EACH ROW EXECUTE FUNCTION public.fn_prevent_update_delete();


--
-- Name: voz_ingesta_media_links trg_voz_ingesta_media_links_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_voz_ingesta_media_links_immutable BEFORE DELETE OR UPDATE ON public.voz_ingesta_media_links FOR EACH ROW EXECUTE FUNCTION public.fn_prevent_update_delete();


--
-- Name: voz_ingestas trg_voz_ingestas_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_voz_ingestas_immutable BEFORE DELETE OR UPDATE ON public.voz_ingestas FOR EACH ROW EXECUTE FUNCTION public.fn_prevent_update_delete();


--
-- Name: voz_transcripciones trg_voz_transcripciones_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_voz_transcripciones_immutable BEFORE DELETE OR UPDATE ON public.voz_transcripciones FOR EACH ROW EXECUTE FUNCTION public.fn_prevent_update_delete();


--
-- Name: cerebro_borradores cerebro_borradores_borrador_padre_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_borradores
    ADD CONSTRAINT cerebro_borradores_borrador_padre_id_fkey FOREIGN KEY (borrador_padre_id) REFERENCES public.cerebro_borradores(id);


--
-- Name: cerebro_borradores cerebro_borradores_extraccion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_borradores
    ADD CONSTRAINT cerebro_borradores_extraccion_id_fkey FOREIGN KEY (extraccion_id) REFERENCES public.cerebro_extracciones(id);


--
-- Name: cerebro_correcciones cerebro_correcciones_borrador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_correcciones
    ADD CONSTRAINT cerebro_correcciones_borrador_id_fkey FOREIGN KEY (borrador_id) REFERENCES public.cerebro_borradores(id);


--
-- Name: cerebro_correcciones cerebro_correcciones_borrador_nuevo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_correcciones
    ADD CONSTRAINT cerebro_correcciones_borrador_nuevo_id_fkey FOREIGN KEY (borrador_nuevo_id) REFERENCES public.cerebro_borradores(id);


--
-- Name: cerebro_correcciones cerebro_correcciones_extraccion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_correcciones
    ADD CONSTRAINT cerebro_correcciones_extraccion_id_fkey FOREIGN KEY (extraccion_id) REFERENCES public.cerebro_extracciones(id);


--
-- Name: cerebro_ejecuciones cerebro_ejecuciones_borrador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_ejecuciones
    ADD CONSTRAINT cerebro_ejecuciones_borrador_id_fkey FOREIGN KEY (borrador_id) REFERENCES public.cerebro_borradores(id);


--
-- Name: cerebro_encargos_decisiones cerebro_encargos_decisiones_borrador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_encargos_decisiones
    ADD CONSTRAINT cerebro_encargos_decisiones_borrador_id_fkey FOREIGN KEY (borrador_id) REFERENCES public.cerebro_borradores(id);


--
-- Name: cerebro_extracciones cerebro_extracciones_chat_mensaje_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_extracciones
    ADD CONSTRAINT cerebro_extracciones_chat_mensaje_id_fkey FOREIGN KEY (chat_mensaje_id) REFERENCES public.chat_mensajes(id);


--
-- Name: cerebro_extracciones cerebro_extracciones_transcripcion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_extracciones
    ADD CONSTRAINT cerebro_extracciones_transcripcion_id_fkey FOREIGN KEY (transcripcion_id) REFERENCES public.voz_transcripciones(id);


--
-- Name: cerebro_tareas_internas cerebro_tareas_internas_asignado_a_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_tareas_internas
    ADD CONSTRAINT cerebro_tareas_internas_asignado_a_id_fkey FOREIGN KEY (asignado_a_id) REFERENCES public.panel_users_acl(id);


--
-- Name: cerebro_tareas_internas cerebro_tareas_internas_borrador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_tareas_internas
    ADD CONSTRAINT cerebro_tareas_internas_borrador_id_fkey FOREIGN KEY (borrador_id) REFERENCES public.cerebro_borradores(id);


--
-- Name: cerebro_tareas_internas_eventos cerebro_tareas_internas_eventos_tarea_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_tareas_internas_eventos
    ADD CONSTRAINT cerebro_tareas_internas_eventos_tarea_id_fkey FOREIGN KEY (tarea_id) REFERENCES public.cerebro_tareas_internas(id);


--
-- Name: cerebro_tareas_internas cerebro_tareas_internas_extraccion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cerebro_tareas_internas
    ADD CONSTRAINT cerebro_tareas_internas_extraccion_id_fkey FOREIGN KEY (extraccion_id) REFERENCES public.cerebro_extracciones(id);


--
-- Name: client_fact_supersedes client_fact_supersedes_fact_id_nuevo_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_fact_supersedes
    ADD CONSTRAINT client_fact_supersedes_fact_id_nuevo_fkey FOREIGN KEY (fact_id_nuevo) REFERENCES public.client_facts(id);


--
-- Name: client_fact_supersedes client_fact_supersedes_fact_id_superado_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_fact_supersedes
    ADD CONSTRAINT client_fact_supersedes_fact_id_superado_fkey FOREIGN KEY (fact_id_superado) REFERENCES public.client_facts(id);


--
-- Name: client_facts client_facts_chat_mensaje_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_facts
    ADD CONSTRAINT client_facts_chat_mensaje_id_fkey FOREIGN KEY (chat_mensaje_id) REFERENCES public.chat_mensajes(id);


--
-- Name: client_facts client_facts_cliente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_facts
    ADD CONSTRAINT client_facts_cliente_id_fkey FOREIGN KEY (cliente_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: client_facts client_facts_extraccion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_facts
    ADD CONSTRAINT client_facts_extraccion_id_fkey FOREIGN KEY (extraccion_id) REFERENCES public.cerebro_extracciones(id);


--
-- Name: client_facts client_facts_transcripcion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_facts
    ADD CONSTRAINT client_facts_transcripcion_id_fkey FOREIGN KEY (transcripcion_id) REFERENCES public.voz_transcripciones(id);


--
-- Name: voz_ingesta_media_links voz_ingesta_media_links_cliente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.voz_ingesta_media_links
    ADD CONSTRAINT voz_ingesta_media_links_cliente_id_fkey FOREIGN KEY (cliente_id) REFERENCES public.clients(id);


--
-- Name: voz_ingesta_media_links voz_ingesta_media_links_ingesta_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.voz_ingesta_media_links
    ADD CONSTRAINT voz_ingesta_media_links_ingesta_id_fkey FOREIGN KEY (ingesta_id) REFERENCES public.voz_ingestas(id);


--
-- Name: voz_ingesta_media_links voz_ingesta_media_links_media_asset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.voz_ingesta_media_links
    ADD CONSTRAINT voz_ingesta_media_links_media_asset_id_fkey FOREIGN KEY (media_asset_id) REFERENCES public.media_assets(id);


--
-- Name: voz_trabajos_stt voz_trabajos_stt_ingesta_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.voz_trabajos_stt
    ADD CONSTRAINT voz_trabajos_stt_ingesta_id_fkey FOREIGN KEY (ingesta_id) REFERENCES public.voz_ingestas(id);


--
-- Name: voz_transcripciones voz_transcripciones_ingesta_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.voz_transcripciones
    ADD CONSTRAINT voz_transcripciones_ingesta_id_fkey FOREIGN KEY (ingesta_id) REFERENCES public.voz_ingestas(id);


--
-- Name: voz_transcripciones voz_transcripciones_trabajo_stt_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.voz_transcripciones
    ADD CONSTRAINT voz_transcripciones_trabajo_stt_id_fkey FOREIGN KEY (trabajo_stt_id) REFERENCES public.voz_trabajos_stt(id);


--
-- PostgreSQL database dump complete
--


