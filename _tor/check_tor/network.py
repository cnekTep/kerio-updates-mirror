import asyncio
import logging

import httpx

from config import settings

log = logging.getLogger(__name__)


async def wait_for_internet(client: httpx.AsyncClient) -> None:
    """Block until at least one probe URL returns HTTP 200 (direct connection)."""
    log.info("Checking internet connectivity…")
    while True:
        for url in settings.INTERNET_CHECK_URLS:
            try:
                resp = await client.get(url, timeout=5.0)
                if resp.status_code == 200:
                    log.info("Internet reachable via %s", url)
                    return
            except Exception:
                pass
        log.warning("No internet connection - retrying in 30s")
        await asyncio.sleep(30)


async def is_tor_working(tor_client: httpx.AsyncClient) -> bool:
    """
    Return True if Tor is routing traffic correctly.

    Requires a client pre-configured with the Tor transport (see tor.make_tor_client).
    Verifies both HTTP 200 and the presence of "Congratulations" in the response
    body - check.torproject.org only includes that string for genuine Tor requests.
    """
    try:
        resp = await tor_client.get(settings.TOR_CHECK_URL, timeout=10.0)
        return resp.status_code == 200 and "Congratulations" in resp.text
    except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ProxyError, OSError):
        log.debug("Tor connection failed (timeout or proxy error)")
    except Exception as exc:
        log.debug("Tor check error: %s", exc)
    return False
