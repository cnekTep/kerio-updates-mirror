import asyncio
import contextlib
import logging

from network_utils import check_internet, check_tor
from tor_utils import get_tor_relays


async def main_async():
    """
    Main asynchronous function that checks internet, Tor connections, and retrieves Tor relays if Tor check fails.
    """
    # Set up basic logging configuration
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    try:
        await asyncio.sleep(30)  # initial delay to let the system start
        logging.info("Internet check started...")
        await check_internet()
        logging.info("Background Tor check started...")
        await check_tor()
    except Exception as err:
        logging.error(f"Tor Check Error: {err}")
        await get_tor_relays()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(main_async())
