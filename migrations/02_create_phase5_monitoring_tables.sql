-- Migration: Phase 5 Audit & Optimization - Monitoring and Governance Tables
-- Creates comprehensive monitoring infrastructure for drift detection, A/B testing,
-- performance tracking, and feedback-driven improvements

-- Ensure required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================================
-- 1. MODEL DRIFT MONITORING
-- ============================================================================

-- Table: model_performance_metrics
-- Tracks model performance over time for drift detection
CREATE TABLE IF NOT EXISTS model_performance_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    model_id UUID REFERENCES ml_models(id) ON DELETE CASCADE,
    model_type TEXT NOT NULL,
    model_version TEXT,
    
    -- Performance metrics
    mape FLOAT,
    smape FLOAT,
    mae FLOAT,
    rmse FLOAT,
    accuracy FLOAT,
    
    -- Drift indicators
    drift_score FLOAT, -- 0-1, higher = more drift
    drift_detected BOOLEAN DEFAULT FALSE,
    drift_type TEXT, -- 'concept', 'data', 'prediction'
    
    -- Statistical tests
    ks_statistic FLOAT, -- Kolmogorov-Smirnov test
    psi_score FLOAT, -- Population Stability Index
    
    -- Metadata
    evaluation_period_start TIMESTAMP WITH TIME ZONE,
    evaluation_period_end TIMESTAMP WITH TIME ZONE,
    sample_size INT,
    baseline_model_id UUID,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_model_perf_tenant_created ON model_performance_metrics(tenant_id, created_at DESC);
CREATE INDEX idx_model_perf_model_id ON model_performance_metrics(model_id, created_at DESC);
CREATE INDEX idx_model_perf_drift_detected ON model_performance_metrics(tenant_id, drift_detected) WHERE drift_detected = TRUE;

-- Table: drift_alerts
-- Stores drift detection alerts and retraining triggers
CREATE TABLE IF NOT EXISTS drift_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    model_id UUID REFERENCES ml_models(id),
    metric_id UUID REFERENCES model_performance_metrics(id),
    
    alert_type TEXT NOT NULL, -- 'drift_detected', 'performance_degradation', 'data_quality'
    severity TEXT NOT NULL, -- 'low', 'medium', 'high', 'critical'
    
    -- Alert details
    message TEXT NOT NULL,
    details JSONB DEFAULT '{}',
    threshold_exceeded FLOAT,
    current_value FLOAT,
    
    -- Actions
    status TEXT DEFAULT 'pending', -- 'pending', 'acknowledged', 'resolved', 'ignored'
    retraining_triggered BOOLEAN DEFAULT FALSE,
    retraining_job_id TEXT,
    
    -- Resolution
    acknowledged_by TEXT,
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolution_notes TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_drift_alerts_tenant_status ON drift_alerts(tenant_id, status, created_at DESC);
CREATE INDEX idx_drift_alerts_severity ON drift_alerts(severity, created_at DESC) WHERE status = 'pending';

-- ============================================================================
-- 2. A/B TESTING FRAMEWORK
-- ============================================================================

-- Table: ab_experiments
-- Defines A/B testing experiments for model comparison
CREATE TABLE IF NOT EXISTS ab_experiments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    
    -- Experiment configuration
    name TEXT NOT NULL,
    description TEXT,
    experiment_type TEXT NOT NULL, -- 'model_comparison', 'feature_comparison', 'prompt_comparison'
    
    -- Models/variants being tested
    control_model_id UUID REFERENCES ml_models(id),
    treatment_model_id UUID REFERENCES ml_models(id),
    control_config JSONB DEFAULT '{}',
    treatment_config JSONB DEFAULT '{}',
    
    -- Traffic allocation
    traffic_split FLOAT DEFAULT 0.5, -- 0-1, percentage to treatment
    allocation_method TEXT DEFAULT 'random', -- 'random', 'hash', 'sequential'
    
    -- Status and timing
    status TEXT DEFAULT 'draft', -- 'draft', 'running', 'paused', 'completed', 'cancelled'
    start_date TIMESTAMP WITH TIME ZONE,
    end_date TIMESTAMP WITH TIME ZONE,
    
    -- Success criteria
    primary_metric TEXT NOT NULL, -- 'mape', 'accuracy', 'cost', 'latency'
    success_threshold FLOAT,
    min_sample_size INT DEFAULT 100,
    confidence_level FLOAT DEFAULT 0.95,
    
    -- Results
    winner TEXT, -- 'control', 'treatment', 'inconclusive'
    statistical_significance FLOAT,
    effect_size FLOAT,
    results_summary JSONB DEFAULT '{}',
    
    created_by TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_ab_experiments_tenant_status ON ab_experiments(tenant_id, status);
