"""
ESPN unofficial scoreboard API client.

Covers Golf (PGA), Tennis (ATP/WTA), and MMA (UFC) — sports not covered by
The Odds API scores endpoint or API-Sports free tier.

No authentication required. No published rate limits; poll conservatively.
Endpoints are unofficial but have been stable for several years.

Status state values:
  "pre"  → scheduled / not yet started
  "in"   → in progress / live
  "post" → final / completed
"""

import httpx
import structlog

log = structlog.get_logger()

# Unofficial ESPN scoreboard endpoints by sport key
ENDPOINTS: dict[str, str] = {
    "golf": "https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard",
    "tennis_atp": "https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard",
    "tennis_wta": "https://site.api.espn.com/apis/site/v2/sports/tennis/wta/scoreboard",
    "mma": "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard",
}

# ProphetX sport name (lowercase) → ESPN endpoint keys to query
PX_TO_ESPN: dict[str, list[str]] = {
    "tennis": ["tennis_atp", "tennis_wta"],
    "mma": ["mma"],
    "golf": ["golf"],
}


def _parse_events(data: dict, endpoint_key: str) -> list[dict]:
    """Extract normalised match records from an ESPN scoreboard response.

    Returns a list of dicts with keys:
      home_name   – name of competitor 1 (empty string for tournament-level golf)
      away_name   – name of competitor 2 (empty string for tournament-level golf)
      event_name  – full event / tournament name
      date        – ISO date string (YYYY-MM-DD)
      status_state – "pre", "in", or "post"
      endpoint    – which ESPN endpoint key this came from
      is_tournament – True for golf tournament events (no head-to-head competitors)
    """
    results = []
    for event in data.get("events", []):
        event_name = event.get("name", "")
        date_str = event.get("date", "")

        if not date_str:
            continue

        try:
            from datetime import datetime
            event_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date().isoformat()
        except Exception:
            event_date = ""

        # Event-level status (fallback for competitions without their own status)
        event_state = event.get("status", {}).get("type", {}).get("state", "pre")

        if endpoint_key == "golf":
            # Golf: one record per tournament — no head-to-head competitors
            results.append({
                "home_name": "",
                "away_name": "",
                "event_name": event_name,
                "date": event_date,
                "status_state": event_state,
                "endpoint": endpoint_key,
                "is_tournament": True,
            })
        else:
            # Tennis / MMA: each competition is an individual match or fight
            for comp in event.get("competitions", []):
                comp_state = comp.get("status", {}).get("type", {}).get("state", "")
                effective_state = comp_state if comp_state else event_state

                names = []
                for competitor in comp.get("competitors", []):
                    name = (
                        competitor.get("athlete", {}).get("displayName", "")
                        or competitor.get("team", {}).get("displayName", "")
                    )
                    if name:
                        names.append(name)

                if len(names) < 2:
                    continue

                results.append({
                    "home_name": names[0],
                    "away_name": names[1],
                    "event_name": event_name,
                    "date": event_date,
                    "status_state": effective_state,
                    "endpoint": endpoint_key,
                    "is_tournament": False,
                })

    return results


class EspnApiClient:
    """Async HTTP client for ESPN unofficial scoreboard API. Use as async context manager."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            headers={"Accept": "application/json"},
            timeout=30.0,
        )

    async def __aenter__(self) -> "EspnApiClient":
        return self

    async def __aexit__(self, *_) -> None:
        await self._client.aclose()

    async def get_scoreboard(self, endpoint_key: str) -> list[dict]:
        """Fetch and parse the scoreboard for a given ESPN endpoint key.

        Returns list of normalised match dicts (see _parse_events).
        Returns empty list on any error so callers can safely continue.
        """
        url = ENDPOINTS.get(endpoint_key)
        if not url:
            log.warning("espn_unknown_endpoint", endpoint_key=endpoint_key)
            return []

        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            log.warning("espn_fetch_failed", endpoint_key=endpoint_key, error=str(exc))
            return []

        results = _parse_events(data, endpoint_key)
        log.info("espn_scoreboard_fetched", endpoint_key=endpoint_key, count=len(results))
        return results
