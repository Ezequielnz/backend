-- =====================================================
-- SEED NOTIFICATIONS & ML TEMPLATES (IDEMPOTENT)
-- =====================================================
-- Fecha: 2025-08-28
-- Objetivo: Poblar/actualizar templates de mensajes y reglas con UPSERTs
-- IMPORTANTE: Ejecutar después de create_notifications_ml_schema.sql

-- =====================================
-- 1) MESSAGE TEMPLATES (notification_templates)
-- =====================================
-- Esquema real: template_key, language, channel, title_template, message_template, icon, color, priority
-- Clave compuesta utilizada para idempotencia: (template_key, language, channel)

-- UPSERT idempotente de templates
WITH data(template_key, language, channel, title_template, message_template, icon, color, priority) AS (
  VALUES
    ('sales_drop', 'es', 'app', 'Caída en Ventas Detectada', 'Las ventas han disminuido un {{percentage}}% en los últimos {{days}} días. Considera revisar tu estrategia.', 'trending_down', 'warning', 4),
    ('sales_spike', 'es', 'app', 'Aumento en Ventas', 'Excelente! Las ventas han aumentado un {{percentage}}% en los últimos {{days}} días.', 'trending_up', 'success', 2),
    ('low_stock', 'es', 'app', 'Stock Bajo', 'El producto {{product_name}} tiene solo {{quantity}} unidades restantes.', 'inventory', 'warning', 4),
    ('out_of_stock', 'es', 'app', 'Sin Stock', 'El producto {{product_name}} está agotado.', 'warning', 'error', 5),
    ('no_purchases', 'es', 'app', 'Sin Compras Recientes', 'No se han registrado compras en los últimos {{days}} días.', 'shopping_cart', 'info', 3),
    ('high_expenses', 'es', 'app', 'Gastos Elevados', 'Los gastos han aumentado un {{percentage}}% este mes.', 'account_balance_wallet', 'warning', 4),
    ('seasonal_alert', 'es', 'app', 'Oportunidad Estacional', 'Se aproxima {{season}}. Considera ajustar tu inventario.', 'schedule', 'info', 2),
    ('ingredient_stock', 'es', 'app', 'Ingrediente Agotándose', 'El ingrediente {{ingredient}} está por agotarse.', 'restaurant', 'warning', 4),
    ('payment_overdue', 'es', 'app', 'Pago Vencido', 'Tienes pagos vencidos por ${{amount}}.', 'payment', 'error', 5),
    ('ml_forecast', 'es', 'app', 'Predicción de Ventas', 'Se prevé {{trend}} en ventas para los próximos {{days}} días.', 'insights', 'info', 2)
)
INSERT INTO public.notification_templates (template_key, language, channel, title_template, message_template, icon, color, priority)
SELECT d.template_key, d.language, d.channel, d.title_template, d.message_template, d.icon, d.color, d.priority
FROM data d
ON CONFLICT (template_key, language, channel) DO UPDATE SET
    title_template = EXCLUDED.title_template,
    message_template = EXCLUDED.message_template,
    icon = EXCLUDED.icon,
    color = EXCLUDED.color,
    priority = EXCLUDED.priority;

-- =====================================
-- 2) RULE TEMPLATES (notification_rule_templates)
-- =====================================
-- Esquema real: rubro, rule_type, version, is_latest, priority, description, condition_config, default_parameters
-- Clave de idempotencia usada: (rubro, rule_type, version)

-- UPSERT idempotente de rule templates
INSERT INTO public.notification_rule_templates (
  rubro, rule_type, version, is_latest, priority, description, condition_config, default_parameters
) VALUES
  ('general','sales_drop','1.0', TRUE, 'high', 'Alerta por caída de ventas', '{"metric":"sales","window_days":7,"drop_pct":20}'::jsonb, '{"pct":20,"days":7}'::jsonb),
  ('general','low_stock','1.0', TRUE, 'medium', 'Alerta por stock bajo', '{"metric":"stock","threshold":5}'::jsonb, '{"stock":5,"item":"*"}'::jsonb),
  ('general','no_purchases','1.0', TRUE, 'medium', 'Sin compras recientes', '{"metric":"purchases","days_without":14}'::jsonb, '{"days":14}'::jsonb),
  ('general','seasonal_alert','1.0', TRUE, 'medium', 'Alerta estacional', '{"metric":"seasonality","enabled":true}'::jsonb, '{}'::jsonb),
  ('general','ingredient_stock','1.0', TRUE, 'medium', 'Ingredientes bajos', '{"metric":"ingredient_stock","threshold":10}'::jsonb, '{"threshold":10}'::jsonb),
  ('general','high_expenses','1.0', TRUE, 'medium', 'Gasto elevado', '{"metric":"expenses","increase_pct":30}'::jsonb, '{"pct":30}'::jsonb),
  ('general','payment_overdue','1.0', TRUE, 'high', 'Pagos vencidos', '{"metric":"payments","overdue_days":7}'::jsonb, '{"days":7}'::jsonb),
  ('general','inventory_alert','1.0', TRUE, 'medium', 'Alerta de inventario', '{"metric":"inventory","anomaly":true}'::jsonb, '{}'::jsonb)
ON CONFLICT (rubro, rule_type, version) DO UPDATE SET
  description = EXCLUDED.description,
  priority = EXCLUDED.priority,
  is_latest = EXCLUDED.is_latest,
  condition_config = EXCLUDED.condition_config,
  default_parameters = EXCLUDED.default_parameters;

-- =====================================
-- 3) VALIDACIÓN
-- =====================================
SELECT COUNT(*) AS seeded_templates
FROM public.notification_templates 
WHERE language='es' AND channel='app' AND template_key IN (
  'sales_drop','sales_spike','low_stock','out_of_stock','no_purchases','high_expenses','seasonal_alert','ingredient_stock','payment_overdue','ml_forecast'
);

SELECT COUNT(*) AS seeded_rules
FROM public.notification_rule_templates 
WHERE rubro='general' AND version='1.0' AND rule_type IN (
  'sales_drop','low_stock','no_purchases','seasonal_alert','ingredient_stock','high_expenses','payment_overdue','inventory_alert'
);
