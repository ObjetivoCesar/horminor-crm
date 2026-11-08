-- =====================================================================
-- ORMINORTH - Migracion 020: recetas de hormigon e inventario base
--
-- !!! ATENCION !!!
-- El PDR NO trae la tabla de dosificaciones. El unico dato numerico
-- disponible es el ejemplo del tracking_payload: 60 sacos y 9.6 L de
-- retardante para 8 m3 de FC-210 (=> 7.5 sacos/m3 y 1.2 L/m3).
-- Por eso FC-210 queda confirmado=false y las demas recetas vacias.
-- El motor de calculo se NIEGA a operar con confirmado=false.
-- =====================================================================

INSERT INTO concrete_recipes
    (resistencia, cemento_sacos_m3, arena_m3_m3, ripio_m3_m3, agua_litros_m3,
     retardante_litros_m3, saco_kg, confirmado, fuente)
VALUES
    ('FC-180', NULL, NULL, NULL, NULL, NULL, NULL, false,
     'PENDIENTE: Julio debe entregar la dosificacion real por m3.'),
    ('FC-210', 7.500, NULL, NULL, NULL, 1.200, NULL, false,
     'DERIVADA del ejemplo del PDR v4.0 (60 sacos / 8 m3 y 9.6 L / 8 m3). NO validada por planta.'),
    ('FC-280', NULL, NULL, NULL, NULL, NULL, NULL, false,
     'PENDIENTE: Julio debe entregar la dosificacion real por m3.'),
    ('FC-350', NULL, NULL, NULL, NULL, NULL, NULL, false,
     'PENDIENTE: Julio debe entregar la dosificacion real por m3.')
ON CONFLICT (resistencia) DO NOTHING;

INSERT INTO materials (codigo, nombre, unidad, stock_actual, stock_minimo, costo_unitario) VALUES
    ('CEMENTO',    'Cemento',              'saco',  NULL, NULL, NULL),
    ('ARENA',      'Arena',                'm3',    NULL, NULL, NULL),
    ('RIPIO',      'Ripio / piedra chispa','m3',    NULL, NULL, NULL),
    ('AGUA',       'Agua',                 'litro', NULL, NULL, NULL),
    ('RETARDANTE', 'Aditivo retardante',   'litro', NULL, NULL, NULL)
ON CONFLICT (codigo) DO NOTHING;
