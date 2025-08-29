-- =====================================================
-- ESQUEMA DE BASE DE DATOS: NOTIFICACIONES Y ML
-- =====================================================
-- Fecha: 2025-08-25
-- Objetivo: Crear tablas de configuración, templates y ML
-- IMPORTANTE: Ejecutar después de disable_triggers_migration.sql

-- PASO 1: EXTENSIONES NECESARIAS
-- =====================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- PASO 2: TABLAS DE CONFIGURACIÓN DE NOTIFICACIONES
-- =====================================================

-- Tabla de configuración por tenant/negocio
CREATE TABLE IF NOT EXISTS business_notification_config (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES negocios(id) ON DELETE CASCADE,
    rubro VARCHAR(50) NOT NULL DEFAULT 'general',
    template_version VARCHAR(20) NOT NULL DEFAULT 'latest',
    custom_overrides JSONB DEFAULT '{}'::jsonb,
    strategy_config JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT unique_tenant_config UNIQUE (tenant_id),
    CONSTRAINT valid_rubro CHECK (rubro IN (
        'general', 'restaurante', 'retail', 'servicios', 'manufactura',
        'construccion', 'salud', 'educacion', 'tecnologia', 'transporte'
    ))
);

-- Tabla de templates de reglas por rubro
CREATE TABLE IF NOT EXISTS notification_rule_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rubro VARCHAR(50) NOT NULL,
    rule_type VARCHAR(100) NOT NULL,
    version VARCHAR(20) NOT NULL DEFAULT '1.0',
    is_latest BOOLEAN DEFAULT true,
    condition_config JSONB NOT NULL,
    default_parameters JSONB NOT NULL,
    description TEXT,
    priority VARCHAR(20) DEFAULT 'medium',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT unique_rubro_rule_version UNIQUE (rubro, rule_type, version),
    CONSTRAINT valid_template_rubro CHECK (rubro IN (
        'general', 'restaurante', 'retail', 'servicios', 'manufactura',
        'construccion', 'salud', 'educacion', 'tecnologia', 'transporte'
    )),
    CONSTRAINT valid_rule_type CHECK (rule_type IN (
        'sales_drop', 'low_stock', 'no_purchases', 'seasonal_alert',
        'ingredient_stock', 'high_expenses', 'payment_overdue', 'inventory_alert'
    ))
);

-- PASO 3: TABLAS DE NOTIFICACIONES
-- =====================================================

-- Tabla de templates de mensajes
CREATE TABLE IF NOT EXISTS notification_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    template_key VARCHAR(100) NOT NULL,
    language VARCHAR(5) DEFAULT 'es',
    channel VARCHAR(20) DEFAULT 'app',
    title_template TEXT NOT NULL,
    message_template TEXT NOT NULL,
    icon VARCHAR(50),
    color VARCHAR(20),
    priority INTEGER DEFAULT 3,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT unique_template_lang_channel UNIQUE (template_key, language, channel),
    CONSTRAINT valid_channel CHECK (channel IN ('app', 'email', 'sms', 'push')),
    CONSTRAINT valid_priority CHECK (priority BETWEEN 1 AND 5)
);

-- Tabla de notificaciones generadas
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES negocios(id) ON DELETE CASCADE,
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    template_id UUID REFERENCES notification_templates(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    severity VARCHAR(20) DEFAULT 'info',
    is_read BOOLEAN DEFAULT false,
    read_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_severity CHECK (severity IN ('info', 'warning', 'error', 'success'))
);

-- PASO 4: TABLAS DE MACHINE LEARNING
-- =====================================================

-- Tabla de features extraídas para ML
CREATE TABLE IF NOT EXISTS ml_features (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES negocios(id) ON DELETE CASCADE,
    feature_date DATE NOT NULL,
    feature_type VARCHAR(50) NOT NULL,
    features JSONB NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT unique_tenant_date_type UNIQUE (tenant_id, feature_date, feature_type),
    CONSTRAINT valid_feature_type CHECK (feature_type IN (
        'sales_metrics', 'inventory_metrics', 'purchase_metrics', 
        'financial_metrics', 'seasonal_patterns', 'business_context'
    ))
);

