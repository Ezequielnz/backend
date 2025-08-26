-- =====================================================
-- POBLAR TEMPLATES DE NOTIFICACIONES Y REGLAS
-- =====================================================
-- Fecha: 2025-08-25
-- Objetivo: Poblar datos iniciales para templates y reglas por rubro
-- IMPORTANTE: Ejecutar después de create_notifications_ml_schema.sql

-- PASO 1: TEMPLATES DE MENSAJES
-- =====================================================

-- Templates básicos de notificaciones
INSERT INTO notification_templates (template_key, language, channel, title_template, message_template, icon, color, priority) VALUES
-- Sales alerts
('sales_drop', 'es', 'app', 'Caída en Ventas Detectada', 'Las ventas han disminuido un {{percentage}}% en los últimos {{days}} días. Considera revisar tu estrategia.', 'trending_down', 'warning', 4),
('sales_spike', 'es', 'app', 'Aumento en Ventas', 'Excelente! Las ventas han aumentado un {{percentage}}% en los últimos {{days}} días.', 'trending_up', 'success', 2),

-- Inventory alerts
('low_stock', 'es', 'app', 'Stock Bajo', 'El producto {{product_name}} tiene solo {{quantity}} unidades restantes.', 'inventory', 'warning', 4),
('out_of_stock', 'es', 'app', 'Sin Stock', 'El producto {{product_name}} está agotado.', 'warning', 'error', 5),

-- Purchase alerts
('no_purchases', 'es', 'app', 'Sin Compras Recientes', 'No se han registrado compras en los últimos {{days}} días.', 'shopping_cart', 'info', 3),
('high_expenses', 'es', 'app', 'Gastos Elevados', 'Los gastos han aumentado un {{percentage}}% este mes.', 'account_balance_wallet', 'warning', 4),

-- Seasonal alerts
('seasonal_alert', 'es', 'app', 'Oportunidad Estacional', 'Se aproxima {{season}}. Considera ajustar tu inventario.', 'schedule', 'info', 2),

-- Restaurant specific
('ingredient_stock', 'es', 'app', 'Ingrediente Agotándose', 'El ingrediente {{ingredient}} está por agotarse.', 'restaurant', 'warning', 4),

-- Financial alerts
('payment_overdue', 'es', 'app', 'Pago Vencido', 'Tienes pagos vencidos por ${{amount}}.', 'payment', 'error', 5),

-- ML insights
('ml_forecast', 'es', 'app', 'Predicción de Ventas', 'Se prevé {{trend}} en ventas para los próximos {{days}} días.', 'insights', 'info', 2)

ON CONFLICT (template_key, language, channel) DO UPDATE SET
    title_template = EXCLUDED.title_template,
    message_template = EXCLUDED.message_template,
    icon = EXCLUDED.icon,
    color = EXCLUDED.color,
    priority = EXCLUDED.priority;

-- PASO 2: REGLAS PARA RUBRO GENERAL
-- =====================================================

INSERT INTO notification_rule_templates (rubro, rule_type, version, is_latest, condition_config, default_parameters, description) VALUES

-- General - Sales rules
('general', 'sales_drop', '1.0', true, 
 '{"metric": "sales_percentage_change", "operator": "less_than", "timeframe": "7_days"}',
 '{"threshold_percentage": -15, "min_days": 7, "severity": "warning"}',
 'Detecta caídas significativas en ventas'),

('general', 'low_stock', '1.0', true,
 '{"metric": "stock_quantity", "operator": "less_than_or_equal", "per_product": true}',
 '{"min_quantity": 5, "severity": "warning", "exclude_categories": []}',
 'Alerta cuando productos tienen stock bajo'),

('general', 'no_purchases', '1.0', true,
 '{"metric": "days_since_last_purchase", "operator": "greater_than"}',
 '{"max_days": 30, "severity": "info"}',
 'Alerta cuando no hay compras recientes'),

('general', 'high_expenses', '1.0', true,
 '{"metric": "expense_percentage_change", "operator": "greater_than", "timeframe": "30_days"}',
 '{"threshold_percentage": 25, "severity": "warning"}',
 'Detecta aumentos significativos en gastos');

-- PASO 3: REGLAS ESPECÍFICAS PARA RESTAURANTES
-- =====================================================

INSERT INTO notification_rule_templates (rubro, rule_type, version, is_latest, condition_config, default_parameters, description) VALUES

-- Restaurante - Reglas específicas
('restaurante', 'sales_drop', '1.0', true,
 '{"metric": "sales_percentage_change", "operator": "less_than", "timeframe": "3_days"}',
 '{"threshold_percentage": -20, "min_days": 3, "severity": "warning"}',
 'Caídas en ventas más sensibles para restaurantes'),

('restaurante', 'ingredient_stock', '1.0', true,
 '{"metric": "ingredient_quantity", "operator": "less_than_or_equal", "per_ingredient": true}',
 '{"min_quantity": 2, "severity": "warning", "critical_ingredients": ["carne", "pollo", "pescado"]}',
 'Control de ingredientes críticos'),

('restaurante', 'seasonal_alert', '1.0', true,
 '{"metric": "seasonal_pattern", "operator": "approaching", "seasons": ["summer", "winter", "holidays"]}',
 '{"advance_days": 14, "severity": "info"}',
 'Alertas estacionales para menús'),

