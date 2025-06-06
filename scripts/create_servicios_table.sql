-- Crear tabla de servicios
CREATE TABLE IF NOT EXISTS servicios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    negocio_id UUID NOT NULL REFERENCES negocios(id) ON DELETE CASCADE,
    nombre VARCHAR(100) NOT NULL,
    descripcion TEXT,
    precio DECIMAL(10,2) NOT NULL CHECK (precio > 0),
    duracion_minutos INTEGER CHECK (duracion_minutos >= 0),
    categoria_id UUID REFERENCES categorias(id) ON DELETE SET NULL,
    activo BOOLEAN DEFAULT true,
    creado_en TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    actualizado_en TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Crear índices para servicios
CREATE INDEX IF NOT EXISTS idx_servicios_negocio_id ON servicios(negocio_id);
CREATE INDEX IF NOT EXISTS idx_servicios_nombre ON servicios(nombre);
CREATE INDEX IF NOT EXISTS idx_servicios_categoria_id ON servicios(categoria_id);
CREATE INDEX IF NOT EXISTS idx_servicios_activo ON servicios(activo);

-- Crear trigger para actualizar timestamp
CREATE OR REPLACE FUNCTION update_servicios_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.actualizado_en = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_servicios_updated_at
    BEFORE UPDATE ON servicios
    FOR EACH ROW
    EXECUTE FUNCTION update_servicios_updated_at();

-- Habilitar RLS en la tabla
ALTER TABLE servicios ENABLE ROW LEVEL SECURITY;

-- Políticas RLS para servicios
-- Los usuarios pueden ver servicios de sus negocios
CREATE POLICY "Users can view services from their businesses" ON servicios
    FOR SELECT USING (
        negocio_id IN (
            SELECT nu.negocio_id 
            FROM negocio_usuarios nu 
            WHERE nu.usuario_id = auth.uid()
        )
    );

-- Los usuarios pueden insertar servicios en sus negocios
CREATE POLICY "Users can insert services in their businesses" ON servicios
    FOR INSERT WITH CHECK (
        negocio_id IN (
            SELECT nu.negocio_id 
            FROM negocio_usuarios nu 
            WHERE nu.usuario_id = auth.uid()
        )
    );

-- Los usuarios pueden actualizar servicios de sus negocios
CREATE POLICY "Users can update services from their businesses" ON servicios
    FOR UPDATE USING (
        negocio_id IN (
            SELECT nu.negocio_id 
            FROM negocio_usuarios nu 
            WHERE nu.usuario_id = auth.uid()
        )
    );

-- Los usuarios pueden eliminar servicios de sus negocios
CREATE POLICY "Users can delete services from their businesses" ON servicios
    FOR DELETE USING (
        negocio_id IN (
            SELECT nu.negocio_id 
            FROM negocio_usuarios nu 
            WHERE nu.usuario_id = auth.uid()
        )
    );

-- Comentarios para documentación
COMMENT ON TABLE servicios IS 'Tabla para almacenar los servicios que ofrece cada negocio';
COMMENT ON COLUMN servicios.duracion_minutos IS 'Duración estimada del servicio en minutos'; 