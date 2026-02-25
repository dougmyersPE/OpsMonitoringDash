"""
Unit tests for EventMatcher and confidence scoring.

No Redis or network connections needed — Redis is mocked.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.monitoring.event_matcher import (
    CONFIDENCE_THRESHOLD,
    EventMatcher,
    compute_confidence,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_TIME = datetime(2026, 3, 1, 19, 0, 0, tzinfo=timezone.utc)


def _dt_iso(dt: datetime) -> str:
    return dt.isoformat()


# ---------------------------------------------------------------------------
# compute_confidence tests
# ---------------------------------------------------------------------------


def test_compute_confidence_sport_mismatch_returns_zero():
    """Different sports must immediately return 0.0."""
    score = compute_confidence(
        px_home="Lakers",
        px_away="Celtics",
        px_start=_BASE_TIME,
        sdio_home="Patriots",
        sdio_away="Cowboys",
        sdio_start=_BASE_TIME,
        px_sport="NBA",
        sdio_sport="NFL",
    )
    assert score == 0.0


def test_compute_confidence_identical_teams_same_time():
    """Identical team names with exact same start time must score >= 0.90."""
    score = compute_confidence(
        px_home="Los Angeles Lakers",
        px_away="Boston Celtics",
        px_start=_BASE_TIME,
        sdio_home="Los Angeles Lakers",
        sdio_away="Boston Celtics",
        sdio_start=_BASE_TIME,
        px_sport="NBA",
        sdio_sport="NBA",
    )
    assert score >= CONFIDENCE_THRESHOLD, f"Expected >= {CONFIDENCE_THRESHOLD}, got {score}"


def test_compute_confidence_similar_names_same_time():
    """'LA Lakers' vs 'Los Angeles Lakers' with same time — log actual score for calibration."""
    score = compute_confidence(
        px_home="LA Lakers",
        px_away="Boston Celtics",
        px_start=_BASE_TIME,
        sdio_home="Los Angeles Lakers",
        sdio_away="Boston Celtics",
        sdio_start=_BASE_TIME,
        px_sport="NBA",
        sdio_sport="NBA",
    )
    # Log the score so calibration is visible in test output
    print(f"\n[calibration] 'LA Lakers' vs 'Los Angeles Lakers' confidence: {score:.4f}")
    # Verify sport mismatch guard is not triggered and score is positive
    assert score > 0.0, "Expected positive score for same-sport similar-name teams"


def test_compute_confidence_time_outside_window_reduces_score():
    """35-minute time delta forces time_score=0.0; overall < 0.90 for typical team scores."""
    from datetime import timedelta

    late_time = _BASE_TIME + timedelta(minutes=35)
    score = compute_confidence(
        px_home="Los Angeles Lakers",
        px_away="Boston Celtics",
        px_start=_BASE_TIME,
        sdio_home="Los Angeles Lakers",
        sdio_away="Boston Celtics",
        sdio_start=late_time,
        px_sport="NBA",
        sdio_sport="NBA",
    )
    # time_score must be 0.0 at 35 min; total weight of teams is 0.70 max
    # Identical names give teams=0.70, time=0.0 → total=0.70 < 0.90
    assert score < CONFIDENCE_THRESHOLD, (
        f"Expected < {CONFIDENCE_THRESHOLD} with 35-min delta, got {score}"
    )


# ---------------------------------------------------------------------------
# EventMatcher tests
# ---------------------------------------------------------------------------


def _make_redis(cached_value=None) -> MagicMock:
    """Create a mock Redis client."""
    redis = MagicMock()
    if cached_value is not None:
        redis.get.return_value = json.dumps(cached_value).encode()
    else:
        redis.get.return_value = None
    return redis


def test_find_best_match_returns_none_when_no_games():
    """Empty sdio_games list must return None."""
    redis = _make_redis()
    matcher = EventMatcher(redis)
    result = matcher.find_best_match(
        px_event={
            "px_event_id": "px-001",
            "sport": "NBA",
            "home_team": "Lakers",
            "away_team": "Celtics",
            "scheduled_start": _BASE_TIME,
        },
        sdio_games=[],
    )
    assert result is None


def test_find_best_match_cache_hit_skips_compute():
    """When Redis returns a cached match, fuzzy computation must be skipped."""
    cached = {"sdio_game_id": "sdio-42", "confidence": 0.97, "is_confirmed": True}
    redis = _make_redis(cached_value=cached)

    matcher = EventMatcher(redis)

    # Patch compute_confidence to detect if it's called
    call_log = []
    import app.monitoring.event_matcher as em_module
    original = em_module.compute_confidence

    def spy(*args, **kwargs):
        call_log.append(args)
        return original(*args, **kwargs)

    em_module.compute_confidence = spy
    try:
        result = matcher.find_best_match(
            px_event={
                "px_event_id": "px-001",
                "sport": "NBA",
                "home_team": "Lakers",
                "away_team": "Celtics",
                "scheduled_start": _BASE_TIME,
            },
            sdio_games=[
                {
                    "sdio_game_id": "sdio-42",
                    "sport": "NBA",
                    "home_team": "Lakers",
                    "away_team": "Celtics",
                    "scheduled_start": _BASE_TIME,
                }
            ],
        )
    finally:
        em_module.compute_confidence = original

    assert result == cached, f"Expected cached result, got {result}"
    assert len(call_log) == 0, "compute_confidence must NOT be called on cache hit"
