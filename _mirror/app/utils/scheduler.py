from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.dependencies import get_mirror_update_service
from app.utils.app_logging import log_event

FULL_UPDATE_JOB_ID = "full_mirror_update"


async def scheduled_full_update():
    """Wrapper for scheduled mirror update task."""
    try:
        service = await get_mirror_update_service()
        await service.full_mirror_update(scheduled=True)
    except Exception as exc:
        log_event(
            log_type="errors",
            message=f"Scheduled full mirror update failed: {exc!r}",
            notify=True,
            action_name="Scheduled full mirror update",
        )


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure scheduler with all jobs."""
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        scheduled_full_update,
        trigger=CronTrigger(
            hour=settings.app.scheduler_full_update_hour,
            minute=settings.app.scheduler_full_update_minute,
        ),
        id=FULL_UPDATE_JOB_ID,
        name="Daily full mirror update",
        replace_existing=True,
        misfire_grace_time=600,
        coalesce=True,
        max_instances=1,
    )

    log_event(
        log_type="system",
        message=(
            f"Scheduler configured: full update at "
            f"{settings.app.scheduler_full_update_hour:02d}:"
            f"{settings.app.scheduler_full_update_minute:02d}"
        ),
    )

    return scheduler


def reschedule_full_update(scheduler: AsyncIOScheduler, hour: int, minute: int) -> None:
    """Change the run time of the daily full update job without restart."""
    scheduler.reschedule_job(
        job_id=FULL_UPDATE_JOB_ID,
        trigger=CronTrigger(hour=hour, minute=minute),
    )
    log_event(
        log_type="system",
        message=f"Scheduler updated: full update at {hour:02d}:{minute:02d}",
    )
