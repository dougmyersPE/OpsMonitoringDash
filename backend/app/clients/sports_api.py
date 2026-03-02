"""
Sports API client (api-sports.io / dashboard.api-football.com).

Covers all major sports via a single key:
  Soccer:           https://v3.football.api-sports.io/fixtures
  Basketball (NBA): https://v2.basketball.api-sports.io/games
  Hockey (NHL):     https://v2.hockey.api-sports.io/games
  Baseball (MLB):   https://v2.baseball.api-sports.io/games
  American Football (NFL): https://v1.american-football.api-sports.io/games

All endpoints accept the key via x-apisports-key header.
"""

import httpx
import redis as _sync_redis
import structlog
from datetime import date, datetime, timezone

from app.core.config import settings

log = structlog.get_logger()

# Base URLs and endpoint paths per sport
SPORT_CONFIGS: dict[str, dict] = {
    "soccer": {
        "base_url": "https://v3.football.api-sports.io",
        "endpoint": "/fixtures",
        "date_param": "date",
        "response_key": "response",
    },
    "basketball": {
        "base_url": "https://v1.basketball.api-sports.io",
        "endpoint": "/games",
        "date_param": "date",
        "response_key": "response",
    },
    "hockey": {
        "base_url": "https://v1.hockey.api-sports.io",
        "endpoint": "/games",
        "date_param": "date",
        "response_key": "response",
    },
    "baseball": {
        "base_url": "https://v1.baseball.api-sports.io",
        "endpoint": "/games",
        "date_param": "date",
        "response_key": "response",
    },
    "american-football": {
        "base_url": "https://v1.american-football.api-sports.io",
        "endpoint": "/games",
        "date_param": "date",
        "response_key": "response",
    },
}

# Map ProphetX sport names to API-Sports sport keys
PX_TO_API_SPORTS: dict[str, str] = {
    "soccer": "soccer",
    "basketball": "basketball",
    "hockey": "hockey",
    "baseball": "baseball",
    "american-football": "american-football",
    # Common ProphetX variations
    "nba": "basketball",
    "nhl": "hockey",
    "mlb": "baseball",
    "nfl": "american-football",
    "mls": "soccer",
    "ice hockey": "hockey",
    "american football": "american-football",
}


def _extract_status(game: dict, sport: str) -> str:
    """Extract the status short code from a game object, normalised across sports."""
    if sport == "soccer":
        return game.get("fixture", {}).get("status", {}).get("short", "NS")
    else:
        return game.get("status", {}).get("short", "NS")


def _extract_teams(game: dict, sport: str) -> tuple[str, str]:
    """Return (home_team_name, away_team_name) from a game object."""
    home = game.get("teams", {}).get("home", {}).get("name", "")
    away = game.get("teams", {}).get("away", {}).get("name", "")
    return home, away


def _extract_date(game: dict, sport: str) -> str:
    """Return ISO date string for the game."""
    if sport == "soccer":
        return game.get("fixture", {}).get("date", "")
    else:
        return game.get("date", "")


class SportsApiClient:
    """Async HTTP client for api-sports.io. Use as async context manager."""

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._clients: dict[str, httpx.AsyncClient] = {}

    async def __aenter__(self) -> "SportsApiClient":
        return self

    async def __aexit__(self, *_) -> None:
        for client in self._clients.values():
            await client.aclose()

    def _get_client(self, sport: str) -> httpx.AsyncClient:
        if sport not in self._clients:
            config = SPORT_CONFIGS[sport]
            self._clients[sport] = httpx.AsyncClient(
                base_url=config["base_url"],
                headers={
                    "x-apisports-key": self._api_key,
                    "Accept": "application/json",
                },
                timeout=30.0,
            )
        return self._clients[sport]

    async def get_games(self, sport: str, game_date: date) -> list[dict]:
        """Fetch all games for a sport on a given date.

        Returns a list of normalised game dicts with keys:
          home_team, away_team, status_short, date_str, sport
        """
        config = SPORT_CONFIGS.get(sport)
        if config is None:
            log.warning("sports_api_unknown_sport", sport=sport)
            return []

        client = self._get_client(sport)
        params = {config["date_param"]: game_date.isoformat()}

        try:
            resp = await client.get(config["endpoint"], params=params)
            resp.raise_for_status()
            # Capture per-sport quota headers (api-sports.io rate limits)
            try:
                remaining = resp.headers.get("x-ratelimit-requests-remaining")
                limit = resp.headers.get("x-ratelimit-requests-limit")
                if remaining is not None:
                    r = _sync_redis.from_url(settings.REDIS_URL)
                    pipe = r.pipeline()
                    pipe.set(f"api_quota:sports_api:{sport}:remaining", remaining, ex=25 * 3600)
                    pipe.set(f"api_quota:sports_api:{sport}:limit", limit or "100", ex=25 * 3600)
                    pipe.set(
                        f"api_quota:sports_api:{sport}:updated_at",
                        datetime.now(timezone.utc).isoformat(),
                        ex=25 * 3600,
                    )
                    pipe.execute()
            except Exception:
                log.debug("sports_api_quota_capture_failed", sport=sport, exc_info=True)
            data = resp.json()
        except Exception as exc:
            log.warning("sports_api_fetch_failed", sport=sport, date=str(game_date), error=str(exc))
            return []

        raw_games = data.get(config["response_key"], [])
        results = []
        for game in raw_games:
            home, away = _extract_teams(game, sport)
            status_short = _extract_status(game, sport)
            date_str = _extract_date(game, sport)
            if home and away:
                results.append({
                    "home_team": home,
                    "away_team": away,
                    "status_short": status_short,
                    "date_str": date_str,
                    "sport": sport,
                })

        log.debug("sports_api_games_fetched", sport=sport, date=str(game_date), count=len(results))
        return results
