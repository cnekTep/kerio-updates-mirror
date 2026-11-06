import contextlib
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response

from app.config import settings

UPDATE_FILES_DIR = Path(f"/mirror/{settings.updates.update_dir}")
INTERNAL_PREFIX = "/internal-update-files"


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
