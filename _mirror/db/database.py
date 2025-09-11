import sqlite3
import time
from contextlib import contextmanager
from typing import Optional, List, Dict, Generator

from flask import g
from flask_babel import gettext as _

from config.config_env import config
from db.migrations import apply_migrations
from utils.app_logging import write_log


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
        db = g._database = sqlite3.connect(
            database=config.db,
            timeout=30,
            check_same_thread=False,
            isolation_level=None,
        )
        db.row_factory = sqlite3.Row  # Returns rows as dictionaries

        # Configure database for optimal performance and safety
        pragmas = [
            "PRAGMA journal_mode=WAL;",  # Enable WAL mode for better concurrency
            "PRAGMA synchronous=NORMAL;",  # Balance performance/durability
            "PRAGMA foreign_keys=ON;",  # Enable FK constraints
            "PRAGMA cache_size=10000;",  # Optimize page cache (40MB)
            "PRAGMA busy_timeout=30000;",  # Handle concurrent access
            "PRAGMA temp_store=MEMORY;",  # Store temp tables in memory
        ]

        for pragma in pragmas:
            db.execute(pragma)

    return db


def close_connection(exception: Optional[Exception] = None) -> None:
    """Close the database connection when the request ends.

    Args:
        exception (Optional[Exception]): Exception that might be raised during the request.
    """
    db = getattr(g, "_database", None)
    if db is not None:
        try:
            db.close()
        except sqlite3.Error:
            pass  # Ignore close errors


@contextmanager
def transaction(retries: int = 3) -> Generator[sqlite3.Connection, None, None]:
    """Transaction context manager with retry logic.

    Args:
        retries (int): Maximum number of retry attempts.

    Yields:
        sqlite3.Connection: Database connection with active transaction.
    """
    last_exception = None

    for attempt in range(1, retries + 1):
        db = None
        try:
            db = get_db()
            db.execute("BEGIN IMMEDIATE")  # Use IMMEDIATE to avoid upgrade locks
            yield db
            db.commit()
            return

        except sqlite3.OperationalError as e:
            _handle_rollback(db)

            # Check if this is a retryable error
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                if attempt < retries:
                    last_exception = e
                    time.sleep(0.1 * attempt)  # Simple linear backoff
                    continue
                else:
                    raise  # Last attempt failed
            else:
                raise  # Non-retryable error

        except Exception as e:
            _handle_rollback(db)
            raise

    # This should never be reached, but just in case
    if last_exception:
        raise last_exception


def _handle_rollback(db: Optional[sqlite3.Connection]) -> None:
    """Handle database rollback with error suppression.

    Args:
        db: Database connection to rollback.
    """
    if db:
        try:
            db.rollback()
        except sqlite3.Error:
            pass  # Ignore rollback errors


def add_webfilter_key(lic_number: str, key: str) -> bool:
    """Add a new or update existing Web Filter key.

    Args:
        lic_number: License number
        key: Web filter key

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with transaction() as db:
            db.execute(
                "INSERT INTO webfilter (lic_number, key) VALUES (?, ?) ON CONFLICT(lic_number) DO UPDATE SET key=excluded.key",
                (lic_number, key),
            )
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


def get_shield_matrix_version() -> Optional[int]:
    """Get Shield Matrix version from the database.

    Returns:
        Optional[int]: Shield Matrix version if found, None otherwise
    """
    db = get_db()
    cursor = db.cursor()
    try:
        result = cursor.execute("SELECT version FROM shield_matrix ORDER BY version DESC LIMIT 1").fetchone()
        return result[0] if result else None
    except sqlite3.Error:
        return None


def update_shield_matrix_version(version: int) -> bool:
    """Update or insert Shield Matrix version in the database.

    Args:
        version: New Shield Matrix version

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with transaction() as db:
            # Clear existing version and insert new one
            db.execute("DELETE FROM shield_matrix")
            db.execute("INSERT INTO shield_matrix (version) VALUES (?)", (version,))
        return True
    except sqlite3.Error:
        return False


def clear_webfilter_table() -> bool:
    """Clear the webfilter table in the database."""
    try:
        with transaction() as db:
            db.execute("DELETE FROM webfilter")
        return True
    except sqlite3.Error:
        return False


def clear_ids_table() -> bool:
    """Clear the ids table in the database."""
    try:
        with transaction() as db:
            db.execute("DELETE FROM ids")
        return True
    except sqlite3.Error:
        return False


