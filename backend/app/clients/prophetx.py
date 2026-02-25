from app.clients.base import BaseAPIClient
from app.core.config import settings
import structlog

log = structlog.get_logger()

# NOTE: Confirm base URL with Doug before testing against live ProphetX API.
# This is a best-guess based on Medium articles referencing prophetx.co.
# Update PROPHETX_BASE_URL in settings if the real URL differs.
PROPHETX_BASE_URL = "https://api.prophetx.co"


class ProphetXClient(BaseAPIClient):
    def __init__(self, api_key: str | None = None):
        super().__init__(base_url=PROPHETX_BASE_URL)
        self._api_key = api_key or settings.PROPHETX_API_KEY
        self._headers = {"Authorization": f"Bearer {self._api_key}"}

    async def get_events_raw(self) -> dict | list:
        """
        Fetch raw ProphetX events response.
        Phase 1: Log verbatim to confirm status enum values (unconfirmed per STATE.md).
        Phase 2 will parse these into typed models.
        """
        raw = await self._get("/events", headers=self._headers)
        log.info(
            "prophetx_events_raw",
            response_type=type(raw).__name__,
            response_keys=list(raw.keys()) if isinstance(raw, dict) else f"list of {len(raw)}",
        )
        # Log full raw response at DEBUG level so enum values can be inspected
        log.debug("prophetx_events_full_response", response=raw)
        return raw

    async def get_markets_raw(self) -> dict | list:
        """
        Fetch raw ProphetX markets response.
        Endpoint path may need adjustment — confirm from ProphetX docs.
        """
        raw = await self._get("/markets", headers=self._headers)
        log.info(
            "prophetx_markets_raw",
            response_type=type(raw).__name__,
        )
        log.debug("prophetx_markets_full_response", response=raw)
        return raw
