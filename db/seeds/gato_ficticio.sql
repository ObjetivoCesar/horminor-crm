-- Semilla FICTICIA para el bot "Gato" (pruebas del bibliotecario).
-- Base destino: orminorth_gato_test (NUNCA la base real).
-- Todo lleva [FICTICIO] o FICT- para poder borrarlo sin tocar datos reales.
-- Idempotente: limpia lo ficticio antes de insertar.

BEGIN;

DELETE FROM loan_payments
 WHERE liability_id IN (SELECT id FROM financial_liabilities WHERE numero_operacion LIKE 'FICT-%');
DELETE FROM financial_liabilities WHERE numero_operacion LIKE 'FICT-%';
DELETE FROM dispatch_schedule WHERE notas LIKE '[FICTICIO]%';
DELETE FROM payments WHERE referencia LIKE '[FICTICIO]%';
DELETE FROM cash_closures WHERE snapshot->>'origen' = 'FICTICIO';
DELETE FROM orders WHERE notas LIKE '[FICTICIO]%';
DELETE FROM clients WHERE nombre LIKE '%[FICTICIO]%';

-- Clientes ficticios
INSERT INTO clients (id, nombre, constructora, ruc, telefono_whatsapp, estado, provincia, ciudad, direccion_obra, credit_limit_usd)
VALUES
  ('11111111-1111-4111-8111-111111111111', 'Constructora Los Andes [FICTICIO]', 'Los Andes', '1790000001001', '+593990000101', 'ACTIVO', 'ORELLANA', 'El Coca', 'Obra Central [FICTICIO]', 5000.00),
  ('22222222-2222-4222-8222-222222222222', 'Vialcosta Cia. Ltda. [FICTICIO]', 'Vialcosta', '1790000002001', '+593990000102', 'ACTIVO', 'SUCUMBIOS', 'Lago Agrio', 'Via Auca Km 14 [FICTICIO]', 8000.00),
  ('33333333-3333-4333-8333-333333333333', 'Ing. Marco Salazar [FICTICIO]', 'Salazar Construcciones', '1790000003001', '+593990000103', 'ACTIVO', 'ORELLANA', 'El Coca', 'Urbanizacion Norte [FICTICIO]', 3000.00);

-- Ordenes ficticias (sin IVA para simplificar la demo)
INSERT INTO orders (cliente_id, resistencia, volumen_m3, planta_id, forma_pago, precio_m3, estado, creada_por, notas)
VALUES
  ('11111111-1111-4111-8111-111111111111', 'FC-210', 20.00,
   (SELECT id FROM plants WHERE codigo = 'PLANTA-COCA'), 'FIADO', 118.00, 'EN_DESPACHO', 'SECRETARIA',
   '[FICTICIO] Orden de Los Andes'),
  ('22222222-2222-4222-8222-222222222222', 'FC-180', 8.00,
   (SELECT id FROM plants WHERE codigo = 'PLANTA-COCA'), 'TRANSFERENCIA', 108.00, 'COMPLETADA', 'SECRETARIA',
   '[FICTICIO] Orden de Vialcosta'),
  ('33333333-3333-4333-8333-333333333333', 'FC-350', 52.00,
   (SELECT id FROM plants WHERE codigo = 'PLANTA-COCA'), 'ABONO', 158.00, 'EN_DESPACHO', 'SECRETARIA',
   '[FICTICIO] Orden de Salazar');

-- Cobro de Vialcosta (transferencia al Pichincha) y abono de Salazar (efectivo)
INSERT INTO payments (order_id, cliente_id, fecha, tipo_movimiento, metodo, monto, referencia, bolsa, account_id, es_anticipo)
SELECT o.id, o.cliente_id, CURRENT_DATE - 1, 'COBRO', 'TRANSFERENCIA', 864.00,
       '[FICTICIO] Cobro Vialcosta', 'BANCO_GERENCIA',
       (SELECT id FROM accounting_accounts WHERE code = '1102.01'), false
  FROM orders o
 WHERE o.notas = '[FICTICIO] Orden de Vialcosta';

