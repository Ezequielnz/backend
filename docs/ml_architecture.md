# ML Ventas (Multi-tenant, Argentina) – Arquitectura y Configuración

Este documento describe la arquitectura del módulo de ML para predicción de ventas y detección de anomalías, con foco multi-tenant (PyMEs argentinas) y operación en contextos cambiantes (inflación, estacionalidad, feriados).

## Diagrama de Flujo (alto nivel)

```
Ingesta (Supabase) → Feature Engineering (timeseries diarias)
        ↓
Candidatos de Modelo (Prophet | SARIMAX | [Baseline|XGBoost opcional])
        ↓
CV (forward-chaining, n folds) con métricas (MAPE, sMAPE, MAE, RMSE, timing)
        ↓
Selección (automática por métrica primaria o forzada por flags)
        ↓
Entrenamiento final (todo el histórico)
        ↓
Forecast (horizon N días) + Intervalos de confianza
        ↓
Anomalías (STL residuales o IsolationForest)
        ↓
Persistencia (ml_models, ml_predictions) + Métricas/hiperparámetros
```

## Módulos Principales

- `app/services/ml/feature_engineer.py`: construcción de series diarias por negocio (`sales_timeseries_daily`) y persistencia de features.
- `app/services/ml/ml_engine.py`: wrappers de entrenamiento e inferencia (Prophet, SARIMAX, anomalías).
- `app/services/ml/pipeline.py`: orquestación E2E `train_and_predict_sales()` con CV, selección, forecast, anomalías y persistencia.
- `app/services/ml/model_version_manager.py`: versionado y almacenamiento de modelos (`ml_models`).
- `app/workers/ml_worker.py`: tareas periódicas con Celery (re-entrenos, actualización de features, generación de predicciones bajo demanda).

## Multi-tenant

- Aislamiento por `tenant_id` (a.k.a. `business_id`) en todas las consultas y escrituras.
- Tablas clave:
  - `ml_models(tenant_id, model_type, model, model_version, hyperparameters JSON, training_metrics JSON, accuracy, is_active)`
  - `ml_predictions(tenant_id, model_id, prediction_date, prediction_type, predicted_values JSON, confidence_score)`
  - `ml_features(...)` (para métricas derivadas de ventas e inventario, si aplica)
- Caché y claves incluyen el `tenant_id` (ver `cache_manager` y decoradores de caché en `app/core/cache_decorators.py`).

## Configuración vía Flags de Entorno (`app/core/config.py`)

- `ML_CV_FOLDS`: cantidad de folds para validación cruzada (forward-chaining).
- `ML_SEASONALITY_MODE`: `additive` o `multiplicative` (Prophet).
- `ML_HOLIDAYS_COUNTRY`: código país feriados (ej. `AR`).
- `ML_LOG_TRANSFORM`: aplicar transformación log1p a la variable objetivo.
- `ML_MODEL_CANDIDATES`: lista separada por comas, ej. `prophet,sarimax`.
- `ML_SELECT_BEST`: habilita selección automática por métrica primaria.
- `ML_CV_PRIMARY_METRIC`: `mape|smape|mae|rmse` para selección.
- `ML_SARIMAX_ORDER`: tupla `p,d,q` o string `"p,d,q"`.
- `ML_SARIMAX_SEASONAL`: tupla `P,D,Q,s` o string `"P,D,Q,s"`.
- `ML_ANOMALY_METHOD`: `stl_resid` o `iforest`.
- `ML_STL_PERIOD`: periodo STL para descomposición estacional.

Todos los flags son leídos y normalizados en `train_and_predict_sales()`.

## Modelos y Selección

- Soportados: Prophet, SARIMAX. Diseño preparado para agregar Baseline/XGBoost.
- Selección automática: se evalúan candidatos con CV y se elige por `ML_CV_PRIMARY_METRIC` si `ML_SELECT_BEST=true`.
- Forzado por flags: establecer `ML_MODEL_CANDIDATES` con un solo modelo.

## Métricas y Explicabilidad

