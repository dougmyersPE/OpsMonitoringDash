"""
EventMatcher — fuzzy matching between ProphetX events and SportsDataIO games.

Combines team name similarity (rapidfuzz token_sort_ratio) with start time
proximity to produce a confidence score in [0.0, 1.0].

Usage:
    from app.monitoring.event_matcher import EventMatcher

    matcher = EventMatcher(redis_client)
    result = matcher.find_best_match(px_event, sdio_games)
"""

import json
from datetime import datetime, timezone

from rapidfuzz import fuzz

# ---------------------------------------------------------------------------
# Scoring weights and thresholds
# ---------------------------------------------------------------------------
TEAM_WEIGHT_HOME = 0.35
TEAM_WEIGHT_AWAY = 0.35
TIME_WEIGHT = 0.30
# >= this triggers auto-action (confirmed match)
CONFIDENCE_THRESHOLD = 0.90
# full score within ± 15 min; decays to 0 at 30 min
TIME_WINDOW_MINUTES = 15
# 24 hours — Redis TTL for match cache entries
MATCH_CACHE_TTL = 86400


def _parse_dt(value) -> datetime | None:
    """Parse ISO string or return datetime as-is. Attaches UTC if no tzinfo."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    # ISO string
    dt = datetime.fromisoformat(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def compute_confidence(
    px_home: str,
    px_away: str,
    px_start,
    sdio_home: str,
    sdio_away: str,
    sdio_start,
    px_sport: str,
    sdio_sport: str,
) -> float:
    """Compute a confidence score in [0.0, 1.0] for a ProphetX/SportsDataIO pair.

    Returns 0.0 immediately when sports don't match.

    Weights: home_team=0.35, away_team=0.35, start_time=0.30.
    Time score is 1.0 within ±15 min, decays linearly to 0.0 at 30 min.

    # Threshold calibration: adjust weights/threshold after observing real API
    # data (see RESEARCH.md Pitfall 2). Current values are reasonable defaults
    # but may need tuning once live data is available.
    """
    # Sport mismatch → immediate reject
    if px_sport.lower().strip() != sdio_sport.lower().strip():
        return 0.0

    # Normalize team names
    def norm(s: str) -> str:
        return (s or "").lower().strip()

    home_score = fuzz.token_sort_ratio(norm(px_home), norm(sdio_home)) / 100.0
    away_score = fuzz.token_sort_ratio(norm(px_away), norm(sdio_away)) / 100.0

    # Time score: 1.0 within ±15 min, linear decay to 0.0 at 30 min, 0.0 beyond
    px_dt = _parse_dt(px_start)
    sdio_dt = _parse_dt(sdio_start)

    if px_dt is None or sdio_dt is None:
        time_score = 0.0
    else:
        delta_minutes = abs((px_dt - sdio_dt).total_seconds()) / 60.0
        if delta_minutes <= TIME_WINDOW_MINUTES:
            time_score = 1.0
        elif delta_minutes <= TIME_WINDOW_MINUTES * 2:
            # Linear decay from 1.0 at 15 min to 0.0 at 30 min
            time_score = 1.0 - (delta_minutes - TIME_WINDOW_MINUTES) / TIME_WINDOW_MINUTES
        else:
            time_score = 0.0

    return (
        TEAM_WEIGHT_HOME * home_score
        + TEAM_WEIGHT_AWAY * away_score
        + TIME_WEIGHT * time_score
    )


def _cache_key(px_event_id: str) -> str:
    return f"match:px:{px_event_id}"


def get_cached_match(redis_client, px_event_id: str) -> dict | None:
    """Return the cached match dict for a ProphetX event, or None on miss."""
    key = _cache_key(px_event_id)
    raw = redis_client.get(key)
    if raw is None:
        return None
    return json.loads(raw)


def cache_match(redis_client, px_event_id: str, match: dict) -> None:
    """Write a match dict to Redis with 24-hour TTL."""
    key = _cache_key(px_event_id)
    redis_client.setex(key, MATCH_CACHE_TTL, json.dumps(match))


def invalidate_match_cache(redis_client, px_event_id: str) -> None:
    """Remove a cached match — call when event's scheduled_start changes."""
    redis_client.delete(_cache_key(px_event_id))


class EventMatcher:
    """Matches ProphetX events to SportsDataIO games using fuzzy name + time scoring.

    Checks Redis cache before computing. Writes confirmed matches (>= 0.90) to cache.

    Args:
        redis_client: A redis.Redis (or compatible) client instance.
    """

    def __init__(self, redis_client) -> None:
        self.redis_client = redis_client

    def find_best_match(self, px_event: dict, sdio_games: list[dict]) -> dict | None:
        """Find the best-matching SportsDataIO game for a ProphetX event.

        Args:
            px_event: Dict with keys: px_event_id, sport, home_team, away_team,
                      scheduled_start (ISO string or datetime).
            sdio_games: List of dicts with keys: sdio_game_id, sport, home_team,
                        away_team, scheduled_start (ISO string or datetime).

        Returns:
            Dict with {sdio_game_id, confidence, is_confirmed} if a match is found,
            {sdio_game_id, confidence, is_confirmed, is_flagged} if a low-confidence
            candidate exists, or None if no games or all scores are 0.
        """
        px_event_id = px_event["px_event_id"]

        # Cache hit — skip fuzzy computation
        cached = get_cached_match(self.redis_client, px_event_id)
        if cached is not None:
            return cached

        if not sdio_games:
            return None

        best_score = 0.0
        best_game = None

        for game in sdio_games:
            score = compute_confidence(
                px_home=px_event.get("home_team", ""),
                px_away=px_event.get("away_team", ""),
                px_start=px_event.get("scheduled_start"),
                sdio_home=game.get("home_team", ""),
                sdio_away=game.get("away_team", ""),
                sdio_start=game.get("scheduled_start"),
                px_sport=px_event.get("sport", ""),
                sdio_sport=game.get("sport", ""),
            )
            if score > best_score:
                best_score = score
                best_game = game

        if best_game is None or best_score == 0.0:
            return None

        if best_score >= CONFIDENCE_THRESHOLD:
            result = {
                "sdio_game_id": best_game["sdio_game_id"],
                "confidence": best_score,
                "is_confirmed": True,
            }
            cache_match(self.redis_client, px_event_id, result)
            return result

        # Low-confidence candidate — flagged but not confirmed
        return {
            "sdio_game_id": best_game["sdio_game_id"],
            "confidence": best_score,
            "is_confirmed": False,
            "is_flagged": True,
        }
