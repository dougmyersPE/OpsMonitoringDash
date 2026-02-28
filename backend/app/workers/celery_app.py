from celery import Celery
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
        "app.workers.poll_critical_check",
    ],
)

celery_app.conf.update(
    # RedBeat scheduler — stores schedule state in Redis (locked decision per STATE.md)
    beat_scheduler="redbeat.RedBeatScheduler",
    redbeat_redis_url=settings.REDBEAT_REDIS_URL,
    redbeat_lock_timeout=300,  # 5 minutes; prevents duplicate Beat instances

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

    # Beat schedule — intervals configured via POLL_INTERVAL_* env vars
    beat_schedule={
        "poll-prophetx": {
            "task": "app.workers.poll_prophetx.run",
            "schedule": float(settings.POLL_INTERVAL_PROPHETX),
        },
        "poll-sports-data": {
            "task": "app.workers.poll_sports_data.run",
            "schedule": float(settings.POLL_INTERVAL_SPORTS_DATA),
        },
        "poll-odds-api": {
            "task": "app.workers.poll_odds_api.run",
            "schedule": float(settings.POLL_INTERVAL_ODDS_API),
        },
        "poll-sports-api": {
            "task": "app.workers.poll_sports_api.run",
            "schedule": float(settings.POLL_INTERVAL_SPORTS_API),
        },
        "poll-espn": {
            "task": "app.workers.poll_espn.run",
            "schedule": float(settings.POLL_INTERVAL_ESPN),
        },
        "poll-critical-check": {
            "task": "app.workers.poll_critical_check.run",
            "schedule": 60.0,
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
