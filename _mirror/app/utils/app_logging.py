import logging
from datetime import datetime
from typing import Union


def write_log(
    log_type: Union[str, list[str]], message: str, date: bool = True, ip: str = None
) -> None:
    """
    Write a formatted message to one or more log files with optional timestamp and IP.

    Args:
        log_type: Log destination(s) to write to (e.g., "system", ["system", "updates"])
        message: Message text to write to the log file(s)
        date: Whether to prefix the message with current timestamp
        ip: Optional IP address to include in the log entry
    """
    now_date = datetime.now().strftime("%Y.%m.%d %H:%M:%S")
    logging.warning(f"[{ip}] {message}" if ip else message)

    prefix = ""
    if date:
        prefix = f"[{now_date}] "
    if ip:
        prefix += f"[{ip}] "
    log_message = f"{prefix}{message}\n"

    log_types = [log_type] if isinstance(log_type, str) else log_type

    for log_type in log_types:
        with open(f"./logs/{log_type}.log", "a", encoding="utf-8") as f:
            f.write(log_message)


def read_last_lines(log_type: str, encoding="utf-8", lines=1000):
    """Reads the last lines from the file"""
    try:
        with open(f"./logs/{log_type}.log", "r", encoding=encoding) as file:
            all_lines = file.readlines()
            return "".join(all_lines[-lines:])
    except Exception as e:
        return f"File reading error: {e}"
