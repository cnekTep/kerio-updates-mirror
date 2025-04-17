def read_log_file(file_path: str) -> str:
    """
    Reads and returns the content of a log file.

    Args:
        file_path (str): The path to the log file.

    Returns:
        str: The content of the log file.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"Log file not found: {file_path}"
    except Exception as e:
        return f"Failed to read log file {file_path}: {e}"


def get_system_log() -> str:
    """
    Returns the content of system.log.

    Returns:
        str: Content of the system log file.
    """
    return read_log_file("./logs/system.log")


def get_updates_log() -> str:
    """
    Returns the content of updates.log.

    Returns:
        str: Content of the mirror updates log file.
    """
    return read_log_file("./logs/updates.log")
