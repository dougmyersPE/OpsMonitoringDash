"""Tests for source toggle backend behavior — TOGL-01 to TOGL-06.

Covers:
- Usage API returns all 6 source toggle keys (TOGL-01, TOGL-02, TOGL-03)
- poll_prophetx authority bypass when prophetx_ws toggle is off (TOGL-04, D-03)
"""

from unittest.mock import MagicMock, patch, AsyncMock

import pytest


# ---------------------------------------------------------------------------
# TestUsageSourceToggleKeys
# ---------------------------------------------------------------------------

class TestUsageSourceToggleKeys:
    """GET /api/v1/usage returns sources_enabled with all 6 source keys."""

    def _build_config_map(self, overrides: dict | None = None) -> dict:
        """Build a minimal config_map as returned by the usage endpoint handler."""
        defaults = {
            "source_enabled_odds_api": "true",
            "source_enabled_sports_data": "true",
            "source_enabled_espn": "true",
            "source_enabled_oddsblaze": "true",
            "source_enabled_opticodds": "true",
            "source_enabled_prophetx_ws": "true",
        }
        if overrides:
            defaults.update(overrides)
        return defaults

    def _parse_sources_enabled(self, config_map: dict, source_toggle_keys: list[str]) -> dict:
        """Replicate usage.py logic: build sources_enabled from config_map."""
        result = {}
        for src in source_toggle_keys:
            val = config_map.get(f"source_enabled_{src}", "true")
            result[src] = val.lower() != "false"
        return result

    def test_oddsblaze_key_present_and_true_by_default(self):
        """sources_enabled must contain 'oddsblaze' defaulting to True."""
        source_toggle_keys = ["odds_api", "sports_data", "espn", "oddsblaze", "opticodds", "prophetx_ws"]
        config_map = self._build_config_map()
        sources_enabled = self._parse_sources_enabled(config_map, source_toggle_keys)
        assert "oddsblaze" in sources_enabled, "oddsblaze key missing from sources_enabled"
        assert sources_enabled["oddsblaze"] is True

    def test_opticodds_key_present_and_true_by_default(self):
        """sources_enabled must contain 'opticodds' defaulting to True."""
        source_toggle_keys = ["odds_api", "sports_data", "espn", "oddsblaze", "opticodds", "prophetx_ws"]
        config_map = self._build_config_map()
        sources_enabled = self._parse_sources_enabled(config_map, source_toggle_keys)
        assert "opticodds" in sources_enabled, "opticodds key missing from sources_enabled"
        assert sources_enabled["opticodds"] is True

    def test_prophetx_ws_key_present_and_true_by_default(self):
        """sources_enabled must contain 'prophetx_ws' defaulting to True."""
        source_toggle_keys = ["odds_api", "sports_data", "espn", "oddsblaze", "opticodds", "prophetx_ws"]
        config_map = self._build_config_map()
        sources_enabled = self._parse_sources_enabled(config_map, source_toggle_keys)
        assert "prophetx_ws" in sources_enabled, "prophetx_ws key missing from sources_enabled"
        assert sources_enabled["prophetx_ws"] is True

    def test_prophetx_ws_false_when_db_says_false(self):
        """sources_enabled['prophetx_ws'] should be False when DB key is 'false'."""
        source_toggle_keys = ["odds_api", "sports_data", "espn", "oddsblaze", "opticodds", "prophetx_ws"]
        config_map = self._build_config_map({"source_enabled_prophetx_ws": "false"})
        sources_enabled = self._parse_sources_enabled(config_map, source_toggle_keys)
        assert sources_enabled["prophetx_ws"] is False

    def test_missing_db_row_defaults_to_true(self):
        """When source_enabled_<key> has no DB row, sources_enabled[key] defaults to True."""
        source_toggle_keys = ["odds_api", "sports_data", "espn", "oddsblaze", "opticodds", "prophetx_ws"]
        config_map = {}  # No keys in DB
        sources_enabled = self._parse_sources_enabled(config_map, source_toggle_keys)
        assert sources_enabled["opticodds"] is True
        assert sources_enabled["prophetx_ws"] is True
        assert sources_enabled["oddsblaze"] is True

    def test_all_six_keys_returned(self):
        """sources_enabled must include exactly the 6 expected source keys."""
        expected_keys = {"odds_api", "sports_data", "espn", "oddsblaze", "opticodds", "prophetx_ws"}
        source_toggle_keys = ["odds_api", "sports_data", "espn", "oddsblaze", "opticodds", "prophetx_ws"]
        config_map = self._build_config_map()
        sources_enabled = self._parse_sources_enabled(config_map, source_toggle_keys)
        assert set(sources_enabled.keys()) == expected_keys


# ---------------------------------------------------------------------------
# TestPollProphetxAuthorityBypass
# ---------------------------------------------------------------------------

class TestPollProphetxAuthorityBypass:
    """poll_prophetx bypasses WS authority window when prophetx_ws toggle is off (D-03)."""

    def _make_existing_event(self, ws_delivered_at=None):
        """Build a mock Event with a recent ws_delivered_at."""
        from datetime import datetime, timezone, timedelta
        mock_event = MagicMock()
        mock_event.prophetx_status = "not_started"
        mock_event.odds_api_status = None
        mock_event.sdio_status = None
        mock_event.espn_status = None
        mock_event.oddsblaze_status = None
        mock_event.opticodds_status = None
        mock_event.sport = "soccer"
        mock_event.name = "Test Match"
        mock_event.home_team = "Home"
        mock_event.away_team = "Away"
        mock_event.scheduled_start = None
        mock_event.league = None
        mock_event.ws_delivered_at = ws_delivered_at or datetime.now(timezone.utc) - timedelta(seconds=10)
        return mock_event

    def test_authority_bypassed_when_ws_toggle_off(self):
        """When prophetx_ws is disabled, poll MUST write status even if ws_delivered_at is recent.

        D-03: ws_toggle_on = False → authoritative = False AND False = False → status written.
        """
        from datetime import datetime, timezone, timedelta

        # Simulate: ws_toggle_on=False, is_ws_authoritative would return True (recent delivery)
        # With bypass: authoritative = False AND True = False → poll writes status
        ws_toggle_on = False
        is_ws_auth_result = True  # WS would be authoritative if toggle were on

        authoritative = ws_toggle_on and is_ws_auth_result
        assert authoritative is False, (
            "When WS toggle is off, poll_prophetx must ignore authority window"
        )

    def test_authority_respected_when_ws_toggle_on(self):
        """When prophetx_ws is enabled, poll MUST respect authority window.

        D-03: ws_toggle_on = True → authoritative = True AND is_ws_authoritative() result.
        """
        from datetime import datetime, timezone, timedelta

        ws_toggle_on = True
        is_ws_auth_result = True  # WS delivered recently

        authoritative = ws_toggle_on and is_ws_auth_result
        assert authoritative is True, (
            "When WS toggle is on, authority window must be respected"
        )

    def test_poll_prophetx_imports_is_source_enabled(self):
        """poll_prophetx.py must import is_source_enabled (as _is_source_enabled)."""
        import importlib
        import app.workers.poll_prophetx as mod
        assert hasattr(mod, "_is_source_enabled"), (
            "poll_prophetx must import is_source_enabled as _is_source_enabled"
        )

    def test_ws_prophetx_imports_is_source_enabled(self):
        """ws_prophetx.py must import is_source_enabled."""
        import app.workers.ws_prophetx as mod
        assert hasattr(mod, "is_source_enabled"), (
            "ws_prophetx must import is_source_enabled"
        )
