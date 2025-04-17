import asyncio
import logging

import requests


async def check_internet() -> None:
    """
    Continuously check internet connectivity by trying to reach a list of sites.
    """
    sites = [
        "http://1.1.1.1",
        "http://8.8.8.8",
        "http://google.com",
        "http://ya.ru",
        "http://example.com",
        "http://github.com",
    ]
    while True:
        for site in sites:
            try:
                response = requests.get(url=site, timeout=10)
                if response.status_code == 200:
                    logging.info(f"Internet connection is working. Site, {site} is reachable.")
                    return
            except Exception:
                await asyncio.sleep(5)
        logging.error("ERROR, not internet connection! Sleep 60 seconds...")
        await asyncio.sleep(60)


async def check_tor() -> None:
    """
    Continuously check the Tor connection by attempting to reach the Tor check URL.
    """
    attempt = 1
    max_attempts = 5
    tor_check_url = "https://check.torproject.org"
    proxies = {
        "http": "socks5h://127.0.0.1:9050",
        "https": "socks5h://127.0.0.1:9050",
    }

    while attempt <= max_attempts:
        try:
            requests.get(url=tor_check_url, timeout=10, proxies=proxies)
            attempt = 1  # reset attempt counter on success
            await asyncio.sleep(600)  # wait for 10 minutes

        except Exception as err:
            logging.error(f"ERROR Tor Check [{attempt}/{max_attempts}]: {err}")
            attempt += 1
            await asyncio.sleep(10)
    raise Exception(f"ERROR Tor Check after {max_attempts} attempts!")
