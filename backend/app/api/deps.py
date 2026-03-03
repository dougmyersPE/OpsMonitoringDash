"""Auth dependencies — authentication removed; all endpoints are open."""


async def get_current_user() -> dict:
    """Return a default admin user (no authentication required)."""
    return {"sub": "anonymous", "role": "admin"}


def require_role(*roles):
    async def _checker():
        return {"sub": "anonymous", "role": "admin"}
    return _checker


async def verify_token_from_query() -> dict:
    """SSE endpoint — no token required."""
    return {"sub": "anonymous", "role": "admin"}
