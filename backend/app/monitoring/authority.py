"""
WS Authority Helper — pure function for WS-primary status authority model.

Determines whether the WebSocket-delivered status is still authoritative
(within the configured window). Workers call this before deciding whether
to overwrite prophetx_status from poll data.

No network or DB dependencies — fully testable in isolation.
"""

from datetime import datetime, timezone


def is_ws_authoritative(ws_delivered_at: datetime | None, threshold_seconds: int) -> bool:
    """Return True if ws_delivered_at is within threshold_seconds of now.

    Args:
        ws_delivered_at: UTC timestamp when the WS consumer last delivered a status
            update for this event. None means WS has never delivered status.
        threshold_seconds: Authority window in seconds (typically from
            settings.WS_AUTHORITY_WINDOW_SECONDS = 600).

    Returns:
        True  — WS is authoritative; poll workers must not overwrite prophetx_status.
        False — WS authority has expired or was never established; poll may write.

    Edge cases:
        - None ws_delivered_at → False (WS never delivered status for this event)
        - Naive datetime → coerced to UTC before comparison
        - elapsed == threshold → False (boundary is exclusive: must be strictly <)
    """
    if ws_delivered_at is None:
        return False

    now = datetime.now(timezone.utc)
    if ws_delivered_at.tzinfo is None:
        ws_delivered_at = ws_delivered_at.replace(tzinfo=timezone.utc)

    elapsed = (now - ws_delivered_at).total_seconds()
    return elapsed < threshold_seconds
