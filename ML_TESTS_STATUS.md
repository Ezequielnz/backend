# ML — Estado de Tests de Predicción de Ventas

Este documento resume los resultados y detalles técnicos de los tests corridos hasta ahora para el módulo de predicción de ventas.

## Resumen de ejecución reciente
- 26 passed, 1 skipped en el backend (histórico; warnings sólo en tests de Celery locales; no afectan los tests ML).
- Lotes ML recientes:
  - Subset 1: 8 tests añadidos (unit + integración + cobertura). Resultado: 8 passed, 0 skipped. Warnings menores de pandas por deprecations de dtype (sin impacto funcional).
  - Subset 2: 4 tests añadidos (persistencia de features, overrides por tenant + pipeline, estabilidad de métricas con holdout). Resultado: 4 passed, 0 skipped.
- Los tests ML cubren integración end-to-end, backtesting multi-horizonte, robustez ante ruido/gaps/outliers/series cortas/shift estacional, aislamiento multi-tenant e idempotencia, y ahora además: transformaciones/normalización de series, features de tiempo y lags, serialización/deserialización completa de modelos, trigger de reentrenamiento, anomalías STL unitarias, cobertura nominal de intervalos y estabilidad de métricas entre períodos.

## Cobertura actual (lo que ya pasa)

### Integración end-to-end
- Pipeline completo con ingesta → validación (CV) → entrenamiento → inferencia → persistencia en `ml_predictions`: cubierto por `tests/ml/test_ml_candidates_and_drift.py`, `tests/ml/test_cv_multi_horizon.py`, `tests/ml/test_stress_series.py`.
- Entrenamiento y guardado de modelo por tenant (idempotente): cubierto por `tests/ml/test_isolation_idempotence.py` usando `on_conflict` en `ml_models`.
- Aislamiento multi-tenant (sin cruces de llaves entre tenants): cubierto por `tests/ml/test_isolation_idempotence.py`.
- Logging y captura de anomalías (upsert a `ml_predictions` con `prediction_type='sales_anomaly'`): cubierto por `tests/ml/test_stress_series.py`.
- Alerta por drift (si MAPE > umbral → notificación): cubierto por `tests/ml/test_ml_candidates_and_drift.py`.

### Backtesting & evaluación
- Rolling CV multi-horizonte con comparación de candidatos (naive, snaive, SARIMAX, Prophet, XGBoost opcional): cubierto por `tests/ml/test_cv_multi_horizon.py` y `tests/ml/test_ml_candidates_and_drift.py`.
  - Nota: XGBoost se salta si no está instalado (skip) — el mecanismo de skip funciona.

- Cobertura nominal de intervalos: `tests/ml/test_interval_coverage_sarimax.py` verifica cobertura ~80% (tolerancia amplia 65–90%) para SARIMAX sobre serie AR(1) sintética con holdout. Confirma que los intervalos producidos cubren el porcentaje esperado.
 
- Estabilidad de métricas entre períodos (holdout por tenant): `tests/ml/test_tenant_overrides_and_pipeline.py::test_holdout_stability_across_periods` corre el pipeline dos veces con periodos ligeramente distintos y verifica |ΔMAPE| ≤ 0.1.

### Robustez / stress
- Datos con huecos (faltantes): cubierto en `tests/ml/test_stress_series.py` (variant "gaps").
- Series muy cortas (cold-start, ~7 días): cubierto en `tests/ml/test_stress_series.py` (variant "short_series").
- Outliers fuertes: cubierto en `tests/ml/test_stress_series.py` (variant "outliers").
- Cambios abruptos de estacionalidad/amplitud: cubierto en `tests/ml/test_stress_series.py` (variant "seasonal_shift").
- Además, se validan salidas sin NaNs y el orden de intervalos (yhat_lower ≤ yhat ≤ yhat_upper), y la presencia de anomalías cuando corresponde.

### Unit tests (nuevo)
- Transformaciones de series (resampling/tz/imputación): `tests/ml/test_feature_engineer_transformations.py` valida que `FeatureEngineer.sales_timeseries_daily(...)`:
  - Normaliza `fecha` a `ds` (date), maneja mezclas tz-aware/naive, rellena días faltantes con 0 y agrega `total` (Decimal/str/None → float).
