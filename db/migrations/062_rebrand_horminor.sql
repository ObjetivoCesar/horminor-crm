-- HORMINOR / CENTINELA - Migracion 062: correccion de marca y datos publicos
--
-- El cliente confirmo que el nombre comercial es HORMINOR (no Orminorth).
-- Las migraciones 050 y 060 ya estaban aplicadas y no se editan: esta
-- migracion corrige el ADN publico y el host de evidencias sin reiniciar.
-- Los datos siguen siendo PROVISIONALES hasta que Julio entregue los reales.

UPDATE system_settings
SET value = jsonb_set(
      jsonb_set(
        jsonb_set(
          value,
          '{company_name}',
          to_jsonb('HORMINOR HORMIGONES Y PREFABRICADOS S.A.S.'::text)
        ),
        '{trade_name}',
        to_jsonb('Horminor Hormigones'::text)
      ),
      '{bank_accounts}',
      COALESCE(
        (
          SELECT jsonb_agg(to_jsonb(replace(cuenta, 'ORMINORTH', 'HORMINOR')))
          FROM jsonb_array_elements_text(value->'bank_accounts') AS cuenta
        ),
        '[]'::jsonb
      )
    ),
    descripcion = 'ADN publico de Horminor para el bot y los comprobantes. Datos PROVISIONALES autorizados por Direccion (2026-11-08); editables en Superadmin > empresa_bot_publico.',
    actualizado_at = now()
WHERE key = 'empresa.bot_publico';

UPDATE system_settings
SET value = jsonb_set(
      jsonb_set(
        value,
        '{storage_zone}',
        to_jsonb('horminor-media'::text)
      ),
      '{cdn_host}',
      to_jsonb('https://horminor.b-cdn.net'::text)
    ),
    actualizado_at = now()
WHERE key = 'integraciones.bunny';
