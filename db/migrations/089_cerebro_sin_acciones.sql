-- =====================================================================
-- ORMINORTH - Migracion 089: el borrador sin acciones tambien existe
-- Motivo: el compilador devuelve SIN_ACCIONES cuando el dictado no pide
--         nada ejecutable (una consulta pura). El endpoint guarda ese
--         borrador para que quede el registro de lo que se entendio, pero
--         el CHECK de la 085 no incluia ese estado y la peticion fallaba.
--         No se edita la 085: se amplia el CHECK con una migracion nueva.
-- =====================================================================

ALTER TABLE cerebro_borradores
    DROP CONSTRAINT IF EXISTS cerebro_borradores_estado_check;

ALTER TABLE cerebro_borradores
    ADD CONSTRAINT cerebro_borradores_estado_check CHECK (
        estado IN (
            'SIN_ACCIONES',
            'PENDIENTE_CONFIRMACION',
            'REQUIERE_ACLARACION',
            'CONFIRMADO',
            'RECHAZADO',
            'SUPERADO_POR_CORRECCION',
            'EJECUTADO',
            'ERROR_EJECUCION'
        )
    );

COMMENT ON CONSTRAINT cerebro_borradores_estado_check ON cerebro_borradores IS
    'Estados del borrador. SIN_ACCIONES = el dictado no pide nada ejecutable; se guarda igual para dejar constancia.';
