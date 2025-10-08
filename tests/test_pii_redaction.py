"""
Tests for PII redaction in LLM reasoning service.
Ensures prompts and responses are properly sanitized according to tenant policies.
"""
import pytest
from unittest.mock import patch, MagicMock
from app.services.llm_reasoning_service import LLMReasoningService
from app.services.ml.pii_utils import PIIHashingUtility


class TestPIIRedaction:
    """Test PII redaction functionality in LLM reasoning."""

    @pytest.fixture
    def llm_service(self):
        """LLM reasoning service instance."""
        return LLMReasoningService()

    @pytest.fixture
    def pii_utility(self):
        """PII hashing utility instance."""
        return PIIHashingUtility()

    def test_prompt_redaction_with_pii(self, llm_service, pii_utility):
        """Test that prompts containing PII are redacted."""
        # Create a prompt with various types of PII
        prompt_with_pii = """
        Customer john.doe@example.com called from phone 555-123-4567.
        Their DNI is 12345678 and they mentioned account CBU 1234567890123456789012.
        Please analyze this customer interaction.
        """

        # Apply PII sanitization
        sanitized_prompt = llm_service._apply_pii_sanitization(prompt_with_pii, "tenant_123")

        # Verify PII is redacted
        assert "john.doe@example.com" not in sanitized_prompt
        assert "555-123-4567" not in sanitized_prompt
        assert "12345678" not in sanitized_prompt
        assert "1234567890123456789012" not in sanitized_prompt

        # Verify placeholders are present
        assert "[EMAIL_MASKED]" in sanitized_prompt
        assert "[PHONE_MASKED]" in sanitized_prompt
        assert "[DOCUMENT_MASKED]" in sanitized_prompt
        # Bank account may be detected as document or bank_account
        assert ("[BANK_ACCOUNT_MASKED]" in sanitized_prompt or
                "[DOCUMENT_MASKED]" in sanitized_prompt)

    def test_prompt_redaction_without_pii(self, llm_service):
        """Test that prompts without PII remain unchanged."""
        clean_prompt = """
        Please analyze this sales data for the month of January.
        The total revenue was $10,000 with 500 transactions.
        """

        sanitized_prompt = llm_service._apply_pii_sanitization(clean_prompt, "tenant_123")

        # Should remain unchanged
        assert sanitized_prompt == clean_prompt

    def test_redact_before_send_policy_true(self, llm_service):
        """Test that PII is redacted when redact_before_send=True."""
        prompt_with_email = "Contact user@test.com for details."

        # Mock the policy to return True
        with patch.object(llm_service, '_get_tenant_redact_policy', return_value=True):
            sanitized = llm_service._apply_pii_sanitization(prompt_with_email, "tenant_123")
            assert "[EMAIL_MASKED]" in sanitized
            assert "user@test.com" not in sanitized

    def test_redact_before_send_policy_false(self, llm_service):
        """Test that PII is NOT redacted when redact_before_send=False."""
        prompt_with_email = "Contact user@test.com for details."

        # Mock the policy to return False
        with patch.object(llm_service, '_get_tenant_redact_policy', return_value=False):
            sanitized = llm_service._apply_pii_sanitization(prompt_with_email, "tenant_123")
            assert sanitized == prompt_with_email  # No change
            assert "user@test.com" in sanitized

    def test_reason_method_applies_pii_redaction(self, llm_service):
        """Test that the main reason method applies PII redaction."""
        prediction_data = {
            "prediction_type": "sales_anomaly",
            "anomaly_score": 0.85,
            "context": {
                "customer_email": "customer@example.com",
                "customer_phone": "555-123-4567",
                "message": "Normal business context"
            }
        }

        # Mock dependencies to focus on PII testing
        with patch.object(llm_service, '_should_call_llm', return_value=True), \
             patch.object(llm_service, '_build_prompt') as mock_build, \
             patch.object(llm_service, '_get_tenant_redact_policy', return_value=True):

            # Mock prompt building to return a prompt with PII
            mock_build.return_value = {
                "prompt": "Analyze customer@example.com data",
                "prediction_type": "test",
                "context_length": 10
            }

            result = llm_service.reason("tenant_123", "pred_123", prediction_data, 0.9)

            # Verify PII was detected and redaction applied
            assert result["pii_sanitization_applied"] is True
            assert result["status"] == "processed"

    def test_reason_method_no_pii_redaction_needed(self, llm_service):
        """Test that reason method works when no PII is present."""
        prediction_data = {
            "prediction_type": "sales_anomaly",
            "anomaly_score": 0.85,
            "context": {
                "message": "Normal business context without PII"
            }
        }

        with patch.object(llm_service, '_should_call_llm', return_value=True), \
             patch.object(llm_service, '_build_prompt') as mock_build, \
             patch.object(llm_service, '_get_tenant_redact_policy', return_value=True):

            mock_build.return_value = {
                "prompt": "Analyze normal business data",
                "prediction_type": "test",
                "context_length": 10
            }

            result = llm_service.reason("tenant_123", "pred_123", prediction_data, 0.9)

            # Verify no PII redaction was needed
            assert result["pii_sanitization_applied"] is False
            assert result["status"] == "processed"

    def test_multiple_pii_types_redaction(self, llm_service, pii_utility):
        """Test redaction of multiple PII types in one prompt."""
        complex_prompt = """
        Customer John Smith with email john.smith@company.com
        called from 555-123-4567. DNI: 87654321.
        Bank account: 1234-5678-9012-3456.
        Please review their transaction history.
        """

        sanitized = llm_service._apply_pii_sanitization(complex_prompt, "tenant_123")

        # Check that all PII types are redacted
        assert "john.smith@company.com" not in sanitized
        assert "555-123-4567" not in sanitized
        assert "87654321" not in sanitized
        assert "1234-5678-9012-3456" not in sanitized

        # Check that placeholders are present
        assert "[EMAIL_MASKED]" in sanitized
        assert "[PHONE_MASKED]" in sanitized
        assert "[DOCUMENT_MASKED]" in sanitized
        assert "[CREDIT_CARD_MASKED]" in sanitized

        # Check that non-PII content is preserved (some names may be detected as PII)
        assert "called from" in sanitized
        assert "Please review their transaction history" in sanitized

    def test_pii_detection_accuracy(self, pii_utility):
        """Test PII detection accuracy for various patterns."""
        test_cases = [
            ("Email: user@test.com", ["email"]),
            ("Phone: 555-123-4567", ["phone"]),
            ("DNI: 12345678", ["document"]),
            ("IP: 192.168.1.1", ["ip_address"]),
            ("Name: John Doe", ["name"]),
            ("No PII here", []),  # No PII
        ]

        for text, expected_types in test_cases:
            detected = pii_utility.detect_pii(text)
            detected_types = [field['type'] for field in detected]

            for expected_type in expected_types:
                assert expected_type in detected_types, f"Failed to detect {expected_type} in: {text}"

        # Test that bank account detection works (may be overridden by document detection)
        bank_text = "Account: 1234567890123456789012"
        detected_bank = pii_utility.detect_pii(bank_text)
        # Either bank_account or document detection is acceptable
        detected_types_bank = [field['type'] for field in detected_bank]
        assert any(t in ['bank_account', 'document'] for t in detected_types_bank), \
            f"Failed to detect account number in: {bank_text}"

    def test_sanitization_preserves_structure(self, llm_service):
        """Test that sanitization preserves prompt structure and readability."""
        original_prompt = """
        Based on customer john.doe@example.com's recent activity
        from phone number 555-123-4567, and their document 12345678,
        please analyze the following sales pattern...
        """

        sanitized = llm_service._apply_pii_sanitization(original_prompt, "tenant_123")

        # Structure should be preserved
        assert "Based on customer" in sanitized
        assert "recent activity" in sanitized
        assert "from phone number" in sanitized
        assert "please analyze the following sales pattern" in sanitized

        # PII should be replaced with placeholders
        assert "[EMAIL_MASKED]" in sanitized
        assert "[PHONE_MASKED]" in sanitized
        assert "[DOCUMENT_MASKED]" in sanitized

    @pytest.mark.parametrize("redact_policy,should_redact", [
        (True, True),
        (False, False),
    ])
    def test_tenant_redact_policy_integration(self, llm_service, redact_policy, should_redact):
        """Test integration with tenant redact policy."""
        prompt_with_pii = "Contact customer@test.com immediately."

        with patch.object(llm_service, '_get_tenant_redact_policy', return_value=redact_policy):
            sanitized = llm_service._apply_pii_sanitization(prompt_with_pii, "tenant_123")

            if should_redact:
                assert "[EMAIL_MASKED]" in sanitized
                assert "customer@test.com" not in sanitized
            else:
                assert sanitized == prompt_with_pii
                assert "customer@test.com" in sanitized


if __name__ == "__main__":
    pytest.main([__file__])