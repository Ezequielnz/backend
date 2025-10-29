import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


# Ensure backend root is on sys.path so `import app...` works when running tests directly
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture
def mock_supabase():
    """
    Provide a mocked Supabase client for tests that don't define their own fixture.
    Mirrors the behaviour expected by action system tests while avoiding real I/O.
    """
    from app.services.safe_action_engine import safe_action_engine

    with patch("app.services.safe_action_engine.get_supabase_client") as mock_factory:
        mock_client = Mock()

        # Default table mock that supports select/eq/insert chains returning deterministic data
        table_mock = Mock()
        table_mock.select.return_value = table_mock
        table_mock.eq.return_value = table_mock
        table_mock.insert.return_value = table_mock
        table_mock.update.return_value = table_mock
        table_mock.execute.return_value = Mock(data=[])
        mock_client.table.return_value = table_mock

        mock_factory.return_value = mock_client
        previous_client = getattr(safe_action_engine, "_supabase_client", None)
        safe_action_engine.supabase = mock_client
        try:
            yield mock_client
        finally:
            safe_action_engine.supabase = previous_client


@pytest.fixture
def mock_cache():
    """
    Provide a mocked cache manager to isolate tests from shared state.
    """
    with patch("app.services.safe_action_engine.cache_manager") as mock_cache_manager:
        mock_cache_manager.get.return_value = None
        mock_cache_manager.set.return_value = None
        yield mock_cache_manager
