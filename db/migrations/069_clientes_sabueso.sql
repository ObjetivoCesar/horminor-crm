-- =====================================================================
-- ORMINORTH - Migracion 069: ciudad, obra frecuente y busqueda Sabueso
-- Motivo: v6.6 agrega filtros por ciudad/sector y ficha editable con
--         direccion de obra frecuente. No se borra ni se inventa data.
-- =====================================================================

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS ciudad TEXT,
    ADD COLUMN IF NOT EXISTS direccion_obra TEXT;

CREATE INDEX IF NOT EXISTS idx_clients_ciudad
    ON clients (lower(ciudad));

CREATE INDEX IF NOT EXISTS idx_clients_obra
    ON clients (lower(direccion_obra));

-- Indice funcional para el buscador normalizado (sin tildes y con
-- equivalencias foneticas basicas). No cambia datos existentes.
CREATE INDEX IF NOT EXISTS idx_clients_sabueso
    ON clients (
        replace(replace(replace(replace(
            translate(lower(coalesce(nombre, '')), 'áéíóúüñ', 'aeiouun'),
        'v', 'b'), 'z', 's'), 'c', 's'), 'll', 'y')
    );
