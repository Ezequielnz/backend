from __future__ import annotations

import pytest
import pandas as pd
from unittest.mock import Mock, patch
from app.services.ml.ml_engine import BusinessMLEngine
from app.services.ml.recommendation_engine import RecommendationEngine, check_stock_recommendations, check_sales_review_recommendations


class TestHolidaysAndSpecialDates:
    def test_make_time_features_includes_holidays_and_special_dates(self):
        """Test that _make_time_features includes is_holiday and is_special_date columns."""
        engine = BusinessMLEngine()

        # Create test dates including a known holiday (e.g., 2024-01-01 is New Year)
        dates = pd.Series([
            pd.Timestamp("2024-01-01"),  # Holiday
            pd.Timestamp("2024-02-14"),  # Valentine's Day (special)
            pd.Timestamp("2024-05-01"),  # Labor Day (holiday)
            pd.Timestamp("2024-07-15"),  # Regular day
        ])

        features = engine._make_time_features(dates, "test_tenant")

        # Check columns exist
        assert "dow" in features.columns
        assert "dom" in features.columns
        assert "month" in features.columns
        assert "is_holiday" in features.columns
        assert "is_special_date" in features.columns

        # Check types
        assert features["is_holiday"].dtype == int
        assert features["is_special_date"].dtype == int

        # Check some values (New Year should be holiday)
        assert features.loc[0, "is_holiday"] == 1  # 2024-01-01
        assert features.loc[1, "is_special_date"] == 1  # 2024-02-14 Valentine's

    def test_get_holidays_for_tenant(self):
        """Test holiday fetching for tenant."""
        engine = BusinessMLEngine()

        holidays = engine._get_holidays_for_tenant("test_tenant", [2024])

        # Should include Argentine holidays
        assert len(holidays) > 0
        # Check if New Year is included
        from datetime import date
        assert date(2024, 1, 1) in holidays

    def test_get_special_dates(self):
        """Test special dates detection."""
        engine = BusinessMLEngine()

        dates = pd.Series([
            pd.Timestamp("2024-02-14"),  # Valentine's
            pd.Timestamp("2024-11-29"),  # Black Friday (assuming Friday)
            pd.Timestamp("2024-12-31"),  # New Year's Eve
            pd.Timestamp("2024-07-15"),  # Regular
        ])

        special = engine._get_special_dates(dates)

        assert special.iloc[0] == 1  # Valentine's
        assert special.iloc[2] == 1  # New Year's Eve


class TestRecommendationEngine:
    @patch('app.services.ml.recommendation_engine.get_supabase_service_client')
    def test_check_stock_recommendations(self, mock_client):
        """Test stock recommendations logic."""
        # Mock client and responses
        mock_table = Mock()
        mock_client.return_value.table.return_value = mock_table

        # Mock forecasts response
        mock_table.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = Mock(
            data=[
                {"predicted_values": {"yhat": 100.0}},
                {"predicted_values": {"yhat": 150.0}},
            ]
        )

        # Mock products response
        mock_table.select.return_value.eq.return_value.gte.return_value.execute.return_value = Mock(
            data=[
                {"id": "prod1", "nombre": "Product 1", "stock_actual": 200.0},
                {"id": "prod2", "nombre": "Product 2", "stock_actual": 50.0},  # Low stock
            ]
        )

        engine = RecommendationEngine()

        with patch.object(engine, '_send_notification') as mock_send:
            result = engine.check_stock_recommendations("test_tenant")

            # Should send 1 recommendation for prod2
            assert result == 1
            mock_send.assert_called_once()
            call_args = mock_send.call_args[0]
            assert call_args[0] == "test_tenant"
            assert "stock_recommendation" in call_args[1]

    @patch('app.services.ml.recommendation_engine.get_supabase_service_client')
    def test_check_sales_review_recommendations(self, mock_client):
        """Test sales review recommendations."""
        mock_table = Mock()
        mock_client.return_value.table.return_value = mock_table

        # Mock anomalies response with 5 anomalies
        anomalies = [{"prediction_date": f"2024-01-{i:02d}"} for i in range(1, 6)]
        mock_table.select.return_value.eq.return_value.gte.return_value.execute.return_value = Mock(
            data=anomalies
        )

        engine = RecommendationEngine()

        with patch.object(engine, '_send_notification') as mock_send:
            result = engine.check_sales_review_recommendations("test_tenant")

            # Should send 1 recommendation
            assert result == 1
            mock_send.assert_called_once()

    def test_convenience_functions(self):
        """Test convenience functions call the engine methods."""
        with patch('app.services.ml.recommendation_engine.RecommendationEngine') as mock_engine_class:
            mock_engine = Mock()
            mock_engine_class.return_value = mock_engine
            mock_engine.check_stock_recommendations.return_value = 2
            mock_engine.check_sales_review_recommendations.return_value = 1

            assert check_stock_recommendations("tenant1") == 2
            assert check_sales_review_recommendations("tenant1") == 1

            mock_engine.check_stock_recommendations.assert_called_with("tenant1", 0.1)
            mock_engine.check_sales_review_recommendations.assert_called_with("tenant1", 0.2)


class TestPipelineIntegration:
    """Test that pipeline integrates new features correctly."""

    @patch('app.services.ml.pipeline.get_supabase_service_client')
    @patch('app.services.ml.pipeline.FeatureEngineer')
    @patch('app.services.ml.pipeline.BusinessMLEngine')
    @patch('app.services.ml.pipeline.ModelVersionManager')
    @patch('app.services.ml.pipeline.check_stock_recommendations')
    @patch('app.services.ml.pipeline.check_sales_review_recommendations')
    def test_pipeline_calls_recommendations(self, mock_sales_rec, mock_stock_rec, mock_mvm, mock_engine, mock_fe, mock_client):
        """Test that pipeline calls recommendation functions."""
        from app.services.ml.pipeline import train_and_predict_sales

        # Setup mocks
        mock_fe_instance = Mock()
        mock_fe.return_value = mock_fe_instance
        mock_fe_instance.sales_timeseries_daily.return_value = pd.DataFrame({
            "ds": pd.date_range("2024-01-01", periods=100, freq="D"),
            "y": [100 + i for i in range(100)]
        })

        mock_engine_instance = Mock()
        mock_engine.return_value = mock_engine_instance
        mock_engine_instance.train_sales_forecasting_prophet.return_value = Mock()
        mock_engine_instance.forecast_sales_prophet.return_value = pd.DataFrame({
            "ds": pd.date_range("2024-04-11", periods=14, freq="D"),
            "yhat": [200] * 14,
            "yhat_lower": [180] * 14,
            "yhat_upper": [220] * 14
        })

        mock_mvm_instance = Mock()
        mock_mvm.return_value = mock_mvm_instance
        mock_mvm_instance.save_model.return_value = Mock(id="test_model_id")

        mock_stock_rec.return_value = 1
        mock_sales_rec.return_value = 0

        # Mock client for upsert
        mock_table = Mock()
        mock_client.return_value.table.return_value = mock_table
        mock_table.upsert.return_value.execute.return_value = None

        result = train_and_predict_sales("test_tenant", horizon_days=14, history_days=100)

        # Check recommendations were called
        mock_stock_rec.assert_called_once_with("test_tenant")
        mock_sales_rec.assert_called_once_with("test_tenant")

        # Check result includes recommendations
        assert "recommendations" in result
        assert result["recommendations"]["stock_recommendations"] == 1
        assert result["recommendations"]["sales_recommendations"] == 0