('restaurante', 'low_stock', '1.0', true,
 '{"metric": "stock_quantity", "operator": "less_than_or_equal", "per_product": true}',
 '{"min_quantity": 3, "severity": "warning", "exclude_categories": ["bebidas"]}',
 'Stock bajo adaptado para restaurantes');

-- PASO 4: REGLAS ESPECÍFICAS PARA RETAIL
-- =====================================================

INSERT INTO notification_rule_templates (rubro, rule_type, version, is_latest, condition_config, default_parameters, description) VALUES

-- Retail - Reglas específicas
('retail', 'sales_drop', '1.0', true,
 '{"metric": "sales_percentage_change", "operator": "less_than", "timeframe": "7_days"}',
 '{"threshold_percentage": -10, "min_days": 7, "severity": "warning"}',
 'Caídas en ventas para retail'),

('retail', 'low_stock', '1.0', true,
 '{"metric": "stock_quantity", "operator": "less_than_or_equal", "per_product": true}',
 '{"min_quantity": 10, "severity": "warning", "exclude_categories": []}',
 'Stock bajo para productos retail'),

('retail', 'seasonal_alert', '1.0', true,
 '{"metric": "seasonal_pattern", "operator": "approaching", "seasons": ["back_to_school", "christmas", "summer"]}',
 '{"advance_days": 30, "severity": "info"}',
 'Alertas estacionales para retail'),

('retail', 'high_expenses', '1.0', true,
 '{"metric": "expense_percentage_change", "operator": "greater_than", "timeframe": "30_days"}',
 '{"threshold_percentage": 20, "severity": "warning"}',
 'Control de gastos para retail');

-- PASO 5: REGLAS ESPECÍFICAS PARA SERVICIOS
-- =====================================================

INSERT INTO notification_rule_templates (rubro, rule_type, version, is_latest, condition_config, default_parameters, description) VALUES

-- Servicios - Reglas específicas
('servicios', 'sales_drop', '1.0', true,
 '{"metric": "service_bookings_change", "operator": "less_than", "timeframe": "14_days"}',
 '{"threshold_percentage": -25, "min_days": 14, "severity": "warning"}',
 'Caída en reservas de servicios'),

('servicios', 'payment_overdue', '1.0', true,
 '{"metric": "overdue_payments", "operator": "greater_than"}',
 '{"max_days_overdue": 15, "severity": "error"}',
 'Pagos vencidos en servicios'),

('servicios', 'no_purchases', '1.0', true,
 '{"metric": "days_since_last_service", "operator": "greater_than"}',
 '{"max_days": 45, "severity": "info"}',
 'Servicios sin actividad reciente');

-- PASO 6: REGLAS PARA OTROS RUBROS
-- =====================================================

-- Manufactura
INSERT INTO notification_rule_templates (rubro, rule_type, version, is_latest, condition_config, default_parameters, description) VALUES
('manufactura', 'low_stock', '1.0', true,
 '{"metric": "raw_material_quantity", "operator": "less_than_or_equal", "per_material": true}',
 '{"min_quantity": 50, "severity": "warning", "critical_materials": []}',
 'Control de materias primas'),

('manufactura', 'high_expenses', '1.0', true,
 '{"metric": "production_cost_change", "operator": "greater_than", "timeframe": "30_days"}',
 '{"threshold_percentage": 15, "severity": "warning"}',
 'Control de costos de producción');

-- Construcción
INSERT INTO notification_rule_templates (rubro, rule_type, version, is_latest, condition_config, default_parameters, description) VALUES
('construccion', 'low_stock', '1.0', true,
 '{"metric": "material_quantity", "operator": "less_than_or_equal", "per_material": true}',
 '{"min_quantity": 20, "severity": "warning", "critical_materials": ["cemento", "hierro", "arena"]}',
 'Control de materiales de construcción');

-- PASO 7: VALIDACIÓN DE DATOS INSERTADOS
-- =====================================================

SELECT 
    'TEMPLATES POBLADOS' as status,
    (SELECT COUNT(*) FROM notification_templates) as message_templates,
    (SELECT COUNT(*) FROM notification_rule_templates) as rule_templates,
    (SELECT COUNT(DISTINCT rubro) FROM notification_rule_templates) as rubros_configured;

-- Verificar distribución por rubro
SELECT 
    rubro,
    COUNT(*) as reglas_count,
    array_agg(rule_type ORDER BY rule_type) as tipos_reglas
FROM notification_rule_templates
WHERE is_latest = true
GROUP BY rubro
ORDER BY rubro;

-- Log de población de templates
INSERT INTO migration_log (migration_name, notes) 
VALUES (
    'populate_notification_templates', 
    CONCAT(
        'Poblados templates de notificaciones: ',
        (SELECT COUNT(*) FROM notification_templates), ' mensajes, ',
        (SELECT COUNT(*) FROM notification_rule_templates), ' reglas para ',
        (SELECT COUNT(DISTINCT rubro) FROM notification_rule_templates), ' rubros'
    )
);

RAISE NOTICE 'Templates de notificaciones poblados exitosamente';

-- COMENTARIOS IMPORTANTES:
-- ========================
-- 1. Templates con placeholders {{variable}} para personalización
-- 2. Reglas específicas por rubro con parámetros optimizados
-- 3. Configuración JSONB flexible para condiciones complejas
-- 4. Severity levels: info, warning, error, success
-- 5. Versioning para futuras actualizaciones
-- 6. Cobertura de casos de uso principales por sector
