-- =====================================================================
-- ORMINORTH - Migracion 050: semilla oficial + Centro de Configuracion
--
-- Ratificado por Direccion (2026-11-08):
--   1. El Hito 1 se cierra con una semilla oficial investigada para
--      Orellana / Sucumbios. Las 5 recetas quedan confirmadas y con
--      precio de venta por m3 (sin IVA). Los valores son editables desde
--      el Centro de Configuracion Superadmin: esta migracion solo fija
--      el punto de partida.
--   2. La flota, el stock, la politica de viajes y el reloj termico
--      tambien quedan pre-cargados y son editables en caliente.
--   3. El IVA se guarda como porcentaje aplicable (15% en Ecuador). El
--      precio de la receta esta cargado SIN IVA; el Frontend decide
--      cuando mostrarlo con impuesto.
--
-- Nada de esto se escribe en el codigo: todo vive en PostgreSQL y el
-- Superadmin lo puede cambiar sin reiniciar el servidor.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Columnas comerciales de las recetas
-- ---------------------------------------------------------------------
ALTER TABLE concrete_recipes
    ADD COLUMN IF NOT EXISTS precio_m3    numeric(12,2),
    ADD COLUMN IF NOT EXISTS iva_pct      numeric(5,2) NOT NULL DEFAULT 15.00,
    ADD COLUMN IF NOT EXISTS uso_comercial text;

COMMENT ON COLUMN concrete_recipes.precio_m3 IS
    'Precio de venta por m3 SIN IVA. Editable desde Superadmin > formulas_y_precios.';
COMMENT ON COLUMN concrete_recipes.iva_pct IS
    'Porcentaje de IVA aplicable. Ecuador: 15%. El precio base no lo incluye.';
COMMENT ON COLUMN concrete_recipes.uso_comercial IS
    'Descripcion comercial que usa el bot para explicar la resistencia al cliente.';

-- ---------------------------------------------------------------------
-- 2. Las 5 recetas oficiales (sacos de 50 kg)
--    Fuente: estandar de mercado hormigonero Orellana / Sucumbios,
--    pre-cargado por Direccion el 2026-11-08. Editable en Superadmin.
-- ---------------------------------------------------------------------
INSERT INTO concrete_recipes
    (resistencia, cemento_sacos_m3, arena_m3_m3, ripio_m3_m3,
     agua_litros_m3, retardante_litros_m3, saco_kg, confirmado, fuente,
     precio_m3, iva_pct, uso_comercial)
VALUES
    ('FC-180', 6.500, 0.5600, 0.6800, 190.00, 1.000, 50.00, true,
     'Semilla oficial Orellana/Sucumbios (Direccion, 2026-11-08). Editable en Superadmin.',
     108.00, 15.00, 'Contrapisos, veredas y obras livianas.'),
    ('FC-210', 7.500, 0.5200, 0.6800, 185.00, 1.200, 50.00, true,
     'Semilla oficial Orellana/Sucumbios (Direccion, 2026-11-08). Editable en Superadmin.',
     118.00, 15.00, 'Losas, vigas, columnas residenciales y muros.'),
    ('FC-240', 8.500, 0.5000, 0.6600, 182.00, 1.400, 50.00, true,
     'Semilla oficial Orellana/Sucumbios (Direccion, 2026-11-08). Editable en Superadmin.',
     126.00, 15.00, 'Galpones industriales y pavimentos urbanos.'),
    ('FC-280', 9.500, 0.4800, 0.6500, 178.00, 1.600, 50.00, true,
     'Semilla oficial Orellana/Sucumbios (Direccion, 2026-11-08). Editable en Superadmin.',
     136.00, 15.00, 'Puentes, vias de carga pesada y plataformas.'),
    ('FC-350', 11.000, 0.4500, 0.6200, 172.00, 2.000, 50.00, true,
     'Semilla oficial Orellana/Sucumbios (Direccion, 2026-11-08). Editable en Superadmin.',
     158.00, 15.00, 'Plataformas petroleras y cimentaciones especiales.')