def add_bitdefender_cache(file_name: str) -> bool:
    """Add a Bitdefender cache entry to the database.

    Args:
        file_name: Original file name

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO bitdefender_cache (file_name, last_usage) VALUES (?, datetime('now'))",
                (file_name,),
            )
        return True
    except sqlite3.Error:
        return False


def get_bitdefender_cache(file_name: str, do_update: bool = True) -> bool | dict:
    """Get Bitdefender cache entry by file path and update last_usage.

    Args:
        file_name: File name to look up
        do_update: Whether to update last_usage

    Returns:
        bool | dict: True if file exists in cache or dict with file_name and last_usage if do_update is False, False otherwise
    """
    try:
        with transaction() as db:
            # Check if file exists in cache
            result = db.execute(
                "SELECT file_name, last_usage FROM bitdefender_cache WHERE file_name = ?", (file_name,)
            ).fetchone()

            if result:
                if do_update:
                    # Update last_usage to current time
                    db.execute(
                        "UPDATE bitdefender_cache SET last_usage = datetime('now') WHERE file_name = ?", (file_name,)
                    )
                    return True
                else:
                    return result
            return False
    except sqlite3.Error:
        return False


def cleanup_bitdefender_cache(days_threshold: int = 5) -> None:
    """Remove old Bitdefender cache entries from the database.

    Args:
        days_threshold: Number of days to keep cache entries
    """
    try:
        with transaction() as db:
            db.execute(
                "DELETE FROM bitdefender_cache WHERE last_usage < datetime('now', '-' || ? || ' days')",
                (days_threshold,),
            )
    except sqlite3.Error as e:
        pass


def get_all_bitdefender_cache_file_names() -> List[str]:
    """Get a list of all bitdefender_cache file names from the database.

    Returns:
        List: List of bitdefender_cache file names
    """
    db = get_db()
    cursor = db.cursor()
    try:
        rows = cursor.execute("SELECT file_name FROM bitdefender_cache").fetchall()
        return [row[0] for row in rows]
    except sqlite3.Error:
        return []


def update_cache_last_usage_batch(file_hashes: List[str]) -> None:
    """Update last_usage for all files in the database that contain the given file hash.

    Args:
        file_hashes: List of file hashes
    """
    try:
        with transaction() as db:
            # Build OR conditions for each hash
            conditions = []
            params = []

            for hash_value in file_hashes:
                conditions.append("file_name LIKE ?")
                params.append(f"%.{hash_value}.%")

            where_clause = " OR ".join(conditions)

            db.execute(f"UPDATE bitdefender_cache SET last_usage = datetime('now') WHERE {where_clause}", params)
    except sqlite3.Error:
        pass


def add_stat_mirror_update(update_type: str, bytes_downloaded: int = 0) -> None:
    """Add a record to the stats_mirror_updates table in the database.

    Args:
        update_type: Type of update
        bytes_downloaded: Number of bytes downloaded
    """
    try:
        with transaction() as db:
            if update_type == "antivirus" and bytes_downloaded > 0:
                # Special case: Update the last antivirus record with downloaded bytes
                db.execute(
                    """
                    UPDATE stats_mirror_updates
                    SET bytes_downloaded = bytes_downloaded + ?
                    WHERE id = (SELECT id
                                FROM stats_mirror_updates
                                WHERE update_type = 'antivirus'
                                ORDER BY timestamp DESC
                                LIMIT 1)
                    """,
                    (bytes_downloaded,),
                )
            elif update_type == "shield_matrix_update":
                # Special case: Update the last shield_matrix record with downloaded bytes
                db.execute(
                    """
                    UPDATE stats_mirror_updates
                    SET bytes_downloaded = bytes_downloaded + ?
                    WHERE id = (SELECT id
                                FROM stats_mirror_updates
                                WHERE update_type = 'shield_matrix'
                                ORDER BY timestamp DESC
                                LIMIT 1)
                    """,
                    (bytes_downloaded,),
                )
            else:
                # Normal behavior: Create new record (for all types and antivirus with 0 bytes)
                db.execute(
                    """
                    INSERT INTO stats_mirror_updates (update_type, bytes_downloaded)
                    VALUES (?, ?)
                    """,
                    (update_type, bytes_downloaded),
                )
    except sqlite3.Error:
        pass


def add_stat_kerio_update(ip_address: str, update_type: str, bytes_transferred: int = 0) -> None:
    try:
        with transaction() as db:
            if update_type == "antivirus" and bytes_transferred > 0:
                # Special case: Update the last antivirus record with uploaded bytes
                db.execute(
                    """
                    UPDATE stats_kerio_updates
                    SET bytes_transferred = bytes_transferred + ?
                    WHERE id = (SELECT id
                                FROM stats_kerio_updates
                                WHERE update_type = 'antivirus'
                                ORDER BY timestamp DESC
                                LIMIT 1)
                    """,
                    (bytes_transferred,),
                )
            elif update_type == "shield_matrix_update":
                # Special case: Update the last shield_matrix record with uploaded bytes
                db.execute(
                    """
                    UPDATE stats_kerio_updates
                    SET bytes_transferred = bytes_transferred + ?
                    WHERE id = (SELECT id
                                FROM stats_kerio_updates
                                WHERE update_type = 'shield_matrix'
                                ORDER BY timestamp DESC
                                LIMIT 1)
                    """,
                    (bytes_transferred,),
                )
            else:
                # Normal behavior: Create new record (for all types and antivirus with 0 bytes)
                db.execute(
                    """
                    INSERT INTO stats_kerio_updates (ip_address, update_type, bytes_transferred)
                    VALUES (?, ?, ?)
                    """,
                    (ip_address, update_type, bytes_transferred),
                )
    except sqlite3.Error:
        pass
