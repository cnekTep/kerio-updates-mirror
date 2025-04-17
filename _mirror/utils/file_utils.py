from pathlib import Path
from typing import List


def clean_update_files(files_to_keep: List[str]) -> None:
    """
    Deletes all update_files except files from the files_to_keep list.

    Args:
        files_to_keep: List of files to save
    """
    directory_path = Path("update_files")

    for path in directory_path.iterdir():
        if path.is_file() and path.name not in files_to_keep:
            try:
                path.unlink()
            except Exception:
                pass
