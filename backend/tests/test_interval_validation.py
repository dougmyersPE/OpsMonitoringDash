"""
Tests for poll interval validation in PATCH /api/v1/config/{key}.

Covers FREQ-02 (server-enforced minimum intervals) and FREQ-03 (valid updates persist).
RedBeat propagation is mocked to avoid needing a live Redis/Celery connection.

NOTE: Integration test — requires running PostgreSQL and Redis (for FastAPI app startup).
Before running: docker compose up -d postgres redis backend
"""
import pytest
from unittest.mock import patch


@pytest.fixture
async def admin_token(client):
    """Login as the seeded admin user and return a valid JWT token."""
    from app.core.config import settings

    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": settings.ADMIN_EMAIL, "password": settings.ADMIN_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["access_token"]


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_patch_interval_below_minimum(client, admin_token):
    """PATCH poll_interval_espn with value below minimum (60) returns 422."""
    resp = await client.patch(
        "/api/v1/config/poll_interval_espn",
        json={"value": "30"},
        headers=_auth_header(admin_token),
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "60" in detail, f"Expected minimum '60' in error detail: {detail}"


@pytest.mark.asyncio
async def test_patch_interval_non_integer(client, admin_token):
    """PATCH poll_interval_espn with non-integer value returns 422."""
    resp = await client.patch(
        "/api/v1/config/poll_interval_espn",
        json={"value": "abc"},
        headers=_auth_header(admin_token),
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "positive integer" in detail.lower(), f"Expected 'positive integer' in error: {detail}"


@pytest.mark.asyncio
async def test_patch_interval_negative(client, admin_token):
    """PATCH poll_interval_espn with negative value returns 422."""
    resp = await client.patch(
        "/api/v1/config/poll_interval_espn",
        json={"value": "-5"},
        headers=_auth_header(admin_token),
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "positive integer" in detail.lower(), f"Expected 'positive integer' in error: {detail}"


@pytest.mark.asyncio
async def test_patch_interval_valid(client, admin_token):
    """PATCH poll_interval_espn with valid value (120 >= min 60) returns 200."""
    with patch("app.workers.beat_bootstrap.update_redbeat_entry"):
        resp = await client.patch(
            "/api/v1/config/poll_interval_espn",
            json={"value": "120"},
            headers=_auth_header(admin_token),
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["value"] == "120"

    # Restore the original default to avoid polluting other tests
    with patch("app.workers.beat_bootstrap.update_redbeat_entry"):
        await client.patch(
            "/api/v1/config/poll_interval_espn",
            json={"value": "600"},
            headers=_auth_header(admin_token),
        )


@pytest.mark.asyncio
async def test_patch_non_interval_key(client, admin_token):
    """PATCH a non-interval key passes through without interval validation."""
    resp = await client.patch(
        "/api/v1/config/alert_only_mode",
        json={"value": "true"},
        headers=_auth_header(admin_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["value"] == "true"


@pytest.mark.asyncio
async def test_patch_interval_odds_api_below_min(client, admin_token):
    """PATCH poll_interval_odds_api with value below minimum (600) returns 422."""
    resp = await client.patch(
        "/api/v1/config/poll_interval_odds_api",
        json={"value": "500"},
        headers=_auth_header(admin_token),
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "600" in detail, f"Expected minimum '600' in error detail: {detail}"
