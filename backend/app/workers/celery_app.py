from celery import Celery
from celery.schedules import crontab
from app.core.config import settings
import structlog

log = structlog.get_logger()

celery_app = Celery(
    "prophet_monitor",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.poll_prophetx",
        "app.workers.poll_sports_data",
        "app.workers.poll_odds_api",
        "app.workers.poll_sports_api",
        "app.workers.poll_espn",
        "app.workers.poll_oddsblaze",
        "app.workers.poll_critical_check",
        "app.workers.rollup_api_usage",
        "app.workers.cleanup_old_events",
    ],
)

celery_app.conf.update(
    # RedBeat scheduler — stores schedule state in Redis (locked decision per STATE.md)
    beat_scheduler="redbeat.RedBeatScheduler",
    redbeat_redis_url=settings.REDBEAT_REDIS_URL,
    redbeat_lock_timeout=900,  # 15 min — must be > beat_max_loop_interval (300s default) to avoid LockNotOwnedError

    # Task serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Reliability settings
    task_acks_late=True,             # Only ack after successful execution
    task_reject_on_worker_lost=True, # Re-queue if worker dies mid-task

    # Memory management
    result_expires=3600,             # 1-hour TTL on task results in Redis
    task_ignore_result=True,         # Polling tasks don't need result storage
    worker_max_memory_per_child=400000,  # 400MB — recycle fork worker after task instead of OOM kill

    # Beat schedule: only static (non-operator-configurable) tasks go here.
    # Poll interval entries are DB-backed (FREQ-03) — beat_bootstrap.py writes
    # RedBeat entries from system_config before Beat starts.
    # DO NOT add poll_interval entries here — they would overwrite DB-configured intervals on restart.
    beat_schedule={
        "rollup-api-usage": {
            "task": "app.workers.rollup_api_usage.run",
            "schedule": crontab(hour=2, minute=0),  # 02:00 UTC nightly
        },
        "cleanup-old-events": {
            "task": "app.workers.cleanup_old_events.run",
            "schedule": crontab(hour="*/6", minute=15),  # every 6 hours at :15
        },
    },
)

# Startup assertion: fail loudly if RedBeat is not configured correctly.
# Per Pitfall 3 in research: without this check, Beat silently falls back
# to the file-based scheduler, causing duplicate tasks on container restart.
assert celery_app.conf.beat_scheduler == "redbeat.RedBeatScheduler", (
    "Beat scheduler must be RedBeatScheduler — check REDBEAT_REDIS_URL in .env. "
    "The file-based scheduler causes duplicate tasks on container restart."
)