CREATE INDEX idx_ab_experiments_dates ON ab_experiments(start_date, end_date) WHERE status = 'running';

-- Table: ab_experiment_observations
-- Records individual observations for A/B experiments
CREATE TABLE IF NOT EXISTS ab_experiment_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES ab_experiments(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    
    -- Assignment
    variant TEXT NOT NULL, -- 'control', 'treatment'
    user_id TEXT,
    session_id TEXT,
    
    -- Prediction details
    prediction_id UUID,
    model_id UUID,
    
    -- Metrics
    metric_values JSONB DEFAULT '{}',
    latency_ms INT,
    cost FLOAT,
    
    -- Outcome
    actual_value FLOAT,
    predicted_value FLOAT,
    error FLOAT,
    
    observed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_ab_observations_experiment ON ab_experiment_observations(experiment_id, observed_at DESC);
CREATE INDEX idx_ab_observations_variant ON ab_experiment_observations(experiment_id, variant);

-- ============================================================================
-- 3. PERFORMANCE & COST DASHBOARDS
-- ============================================================================

-- Table: system_performance_metrics
-- Aggregated system-wide performance metrics
CREATE TABLE IF NOT EXISTS system_performance_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    
    -- Time window
    metric_date DATE NOT NULL,
    metric_hour INT, -- 0-23, NULL for daily aggregates
    aggregation_level TEXT NOT NULL, -- 'hourly', 'daily', 'weekly', 'monthly'
    
    -- ML Pipeline metrics
    ml_predictions_count INT DEFAULT 0,
    ml_avg_latency_ms FLOAT,
    ml_p95_latency_ms FLOAT,
    ml_error_rate FLOAT,
    
    -- LLM metrics
    llm_calls_count INT DEFAULT 0,
    llm_avg_latency_ms FLOAT,
    llm_cache_hit_rate FLOAT,
    llm_total_tokens INT DEFAULT 0,
    llm_total_cost FLOAT DEFAULT 0,
    
    -- Vector operations
    vector_embeddings_created INT DEFAULT 0,
    vector_searches_count INT DEFAULT 0,
    vector_avg_search_latency_ms FLOAT,
    
    -- Action system
    actions_executed INT DEFAULT 0,
    actions_auto_approved INT DEFAULT 0,
    actions_manual_approved INT DEFAULT 0,
    actions_rejected INT DEFAULT 0,
    actions_failed INT DEFAULT 0,
    
    -- Resource utilization
    avg_cpu_percent FLOAT,
    avg_memory_mb FLOAT,
    peak_memory_mb FLOAT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(tenant_id, metric_date, metric_hour, aggregation_level)
);

CREATE INDEX idx_system_perf_tenant_date ON system_performance_metrics(tenant_id, metric_date DESC, aggregation_level);
CREATE INDEX idx_system_perf_date_level ON system_performance_metrics(metric_date DESC, aggregation_level);