-- Tabla de modelos ML entrenados
CREATE TABLE IF NOT EXISTS ml_models (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES negocios(id) ON DELETE CASCADE,
    model_type VARCHAR(50) NOT NULL,
    model_version VARCHAR(20) NOT NULL DEFAULT '1.0',
    model_data BYTEA NOT NULL, -- Modelo serializado
    hyperparameters JSONB DEFAULT '{}'::jsonb,
    training_metrics JSONB DEFAULT '{}'::jsonb,
    accuracy DECIMAL(5,4),
    last_trained TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT unique_tenant_model_version UNIQUE (tenant_id, model_type, model_version),
    CONSTRAINT valid_model_type CHECK (model_type IN (
        'sales_forecasting', 'anomaly_detection', 'demand_prediction',
        'churn_prediction', 'inventory_optimization'
    )),
    CONSTRAINT valid_accuracy CHECK (accuracy >= 0 AND accuracy <= 1)
);

-- Tabla de predicciones ML
CREATE TABLE IF NOT EXISTS ml_predictions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES negocios(id) ON DELETE CASCADE,
    model_id UUID NOT NULL REFERENCES ml_models(id) ON DELETE CASCADE,
    prediction_date DATE NOT NULL,
    prediction_type VARCHAR(50) NOT NULL,
    predicted_values JSONB NOT NULL,
    confidence_score DECIMAL(5,4),
    actual_values JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT unique_tenant_date_prediction UNIQUE (tenant_id, prediction_date, prediction_type),
    CONSTRAINT valid_confidence CHECK (confidence_score >= 0 AND confidence_score <= 1)
);

-- PASO 5: TABLA DE AUDITORÍA
-- =====================================================

-- Tabla de log de auditoría para cambios de configuración
CREATE TABLE IF NOT EXISTS notification_audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES negocios(id) ON DELETE CASCADE,
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    action VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID,
    old_values JSONB,
    new_values JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_action CHECK (action IN ('create', 'update', 'delete', 'disable'))
);

-- PASO 6: ÍNDICES PARA PERFORMANCE
-- =====================================================

-- Índices para business_notification_config
CREATE INDEX IF NOT EXISTS idx_business_notification_config_tenant_id 
ON business_notification_config(tenant_id);

CREATE INDEX IF NOT EXISTS idx_business_notification_config_rubro 
ON business_notification_config(rubro) WHERE is_active = true;

-- Índices para notification_rule_templates
CREATE INDEX IF NOT EXISTS idx_notification_rule_templates_rubro_latest 
ON notification_rule_templates(rubro, rule_type) WHERE is_latest = true;

-- Índices para notifications
CREATE INDEX IF NOT EXISTS idx_notifications_tenant_unread 
ON notifications(tenant_id, is_read, created_at) WHERE is_read = false;

CREATE INDEX IF NOT EXISTS idx_notifications_created_at 
ON notifications(created_at DESC);

-- Índices para ml_features
CREATE INDEX IF NOT EXISTS idx_ml_features_tenant_date 
ON ml_features(tenant_id, feature_date DESC);

CREATE INDEX IF NOT EXISTS idx_ml_features_type 
ON ml_features(feature_type, feature_date DESC);

-- Índices para ml_models
CREATE INDEX IF NOT EXISTS idx_ml_models_tenant_active 
ON ml_models(tenant_id, model_type) WHERE is_active = true;

-- Índices para ml_predictions
CREATE INDEX IF NOT EXISTS idx_ml_predictions_tenant_date 
ON ml_predictions(tenant_id, prediction_date DESC);

-- PASO 7: POLÍTICAS RLS (ROW LEVEL SECURITY)
-- =====================================================

-- Habilitar RLS en todas las tablas
ALTER TABLE business_notification_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_rule_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE ml_features ENABLE ROW LEVEL SECURITY;
ALTER TABLE ml_models ENABLE ROW LEVEL SECURITY;
ALTER TABLE ml_predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_audit_log ENABLE ROW LEVEL SECURITY;

-- Políticas para business_notification_config
DROP POLICY IF EXISTS "Users can view their business notification config" ON business_notification_config;
CREATE POLICY "Users can view their business notification config" ON business_notification_config
    FOR SELECT USING (
        tenant_id IN (
            SELECT negocio_id FROM usuarios_negocios 
            WHERE usuario_id = auth.uid() AND estado = 'aceptado'
        )
    );

