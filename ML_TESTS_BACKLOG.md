# Backlog priorizado de tests ML faltantes

Este documento define un checklist priorizado con detalles técnicos de implementación y criterios de aceptación para completar la cobertura de calidad del módulo de predicción de ventas.

Estado base: el sistema ya pasa integración E2E con persistencia (`ml_predictions`), selección de modelo con CV multi‑horizonte, robustez ante gaps/outliers/series cortas/shift estacional, idempotencia y aislamiento multi‑tenant, y logging/anomalías.

---

## Priorización
- P0: Alto impacto en confianza de negocio y riesgo de regresión.
- P1: Impacto alto/medio, mejora robustez y operación.
- P2: Completa calidad total, analítica avanzada y compliance.

---

## P0 — Críticos

1) Backtest con holdout temporal por tenant
- Tipo: Backtesting & evaluación (integración controlada)
- Objetivo: Estimar performance realista fuera de muestra por tenant y candidatear mejoras.
- Dataset/escenarios:
  - Sintéticos con tendencia + estacionalidad semanal/mensual; y uno estacionario con baja varianza.
  - Split temporal: entrenar hasta T−k, evaluar en [T−k+1, T]. Variar k (p. ej. 14 y 28 días).
- Procedimiento:
  - Reutilizar `FakeSupabase` y monkeypatch de `get_supabase_service_client` como en tests actuales.
  - `FeatureEngineer.sales_timeseries_daily` parcheado para devolver series sintéticas reproducibles.
  - Ejecutar `train_and_predict_sales` con `cv_folds=2`, `horizon_days` alineado al holdout.
  - Comparar forecasts vs. ground truth del holdout; computar MAE, RMSE, sMAPE y MASE vs naive.
- Criterios de aceptación:
  - MASE < 1.0 en al menos 60% de los tenants sintéticos (o datasets) y no peor que naive en el resto.
  - Reportar distribución de sMAPE/MAE por escenario (no flakey, tolerancias fijas).
- Archivos sugeridos: `tests/ml/test_backtest_holdout.py`.

2) Cobertura de intervalos (80% nominal)
- Tipo: Calibration & probabilistic
- Objetivo: Verificar que el 80% CI cubre ~80% de observaciones (±5%).
- Dataset/escenarios: Sintéticos suaves (ruido gaussiano estable) y con leve heteroscedasticidad.
- Procedimiento:
  - Generar forecasts para múltiples ventanas/fechas (rolling origin pequeño para acotar tiempo).
  - Medir coverage empírico: proporción y in/out por fecha.
- Criterios de aceptación:
  - Coverage entre 0.75 y 0.85 para 80% nominal en los escenarios suaves.
- Archivos sugeridos: `tests/ml/test_calibration_intervals.py`.

3) Patrón “ventas sólo inicio de mes” (calendar aware)
- Tipo: Seasonality & calendar-aware (integración con FE)
- Objetivo: Validar que el sistema no predice >0 fuera de días 1–3 y que la incertidumbre sea mayor fuera de ventana.
- Dataset/escenarios: Serie mensual con ventas >0 sólo días 1–3 de cada mes; resto 0.
- Procedimiento:
  - FE retorna patrón sintético; horizonte 14–28 días cruzando cambio de mes.
  - Chequear `yhat`≈0 fuera de 1–3 y `yhat`>0 sólo cerca de esos días; PIs más anchos fuera de 1–3.
- Criterios de aceptación:
  - Error bajo en días 1–3 y falsos positivos < umbral fuera de 1–3.
- Archivos sugeridos: `tests/ml/test_calendar_patterns.py`.

4) Detección y reacción a drift (súbito y gradual)
- Tipo: Concept drift / adaptabilidad
- Objetivo: Confirmar sensibilidad a cambios de nivel/tendencia y mecanismo de alerta.
- Dataset/escenarios: 
  - Drift súbito: +50% de nivel a partir de t0.
  - Drift gradual: cambio de pendiente en un periodo.
- Procedimiento:
  - Ejecutar CV/válidas recientes antes y después del changepoint.
  - Forzar escenario con MAPE que supere `ML_ERROR_ALERT_MAPE` y verificar que se dispare el flujo de alerta/notificación (mockear `send_notification`).
- Criterios de aceptación:
  - Se registra/retorna señal de drift (alerta) cuando la métrica supera umbral.
- Archivos sugeridos: `tests/ml/test_drift_adaptation.py`.

5) Anti‑leakage temporal
- Tipo: Security / Data leakage
- Objetivo: Asegurar que el entrenamiento y features no usan info futura.
- Dataset/escenarios: Serie donde un leakage produciría error casi 0 si existiese.
- Procedimiento:
  - Split claro train/test por fecha; inspección de features y verificación de que sólo se usan datos ≤ corte.
  - Validar que rendimiento no es “demasiado bueno para ser verdad” vs. control.
- Criterios de aceptación:
  - MASE razonable (>0.5 en escenario diseñado); no hay acceso a target futuro.
- Archivos sugeridos: `tests/ml/test_leakage.py`.

---

## P1 — Altos/Medios

