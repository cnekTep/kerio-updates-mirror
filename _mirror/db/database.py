import sqlite3
from contextlib import contextmanager
from typing import Optional, List, Dict

from flask import g
from flask_babel import gettext as _

from config.config_env import config
from db.migrations import apply_migrations
from utils.logging import write_log


def init_db() -> None:
    """Initialize database."""
    try:
        with transaction() as db:
            apply_migrations(db)  # applying all migrations
    except sqlite3.Error as e:
        write_log(log_type="system", message=_("Database initialization error: %(error)s", error=str(e)))


def get_db() -> sqlite3.Connection:
    """Get a database connection from the Flask global object or create a new one.

    Returns:
        sqlite3.Connection: Database connection with dictionary row factory.
    """
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(config.db)
        db.row_factory = sqlite3.Row  # Returns rows as dictionaries
    return db


def close_connection(exception: Optional[Exception] = None) -> None:
    """Close the database connection when the request ends.

    Args:
        exception (Optional[Exception]): Exception that might be raised during the request.
    """
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


@contextmanager
def transaction():
    """Context manager for database transactions to handle commits and rollbacks.

    Yields:
        sqlite3.Connection: Database connection with active transaction.

    Example:
        with transaction() as conn:
            conn.execute("INSERT INTO table VALUES (?)", (value,))
    """
    db = get_db()
    try:
        yield db
        db.commit()
    except sqlite3.Error:
        db.rollback()
        raise


def add_webfilter_key(lic_number: str, key: str) -> bool:
    """Add a new Web Filter key to the database.

    Args:
        lic_number: License number
        key: Web filter key

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with transaction() as db:
            db.execute("INSERT INTO webfilter (lic_number, key) VALUES (?, ?)", (lic_number, key))
        return True
    except sqlite3.Error:
        return False


def get_webfilter_key(lic_number: str) -> Optional[str]:
    """Get Web Filter key by license number.

    Args:
        lic_number: License number to look up

    Returns:
        Optional: Web filter key if found, None otherwise
    """
    db = get_db()
    cursor = db.cursor()
    try:
        result = cursor.execute("SELECT key FROM webfilter WHERE lic_number = ?", (lic_number,)).fetchone()
        return result[0] if result else None
    except sqlite3.Error:
        return None


def add_ids(name: str, version: str, file_name: str) -> bool:
    """Add an IDS system record to the database.

    Args:
        name: IDS system name
        version: IDS system version
        file_name: IDS system file name

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with transaction() as db:
            db.execute("INSERT INTO ids (name, version, file_name) VALUES (?, ?, ?)", (name, version, file_name))
        return True
    except sqlite3.Error:
        return False


def get_ids(name: str) -> Optional[Dict[str, int]]:
    """Get information about an IDS system by name.

    Args:
        name: IDS system name to look up

    Returns:
        Optional: Dictionary with 'version' and 'file_name' if found, None otherwise
    """
    db = get_db()
    cursor = db.cursor()
    try:
        result = cursor.execute("SELECT version, file_name FROM ids WHERE name = ?", (name,)).fetchone()
        if result:
            return {"version": result[0], "file_name": result[1]}
        return None
    except sqlite3.Error:
        return None


def get_all_ids_file_names() -> List[str]:
    """Get a list of all IDS file names from the database.

    Returns:
        List: List of IDS file names
    """
    db = get_db()
    cursor = db.cursor()
    try:
        rows = cursor.execute("SELECT file_name FROM ids").fetchall()
        return [row[0] for row in rows]
    except sqlite3.Error:
        return []


def update_ids(name: str, version: int, file_name: str) -> bool:
    """Update or insert information about an IDS system in the database.

    Args:
        name: IDS system name to update
        version: New IDS system version
        file_name: New IDS system file name

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with transaction() as db:
            cursor = db.execute("UPDATE ids SET version = ?, file_name = ? WHERE name = ?", (version, file_name, name))
            if cursor.rowcount == 0:
                db.execute("INSERT INTO ids (name, version, file_name) VALUES (?, ?, ?)", (name, version, file_name))
        return True
    except sqlite3.Error:
        return False
