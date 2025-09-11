from utils.app_logging import read_last_lines


def get_system_log() -> str:
    """
    Returns the content of system.log.

    Returns:
        str: Content of the system log file.
    """
    return read_last_lines("./logs/system.log")


def get_updates_log() -> str:
    """
    Returns the content of updates.log.

    Returns:
        str: Content of the mirror updates log file.
    """
    return read_last_lines("./logs/updates.log")


def get_connections_log() -> str:
    """
    Returns the content of connections.log.

    Returns:
        str: Content of the mirror connections log file.
    """
    return read_last_lines("./logs/connections.log")
