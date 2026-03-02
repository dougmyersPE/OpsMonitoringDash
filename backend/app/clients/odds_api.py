from datetime import datetime, timezone

import httpx
import redis as _sync_redis
import structlog

from app.clients.base import BaseAPIClient
from app.core.config import settings

log = structlog.get_logger()

BASE_URL = "https://api.the-odds-api.com"

# ProphetX sport_name (lowercase) → Odds API sport_keys to query
SPORT_KEY_MAP: dict[str, list[str]] = {
    "basketball": ["basketball_nba", "basketball_ncaab"],
    "ice hockey": ["icehockey_nhl"],
    "mma": ["mma_mixed_martial_arts"],
    "baseball": ["baseball_mlb"],
    "american football": ["americanfootball_ncaaf"],
    "soccer": [
        "soccer_usa_mls",
        "soccer_epl",
        "soccer_uefa_champs_league",
        "soccer_uefa_europa_league",
    ],
    "tennis": ["tennis_atp_dubai"],
}


class OddsAPIClient(BaseAPIClient):
    def __init__(self, api_key: str | None = None):
        super().__init__(base_url=BASE_URL)
        self._api_key = api_key or settings.ODDS_API_KEY

    def _capture_quota_headers(self, response: httpx.Response) -> None:
        """Capture Odds API quota headers and store in Redis with 25h TTL.

        Headers: x-requests-remaining, x-requests-used (from the-odds-api.com docs).
        """
        try:
            remaining = response.headers.get("x-requests-remaining")
            used = response.headers.get("x-requests-used")
            if remaining is None:
                return
            r = _sync_redis.from_url(settings.REDIS_URL)
            pipe = r.pipeline()
            pipe.set("api_quota:odds_api:remaining", remaining, ex=25 * 3600)
            pipe.set("api_quota:odds_api:used", used or "0", ex=25 * 3600)
            pipe.set(
                "api_quota:odds_api:updated_at",
                datetime.now(timezone.utc).isoformat(),
                ex=25 * 3600,
            )
            pipe.execute()
        except Exception:
            log.debug("odds_api_quota_capture_failed", exc_info=True)

    async def get_scores(self, sport_key: str, days_from: int = 1) -> list:
        """Fetch completed/in-progress scores for a sport. daysFrom=1 includes today + yesterday."""
        raw = await self._get(
            f"/v4/sports/{sport_key}/scores/",
            params={"apiKey": self._api_key, "daysFrom": days_from},
        )
        games = raw if isinstance(raw, list) else []
        log.info("odds_api_scores_fetched", sport_key=sport_key, count=len(games))
        return games