-- Table: cost_tracking
-- Detailed cost tracking for budget management
CREATE TABLE IF NOT EXISTS cost_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    
    -- Cost breakdown
    cost_type TEXT NOT NULL, -- 'llm_api', 'compute', 'storage', 'vector_ops'
    service_name TEXT, -- 'openai', 'anthropic', 'aws', etc.
    
    -- Amount
    amount FLOAT NOT NULL,
    currency TEXT DEFAULT 'USD',
    
    -- Usage details
    usage_units INT, -- tokens, requests, GB, etc.
    unit_type TEXT, -- 'tokens', 'requests', 'gb_hours'
    unit_cost FLOAT,
    
    -- Context
    model_id UUID,
    llm_response_id UUID,
    action_execution_id UUID,
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    billing_period DATE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_cost_tracking_tenant_period ON cost_tracking(tenant_id, billing_period DESC);
CREATE INDEX idx_cost_tracking_type ON cost_tracking(tenant_id, cost_type, created_at DESC);

-- ============================================================================
-- 4. PRIVACY AUDIT AUTOMATION
-- ============================================================================

-- Table: privacy_audit_log
-- Comprehensive privacy compliance audit trail
CREATE TABLE IF NOT EXISTS privacy_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    
    -- Audit event
    event_type TEXT NOT NULL, -- 'pii_detected', 'pii_sanitized', 'data_access', 'data_export', 'data_deletion'
    event_category TEXT NOT NULL, -- 'detection', 'processing', 'access', 'compliance'
    
    -- Data subject
    data_subject_id TEXT,
    data_subject_type TEXT, -- 'customer', 'user', 'employee'
    
    -- PII details
    pii_types JSONB DEFAULT '[]', -- ['email', 'phone', 'document']
    pii_fields_count INT DEFAULT 0,
    sanitization_method TEXT, -- 'mask', 'remove', 'hash', 'encrypt'
    
    -- Context
    source_system TEXT, -- 'ml_pipeline', 'llm_reasoning', 'vector_enrichment'
    source_id TEXT,
    content_type TEXT,
    
    -- Compliance
    gdpr_compliant BOOLEAN DEFAULT TRUE,
    consent_verified BOOLEAN,
    legal_basis TEXT, -- 'consent', 'contract', 'legitimate_interest'
    
    -- Risk assessment
    risk_level TEXT, -- 'low', 'medium', 'high', 'critical'
    requires_review BOOLEAN DEFAULT FALSE,
    reviewed_by TEXT,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_privacy_audit_tenant_created ON privacy_audit_log(tenant_id, created_at DESC);
CREATE INDEX idx_privacy_audit_event_type ON privacy_audit_log(event_type, created_at DESC);
CREATE INDEX idx_privacy_audit_requires_review ON privacy_audit_log(tenant_id, requires_review) WHERE requires_review = TRUE;
CREATE INDEX idx_privacy_audit_risk ON privacy_audit_log(risk_level, created_at DESC) WHERE risk_level IN ('high', 'critical');

-- Table: compliance_reports
-- Automated compliance report generation
CREATE TABLE IF NOT EXISTS compliance_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    
    -- Report details
    report_type TEXT NOT NULL, -- 'gdpr', 'privacy_impact', 'data_inventory', 'audit_summary'
    report_period_start DATE NOT NULL,
    report_period_end DATE NOT NULL,
    
    -- Findings
    total_events INT DEFAULT 0,
    pii_detections INT DEFAULT 0,
    compliance_violations INT DEFAULT 0,
    high_risk_events INT DEFAULT 0,
    
    -- Metrics
    compliance_score FLOAT, -- 0-100
    risk_score FLOAT, -- 0-100
    
    -- Report content
    summary TEXT,
    findings JSONB DEFAULT '[]',
    recommendations JSONB DEFAULT '[]',
    report_data JSONB DEFAULT '{}',
    
    -- Status
    status TEXT DEFAULT 'generated', -- 'generated', 'reviewed', 'approved', 'archived'
    generated_by TEXT DEFAULT 'system',
    reviewed_by TEXT,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_compliance_reports_tenant_period ON compliance_reports(tenant_id, report_period_end DESC);
