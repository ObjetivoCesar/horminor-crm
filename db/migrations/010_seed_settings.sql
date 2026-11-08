-- =====================================================================
-- ORMINORTH - Migracion 010: parametros maestros (system_settings)
--
-- Regla: aqui solo entra lo que el PDR dice literalmente. Lo que no
-- esta definido se guarda como null o como estructura vacia, con una
-- descripcion que dice "PENDIENTE". Nada de valores inventados.
-- =====================================================================

INSERT INTO system_settings (key, value, descripcion) VALUES
    ('core.zona_horaria',              '"America/Guayaquil"'::jsonb,
     'Zona horaria operativa (PDR: timestamps -05:00).'),
    ('core.moneda',                    '"USD"'::jsonb,
     'Moneda de operacion.'),

    ('operacion.reloj_termico_minutos', '150'::jsonb,
     'PDR 3.2 Gate #1: ventana maxima de fraguado desde salida de planta.'),
    ('operacion.alerta_viaje_sin_llegada_minutos', '90'::jsonb,
     'PDR 4.1.3: viaje en ruta > 90 min sin confirmar llegada = riesgo.'),
    ('operacion.hora_limite_cierre_caja', '"19:00"'::jsonb,
     'PDR 4.1.3: la secretaria debe cerrar caja antes de esta hora.'),
    ('operacion.debounce_segundos',     '14'::jsonb,
     'PDR Modulo 1: agrupacion de mensajes fragmentados en Redis.'),

    ('operacion.politica_redondeo_viajes', '"ultimo_parcial"'::jsonb,
     'PENDIENTE CONFIRMAR. Como se reparte el ultimo viaje cuando el volumen no es multiplo de la capacidad del mixer. Valores: ultimo_parcial | ultimo_completo | distribucion_uniforme.'),
    ('operacion.merma_cemento_pct_alerta', 'null'::jsonb,
     'PENDIENTE. PDR 4.1.3 dice "diferencia anormal" sin cifra. Mientras sea null, el Centinela reporta SIN_UMBRAL en vez de alertar.'),

    ('flota.mixers', '[
        {"codigo": "MIXER-01", "capacidad_m3": 8, "activo": true,
         "fuente": "PDR v4.0, ejemplo de tracking_payload (8 m3)"}
     ]'::jsonb,
     'PENDIENTE CONFIRMAR flota real. El PDR menciona mixers de 7 m3 u 8 m3 pero solo nombra MIXER-01. Agregar aqui, sin tocar codigo.'),

    ('whatsapp.numero_corporativo', 'null'::jsonb,
     'PENDIENTE. Numero unico de WhatsApp corporativo de Orminorth.'),
    ('whatsapp.staff', '{}'::jsonb,
     'PENDIENTE. Mapa telefono -> rol (BODEGUERO | CHOFER | GERENCIA) para que el bot sepa quien habla. Sin esto los Gates #1 y #3 no pueden atribuir autor.'),
    ('whatsapp.grupo_operativo', 'null'::jsonb,
     'PENDIENTE CONFIRMAR. Si la operacion usa un grupo de WhatsApp en vez de numeros individuales.'),

    ('precios.hormigon', '{}'::jsonb,
     'PENDIENTE. Precio por m3 por resistencia. Sin precio, las ordenes quedan con total 0 y el dashboard no calcula facturacion.'),

    ('finanzas.pluma', '[
        {"nombre": "Pluma de hormigon", "monto_usd": 100000, "plazo_meses": 36, "tasa_anual_pct": 11.2},
        {"nombre": "Combo pluma + 2 mixers chinos", "monto_usd": 240000, "plazo_meses": 48, "tasa_anual_pct": 11.2}
     ]'::jsonb,
     'PDR 6, As #2. Escenarios bancarios. Las cuotas/DSCR del documento se usan como prueba de regresion en el Hito 5.'),

    ('integraciones.evolution', '{"url": null, "instancia": null, "api_key": null}'::jsonb,
     'PENDIENTE. Instancia existente de Evolution API (PDR seccion 8.5).'),
    ('integraciones.bunny', '{"storage_zone": null, "cdn_host": null, "api_key": null}'::jsonb,
     'PENDIENTE. Storage Zone y CDN de Bunny.net.'),
    ('integraciones.agency_crm', '{"webhook_url": null}'::jsonb,
     'PENDIENTE. URL real del webhook del CRM Central (el PDR trae crm-tu-empresa.com como marcador).')
ON CONFLICT (key) DO NOTHING;

INSERT INTO plants (codigo, nombre, tipo, ubicacion) VALUES
    ('PLANTA-COCA',  'Planta Fija El Coca',       'FIJA',  'El Coca, Orellana'),
    ('PLANTA-MOVIL', 'Planta Movil Campamento',   'MOVIL', NULL)
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO market_benchmarks (provincia, anio, demanda_m3, precio_promedio_m3, fuente) VALUES
    ('Orellana',   NULL, 120000, NULL, 'PDR v4.0 seccion 6 (anio no especificado)'),
    ('Sucumbios',  NULL,  95000, NULL, 'PDR v4.0 seccion 6 (anio no especificado)')
ON CONFLICT DO NOTHING;
