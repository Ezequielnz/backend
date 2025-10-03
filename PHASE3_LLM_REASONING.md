
# Phase 3: LLM Reasoning Core — Implementation & Integration Guide

## Purpose
This document is the single-source technical documentation for Phase 3 (LLM Reasoning Core). It records the design, files to create, integration points, gating checks, migration notes, environment variables, testing strategy and rollout checklist. Use this document as the authoritative guide during implementation and review.

## High-level summary
Goal: Provide cost-controlled, high-quality, auditable natural-language explanations for ML predictions and anomalies with a human-in-the-loop feedback loop that improves prompts and models over time.

High-level flow:
- ML pipeline detects predictions/anomalies (see [`app/services/ml/pipeline.py`](app/services/ml/pipeline.py:264))
- Vector enrichment provides context (see [`app/services/ml/vector_enrichment_service.py`](app/services/ml/vector_enrichment_service.py:1))
- LLM Reasoning Service decides to call LLM (impact check) and coordinates cache, cost control, vendor calls and QA
- Responses are validated; low-confidence items are enqueued for human review
- Feedback is stored and consumed by a prompt optimizer worker

## Document structure
- Overview & diagram
- File-by-file responsibilities (what to create and how it integrates)
- Gating checks (Step A) and how to run them
- Database migrations (schema + notes)
- Environment variables and config
- Tests and QA
- Observability and metrics
- Rollout & staging checklist
- Appendix: useful commands and examples

---

## ASCII Logical Diagram
ML Pipeline -> [`app/services/ml/vector_enrichment_service.py`](app/services/ml/vector_enrichment_service.py:1) -> [`app/services/llm_reasoning_service.py`](app/services/llm_reasoning_service.py:1)
  ├─> Exact cache (Redis)
  ├─> Semantic cache (pgvector - [`llm_cache`])
  ├─> Cost Estimator (`tiktoken`) + Redis budget counters
  ├─> LLM Client (primary -> fallback)
  ├─> Circuit Breaker (Redis-based)
  ├─> QA / Confidence Scorer (embedding evidence + optional NLI)
  ├─> Human Review Queue (`llm_review_queue`)
  └─> Feedback store (`llm_feedback_examples`) -> Prompt Optimizer Worker

---

## File-by-file specification (what to create and integration notes)

Note: each filename below is referenced as a clickable link to its intended path and a recommended starting line number for context.

- Core orchestration
  - [`app/services/llm_reasoning_service.py`](app/services/llm_reasoning_service.py:1)
    - Responsibilities:
      - Public API: `reason(tenant_id, prediction_id, prediction_data, impact_score, async=True|False)`
      - Decide to call LLM via `_should_call_llm(impact_score, tenant_settings)`
      - Build RAG prompt: `_build_prompt(prediction, vector_context, tenant_settings)`
      - Exact & semantic cache checks via [`app/services/semantic_cache.py`](app/services/semantic_cache.py:1)
      - Cost estimation and budget reservation via [`app/services/cost_estimator.py`](app/services/cost_estimator.py:1)
      - Vendor call via [`app/services/llm_client.py`](app/services/llm_client.py:1) wrapped with circuit breaker [`app/services/circuit_breaker.py`](app/services/circuit_breaker.py:1)
      - Validation & scoring via [`app/services/response_validator.py`](app/services/response_validator.py:1) and [`app/services/confidence_scorer.py`](app/services/confidence_scorer.py:1)
      - Persistence of responses to `llm_responses` table and caching to `llm_cache`
      - Enqueue human review if confidence < threshold

- Vendor abstraction
  - [`app/services/llm_client.py`](app/services/llm_client.py:1)
    - Responsibilities:
      - Wrap providers (OpenAI, Azure, Anthropic, local)
      - Accept settings: model, timeout, max_tokens, temperature
      - Return: text, tokens_used, raw_response, model_name, latency, error_info
      - Implement retries with backoff (`tenacity`) and integrate with circuit breaker

- Cost & budget
  - [`app/services/cost_estimator.py`](app/services/cost_estimator.py:1)
    - Responsibilities:
      - Token count using `tiktoken` (or fallback heuristic)
      - Convert tokens -> cost using pricing config or DB table `llm_model_pricing`
      - Reserve budget atomically in Redis using Lua script (`scripts/redis/atomic_budget_reserve.lua`)
      - Expose `estimate_cost(prompt, expected_output_tokens)` and `reserve_budget(tenant_id, cost)`, `release_budget(...)` for rollback

