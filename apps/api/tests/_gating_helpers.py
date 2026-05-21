"""Helpers for Stage 3 gating tests — keeps each test file focused."""
from __future__ import annotations

from typing import Any, Optional

import pytest


def mock_request(
    *,
    body: Optional[dict[str, Any]] = None,
    path_params: Optional[dict[str, str]] = None,
    path: str = "/test",
    method: str = "POST",
):
    """Construct a minimal Request-like object for direct calls to the gating dep.

    Just sufficient surface area for `_safe_body`, path_params lookup, and
    structured logging. No real FastAPI Request needed."""
    class _State:
        pass

    class _URL:
        def __init__(self, p: str) -> None:
            self.path = p

    class _MockRequest:
        def __init__(self) -> None:
            self.method = method
            self.state = _State()
            self.path_params = path_params or {}
            self.url = _URL(path)
            self.headers: dict[str, str] = {}
            self._body = body or {}

        async def json(self) -> dict[str, Any]:
            return self._body

    return _MockRequest()


@pytest.fixture
def enable_gating(monkeypatch):
    """Flip GATING_ENABLED=true for the test. Patches the cached Settings
    instance directly so subsequent get_settings() calls see it."""
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "gating_enabled", True)
    yield


@pytest.fixture
def disable_gating(monkeypatch):
    """Force GATING_ENABLED=false for the test (shadow mode)."""
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "gating_enabled", False)
    yield