CREATE INDEX idx_compliance_reports_type ON compliance_reports(report_type, created_at DESC);

-- ============================================================================
-- 5. FEEDBACK-DRIVEN IMPROVEMENT
-- ============================================================================

-- Table: user_feedback
-- Captures user feedback on predictions and actions
CREATE TABLE IF NOT EXISTS user_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    
    -- Feedback target
    feedback_type TEXT NOT NULL, -- 'prediction', 'action', 'explanation', 'recommendation'
    target_id UUID, -- prediction_id, action_execution_id, llm_response_id
    
    -- User information
    user_id TEXT NOT NULL,
    user_role TEXT,
    
    -- Feedback content
    rating INT, -- 1-5 stars
    sentiment TEXT, -- 'positive', 'neutral', 'negative'
    feedback_text TEXT,
    feedback_tags TEXT[], -- ['inaccurate', 'helpful', 'confusing', etc.]
    
    -- Corrections
    expected_value FLOAT,
    actual_value FLOAT,
    correction_provided BOOLEAN DEFAULT FALSE,
    correction_data JSONB DEFAULT '{}',
    
    -- Processing
    processed BOOLEAN DEFAULT FALSE,
    incorporated_into_training BOOLEAN DEFAULT FALSE,
    processing_notes TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_user_feedback_tenant_created ON user_feedback(tenant_id, created_at DESC);
CREATE INDEX idx_user_feedback_type_target ON user_feedback(feedback_type, target_id);
CREATE INDEX idx_user_feedback_unprocessed ON user_feedback(tenant_id, processed) WHERE processed = FALSE;
CREATE INDEX idx_user_feedback_rating ON user_feedback(tenant_id, rating, created_at DESC);

-- Table: improvement_suggestions
-- AI-generated improvement suggestions based on feedback and metrics
CREATE TABLE IF NOT EXISTS improvement_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    
    -- Suggestion details
    suggestion_type TEXT NOT NULL, -- 'model_retrain', 'feature_engineering', 'prompt_optimization', 'config_change'
    priority TEXT NOT NULL, -- 'low', 'medium', 'high', 'critical'
    
    -- Analysis
    issue_identified TEXT NOT NULL,
    root_cause_analysis TEXT,
    expected_improvement FLOAT, -- Expected % improvement
    confidence_score FLOAT, -- 0-1
    
    -- Recommendation
    recommendation TEXT NOT NULL,
    implementation_steps JSONB DEFAULT '[]',
    estimated_effort TEXT, -- 'low', 'medium', 'high'
    
    -- Supporting data
    supporting_metrics JSONB DEFAULT '{}',
    related_feedback_ids UUID[],
    related_alert_ids UUID[],
    
    -- Status
    status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'implemented', 'rejected', 'deferred'
    approved_by TEXT,
    approved_at TIMESTAMP WITH TIME ZONE,
    implemented_at TIMESTAMP WITH TIME ZONE,
    implementation_result JSONB DEFAULT '{}',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_improvement_suggestions_tenant_status ON improvement_suggestions(tenant_id, status, priority);
CREATE INDEX idx_improvement_suggestions_type ON improvement_suggestions(suggestion_type, created_at DESC);

-- ============================================================================
-- 6. CACHING & OPTIMIZATION METADATA
-- ============================================================================

-- Table: cache_performance_metrics
-- Tracks cache hit rates and performance
CREATE TABLE IF NOT EXISTS cache_performance_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    
    -- Cache type
    cache_type TEXT NOT NULL, -- 'llm_exact', 'llm_semantic', 'vector_search', 'api_response'
    
    -- Time window
    metric_date DATE NOT NULL,
    metric_hour INT,
    
    -- Performance metrics
    total_requests INT DEFAULT 0,
    cache_hits INT DEFAULT 0,
    cache_misses INT DEFAULT 0,
    hit_rate FLOAT, -- Computed: hits / total
    
    -- Latency improvements
    avg_cache_hit_latency_ms FLOAT,
    avg_cache_miss_latency_ms FLOAT,
    latency_improvement_percent FLOAT,
    
    -- Cost savings
    estimated_cost_saved FLOAT,
    
    -- Cache health
    evictions INT DEFAULT 0,
    cache_size_mb FLOAT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(tenant_id, cache_type, metric_date, metric_hour)
);

