import structlog

from app.clients.base import BaseAPIClient
from app.core.config import settings

log = structlog.get_logger()

BASE_URL = "https://api.oddsblaze.com/v2"

# ProphetX sport name (lowercase) -> OddsBlaze league IDs
LEAGUE_MAP: dict[str, list[str]] = {
    "basketball": ["nba", "wnba"],
    "baseball": ["mlb"],
    "american football": ["nfl", "ncaaf"],
    "mma": ["ufc"],
    "soccer": ["usa-mls", "england-premier-league", "france-ligue-1", "spain-laliga"],
}


class OddsBlazeClient(BaseAPIClient):
    def __init__(self, api_key: str | None = None):
        super().__init__(base_url=BASE_URL)
        self._api_key = api_key or settings.ODDSBLAZE_API_KEY

    async def get_schedule(self, league_id: str) -> list[dict]:
        """Fetch schedule for a league. Returns list of event dicts."""
        raw = await self._get(
            f"/schedule/{league_id}.json",
            params={"key": self._api_key},
        )
        events = raw.get("events", []) if isinstance(raw, dict) else []
        log.info("oddsblaze_schedule_fetched", league=league_id, count=len(events))
        return events
