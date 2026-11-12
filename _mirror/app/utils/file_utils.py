import contextlib
import os
import stat
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response

from app.config import settings

UPDATE_FILES_DIR = Path(f"/mirror/{settings.updates.update_dir}")
INTERNAL_PREFIX = "/internal-update-files"

# Suffix of temporary download files (internet_utils writes them, the cleanup below
# removes the leftovers), so both sides must use the same value
PART_SUFFIX = ".part"

# Leftover temporary files older than this (seconds) are stale: the download that
# created them was killed (restart, OOM) and will never finish
STALE_PART_AGE = 3600.0


def ensure_dir(path: Path) -> Path:
    # Ensure directory exists and create it if it doesn't
    path.mkdir(parents=True, exist_ok=True)
    return path


def delete_file(path: Path) -> None:
    """Silently delete a file if it exists."""
    with contextlib.suppress(OSError):
        path.unlink()


def clean_directory(dir_path: Path, files_to_keep: set[str] = frozenset()) -> None:
    """Remove all files from dir_path that are not in files_to_keep."""
    for path in dir_path.iterdir():
        if path.is_file() and path.name not in files_to_keep:
            delete_file(path)


def cleanup_stale_part_files(dir_path: Path, max_age: float = STALE_PART_AGE) -> None:
    """
    Remove leftover temporary download files (*.part) older than max_age seconds.

    A killed or restarted process cannot clean up its temporary file, and with unique
    names such leftovers are never overwritten, so they have to be removed explicitly.
    The age limit protects files of downloads that are still running (every write
    refreshes the modification time). Matches both the current hidden names
    (".<name>.<random>.part") and the old fixed "<name>.part" ones.

    Best effort (deletion goes through delete_file): files that are locked, already
    gone or not accessible are skipped.

    Args:
        dir_path: Directory to clean (searched recursively; symlinks are not followed)
        max_age: Minimum age of a file in seconds to be considered stale
    """
    cutoff = time.time() - max_age

    for root, _dirs, files in os.walk(dir_path):
        for name in files:
            if not name.endswith(PART_SUFFIX):
                continue

            path = Path(root, name)
            try:
                # lstat: never touch symlinks or anything that is not a regular file
                info = path.lstat()
            except OSError:
                # Already removed by another process or no access
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_mtime > cutoff:
                continue

            delete_file(path)


def build_file_response(file_path: Path) -> Response | FileResponse:
    """
    Returns a file to the client either directly via FastAPI (FileResponse)
    or by delegating actual byte transfer to nginx (X-Accel-Redirect),
    depending on whether the app is running behind nginx.
    """
    # Resolve ".." and symlinks first, then make sure the file stays inside the base dir
    base_dir = UPDATE_FILES_DIR.resolve()
    resolved = file_path.resolve()
    if not resolved.is_relative_to(base_dir) or not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    if not settings.has_nginx:
        # No nginx in front - app must serve the bytes itself
        return FileResponse(
            path=resolved,
            media_type="application/octet-stream",
            filename=file_path.name,
        )

    # Behind nginx - hand off actual file transfer to it.
    # Path relative to base_dir, since app and nginx mount the same
    # underlying directory at different container paths.
    relative_path = resolved.relative_to(base_dir)
    # nginx treats the value as a URI, so it must be percent-encoded
    internal_path = f"{INTERNAL_PREFIX}/{quote(relative_path.as_posix())}"

    encoded_name = quote(file_path.name)
    headers = {
        "X-Accel-Redirect": internal_path,
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
        "Content-Type": "application/octet-stream",
    }
    return Response(content=b"", headers=headers)
