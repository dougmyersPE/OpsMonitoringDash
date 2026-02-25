from app.workers.celery_app import celery_app
import structlog

log = structlog.get_logger()


@celery_app.task(name="app.workers.poll_prophetx.run", bind=True, max_retries=3)
def run(self):
    """Phase 1 stub: logs that the task fired. Phase 2 adds actual ProphetX API calls."""
    log.info("poll_prophetx_fired", task_id=self.request.id)
    # Phase 2 will call ProphetXClient().get_events_raw() here