ON CONFLICT (resistencia) DO UPDATE
   SET cemento_sacos_m3     = EXCLUDED.cemento_sacos_m3,
       arena_m3_m3          = EXCLUDED.arena_m3_m3,
       ripio_m3_m3          = EXCLUDED.ripio_m3_m3,
       agua_litros_m3       = EXCLUDED.agua_litros_m3,
       retardante_litros_m3 = EXCLUDED.retardante_litros_m3,
       saco_kg              = EXCLUDED.saco_kg,
       confirmado           = true,
       fuente               = EXCLUDED.fuente,
       precio_m3            = EXCLUDED.precio_m3,
       iva_pct              = EXCLUDED.iva_pct,
       uso_comercial        = EXCLUDED.uso_comercial,
       updated_at           = now();

-- ---------------------------------------------------------------------
-- 3. Stock y costos iniciales de Planta Central El Coca
-- ---------------------------------------------------------------------
UPDATE materials
   SET stock_actual = 3500, stock_minimo = 500, costo_unitario = 8.20,
       updated_at = now()
 WHERE codigo = 'CEMENTO';

UPDATE materials
   SET stock_actual = 450, stock_minimo = 80, costo_unitario = 14.00,
       updated_at = now()
 WHERE codigo = 'ARENA';

UPDATE materials
   SET stock_actual = 550, stock_minimo = 100, costo_unitario = 16.50,
       updated_at = now()
 WHERE codigo = 'RIPIO';

UPDATE materials
   SET stock_actual = 600, stock_minimo = 100, costo_unitario = 3.80,
       updated_at = now()
 WHERE codigo = 'RETARDANTE';

-- ---------------------------------------------------------------------
-- 4. Flota inicial, politica de viajes y reloj termico
-- ---------------------------------------------------------------------
INSERT INTO system_settings (key, value, descripcion) VALUES
    ('flota.mixers',
     '[
        {"codigo": "MIXER-01", "placa": null, "capacidad_m3": 8.0, "chofer_asignado": null, "activo": true},
        {"codigo": "MIXER-02", "placa": null, "capacidad_m3": 8.0, "chofer_asignado": null, "activo": true},
        {"codigo": "MIXER-03", "placa": null, "capacidad_m3": 7.0, "chofer_asignado": null, "activo": true}
      ]'::jsonb,
     'Flota inicial (Direccion, 2026-11-08). Placa y chofer quedan NULL hasta que Julio los entregue. Editable en Superadmin > flota_y_operacion.'),

    ('operacion.politica_redondeo_viajes', '"PARCIAL"'::jsonb,
     'Politica del ultimo viaje: PARCIAL | COMPLETO | UNIFORME. PARCIAL = 52 m3 -> 6x8 + 4 m3. Editable en Superadmin > flota_y_operacion.'),

    ('operacion.reloj_termico_minutos', '150'::jsonb,
     'Ventana maxima de fraguado desde la salida de planta. Editable en Superadmin > flota_y_operacion.'),

    ('operacion.alerta_temprana_minutos_antes', '60'::jsonb,
     'Minutos antes del limite para ALERTA_TEMPRANA (150 - 60 = minuto 90). Editable en Superadmin.'),

    ('operacion.por_vencer_critico_minutos_antes', '30'::jsonb,
     'Minutos antes del limite para POR_VENCER_CRITICO (150 - 30 = minuto 120). Editable en Superadmin.'),

    ('operacion.debounce_segundos', '14'::jsonb,
     'Ventana de agrupacion de mensajes de WhatsApp. Editable en Superadmin > whatsapp_evolution_y_cdn.')
ON CONFLICT (key) DO UPDATE
   SET value = EXCLUDED.value,
       descripcion = EXCLUDED.descripcion,
       actualizado_at = now();

