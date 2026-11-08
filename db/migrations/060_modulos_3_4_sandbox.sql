-- =====================================================================
-- ORMINORTH / CENTINELA - Modulos 3 y 4 + modo SANDBOX
-- Migracion 060: semillas administrativas, cupo de credito, outbox de
-- sandbox, benchmarks 2025/2026 y parametros de los dashboards.
--
-- Directriz de Arquitectura (2026-11-08): ningun dato externo bloquea el
-- cierre del Hito 3. Todo valor cargado aqui es PROVISIONAL y editable
-- desde el Centro de Configuracion Superadmin.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Cupo de credito por cliente y marca de exceso en la orden
-- ---------------------------------------------------------------------
ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS credit_limit_usd numeric(12,2);

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS provincia text;

ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS excede_cupo_credito boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN clients.credit_limit_usd IS
    'Cupo de fiado acordado con el cliente. NULL = usar el default de finanzas.tope_credito_auto.';
COMMENT ON COLUMN clients.provincia IS
    'Provincia de la obra del cliente (Orellana / Sucumbios). Base de la cuota de mercado del Modulo 4; NULL no se reparte.';
COMMENT ON COLUMN orders.excede_cupo_credito IS
    'true = la orden supero el cupo de credito al momento de crearse. No bloquea la venta; alerta al Centinela.';

-- ---------------------------------------------------------------------
-- 2. Bandeja de salida SANDBOX
--    Cuando Evolution API no esta configurada, todo mensaje saliente se
--    encola aqui y la UI lo muestra. Nunca se finge un envio real.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sandbox_outbox (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    canal       text NOT NULL CHECK (canal IN ('WHATSAPP', 'BUNNY', 'CRM')),
    destino     text NOT NULL,
    tipo        text NOT NULL DEFAULT 'TEXTO'
                CHECK (tipo IN ('TEXTO', 'MEDIA', 'ALERTA')),
    contenido   text NOT NULL,
    metadatos   jsonb NOT NULL DEFAULT '{}'::jsonb,
    estado      text NOT NULL DEFAULT 'ENCOLADO'
                CHECK (estado IN ('ENCOLADO', 'ENTREGADO', 'FALLIDO')),
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_sandbox_outbox_created
    ON sandbox_outbox (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_sandbox_outbox_canal
    ON sandbox_outbox (canal, created_at DESC);

COMMENT ON TABLE sandbox_outbox IS
    'Salida simulada del modo SANDBOX (WhatsApp / Bunny / CRM). Visible en el Superadmin para demos sin credenciales reales.';

-- ---------------------------------------------------------------------
-- 3. ADN publico completo (datos provisionales autorizados por Direccion)
-- ---------------------------------------------------------------------
INSERT INTO system_settings (key, value, descripcion) VALUES
    ('empresa.bot_publico',
     '{
        "company_name": "ORMINORTH HORMIGONES Y PREFABRICADOS S.A.S.",
        "trade_name": "Orminorth Hormigones",
        "ruc": "2290000000001",
        "main_plant_address": "Via Lago Agrio Km 3.5, El Coca - Francisco de Orellana",
        "coverage_zones": ["Orellana", "Sucumbios", "Via Auca", "Via Payamino", "Lago Agrio", "Loreto"],
        "business_hours": "Lunes a Sabado de 07:00 a 18:00 (Despachos especiales 24/7 para proyectos petroleros y viales previa programacion)",
        "mobile_plant_pitch": "Instalamos planta movil en sitio para proyectos desde 1,000 m3",
        "bank_accounts": [
          "Banco Pichincha - Cuenta Corriente #2100XXXXXX - Titular: ORMINORTH",
          "BanEcuador - Cuenta Corriente #300XXXXXXX - Titular: ORMINORTH"
        ],
        "extra_services": ["Bomba pluma de hormigon", "Planta movil en campamento", "Hormigon de alta resistencia petrolera"],
        "dato_provisional": true
      }'::jsonb,
     'ADN publico de Orminorth para el bot y los comprobantes. Datos PROVISIONALES autorizados por Direccion (2026-11-08); editables en Superadmin > empresa_bot_publico.')
ON CONFLICT (key) DO UPDATE
   SET value = EXCLUDED.value,
       descripcion = EXCLUDED.descripcion,
       actualizado_at = now();

-- ---------------------------------------------------------------------
-- 4. Flota con placas y choferes semilla
-- ---------------------------------------------------------------------
INSERT INTO system_settings (key, value, descripcion) VALUES
    ('flota.mixers',
     '[
        {"codigo": "MIXER-01", "placa": "OAA-1024", "capacidad_m3": 8.0, "chofer_asignado": "Pedro Andy", "activo": true},
        {"codigo": "MIXER-02", "placa": "OAA-1088", "capacidad_m3": 8.0, "chofer_asignado": "Carlos Grefa", "activo": true},
        {"codigo": "MIXER-03", "placa": "PBA-4512", "capacidad_m3": 7.0, "chofer_asignado": "Luis Zambrano", "activo": true}
      ]'::jsonb,
     'Flota con placas y choferes SEMILLA (Direccion, 2026-11-08). Editables en Superadmin > flota_y_operacion.')
