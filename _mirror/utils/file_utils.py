from pathlib import Path
from typing import List


def delete_file(path: Path) -> None:
    """
    Delete file if exists.

    Args:
        path: Path to file to delete
    """
    try:
        path.unlink()
    except Exception:
        pass


def clean_directory(dir_path: Path, files_to_keep: List[str]) -> None:
    """
    Clean directory by removing files not in files_to_keep list.

    Args:
        dir_path: Path to directory to clean
        files_to_keep: List of filenames to save
    """

    for path in dir_path.iterdir():
        if path.is_file() and path.name not in files_to_keep:
            delete_file(path)


def delete_oldest_files_until(dir_path: Path, max_folder_bytes: int) -> None:
    """
    Delete the oldest files in a directory (non-recursively) until the total size <= max_folder_bytes.
    This function is silent: it does not print, log or return anything.

    Args:
        dir_path: Path to the directory to trim
        max_folder_bytes: target max total size in bytes
    """
    # Walk the directory (top-level only) and collect regular files with mtime and size.
    files: List[tuple] = []  # list of (mtime, Path, size)
    total_size = 0

    for path in dir_path.iterdir():
        try:
            st = path.stat()  # may raise if file disappeared or permission denied
        except OSError:
            continue

        # Only consider regular files (skip sockets / device files). Follows symlinks to files.
        if not path.is_file():
            continue

        files.append((st.st_mtime, path, st.st_size))
        total_size += st.st_size

    # Nothing to do
    if total_size <= max_folder_bytes:
        return

    # Sort by mtime ascending (oldest first)
    files.sort(key=lambda x: x[0])

    for _, path, file_size in files:
        if total_size <= max_folder_bytes:
            break

        try:
            path.unlink()
            total_size -= file_size
        except OSError:
            continue

    return
