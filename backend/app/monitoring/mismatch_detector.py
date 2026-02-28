"""
Mismatch Detector — pure-function status comparison between ProphetX and SportsDataIO.

No network or DB dependencies. Fully testable in isolation.

Key concepts:
- FLAG_ONLY_STATUSES: statuses where no automated action is taken (SYNC-02)
- SDIO_TO_PX_STATUS: mapping from SportsDataIO status to expected ProphetX status
  NOTE: All ProphetX values are UNCONFIRMED — update after Plan 02-02 logs real API response.
- is_mismatch(): returns True only when auto-correctable mismatch is detected
- is_flag_only(): returns True for statuses requiring human review (Postponed, Canceled, etc.)
"""

import re
from enum import Enum

import structlog

log = structlog.get_logger()


class SdioStatus(str, Enum):
    """Confirmed SportsDataIO game status values."""

    SCHEDULED = "Scheduled"
    IN_PROGRESS = "InProgress"
    FINAL = "Final"
    FINAL_OT = "F/OT"
    FINAL_SO = "F/SO"
    POSTPONED = "Postponed"
    CANCELED = "Canceled"
    SUSPENDED = "Suspended"
    DELAYED = "Delayed"
    FORFEIT = "Forfeit"
    NOT_NECESSARY = "NotNecessary"


# Statuses that require human review — no auto-action should be taken (SYNC-02)
FLAG_ONLY_STATUSES: set[str] = {
    "Postponed",
    "Canceled",
    "Suspended",
    "Delayed",
    "Forfeit",
    "NotNecessary",
}

# Sports API (api-sports.io) status codes that require human review
_SPORTS_API_FLAG_STATUSES: set[str] = {
    "CANC",  # Cancelled
    "PSP",   # Postponed
    "SUSP",  # Suspended
    "ABD",   # Abandoned
}

# Mapping from SportsDataIO status to expected ProphetX status.
# IMPORTANT: All ProphetX values are UNCONFIRMED — must be validated against
# live API response logged by poll_prophetx "prophetx_status_values_observed".
# Update every value with real ProphetX status strings before Plan 02-03 begins.
SDIO_TO_PX_STATUS: dict[str, str] = {
    "Scheduled": "not_started",  # confirmed via prophetx_status_values_observed logs
    "InProgress": "live",  # UNCONFIRMED ProphetX value
    "Final": "ended",  # UNCONFIRMED ProphetX value
    "F/OT": "ended",  # UNCONFIRMED ProphetX value
    "F/SO": "ended",  # UNCONFIRMED ProphetX value
}

# All recognized SDIO statuses (union of mapping keys + flag-only statuses)
_ALL_KNOWN_STATUSES: set[str] = set(SDIO_TO_PX_STATUS.keys()) | FLAG_ONLY_STATUSES


def get_expected_px_status(sdio_status: str) -> str | None:
    """Return the expected ProphetX status for a given SportsDataIO status.

    Returns None for:
    - FLAG_ONLY_STATUSES (Postponed, Canceled, Suspended, etc.) — no auto-action
    - Unknown statuses not in the mapping

    Logs a warning if the status is completely unrecognized.
    """
    if sdio_status in FLAG_ONLY_STATUSES:
        return None

    expected = SDIO_TO_PX_STATUS.get(sdio_status)

    if sdio_status not in _ALL_KNOWN_STATUSES:
        log.warning(
            "unrecognized_sdio_status",
            sdio_status=sdio_status,
            action="returning_none",
        )

    return expected


def is_mismatch(px_status: str, sdio_status: str) -> bool:
    """Return True when ProphetX status does not match what we expect given SDIO status.

    Returns False for flag-only statuses (Postponed, Canceled, etc.) — these
    require human review and cannot be auto-corrected (SYNC-02).

    Returns False for unknown SDIO statuses — safe default to avoid false positives.

    Comparison is case-sensitive; ProphetX values must be confirmed via live API logs.
    """
    expected = get_expected_px_status(sdio_status)
    if expected is None:
        return False
    return px_status != expected


def is_flag_only(sdio_status: str) -> bool:
    """Return True when this SDIO status requires human review (no auto-action).

    Covers Postponed, Canceled, Suspended, Delayed, Forfeit, NotNecessary.
    SYNC-02: system must flag but never take write action for these statuses.
    """
    return sdio_status in FLAG_ONLY_STATUSES


def compute_is_flagged(
    sdio_status: str | None,
    sports_api_status: str | None,
) -> bool:
    """Return True when any source currently reports a flag-worthy status.

    Derived live from current source columns — updates automatically each poll
    cycle without manual clearing. Clears itself when no source reports a
    flag-worthy status (e.g. game rescheduled, or source had no data).
    """
    return (
        bool(sdio_status and sdio_status in FLAG_ONLY_STATUSES)
        or bool(sports_api_status and sports_api_status in _SPORTS_API_FLAG_STATUSES)
    )


# ---------------------------------------------------------------------------
# Canonical status mapping — shared by all three real-world source workers
# ---------------------------------------------------------------------------

