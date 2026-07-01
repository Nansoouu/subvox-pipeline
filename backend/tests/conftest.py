"""Test fixtures for Subvox Pipeline backend."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


# ── Mock DB so the app can start without PostgreSQL ────
@pytest.fixture(autouse=True)
def _mock_db_pool():
    """Mock init_pool / close_pool so the FastAPI lifespan doesn't error."""
    with (
        patch("core.db.init_pool", AsyncMock()),
        patch("core.db.close_pool", AsyncMock()),
    ):
        yield


@pytest.fixture
def fastapi_app():
    """Import main app AFTER DB is mocked (avoids startup failures)."""
    from main import app
    return app


@pytest.fixture
async def client(fastapi_app):
    """Async HTTP client backed by FastAPI's ASGI transport."""
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_get_conn():
    """Mock get_conn() where it's imported (api.jobs.status).

    The route module does ``from core.db import get_conn`` at import time,
    so we must patch in *that* namespace.

    Returns a MagicMock whose .return_value.__aenter__.return_value is
    an AsyncMock whose ``.fetchval.side_effect`` is a list-of-values
    that the test must set **as a coroutine function** (since AsyncMock
    returns list values directly, not wrapped in awaitables).

    Usage:
        async def test_something(mock_get_conn):
            conn = mock_get_conn.return_value.__aenter__.return_value
            values = iter([3, 5, 90.0])

            async def fetchval_side(*a, **kw):
                return next(values)

            conn.fetchval.side_effect = fetchval_side
            resp = await client.get("/jobs/queue-stats")
            assert resp.status_code == 200
    """
    from unittest.mock import MagicMock

    patcher = patch("api.jobs.status.get_conn", new_callable=MagicMock)
    mock = patcher.start()
    # Make the return value an AsyncMock that acts as an async context manager
    mock.return_value.__aenter__.return_value = AsyncMock()
    yield mock
    patcher.stop()
