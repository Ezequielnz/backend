-- Migration: Optimize Dashboard Aggregations via RPC
-- This migration creates functions to handle heavy data aggregations natively in Postgres.

-- 1. Sales Trend (Last 7 Days)
CREATE OR REPLACE FUNCTION get_dashboard_sales_trend(
    p_negocio_id UUID, 
    p_sucursal_id UUID DEFAULT NULL, 
    p_start_date DATE DEFAULT (CURRENT_DATE - INTERVAL '6 days')
)
RETURNS TABLE (
    sale_date DATE,
    daily_total NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        v.fecha::DATE AS sale_date,
        SUM(v.total)::NUMERIC AS daily_total
    FROM 
        ventas v
    WHERE 
        v.negocio_id = p_negocio_id
        AND (p_sucursal_id IS NULL OR v.sucursal_id = p_sucursal_id)
        AND v.fecha >= p_start_date::timestamp
    GROUP BY 
        v.fecha::DATE
    ORDER BY 
        v.fecha::DATE ASC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 2. Top Products (Last 30 Days)
CREATE OR REPLACE FUNCTION get_dashboard_top_products(
    p_negocio_id UUID,
    p_sucursal_id UUID DEFAULT NULL,
    p_start_date DATE DEFAULT (CURRENT_DATE - INTERVAL '30 days')
)
RETURNS TABLE (
    producto_id UUID,
    nombre TEXT,
    total_cantidad NUMERIC,
    total_ingresos NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        vd.producto_id,
        p.nombre,
        SUM(vd.cantidad)::NUMERIC AS total_cantidad,
        SUM(vd.subtotal)::NUMERIC AS total_ingresos
    FROM 
        venta_detalle vd
    JOIN 
        ventas v ON vd.venta_id = v.id
    JOIN 
        productos p ON vd.producto_id = p.id
    WHERE 
        v.negocio_id = p_negocio_id
        AND (p_sucursal_id IS NULL OR v.sucursal_id = p_sucursal_id)
        AND v.fecha >= p_start_date::timestamp
        AND vd.producto_id IS NOT NULL
    GROUP BY 
        vd.producto_id, p.nombre
    ORDER BY 
        total_cantidad DESC
    LIMIT 5;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 3. Cash Flow Today
CREATE OR REPLACE FUNCTION get_dashboard_cash_flow_today(
    p_negocio_id UUID,
    p_sucursal_id UUID DEFAULT NULL,
    p_target_date DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    tipo TEXT,
    total NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        mf.tipo::TEXT,
        SUM(mf.monto)::NUMERIC AS total
    FROM 
        movimientos_financieros mf
    WHERE 
        mf.negocio_id = p_negocio_id
        AND (p_sucursal_id IS NULL OR mf.sucursal_id = p_sucursal_id)
        AND mf.fecha::DATE = p_target_date
    GROUP BY 
        mf.tipo;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 4. Today's Sales
CREATE OR REPLACE FUNCTION get_dashboard_sales_today(
    p_negocio_id UUID,
    p_sucursal_id UUID DEFAULT NULL,
    p_target_date DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    total_sales NUMERIC,
    sales_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COALESCE(SUM(v.total), 0)::NUMERIC AS total_sales,
        COUNT(v.id)::BIGINT AS sales_count
    FROM 
        ventas v
    WHERE 
        v.negocio_id = p_negocio_id
        AND (p_sucursal_id IS NULL OR v.sucursal_id = p_sucursal_id)
        AND v.fecha::DATE = p_target_date;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
