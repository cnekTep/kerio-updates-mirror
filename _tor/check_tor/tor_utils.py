import asyncio
import logging
import random
import urllib.parse
from typing import Optional

import requests

from common import format_host, chunk_list, join_with_prefix


class TCPSocketChecker:
    """
    Utility class for checking TCP connectivity to a given host and port.
    """

    def __init__(self, host: str, port: int, timeout: float = 10.0):
        """
        Initialize the TCPSocketChecker.

        :param host: The host to connect to.
        :param port: The port to connect to.
        :param timeout: The timeout for the connection attempt.
        """
        self.host = host
        self.port = port
        self.timeout = timeout

    def __repr__(self) -> str:
        """
        Return a string representation of the TCPSocketChecker.

        :return: The string representation.
        """
        return f"{format_host(self.host)}:{self.port}"

    async def is_reachable(self) -> bool:
        """
        Check if the TCP connection to the host and port can be established within the timeout.

        :return: True if the connection is successful, False otherwise.
        """
        try:
            _, writer = await asyncio.wait_for(
                fut=asyncio.open_connection(host=self.host, port=self.port), timeout=self.timeout
            )  # Open connection
            writer.close()  # And close it
            await writer.wait_closed()
            return True
        except (OSError, asyncio.TimeoutError):
            return False


class TorRelayGrabber:
    """
    Utility class to fetch and parse Tor relay data from multiple sources.
    """
    def __init__(self, timeout: float = 10.0):
        """
        Initialize the grabber with a default timeout for requests.

        :param timeout: Timeout for HTTP requests, in seconds.
        """
        self.timeout = timeout

    def _fetch_data(self, url: str) -> dict[str, any]:
        """
        Fetch JSON data from a given URL.

        :param url: The URL to fetch data from.
        :return: The JSON response from the URL.
        """
        response = requests.get(url=url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def fetch_data_from_sources(self) -> Optional[dict[str, any]]:
        """
        Attempt to fetch Tor relay data from multiple URLs.

        :return:The JSON response if successful, None otherwise.
        """
        base_url = (
            "https://onionoo.torproject.org/details?type=relay&running=true&fields=fingerprint,or_addresses,country"
        )
        # Use public CORS proxy as a regular proxy in case if onionoo.torproject.org is unreachable
        urls = [
            base_url,
            "https://icors.vercel.app/?" + base_url,
            "https://github.com/ValdikSS/tor-onionoo-mirror/raw/master/details-running-relays-fingerprint-address-only.json",
            "https://bitbucket.org/ValdikSS/tor-onionoo-mirror/raw/master/details-running-relays-fingerprint-address-only.json",
        ]
        for url in urls:
            try:
                return self._fetch_data(url)
            except Exception as e:
                logging.error(f"Can't download Tor Relay data from {urllib.parse.urlparse(url).hostname}: {e}")

        return None

    def get_relays(self) -> list[dict[str, any]]:
        """
        Fetch and parse Tor relay data.

        :return: A list of relays or an empty list if no data is available.
        """
        data = self.fetch_data_from_sources()
        return data.get("relays", []) if data else []


class TorRelay:
    """
    Represents a Tor relay and provides methods to check its reachability.
    """

    def __init__(self, relay_info: dict[str, any]):
        """
        Initialize the TorRelay.

        :param relay_info: The dictionary containing the relay information.
        """
        self.relay_info = relay_info
        self.fingerprint = relay_info["fingerprint"]
        self.ip_tuples = self._parse_or_addresses(relay_info["or_addresses"])
        self.reachable: list[tuple[str, int]] = []

    def __repr__(self) -> str:
        """
        Return a string representation of the TorRelay.

        :return: The string representation.
        """
        return (
            "\n".join(self.get_reachable_addresses())
            if self.reachable
            else f"Relay {self.fingerprint}: No reachable addresses found."
        )

    def get_reachable_addresses(self) -> list[str]:
        """
        Return a list of reachable addresses in the format "host:port fingerprint".

        :return: A list of reachable addresses.
        """
        return [f"{format_host(ip)}:{port} {self.fingerprint}" for ip, port in self.reachable]

    def _parse_or_addresses(self, or_addresses: list[str]) -> list[tuple[str, int]]:
        """
        Parse OR addresses into a list of (host, port) tuples.

        :param or_addresses: The list of OR addresses.
        :return:A list of tuples containing the hostname and port.
        """
        parsed_addresses = []
        for address in or_addresses:
            parsed = urllib.parse.urlparse(f"//{address}")
            parsed_addresses .append((parsed.hostname, parsed.port))
        return parsed_addresses

    async def check_reachability(self) -> bool:
        """
        Check the reachability of the relay's OR addresses.

        :return: True if any of the addresses are reachable, False otherwise.
        """
        for ip, port in self.ip_tuples:
            checker = TCPSocketChecker(host=ip, port=port)
            if await checker.is_reachable():
                self.reachable.append((ip, port))
        return bool(self.reachable)


async def get_tor_relays(max_working_relays: int = 5) -> None:
    """
    Fetch and check Tor relays for reachability, then save the reachable relays to a file.

    :param max_working_relays: The maximum number of working relays to find.
    """
    logging.info("Tor Relay Scanner. Will scan up to 5 working relays (or until the end)")
    logging.info("Downloading Tor Relay information from Tor Metrics…")

    try:  # Download Tor Relay information using the TorRelayGrabber class
        relay_grabber = TorRelayGrabber()
        relays_info = relay_grabber.get_relays()

        logging.info("Tor Relay information downloaded!")
        logging.info("Relay scanner started...")
    except Exception as err:
        logging.error(f"ERROR: Tor Relay information can't be downloaded: {err}")
        return

    random.shuffle(relays_info)  # Shuffle the list of relays to randomize the order of checking
    working_relays: list[str] = []  # Initialize an empty list to store the working relays
    num_attempts = (len(relays_info) + 29) // 30  # Calculate the number of attempts needed to check all relays

    # Iterate over the relays in chunks of 30
    for attempt_number, relay_chunk in enumerate(chunk_list(items=relays_info, chunk_size=30), start=1):
        # Stop checking relays if the maximum number of working relays is reached
        if len(working_relays) >= max_working_relays:
            break

        # Create a list of TorRelay objects from the current chunk of relays
        test_relays = [TorRelay(info) for info in relay_chunk]
        logging.info(f"Attempt {attempt_number}/{num_attempts}")

        # Create tasks to check the reachability of each relay in the current chunk
        tasks = [asyncio.create_task(relay.check_reachability()) for relay in test_relays]
        await asyncio.gather(*tasks)  # Wait for all tasks to complete

        for relay in test_relays:  # Iterate over the relays in the current chunk and check if they are reachable
            if relay.reachable:
                # If a relay is reachable, add it to the list of working relays
                output = join_with_prefix(prefix="Bridge ", items=relay.get_reachable_addresses())
                working_relays.append(output)
                logging.info(f"Find working relay [{len(working_relays)}/{max_working_relays}]: {output}")
        if not any(relay.reachable for relay in test_relays):
            logging.info("No relays are reachable this attempt.")

    if working_relays:  # Save the working relays to a file
        with open("/etc/tor/bridges", "w") as f:
            f.write("\n".join(working_relays))
            f.write("\nUseBridges 1")
            logging.info(f"Saved {len(working_relays)} working relays to /etc/tor/bridges")
    else:
        logging.warning("No working relays found.")
