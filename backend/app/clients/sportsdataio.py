from app.clients.base import BaseAPIClient
from app.core.config import settings
from datetime import date
import structlog

log = structlog.get_logger()

SPORTSDATAIO_BASE_URL = "https://api.sportsdata.io/v3"

# SportsDataIO URL path segment differs from the logical sport name for some sports.
# e.g. college basketball is /cbb/ not /ncaab/, college football is /cfb/ not /ncaaf/
SPORT_PATH_MAP: dict[str, str] = {
    "ncaab": "cbb",
    "ncaaf": "cfb",
}


class SportsDataIOClient(BaseAPIClient):
    def __init__(self, api_key: str | None = None):
        super().__init__(base_url=SPORTSDATAIO_BASE_URL)
        self._api_key = api_key or settings.SPORTSDATAIO_API_KEY
        # Per research Pitfall 5: ALWAYS use header auth, never query param.
        # Query param auth logs the API key in Nginx access logs — security risk.
        self._headers = {"Ocp-Apim-Subscription-Key": self._api_key}

    async def get_games_by_date_raw(self, sport: str, game_date: str | None = None) -> list:
        """
        Fetch raw games for a sport on a given date (default: today).
        sport: logical sport name e.g. "ncaab", "nba", "mlb", "nhl"
        game_date: YYYY-MM-DD format; defaults to today
        """
        if game_date is None:
            game_date = date.today().isoformat()
        path_sport = SPORT_PATH_MAP.get(sport, sport)
        raw = await self._get(
            f"/{path_sport}/scores/json/GamesByDate/{game_date}",
            headers=self._headers,
        )
        log.info(
            "sportsdataio_games_raw",
            sport=sport,
            date=game_date,
            count=len(raw) if isinstance(raw, list) else "not-a-list",
        )
        log.debug("sportsdataio_games_full_response", sport=sport, response=raw)
        return raw

    async def get_soccer_competitions(self) -> list[dict]:
        """Return all available soccer competitions from SDIO."""
        raw = await self._get("/soccer/scores/json/Competitions", headers=self._headers)
        return raw if isinstance(raw, list) else []

    async def get_soccer_games_by_date(self, competition_id: int | str, game_date: str) -> list:
        """Fetch games for one soccer competition on a given date."""
        raw = await self._get(
            f"/soccer/scores/json/GamesByDate/{competition_id}/{game_date}",
            headers=self._headers,
        )
        return raw if isinstance(raw, list) else []

    async def get_team_names(self, sport: str) -> dict[str, str]:
        """Return {abbreviation: 'School Mascot'} for all teams in a sport.

        Used for college sports where GamesByDate returns short codes (e.g. 'TROY')
        instead of full names. Result should be cached by the caller.
        """
        path_sport = SPORT_PATH_MAP.get(sport, sport)
        raw = await self._get(f"/{path_sport}/scores/json/Teams", headers=self._headers)
        if not isinstance(raw, list):
            return {}
        return {
            t["Key"]: f"{t['School']} {t['Name']}"
            for t in raw
            if isinstance(t, dict) and t.get("Key") and t.get("School") and t.get("Name")
        }

    async def probe_subscription_coverage(self) -> dict[str, int]:
        """
        Phase 1 helper: test which sports are in the current subscription.
        Returns dict of sport -> HTTP status code (200 = covered, 403 = not covered).
        Per research Open Question 3: document coverage before Phase 2 builds polling.
        """
        import httpx
        sports = ["nfl", "nba", "mlb", "nhl", "ncaab", "ncaaf", "soccer"]
        coverage: dict[str, int] = {}
        for sport in sports:
            try:
                await self.get_games_by_date_raw(sport)
                coverage[sport] = 200
            except httpx.HTTPStatusError as e:
                coverage[sport] = e.response.status_code
            except Exception:
                coverage[sport] = -1
        log.info("sportsdataio_subscription_coverage", coverage=coverage)
        return coverage
