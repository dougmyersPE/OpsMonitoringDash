import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture(scope="session")
async def client():
    """Async HTTP test client for the FastAPI app (session-scoped for connection pool stability)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def operator_token(client):
    """Create an operator user and return a valid JWT token for that user.

    Used to test 403 responses on Admin-only endpoints. The user is created
    directly via the sync DB session (not via login) to avoid seeding complexity.
    """
    from app.core.constants import RoleEnum
    from app.core.security import hash_password
    from app.db.sync_session import SyncSessionLocal
    from app.models.user import User

    # Create operator user directly in DB (sync, avoids async loop issues)
    with SyncSessionLocal() as session:
        # Clean up any existing operator test user first
        from sqlalchemy import select, delete
        existing = session.execute(
            select(User).where(User.email == "operator@test.com")
        ).scalar_one_or_none()
        if not existing:
            op_user = User(
                email="operator@test.com",
                password_hash=hash_password("testpass"),
                role=RoleEnum.operator,
                name="Test Operator",
            )
            session.add(op_user)
            session.commit()

    # Login to get a token
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "operator@test.com", "password": "testpass"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200, f"Operator login failed: {resp.text}"
    yield resp.json()["access_token"]
