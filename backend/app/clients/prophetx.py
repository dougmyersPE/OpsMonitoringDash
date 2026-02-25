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
        """Exchange access_key + secret_key for a Bearer token.

        Response shape: {"data": {"access_token": "...", "access_expire_time": <unix ts>, ...}}
        """
        resp = await self._post(
            "/auth/login",
            json={"access_key": self._access_key, "secret_key": self._secret_key},
        )
        payload = resp["data"]
        self._access_token = payload["access_token"]
        # Use server-provided expiry; subtract 60s buffer to avoid racing the edge
        self._token_expires_at = payload["access_expire_time"] - 60
        ttl = int(self._token_expires_at - time.time())
        log.info("prophetx_authenticated", ttl_seconds=ttl)

    async def _ensure_token(self) -> str:
        """Return a valid access token, re-authenticating if expired or missing."""
        if self._access_token is None or time.time() >= self._token_expires_at:
            await self._authenticate()
        return self._access_token  # type: ignore[return-value]

    async def get_tournaments_raw(self) -> dict | list:
        """
        Fetch raw ProphetX tournaments response and log verbatim.
        Phase 1: confirms API connectivity and response shape.
        """
        token = await self._ensure_token()
        raw = await self._get("/mm/get_tournaments", headers={"Authorization": f"Bearer {token}"})
        log.info(
            "prophetx_tournaments_raw",
            response_type=type(raw).__name__,
            response_keys=list(raw.keys()) if isinstance(raw, dict) else f"list of {len(raw)}",
        )
        log.debug("prophetx_tournaments_full_response", response=raw)
        return raw

    async def get_events_raw(self, tournament_id: str | None = None) -> dict | list:
        """
        Fetch raw ProphetX sport events response and log verbatim.
        Phase 1: confirms status enum values and response shape for Phase 2 parsing.
        """
        token = await self._ensure_token()
        params = {"tournament_id": tournament_id} if tournament_id else {}
        raw = await self._get(
            "/mm/get_sport_events",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        log.info(
            "prophetx_events_raw",
            response_type=type(raw).__name__,
            response_keys=list(raw.keys()) if isinstance(raw, dict) else f"list of {len(raw)}",
        )
        log.debug("prophetx_events_full_response", response=raw)
        return raw

    async def get_markets_raw(self, event_id: str | None = None) -> dict | list:
        """Fetch raw ProphetX markets response and log verbatim."""
        token = await self._ensure_token()
        params = {"event_id": event_id} if event_id else {}
        raw = await self._get(
            "/mm/get_markets",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        log.info("prophetx_markets_raw", response_type=type(raw).__name__)
        log.debug("prophetx_markets_full_response", response=raw)
        return raw
