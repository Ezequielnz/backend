-- Crear tabla tenant_holidays para overrides custom de holidays por tenant
-- Ejecutar después de create_notifications_ml_schema.sql

CREATE TABLE IF NOT EXISTS tenant_holidays (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES negocios(id) ON DELETE CASCADE,
    holiday_date DATE NOT NULL,
    description TEXT,
    is_recurring BOOLEAN DEFAULT TRUE,  -- TRUE para feriados anuales, FALSE para únicos
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraint for ON CONFLICT
    CONSTRAINT unique_tenant_holiday_date UNIQUE (tenant_id, holiday_date)
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_tenant_holidays_tenant_date
ON tenant_holidays(tenant_id, holiday_date);

CREATE INDEX IF NOT EXISTS idx_tenant_holidays_date
ON tenant_holidays(holiday_date);

-- Políticas RLS
ALTER TABLE tenant_holidays ENABLE ROW LEVEL SECURITY;

-- Política para que solo admins del tenant puedan ver/modificar sus holidays
DROP POLICY IF EXISTS "Tenant admins can manage their holidays" ON tenant_holidays;
CREATE POLICY "Tenant admins can manage their holidays" ON tenant_holidays
    FOR ALL USING (
        tenant_id IN (
            SELECT negocio_id FROM usuarios_negocios
            WHERE usuario_id = auth.uid() AND rol = 'admin'
        )
    );

-- Insertar algunos holidays de ejemplo para Argentina (pueden ser removidos o ajustados)
-- Nacionales fijos
INSERT INTO tenant_holidays (tenant_id, holiday_date, description, is_recurring)
SELECT DISTINCT
    b.id as tenant_id,
    d.holiday_date::DATE,
    d.description,
    TRUE
FROM negocios b
CROSS JOIN (
    VALUES
        ('2024-01-01', 'Año Nuevo'),
        ('2024-03-24', 'Día de la Memoria'),
        ('2024-03-25', 'Día de la Memoria'),
        ('2024-04-02', 'Día del Veterano'),
        ('2024-05-01', 'Día del Trabajo'),
        ('2024-05-25', 'Revolución de Mayo'),
        ('2024-06-20', 'Bandera'),
        ('2024-07-09', 'Independencia'),
        ('2024-08-17', 'Paso a la Inmortalidad de San Martín'),
        ('2024-10-12', 'Día de la Raza'),
        ('2024-12-08', 'Inmaculada Concepción'),
        ('2024-12-25', 'Navidad')
) AS d(holiday_date, description)
ON CONFLICT (tenant_id, holiday_date) DO NOTHING;

-- Nota: Los móviles (Viernes Santo, Carnaval, etc.) se calculan dinámicamente en código
-- Los provinciales se agregan por tenant según necesidad