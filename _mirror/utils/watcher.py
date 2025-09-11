import atexit
import os
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import logging


class EnvChangeHandler(FileSystemEventHandler):
    """
    File system event handler that monitors .env file for modifications
    and triggers configuration reloads with throttling.
    """

    def __init__(self, config, env_path, worker_pid, min_interval=0.6) -> None:
        """
        Initialize the handler.

        Args:
            config: The configuration object that supports reload().
            env_path (str): Path to the .env file to watch.
            worker_pid (int): Process ID of the worker (for logging purposes).
            min_interval (float): Minimum interval (in seconds) between handling events.
        """
        super().__init__()
        self.config = config
        self.env_path = os.path.abspath(env_path)
        self.worker_pid = worker_pid
        self.min_interval = min_interval
        self._last_time = 0.0
        self._last_mtime = self._get_mtime()

    def _get_mtime(self) -> float | None:
        """Get the last modification time of the .env file."""
        try:
            return os.path.getmtime(self.env_path)
        except OSError:
            return None

    def _should_handle(self) -> bool:
        """
        Determine whether the current event should be handled,
        based on file modification time and debounce interval.
        """
        current_mtime = self._get_mtime()
        now = time.time()

        # Ignore if mtime has not changed AND the last event was too recent
        if current_mtime == self._last_mtime and (now - self._last_time) < self.min_interval:
            return False

        # Update state
        self._last_time = now
        self._last_mtime = current_mtime
        return True

    def on_modified(self, event) -> None:
        """
        Handle file modification events. If the watched .env file is modified,
        reload the configuration with error handling.
        """
        if event.is_directory:
            return

        if os.path.abspath(event.src_path) != self.env_path:
            return

        if not self._should_handle():
            return

        logging.info(f"[PID:{self.worker_pid}] Detected .env modification, reloading config")

        try:
            self.config.reload()
            logging.info(f"[PID:{self.worker_pid}] Configuration successfully reloaded")
        except Exception as e:
            logging.error(f"[PID:{self.worker_pid}] Error while reloading configuration: {str(e)}")


def start_env_watcher(config, env_path, worker_pid):
    """
    Start a watchdog observer to monitor changes in the .env file.

    Args:
        config: The configuration object that supports reload().
        env_path (str): Path to the .env file.
        worker_pid (int): Process ID of the worker (for logging purposes).

    Returns:
        Observer | None: The watchdog observer instance, or None if the .env file does not exist.
    """
    if not os.path.exists(env_path):
        logging.warning(f"[PID:{worker_pid}] .env file not found: {env_path}")
        return None

    observer = Observer()
    handler = EnvChangeHandler(config=config, env_path=env_path, worker_pid=worker_pid)
    watch_dir = os.path.dirname(os.path.abspath(env_path)) or "."

    observer.schedule(handler, path=watch_dir, recursive=False)
    observer.start()

    logging.info(f"[PID:{worker_pid}] Started .env watcher: {env_path}")

    # Register shutdown hook to stop the observer when the worker exits
    def stop_observer():
        try:
            observer.stop()
            observer.join(timeout=1.0)
            logging.info(f"[PID:{worker_pid}] .env watcher stopped")
        except Exception as e:
            logging.error(f"[PID:{worker_pid}] Error while stopping watcher: {str(e)}")

    # Ensure the observer is stopped on process exit
    atexit.register(stop_observer)

    return observer
