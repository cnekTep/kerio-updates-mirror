import os
import signal
import time


def delayed_restart():
    """Delayed restart after 1 second"""
    time.sleep(1)
    os.kill(1, signal.SIGTERM)
