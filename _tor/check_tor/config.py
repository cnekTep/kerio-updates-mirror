from dataclasses import dataclass, field
from pathlib import Path


def _default_internet_urls() -> list[str]:
    """URLs used to verify internet reachability (direct or Tor)."""
    return [
        "https://one.one.one.one",
        "https://dns.google",
        "http://example.com",
    ]


def _default_onionoo_urls() -> list[str]:
    base = (
        "https://onionoo.torproject.org/details"
        "?type=relay&running=true&fields=fingerprint,or_addresses,country"
    )
    return [
        base,
        f"https://icors.vercel.app/?{base}",
        "https://raw.githubusercontent.com/ValdikSS/tor-onionoo-mirror/"
        "master/details-running-relays-fingerprint-address-only.json",
        "https://bitbucket.org/ValdikSS/tor-onionoo-mirror/raw/master/"
        "details-running-relays-fingerprint-address-only.json",
    ]


def _default_collector_urls() -> dict[str, str]:
    base = (
        "https://raw.githubusercontent.com/Delta-Kronecker/"
        "Tor-Bridges-Collector/refs/heads/main/bridge"
    )
    return {
        "obfs4": f"{base}/obfs4_tested.txt",
        "webtunnel": f"{base}/webtunnel_tested.txt",
        "vanilla": f"{base}/vanilla_tested.txt",
    }


@dataclass
class Settings:
    # -------------------------------------------------------------------------
    # Operating mode
    # -------------------------------------------------------------------------
    # 0 - passive:   just run Tor, no Python monitoring
    # 1 - scanner:   scan public Onionoo relay list, find working bridges
    # 2 - collector: check target sites through Tor; if unreachable,
    #                pull pre-tested bridges from GitHub and rotate until working
    MODE: int = 2

    # -------------------------------------------------------------------------
    # Tor process
    # -------------------------------------------------------------------------
    # socks5h: DNS resolved on the proxy side - prevents DNS leaks through Tor
    TOR_SOCKS_PROXY: str = "socks5h://127.0.0.1:9050"
    TOR_CHECK_URL: str = "https://check.torproject.org"
    TOR_PID_FILE: Path = Path("/var/lib/tor/tor.pid")
    BRIDGES_FILE: Path = Path("/tor/bridges/bridges.config")
    USER_BRIDGES_FILE: Path = Path("/tor/bridges/user_bridges.config")
    # When True, Bridge lines are cleared from USER_BRIDGES_FILE after new
    # bridges are found (comment lines and blank lines are preserved)
    CLEAR_USER_BRIDGES_ON_ROTATION: bool = True

    # -------------------------------------------------------------------------
    # Internet connectivity probes (direct or Tor)
    # -------------------------------------------------------------------------
    INTERNET_CHECK_URLS: list[str] = field(default_factory=_default_internet_urls)

    # -------------------------------------------------------------------------
    # Mode 1 - Onionoo relay scanner
    # -------------------------------------------------------------------------
    ONIONOO_URLS: list[str] = field(default_factory=_default_onionoo_urls)
    MAX_BRIDGES: int = 5
    CHUNK_SIZE: int = 30  # relays probed concurrently per batch
    TCP_TIMEOUT: float = 10.0
    # TLS + Tor VERSIONS handshake instead of a plain TCP connect.
    # Much more reliable - filters out ports that are open but not actually Tor.
    VERIFY_TOR_PROTOCOL: bool = True

    # -------------------------------------------------------------------------
    # Mode 2 - GitHub bridge collector
    # -------------------------------------------------------------------------
    # Pre-tested bridge lists keyed by transport name
    COLLECTOR_URLS: dict[str, str] = field(default_factory=_default_collector_urls)
    # Local cache of downloaded bridge lists
    COLLECTOR_CACHE_DIR: Path = Path("/tor/bridges/cache")
    # Bridges written per rotation attempt
    BRIDGES_PER_BATCH: int = 10

    # -------------------------------------------------------------------------
    # Shared timing (seconds)
    # -------------------------------------------------------------------------
    STARTUP_DELAY: int = 300  # wait for Tor circuits before first check (5 min)
    TOR_POLL_INTERVAL: int = 300  # interval between healthy Tor checks (5 min)
    SCAN_RETRY_DELAY: int = 60  # pause before retrying a failed scan
    SITE_FAIL_THRESHOLD: int = (
        5  # Consecutive site-check failures before triggering bridge search
    )
    SITE_RETRY_INTERVAL: int = (
        60  # Pause between site-check retries during failure detection (seconds)
    )
    TOR_RECONNECT_WAIT: int = (
        30  # Time to wait after reloading Tor before re-checking sites (seconds)
    )


settings = Settings()