DROP POLICY IF EXISTS "Business admins can manage notification config" ON business_notification_config;
CREATE POLICY "Business admins can manage notification config" ON business_notification_config
    FOR ALL USING (
        tenant_id IN (
            SELECT un.negocio_id FROM usuarios_negocios un
            JOIN permisos_usuario_negocio pun ON un.id = pun.usuario_negocio_id
            WHERE un.usuario_id = auth.uid() 
              AND un.estado = 'aceptado'
              AND (un.rol = 'admin' OR pun.acceso_total = true)
        )
    );

-- Políticas para notifications
DROP POLICY IF EXISTS "Users can view their business notifications" ON notifications;
CREATE POLICY "Users can view their business notifications" ON notifications
    FOR SELECT USING (
        tenant_id IN (
            SELECT negocio_id FROM usuarios_negocios 
            WHERE usuario_id = auth.uid() AND estado = 'aceptado'
        )
    );

-- Políticas para ML tables (solo admins)
DROP POLICY IF EXISTS "Business admins can view ML data" ON ml_features;
CREATE POLICY "Business admins can view ML data" ON ml_features
    FOR SELECT USING (
        tenant_id IN (
            SELECT un.negocio_id FROM usuarios_negocios un
            JOIN permisos_usuario_negocio pun ON un.id = pun.usuario_negocio_id
            WHERE un.usuario_id = auth.uid() 
              AND un.estado = 'aceptado'
              AND (un.rol = 'admin' OR pun.acceso_total = true)
        )
    );

DROP POLICY IF EXISTS "Business admins can view ML models" ON ml_models;
CREATE POLICY "Business admins can view ML models" ON ml_models
    FOR SELECT USING (
        tenant_id IN (
            SELECT un.negocio_id FROM usuarios_negocios un
            JOIN permisos_usuario_negocio pun ON un.id = pun.usuario_negocio_id
            WHERE un.usuario_id = auth.uid() 
              AND un.estado = 'aceptado'
              AND (un.rol = 'admin' OR pun.acceso_total = true)
        )
    );

DROP POLICY IF EXISTS "Business admins can view ML predictions" ON ml_predictions;
CREATE POLICY "Business admins can view ML predictions" ON ml_predictions
    FOR SELECT USING (
        tenant_id IN (
            SELECT un.negocio_id FROM usuarios_negocios un
            JOIN permisos_usuario_negocio pun ON un.id = pun.usuario_negocio_id
            WHERE un.usuario_id = auth.uid() 
              AND un.estado = 'aceptado'
              AND (un.rol = 'admin' OR pun.acceso_total = true)
        )
    );

-- Política pública para templates (solo lectura)
DROP POLICY IF EXISTS "Anyone can view notification templates" ON notification_templates;
CREATE POLICY "Anyone can view notification templates" ON notification_templates
    FOR SELECT USING (true);

DROP POLICY IF EXISTS "Anyone can view notification rule templates" ON notification_rule_templates;
CREATE POLICY "Anyone can view notification rule templates" ON notification_rule_templates
    FOR SELECT USING (true);

-- PASO 8: VALIDACIÓN FINAL
-- =====================================================
SELECT 
    'ESQUEMA CREADO: Tablas de notificaciones y ML' as status,
    COUNT(*) as total_tables
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name IN (
      'business_notification_config',
      'notification_rule_templates', 
      'notification_templates',
      'notifications',
      'ml_features',
      'ml_models',
      'ml_predictions',
      'notification_audit_log'
  );

-- Log de creación del esquema
INSERT INTO migration_log (migration_name, notes) 
VALUES (
    'create_notifications_ml_schema', 
    'Creado esquema completo de notificaciones y ML con RLS y índices optimizados'
);

SELECT 'Esquema de notificaciones y ML creado exitosamente' AS notice;

-- COMENTARIOS IMPORTANTES:
-- ========================
-- 1. Todas las tablas tienen RLS habilitado para seguridad multi-tenant
-- 2. Índices optimizados para consultas frecuentes
-- 3. Constraints para integridad de datos
-- 4. JSONB para flexibilidad en configuraciones y features
-- 5. UUID como primary keys para escalabilidad
-- 6. Referencias a tablas existentes (negocios, auth.users)
-- 7. Políticas de acceso basadas en roles y permisos existentes
