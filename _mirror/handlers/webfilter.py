import base64

import requests
from flask import Response

from config.config_env import config
from db.database import get_webfilter_key, add_webfilter_key
from utils.logging import write_log


def handle_webfilter():
    """Handler for Web Filter key request"""
    write_log(log_type="system", message=f"Received request for Web Filter key")
    webfilter_key = get_webfilter_key(lic_number=config.license_number)

    if not webfilter_key:
        return Response(response="404 Not found", status=404, mimetype="text/plain")

    # Create and return response with status code 200 and Web Filter key as response body
    return Response(response=webfilter_key, status=200)


def update_web_filter_key():
    """Updates Web Filter key by fetching it from Kerio server"""
    webfilter_key = get_webfilter_key(lic_number=config.license_number)

    if webfilter_key:
        write_log(log_type="system", message="Database already contains an actual Web Filter key")
        write_log(log_type="updates", message="Web Filter: database already contains an actual Web Filter key.")
        return

    write_log(log_type="system", message=f"Fetching new Web Filter key from wf-activation.kerio.com server")
    target_host = "wf-activation.kerio.com"
    url = f"https://wf-activation.kerio.com/getkey.php?id={config.license_number}&tag="
    headers = {"Host": target_host}

    # First attempt without proxy, then with proxy if configured
    for use_proxy in [False, True]:
        # Skip proxy attempt if proxy is not configured
        if use_proxy and not config.proxy:
            break

        try:
            request_params = {
                "url": url,
                "headers": headers,
                "timeout": 30,
                # "verify": False,
            }

            # Add proxy configuration if needed
            if use_proxy:
                request_params["proxies"] = {
                    "http": f"http://{config.proxy_host}:{config.proxy_port}",
                    "https": f"http://{config.proxy_host}:{config.proxy_port}",
                }

                # Add proxy authentication if configured
                if config.proxy_login:
                    auth_str = f"{config.proxy_login}:{config.proxy_password}"
                    headers["Proxy-Authorization"] = f"Basic {base64.b64encode(auth_str.encode()).decode()}"

            response = requests.get(**request_params)

            # Check for specific error messages in response
            if "Invalid product license" in response.text:
                write_log(log_type="system", message=f"Invalid license key: {config.license_number}")
                write_log(log_type="updates", message=f"Web Filter: invalid license key. {config.license_number}")
                return

            if "Product Software Maintenance expired" in response.text:
                write_log(log_type="system", message=f"License key expired: {config.license_number}")
                write_log(log_type="updates", message=f"Web Filter: license key expired. {config.license_number}")
                return

            if response.ok:
                add_webfilter_key(lic_number=config.license_number, key=response.text)  # Save key to database
                write_log(log_type="system", message=f"Received Web Filter key: {response.text.strip()}")
                write_log(log_type="updates", message=f"Web Filter: received new key - {response.text.strip()}")
                return
        except requests.RequestException as err:
            proxy_status = "with proxy" if use_proxy else "without proxy"
            write_log(log_type="system", message=f"Error fetching Web Filter key {proxy_status}: {str(err)}")

            # Log to mkc only after all attempts failed
            if use_proxy or not config.proxy:
                write_log(log_type="updates", message=f"Web Filter: error fetching Web Filter key.")
