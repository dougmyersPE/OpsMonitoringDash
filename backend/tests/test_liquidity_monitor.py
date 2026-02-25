"""Unit tests for liquidity_monitor.py — no network required, DB session mocked."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from app.monitoring.liquidity_monitor import get_effective_threshold, is_below_threshold


def _make_market(current_liquidity: str, min_liquidity_threshold: str | None) -> MagicMock:
    """Build a mock Market with the given liquidity values."""
    market = MagicMock()
    market.current_liquidity = Decimal(current_liquidity)
    market.min_liquidity_threshold = (
        Decimal(min_liquidity_threshold) if min_liquidity_threshold is not None else None
    )
    market.id = "test-market-uuid"
    return market


def _make_session(config_value: str | None) -> MagicMock:
    """Build a mock Session that returns a SystemConfig row or None."""
    session = MagicMock()
    if config_value is not None:
        config_row = MagicMock()
        config_row.value = config_value
        session.query.return_value.filter.return_value.first.return_value = config_row
    else:
        session.query.return_value.filter.return_value.first.return_value = None
    return session


class TestGetEffectiveThreshold:
    def test_returns_market_threshold_when_set(self):
        """Per-market threshold takes priority over global default."""
        market = _make_market("50", "100")
        session = _make_session("200")  # global default should be ignored
        result = get_effective_threshold(market, session)
        assert result == Decimal("100")

    def test_returns_global_default_when_market_threshold_none(self):
        """When market threshold is None, fall back to global SystemConfig default."""
        market = _make_market("50", None)
        session = _make_session("100")
        result = get_effective_threshold(market, session)
        assert result == Decimal("100")

    def test_returns_zero_when_no_threshold_configured(self):
        """When neither market nor global threshold exists, return Decimal('0')."""
        market = _make_market("50", None)
        session = _make_session(None)
        result = get_effective_threshold(market, session)
        assert result == Decimal("0")


class TestIsBelowThreshold:
    def test_is_below_threshold_uses_market_threshold_when_set(self):
        """Market threshold 100, liquidity 50 → below threshold → True."""
        market = _make_market("50", "100")
        session = _make_session(None)
        assert is_below_threshold(market, session) is True

    def test_is_below_threshold_uses_global_default_when_market_threshold_none(self):
        """Global threshold 100, market liquidity 50 → below threshold → True."""
        market = _make_market("50", None)
        session = _make_session("100")
        assert is_below_threshold(market, session) is True

    def test_is_below_threshold_false_when_no_threshold_configured(self):
        """No threshold configured → returns False (safe default, no alert without threshold)."""
        market = _make_market("50", None)
        session = _make_session(None)
        assert is_below_threshold(market, session) is False

    def test_is_below_threshold_false_when_above_threshold(self):
        """Liquidity 150 > threshold 100 → not below → False."""
        market = _make_market("150", "100")
        session = _make_session(None)
        assert is_below_threshold(market, session) is False

    def test_is_below_threshold_false_when_equal_to_threshold(self):
        """Liquidity exactly equal to threshold → not strictly below → False."""
        market = _make_market("100", "100")
        session = _make_session(None)
        assert is_below_threshold(market, session) is False

    def test_is_below_threshold_zero_threshold_always_false(self):
        """Threshold 0 (unconfigured) → False regardless of liquidity."""
        market = _make_market("0", None)
        session = _make_session(None)
        assert is_below_threshold(market, session) is False