_PX_CANONICAL: dict[str, str] = {
    "not_started": "scheduled",
    "upcoming": "scheduled",
    "live": "inprogress",
    "settled": "final",
    "suspended": "inprogress",
    "ended": "final",
}

_ODDS_API_CANONICAL: dict[str, str] = {
    "Scheduled": "scheduled",
    "InProgress": "inprogress",
    "Final": "final",
}

_SDIO_CANONICAL: dict[str, str] = {
    "Scheduled": "scheduled",
    "InProgress": "inprogress",
    "Final": "final",
    "F/OT": "final",
    "F/SO": "final",
}

# ESPN unofficial API status states (Golf/Tennis/MMA)
_ESPN_CANONICAL: dict[str, str] = {
    "pre": "scheduled",
    "in": "inprogress",
    "post": "final",
}

# Sports API status codes (api-sports.io — shared across soccer, basketball, hockey, baseball, NFL)
_SPORTS_API_CANONICAL: dict[str, str] = {
    # Not started
    "NS": "scheduled",
    "TBD": "scheduled",
    # Soccer in-play
    "1H": "inprogress",
    "HT": "inprogress",
    "2H": "inprogress",
    "ET": "inprogress",
    "BT": "inprogress",
    "P": "inprogress",
    "INT": "inprogress",
    "LIVE": "inprogress",
    # Basketball quarters / overtime
    "Q1": "inprogress",
    "Q2": "inprogress",
    "Q3": "inprogress",
    "Q4": "inprogress",
    "OT": "inprogress",
    # Hockey periods
    "P1": "inprogress",
    "P2": "inprogress",
    "P3": "inprogress",
    "AP": "inprogress",
    "SO": "inprogress",
    # Baseball innings: IN1, IN2, ... IN9, IN10, IN11 (extra innings)
    # Handled via _sports_api_to_canonical() — no need to enumerate every number
    # Finished
    "FT": "final",
    "AET": "final",
    "PEN": "final",
    "AOT": "final",
    "POST": "final",
    "CANC": "final",  # Cancelled — treat as terminal for status_match purposes
    "AWD": "final",
    "WO": "final",
}


def _sports_api_to_canonical(status: str) -> str:
    """Map a Sports API status code to canonical form.

    Handles the regular dict lookup plus baseball innings (IN1, IN2, ...) which
    follow a numeric pattern too open-ended to enumerate exhaustively.
    """
    if status in _SPORTS_API_CANONICAL:
        return _SPORTS_API_CANONICAL[status]
    if re.match(r"^IN\d+$", status):  # baseball inning: IN1, IN2, ..., IN12, etc.
        return "inprogress"
    return status.lower()


def compute_status_match(
    px_status: str | None,
    odds_api_status: str | None,
    sports_api_status: str | None,
    sdio_status: str | None,
    espn_status: str | None = None,
) -> bool:
    """Return False if any source with data disagrees with ProphetX status.

    Uses canonical form (scheduled/inprogress/final) for comparison so that
    different string representations of the same state don't cause false mismatches.
    Returns True when ProphetX status is unknown or all sources agree.
    """
    if px_status is None:
        return True

    px_canonical = _PX_CANONICAL.get(px_status, px_status.lower())

    sources: list[tuple[str | None, dict[str, str] | None]] = [
        (odds_api_status, _ODDS_API_CANONICAL),
        (sports_api_status, None),  # uses _sports_api_to_canonical() for baseball inning support
        (sdio_status, _SDIO_CANONICAL),
        (espn_status, _ESPN_CANONICAL),
    ]

    for source_status, canonical_map in sources:
        if not source_status:  # None or empty string — no data from this source
            continue
        if canonical_map is None:
            source_canonical = _sports_api_to_canonical(source_status)
        else:
            source_canonical = canonical_map.get(source_status, source_status.lower())
        if px_canonical != source_canonical:
            return False

    return True


def compute_is_critical(
    px_status: str | None,
    odds_api_status: str | None,
    sports_api_status: str | None,
    sdio_status: str | None,
    espn_status: str | None,
) -> bool:
    """True when any source reports the event as live but ProphetX does not.

    Higher severity than a plain status_match=False: the game is live in the
    real world but ProphetX still shows it as not started (or ended), meaning
    markets on the platform are potentially stale and need immediate attention.
    """
    if not px_status:
        return False

    px_canonical = _PX_CANONICAL.get(px_status, px_status.lower())
    if px_canonical != "scheduled":
        return False  # Only critical when ProphetX shows not-started but sources say live

    sources: list[tuple[str | None, dict[str, str] | None]] = [
        (odds_api_status, _ODDS_API_CANONICAL),
        (sports_api_status, None),
        (sdio_status, _SDIO_CANONICAL),
        (espn_status, _ESPN_CANONICAL),
    ]

    for source_status, canonical_map in sources:
        if not source_status:
            continue
        if canonical_map is None:
            source_canonical = _sports_api_to_canonical(source_status)
        else:
            source_canonical = canonical_map.get(source_status, source_status.lower())
        if source_canonical == "inprogress":
            return True

    return False
