import time
import structlog
from app.clients.base import BaseAPIClient
from app.core.config import settings

log = structlog.get_logger()


class ProphetXClient(BaseAPIClient):
    """
    ProphetX API client using two-credential OAuth2 token exchange.

    Authentication flow:
      1. POST /auth/login with access_key + secret_key
      2. Receive access_token (20 min TTL) + refresh_token (3 days)
      3. All subsequent requests: Authorization: Bearer {access_token}
      4. Auto-re-authenticate 60s before expiry
    """

    def __init__(
        self,
        access_key: str | None = None,
        secret_key: str | None = None,
        base_url: str | None = None,
    ):
        url = base_url or settings.PROPHETX_BASE_URL
        super().__init__(base_url=url)
        self._access_key = access_key or settings.PROPHETX_ACCESS_KEY
        self._secret_key = secret_key or settings.PROPHETX_SECRET_KEY
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0  # unix timestamp

    async def _authenticate(self) -> None:
        """Exchange access_key + secret_key for a Bearer token (20 min TTL)."""
        data = await self._post(
            "/auth/login",
            json={"access_key": self._access_key, "secret_key": self._secret_key},
        )
        self._access_token = data["access_token"]
        # Expire 60s early to avoid using a nearly-expired token
        self._token_expires_at = time.time() + (20 * 60) - 60
        log.info("prophetx_authenticated", ttl_seconds=19 * 60)

    async def _ensure_token(self) -> str:
        """Return a valid access token, re-authenticating if expired or missing."""
        if self._access_token is None or time.time() >= self._token_expires_at:
            await self._authenticate()
        return self._access_token  # type: ignore[return-value]

    async def get_events_raw(self) -> dict | list:
        """
        Fetch raw ProphetX events response and log verbatim.
        Phase 1: confirms status enum values and response shape for Phase 2 parsing.
        """
        token = await self._ensure_token()
        raw = await self._get("/events", headers={"Authorization": f"Bearer {token}"})
        log.info(
            "prophetx_events_raw",
            response_type=type(raw).__name__,
            response_keys=list(raw.keys()) if isinstance(raw, dict) else f"list of {len(raw)}",
        )
        log.debug("prophetx_events_full_response", response=raw)
        return raw

    async def get_markets_raw(self) -> dict | list:
        """Fetch raw ProphetX markets response and log verbatim."""
        token = await self._ensure_token()
        raw = await self._get("/markets", headers={"Authorization": f"Bearer {token}"})
        log.info("prophetx_markets_raw", response_type=type(raw).__name__)
        log.debug("prophetx_markets_full_response", response=raw)
        return raw
