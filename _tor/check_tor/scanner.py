import asyncio
import logging
import random
import ssl
import urllib.parse
from dataclasses import dataclass, field

import httpx
import time

from config import settings
from tor import write_bridges_file, reload_tor

log = logging.getLogger(__name__)

# Tor link-protocol VERSIONS cell (circid=0, cmd=7, versions 3–6)
# Reference: ValdikSS/tor-relay-scanner
_TOR_VERSIONS = b"\x00\x00\x07\x00\x06\x00\x03\x00\x04\x00\x05"


# ---------------------------------------------------------------------------
# TCP / TLS probes
# ---------------------------------------------------------------------------


def _random_tor_sni() -> str:
    """
    Generate a random SNI hostname for TLS negotiation.
    Real Tor clients randomise SNI to avoid TLS fingerprinting by censors.
    """
    import random as _r

    chars = "abcdefghijklmnopqrstuvwxyz234567"
    label = "".join(_r.choice(chars) for _ in range(_r.randint(4, 25)))
    return f"www.{label}.org"


async def _tcp_connect(host: str, port: int, timeout: float) -> bool:
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        return True
    except (OSError, asyncio.TimeoutError):
        return False


async def _tor_tls_handshake(host: str, port: int, timeout: float) -> bool:
    """
    Open a TLS connection and exchange a Tor VERSIONS cell.

    A plain TCP connect succeeds even when DPI or a transparent proxy
    intercepts traffic.  Verifying the Tor handshake response confirms
    the endpoint is a genuine relay, not just an open port.
    """
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE  # Tor relays use self-signed certificates

    remaining = timeout
    try:
        t0 = time.monotonic()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                host,
                port,
                ssl=ssl_ctx,
                server_hostname=_random_tor_sni(),
                ssl_handshake_timeout=remaining,
            ),
            timeout=remaining,
        )
        remaining -= time.monotonic() - t0

        writer.write(_TOR_VERSIONS)
        t0 = time.monotonic()
        await asyncio.wait_for(writer.drain(), timeout=remaining)
        remaining -= time.monotonic() - t0

        data = await asyncio.wait_for(reader.read(8192), timeout=remaining)
        remaining -= time.monotonic() - t0

        writer.close()
        await asyncio.wait_for(writer.wait_closed(), timeout=max(remaining, 0.5))

        # A valid VERSIONS response starts with the same \x00\x00 prefix
        return bool(data) and data[:2] == _TOR_VERSIONS[:2]

    except (OSError, asyncio.TimeoutError, ssl.SSLError):
        return False


async def _probe_address(host: str, port: int, verify: bool, timeout: float) -> bool:
    if verify:
        return await _tor_tls_handshake(host, port, timeout)
    return await _tcp_connect(host, port, timeout)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class _RelayAddress:
    host: str
    port: int

    def __str__(self) -> str:
        return (
            f"[{self.host}]:{self.port}"
            if ":" in self.host
            else f"{self.host}:{self.port}"
        )


@dataclass
class _TorRelay:
    fingerprint: str
    addresses: list[_RelayAddress]
    reachable: list[_RelayAddress] = field(default_factory=list)

    @classmethod
    def from_dict(cls, info: dict) -> "_TorRelay":
        addresses = []
        for raw in info.get("or_addresses", []):
            parsed = urllib.parse.urlparse(f"//{raw}")
            if parsed.hostname and parsed.port:
                addresses.append(_RelayAddress(parsed.hostname, parsed.port))
        return cls(fingerprint=info["fingerprint"], addresses=addresses)

    async def probe(self, verify: bool, timeout: float) -> bool:
        """Probe all OR addresses concurrently; populate self.reachable."""
        results = await asyncio.gather(
            *[_probe_address(a.host, a.port, verify, timeout) for a in self.addresses],
            return_exceptions=True,
        )
        self.reachable = [a for a, ok in zip(self.addresses, results) if ok is True]
        return bool(self.reachable)

    def bridge_lines(self) -> list[str]:
        return [f"Bridge {addr} {self.fingerprint}" for addr in self.reachable]


# ---------------------------------------------------------------------------
# Relay list downloader
# ---------------------------------------------------------------------------


async def _fetch_relay_list(client: httpx.AsyncClient) -> list[dict]:
    """
    Try each Onionoo mirror in order; return the relay list on first success.
    Raises RuntimeError when every source is unreachable.
    """
    for url in settings.ONIONOO_URLS:
        hostname = urllib.parse.urlparse(url).hostname or url
        try:
            resp = await client.get(url, timeout=15.0)
            resp.raise_for_status()
            relays = resp.json().get("relays", [])
            log.info("Relay list: %d entries from %s", len(relays), hostname)
            return relays
        except Exception as exc:
            log.warning("Source %s unavailable: %s", hostname, exc)
    raise RuntimeError("All Onionoo sources are unreachable")


async def _find_working_bridges(client: httpx.AsyncClient) -> list[str]:
    """Scan randomly-ordered relays in parallel batches; return up to MAX_BRIDGES Bridge lines."""
    raw = await _fetch_relay_list(client)
    random.shuffle(raw)
    relays = [_TorRelay.from_dict(r) for r in raw]

    verify = settings.VERIFY_TOR_PROTOCOL
    timeout = settings.TCP_TIMEOUT
    size = settings.CHUNK_SIZE
    total = (len(relays) + size - 1) // size
    found: list[str] = []

    log.info(
        "Scanning %d relays, batch=%d, verify_protocol=%s", len(relays), size, verify
    )

    for chunk_num, idx in enumerate(range(0, len(relays), size), start=1):
        if len(found) >= settings.MAX_BRIDGES:
            break

        batch = relays[idx : idx + size]
        log.info(
            "Batch %d/%d (found %d/%d)",
            chunk_num,
            total,
            len(found),
            settings.MAX_BRIDGES,
        )
        await asyncio.gather(*[r.probe(verify, timeout) for r in batch])

        for relay in batch:
            for line in relay.bridge_lines():
                found.append(line)
                log.info("  ✓ %s", line)
                if len(found) >= settings.MAX_BRIDGES:
                    return found

    return found


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_scanner(direct_client: httpx.AsyncClient) -> None:
    """
    Search phase entry point for Mode 1.

    Scans the Onionoo relay list until MAX_BRIDGES working bridges are found,
    writes them to BRIDGES_FILE, reloads Tor, and returns so monitoring_phase()
    can resume.  Retries indefinitely on network errors or empty results.
    """
    while True:
        try:
            bridges = await _find_working_bridges(direct_client)
        except RuntimeError as exc:
            log.error(
                "Relay list unavailable: %s - retrying in %ds",
                exc,
                settings.SCAN_RETRY_DELAY,
            )
            await asyncio.sleep(settings.SCAN_RETRY_DELAY)
            continue

        if not bridges:
            log.error(
                "No working bridges found - retrying in %ds", settings.SCAN_RETRY_DELAY
            )
            await asyncio.sleep(settings.SCAN_RETRY_DELAY)
            continue

        write_bridges_file(bridges)
        reload_tor()

        log.info("Waiting %ds for Tor to reconnect…", settings.TOR_RECONNECT_WAIT)
        await asyncio.sleep(settings.TOR_RECONNECT_WAIT)
        return
