"""
PII Protection and Governance Utilities for Vector Enrichment
Phase 2: Vector Enrichment
"""

import hashlib
import re
import logging
from typing import Dict, List, Tuple, Any, Pattern, Optional
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PIIFieldType(Enum):
    """Types of PII that can be detected and protected."""
    EMAIL = "email"
    PHONE = "phone"
    DOCUMENT = "document"  # DNI, passport, etc.
    NAME = "name"
    ADDRESS = "address"
    CREDIT_CARD = "credit_card"
    BANK_ACCOUNT = "bank_account"
    IP_ADDRESS = "ip_address"
    DATE_OF_BIRTH = "date_of_birth"
    LICENSE_NUMBER = "license_number"


class ComplianceStatus(Enum):
    """Compliance status for PII processing."""
    COMPLIANT = "compliant"
    REVIEW_REQUIRED = "review_required"
    FAILED = "failed"
    PENDING = "pending"


@dataclass
class PIIDetectionResult:
    """Result of PII detection in content."""
    original_content: str
    sanitized_content: str
    pii_fields_detected: List[Dict[str, Any]]
    compliance_status: ComplianceStatus
    sanitization_method: str
    metadata: Dict[str, Any]


@dataclass
class PIIHashResult:
    """Result of PII hashing operation."""
    original_hash: str
    pii_hash: str
    salt: str
    algorithm: str
    timestamp: datetime


