-- 066_iva_default_v44.sql
-- v4.4.0: las ventas nuevas solo llevan IVA si el contrato envia
-- aplica_iva=true. El panel ya lo envia; los candados tambien lo hacen para
-- conservar la cartera historica verificada de $55,043.60.
--
-- No edita 065 (ya aplicada). Es una migracion nueva e idempotente.

UPDATE system_settings
   SET value = 'false'::jsonb,
       actualizado_at = now()
 WHERE key = 'finanzas.iva_default_aplica'
   AND value = 'true'::jsonb;
