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