CREATE INDEX idx_cache_perf_tenant_date ON cache_performance_metrics(tenant_id, metric_date DESC, cache_type);

-- ============================================================================
-- 7. PARTITIONING METADATA (for future scaling)
-- ============================================================================

-- Table: partition_management
-- Tracks table partitioning status and maintenance
CREATE TABLE IF NOT EXISTS partition_management (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Table information
    table_name TEXT NOT NULL UNIQUE,
    partition_strategy TEXT NOT NULL, -- 'range', 'list', 'hash'
    partition_key TEXT NOT NULL,
    
    -- Status
    is_partitioned BOOLEAN DEFAULT FALSE,
    partition_count INT DEFAULT 0,
    
    -- Thresholds
    size_threshold_gb FLOAT DEFAULT 50,
    row_count_threshold BIGINT DEFAULT 10000000,
    
    -- Maintenance
    last_partition_created TIMESTAMP WITH TIME ZONE,
    last_maintenance_run TIMESTAMP WITH TIME ZONE,
    next_maintenance_due TIMESTAMP WITH TIME ZONE,
    
    -- Metadata
    partition_config JSONB DEFAULT '{}',
    maintenance_log JSONB DEFAULT '[]',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- 8. VIEWS FOR MONITORING DASHBOARDS
-- ============================================================================

-- View: drift_detection_summary
CREATE OR REPLACE VIEW drift_detection_summary AS
SELECT 
    tenant_id,
    model_type,
    COUNT(*) as total_evaluations,
    SUM(CASE WHEN drift_detected THEN 1 ELSE 0 END) as drift_detections,
    AVG(drift_score) as avg_drift_score,
    MAX(created_at) as last_evaluation,
    AVG(mape) as avg_mape,
    AVG(accuracy) as avg_accuracy
FROM model_performance_metrics
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY tenant_id, model_type;

-- View: cost_summary_by_tenant
CREATE OR REPLACE VIEW cost_summary_by_tenant AS
SELECT 
    tenant_id,
    billing_period,
    SUM(amount) as total_cost,
    SUM(CASE WHEN cost_type = 'llm_api' THEN amount ELSE 0 END) as llm_cost,
    SUM(CASE WHEN cost_type = 'compute' THEN amount ELSE 0 END) as compute_cost,
    SUM(CASE WHEN cost_type = 'storage' THEN amount ELSE 0 END) as storage_cost,
    SUM(CASE WHEN cost_type = 'vector_ops' THEN amount ELSE 0 END) as vector_cost,
    COUNT(*) as transaction_count
FROM cost_tracking
GROUP BY tenant_id, billing_period;

-- View: privacy_compliance_dashboard
CREATE OR REPLACE VIEW privacy_compliance_dashboard AS
SELECT 
    tenant_id,
    DATE(created_at) as audit_date,
    COUNT(*) as total_events,
    SUM(CASE WHEN event_type = 'pii_detected' THEN 1 ELSE 0 END) as pii_detections,
    SUM(CASE WHEN gdpr_compliant = FALSE THEN 1 ELSE 0 END) as compliance_violations,
    SUM(CASE WHEN risk_level IN ('high', 'critical') THEN 1 ELSE 0 END) as high_risk_events,
    SUM(CASE WHEN requires_review AND reviewed_at IS NULL THEN 1 ELSE 0 END) as pending_reviews
FROM privacy_audit_log
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY tenant_id, DATE(created_at);

-- View: feedback_insights
CREATE OR REPLACE VIEW feedback_insights AS
SELECT 
    tenant_id,
    feedback_type,
    COUNT(*) as total_feedback,
    AVG(rating) as avg_rating,
    SUM(CASE WHEN sentiment = 'positive' THEN 1 ELSE 0 END) as positive_count,
    SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) as negative_count,
    SUM(CASE WHEN correction_provided THEN 1 ELSE 0 END) as corrections_provided,
    SUM(CASE WHEN processed THEN 1 ELSE 0 END) as processed_count
