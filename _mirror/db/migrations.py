import sys

from alembic.command import upgrade as alembic_upgrade
from alembic.config import Config

from app.utils.app_logging import write_log


def apply_migrations() -> None:
    """
    Apply Alembic migrations before starting the application.

    This ensures database schema is up to date before any requests are handled.
    """
    try:
        write_log(log_type="system", message="Applying Alembic migrations...")
        alembic_upgrade(config=Config("alembic.ini"), revision="head")
        write_log(log_type="system", message="Alembic migrations applied successfully")
    except Exception as err:
        write_log(log_type="system", message=f"Failed to apply migrations: {str(err)}")
        sys.exit(1)
