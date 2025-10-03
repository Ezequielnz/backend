-- Migration: create LLM tables for Phase 3 LLM Reasoning Core
-- EMBEDDING_DIM is parameterized: ensure `app/core/config.py` has EMBEDDING_DIM set.
-- Run in staging only after verifying EMBEDDING_DIM in app/core/config.py

-- Ensure pgvector extension installed
CREATE EXTENSION IF NOT EXISTS vector;

-- Table: tenant_llm_settings
CREATE TABLE IF NOT EXISTS tenant_llm_settings (
    tenant_id TEXT PRIMARY KEY,
    model_preference TEXT,
    daily_budget NUMERIC,
    sem_cache_threshold FLOAT DEFAULT 0.92,
    confidence_threshold FLOAT DEFAULT 0.8,
    human_review_threshold FLOAT DEFAULT 0.6,
    redact_before_send BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table: prompt_templates (optional, for versioned prompts)
CREATE TABLE IF NOT EXISTS prompt_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    template TEXT NOT NULL,
    version TEXT NOT NULL,
    description TEXT,
    created_by TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table: llm_responses
CREATE TABLE IF NOT EXISTS llm_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    prediction_id UUID,
    prompt_hash TEXT NOT NULL,
    prompt_template_id UUID REFERENCES prompt_templates(id),
    prompt_version TEXT,
    prompt_text TEXT, -- store redacted prompt only if policy allows
    response TEXT NOT NULL,
    model_used TEXT,
    prompt_embedding_model TEXT,
    confidence_score FLOAT,
    tokens_used INT,
    cost_estimate FLOAT,
    response_type TEXT DEFAULT 'full', -- 'full'|'degraded'|'cached'|'fallback'
    pii_redaction_applied BOOLEAN DEFAULT FALSE,
    prompt_version_metadata JSONB DEFAULT '{}' , -- store prompt vars / model settings used
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_responses_tenant_created_at ON llm_responses (tenant_id, created_at);

-- Table: llm_cache (semantic cache)
CREATE TABLE IF NOT EXISTS llm_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    prompt_embedding vector(384),
    embedding_model_name TEXT,
    embedding_dim INT,
    response TEXT NOT NULL,
    model_used TEXT,
    confidence_score FLOAT,
    ttl_seconds INT DEFAULT 3600,
    usage_count INT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- IVFFLAT index for semantic search
CREATE INDEX IF NOT EXISTS idx_llm_cache_embedding_ivfflat
ON llm_cache USING ivfflat (prompt_embedding vector_cosine_ops)
WITH (lists = 100);

-- Index: created_at for eviction policies and TTL-based maintenance
CREATE INDEX IF NOT EXISTS idx_llm_cache_created_at ON llm_cache (created_at);

CREATE INDEX IF NOT EXISTS idx_llm_cache_tenant_prompt_hash ON llm_cache (tenant_id, prompt_hash);

-- Table: llm_review_queue
CREATE TABLE IF NOT EXISTS llm_review_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    response_id UUID REFERENCES llm_responses(id),
    prediction_id UUID,
    review_reason TEXT,
    priority TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'pending',
    assigned_to TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_review_queue_tenant_status ON llm_review_queue (tenant_id, status);

-- Table: llm_feedback_examples
CREATE TABLE IF NOT EXISTS llm_feedback_examples (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    prompt TEXT NOT NULL,
    context JSONB,
    corrected_response TEXT NOT NULL,
    prompt_template_id UUID,
    original_response_id UUID REFERENCES llm_responses(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tenant isolation / RLS example for llm_cache (optional)
-- If you use row level security, enable and add policy similar to other vector tables
-- ALTER TABLE llm_cache ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY tenant_isolation_llm_cache ON llm_cache
--     USING (tenant_id = current_setting('app.current_tenant_id', TRUE));

-- Function: helper to check embedding dimension (optional)
CREATE OR REPLACE FUNCTION check_embedding_dim() RETURNS VOID AS $$
BEGIN
    -- This is a placeholder function. Validate embedding_dim on insert via application layer.
    RAISE NOTICE 'Embedding dim checks should be enforced by application using EMBEDDING_DIM config.';
END;
$$ LANGUAGE plpgsql;

-- Cleanup: ensure gen_random_uuid exists via pgcrypto or pgcrypto enabled elsewhere
-- Note: gen_random_uuid() requires the 'pgcrypto' extension in some setups; if absent, replace with uuid_generate_v4()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- End of migration