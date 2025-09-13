# ML — Contexto técnico de módulos de predicción y workers

Este documento ofrece un panorama técnico de los módulos de ML y predicciones ya creados en el backend, con foco en:

- `app/services/ml/`
- `app/workers/`
- `app/celery_app.py`
- `app/config/ml_settings.py`

La intención es que sirva como referencia para onboarding, mantenimiento y extensión de la pipeline de pronóstico de ventas.

---

## Arquitectura lógica (alto nivel)

1. Extracción de serie diaria por tenant (`FeatureEngineer.sales_timeseries_daily`).
2. Validación con cross-validation (CV) y selección de modelo (`pipeline.train_and_predict_sales`): naive, snaive, SARIMAX, Prophet y XGBoost (opcional).
3. Entrenamiento final del modelo seleccionado y generación de pronósticos con intervalos.
4. Upsert de predicciones en `ml_predictions` con `on_conflict="tenant_id,prediction_date,prediction_type"`.
5. Detección de anomalías (STL residual o Isolation Forest) y upsert como `prediction_type='sales_anomaly'`.
6. Persistencia del modelo entrenado en `ml_models` con `on_conflict="tenant_id,model_type,model_version"`.
7. Alertas opcionales (p. ej., drift) vía tasks de Celery.

---

## `app/services/ml/`

### `pipeline.py`
- Punto de entrada principal: `train_and_predict_sales(business_id, ...) -> dict[str, object]`.
- Orquesta todo el flujo: extracción de serie, CV y selección, entrenamiento final, forecasting, anomalías, persistencia y logging.
- Persistencia:
  - Predicciones: upsert a `ml_predictions` (chunk de 200 filas) con `on_conflict="tenant_id,prediction_date,prediction_type"`. `predicted_values` es JSON con `yhat`, `yhat_lower`, `yhat_upper`. `confidence_score` se deriva del ancho del intervalo.
  - Modelos: utiliza `ModelVersionManager` para guardar el modelo y métricas en `ml_models`.
- Anomalías:
  - `anomaly_method="stl_resid"`: calcula residuales in-sample vs. (Prophet/SARIMAX) y aplica STL para flaggear outliers; persiste como `sales_anomaly`.
  - Alternativa: Isolation Forest (univariado) con `detect_anomalies`.
- Sanitización de intervalos: se evita NaN en `yhat_lower/upper` y se fuerza el orden `yhat_lower ≤ yhat ≤ yhat_upper` ante escenarios extremos.
- Observabilidad: logging estructurado en JSON (`_log_ml`) para eventos clave (inicio/fin pipeline, métricas CV, upserts, drift alert).
- Config: usa `ml_settings` y overrides por tenant (`ml_settings.get_tenant_overrides`).
- Cliente DB: `get_supabase_service_client()` con helpers tipados (`TableQueryProto`) para evitar Unknowns del type checker.

### `ml_engine.py`
- Implementa algoritmos:
  - Prophet: `train_sales_forecasting_prophet` y `forecast_sales_prophet`.
  - SARIMAX: `train_sarimax`, `forecast_sales_sarimax`, `insample_forecast_sarimax`.
  - Baselines: `forecast_baseline_naive`, `forecast_baseline_snaive` (incluyen intervalos simples por desvío estándar reciente/estacional).
  - XGBoost opcional: `train_xgboost`, `forecast_sales_xgboost` (si no está instalado, se lanza `ImportError` y se omite en tests).
- Anomalías:
  - `detect_anomalies_stl` (sobre `y` crudo) y `detect_anomalies_stl_residuals` (residuales vs. in-sample de un modelo).
- Utiliza wrappers "tipo-safe" para pandas/numpy y logging estructurado.

### `feature_engineer.py`
- Extracción y agregación de ventas por día:
  - `get_sales_rows(business_id, timerange)` y `sales_timeseries_daily(business_id, days)`.
  - Normaliza `fecha` a `ds` (date), convierte `total` a float y rellena días faltantes con 0.
- Persistencia de features:
  - `persist_sales_features` upserta en `ml_features` (metrics diarios `daily_total`, `ma7`, `ma28`) con `on_conflict="tenant_id,feature_date,feature_type"`.
  - `inventory_snapshot` y `persist_inventory_features` guardan métricas simples de inventario (opcional para dashboards o modelos globales futuros).
- Caching:
  - `get_sales_timeseries_cached` (decorador `@cached`), clave `ml_features:features_{tenant}_...`.
- Conexión: `get_supabase_service_client()` y protocolos `TableQueryProto`, `APIResponseProto`.

### `model_version_manager.py`
- Serialización `joblib` a bytes + `base64` para almacenar en Supabase (`BYTEA`/JSON string en `model_data`).
- `save_model(...) -> SavedModel`: upsert en `ml_models` por `(tenant_id, model_type, model_version)`, guarda `hyperparameters`, `training_metrics`, `accuracy`, `last_trained`.
- `load_active_model(tenant_id, model_type)`: recupera el último activo (ordenado por `last_trained` desc) y deserializa (maneja cadenas base64 o bytes).
- Devuelve `SavedModel` como dataclass con metadatos clave.

### `__init__.py`
- Exposición conveniente de símbolos: típicamente `FeatureEngineer`, `ModelVersionManager`, `BusinessMLEngine`, `train_and_predict_sales`.

---

## `app/workers/`

