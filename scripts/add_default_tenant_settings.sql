-- Migration: Add default tenant_settings for existing businesses
-- This script creates default configuration for all businesses that don't have tenant_settings yet

-- Insert default tenant_settings for businesses that don't have configuration yet
INSERT INTO tenant_settings (
    tenant_id,
    locale,
    timezone,
    currency,
    sales_drop_threshold,
    min_days_for_model,
    created_at,
    updated_at
)
SELECT 
    n.id as tenant_id,
    'es-AR' as locale,
    'America/Argentina/Buenos_Aires' as timezone,
    'ARS' as currency,
    15 as sales_drop_threshold,  -- 15% threshold (Media sensitivity)
    30 as min_days_for_model,    -- 30 days minimum for predictions
    NOW() as created_at,
    NOW() as updated_at
FROM negocios n
LEFT JOIN tenant_settings ts ON n.id = ts.tenant_id
WHERE ts.tenant_id IS NULL;

-- Verify the insertion
SELECT 
    COUNT(*) as businesses_with_settings,
    (SELECT COUNT(*) FROM negocios) as total_businesses
FROM tenant_settings;
