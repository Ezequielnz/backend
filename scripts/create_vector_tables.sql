-- Phase 2: Vector Enrichment - Database Setup
-- This script creates the necessary tables and extensions for vector database functionality

-- Enable pgvector extension (requires pgvector to be installed)
CREATE EXTENSION IF NOT EXISTS vector;

-- Create enum for embedding status
CREATE TYPE embedding_status AS ENUM ('pending', 'processing', 'completed', 'failed', 'skipped');

-- Create enum for priority levels
CREATE TYPE embedding_priority AS ENUM ('low', 'medium', 'high', 'critical');

-- Main vector embeddings table with tenant isolation
CREATE TABLE IF NOT EXISTS vector_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    content_type TEXT NOT NULL, -- 'sales_data', 'product_description', 'customer_feedback', etc.
    content_id TEXT NOT NULL, -- ID of the original content (e.g., product_id, sale_id)
    content_hash TEXT NOT NULL, -- Hash of original content for duplicate detection
    embedding_vector vector(384), -- 384 dimensions for sentence-transformers/all-MiniLM-L6-v2
    metadata JSONB DEFAULT '{}', -- Additional metadata about the content
    pii_hash TEXT, -- Hash of PII data for compliance tracking
    priority embedding_priority DEFAULT 'medium',
    status embedding_status DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    UNIQUE(tenant_id, content_type, content_id)
);

-- Vector indexes for tenant-specific searches
CREATE INDEX IF NOT EXISTS idx_vector_embeddings_tenant_content ON vector_embeddings(tenant_id, content_type);
CREATE INDEX IF NOT EXISTS idx_vector_embeddings_status_priority ON vector_embeddings(status, priority);
CREATE INDEX IF NOT EXISTS idx_vector_embeddings_created_at ON vector_embeddings(created_at);
CREATE INDEX IF NOT EXISTS idx_vector_embeddings_pii_hash ON vector_embeddings(pii_hash) WHERE pii_hash IS NOT NULL;

-- Vector index for similarity search (IVFFlat for better performance)
CREATE INDEX IF NOT EXISTS idx_vector_embeddings_vector_tenant
ON vector_embeddings USING ivfflat (embedding_vector vector_cosine_ops)
WHERE tenant_id IS NOT NULL;

-- PII protection tracking table
CREATE TABLE IF NOT EXISTS pii_protection_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    content_type TEXT NOT NULL,
    content_id TEXT NOT NULL,
    original_hash TEXT NOT NULL, -- Hash of original content before PII removal
    sanitized_hash TEXT NOT NULL, -- Hash of content after PII sanitization
    pii_fields_detected JSONB DEFAULT '[]', -- List of PII fields found and removed
    sanitization_method TEXT NOT NULL, -- Method used for PII removal
    compliance_status TEXT NOT NULL, -- 'compliant', 'review_required', 'failed'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    reviewed_by TEXT, -- User who reviewed the sanitization
    reviewed_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes for PII protection log
CREATE INDEX IF NOT EXISTS idx_pii_protection_tenant_content ON pii_protection_log(tenant_id, content_type);
CREATE INDEX IF NOT EXISTS idx_pii_protection_compliance ON pii_protection_log(compliance_status);
CREATE INDEX IF NOT EXISTS idx_pii_protection_created_at ON pii_protection_log(created_at);

-- Embedding queue for priority processing
CREATE TABLE IF NOT EXISTS embedding_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    content_type TEXT NOT NULL,
    content_id TEXT NOT NULL,
    priority embedding_priority DEFAULT 'medium',
    queued_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    scheduled_for TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processing_started_at TIMESTAMP WITH TIME ZONE,
    processing_completed_at TIMESTAMP WITH TIME ZONE,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    error_message TEXT,
    worker_id TEXT, -- ID of worker processing this item
    UNIQUE(tenant_id, content_type, content_id)
);

-- Indexes for embedding queue
CREATE INDEX IF NOT EXISTS idx_embedding_queue_priority_scheduled ON embedding_queue(priority, scheduled_for);
CREATE INDEX IF NOT EXISTS idx_embedding_queue_tenant_status ON embedding_queue(tenant_id, processing_started_at) WHERE processing_started_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_embedding_queue_worker ON embedding_queue(worker_id) WHERE worker_id IS NOT NULL;

-- Vector search analytics table
CREATE TABLE IF NOT EXISTS vector_search_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    search_query TEXT NOT NULL,
    search_type TEXT NOT NULL, -- 'similarity', 'semantic', 'hybrid'
    filters_used JSONB DEFAULT '{}',
    results_count INTEGER NOT NULL,
    execution_time_ms INTEGER NOT NULL,
    cache_hit BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for search logs
CREATE INDEX IF NOT EXISTS idx_vector_search_tenant_created ON vector_search_logs(tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_vector_search_type_time ON vector_search_logs(search_type, execution_time_ms);

-- Enable Row Level Security (RLS) for tenant isolation
ALTER TABLE vector_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE pii_protection_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE embedding_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE vector_search_logs ENABLE ROW LEVEL SECURITY;

-- Create RLS policies for tenant isolation
-- Only allow tenants to access their own data
CREATE POLICY "tenant_isolation_vector_embeddings" ON vector_embeddings
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', TRUE));

CREATE POLICY "tenant_isolation_pii_protection" ON pii_protection_log
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', TRUE));

CREATE POLICY "tenant_isolation_embedding_queue" ON embedding_queue
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', TRUE));

CREATE POLICY "tenant_isolation_search_logs" ON vector_search_logs
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id', TRUE));

-- Create function to set tenant context
CREATE OR REPLACE FUNCTION set_tenant_context(tenant_id TEXT)
RETURNS void AS $$
BEGIN
    PERFORM set_config('app.current_tenant_id', tenant_id, true);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create function to get tenant context
CREATE OR REPLACE FUNCTION get_tenant_context()
RETURNS TEXT AS $$
BEGIN
    RETURN current_setting('app.current_tenant_id', TRUE);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add updated_at triggers
CREATE TRIGGER update_vector_embeddings_updated_at
    BEFORE UPDATE ON vector_embeddings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create view for tenant-specific vector statistics
CREATE OR REPLACE VIEW tenant_vector_stats AS
SELECT
    tenant_id,
    content_type,
    status,
    COUNT(*) as count,
    MIN(created_at) as first_created,
    MAX(updated_at) as last_updated,
    AVG(retry_count) as avg_retries
FROM vector_embeddings
WHERE tenant_id = current_setting('app.current_tenant_id', TRUE)
GROUP BY tenant_id, content_type, status;

-- Grant appropriate permissions (adjust as needed for your setup)
-- GRANT USAGE ON SCHEMA public TO authenticated;
-- GRANT SELECT, INSERT, UPDATE ON vector_embeddings TO authenticated;
-- GRANT SELECT, INSERT ON pii_protection_log TO authenticated;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON embedding_queue TO authenticated;
-- GRANT SELECT, INSERT ON vector_search_logs TO authenticated;

COMMENT ON TABLE vector_embeddings IS 'Stores vector embeddings with tenant isolation and PII protection';
COMMENT ON TABLE pii_protection_log IS 'Tracks PII sanitization and compliance for vectorized content';
COMMENT ON TABLE embedding_queue IS 'Priority queue for incremental embedding processing';
COMMENT ON TABLE vector_search_logs IS 'Analytics and monitoring for vector search operations';