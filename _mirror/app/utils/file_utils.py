import contextlib
from pathlib import Path


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
