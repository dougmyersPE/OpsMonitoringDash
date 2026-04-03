"""Tests for EventResponse schema — opticodds_status field and is_critical integration."""
import pytest
from unittest.mock import patch
from uuid import uuid4
from datetime import datetime, timezone

from app.schemas.event import EventResponse


class TestEventResponseOpticOddsStatus:
    """Verify opticodds_status is serialized in EventResponse (DASH-02)."""

    def _make_event_dict(self, **overrides):
        """Return a minimal dict that satisfies EventResponse fields."""
        base = {
            "id": uuid4(),
            "prophetx_event_id": "PX-001",
            "sport": "Tennis",
            "league": None,
            "name": "Player A vs Player B",
            "home_team": None,
            "away_team": None,
            "scheduled_start": None,
            "prophetx_status": None,
            "odds_api_status": None,
            "sdio_status": None,
            "espn_status": None,
            "oddsblaze_status": None,
            "opticodds_status": None,
            "status_match": True,
            "is_flagged": False,
            "last_prophetx_poll": None,
            "last_real_world_poll": None,
        }
        base.update(overrides)
        return base

    def test_opticodds_status_field_present_in_schema(self):
        """EventResponse must include opticodds_status in its fields."""
        assert "opticodds_status" in EventResponse.model_fields

    def test_opticodds_status_serializes_none(self):
        """Null opticodds_status serializes as None."""
        resp = EventResponse(**self._make_event_dict(opticodds_status=None))
        assert resp.opticodds_status is None

    def test_opticodds_status_serializes_value(self):
        """Non-null opticodds_status serializes correctly."""
        resp = EventResponse(**self._make_event_dict(opticodds_status="live"))
        assert resp.opticodds_status == "live"

    def test_is_critical_receives_opticodds_status(self):
        """compute_is_critical must be called with opticodds_status as 6th arg."""
        with patch("app.schemas.event.compute_is_critical", return_value=False) as mock_crit:
            resp = EventResponse(**self._make_event_dict(opticodds_status="ended"))
            _ = resp.is_critical
            mock_crit.assert_called_once()
            args = mock_crit.call_args[0]
            assert len(args) == 6, f"Expected 6 positional args, got {len(args)}"
            assert args[5] == "ended", f"6th arg should be 'ended', got {args[5]}"
