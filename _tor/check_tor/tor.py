import asyncio
import logging
import os
import signal

import httpx

from config import settings

log = logging.getLogger(__name__)


async def monitoring_phase() -> None:
    """
    Block until SITE_FAIL_THRESHOLD consecutive site checks fail.
    Resets the counter on any success so transient hiccups are ignored.
    """
    fails = 0
    while True:
        async with make_tor_client() as tor_client:
            reachable = await sites_reachable(tor_client)

        if reachable:
            if fails:
                log.info("Sites recovered - resetting failure counter")
            fails = 0
            log.info("Tor is useful - next check in %ds", settings.TOR_POLL_INTERVAL)
            await asyncio.sleep(settings.TOR_POLL_INTERVAL)
        else:
            fails += 1
            log.warning(
                "Site check failed [%d/%d]", fails, settings.SITE_FAIL_THRESHOLD
            )
            if fails >= settings.SITE_FAIL_THRESHOLD:
                log.warning("Entering bridge search phase")
                return
            await asyncio.sleep(settings.SITE_RETRY_INTERVAL)


def make_tor_client() -> httpx.AsyncClient:
    """
    Return an AsyncClient whose transport routes all requests through Tor.

    httpx does not support per-request proxy arguments - the proxy must be
    configured on the transport at construction time.  Always use as a
    context manager so connections are properly closed:

        async with make_tor_client() as client:
            ...
    """
    transport = httpx.AsyncHTTPTransport(proxy=settings.TOR_SOCKS_PROXY)
    return httpx.AsyncClient(transport=transport, follow_redirects=True)


def reload_tor() -> None:
    """
    Signal Tor to reload its configuration without restarting docker container.

    Sends SIGHUP via the PID read from TOR_PID_FILE.  Falls back to BusyBox
    killall when the PID file is absent (e.g. during a startup race).
    """
    pid_file = settings.TOR_PID_FILE
    try:
        if pid_file.exists():
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGHUP)
            log.info("Sent SIGHUP to Tor (PID %d)", pid)
        else:
            log.warning("PID file %s not found - falling back to killall", pid_file)
            os.system("killall -HUP tor")
    except ProcessLookupError:
        log.error("Tor process not found")
    except Exception as exc:
        log.error("Failed to reload Tor: %s", exc)


def write_bridges_file(lines: list[str]) -> None:
    """
    Write *lines* to BRIDGES_FILE, ensuring every entry has the 'Bridge ' prefix.
    """
    normalised = [
        line if line.startswith("Bridge ") else f"Bridge {line}" for line in lines
    ]
    path = settings.BRIDGES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(normalised))
    log.info("Wrote %d bridge(s) to %s", len(normalised), path)


def clear_user_bridges() -> None:
    """
    Remove all Bridge lines from USER_BRIDGES_FILE.

    Comment lines and blank lines are preserved so the user's formatting
    and instructions remain intact.  Does nothing if the file does not exist.
    """
    path = settings.USER_BRIDGES_FILE
    if not path.exists():
        return
    original = path.read_text().splitlines()
    cleaned = [line for line in original if not line.strip().startswith("Bridge ")]
    path.write_text("\n".join(cleaned) + "\n")
    removed = sum(1 for l in original if l.strip().startswith("Bridge "))
    if removed:
        log.info("Removed %d bridge(s) from %s", removed, path)


async def sites_reachable(tor_client: httpx.AsyncClient) -> bool:
    """
    Return True if at least one URL from INTERNET_CHECK_URLS responds through Tor.

    The same URL list is used for both direct internet checks (network.py) and
    through-Tor checks here - one config entry serves both purposes.
    All URLs are checked concurrently; a single success is sufficient.
    """
    results = await asyncio.gather(
        *[_check_site(tor_client, url) for url in settings.INTERNET_CHECK_URLS],
        return_exceptions=True,
    )
    ok_urls = [
        url for url, ok in zip(settings.INTERNET_CHECK_URLS, results) if ok is True
    ]
    if ok_urls:
        log.info("Reachable through Tor: %s", ", ".join(ok_urls))
        return True
    log.warning("No target sites reachable through Tor")
    return False


async def _check_site(tor_client: httpx.AsyncClient, url: str) -> bool:
    """Return True if the specified URL responds through Tor."""
    try:
        resp = await tor_client.get(url, timeout=15.0)
        return resp.status_code < 500
    except Exception:
        return False