- Cache layer
  - [`app/services/semantic_cache.py`](app/services/semantic_cache.py:1)
    - Responsibilities:
      - Exact cache (Redis) keyed by `sha256(prompt)` with TTL (EXACT_TTL)
      - Semantic cache backed by Postgres `llm_cache` table (pgvector)
      - Ensure embedding model/version compatibility (`embedding_model_name`, `embedding_dim`)
      - Operations: `get_exact(prompt_hash)`, `get_semantic_by_embedding(embedding, threshold)`, `insert_cache_entry(...)`

- Circuit breaker
  - [`app/services/circuit_breaker.py`](app/services/circuit_breaker.py:1)
    - Redis-based circuit breaker per (tenant, model)
    - API: `is_open(model, tenant)`, `record_failure(model, tenant)`, `record_success(model, tenant)`
    - Configurable thresholds and open window times

- QA & Confidence
  - [`app/services/response_validator.py`](app/services/response_validator.py:1)
    - RAG evidence check: split response into claims, verify each claim via similarity against vector context; mark unsupported claims
    - PII safety check via existing [`app/services/ml/pii_utils.py`](app/services/ml/pii_utils.py:130)
  - [`app/services/confidence_scorer.py`](app/services/confidence_scorer.py:1)
    - Combine evidence support score, NLI entailment score (optional), semantic coherence score into a weighted confidence

- Workers
  - [`app/workers/llm_worker.py`](app/workers/llm_worker.py:1)
    - Celery task to run `LLMReasoningService.reason` asynchronously and persist results
    - Handles retry/timeouts and budget rollback on failure
  - [`app/workers/prompt_optimizer.py`](app/workers/prompt_optimizer.py:1)
    - Offline worker that samples `llm_feedback_examples` and proposes prompt template updates or few-shot examples

- API endpoints
  - [`app/api/api_v1/endpoints/llm.py`](app/api/api_v1/endpoints/llm.py:1)
    - Endpoints:
      - POST /api/v1/llm/reason -> trigger reasoning (returns async token / job id)
      - GET /api/v1/llm/responses/{id} -> fetch response + metadata
      - POST /api/v1/llm/review/{id}/action -> approve/edit/reject
      - GET /api/v1/metrics/llm -> internal summary (RBAC protected)

- DB models
  - [`app/models/llm_models.py`](app/models/llm_models.py:1)
    - SQLAlchemy/Pydantic models for `llm_responses`, `llm_cache`, `llm_review_queue`, `llm_feedback_examples`, `tenant_llm_settings`, `llm_model_pricing`

- Migrations
  - `migrations/00_create_llm_tables.sql` (create the tables in the DB; see "Database schema" section below)

---

## Step A — Gating: environment & config validation (must pass)
Before writing migration code or any production code, perform the following checks. Do NOT proceed to migrations until all pass.

1) Confirm embedding model and dimension
- Inspect embedding pipeline for active model and expected dim:
  - File: [`app/services/ml/embedding_pipeline.py`](app/services/ml/embedding_pipeline.py:309)
  - Command: open the file and verify `model_name` and whether `SentenceTransformer` or OpenAI embeddings are used.
- Accept criteria:
  - Set `EMBEDDING_MODEL_NAME` and `EMBEDDING_DIM` in config (e.g., [`app/core/config.py`](app/core/config.py:1) or ml_settings).
  - If model is `sentence-transformers/all-MiniLM-L6-v2` -> dim = 384; if OpenAI `text-embedding-3-small` -> dim = 1536.

2) Verify Redis connectivity and version
- Run from the app environment (or local dev container):
  - redis-cli -h $REDIS_HOST -p $REDIS_PORT PING
- Accept criteria: returns `PONG`; connectivity established from API & Celery worker processes.

3) Verify Supabase/Postgres + pgvector
- Run:
  - psql -d micropymes -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
- Accept criteria: extension exists in staging DB (if not, request DBA to install pgvector)

