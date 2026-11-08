-- =====================================================================
-- ORMINORTH / CENTINELA - Limpieza de benchmarks heredados
-- Migracion 061: la semilla original (010) dejo Orellana y Sucumbios con
-- anio NULL. La 060 cargo los benchmarks oficiales 2025/2026, pero las
-- filas viejas seguian apareciendo en /api/v1/dashboard/benchmarks.
--
-- Se eliminan solo las filas sin anio de esas dos provincias: cualquier
-- benchmark nuevo con anio explicito se conserva.
-- =====================================================================

DELETE FROM market_benchmarks
 WHERE anio IS NULL
   AND lower(provincia) IN ('orellana', 'sucumbios');
