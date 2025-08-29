from __future__ import annotations

from typing import Any, cast


def as_float(v: Any, default: float) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except Exception:
            return default
    return default


def listv(features: dict[str, Any], name: str) -> list[Any]:
    v = features.get(name)
    return cast(list[Any], v) if isinstance(v, list) else []


def sev_rank(s: str) -> int:
    return {"info": 0, "success": 1, "warning": 2, "error": 3}.get(s, 1)
