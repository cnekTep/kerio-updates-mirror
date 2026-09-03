import sys

from alembic.command import upgrade as alembic_upgrade
from alembic.config import Config

from app.utils.app_logging import log_event


def apply_migrations() -> None:
    """
    Apply Alembic migrations before starting the application.

    This ensures database schema is up to date before any requests are handled.
    """
    try:
        log_event(log_type="system", message="Applying Alembic migrations...")
        alembic_upgrade(config=Config("alembic.ini"), revision="head")
        log_event(log_type="system", message="Alembic migrations applied successfully")
    except Exception as err:
        log_event(
            log_type=["system", "errors"],
            message=f"Failed to apply migrations: {str(err)}",
            notify=True,
            action_name="DB Migrations",
        )
        sys.exit(1)
