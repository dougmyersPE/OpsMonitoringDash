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

    # Beat schedule — 30-second stub tasks (Phase 2 will replace log stubs with real logic)
    beat_schedule={
        "poll-prophetx": {
            "task": "app.workers.poll_prophetx.run",
            "schedule": 30.0,
        },
        "poll-sports-data": {
            "task": "app.workers.poll_sports_data.run",
            "schedule": 30.0,
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
