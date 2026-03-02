"""Nightly rollup: persist yesterday's Redis call counters to PostgreSQL.

Schedule: 02:00 UTC daily via Celery Beat (crontab).
Reads api_calls:{worker}:{yesterday} from Redis, upserts into api_usage_snapshots.
Safe to re-run — uses INSERT ON CONFLICT UPDATE (idempotent).
"""
from datetime import date, timedelta

import structlog
from sqlalchemy.dialects.postgresql import insert

from app.db.redis import get_sync_redis
from app.db.sync_session import SyncSessionLocal
from app.models.api_usage_snapshot import ApiUsageSnapshot
from app.workers.celery_app import celery_app

log = structlog.get_logger()

WORKER_NAMES = [
    "poll_prophetx",
    "poll_sports_data",
    "poll_odds_api",
    "poll_sports_api",
    "poll_espn",
]


@celery_app.task(name="app.workers.rollup_api_usage.run")
def run():
    """Read yesterday's Redis counters and persist to api_usage_snapshots."""
    yesterday = date.today() - timedelta(days=1)
    yesterday_str = yesterday.isoformat()
    r = get_sync_redis()

    with SyncSessionLocal() as session:
        for name in WORKER_NAMES:
            key = f"api_calls:{name}:{yesterday_str}"
            val = r.get(key)
            count = int(val) if val else 0

            stmt = (
                insert(ApiUsageSnapshot)
                .values(
                    worker_name=name,
                    snapshot_date=yesterday,
                    call_count=count,
                )
                .on_conflict_do_update(
                    constraint="uq_worker_date",
                    set_={"call_count": count},
                )
            )
            session.execute(stmt)

        session.commit()

    log.info("rollup_api_usage_complete", date=yesterday_str, workers=len(WORKER_NAMES))
