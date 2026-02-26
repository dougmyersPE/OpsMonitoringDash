import structlog

from app.clients.base import BaseAPIClient
from app.core.config import settings

log = structlog.get_logger()

BASE_URL = "https://api.the-odds-api.com"

# ProphetX sport_name (lowercase) → Odds API sport_keys to query
SPORT_KEY_MAP: dict[str, list[str]] = {
    "basketball": ["basketball_nba"],
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

    async def get_scores(self, sport_key: str, days_from: int = 1) -> list:
        """Fetch completed/in-progress scores for a sport. daysFrom=1 includes today + yesterday."""
        raw = await self._get(
            f"/v4/sports/{sport_key}/scores/",
            params={"apiKey": self._api_key, "daysFrom": days_from},
        )
        games = raw if isinstance(raw, list) else []
        log.info("odds_api_scores_fetched", sport_key=sport_key, count=len(games))
        return games
