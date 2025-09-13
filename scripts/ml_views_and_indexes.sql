-- ML schema views and indexes (non-destructive)
-- This script maps existing ml_predictions/ml_models into convenient views and adds helpful indexes.
-- It keeps current app behavior intact.

-- 1) Views
-- sales_forecast: normalized forecast outputs with confidence and model info
CREATE OR REPLACE VIEW sales_forecast AS
SELECT
  p.tenant_id,
  p.prediction_date::date AS ds,
  (p.predicted_values->>'yhat')::numeric AS yhat,
  (p.predicted_values->>'yhat_lower')::numeric AS yhat_lower,
  (p.predicted_values->>'yhat_upper')::numeric AS yhat_upper,
  p.confidence_score AS conf_score,
  LEAST(3650, GREATEST(0, (p.prediction_date::date - CURRENT_DATE))) AS horizon,
  m.model_type AS model,
  p.model_id,
  p.created_at AS created_at
FROM ml_predictions p
LEFT JOIN ml_models m ON m.id = p.model_id
WHERE p.prediction_type = 'sales_forecast';

-- sales_anomaly: anomalies with zscore (score) and method from model hyperparameters
CREATE OR REPLACE VIEW sales_anomaly AS
SELECT
  p.tenant_id,
  p.prediction_date::date AS ds,
  NULL::numeric AS residual, -- not persisted today; reserved for future
  (p.predicted_values->>'score')::numeric AS zscore,
  COALESCE(m.hyperparameters->>'anomaly_method', 'unknown') AS method,
  COALESCE((m.hyperparameters->>'stl_period')::int, NULL) AS stl_period,
  COALESCE((m.hyperparameters->>'stl_zthresh')::numeric, NULL) AS z_threshold,
  p.created_at AS created_at
FROM ml_predictions p
LEFT JOIN ml_models m ON m.id = p.model_id
WHERE p.prediction_type = 'sales_anomaly';

-- training_metrics: flattened metrics per model version
CREATE OR REPLACE VIEW training_metrics AS
SELECT
  m.tenant_id,
  m.model_type AS model,
  m.id AS model_id,
  COALESCE((m.hyperparameters->>'horizon_days')::int, NULL) AS horizon,
  COALESCE((m.hyperparameters->>'cv_folds')::int, NULL) AS cv_folds,
  (m.training_metrics->>'mape')::numeric AS mape,
  (m.training_metrics->>'smape')::numeric AS smape,
  (m.training_metrics->>'mae')::numeric AS mae,
  (m.training_metrics->>'rmse')::numeric AS rmse,
  m.last_trained AS timestamp
FROM ml_models m;

-- 2) Indexes to support idempotent upserts and fast queries
-- Unique key used by app upserts today
-- Fast lookups by tenant/date
CREATE INDEX IF NOT EXISTS idx_ml_predictions_tenant_date
  ON ml_predictions(tenant_id, prediction_date);

-- Fast lookups by tenant/type/date
CREATE INDEX IF NOT EXISTS idx_ml_predictions_tenant_type_date
  ON ml_predictions(tenant_id, prediction_type, prediction_date);

-- Metrics time filtering by tenant
CREATE INDEX IF NOT EXISTS idx_ml_models_tenant_last_trained
  ON ml_models(tenant_id, last_trained);

-- Note on RLS: ensure RLS policies on ml_predictions/ml_models restrict rows by tenant_id for non-service keys.
-- Views inherit RLS from underlying tables.
