"""Unit tests for mismatch_detector.py — no network or DB required."""

import pytest
from app.monitoring.mismatch_detector import (
    FLAG_ONLY_STATUSES,
    SDIO_TO_PX_STATUS,
    compute_is_critical,
    compute_status_match,
    get_expected_px_status,
    is_flag_only,
    is_mismatch,
)


class TestIsMismatch:
    def test_scheduled_to_upcoming_no_mismatch(self):
        """Scheduled SDIO + 'upcoming' ProphetX = no mismatch (statuses agree)."""
        assert is_mismatch("upcoming", "Scheduled") is False

    def test_inprogress_to_upcoming_is_mismatch(self):
        """InProgress SDIO + 'upcoming' ProphetX = mismatch (game started, PX still upcoming)."""
        assert is_mismatch("upcoming", "InProgress") is True

    def test_final_to_ended_no_mismatch(self):
        """Final SDIO + 'ended' ProphetX = no mismatch."""
        assert is_mismatch("ended", "Final") is False

    def test_postponed_not_mismatch_is_flag_only(self):
        """Postponed SDIO → is_mismatch False (flag-only, no auto-action per SYNC-02)."""
        assert is_mismatch("upcoming", "Postponed") is False

    def test_canceled_not_mismatch_is_flag_only(self):
        """Canceled SDIO → is_mismatch False (flag-only, no auto-action per SYNC-02)."""
        assert is_mismatch("upcoming", "Canceled") is False

    def test_unknown_sdio_status_returns_false(self):
        """Unknown SDIO status → is_mismatch False (safe default avoids false positives)."""
        assert is_mismatch("upcoming", "Unknown") is False

    def test_inprogress_to_live_no_mismatch(self):
        """InProgress SDIO + 'live' ProphetX = no mismatch (statuses agree)."""
        assert is_mismatch("live", "InProgress") is False

    def test_final_ot_to_ended_no_mismatch(self):
        """F/OT SDIO + 'ended' ProphetX = no mismatch."""
        assert is_mismatch("ended", "F/OT") is False

    def test_final_so_to_ended_no_mismatch(self):
        """F/SO SDIO + 'ended' ProphetX = no mismatch."""
        assert is_mismatch("ended", "F/SO") is False


class TestGetExpectedPxStatus:
    def test_get_expected_px_status_flag_only_returns_none(self):
        """FLAG_ONLY statuses must return None — no expected ProphetX status."""
        assert get_expected_px_status("Postponed") is None

    def test_get_expected_px_status_canceled_returns_none(self):
        """Canceled is FLAG_ONLY — returns None."""
        assert get_expected_px_status("Canceled") is None

    def test_get_expected_px_status_scheduled(self):
        """Scheduled maps to 'upcoming' (UNCONFIRMED ProphetX value)."""
        assert get_expected_px_status("Scheduled") == "upcoming"

    def test_get_expected_px_status_inprogress(self):
        """InProgress maps to 'live' (UNCONFIRMED ProphetX value)."""
        assert get_expected_px_status("InProgress") == "live"

    def test_get_expected_px_status_unknown_returns_none(self):
        """Unknown SDIO status returns None (not in mapping)."""
        assert get_expected_px_status("CompletelyUnknown") is None


class TestIsFlagOnly:
    def test_postponed_is_flag_only(self):
        assert is_flag_only("Postponed") is True

    def test_canceled_is_flag_only(self):
        assert is_flag_only("Canceled") is True

    def test_suspended_is_flag_only(self):
        assert is_flag_only("Suspended") is True

    def test_delayed_is_flag_only(self):
        assert is_flag_only("Delayed") is True

    def test_scheduled_not_flag_only(self):
        assert is_flag_only("Scheduled") is False

    def test_inprogress_not_flag_only(self):
        assert is_flag_only("InProgress") is False

    def test_final_not_flag_only(self):
        assert is_flag_only("Final") is False


class TestComputeStatusMatchOpticOdds:
    """Tests for OpticOdds as the 6th source in compute_status_match and compute_is_critical."""

    def test_in_progress_agrees_with_live_px(self):
        """OpticOdds in_progress maps to inprogress — agrees with ProphetX live."""
        assert compute_status_match("live", None, None, None, None, "in_progress") is True

    def test_not_started_disagrees_with_live_px(self):
        """OpticOdds not_started maps to scheduled — disagrees with ProphetX live (inprogress)."""
        assert compute_status_match("live", None, None, None, None, "not_started") is False

    def test_none_opticodds_skipped(self):
        """OpticOdds None is skipped (NULL-safe) — returns True when no other sources."""
        assert compute_status_match("live", None, None, None, None, None) is True

    def test_walkover_disagrees_with_live_px(self):
        """OpticOdds walkover maps to final — disagrees with ProphetX live (inprogress)."""
        assert compute_status_match("live", None, None, None, None, "walkover") is False

    def test_finished_disagrees_with_live_px(self):
        """OpticOdds finished maps to final — disagrees with ProphetX live (inprogress)."""
        assert compute_status_match("live", None, None, None, None, "finished") is False

    def test_opticodds_alone_not_critical(self):
        """Only 1 live source (opticodds) — not critical (requires 2 sources)."""
        assert compute_is_critical("not_started", None, None, None, None, "in_progress") is False

    def test_opticodds_plus_sdio_is_critical(self):
        """OpticOdds in_progress + SDIO InProgress = 2 live sources — critical."""
        assert compute_is_critical("not_started", None, "InProgress", None, None, "in_progress") is True

    def test_sdio_alone_not_critical_opticodds_none(self):
        """Only SDIO reports live, opticodds None — 1 source, not critical."""
        assert compute_is_critical("not_started", None, "InProgress", None, None, None) is False

    def test_live_consumer_value_agrees_with_live_px(self):
        """OpticOdds 'live' (consumer canonical) maps to inprogress — agrees with ProphetX live."""
        assert compute_status_match("live", None, None, None, None, "live") is True

    def test_suspended_maps_to_inprogress(self):
        """OpticOdds suspended maps to inprogress — agrees with ProphetX live."""
        assert compute_status_match("live", None, None, None, None, "suspended") is True


class TestComputeStatusMatchAllNoneSources:
    def test_not_started_all_none_sources_returns_true(self):
        """compute_status_match with all external sources None returns True (no disagreement)."""
        assert compute_status_match("not_started", None, None, None, None, None) is True

    def test_live_all_none_sources_returns_true(self):
        """compute_status_match with live px_status and all sources None returns True."""
        assert compute_status_match("live", None, None, None, None, None) is True

    def test_ended_all_none_sources_returns_true(self):
        """compute_status_match with ended px_status and all sources None returns True."""
        assert compute_status_match("ended", None, None, None, None, None) is True