INSERT INTO payments (order_id, cliente_id, fecha, tipo_movimiento, metodo, monto, referencia, bolsa, es_anticipo)
SELECT o.id, o.cliente_id, CURRENT_DATE - 1, 'COBRO', 'EFECTIVO', 2000.00,
       '[FICTICIO] Abono Salazar', 'CAJA_DIARIA', false
  FROM orders o
 WHERE o.notas = '[FICTICIO] Orden de Salazar';

INSERT INTO payments (fecha, tipo_movimiento, metodo, monto, referencia, bolsa)
VALUES (CURRENT_DATE - 1, 'GASTO_CAJA_CHICA', 'EFECTIVO', 40.00, '[FICTICIO] Diesel planta', 'CAJA_DIARIA');

-- Cierre ficticio de ayer
INSERT INTO cash_closures
  (fecha, estado, efectivo_sistema, efectivo_contado, transferencias, fiado_otorgado, caja_chica, diferencia, snapshot, cerrado_por, cerrado_at)
VALUES
  (CURRENT_DATE - 1, 'CERRADO', 2000.00, 1980.00, 864.00, 2360.00, 40.00, -20.00,
   '{"origen": "FICTICIO", "nota": "Cierre de prueba del Gato"}'::jsonb,
   'Secretaria [FICTICIO]', now());

-- Agenda ficticia para manana
INSERT INTO dispatch_schedule
  (order_id, cliente_id, planta_id, mixer_codigo, chofer_nombre, receta_codigo, volumen_m3, fecha_entrega, hora_inicio, direccion_obra, estado, creado_por_rol, notas)
SELECT o.id, o.cliente_id, o.planta_id, 'MIXER-01', 'Pedro [FICTICIO]', o.resistencia, o.volumen_m3,
       CURRENT_DATE + 1, TIME '08:00', 'Obra Central [FICTICIO]', 'PROGRAMADO', 'SECRETARIA',
       '[FICTICIO] Entrega Los Andes'
  FROM orders o
 WHERE o.notas = '[FICTICIO] Orden de Los Andes';

INSERT INTO dispatch_schedule
  (order_id, cliente_id, planta_id, mixer_codigo, chofer_nombre, receta_codigo, volumen_m3, fecha_entrega, hora_inicio, direccion_obra, estado, creado_por_rol, notas)
SELECT o.id, o.cliente_id, o.planta_id, 'MIXER-02', 'Carlos [FICTICIO]', o.resistencia, o.volumen_m3,
       CURRENT_DATE + 1, TIME '10:30', 'Urbanizacion Norte [FICTICIO]', 'PROGRAMADO', 'SECRETARIA',
       '[FICTICIO] Entrega Salazar'
  FROM orders o
 WHERE o.notas = '[FICTICIO] Orden de Salazar';

-- Bancos ficticios
UPDATE bank_accounts
   SET saldo_informado = 15000.00, saldo_informado_at = now(),
       numero_cuenta = '2100FICT01', estado = 'ACTIVA'
 WHERE slug = 'pichincha';

UPDATE bank_accounts
   SET saldo_informado = 3200.00, saldo_informado_at = now(),
       numero_cuenta = '2200FICT02', estado = 'ACTIVA'
 WHERE slug = 'guayaquil';

UPDATE bank_accounts
   SET saldo_informado = NULL, saldo_informado_at = NULL,
       numero_cuenta = '2300FICT03', estado = 'PENDIENTE'
 WHERE slug = 'internacional';

-- Prestamo ficticio del Pichincha
INSERT INTO financial_liabilities
  (entidad_financiera, numero_operacion, fecha_desembolso, monto_original, saldo_capital_actual,
   tasa_interes_anual_pct, cuota_mensual_referencial, plazo_restante_meses, bank_account_id)
VALUES
  ('Banco Pichincha [FICTICIO]', 'FICT-001', CURRENT_DATE - 180, 50000.00, 42000.00,
   11.20, 3283.35, 24, (SELECT id FROM bank_accounts WHERE slug = 'pichincha'));

-- Stock critico ficticio: cemento bajo minimo
UPDATE materials SET stock_actual = 120.000 WHERE codigo = 'CEMENTO';

COMMIT;
