import time
from typing import Dict, Any

import requests


class TorChecker:
    """
    A class for checking the status of a Tor connection at request.
    """

    def __init__(self, proxies: Dict[str, str] = None, check_url: str = "https://check.torproject.org"):

        self.proxies = proxies or {
            "http": "socks5h://172.222.0.5:9050",
            "https": "socks5h://172.222.0.5:9050",
        }
        self.check_url = check_url

        # Current status
        self.current_status = False
        self.last_check_time = 0
        self.last_error = None
        self.check_count = 0

    def check_connection(self) -> Dict[str, Any]:
        """
        Checking the connection to Tor.

        Returns:
            Dict with connection status and details
        """
        self.check_count += 1
        self.last_check_time = time.time()

        try:
            response = requests.get(url=self.check_url, timeout=20, proxies=self.proxies)

            # Checking not only the connection, but also the content of the response
            if response.status_code == 200 and "Congratulations" in response.text:
                self._handle_success()
            else:
                self._handle_failure(f"Invalid response from the server: {response.status_code}")
        except Exception as err:
            self._handle_failure(str(err))

        return self.get_status()

    def _handle_success(self):
        """Processing a successful check"""
        old_status = self.current_status
        self.current_status = True
        self.last_error = None

    def _handle_failure(self, error_msg: str):
        """Processing a failed check"""
        old_status = self.current_status
        self.current_status = False
        self.last_error = error_msg

    def get_status(self) -> Dict[str, Any]:
        """
        Getting the current Tor status.

        Returns:
            Dict with information about the status of Tor
        """
        now = time.time()
        seconds_since_check = int(now - self.last_check_time) if self.last_check_time else 0

        return {
            "status": self.current_status,
            "last_check": self.last_check_time,
            "seconds_since_check": seconds_since_check,
            "error": self.last_error,
            "check_count": self.check_count,
        }


# A global instance for use in the application
tor_checker = TorChecker()
