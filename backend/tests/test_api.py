"""Tests for API endpoints — health, queue-stats."""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.api


class TestHealthEndpoint:
    """GET /health — no DB required."""

    async def test_health_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_health_structure(self, client):
        resp = await client.get("/health")
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "pipeline"

    async def test_health_extra_fields_not_present(self, client):
        """Only the expected keys should be in the response."""
        resp = await client.get("/health")
        data = resp.json()
        assert set(data.keys()) == {"status", "service"}


class TestQueueStatsEndpoint:
    """GET /jobs/queue-stats — requires DB mock.

    The real endpoint uses `async with get_conn() as conn:` which blows
    up if the pool isn't initialised.  We mock ``get_conn`` via the
    ``mock_get_conn`` fixture.
    """

    async def test_queue_stats_structure(self, client, mock_get_conn):
        # Arrange: mock the three fetchval calls used by queue-stats
        conn = mock_get_conn.return_value.__aenter__.return_value
        values = iter([3, 5, 90.0])

        async def fetchval_side(*a, **kw):
            return next(values)

        conn.fetchval.side_effect = fetchval_side

        resp = await client.get("/jobs/queue-stats")
        assert resp.status_code == 200

        data = resp.json()
        assert data["active_count"] == 3
        assert data["queued_count"] == 5
        # estimated_wait_s = 5 * (90 + 30) = 600
        assert data["estimated_wait_s"] == 600

    async def test_queue_stats_zero_values(self, client, mock_get_conn):
        conn = mock_get_conn.return_value.__aenter__.return_value
        values = iter([0, 0, 0])

        async def fetchval_side(*a, **kw):
            return next(values)

        conn.fetchval.side_effect = fetchval_side

        resp = await client.get("/jobs/queue-stats")
        assert resp.status_code == 200

        data = resp.json()
        assert data["active_count"] == 0
        assert data["queued_count"] == 0
        assert data["estimated_wait_s"] == 0

    async def test_queue_stats_no_avg_dur_uses_default(self, client, mock_get_conn):
        conn = mock_get_conn.return_value.__aenter__.return_value
        values = iter([1, 2, None])

        async def fetchval_side(*a, **kw):
            return next(values)

        conn.fetchval.side_effect = fetchval_side

        resp = await client.get("/jobs/queue-stats")
        assert resp.status_code == 200

        data = resp.json()
        assert data["active_count"] == 1
        assert data["queued_count"] == 2
        # avg_dur is None → None or 90 → 90, so 2 * (90 + 30) = 240
        assert data["estimated_wait_s"] == 240
