from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.dependencies import get_mirror_update_service
from app.utils.app_logging import log_event


async def scheduled_full_update():
    """Wrapper for scheduled mirror update task."""
    try:
        service = await get_mirror_update_service()
        await service.full_mirror_update(scheduled=True)
    except Exception as exc:
        log_event(
            log_type="errors",
            message=f"Scheduled full mirror update failed: {exc}",
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
        id="full_mirror_update",
        name="Daily full mirror update",
        replace_existing=True,
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
