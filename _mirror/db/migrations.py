import sqlite3
from typing import Dict, Callable

from flask_babel import gettext as _

from utils.logging import write_log

# Dictionary with migrations - the key is the version, the value is the migration function
MIGRATIONS: Dict[float, Callable[[sqlite3.Connection], None]] = {}


def migration(version: float):
    """A decorator for registering migrations"""

    def decorator(func: Callable[[sqlite3.Connection], None]):
        MIGRATIONS[version] = func
        return func

    return decorator


@migration(1.0)
def create_initial_tables(db: sqlite3.Connection):
    """Initial migration - creation of basic tables"""
    db.execute("CREATE TABLE IF NOT EXISTS webfilter (lic_number TEXT PRIMARY KEY, key TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS ids (name TEXT PRIMARY KEY, version INTEGER, file_name TEXT)")


def get_current_db_version(db: sqlite3.Connection) -> float:
    """Get the current version of the database"""
    try:
        cursor = db.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        result = cursor.fetchone()
        return result[0] if result else 0
    except sqlite3.OperationalError:
        # The schema_version table does not exist
        return 0


def set_db_version(db: sqlite3.Connection, version: float):
    """Set database version"""
    db.execute(
        "INSERT OR REPLACE INTO schema_version (id, version, applied_at) VALUES (1, ?, datetime('now'))", (version,)
    )


def apply_migrations(db: sqlite3.Connection):
    """Apply all necessary migrations"""
    # Create a table for version tracking if there isn't one
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version
        (
            id         INTEGER PRIMARY KEY,
            version    INTEGER NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    current_version = get_current_db_version(db)
    max_version = max(MIGRATIONS.keys()) if MIGRATIONS else 0

    write_log(log_type="system", message=_("Current database version: %(version)s", version=float(current_version)))

    if current_version < max_version:
        write_log(log_type="system", message=_("Latest available version: %(version)s", version=float(max_version)))
        write_log(log_type="system", message=_("Applying migrations..."))

        # Apply migrations in order
        for version in sorted(MIGRATIONS.keys()):
            if version > current_version:
                write_log(log_type="system", message=_("Apply migration: %(version)s", version=float(version)))
                try:
                    MIGRATIONS[version](db)
                    set_db_version(db=db, version=version)
                    write_log(
                        log_type="system",
                        message=_("Migration %(version)s successfully applied", version=float(version)),
                    )
                except Exception as e:
                    write_log(
                        log_type="system",
                        message=_(
                            "Error when applying %(version)s migration: %(error)s", version=float(version), error=str(e)
                        ),
                    )
                    raise
    else:
        write_log(log_type="system", message=_("Database is up to date"))
