"""
Smoke test: GET /health returns 200 with postgres and redis connected.

NOTE: This is an integration test — it requires running PostgreSQL and Redis instances.
Before running: docker compose up -d postgres redis backend
"""
import pytest


@pytest.mark.asyncio
async def test_health_returns_200(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["postgres"] == "connected"
    assert data["redis"] == "connected"


@pytest.mark.asyncio
async def test_worker_health_returns_200(client):
    """Regression test for STAB-02: /health/workers must return 200, not 404.

    The endpoint reads Redis heartbeat keys. In the test environment keys may
    not exist (no running workers), so values will be False -- but the response
    shape and status code must be correct.
    """
    response = await client.get("/api/v1/health/workers")
    assert response.status_code == 200
    data = response.json()
    # All 5 workers must be present in the response
    expected_workers = [
        "poll_prophetx",
        "poll_sports_data",
        "poll_odds_api",
        "poll_sports_api",
        "poll_espn",
    ]
    for worker in expected_workers:
        assert worker in data, f"Missing worker key: {worker}"
        assert isinstance(data[worker], bool), f"Worker {worker} value should be bool"
