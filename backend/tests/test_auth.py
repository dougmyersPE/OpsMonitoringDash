"""
Auth and RBAC integration tests.
Requires running postgres + redis (docker compose up postgres redis backend).

Note on Operator/Read-Only role testing:
The seed.py only creates an admin user. Operator and Read-Only role testing
uses the operator_token fixture from conftest.py which creates an operator
user directly via the DB session. Full 403 path is tested via test_operator_token_on_admin_endpoint_returns_403.
"""
import pytest


# Helper to get a token for a specific user
async def get_token(client, email: str, password: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


class TestLogin:
    async def test_valid_credentials_return_token(self, client):
        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "admin@example.com", "password": "changeme"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_invalid_password_returns_401(self, client):
        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "admin@example.com", "password": "wrongpassword"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 401

    async def test_unknown_email_returns_401(self, client):
        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "nobody@example.com", "password": "whatever"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 401


class TestRBAC:
    async def test_config_without_token_returns_401(self, client):
        resp = await client.get("/api/v1/config")
        assert resp.status_code == 401

    async def test_config_with_admin_token_returns_200(self, client):
        token = await get_token(client, "admin@example.com", "changeme")
        resp = await client.get(
            "/api/v1/config",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    async def test_config_patch_upserts_key(self, client):
        token = await get_token(client, "admin@example.com", "changeme")
        resp = await client.patch(
            "/api/v1/config/polling_interval_seconds",
            json={"value": "30", "description": "Polling interval in seconds"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["key"] == "polling_interval_seconds"
        assert resp.json()["value"] == "30"

    async def test_operator_token_on_admin_endpoint_returns_403(self, client, operator_token):
        resp = await client.get(
            "/api/v1/config",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 403