6) Volatilidad súbita (ensanchamiento de PIs)
- Tipo: Robustez / stress
- Objetivo: Ver que PIs se ensanchan ante incremento repentino de varianza.
- Dataset/escenarios: Misma serie con sigma duplicada en tramo final.
- Procedimiento: Comparar ancho de PIs pre/post cambio; validar incremento.
- Criterios: `mean(width_post) ≥ mean(width_pre) * 1.5` (umbral ajustable).
- Archivos: `tests/ml/test_stress_volatility.py`.

7) Bloques masivos de faltantes
- Tipo: Robustez / stress
- Objetivo: Resiliencia ante largos períodos sin datos.
- Dataset: Bloques de NaN o días sin registros (p. ej., 2–4 semanas).
- Criterios: No crash; forecasts válidos; PIs reflejan mayor incertidumbre.
- Archivos: `tests/ml/test_stress_missing_blocks.py`.

8) Overrides por tenant (`tenant_ml_settings`)
- Tipo: Personalización / multi‑tenant
- Objetivo: Que cambios por tenant alteren comportamiento (p. ej. `ML_STL_PERIOD`, `ML_LOG_TRANSFORM`, candidatos).
- Procedimiento: Mockear tabla `tenant_ml_settings` en FakeSupabase y verificar efectos en pipeline.
- Criterios: Diferencias reproducibles en selección de modelo/anomalías/intervalos.
- Archivos: `tests/ml/test_tenant_overrides.py`.

9) Reglas de fallback de modelo
- Tipo: Model selection / hyper‑params
- Objetivo: Si el “mejor” falla, se usa baseline estable.
- Escenario: Forzar fallo de un candidato (mock) y verificar uso de naive/snaive.
- Criterios: No falla pipeline; se inserta forecast con baseline.
- Archivos: `tests/ml/test_model_fallbacks.py`.

10) Performance básica (latencia de inferencia)
- Tipo: Performance & latency
- Objetivo: Medir tiempos de forecast por tenant en condiciones controladas.
- Procedimiento: Cronometrar `train_and_predict_sales` con escenarios sintéticos pequeños; fijar seeds.
- Criterios: Latencia < umbral (definir p95), sin timeouts.
- Archivos: `tests/ml/test_performance_latency.py`.

---

## P2 — Completitud

11) Calibración avanzada (PIT) y sharpness vs reliability
- Tipo: Calibration
- Objetivo: Verificar distribución uniforme de PIT y trade‑off de PIs.
- Criterios: Estadísticos de uniformidad en rango aceptable (no flakey).
- Archivos: `tests/ml/test_prob_calibration.py`.

12) Explainability (importancias/SHAP)
- Tipo: Explainability & stability
- Objetivo: Importancias estables ante pequeñas perturbaciones (cuando se use XGBoost u otro).
- Criterios: Variación de ranking bajo umbrales; opcional y `skip` si lib no está.
- Archivos: `tests/ml/test_explainability.py`.

13) Fairness por cohortes (tamaño/sector)
- Tipo: Fairness / ética
- Objetivo: Que performance no favorezca sistemáticamente a un grupo.
- Criterios: Diferencias de MASE/sMAPE entre cohortes dentro de tolerancias.
- Archivos: `tests/ml/test_fairness_cohorts.py`.

14) Export/ingest downstream y CI gates
- Tipo: Integración CI/CD
- Objetivo: Validar contratos de export a dashboard/API y gates de métrica antes de promover modelo.
- Criterios: Contratos JSON estables; gating de MASE/coverage supera umbral.
- Archivos: `tests/ml/test_export_and_gates.py`.

---

## Guía técnica transversal

- Reutilizar mocks existentes: `FakeSupabase` y `monkeypatch` de `get_supabase_service_client` en `pipeline` y `model_version_manager`.
- Mantener pruebas deterministas: seeds fijos, horizontes cortos (7–14), `cv_folds=2`.
- Validar sólo filas `prediction_type='sales_forecast'` cuando se chequen intervalos y `yhat*`.
- Asegurar `on_conflict` correcto en upserts de tests para idempotencia.
- Evitar dependencia obligatoria de XGBoost: usar `importlib.util.find_spec` y `pytest.skip` si no está instalado.
- Medir cobertura de CIs sobre ventanas múltiples para evitar sobreajuste a una fecha.

---

## Plan de archivos sugerido
- `tests/ml/test_backtest_holdout.py`
- `tests/ml/test_calibration_intervals.py`
- `tests/ml/test_calendar_patterns.py`
- `tests/ml/test_drift_adaptation.py`
- `tests/ml/test_leakage.py`
- `tests/ml/test_stress_volatility.py`
- `tests/ml/test_stress_missing_blocks.py`
- `tests/ml/test_tenant_overrides.py`
- `tests/ml/test_model_fallbacks.py`
- `tests/ml/test_performance_latency.py`
- (Opcionales P2) `tests/ml/test_prob_calibration.py`, `tests/ml/test_explainability.py`, `tests/ml/test_fairness_cohorts.py`, `tests/ml/test_export_and_gates.py`

---

## Abiertos / decisiones futuras
- Trigger de reentrenamiento por drift (además del schedule semanal).
- Modelo global/híbrido para cold‑start (transfer learning) y tests asociados.
- Métricas y umbrales de negocio por sector/estacionalidad específica.
