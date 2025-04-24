from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from flask_babel import gettext as _

from handlers.update_mirror import update_mirror
from utils.logging import write_log


def scheduled_update_mirror(app):
    """
    A function for the scheduled launch of mirror updates.
    It will be called by the scheduler according to the schedule.

    Args:
        app: Flask Application instance
    """
    with app.app_context():
        write_log(log_type="system", message=_("Launching a planned mirror update"))
        try:
            with app.app_context():  # Creating an application context for a background task
                update_mirror()
            write_log(log_type="system", message=_("The planned mirror update has been completed"))
        except Exception as e:
            write_log(log_type="system", message=_("Error during a planned mirror update: %(err)s", err=str(e)))


def setup_scheduler(app, schedule_type="daily", hour=3, minute=0, interval_minutes=None):
    """
    Configuring the task scheduler.

    Args:
        app: Flask Application instance
        schedule_type: Schedule type ("daily" or "interval")
        hour: Hour for daily startup (0-23)
        minute: Minute for daily launch (0-59)
        interval_minutes: Interval in minutes for a recurring launch
    """
    scheduler = BackgroundScheduler()

    with app.app_context():
        if schedule_type == "daily":
            # Daily launch at the specified time
            trigger = CronTrigger(hour=hour, minute=minute)
            scheduler.add_job(
                func=scheduled_update_mirror,
                trigger=trigger,
                id="daily_mirror_update",
                name="Daily mirror updates",
                args=[app],  # Passing an instance of the application to the function
            )
            write_log(
                log_type="system",
                message=_("Daily mirror updates are set up in %(hour)02d:%(minute)02d", hour=hour, minute=minute),
            )
        else:
            # Running at regular intervals
            if not interval_minutes:
                interval_minutes = 480  # By default, every 8 hours

            trigger = IntervalTrigger(minutes=interval_minutes)
            scheduler.add_job(
                func=scheduled_update_mirror,
                trigger=trigger,
                id="interval_mirror_update",
                name=f"Mirror updates every {interval_minutes} minutes",
                args=[app],  # Passing an instance of the application to the function
            )
            write_log(
                log_type="system",
                message=_(
                    "Configured to update the mirror every %(interval_minutes)s minutes",
                    interval_minutes=interval_minutes,
                ),
            )

        scheduler.start()
        return scheduler
