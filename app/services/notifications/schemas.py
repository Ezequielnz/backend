from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class AlertSource(str, Enum):
    STATIC_RULE = "static_rule"
    ML = "ml"
    COMBINED = "combined"


def map_severity(value: str | None, default: str = "info") -> str:
    v = (value or default).lower()
    if v in {"info", "warning", "error", "success"}:
        return v
    if v in {"low"}:
        return "info"
    if v in {"medium", "med", "moderate"}:
        return "warning"
    if v in {"high", "critical", "severe"}:
        return "error"
    return default


@dataclass
class NotificationAlert:
    # Use Any for rule_type to avoid tight coupling at import time
    rule_type: Any
    severity: str  # info | warning | error | success
    title: str
    message: str
    metadata: dict[str, Any]
    score: float
    source: AlertSource

    def to_db_row(self, tenant_id: str) -> dict[str, Any]:
        return {
            "tenant_id": tenant_id,
            "title": self.title,
            "message": self.message,
            "metadata": self.metadata,
            "severity": self.severity,
        }