-- ---------------------------------------------------------------------
-- 5. ADN publico de la empresa para el bot (Gate #4)
-- ---------------------------------------------------------------------
INSERT INTO system_settings (key, value, descripcion) VALUES
    ('empresa.bot_publico',
     '{
        "company_name": "Orminorth Hormigones",
        "ruc": null,
        "main_plant_address": "El Coca, Orellana",
        "coverage_zones": ["Orellana", "Sucumbios", "Via Auca", "Via Payamino", "Lago Agrio", "Loreto"],
        "business_hours": null,
        "mobile_plant_pitch": "Instalamos planta movil en sitio para proyectos desde 1,000 m3",
        "bank_accounts": [],
        "extra_services": ["Bomba pluma de hormigon", "Planta movil en campamento", "Hormigon de alta resistencia petrolera"]
      }'::jsonb,
     'ADN publico de Orminorth que usa el bot para responder a leads. RUC, horario y cuentas bancarias quedan NULL/vacios hasta que Julio los entregue. Editable en Superadmin > empresa_bot_publico.')
ON CONFLICT (key) DO UPDATE
   SET value = EXCLUDED.value,
       descripcion = EXCLUDED.descripcion,
       actualizado_at = now();

-- ---------------------------------------------------------------------
-- 6. Umbrales de bodega por planta
-- ---------------------------------------------------------------------
INSERT INTO system_settings (key, value, descripcion) VALUES
    ('bodega.umbrales_por_planta',
     '{
        "PLANTA-COCA": {
          "CEMENTO":    {"stock_actual": 3500, "stock_minimo": 500, "costo_unitario": 8.20},
          "ARENA":      {"stock_actual": 450,  "stock_minimo": 80,  "costo_unitario": 14.00},
          "RIPIO":      {"stock_actual": 550,  "stock_minimo": 100, "costo_unitario": 16.50},
          "RETARDANTE": {"stock_actual": 600,  "stock_minimo": 100, "costo_unitario": 3.80}
        },
        "PLANTA-MOVIL": {}
      }'::jsonb,
     'Umbrales y costos por planta. La tabla materials guarda el consolidado; esta llave permite ajustar por sucursal. Editable en Superadmin > bodega_y_umbrales.')
ON CONFLICT (key) DO UPDATE
   SET value = EXCLUDED.value,
       descripcion = EXCLUDED.descripcion,
       actualizado_at = now();

-- ---------------------------------------------------------------------
-- 7. Finanzas gerenciales y simulador bancario
-- ---------------------------------------------------------------------
INSERT INTO system_settings (key, value, descripcion) VALUES
    ('finanzas.tope_credito_auto', 'null'::jsonb,
     'PENDIENTE: tope de fiado automatico sin clave gerencial. Julio debe fijar el monto; mientras sea null no se autoriza fiado automatico.'),

    ('finanzas.simulador',
     '{
        "pluma_monto_usd": 100000,
        "combo_china_monto_usd": 240000,
        "tasa_anual_pct": 11.2,
        "plazos_meses": [36, 48]
      }'::jsonb,
     'Parametros del Simulador Bancario (PDR seccion 6). Editable en Superadmin > finanzas_y_ases_gerenciales.')
ON CONFLICT (key) DO UPDATE
   SET value = EXCLUDED.value,
       descripcion = EXCLUDED.descripcion,
       actualizado_at = now();

-- ---------------------------------------------------------------------
-- 8. Descripciones legibles para el Superadmin
-- ---------------------------------------------------------------------
UPDATE system_settings
   SET descripcion = 'Configuracion de Evolution API para el webhook y envio de WhatsApp. Editable en Superadmin > whatsapp_evolution_y_cdn.',
       actualizado_at = now()
 WHERE key = 'integraciones.evolution';

UPDATE system_settings
   SET descripcion = 'Storage Zone, host CDN y API key de Bunny.net para evidencias. Editable en Superadmin > whatsapp_evolution_y_cdn.',
       actualizado_at = now()
 WHERE key = 'integraciones.bunny';

UPDATE system_settings
   SET descripcion = 'Roles validos: SUPERADMIN | CAJA_SECRETARIA | BODEGA_PLANTA | CHOFER_MIXER. Mapa telefono -> rol. Editable en Superadmin > directorio_roles_whatsapp.',
       actualizado_at = now()
 WHERE key = 'whatsapp.staff';

UPDATE system_settings
   SET descripcion = 'Codigos PIN de fallback por mensaje (#BODEGA, #CAJA, #ADMIN). Editable en Superadmin > directorio_roles_whatsapp.',
       actualizado_at = now()
 WHERE key = 'whatsapp.codigos_operador';
