"""Unit tests for WS authority helper (is_ws_authoritative)."""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from app.monitoring.authority import is_ws_authoritative


class TestAuthorityHelper:
    """Tests for the is_ws_authoritative() pure helper function."""

    def test_none_delivered_at_returns_false(self):
        """When ws_delivered_at is None, returns False immediately."""
        result = is_ws_authoritative(None, 600)
        assert result is False

    def test_within_window_returns_true(self):
        """When ws_delivered_at is 5 minutes ago, returns True (within 600s window)."""
        five_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
        result = is_ws_authoritative(five_minutes_ago, 600)
        assert result is True

    def test_expired_window_returns_false(self):
        """When ws_delivered_at is 15 minutes ago, returns False (exceeds 600s window)."""
        fifteen_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=15)
        result = is_ws_authoritative(fifteen_minutes_ago, 600)
        assert result is False

    def test_naive_datetime_coerced_to_utc(self):
        """Naive datetime 5 minutes ago is coerced to UTC and returns True."""
        # Naive datetime (no tzinfo), equivalent to 5 minutes ago in UTC
        five_minutes_ago_naive = datetime.utcnow() - timedelta(minutes=5)
        assert five_minutes_ago_naive.tzinfo is None
        result = is_ws_authoritative(five_minutes_ago_naive, 600)
        assert result is True

    def test_exactly_at_boundary_returns_false(self):
        """When elapsed == threshold (exactly at boundary), returns False (not strictly <)."""
        # We mock datetime.now to control exact elapsed time
        fixed_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        # ws_delivered_at is exactly 600 seconds before "now"
        delivered_at = fixed_now - timedelta(seconds=600)

        with patch("app.monitoring.authority.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            # Make replace() still work for naive datetime coercion
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            result = is_ws_authoritative(delivered_at, 600)

        assert result is False