ON CONFLICT (key) DO UPDATE
   SET value = EXCLUDED.value,
       descripcion = EXCLUDED.descripcion,
       actualizado_at = now();

-- ---------------------------------------------------------------------
-- 5. Directorio de personal semilla y PIN opcional
-- ---------------------------------------------------------------------
INSERT INTO system_settings (key, value, descripcion) VALUES
    ('whatsapp.staff',
     '{
        "+593990000001": {"rol": "SUPERADMIN", "nombre": "Julio Villavicencio", "pin": null},
        "+593990000002": {"rol": "CAJA_SECRETARIA", "nombre": "Caja / Secretaria", "pin": null},
        "+593990000003": {"rol": "BODEGA_PLANTA", "nombre": "Bodega Planta", "pin": null},
        "+593990000101": {"rol": "CHOFER_MIXER", "mixer": "MIXER-01", "nombre": "Pedro Andy", "pin": null},
        "+593990000102": {"rol": "CHOFER_MIXER", "mixer": "MIXER-02", "nombre": "Carlos Grefa", "pin": null},
        "+593990000103": {"rol": "CHOFER_MIXER", "mixer": "MIXER-03", "nombre": "Luis Zambrano", "pin": null}
      }'::jsonb,
     'Telefonos SEMILLA de desarrollo (Direccion, 2026-11-08). Se reemplazan por los reales en Superadmin > directorio_roles_whatsapp sin reiniciar.')
ON CONFLICT (key) DO UPDATE
   SET value = EXCLUDED.value,
       descripcion = EXCLUDED.descripcion,
       actualizado_at = now();

INSERT INTO system_settings (key, value, descripcion) VALUES
    ('whatsapp.codigos_operador',
     '{
        "#BODEGA": "BODEGA_PLANTA",
        "#CAJA": "CAJA_SECRETARIA",
        "#ADMIN": "SUPERADMIN",
        "#M1": "CHOFER_MIXER",
        "#M2": "CHOFER_MIXER",
        "#M3": "CHOFER_MIXER"
      }'::jsonb,
     'Codigos de operador por mensaje. Vigentes (Direccion, 2026-11-08). Editables en Superadmin > directorio_roles_whatsapp.')
ON CONFLICT (key) DO UPDATE
   SET value = EXCLUDED.value,
       descripcion = EXCLUDED.descripcion,
       actualizado_at = now();

INSERT INTO system_settings (key, value, descripcion) VALUES
    ('whatsapp.pin_operador',
     '{"require_pin": false, "pines": {}}'::jsonb,
     'PIN de 4 digitos opcional por operador. Desactivado por defecto para no frenar a los choferes; se activa con un switch en Superadmin.')
ON CONFLICT (key) DO UPDATE
   SET value = EXCLUDED.value,
       descripcion = EXCLUDED.descripcion,
       actualizado_at = now();

-- ---------------------------------------------------------------------
-- 6. Integraciones: modo SANDBOX y valores por defecto
-- ---------------------------------------------------------------------
INSERT INTO system_settings (key, value, descripcion) VALUES
    ('integraciones.evolution',
     '{"url": null, "instancia": "orminorth-main", "api_key": null, "sandbox": true}'::jsonb,
     'Evolution API. En SANDBOX los mensajes salientes se encolan en sandbox_outbox y se ven en la UI. Editable en Superadmin > whatsapp_evolution_y_cdn.')
ON CONFLICT (key) DO UPDATE
   SET value = system_settings.value || EXCLUDED.value,
       descripcion = EXCLUDED.descripcion,
       actualizado_at = now();

