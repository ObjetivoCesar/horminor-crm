-- =====================================================================
-- ORMINORTH - Migracion 040: ratificacion de arquitectura para el Hito 3
--
-- Ajuste tactico #2 (ratificado 2026-11-08):
--   El PDR solo fija el limite de fraguado en 150 min. En las vias de
--   Orellana avisar a los 120 min (30 antes) es demasiado tarde, asi que
--   se agregan dos umbrales previos configurables:
--       ALERTA_TEMPRANA      -> 60 min antes (minuto 90 del viaje)
--       POR_VENCER_CRITICO   -> 30 min antes (minuto 120 del viaje)
--   El valor de 030 (operacion.umbral_por_vencer_minutos) se conserva
--   como alias legado para no romper nada; el codigo nuevo usa los dos
--   umbrales de esta migracion.
--
-- Identidad de WhatsApp (ratificado 2026-11-08):
--   Primaria: telefono registrado en clients / system_settings.whatsapp.staff.
--   Fallback: codigo de operador escrito en el mensaje (#BODEGA, #CAJA,
--   #ADMIN; #M<n> identifica mixer). Estos codigos son protocolo de
--   comunicacion, no datos de negocio: se guardan en base de datos para
--   poder cambiarlos sin reescribir el bot.
-- =====================================================================

INSERT INTO system_settings (key, value, descripcion) VALUES
    ('operacion.alerta_temprana_minutos_antes', '60'::jsonb,
     'RATIFICADO 2026-11-08. Minutos antes del limite de fraguado para marcar ALERTA_TEMPRANA (150 - 60 = minuto 90 del viaje).'),

    ('operacion.por_vencer_critico_minutos_antes', '30'::jsonb,
     'RATIFICADO 2026-11-08. Minutos antes del limite de fraguado para marcar POR_VENCER_CRITICO (150 - 30 = minuto 120 del viaje).'),

    ('whatsapp.codigos_operador',
     '{"#BODEGA": "BODEGA_PLANTA", "#CAJA": "CAJA_SECRETARIA", "#ADMIN": "SUPERADMIN"}'::jsonb,
     'Fallback de identidad del Modulo 1: codigo escrito en el mensaje cuando el telefono no esta registrado. #M<n> se resuelve aparte como CHOFER_MIXER + mixer MIXER-0n.'),
    ('whatsapp.tiempo_maximo_debounce_segundos', '60'::jsonb,
     'Tope de seguridad de la ventana de agrupacion: si un remitente no deja de escribir, el lote se procesa igual al cumplirse este tope.')
ON CONFLICT (key) DO NOTHING;

UPDATE system_settings
   SET descripcion = 'LEGADO (migracion 030). Alias del umbral POR_VENCER previo a la ratificacion de dos umbrales. El codigo vigente usa operacion.alerta_temprana_minutos_antes y operacion.por_vencer_critico_minutos_antes.',
       actualizado_at = now()
 WHERE key = 'operacion.umbral_por_vencer_minutos';

UPDATE system_settings
   SET descripcion = 'Roles validos: SUPERADMIN | CAJA_SECRETARIA | BODEGA_PLANTA | CHOFER_MIXER. Mapa telefono -> rol (identidad primaria del Modulo 1).',
       actualizado_at = now()
 WHERE key = 'whatsapp.staff';