FROM user_feedback
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY tenant_id, feedback_type;

-- ============================================================================
-- 9. FUNCTIONS FOR AUTOMATED MAINTENANCE
-- ============================================================================

-- Function: calculate_drift_score
CREATE OR REPLACE FUNCTION calculate_drift_score(
    p_current_mape FLOAT,
    p_baseline_mape FLOAT,
    p_current_accuracy FLOAT,
    p_baseline_accuracy FLOAT
) RETURNS FLOAT AS $$
DECLARE
    mape_drift FLOAT;
    accuracy_drift FLOAT;
    combined_drift FLOAT;
BEGIN
    -- Calculate relative changes
    mape_drift := ABS(p_current_mape - p_baseline_mape) / NULLIF(p_baseline_mape, 0);
    accuracy_drift := ABS(p_current_accuracy - p_baseline_accuracy) / NULLIF(p_baseline_accuracy, 0);
    
    -- Combine drifts (weighted average)
    combined_drift := (mape_drift * 0.6 + accuracy_drift * 0.4);
    
    -- Normalize to 0-1 range
    RETURN LEAST(combined_drift, 1.0);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Function: aggregate_hourly_metrics
CREATE OR REPLACE FUNCTION aggregate_hourly_metrics(p_tenant_id TEXT, p_date DATE, p_hour INT)
RETURNS VOID AS $$
BEGIN
    -- This function would aggregate metrics from various sources
    -- Implementation depends on specific metric collection mechanisms
    INSERT INTO system_performance_metrics (
        tenant_id, metric_date, metric_hour, aggregation_level
    ) VALUES (
        p_tenant_id, p_date, p_hour, 'hourly'
    ) ON CONFLICT (tenant_id, metric_date, metric_hour, aggregation_level) DO NOTHING;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 10. INITIAL DATA & CONFIGURATION
-- ============================================================================

-- Insert default partition management entries for key tables
INSERT INTO partition_management (table_name, partition_strategy, partition_key, size_threshold_gb, row_count_threshold) VALUES
('model_performance_metrics', 'range', 'created_at', 10, 1000000),
('system_performance_metrics', 'range', 'metric_date', 20, 5000000),
('privacy_audit_log', 'range', 'created_at', 15, 2000000),
('user_feedback', 'range', 'created_at', 5, 500000),
('cost_tracking', 'range', 'created_at', 10, 1000000)
ON CONFLICT (table_name) DO NOTHING;

-- ============================================================================
-- COMMENTS FOR DOCUMENTATION
-- ============================================================================

COMMENT ON TABLE model_performance_metrics IS 'Tracks model performance over time for drift detection and monitoring';
COMMENT ON TABLE drift_alerts IS 'Stores drift detection alerts and triggers for model retraining';
COMMENT ON TABLE ab_experiments IS 'Defines A/B testing experiments for model and feature comparison';
COMMENT ON TABLE system_performance_metrics IS 'Aggregated system-wide performance metrics for dashboards';
COMMENT ON TABLE cost_tracking IS 'Detailed cost tracking for budget management and optimization';
COMMENT ON TABLE privacy_audit_log IS 'Comprehensive privacy compliance audit trail';
COMMENT ON TABLE user_feedback IS 'Captures user feedback on predictions, actions, and explanations';
COMMENT ON TABLE improvement_suggestions IS 'AI-generated improvement suggestions based on feedback and metrics';
COMMENT ON TABLE cache_performance_metrics IS 'Tracks cache hit rates and performance improvements';
COMMENT ON TABLE partition_management IS 'Manages table partitioning for scalability';

-- End of Phase 5 migration