4) Ensure LLM vendor keys present in staging
- Confirm `OPENAI_API_KEY` (or vendor keys) exist in staging `.env` or secret manager
- Accept criteria: keys present in staging environment variables or secret store; keys must not be in CI logs.

5) Privacy/legal signoff for `redact_before_send`
- Confirm legal team's decision about redaction policy for tenants
- Accept criteria: policy documented and accessible for engineering

If any check fails: create an issue, and stop. Resolve before proceeding.

---

## Database schema (migrations)
Create a migration `migrations/00_create_llm_tables.sql` with the following core tables. Use parameter substitution for VECTOR dimension (`EMBEDDING_DIM`) based on config.

Core tables (condensed):

- llm_responses
  - id UUID PRIMARY KEY DEFAULT gen_random_uuid()
  - tenant_id TEXT NOT NULL
  - prediction_id UUID
  - prompt_hash TEXT NOT NULL
  - prompt_template_id TEXT
  - prompt_version TEXT
  - prompt_text TEXT -- store redacted prompt only if `redact_before_send=false`; otherwise store prompt_hash only
  - response TEXT NOT NULL
  - model_used TEXT
  - prompt_embedding_model TEXT
  - confidence_score FLOAT
  - tokens_used INT
  - cost_estimate FLOAT
  - response_type TEXT -- 'full'|'degraded'|'cached'|'fallback'
  - pii_redaction_applied BOOLEAN DEFAULT FALSE
  - created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()

- llm_cache
  - id UUID PRIMARY KEY DEFAULT gen_random_uuid()
  - tenant_id TEXT NOT NULL
  - prompt_hash TEXT NOT NULL
  - prompt_embedding VECTOR(EMBEDDING_DIM)
  - embedding_model_name TEXT
  - embedding_dim INT
  - response TEXT NOT NULL
  - model_used TEXT
  - confidence_score FLOAT
  - created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
  - ttl_seconds INT DEFAULT 3600
  - usage_count INT DEFAULT 0

- llm_review_queue
  - id UUID PRIMARY KEY DEFAULT gen_random_uuid()
  - tenant_id TEXT NOT NULL
  - response_id UUID REFERENCES llm_responses(id)
  - prediction_id UUID
  - review_reason TEXT
  - priority TEXT DEFAULT 'medium'
  - status TEXT DEFAULT 'pending'
  - assigned_to TEXT
  - created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()

- llm_feedback_examples
  - id UUID PRIMARY KEY DEFAULT gen_random_uuid()
  - tenant_id TEXT NOT NULL
  - prompt TEXT NOT NULL -- redacted according to tenant policy
  - context JSONB
  - corrected_response TEXT NOT NULL
  - prompt_template_id TEXT
  - original_response_id UUID
  - created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()

- tenant_llm_settings
  - tenant_id TEXT PRIMARY KEY
  - model_preference TEXT
  - daily_budget NUMERIC
  - sem_cache_threshold FLOAT DEFAULT 0.92
  - confidence_threshold FLOAT DEFAULT 0.8
  - human_review_threshold FLOAT DEFAULT 0.6
  - redact_before_send BOOLEAN DEFAULT TRUE
  - created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()

Migration notes:
- Parameterize VECTOR(EMBEDDING_DIM) in migration templates.
- Add IVFFLAT index on `llm_cache.prompt_embedding` as in Phase 2 vector tables for efficient semantic search.
- If RLS is used, add tenant RLS policies following existing patterns (see [`app/services/ml/vector_db_service.py`](app/services/ml/vector_db_service.py:191)).

---

## Environment variables and config
Update `.env.example` and `app/core/config.py` / `app/config/ml_settings.py` to include:

- LLM_DEFAULT_MODEL=gpt-4
- LLM_FALLBACK_MODELS=gpt-3.5-turbo
- LLM_MAX_COST_PER_REQUEST=0.10
- LLM_DAILY_BUDGET=50.00
- EMBEDDING_MODEL_NAME=text-embedding-3-small
- EMBEDDING_DIM=1536
- LLM_CACHE_TTL=3600
- LLM_CIRCUIT_BREAKER_WINDOW=60
- LLM_CIRCUIT_BREAKER_THRESHOLD=5
- LLM_CIRCUIT_BREAKER_OPEN_SECONDS=120
- LLM_CONFIDENCE_THRESHOLD=0.8
- LLM_HUMAN_REVIEW_THRESHOLD=0.6

