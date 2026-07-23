import asyncio
import logging
import random
from pathlib import Path

import httpx

from config import settings
from tor import (
    make_tor_client,
    reload_tor,
    write_bridges_file,
    sites_reachable,
    clear_user_bridges,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bridge cache
# ---------------------------------------------------------------------------


def _cache_path(name: str) -> Path:
    return settings.COLLECTOR_CACHE_DIR / f"{name}.txt"


def _read_cache(name: str) -> list[str]:
    p = _cache_path(name)
    if not p.exists():
        return []
    return [
        line.strip()
        for line in p.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]


def _write_cache(name: str, lines: list[str]) -> None:
    _cache_path(name).write_text("\n".join(lines) + "\n" if lines else "")


def _purge_cache() -> None:
    """Delete all cached bridge files so the next search downloads fresh lists."""
    for name in settings.COLLECTOR_URLS:
        p = _cache_path(name)
        if p.exists():
            p.unlink()
            log.info("Purged cache: %s", p.name)


def _total_cached() -> int:
    return sum(len(_read_cache(name)) for name in settings.COLLECTOR_URLS)


async def _download_lists(client: httpx.AsyncClient) -> bool:
    """
    Download all bridge lists from GitHub into the local cache.
    Uses the direct (non-Tor) client - these are plain GitHub URLs.
    Returns True if at least one list was downloaded successfully.
    """
    settings.COLLECTOR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    any_ok = False
    for name, url in settings.COLLECTOR_URLS.items():
        try:
            log.info("Downloading %s bridge list…", name)
            resp = await client.get(url, timeout=30.0)
            resp.raise_for_status()
            lines = [
                line.strip()
                for line in resp.text.splitlines()
                if line.strip() and not line.startswith("#")
            ]
            _write_cache(name, lines)
            log.info("  → %d %s bridges cached", len(lines), name)
            any_ok = True
        except Exception as exc:
            log.error("Failed to download %s list: %s", name, exc)
    return any_ok


# ---------------------------------------------------------------------------
# Batch selection
# ---------------------------------------------------------------------------


def _take_batch() -> list[str] | None:
    """
    Pick BRIDGES_PER_BATCH bridges from the cache distributed evenly across
    transport types (obfs4 / webtunnel / vanilla) using round-robin.

    Chosen bridges are removed from the cache so they are never reused in
    subsequent rotation attempts.  Returns None when the cache is empty.
    """
    pools = {name: _read_cache(name) for name in settings.COLLECTOR_URLS}
    active = {name: pool for name, pool in pools.items() if pool}
    if not active:
        return None

    batch: list[str] = []
    names = list(active.keys())
    random.shuffle(names)  # randomise which transport gets the extra slot

    while len(batch) < settings.BRIDGES_PER_BATCH and active:
        for name in list(names):
            if len(batch) >= settings.BRIDGES_PER_BATCH:
                break
            pool = active.get(name)
            if not pool:
                names.remove(name)
                active.pop(name)
                continue
            batch.append(pool.pop(random.randrange(len(pool))))
            if not pool:
                names.remove(name)
                active.pop(name)

    # Persist unconsumed bridges back to disk
    for name in settings.COLLECTOR_URLS:
        _write_cache(name, active.get(name, pools.get(name, [])))

    log.info(
        "Batch: %d bridges selected, %d remaining in cache", len(batch), _total_cached()
    )
    return batch or None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_collector(direct_client: httpx.AsyncClient) -> None:
    """
    Search phase entry point for Mode 2.

    Rotates bridge batches until target sites become reachable through Tor,
    re-downloading lists from GitHub whenever the cache is exhausted.

    *direct_client* is a plain (non-Tor) httpx client used only for
    downloading bridge lists.  All through-Tor requests create a fresh
    Tor client via make_tor_client() to avoid reusing stale connections.
    """
    log.info("Bridge search phase started")

    while True:
        if _total_cached() == 0:
            log.info("Cache empty - downloading bridge lists…")
            if not await _download_lists(direct_client):
                log.error(
                    "All sources failed - retrying in %ds", settings.SCAN_RETRY_DELAY
                )
                await asyncio.sleep(settings.SCAN_RETRY_DELAY)
                continue

        batch = _take_batch()
        if batch is None:
            log.warning(
                "No bridges after download - retrying in %ds", settings.SCAN_RETRY_DELAY
            )
            await asyncio.sleep(settings.SCAN_RETRY_DELAY)
            continue

        write_bridges_file(batch)
        reload_tor()

        log.info("Waiting %ds for Tor to reconnect…", settings.TOR_RECONNECT_WAIT)
        await asyncio.sleep(settings.TOR_RECONNECT_WAIT)

        async with make_tor_client() as tor_client:
            if await sites_reachable(tor_client):
                _purge_cache()
                if settings.CLEAR_USER_BRIDGES_ON_ROTATION:
                    clear_user_bridges()
                log.info("Bridges working - returning to monitoring phase")
                await asyncio.sleep(settings.TOR_POLL_INTERVAL)
                return

        log.warning("Bridges not working - %d bridge(s) left in cache", _total_cached())
