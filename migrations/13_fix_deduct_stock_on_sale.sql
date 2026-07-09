CREATE OR REPLACE FUNCTION public.deduct_stock_on_sale(p_producto_id uuid, p_negocio_id uuid, p_cantidad numeric, p_inventario_modo text DEFAULT 'centralizado'::text, p_sucursal_id uuid DEFAULT NULL::uuid)
 RETURNS TABLE(success boolean, stock_anterior numeric, stock_nuevo numeric, mensaje text)
 LANGUAGE plpgsql
 SECURITY DEFINER
AS $function$
DECLARE
    v_stock_actual NUMERIC := 0;
    v_nuevo_stock NUMERIC := 0;
    v_inv_id UUID;
BEGIN
    IF p_inventario_modo = 'por_sucursal' AND p_sucursal_id IS NOT NULL THEN
        -- Modo sucursal: actualizar inventario_sucursal
        SELECT id, COALESCE(stock_actual, 0)
        INTO v_inv_id, v_stock_actual
        FROM inventario_sucursal
        WHERE producto_id = p_producto_id
          AND sucursal_id = p_sucursal_id
          AND negocio_id = p_negocio_id
        LIMIT 1;

        IF v_inv_id IS NULL THEN
            RETURN QUERY SELECT FALSE, 0::NUMERIC, 0::NUMERIC, 
                'No se encontró registro de inventario para esta sucursal'::TEXT;
            RETURN;
        END IF;

        v_nuevo_stock := GREATEST(0.0, v_stock_actual - p_cantidad);

        UPDATE inventario_sucursal
        SET stock_actual = v_nuevo_stock
        WHERE id = v_inv_id;

        RETURN QUERY SELECT TRUE, v_stock_actual, v_nuevo_stock, 
            format('Stock sucursal actualizado: %s → %s', round(v_stock_actual, 4)::TEXT, round(v_nuevo_stock, 4)::TEXT)::TEXT;

    ELSE
        -- Modo centralizado: actualizar productos.stock_actual
        SELECT COALESCE(stock_actual, 0)
        INTO v_stock_actual
        FROM productos
        WHERE id = p_producto_id
          AND negocio_id = p_negocio_id
        LIMIT 1;

        IF NOT FOUND THEN
            RETURN QUERY SELECT FALSE, 0::NUMERIC, 0::NUMERIC, 
                'Producto no encontrado'::TEXT;
            RETURN;
        END IF;

        v_nuevo_stock := GREATEST(0.0, v_stock_actual - p_cantidad);

        UPDATE productos
        SET stock_actual = v_nuevo_stock
        WHERE id = p_producto_id
          AND negocio_id = p_negocio_id;

        -- Sincronizar inventario_negocio si existe
        UPDATE inventario_negocio
        SET stock_total = v_nuevo_stock
        WHERE producto_id = p_producto_id
          AND negocio_id = p_negocio_id;

        RETURN QUERY SELECT TRUE, v_stock_actual, v_nuevo_stock, 
            format('Stock centralizado actualizado: %s → %s', round(v_stock_actual, 4)::TEXT, round(v_nuevo_stock, 4)::TEXT)::TEXT;
    END IF;
END;
$function$;