- Métricas por fold y agregadas: `MAPE`, `sMAPE`, `MAE`, `RMSE`. Se registran también tiempos de entrenamiento e inferencia.
- Accuracy reportada como `1 - MAPE` (recortada a [0,1]).
- Intervalos de confianza: incluidos en `predicted_values` (`yhat_lower`, `yhat_upper`).
- `confidence_score`: derivado de ancho del intervalo, `1/(1 + width/|yhat|)` acotado a [0,1].
- `training_metrics` e `hyperparameters` se guardan JSON-normalizados y libres de NaN/Inf.

## Manejo de Datos Ruidosos y Faltantes

- Normalización robusta en Feature Engineering (series diarias continuas).
- Opción `ML_LOG_TRANSFORM` reduce asimetrías/extremos.
- Detección de anomalías:
  - `stl_resid`: residuales del modelo, z-score sobre componente de residuo.
  - `iforest`: Isolation Forest sobre la serie (alternativa sin modelo).
- Interpolación: donde aplica, pandas rellena gaps para entrenar modelos temporales.

## Reentrenamiento y Concept Drift

- Celery tasks (`app/workers/ml_worker.py`):
  - `retrain_all_models`: re-entrena modelos activos (programar CRON, ej. semanal).
  - `update_business_features`: refresca features por negocio periódicamente.
  - `generate_predictions`: genera bajo demanda usando modelo activo o pipeline inicial.
- Concept drift (plan): monitorear tendencia de error (MAPE/sMAPE) vs. historial. Disparar alerta/notificación si excede umbrales.

## Logging Estructurado (JSON)

- `_log_ml()` unifica eventos en pipeline y worker.
- Eventos claves: `ml_pipeline_start`, `ml_cv_result`, `ml_validation_completed`, `ml_final_training`, `ml_model_saved`, `ml_forecast_upsert`, `ml_anomaly_upsert`, `ml_pipeline_end`, `ml_retrain_start`, `ml_cv_summary`, `ml_retrain_tenant_done`, `ml_retrain_end`, `ml_update_features_end`, `ml_prediction_generated`, `ml_trends_done`.

## Integración con BD

- `ml_models.training_metrics` contiene:
  ```json
  {
    "mape": 0.14,
    "smape": 0.2,
    "mae": 120.5,
    "rmse": 200.3,
    "cv": { "folds": 3, "horizon_days": 14, "metrics_per_fold": [...] },
    "timing": { "train_time": 3.1, "infer_time": 0.5 },
    "selected_model": "prophet",
    "candidate_metrics": { "prophet": {...}, "sarimax": {...} }
  }
  ```
- `ml_predictions.predicted_values` (forecast): `{ "yhat": 123.4, "yhat_lower": 100.0, "yhat_upper": 150.0 }`
- `ml_predictions.predicted_values` (anomaly): `{ "y": 80.0, "score": 0.9, "is_anomaly": true }`

## Pruebas Recomendadas

- Validación cruzada con distintos horizontes (`horizon_days`) y folds (`ML_CV_FOLDS`).
- Stress test con datos ruidosos y faltantes (inserción de outliers, gaps artificiales).
- Comparación de Prophet vs SARIMAX vs baseline (naive). Baseline puede implementarse como `naive_last_value` o `seasonal_naive` para benchmarking.
- Testing multi-tenant: varios `tenant_id` en paralelo, verificar aislamiento de datos.
- Tests de regresión: asegurar que métricas/outputs no empeoran tras cambios.

## Interpretación de Outputs

- `accuracy`: aproximación como `1 - MAPE` (0 a 1).
- `predicted_values`: valor central y banda de confianza  (más ancho = menor confianza).
- `confidence_score`: score heurístico a partir del ancho del intervalo (0 a 1).
- `metrics_summary`: incluye modelo elegido y métricas agregadas; usarlo para comparar entrenos.

## Dependencias

- Requeridas: `prophet`, `statsmodels==0.14.3`, `pydantic`, `pandas`, `numpy`, `holidays`, `scikit-learn`.
- Opcionales: `xgboost`, `pandera` o `great-expectations` (validación de datos) para etapas posteriores.

## Próximos Pasos

1. Agregar baseline y (opcional) XGBoost como candidato.
2. Implementar alerta de concept drift y umbrales configurables.
3. Añadir tests automatizados (pytest) para CV multi-horizonte, ruido/faltantes y comparación de modelos.