### `ml_worker.py`
- Decoradores `@task_typed(...)` para preservar tipado y evitar warnings del type checker.
- Tareas principales:
  - `retrain_all_models`: recorre tenants (filtrados por `ML_TENANT_IDS` si aplica), ejecuta pipeline y registra métricas CV.
  - `update_business_features`: refresca features de ventas e inventario, e invalida el caché por patrón `ml_features:features_{tenant}`.
  - `generate_predictions`: reutiliza un modelo activo si existe; si no, ejecuta pipeline una vez. Genera pronósticos o anomalías según `prediction_type`.
  - `analyze_business_trends`: ejemplo de análisis general (simulado) para dashboards.
- Upserts a `ml_predictions` y logs estructurados por cada paso.

### `notification_worker.py`
- Refactorizado para usar `get_supabase_service_client()` centralizado.
- Tareas:
  - `send_daily_notifications`: itera negocios y envía/resume notificaciones diarias (placeholder para reglas diarias).
  - `check_notification_rules`: evalúa reglas activas en `business_notification_config`.
  - `send_notification`: inserta una notificación en `notifications` e invalida caché `notifications` (decorador `@invalidate_on_update`).

### `maintenance_worker.py`
- Tareas de limpieza y health-check:
  - `cleanup_old_notifications` (≥30 días) y `cleanup_old_ml_predictions` (≥90 días).
  - `health_check` contra Supabase.
- Nota: actualmente usa `create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)` directamente (pendiente de unificar con `get_supabase_service_client()` si se desea consistencia).

---

## `app/celery_app.py`
- Inicializa `Celery` con broker/backend desde `settings`.
- `include=["app.workers.notification_worker", "app.workers.ml_worker", "app.workers.maintenance_worker"]`.
- `task_routes` separa en colas `notifications` y `ml_processing`.
- `beat_schedule`:
  - `daily-notifications`: 08:00.
  - `weekly-ml-retrain`: lunes 02:00.
  - `check-notification-rules`: cada 300s.
  - `update-ml-features`: cada 3600s.
  - `cleanup-old-notifications`: 00:00.

---

## `app/config/ml_settings.py`
- Configuración central de ML (`pydantic-settings`). Principales claves:
  - Candidatos y selección: `ML_MODEL_CANDIDATES`, `ML_SELECT_BEST`, `ML_CV_PRIMARY_METRIC`.
  - CV y horizonte: `ML_HORIZON_DAYS`, `ML_CV_FOLDS`.
  - Parámetros de Prophet/SARIMAX y anomalías: `ML_SEASONALITY_MODE`, `ML_HOLIDAYS_COUNTRY`, `ML_LOG_TRANSFORM`, `ML_SARIMAX_ORDER`, `ML_SARIMAX_SEASONAL`, `ML_ANOMALY_METHOD`, `ML_STL_PERIOD`, `ML_STL_ZTHRESH`.
  - Ventanas y retrain: `ML_MAX_TRAIN_WINDOW_DAYS`, `ML_RETRAIN_CRON`.
  - Multi-tenant: `ML_TENANT_IDS` ("*"=todos). `allowed_tenants()` devuelve un set para filtrar.
  - Alertas: `ML_ERROR_ALERT_MAPE`.
- Overrides por tenant: `get_tenant_overrides(tenant_id)` leyendo `tenant_ml_settings.settings` (JSONB). Si no existe la tabla o fila, devuelve `{}`.
- `SettingsConfigDict(extra="ignore")` para evitar errores por envs no relacionadas.

---

## Tablas y claves `on_conflict`

- `ml_predictions`:
  - `on_conflict="tenant_id,prediction_date,prediction_type"`.
  - `predicted_values` (JSON): para `sales_forecast` incluye `yhat`, `yhat_lower`, `yhat_upper`; para `sales_anomaly` incluye `y`, `score`, `is_anomaly`.
  - `confidence_score` derivado de ancho de intervalo (o de `score` en anomalías).

- `ml_models`:
  - `on_conflict="tenant_id,model_type,model_version"`.
  - `model_data` como base64 (joblib-serialized), `hyperparameters` y `training_metrics` (JSON), `accuracy`, `last_trained`.

- `ml_features`:
  - `on_conflict="tenant_id,feature_date,feature_type"`.
  - Almacena métricas diarias e inventario.

- Otras tablas usadas por workers:
  - `notifications`, `business_notification_config`, `negocios`, `productos`, `ventas`.

---

## Extensión y buenas prácticas

- Añadir candidatos de modelo: implementar `train_*`/`forecast_*` en `ml_engine.py` y registrarlos en `pipeline`.
- Añadir features: extender `FeatureEngineer` y persistir con `ml_features` (definir `feature_type`).
- Mantener `on_conflict` correcto en upserts para idempotencia.
- Respetar `ml_settings` y `get_tenant_overrides` para personalización por tenant.
- Logging estructurado permite trazabilidad y monitoreo; mantener mensajes consistentes.
- Para pruebas locales, usar los `FakeSupabase` de los tests y monkeypatch a `get_supabase_service_client`.

---

## Relación con la suite de tests

- End-to-end y CV multi-horizonte: `tests/ml/test_ml_candidates_and_drift.py`, `tests/ml/test_cv_multi_horizon.py`.
- Robustez/stress: `tests/ml/test_stress_series.py` (gaps, outliers, short, seasonal_shift).
- Aislamiento e idempotencia: `tests/ml/test_isolation_idempotence.py`.
- Nota: los tests XGBoost hacen skip si el paquete no está instalado.
