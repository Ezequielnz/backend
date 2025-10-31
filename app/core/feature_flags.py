from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict

BRANCH_INVENTORY_MODES = "branch_inventory_modes"


def _bool_env(var_name: str, default: bool) -> bool:
    raw = os.getenv(var_name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_feature_flags() -> Dict[str, bool]:
    """
    Returns the evaluated feature flag map. Cached for the process lifetime.
    """
    return {
        BRANCH_INVENTORY_MODES: _bool_env("FEATURE_FLAG_BRANCH_INVENTORY_MODES", True),
    }


def is_feature_enabled(flag_name: str) -> bool:
    return get_feature_flags().get(flag_name, False)
