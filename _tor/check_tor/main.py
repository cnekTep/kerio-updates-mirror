import asyncio
import contextlib
import logging

import httpx

from collector import run_collector
from config import settings
from network import wait_for_internet
from scanner import run_scanner
from tor import monitoring_phase

log = logging.getLogger(__name__)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def _run() -> None:
    mode = settings.MODE
    log.info("Tor Bridge Finder - MODE=%d", mode)

    if mode == 0:
        log.info("Mode 0 (passive) - no monitoring")
        return

    async with httpx.AsyncClient() as direct_client:
        await wait_for_internet(direct_client)

        log.info(
            "Waiting %ds for Tor to establish circuits…",
            settings.STARTUP_DELAY,
        )
        await asyncio.sleep(settings.STARTUP_DELAY)

        while True:
            await monitoring_phase()

            if mode == 1:
                await run_scanner(direct_client)
            elif mode == 2:
                await run_collector(direct_client)
            else:
                log.error("Unknown MODE=%d (expected 0, 1 or 2)", mode)
                break


if __name__ == "__main__":
    _setup_logging()
    with contextlib.suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(_run())
