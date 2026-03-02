"""
Beat bootstrap: reads poll intervals from system_config DB and writes
RedBeat scheduler entries to Redis before Beat starts its tick loop.

Run as: python -m app.workers.beat_bootstrap

This replaces the static beat_schedule dict that was removed from celery_app.py
(FREQ-03). DB-persisted intervals survive Beat restarts because this script
reads from DB each time, and RedBeat's save() preserves last_run_at via hsetnx.
"""
import structlog
from celery.schedules import schedule as celery_schedule
from redbeat import RedBeatSchedulerEntry
from sqlalchemy import select

from app.db.sync_session import SyncSessionLocal
from app.models.config import SystemConfig
from app.workers.celery_app import celery_app

log = structlog.get_logger()

# Maps DB key suffix -> Celery task dotted path
WORKER_TASK_MAP = {
    "prophetx":       "app.workers.poll_prophetx.run",
    "sports_data":    "app.workers.poll_sports_data.run",
    "odds_api":       "app.workers.poll_odds_api.run",
    "sports_api":     "app.workers.poll_sports_api.run",
    "espn":           "app.workers.poll_espn.run",
    "critical_check": "app.workers.poll_critical_check.run",
}

# Maps DB key suffix -> RedBeat entry name (used as Redis key suffix)
BEAT_NAME_MAP = {
    "prophetx":       "poll-prophetx",
    "sports_data":    "poll-sports-data",
    "odds_api":       "poll-odds-api",
    "sports_api":     "poll-sports-api",
    "espn":           "poll-espn",
    "critical_check": "poll-critical-check",
}

# Fallback defaults if DB rows are missing (matches seed.py defaults)
_FALLBACK_INTERVALS = {
    "prophetx": 300.0,
    "sports_data": 30.0,
    "odds_api": 600.0,
    "sports_api": 1800.0,
    "espn": 600.0,
    "critical_check": 30.0,
}


def update_redbeat_entry(worker_key: str, new_seconds: float) -> None:
    """Update a single RedBeat entry's interval. Called from API after DB commit.

    Uses from_key() to preserve last_run_at, then saves with new schedule.
    Falls back to creating a new entry if one doesn't exist yet.
    """
    beat_name = BEAT_NAME_MAP[worker_key]
    task_name = WORKER_TASK_MAP[worker_key]
    redis_key = RedBeatSchedulerEntry.generate_key(celery_app, beat_name)

    try:
        # Load existing entry to preserve last_run_at
        entry = RedBeatSchedulerEntry.from_key(redis_key, app=celery_app)
        entry.schedule = celery_schedule(new_seconds)
    except KeyError:
        # Entry doesn't exist yet — create fresh
        entry = RedBeatSchedulerEntry(
            name=beat_name,
            task=task_name,
            schedule=celery_schedule(new_seconds),
            app=celery_app,
        )

    entry.save()
    log.info("redbeat_entry_updated", beat_name=beat_name, interval=new_seconds)


def bootstrap_beat_schedule() -> None:
    """Read intervals from system_config and write RedBeat entries to Redis.

    Called before Beat starts. Safe to call multiple times -- save() uses
    hsetnx for meta so last_run_at is preserved if the entry already exists.
    """
    log.info("beat_bootstrap_start")

    # Read all system_config rows into a dict
    with SyncSessionLocal() as session:
        configs = session.execute(select(SystemConfig)).scalars().all()
        config_map = {row.key: row.value for row in configs}

    entries_written = 0
    for worker_key, task_name in WORKER_TASK_MAP.items():
        db_key = f"poll_interval_{worker_key}"
        raw_value = config_map.get(db_key)

        if raw_value is not None:
            interval_seconds = float(raw_value)
        else:
            interval_seconds = _FALLBACK_INTERVALS.get(worker_key, 60.0)
            log.warning(
                "beat_bootstrap_fallback",
                worker=worker_key,
                db_key=db_key,
                fallback=interval_seconds,
                reason="DB key missing — seed may not have run yet",
            )

        beat_name = BEAT_NAME_MAP[worker_key]
        entry = RedBeatSchedulerEntry(
            name=beat_name,
            task=task_name,
            schedule=celery_schedule(interval_seconds),
            app=celery_app,
        )
        entry.save()
        entries_written += 1
        log.info(
            "beat_bootstrap_entry",
            beat_name=beat_name,
            task=task_name,
            interval=interval_seconds,
        )

    log.info("beat_bootstrap_complete", entries_written=entries_written)


if __name__ == "__main__":
    bootstrap_beat_schedule()