class PIIHashingUtility:
    """
    Enhanced PII hashing utilities with multiple algorithms and compliance tracking.
    """

    def __init__(self):
        self.hash_algorithms = {
            'sha256': hashlib.sha256,
            'sha512': hashlib.sha512,
            'blake2b': hashlib.blake2b,
            'blake2s': hashlib.blake2s,
        }
        self.default_algorithm = 'sha256'
        self.salt_length = 32

        # PII detection patterns
        self.pii_patterns = self._compile_pii_patterns()

    def _compile_pii_patterns(self) -> Dict[PIIFieldType, List[Pattern[str]]]:
        """Compile regex patterns for PII detection."""
        patterns = {
            PIIFieldType.EMAIL: [
                re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
            ],
            PIIFieldType.PHONE: [
                re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'),  # US format
                re.compile(r'\b\d{2}[-.\s]?\d{4}[-.\s]?\d{4}\b'),  # Argentina format
                re.compile(r'\b\d{4}[-.\s]?\d{4}\b'),  # Short format
            ],
            PIIFieldType.DOCUMENT: [
                re.compile(r'\b\d{8}\b'),  # DNI Argentina
                re.compile(r'\b\d{2}\.\d{3}\.\d{3}\b'),  # DNI with dots
                re.compile(r'\b[A-Z]{2}\d{7}\b'),  # Passport-like
            ],
            PIIFieldType.CREDIT_CARD: [
                re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'),
                re.compile(r'\b\d{4}[-\s]?\d{6}[-\s]?\d{5}\b'),
            ],
            PIIFieldType.IP_ADDRESS: [
                re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'),
            ],
            PIIFieldType.DATE_OF_BIRTH: [
                re.compile(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b'),
                re.compile(r'\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b'),
            ],
            PIIFieldType.BANK_ACCOUNT: [
                re.compile(r'\b\d{3}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{2}\b'),  # CBU Argentina
                re.compile(r'\b\d{20}\b'),  # Account numbers
            ],
            PIIFieldType.LICENSE_NUMBER: [
                re.compile(r'\b\d{8,12}\b'),  # Various license formats
            ],
        }

        # Name detection (more complex, context-based)
        name_patterns = [
            re.compile(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b'),  # First Last format
            re.compile(r'\b[A-Z][a-z]+ [A-Z]\. [A-Z][a-z]+\b'),  # First M. Last format
        ]
        patterns[PIIFieldType.NAME] = name_patterns

        # Address detection (basic patterns)
        address_patterns = [
            re.compile(r'\b\d+\s+[A-Za-z0-9\s]+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Way|Place|Pl|Court|Ct|Circle|Cir)\b', re.IGNORECASE),
            re.compile(r'\b(?:Calle|Av| Avenida)\s+\d+\b', re.IGNORECASE),  # Spanish addresses
        ]
        patterns[PIIFieldType.ADDRESS] = address_patterns

        return patterns

    def generate_salt(self) -> str:
        """Generate a cryptographically secure salt."""
        import secrets
        return secrets.token_hex(self.salt_length)

    def hash_content(self, content: str, algorithm: Optional[str] = None, salt: Optional[str] = None) -> PIIHashResult:
        """
        Hash content with PII protection.

        Args:
            content: Content to hash
            algorithm: Hash algorithm to use
            salt: Salt for hashing (generated if not provided)

        Returns:
            PIIHashResult with hash details
        """
        if algorithm is None:
            algorithm = self.default_algorithm

        if salt is None:
            salt = self.generate_salt()

        if algorithm not in self.hash_algorithms:
            raise ValueError(f"Unsupported hash algorithm: {algorithm}")

        hash_func = self.hash_algorithms[algorithm]

        # Combine content with salt
        content_with_salt = f"{content}:{salt}".encode('utf-8')
        content_hash = hash_func(content_with_salt).hexdigest()

        return PIIHashResult(
            original_hash=hashlib.sha256(content.encode('utf-8')).hexdigest(),
            pii_hash=content_hash,
            salt=salt,
            algorithm=algorithm,
            timestamp=datetime.utcnow()
        )

    def detect_pii(self, content: str) -> List[Dict[str, Any]]:
        """
        Detect PII fields in content.

        Args:
            content: Text content to analyze

        Returns:
            List of detected PII fields with metadata
        """
        detected_fields = []

        for field_type, patterns in self.pii_patterns.items():
            for pattern in patterns:
                matches = pattern.finditer(content)
                for match in matches:
                    detected_fields.append({
                        'type': field_type.value,
                        'value': match.group(),
                        'start_pos': match.start(),
                        'end_pos': match.end(),
                        'confidence': self._calculate_confidence(field_type, match.group(), content)
                    })

        # Remove duplicates and overlapping matches
        filtered_fields = self._filter_overlapping_pii(detected_fields)

        return filtered_fields

    def _calculate_confidence(self, field_type: PIIFieldType, value: str, context: str) -> float:
        """Calculate confidence score for PII detection."""
        base_confidence = {
            PIIFieldType.EMAIL: 0.9,
            PIIFieldType.PHONE: 0.8,
            PIIFieldType.DOCUMENT: 0.7,
            PIIFieldType.CREDIT_CARD: 0.9,
            PIIFieldType.IP_ADDRESS: 0.8,
            PIIFieldType.DATE_OF_BIRTH: 0.6,
            PIIFieldType.BANK_ACCOUNT: 0.7,
            PIIFieldType.LICENSE_NUMBER: 0.6,
            PIIFieldType.NAME: 0.5,
            PIIFieldType.ADDRESS: 0.4,
        }

        confidence = base_confidence.get(field_type, 0.5)

        # Adjust based on context
        context_lower = context.lower()
        if field_type == PIIFieldType.EMAIL and 'email' in context_lower:
            confidence += 0.1
        elif field_type == PIIFieldType.PHONE and any(word in context_lower for word in ['phone', 'tel', 'mobile']):
            confidence += 0.1
        elif field_type == PIIFieldType.ADDRESS and any(word in context_lower for word in ['address', 'direccion', 'calle']):
            confidence += 0.1

        return min(confidence, 1.0)

    def _filter_overlapping_pii(self, detected_fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out overlapping PII detections."""
        if not detected_fields:
            return []

        # Sort by confidence (highest first)
        sorted_fields = sorted(detected_fields, key=lambda x: x['confidence'], reverse=True)

        filtered = []
        for field in sorted_fields:
            # Check if this field overlaps with any already selected field
            overlaps = False
            for selected in filtered:
                if (field['start_pos'] < selected['end_pos'] and
                    field['end_pos'] > selected['start_pos']):
                    overlaps = True
                    break

            if not overlaps:
                filtered.append(field)

        return filtered

    def sanitize_content(self, content: str, method: str = 'mask') -> Tuple[str, List[Dict[str, Any]]]:
        """
        Sanitize content by removing or masking PII.

        Args:
            content: Original content
            method: Sanitization method ('mask', 'remove', 'replace')

        Returns:
            Tuple of (sanitized_content, pii_fields)
        """
        pii_fields = self.detect_pii(content)
        sanitized = content

        for field in pii_fields:
            if method == 'mask':
                mask = '*' * len(field['value'])
                sanitized = sanitized.replace(field['value'], mask)
            elif method == 'remove':
                sanitized = sanitized.replace(field['value'], '')
            elif method == 'replace':
                if field['type'] == 'email':
                    sanitized = sanitized.replace(field['value'], '[EMAIL_MASKED]')
                elif field['type'] == 'phone':
                    sanitized = sanitized.replace(field['value'], '[PHONE_MASKED]')
                elif field['type'] == 'document':
                    sanitized = sanitized.replace(field['value'], '[DOCUMENT_MASKED]')
                else:
                    sanitized = sanitized.replace(field['value'], '[PII_MASKED]')

        return sanitized, pii_fields

    def validate_compliance(self, pii_fields: List[Dict[str, Any]], tenant_id: str) -> ComplianceStatus:
        """
        Validate compliance based on detected PII and tenant policies.

        Args:
            pii_fields: List of detected PII fields
            tenant_id: Tenant ID for policy lookup

        Returns:
            ComplianceStatus indicating compliance level
        """
        if not pii_fields:
            return ComplianceStatus.COMPLIANT

        # Define compliance rules (could be loaded from tenant settings)
        high_risk_pii = {
            PIIFieldType.CREDIT_CARD,
            PIIFieldType.BANK_ACCOUNT,
            PIIFieldType.DOCUMENT,
        }

        # Check for high-risk PII
        has_high_risk = any(field['type'] in [pii.value for pii in high_risk_pii]
                           for field in pii_fields)

        if has_high_risk:
            return ComplianceStatus.REVIEW_REQUIRED

        # Check confidence thresholds
        low_confidence_fields = [f for f in pii_fields if f['confidence'] < 0.6]
        if len(low_confidence_fields) > len(pii_fields) * 0.3:  # More than 30% low confidence
            return ComplianceStatus.REVIEW_REQUIRED

        return ComplianceStatus.COMPLIANT

    def process_content_for_embedding(
        self,
        content: str,
        content_type: str,
        content_id: str,
        tenant_id: str,
        sanitization_method: str = 'mask'
    ) -> PIIDetectionResult:
        """
        Complete PII processing pipeline for content before embedding.

        Args:
            content: Original content
            content_type: Type of content (e.g., 'product_description')
            content_id: ID of the content
            tenant_id: Tenant ID
            sanitization_method: How to handle PII

        Returns:
            PIIDetectionResult with processing details
        """
        # Detect PII
        pii_fields = self.detect_pii(content)

        # Sanitize content
        sanitized_content, sanitized_pii_fields = self.sanitize_content(content, sanitization_method)

        # Validate compliance
        compliance_status = self.validate_compliance(pii_fields, tenant_id)

        # Create hash of original content for tracking
        original_hash_result = self.hash_content(content)

        # Create metadata
        metadata = {
            'content_type': content_type,
            'content_id': content_id,
            'tenant_id': tenant_id,
            'processing_timestamp': datetime.utcnow().isoformat(),
            'pii_count': len(pii_fields),
            'sanitization_method': sanitization_method,
        }

        return PIIDetectionResult(
            original_content=content,
            sanitized_content=sanitized_content,
            pii_fields_detected=sanitized_pii_fields,
            compliance_status=compliance_status,
            sanitization_method=sanitization_method,
            metadata=metadata
        )


class PIIComplianceValidator:
    """
    Validates PII compliance for embedding pipelines.
    """

    def __init__(self, hashing_utility: PIIHashingUtility):
        self.hashing_utility = hashing_utility
        self.logger = logging.getLogger(__name__)

    def validate_embedding_content(
        self,
        content: str,
        tenant_id: str,
        content_type: str,
        require_compliance: bool = True
    ) -> Dict[str, Any]:
        """
        Validate content for embedding compliance.

        Args:
            content: Content to validate
            tenant_id: Tenant ID
            content_type: Type of content
            require_compliance: Whether to require full compliance

        Returns:
            Validation result with compliance status and recommendations
        """
        result = self.hashing_utility.process_content_for_embedding(
            content, content_type, f"{content_type}_validation", tenant_id
        )

        validation_result = {
            'is_valid': True,
            'compliance_status': result.compliance_status.value,
            'pii_detected': len(result.pii_fields_detected),
            'recommendations': [],
            'metadata': result.metadata
        }

        if result.compliance_status == ComplianceStatus.REVIEW_REQUIRED:
            validation_result['is_valid'] = not require_compliance
            validation_result['recommendations'].append(
                "Content contains high-risk PII that requires manual review"
            )

        elif result.compliance_status == ComplianceStatus.FAILED:
            validation_result['is_valid'] = False
            validation_result['recommendations'].append(
                "Content failed PII compliance validation"
            )

        if result.pii_fields_detected:
            pii_types = list(set(field['type'] for field in result.pii_fields_detected))
            validation_result['recommendations'].append(
                f"Detected PII types: {', '.join(pii_types)}"
            )

        self.logger.info(
            "PII validation completed",
            extra={
                'tenant_id': tenant_id,
                'content_type': content_type,
                'compliance_status': result.compliance_status.value,
                'pii_count': len(result.pii_fields_detected)
            }
        )

        return validation_result