Implementation note:
- Keep vendor API keys in secret manager; reference via env variables (e.g. OPENAI_API_KEY). Do not commit keys to repo.

---

## Scripts & utilities to add (before implementation)
- `scripts/redis/atomic_budget_reserve.lua` — Lua script to atomically check & increment tenant budget counter:
  - Inputs: tenant_key, amount, budget_limit_key
  - Atomically compute current + amount <= budget then increment and return success/fail

- DB migration: `migrations/00_create_llm_tables.sql` (see schema section)

---

## Tests & QA
Add tests under `tests/`:
- `tests/test_pii_redaction.py`
  - Ensure prompts are redacted prior to vendor call when `redact_before_send=true`
- `tests/test_atomic_budget_reservation.py`
  - Concurrency test that spawns parallel reservations and asserts budget not exceeded
- `tests/test_semantic_cache.py`
  - Insert cached embedding and assert semantic lookup returns it given threshold
- `tests/test_fallback.py`
  - Simulate vendor timeouts and assert fallback model used, degraded response created
- `tests/test_confidence_and_review.py`
  - Simulate invented claim and assert that response is flagged with low confidence and review enqueued

Testing notes:
- Mock external providers (OpenAI) in unit tests.
- Use ephemeral Postgres/Redis (docker-compose) for integration tests.

---

## Observability & metrics
Add Prometheus metrics in relevant modules:
- `llm_calls_total{model,tenant}`
- `llm_call_duration_seconds{model,tenant}` (histogram)
- `llm_cache_hits_total{tenant}`, `llm_cache_misses_total{tenant}`
- `llm_cost_total{tenant}`
- `llm_human_reviews_total{status,tenant}`
- `llm_confidence_distribution` (histogram)
- `llm_budget_usage_ratio{tenant}` (gauge)
Expose metrics endpoint via existing Prometheus integration (if any) or instrument app.

Add OpenTelemetry tracing:
- Instrument spans for pipeline -> vector enrichment -> llm_reasoning -> llm_client to detect latency hotspots.

Alerting suggestions:
- Alert when `llm_cost_total / daily_budget > 0.8`
- Alert when p95 latency > 10s
- Alert when `llm_human_reviews_total / llm_responses_total > 0.1`

---

## Security & privacy countermeasures
- Enforce `redact_before_send` per tenant:
  - Use existing [`app/services/ml/pii_utils.py`](app/services/ml/pii_utils.py:130) to detect and redact
  - Store redaction metadata instead of raw PII in `llm_responses`
- Provide option to store original unredacted prompt only in a secure audit store (requires legal approval)
- Implement retention policy for LLM tables; provide purge job for sensitive data.

---

## Rollout & staging checklist
1. Run gating checks (Step A) and pass all
2. Create migration on staging with correct EMBEDDING_DIM
3. Add new dependencies to staging environment and run smoke tests
4. Deploy with conservative tenant budgets (e.g., $1/day) and verify behavior under load
5. Validate Prometheus metrics and alerting
6. Verify human review UI and feedback persistence
7. Gradually increase budgets and move to production after acceptance

---

## Appendix — Useful commands & examples

Check pgvector presence:
psql -d micropymes -c "SELECT * FROM pg_extension WHERE extname = 'vector';"

Redis ping:
redis-cli -h $REDIS_HOST -p $REDIS_PORT PING

Example: atomic budget Lua stub (create in `scripts/redis/atomic_budget_reserve.lua`):
-- Lua script placeholder; implement in code repository as part of step D

Token estimation example using tiktoken:
- Use `tiktoken.get_encoding()` to count prompt tokens; calibrate expected output tokens

Where to update code & integration points:
- Hook call into pipeline after enrichment: [`app/services/ml/pipeline.py`](app/services/ml/pipeline.py:969) — call the LLM Reasoning Worker asynchronously to avoid blocking
- Reuse central embedding generator: [`app/services/ml/embedding_pipeline.py`](app/services/ml/embedding_pipeline.py:309)

---

## Next actions (what will be added to the repo)
- Create `PHASE3_LLM_REASONING.md` (this file)
- Implement gating