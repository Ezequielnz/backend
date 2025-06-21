-- Crear tabla de ventas
CREATE TABLE IF NOT EXISTS ventas (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    negocio_id UUID NOT NULL REFERENCES negocios(id) ON DELETE CASCADE,
    cliente_id UUID REFERENCES clientes(id) ON DELETE SET NULL,
    medio_pago VARCHAR(50) NOT NULL CHECK (medio_pago IN ('efectivo', 'tarjeta', 'transferencia')),
    total DECIMAL(10,2) NOT NULL CHECK (total > 0),
    fecha TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    observaciones TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Crear tabla de detalles de venta
CREATE TABLE IF NOT EXISTS venta_detalle (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    venta_id UUID NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
    producto_id UUID NOT NULL REFERENCES productos(id) ON DELETE RESTRICT,
    cantidad INTEGER NOT NULL CHECK (cantidad > 0),
    precio_unitario DECIMAL(10,2) NOT NULL CHECK (precio_unitario >= 0),
    subtotal DECIMAL(10,2) NOT NULL CHECK (subtotal >= 0),
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Índices para mejorar rendimiento
CREATE INDEX IF NOT EXISTS idx_ventas_negocio_id ON ventas(negocio_id);
CREATE INDEX IF NOT EXISTS idx_ventas_cliente_id ON ventas(cliente_id);
CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha);
CREATE INDEX IF NOT EXISTS idx_venta_detalle_venta_id ON venta_detalle(venta_id);
CREATE INDEX IF NOT EXISTS idx_venta_detalle_producto_id ON venta_detalle(producto_id);

-- Trigger para actualizar updated_at en ventas
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_ventas_updated_at 
    BEFORE UPDATE ON ventas 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Habilitar RLS en ambas tablas
ALTER TABLE ventas ENABLE ROW LEVEL SECURITY;
ALTER TABLE venta_detalle ENABLE ROW LEVEL SECURITY;

-- Políticas RLS para tabla ventas
-- Los usuarios pueden ver ventas de sus negocios
CREATE POLICY "Users can view sales from their businesses" ON ventas
    FOR SELECT USING (
        negocio_id IN (
            SELECT nu.negocio_id 
            FROM negocio_usuarios nu 
            WHERE nu.usuario_id = auth.uid()
        )
    );

-- Los usuarios pueden crear ventas en sus negocios
CREATE POLICY "Users can create sales in their businesses" ON ventas
    FOR INSERT WITH CHECK (
        negocio_id IN (
            SELECT nu.negocio_id 
            FROM negocio_usuarios nu 
            WHERE nu.usuario_id = auth.uid()
        )
    );

-- Los usuarios pueden actualizar ventas de sus negocios
CREATE POLICY "Users can update sales from their businesses" ON ventas
    FOR UPDATE USING (
        negocio_id IN (
            SELECT nu.negocio_id 
            FROM negocio_usuarios nu 
            WHERE nu.usuario_id = auth.uid()
        )
    );

-- Los usuarios pueden eliminar ventas de sus negocios
CREATE POLICY "Users can delete sales from their businesses" ON ventas
    FOR DELETE USING (
        negocio_id IN (
            SELECT nu.negocio_id 
            FROM negocio_usuarios nu 
            WHERE nu.usuario_id = auth.uid()
        )
    );

-- Políticas RLS para tabla venta_detalle
-- Los usuarios pueden ver detalles de ventas de sus negocios
CREATE POLICY "Users can view sale details from their businesses" ON venta_detalle
    FOR SELECT USING (
        venta_id IN (
            SELECT v.id 
            FROM ventas v 
            WHERE v.negocio_id IN (
                SELECT nu.negocio_id 
                FROM negocio_usuarios nu 
                WHERE nu.usuario_id = auth.uid()
            )
        )
    );

-- Los usuarios pueden crear detalles de ventas en sus negocios
CREATE POLICY "Users can create sale details in their businesses" ON venta_detalle
    FOR INSERT WITH CHECK (
        venta_id IN (
            SELECT v.id 
            FROM ventas v 
            WHERE v.negocio_id IN (
                SELECT nu.negocio_id 
                FROM negocio_usuarios nu 
                WHERE nu.usuario_id = auth.uid()
            )
        )
    );

-- Los usuarios pueden actualizar detalles de ventas de sus negocios
CREATE POLICY "Users can update sale details from their businesses" ON venta_detalle
    FOR UPDATE USING (
        venta_id IN (
            SELECT v.id 
            FROM ventas v 
            WHERE v.negocio_id IN (
                SELECT nu.negocio_id 
                FROM negocio_usuarios nu 
                WHERE nu.usuario_id = auth.uid()
            )
        )
    );

-- Los usuarios pueden eliminar detalles de ventas de sus negocios
CREATE POLICY "Users can delete sale details from their businesses" ON venta_detalle
    FOR DELETE USING (
        venta_id IN (
            SELECT v.id 
            FROM ventas v 
            WHERE v.negocio_id IN (
                SELECT nu.negocio_id 
                FROM negocio_usuarios nu 
                WHERE nu.usuario_id = auth.uid()
            )
        )
    );

-- Comentarios para documentación
COMMENT ON TABLE ventas IS 'Tabla que almacena las ventas realizadas por cada negocio';
COMMENT ON TABLE venta_detalle IS 'Tabla que almacena los detalles/items de cada venta';
COMMENT ON COLUMN ventas.medio_pago IS 'Método de pago utilizado: efectivo, tarjeta, transferencia';
COMMENT ON COLUMN ventas.total IS 'Total de la venta en la moneda local';
COMMENT ON COLUMN venta_detalle.cantidad IS 'Cantidad del producto vendido';
COMMENT ON COLUMN venta_detalle.precio_unitario IS 'Precio unitario del producto al momento de la venta';
COMMENT ON COLUMN venta_detalle.subtotal IS 'Subtotal del item (cantidad * precio_unitario)'; 