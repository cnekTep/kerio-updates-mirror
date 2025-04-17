import datetime
from pathlib import Path

import logging


def setup_logging():
    """Configures basic logging"""
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%Y.%m.%d %H:%M:%S")

    # Creating a directory for logs if it does not exist
    log_dir = Path("./logs")
    log_dir.mkdir(exist_ok=True)


def write_log(log_type, message, date=True):
    """Writes a message to a log file with the specified type"""
    now_date = datetime.datetime.now().strftime("%Y.%m.%d %H:%M:%S")
    logging.info(message)
    with open(f"./logs/{log_type}.log", "a", encoding="utf-8") as f:
        if date:
            f.write(f"[{now_date}] {message}\n")
        else:
            f.write(f"{message}\n")


def read_last_lines(file_path, encoding="utf-8", lines=1000):
    """Reads the last lines from the file"""
    try:
        with open(file_path, "r", encoding=encoding) as file:
            all_lines = file.readlines()
            return "".join(all_lines[-lines:])
    except Exception as e:
        return f"File reading error: {e}"
