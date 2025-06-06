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

-- Crear tabla de suscripciones
CREATE TABLE IF NOT EXISTS suscripciones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    negocio_id UUID NOT NULL REFERENCES negocios(id) ON DELETE CASCADE,
    cliente_id UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    servicio_id UUID NOT NULL REFERENCES servicios(id) ON DELETE CASCADE,
    nombre VARCHAR(100) NOT NULL,
    descripcion TEXT,
    precio_mensual DECIMAL(10,2) NOT NULL CHECK (precio_mensual > 0),
    tipo VARCHAR(20) NOT NULL DEFAULT 'mensual' CHECK (tipo IN ('mensual', 'trimestral', 'semestral', 'anual')),
    estado VARCHAR(20) NOT NULL DEFAULT 'activa' CHECK (estado IN ('activa', 'pausada', 'cancelada', 'vencida')),
    fecha_inicio TIMESTAMP WITH TIME ZONE NOT NULL,
    fecha_fin TIMESTAMP WITH TIME ZONE,
    fecha_proximo_pago TIMESTAMP WITH TIME ZONE,
    activa BOOLEAN DEFAULT true,
    creado_en TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    actualizado_en TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Crear índices para suscripciones
CREATE INDEX IF NOT EXISTS idx_suscripciones_negocio_id ON suscripciones(negocio_id);
CREATE INDEX IF NOT EXISTS idx_suscripciones_cliente_id ON suscripciones(cliente_id);
CREATE INDEX IF NOT EXISTS idx_suscripciones_servicio_id ON suscripciones(servicio_id);
CREATE INDEX IF NOT EXISTS idx_suscripciones_estado ON suscripciones(estado);
CREATE INDEX IF NOT EXISTS idx_suscripciones_fecha_proximo_pago ON suscripciones(fecha_proximo_pago);

-- Crear trigger para actualizar timestamp
CREATE OR REPLACE FUNCTION update_suscripciones_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.actualizado_en = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_suscripciones_updated_at
    BEFORE UPDATE ON suscripciones
    FOR EACH ROW
    EXECUTE FUNCTION update_suscripciones_updated_at();

-- Habilitar RLS en las tablas
ALTER TABLE servicios ENABLE ROW LEVEL SECURITY;
ALTER TABLE suscripciones ENABLE ROW LEVEL SECURITY;

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

-- Políticas RLS para suscripciones
-- Los usuarios pueden ver suscripciones de sus negocios
CREATE POLICY "Users can view subscriptions from their businesses" ON suscripciones
    FOR SELECT USING (
        negocio_id IN (
            SELECT nu.negocio_id 
            FROM negocio_usuarios nu 
            WHERE nu.usuario_id = auth.uid()
        )
    );

-- Los usuarios pueden insertar suscripciones en sus negocios
CREATE POLICY "Users can insert subscriptions in their businesses" ON suscripciones
    FOR INSERT WITH CHECK (
        negocio_id IN (
            SELECT nu.negocio_id 
            FROM negocio_usuarios nu 
            WHERE nu.usuario_id = auth.uid()
        )
    );

-- Los usuarios pueden actualizar suscripciones de sus negocios
CREATE POLICY "Users can update subscriptions from their businesses" ON suscripciones
    FOR UPDATE USING (
        negocio_id IN (
            SELECT nu.negocio_id 
            FROM negocio_usuarios nu 
            WHERE nu.usuario_id = auth.uid()
        )
    );

-- Los usuarios pueden eliminar suscripciones de sus negocios
CREATE POLICY "Users can delete subscriptions from their businesses" ON suscripciones
    FOR DELETE USING (
        negocio_id IN (
            SELECT nu.negocio_id 
            FROM negocio_usuarios nu 
            WHERE nu.usuario_id = auth.uid()
        )
    );

-- Comentarios para documentación
COMMENT ON TABLE servicios IS 'Tabla para almacenar los servicios que ofrece cada negocio';
COMMENT ON TABLE suscripciones IS 'Tabla para almacenar las suscripciones de clientes a servicios';

COMMENT ON COLUMN servicios.duracion_minutos IS 'Duración estimada del servicio en minutos';
COMMENT ON COLUMN suscripciones.tipo IS 'Tipo de suscripción: mensual, trimestral, semestral, anual';
COMMENT ON COLUMN suscripciones.estado IS 'Estado de la suscripción: activa, pausada, cancelada, vencida';
COMMENT ON COLUMN suscripciones.fecha_proximo_pago IS 'Fecha del próximo pago de la suscripción'; 