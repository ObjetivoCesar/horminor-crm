-- =====================================================================
-- ORMINORTH / CENTINELA - Modulo 0: Nucleo de Datos y Configuracion
-- Migracion 001: esquema base (12 tablas + vistas de contrato)
--
-- NOTA: el PDR dice "10 tablas" pero no las enumera. Este esquema
-- implementa 12 (10 de negocio + market_benchmarks + error_logs).
-- Ver docs/00_DECISIONES_PENDIENTES.md antes de tocar nada.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Parametros maestros (nada de recetas, precios o telefonos en codigo)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_settings (
    key             text PRIMARY KEY,
    value           jsonb NOT NULL,
    descripcion     text,
    actualizado_at  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE system_settings IS
    'Tabla maestra de parametros. El codigo solo conoce las llaves, nunca los valores.';

-- ---------------------------------------------------------------------
-- 2. Plantas (fija / movil). Agregar planta = una fila nueva.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS plants (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo      text NOT NULL UNIQUE,
    nombre      text NOT NULL,
    tipo        text NOT NULL CHECK (tipo IN ('FIJA', 'MOVIL')),
    ubicacion   text,
    activa      boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 3. Recetas de hormigon por m3.
--    Un campo NULL significa "dato no entregado por el cliente".
--    confirmado = false => el motor de calculo SE NIEGA a usarla.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS concrete_recipes (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    resistencia            text NOT NULL UNIQUE,
    cemento_sacos_m3       numeric(8,3),
    arena_m3_m3            numeric(8,4),
    ripio_m3_m3            numeric(8,4),
    agua_litros_m3         numeric(8,2),
    retardante_litros_m3   numeric(8,3),
    saco_kg                numeric(6,2),
    confirmado             boolean NOT NULL DEFAULT false,
    fuente                 text,
    updated_at             timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 4. Clientes (ACTIVO = cliente, PROSPECTO = lead del Gate #4)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clients (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre              text NOT NULL,
    constructora        text,
    ruc                 text,
    telefono_whatsapp   text UNIQUE,      -- identificador en el bot
    estado              text NOT NULL DEFAULT 'ACTIVO'
                        CHECK (estado IN ('ACTIVO', 'PROSPECTO', 'INACTIVO')),
    notas               text,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_clients_estado ON clients (estado);
CREATE INDEX IF NOT EXISTS ix_clients_busqueda
    ON clients (lower(nombre), lower(coalesce(constructora, '')));

-- ---------------------------------------------------------------------
-- 5. Ordenes
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    numero        bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    cliente_id    uuid NOT NULL REFERENCES clients (id),
    resistencia   text NOT NULL REFERENCES concrete_recipes (resistencia),
    volumen_m3    numeric(10,2) NOT NULL CHECK (volumen_m3 > 0),
    planta_id     uuid NOT NULL REFERENCES plants (id),
    forma_pago    text NOT NULL
                  CHECK (forma_pago IN ('EFECTIVO', 'TRANSFERENCIA', 'ABONO', 'FIADO')),
    precio_m3     numeric(10,2) CHECK (precio_m3 IS NULL OR precio_m3 >= 0),
    total         numeric(12,2)
                  GENERATED ALWAYS AS (round(volumen_m3 * precio_m3, 2)) STORED,
    estado        text NOT NULL DEFAULT 'CONFIRMADA'
                  CHECK (estado IN ('BORRADOR', 'CONFIRMADA', 'EN_DESPACHO', 'COMPLETADA', 'ANULADA')),
    creada_por    text,
    notas         text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_orders_cliente  ON orders (cliente_id);
CREATE INDEX IF NOT EXISTS ix_orders_created  ON orders (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_orders_planta   ON orders (planta_id);

-- ---------------------------------------------------------------------
-- 6. Viajes de mixer. El JSONB (tracking_payload) es EL contrato.
--    Las columnas planas son solo proyeccion para indexar/consultar y
--    las mantiene un trigger: ningun modulo debe escribirlas a mano.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mixer_dispatches (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id            uuid NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    viaje_numero        integer NOT NULL CHECK (viaje_numero > 0),
    total_viajes_orden  integer NOT NULL CHECK (total_viajes_orden > 0),
    mixer_codigo        text,
    chofer_nombre       text,
    volumen_m3          numeric(6,2) NOT NULL CHECK (volumen_m3 > 0),
    estado_actual       text NOT NULL DEFAULT 'PROGRAMADO',
    tracking_payload    jsonb NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (order_id, viaje_numero)
);

CREATE INDEX IF NOT EXISTS ix_dispatch_order  ON mixer_dispatches (order_id);
CREATE INDEX IF NOT EXISTS ix_dispatch_estado ON mixer_dispatches (estado_actual);
CREATE INDEX IF NOT EXISTS ix_dispatch_payload ON mixer_dispatches USING gin (tracking_payload);

CREATE OR REPLACE FUNCTION fn_dispatch_project() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.tracking_payload IS NULL THEN
        RAISE EXCEPTION 'tracking_payload es obligatorio en mixer_dispatches';
    END IF;

    -- El payload manda; las columnas solo reflejan.
    NEW.viaje_numero       := COALESCE((NEW.tracking_payload ->> 'viaje_numero')::integer,
                                       NEW.viaje_numero);
    NEW.total_viajes_orden := COALESCE((NEW.tracking_payload ->> 'total_viajes_orden')::integer,
                                       NEW.total_viajes_orden);
    NEW.volumen_m3         := COALESCE((NEW.tracking_payload ->> 'volumen_m3')::numeric,
                                       NEW.volumen_m3);
    NEW.mixer_codigo       := COALESCE(NEW.tracking_payload ->> 'mixer_codigo',
                                       NEW.mixer_codigo);
    NEW.chofer_nombre      := COALESCE(NEW.tracking_payload ->> 'chofer_nombre',
                                       NEW.chofer_nombre);
    NEW.estado_actual      := COALESCE(NEW.tracking_payload ->> 'estado_actual',
                                       NEW.estado_actual);
    NEW.updated_at         := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_dispatch_project ON mixer_dispatches;
CREATE TRIGGER trg_dispatch_project
    BEFORE INSERT OR UPDATE ON mixer_dispatches
    FOR EACH ROW EXECUTE FUNCTION fn_dispatch_project();

-- ---------------------------------------------------------------------
-- 7. Materiales / stock (unidades: saco, m3, litro)
--    stock_actual NULL = inventario no levantado todavia (no inventar 0)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS materials (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo          text NOT NULL UNIQUE,
    nombre          text NOT NULL,
    unidad          text NOT NULL CHECK (unidad IN ('saco', 'm3', 'litro', 'kg')),
    stock_actual    numeric(12,3),
    stock_minimo    numeric(12,3),
    costo_unitario  numeric(10,4),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 8. Kardex: movimientos teoricos (receta) y reales (bodega)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS inventory_movements (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    material_id   uuid NOT NULL REFERENCES materials (id),
    tipo          text NOT NULL
                  CHECK (tipo IN ('TEORICO', 'REAL', 'COMPRA', 'AJUSTE')),
    cantidad      numeric(12,3) NOT NULL,   -- con signo: + entra, - sale
    order_id      uuid REFERENCES orders (id) ON DELETE SET NULL,
    dispatch_id   uuid REFERENCES mixer_dispatches (id) ON DELETE SET NULL,
    referencia    text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_invmov_material ON inventory_movements (material_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_invmov_order    ON inventory_movements (order_id);

-- ---------------------------------------------------------------------
-- 9. Cobros y movimientos de caja
--    FIADO no es efectivo: es credito otorgado (se reporta aparte).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS payments (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id         uuid REFERENCES orders (id) ON DELETE SET NULL,
    cliente_id       uuid NOT NULL REFERENCES clients (id),
    fecha            date NOT NULL,
    tipo_movimiento  text NOT NULL
                     CHECK (tipo_movimiento IN ('COBRO', 'GASTO_CAJA_CHICA')),
    metodo           text NOT NULL
                     CHECK (metodo IN ('EFECTIVO', 'TRANSFERENCIA', 'FIADO')),
    monto            numeric(12,2) NOT NULL CHECK (monto > 0),
    referencia       text,
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_payments_fecha   ON payments (fecha);
CREATE INDEX IF NOT EXISTS ix_payments_cliente ON payments (cliente_id);

-- ---------------------------------------------------------------------
-- 10. Cierre de caja diario (snapshot inmutable por fecha)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cash_closures (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    fecha             date NOT NULL UNIQUE,
    estado            text NOT NULL DEFAULT 'CERRADO'
                      CHECK (estado IN ('ABIERTO', 'CERRADO', 'REABIERTO')),
    efectivo_sistema  numeric(12,2) NOT NULL DEFAULT 0,
    efectivo_contado  numeric(12,2),
    transferencias    numeric(12,2) NOT NULL DEFAULT 0,
    fiado_otorgado    numeric(12,2) NOT NULL DEFAULT 0,
    caja_chica        numeric(12,2) NOT NULL DEFAULT 0,
    diferencia        numeric(12,2),
    snapshot          jsonb NOT NULL DEFAULT '{}'::jsonb,
    cerrado_por       text,
    cerrado_at        timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 11. Benchmarks de mercado (As #1, Orellana / Sucumbios)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market_benchmarks (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provincia           text NOT NULL,
    anio                integer,          -- NULL = el PDR no fija el anio
    demanda_m3          numeric(12,2) NOT NULL,
    precio_promedio_m3  numeric(10,2),
    fuente              text,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_benchmarks_prov_anio
    ON market_benchmarks (provincia, coalesce(anio, 0));

-- ---------------------------------------------------------------------
-- 12. Errores y eventos (Centinela)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS error_logs (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nivel       text NOT NULL CHECK (nivel IN ('INFO', 'WARN', 'ERROR', 'CRITICAL')),
    origen      text NOT NULL,
    mensaje     text NOT NULL,
    contexto    jsonb,
    order_id    uuid,
    dispatch_id uuid,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_error_logs_created ON error_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_error_logs_nivel   ON error_logs (nivel, created_at DESC);

-- =====================================================================
-- VISTAS DE CONTRATO (lo que consultan los modulos 3, 4 y 5)
-- =====================================================================

CREATE OR REPLACE VIEW v_dispatch_timeline AS
SELECT
    d.id,
    d.order_id,
    o.numero                                         AS orden_numero,
    c.nombre                                         AS cliente,
    o.resistencia,
    p.nombre                                         AS planta,
    d.viaje_numero,
    d.total_viajes_orden,
    d.mixer_codigo,
    d.chofer_nombre,
    d.volumen_m3,
    d.estado_actual,
    (d.tracking_payload #>> '{juez_binario_jeb,despacho_validado}')::boolean        AS despacho_validado,
    (d.tracking_payload #>> '{juez_binario_jeb,recepcion_cliente_validada}')::boolean AS recepcion_validada,
    (d.tracking_payload #>> '{juez_binario_jeb,incidencia_detectada}')::boolean      AS incidencia_detectada,
    (d.tracking_payload #>> '{tiempos_forenses,dosificado_planta}')::timestamptz      AS dosificado_planta,
    (d.tracking_payload #>> '{tiempos_forenses,salida_planta}')::timestamptz          AS salida_planta,
    (d.tracking_payload #>> '{tiempos_forenses,limite_termico_fraguado}')::timestamptz AS limite_termico_fraguado,
    (d.tracking_payload #>> '{tiempos_forenses,llegada_obra_chofer}')::timestamptz    AS llegada_obra_chofer,
    (d.tracking_payload #>> '{tiempos_forenses,confirmacion_whatsapp_cliente}')::timestamptz
                                                     AS confirmacion_whatsapp_cliente,
    (d.tracking_payload #>> '{consumo_materiales,cemento_sacos_teorico}')::numeric    AS cemento_sacos_teorico,
    (d.tracking_payload #>> '{consumo_materiales,cemento_sacos_real}')::numeric       AS cemento_sacos_real,
    (d.tracking_payload #>> '{consumo_materiales,retardante_litros}')::numeric        AS retardante_litros,
    d.tracking_payload
FROM mixer_dispatches d
JOIN orders  o ON o.id = d.order_id
JOIN clients c ON c.id = o.cliente_id
JOIN plants  p ON p.id = o.planta_id;

CREATE OR REPLACE VIEW v_cliente_saldo AS
SELECT
    c.id,
    c.nombre,
    c.estado,
    COALESCE(SUM(o.volumen_m3) FILTER (WHERE o.estado <> 'ANULADA'), 0)  AS total_m3,
    COALESCE(SUM(o.total)      FILTER (WHERE o.estado <> 'ANULADA'), 0)  AS total_facturado,
    COALESCE((
        SELECT SUM(p.monto) FROM payments p
        WHERE p.cliente_id = c.id
          AND p.tipo_movimiento = 'COBRO'
          AND p.metodo <> 'FIADO'
    ), 0)                                                                AS total_cobrado,
    COALESCE((
        SELECT SUM(p.monto) FROM payments p
        WHERE p.cliente_id = c.id AND p.metodo = 'FIADO'
    ), 0)                                                                AS total_fiado,
    COALESCE(SUM(o.total) FILTER (WHERE o.estado <> 'ANULADA'), 0)
      - COALESCE((
            SELECT SUM(p.monto) FROM payments p
            WHERE p.cliente_id = c.id
              AND p.tipo_movimiento = 'COBRO'
              AND p.metodo = 'FIADO'
        ), 0)                                                            AS saldo_pendiente
FROM clients c
LEFT JOIN orders o ON o.cliente_id = c.id
GROUP BY c.id;

CREATE OR REPLACE VIEW v_inventario AS
SELECT
    m.id,
    m.codigo,
    m.nombre,
    m.unidad,
    m.stock_actual,
    m.stock_minimo,
    CASE
        WHEN m.stock_actual IS NULL THEN 'SIN_LEVANTAR'
        WHEN m.stock_minimo IS NULL THEN 'SIN_UMBRAL'
        WHEN m.stock_actual <= m.stock_minimo THEN 'CRITICO'
        ELSE 'OK'
    END AS estado
FROM materials m;
