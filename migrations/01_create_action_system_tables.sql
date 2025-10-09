-- Migration: create Action System tables for Phase 4 Safe Action Engine
-- Adds tables for automated actions, approvals, executions, and tenant settings
-- Run in staging only after verifying action engine requirements

-- Ensure pgvector extension (already created in Phase 3)
-- CREATE EXTENSION IF NOT EXISTS vector;

-- Table: action_definitions
-- Defines available action types and their configurations
CREATE TABLE IF NOT EXISTS action_definitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action_type TEXT NOT NULL UNIQUE, -- 'create_task', 'send_notification', 'update_inventory', etc.
    name TEXT NOT NULL,
    description TEXT,
    category TEXT DEFAULT 'general', -- 'task_management', 'communication', 'inventory', 'reporting'
    requires_approval BOOLEAN DEFAULT TRUE,
    impact_level TEXT DEFAULT 'medium', -- 'low', 'medium', 'high', 'critical'
    rollback_supported BOOLEAN DEFAULT FALSE,
    config_schema JSONB DEFAULT '{}', -- JSON schema for action parameters
    ui_component TEXT, -- Frontend component name for rendering
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table: tenant_action_settings
-- Tenant-specific settings for action automation
CREATE TABLE IF NOT EXISTS tenant_action_settings (
    tenant_id TEXT PRIMARY KEY,
    automation_enabled BOOLEAN DEFAULT FALSE,
    approval_required BOOLEAN DEFAULT TRUE,
    auto_approval_threshold FLOAT DEFAULT 0.9, -- Confidence threshold for auto-approval
    max_actions_per_hour INT DEFAULT 10,
    max_actions_per_day INT DEFAULT 50,
    allowed_action_types TEXT[] DEFAULT ARRAY['create_task', 'send_notification'],
    canary_percentage FLOAT DEFAULT 0.0, -- 0-1, percentage of predictions that trigger actions
    safety_mode TEXT DEFAULT 'strict', -- 'strict', 'moderate', 'permissive'
    notification_on_auto_action BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table: action_executions
-- Records all action executions (successful or failed)
CREATE TABLE IF NOT EXISTS action_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    prediction_id UUID,
    llm_response_id UUID REFERENCES llm_responses(id),
    action_definition_id UUID REFERENCES action_definitions(id),
    action_type TEXT NOT NULL,
    action_params JSONB DEFAULT '{}',
    execution_status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'executing', 'completed', 'failed', 'cancelled'
    approval_status TEXT DEFAULT 'pending', -- 'pending', 'auto_approved', 'manual_approved', 'rejected'
    approved_by TEXT, -- user_id who approved
    approved_at TIMESTAMP WITH TIME ZONE,
    executed_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    execution_result JSONB DEFAULT '{}', -- Success details or error info
    rollback_status TEXT, -- 'not_needed', 'pending', 'completed', 'failed'
    rollback_result JSONB DEFAULT '{}',
    confidence_score FLOAT,
    impact_assessment JSONB DEFAULT '{}', -- Pre-execution impact analysis
    error_message TEXT,
    retry_count INT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table: action_approvals
-- Queue for manual approvals of automated actions
CREATE TABLE IF NOT EXISTS action_approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    execution_id UUID REFERENCES action_executions(id),
    action_type TEXT NOT NULL,
    action_description TEXT NOT NULL,
    impact_summary TEXT,
    confidence_score FLOAT,
    requested_by TEXT DEFAULT 'system', -- 'system' for automated, user_id for manual
    assigned_to TEXT, -- user_id assigned to review
    priority TEXT DEFAULT 'medium', -- 'low', 'medium', 'high', 'urgent'
    status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'rejected', 'expired'
    decision TEXT, -- 'approve', 'reject', 'modify'
    decision_notes TEXT,
    decided_by TEXT, -- user_id who made the decision
    decided_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE, -- Auto-expire pending approvals
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table: action_audit_log
-- Comprehensive audit trail for all action-related activities
CREATE TABLE IF NOT EXISTS action_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    execution_id UUID REFERENCES action_executions(id),
    approval_id UUID REFERENCES action_approvals(id),
    event_type TEXT NOT NULL, -- 'created', 'approved', 'executed', 'failed', 'rolled_back', etc.
    event_description TEXT,
    user_id TEXT, -- NULL for system events
    old_values JSONB DEFAULT '{}',
    new_values JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_action_executions_tenant_status ON action_executions (tenant_id, execution_status);
CREATE INDEX IF NOT EXISTS idx_action_executions_created_at ON action_executions (created_at);
CREATE INDEX IF NOT EXISTS idx_action_executions_prediction_id ON action_executions (prediction_id);
CREATE INDEX IF NOT EXISTS idx_action_approvals_tenant_status ON action_approvals (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_action_approvals_assigned_to ON action_approvals (assigned_to, status);
CREATE INDEX IF NOT EXISTS idx_action_approvals_expires_at ON action_approvals (expires_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_action_audit_log_tenant_created ON action_audit_log (tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_action_audit_log_execution_id ON action_audit_log (execution_id);

-- Insert default action definitions
INSERT INTO action_definitions (action_type, name, description, category, requires_approval, impact_level, rollback_supported, config_schema, ui_component) VALUES
('create_task', 'Crear Tarea', 'Crea una nueva tarea en el sistema de gestión de tareas', 'task_management', TRUE, 'medium', TRUE, '{
  "type": "object",
  "properties": {
    "titulo": {"type": "string", "maxLength": 200},
    "descripcion": {"type": "string", "maxLength": 1000},
    "prioridad": {"type": "string", "enum": ["baja", "media", "alta", "urgente"]},
    "asignada_a_id": {"type": "string"}
  },
  "required": ["titulo"]
}', 'TaskCreationForm'),
('send_notification', 'Enviar Notificación', 'Envía una notificación al usuario o equipo', 'communication', FALSE, 'low', FALSE, '{
  "type": "object",
  "properties": {
    "titulo": {"type": "string", "maxLength": 200},
    "mensaje": {"type": "string", "maxLength": 1000},
    "tipo": {"type": "string", "enum": ["info", "warning", "error", "success"]},
    "destinatarios": {"type": "array", "items": {"type": "string"}}
  },
  "required": ["titulo", "mensaje"]
}', 'NotificationForm'),
('update_inventory', 'Actualizar Inventario', 'Ajusta niveles de inventario de productos', 'inventory', TRUE, 'high', TRUE, '{
  "type": "object",
  "properties": {
    "producto_id": {"type": "string"},
    "cantidad": {"type": "number"},
    "tipo_ajuste": {"type": "string", "enum": ["incremento", "decremento", "set"]},
    "motivo": {"type": "string", "maxLength": 500}
  },
  "required": ["producto_id", "cantidad", "tipo_ajuste"]
}', 'InventoryAdjustmentForm'),
('generate_report', 'Generar Reporte', 'Crea un reporte basado en datos específicos', 'reporting', FALSE, 'low', FALSE, '{
  "type": "object",
  "properties": {
    "tipo_reporte": {"type": "string", "enum": ["ventas", "inventario", "finanzas", "clientes"]},
    "fecha_inicio": {"type": "string", "format": "date"},
    "fecha_fin": {"type": "string", "format": "date"},
    "filtros": {"type": "object"}
  },
  "required": ["tipo_reporte"]
}', 'ReportGenerationForm')
ON CONFLICT (action_type) DO NOTHING;

-- Insert default tenant settings template (for new tenants)
-- This will be used as a template when initializing new tenants
INSERT INTO tenant_action_settings (tenant_id, automation_enabled, approval_required, auto_approval_threshold, max_actions_per_hour, max_actions_per_day, allowed_action_types, canary_percentage, safety_mode, notification_on_auto_action) VALUES
('template', FALSE, TRUE, 0.9, 10, 50, ARRAY['create_task', 'send_notification'], 0.0, 'strict', TRUE)
ON CONFLICT (tenant_id) DO NOTHING;

-- RLS Policies (if using Row Level Security)
-- ALTER TABLE action_executions ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE action_approvals ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE action_audit_log ENABLE ROW LEVEL SECURITY;

-- CREATE POLICY tenant_isolation_action_executions ON action_executions
--     USING (tenant_id = current_setting('app.current_tenant_id', TRUE));

-- CREATE POLICY tenant_isolation_action_approvals ON action_approvals
--     USING (tenant_id = current_setting('app.current_tenant_id', TRUE));

-- CREATE POLICY tenant_isolation_action_audit_log ON action_audit_log
--     USING (tenant_id = current_setting('app.current_tenant_id', TRUE));

-- End of migration