INSERT INTO system_settings (key, value, descripcion) VALUES
    ('integraciones.bunny',
     '{"storage_zone": "orminorth-media", "api_key": null, "cdn_host": "https://orminorth.b-cdn.net", "sandbox": true}'::jsonb,
     'Bunny.net. En SANDBOX las evidencias reciben una URL simulada deterministica bajo /sandbox/. Editable en Superadmin > whatsapp_evolution_y_cdn.')
ON CONFLICT (key) DO UPDATE
   SET value = system_settings.value || EXCLUDED.value,
       descripcion = EXCLUDED.descripcion,
       actualizado_at = now();

INSERT INTO system_settings (key, value, descripcion) VALUES
    ('ia.juez',
     '{"model": "gemini-2.5-flash", "modo": "AUTO"}'::jsonb,
     'Modelo del Juez Binario Jeb. Sin GEMINI_API_KEY el sistema usa DeterministicRuleMockJudge y el Centinela informa DETERMINISTIC_FALLBACK.')
ON CONFLICT (key) DO UPDATE
   SET value = EXCLUDED.value,
       descripcion = EXCLUDED.descripcion,
       actualizado_at = now();

-- ---------------------------------------------------------------------
-- 7. Credito y simulador financiero
-- ---------------------------------------------------------------------
INSERT INTO system_settings (key, value, descripcion) VALUES
    ('finanzas.tope_credito_auto',
     '{"enabled": true, "default_credit_limit_usd": 1500.00, "max_overdue_days": 15}'::jsonb,
     'Cupo de fiado automatico. Al excederse, la orden se registra igual y queda marcada excede_cupo_credito=true (alerta, no bloqueo). Editable en Superadmin > finanzas_y_ases_gerenciales.')
ON CONFLICT (key) DO UPDATE
   SET value = EXCLUDED.value,
       descripcion = EXCLUDED.descripcion,
       actualizado_at = now();

INSERT INTO system_settings (key, value, descripcion) VALUES
    ('finanzas.simulador',
     '{
        "pluma_monto_usd": 100000,
        "combo_china_monto_usd": 240000,
        "tasa_anual_pct": 11.2,
        "plazos_meses": [36, 48],
        "margen_neto_m3": 42.50,
        "m3_extra_pluma": 180,
        "m3_extra_combo": 450
      }'::jsonb,
     'Simulador Bancario: amortizacion francesa, 11.2% nominal anual capitalizable mensual, 36/48 meses y margen neto por m3. Editable en Superadmin.')
ON CONFLICT (key) DO UPDATE
   SET value = EXCLUDED.value,
       descripcion = EXCLUDED.descripcion,
       actualizado_at = now();

-- ---------------------------------------------------------------------
-- 8. Cuota de mercado: benchmarks 2025/2026 y precio de valorizacion
-- ---------------------------------------------------------------------
DELETE FROM market_benchmarks WHERE anio IN (2025, 2026);

INSERT INTO market_benchmarks (provincia, anio, demanda_m3, precio_promedio_m3, fuente) VALUES
    ('Orellana',  2025, 120000, NULL, 'Benchmark Direccion 2026-11-08 (demanda anual)'),
    ('Orellana',  2026, 120000, NULL, 'Benchmark Direccion 2026-11-08 (demanda anual)'),
    ('Sucumbios', 2025,  95000, NULL, 'Benchmark Direccion 2026-11-08 (demanda anual)'),
    ('Sucumbios', 2026,  95000, NULL, 'Benchmark Direccion 2026-11-08 (demanda anual)');

INSERT INTO system_settings (key, value, descripcion) VALUES
    ('mercado.valorizacion',
     '{"precio_m3": 118.00, "resistencia": "FC-210", "periodo_default": "12_MESES_MOVILES", "anio_actual": 2026}'::jsonb,
     'Precio con el que se valoriza el mercado de la competencia (FC-210 por defecto) y periodo del selector. Editable en Superadmin > finanzas_y_ases_gerenciales.')
ON CONFLICT (key) DO UPDATE
   SET value = EXCLUDED.value,
       descripcion = EXCLUDED.descripcion,
       actualizado_at = now();

-- ---------------------------------------------------------------------
-- 9. Descripciones legibles
-- ---------------------------------------------------------------------
UPDATE system_settings
   SET descripcion = 'Roles validos: SUPERADMIN | CAJA_SECRETARIA | BODEGA_PLANTA | CHOFER_MIXER. Acepta texto o {"rol","mixer","nombre","pin"}. Editable en Superadmin > directorio_roles_whatsapp.',
       actualizado_at = now()
 WHERE key = 'whatsapp.staff';
