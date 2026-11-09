-- 065_http_gate_v44.sql
-- Parametros de negocio pendientes y reglas HTTP v4.4.0.
--
-- No edita 063/064. Todos los INSERT son idempotentes y no sobreescriben un
-- valor que Julio/Direccion ya hayan cambiado.

INSERT INTO system_settings (key, value, descripcion) VALUES
    (
        'finanzas.iva_historico_pct',
        'null'::jsonb,
        'v4.4.0: porcentaje de IVA para backfill historico. NULL = no backfillear hasta que Julio confirme.'
    ),
    (
        'finanzas.valoracion_10y',
        '{"estado": "PENDIENTE", "fuente": "finanzas.parametros_contables", "horizon_years": 10}'::jsonb,
        'v4.4.0: la valoracion lee las tasas de finanzas.parametros_contables; si faltan, devuelve la foto real.'
    ),
    (
        'finanzas.dscr',
        '{"estado": "PENDIENTE", "fuente": "finanzas.parametros_contables", "horizon_years": 10}'::jsonb,
        'v4.4.0: el DSCR lee dscr_minimo_banco y las tasas; si faltan, devuelve UNCONFIRMED_FINANCIAL_RATES.'
    ),
    (
        'finanzas.regla_reembolso',
        '{"estado": "CONFIRMADA", "modos": ["CONVERTIR_A_ANTICIPO_CLIENTE", "DEVOLVER_DINERO_CAJA_O_BANCO"]}'::jsonb,
        'v4.4.0: Julio debe indicar el modo al aprobar una anulacion con cobros activos.'
    ),
    (
        'finanzas.nota_credito_compras',
        '{"estado": "FASE_1", "codigo": "PURCHASE_REQUIRES_CREDIT_NOTE"}'::jsonb,
        'v4.4.0: Fase 1 rechaza la correccion por testigo y exige nota de credito; el intent dedicado queda para Fase 2.'
    ),
    (
        'contabilidad.rol_contadora',
        '{"habilitado": true, "rol_efectivo": "CONTADORA"}'::jsonb,
        'v4.4.0: rol CONTADORA separado de SUPERADMIN, con permisos contables y sin aprobar solicitudes.'
    ),
    (
        'inventario.conteo',
        '{"fecha": null, "estado": "PENDIENTE"}'::jsonb,
        'v4.4.0: fecha del ultimo conteo fisico. NULL = SIN_FECHA_CONTEO; no se inventa.'
    ),
    (
        'secretaria.pagos',
        '{"abono_parcial": true, "permitir_anticipo": true, "monto_minimo": "0.01", "validar_saldo": true}'::jsonb,
        'v4.4.0: reglas del endpoint de pagos. Abono parcial y anticipo permitidos; saldo validado.'
    )
ON CONFLICT (key) DO NOTHING;

COMMENT ON COLUMN system_settings.descripcion IS
    'Descripcion operativa. Los valores de negocio viven en value (JSONB), nunca en el codigo.';
