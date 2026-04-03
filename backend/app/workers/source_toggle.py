"""Source enable/disable toggle helpers for poll workers.

Each real-world source (odds_api, sports_data, espn, oddsblaze) can be
disabled via system_config key `source_enabled_{name}`. When disabled:
1. Worker skips polling (no API calls)
2. Source column is NULLed on all events
3. status_match is recomputed so stale data doesn't cause false alerts
"""
import structlog
from sqlalchemy import select, update

from app.db.sync_session import SyncSessionLocal
from app.models.config import SystemConfig
from app.models.event import Event
from app.monitoring.mismatch_detector import compute_status_match

log = structlog.get_logger()

# Maps source key suffix -> Event column name
SOURCE_COLUMN_MAP = {
    "odds_api": "odds_api_status",
    "sports_data": "sdio_status",
    "espn": "espn_status",
    "oddsblaze": "oddsblaze_status",
    "opticodds": "opticodds_status",
}


def is_source_enabled(source_key: str) -> bool:
    """Check if a source is enabled in system_config. Returns True if key missing."""
    config_key = f"source_enabled_{source_key}"
    with SyncSessionLocal() as session:
        result = session.execute(
            select(SystemConfig.value).where(SystemConfig.key == config_key)
        ).scalar_one_or_none()
        return result is None or result.lower() != "false"


def clear_source_and_recompute(source_key: str) -> int:
    """NULL out a source's status column and recompute status_match for all events.

    Returns the number of events updated.
    """
    column_name = SOURCE_COLUMN_MAP.get(source_key)
    if not column_name:
        return 0

    with SyncSessionLocal() as session:
        # NULL out the source column for all events that have data
        column = getattr(Event, column_name)
        events = session.execute(
            select(Event).where(column.isnot(None))
        ).scalars().all()

        count = 0
        for ev in events:
            setattr(ev, column_name, None)
            ev.status_match = compute_status_match(
                ev.prophetx_status,
                ev.odds_api_status if column_name != "odds_api_status" else None,
                ev.sdio_status if column_name != "sdio_status" else None,
                ev.espn_status if column_name != "espn_status" else None,
                ev.oddsblaze_status if column_name != "oddsblaze_status" else None,
                ev.opticodds_status if column_name != "opticodds_status" else None,
            )
            count += 1

        if count > 0:
            session.commit()
            log.info("source_column_cleared", source=source_key, column=column_name, events=count)

        return count