- Features temporales y lags: `tests/ml/test_engine_time_features.py` cubre `BusinessMLEngine._make_time_features` (dow/dom/month) y `_add_lags` (desplazamientos correctos y NaN iniciales).
- Serialización/deserialización: `tests/ml/test_model_serialization.py` prueba round-trip `ModelVersionManager.save_model()` → `load_active_model()` con `joblib` + `base64` (BYTEA simulado en `ml_models`).
- Anomalías STL univariantes: `tests/ml/test_anomalies_stl.py` inyecta un bloque de outliers y valida que el detector marque una fracción significativa en el bloque y globalmente acotada.
- Persistencia de features (ma7/ma28 y esquema `ml_features`): `tests/ml/test_persist_sales_features.py` verifica cálculo de `ma7`/`ma28`, `daily_total` y upsert con `on_conflict="tenant_id,feature_date,feature_type"`.

### Integración (nuevo)
- Trigger de reentrenamiento (Celery): `tests/ml/test_worker_retrain_integration.py` ejecuta `retrain_all_models.run()` (sin worker) con `FakeSupabase` y stub de `train_and_predict_sales`, verificando iteración por múltiples tenants, métricas CV, y suma de pronósticos upsertados.

### Personalización / multi-tenant
- Aislamiento de datos (A no afecta B): cubierto.
- Upserts idempotentes por tenant/horizonte/fecha/tipo: cubierto.
- Overrides por tenant y reflejo en hiper-parámetros guardados: `tests/ml/test_tenant_overrides_and_pipeline.py::test_pipeline_saves_hyperparams_reflecting_overrides` mockea `tenant_ml_settings` y valida que `pipeline.save_model` (vía `ModelVersionManager`) persista `hyperparameters` con `cv_folds`, `seasonality_mode`, `holidays_country`, `cv_primary_metric`, `model_candidates` y, si aplica, `baseline_variant`.

### Selección de modelo / hyper-parámetros
- Comparación entre naive / snaive / SARIMAX / Prophet: cubierto.
- XGBoost probado si disponible; si no, se marca como skip (mecanismo funcionando).

---

## Detalles técnicos relevantes
- Orquestador principal: `app/services/ml/pipeline.py` → función `train_and_predict_sales(...)`.
  - Upsert de pronósticos a `ml_predictions` con `on_conflict="tenant_id,prediction_date,prediction_type"`.
  - Detección de anomalías por STL residual (`prediction_type='sales_anomaly'`) y upsert en la misma tabla.
  - Intervalos de predicción saneados para evitar NaNs y forzar `yhat_lower ≤ yhat ≤ yhat_upper`.
- Modelos candidatos: `naive`, `snaive`, `sarimax`, `prophet`, `xgboost` (opcional).
- Manager de versiones de modelo por tenant: `app/services/ml/model_version_manager.py` (upsert a `ml_models` con `on_conflict="tenant_id,model_type,model_version"`).
- Cliente Supabase centralizado: `app/db/supabase_client.py` vía `get_supabase_service_client()`.

### Novedades técnicas del lote actual
- `FeatureEngineer` (archivo `app/services/ml/feature_engineer.py`):
  - `_to_datetime_series(..., utc=True)` por defecto para robustez con entradas mixtas tz-aware/naive; en el reindexado continuo se usa conversión "naive" (`utc=None`) para construir el índice diario y luego se convierte de nuevo a `date`. El contrato de salida se mantiene (`ds: date`, `y: float`).
- `ModelVersionManager`:
  - Validado round-trip `joblib` + `base64` contra `ml_models` simulado (BYTEA/JSON string), y `load_active_model()` ordenado por `last_trained` desc.
- `ml_worker.retrain_all_models`:
  - Test integra el trigger usando `.run()` y parchea `get_supabase_service_client` desde `app.db.supabase_client` para aislar de entornos reales; `train_and_predict_sales` se stubbea para evitar entrenamiento pesado.

## Ubicación de los tests
- `tests/ml/test_ml_candidates_and_drift.py`
- `tests/ml/test_cv_multi_horizon.py`
- `tests/ml/test_stress_series.py`
- `tests/ml/test_isolation_idempotence.py`
- `tests/ml/test_feature_engineer_transformations.py`
- `tests/ml/test_engine_time_features.py`
- `tests/ml/test_model_serialization.py`
- `tests/ml/test_anomalies_stl.py`
- `tests/ml/test_worker_retrain_integration.py`
- `tests/ml/test_interval_coverage_sarimax.py`
- `tests/ml/test_persist_sales_features.py`
- `tests/ml/test_tenant_overrides_and_pipeline.py`

## Nota
- Los tests de XGBoost se ejecutan sólo si el paquete está instalado; de lo contrario se marcan `skip`.
- Las advertencias registradas en la última corrida corresponden a tests locales de Celery (no ML) y no afectan los escenarios ML definidos arriba.
 - En el nuevo subset ML, aparecieron warnings de pandas (FutureWarning por inferencia de dtype en `Index`/asignación de series) sin impacto funcional; se dejan documentados para seguimiento.
