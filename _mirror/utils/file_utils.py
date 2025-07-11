from pathlib import Path
from typing import List


def clean_directory(directory_path: Path, files_to_keep: List[str]) -> None:
    """
    Clean directory by removing files not in files_to_keep list.

    Args:
        directory_path: Path to directory to clean
        files_to_keep: List of filenames to save
    """

    for path in directory_path.iterdir():
        if path.is_file() and path.name not in files_to_keep:
            try:
                path.unlink()
            except Exception:
                pass
